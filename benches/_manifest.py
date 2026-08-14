"""Versioned performance endpoint and hypothesis-family manifest."""

from __future__ import annotations

import json
from itertools import product
from pathlib import Path
from typing import Any

MANIFEST_PATH = Path(__file__).with_name("performance-manifest.json")


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported performance manifest schema")
    return manifest


def expand_endpoints(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    endpoints: list[dict[str, Any]] = []
    for template in manifest["endpoint_templates"]:
        for records in manifest["record_ladder"]:
            endpoints.append(
                {
                    "id": f"{template['slug']}@{records}",
                    "module": template["module"],
                    "args": [records],
                    "section": template["section"],
                    "metric": template["metric"],
                    "sampler_metric": template["sampler_metric"],
                    "label": template["label"],
                }
            )
    endpoints.extend(dict(endpoint) for endpoint in manifest["fixed_endpoints"])
    ids = [endpoint["id"] for endpoint in endpoints]
    if len(ids) != len(set(ids)):
        raise ValueError("performance endpoint IDs must be unique")
    return endpoints


def select_family(
    name: str, manifest: dict[str, Any] | None = None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = manifest or load_manifest()
    endpoints = expand_endpoints(manifest)
    try:
        declared = manifest["families"][name]
    except KeyError as error:
        raise ValueError(f"unknown performance family: {name}") from error

    members = declared["members"]
    if members == "*":
        roles = {endpoint["id"]: "exploratory" for endpoint in endpoints}
    else:
        roles = dict(members)
    by_id = {endpoint["id"]: endpoint for endpoint in endpoints}
    missing = sorted(set(roles) - set(by_id))
    if missing:
        raise ValueError(f"performance family {name} references unknown endpoints: {missing}")

    selected = []
    for endpoint_id, role in roles.items():
        if role not in {"improvement", "non_inferiority", "exploratory"}:
            raise ValueError(f"invalid role {role!r} for {endpoint_id}")
        endpoint = dict(by_id[endpoint_id])
        endpoint["role"] = role
        selected.append(endpoint)

    family = {
        "name": name,
        "description": declared["description"],
        "pairs": declared["pairs"],
        "regression_margin_pct": declared["regression_margin_pct"],
        "improvement_margin_pct": declared["improvement_margin_pct"],
        "gating": declared["gating"],
        **manifest["defaults"],
    }
    return family, selected


def _axis_rows(panel: dict[str, Any]) -> list[dict[str, Any]]:
    axis_names = list(panel["axes"])
    rows: list[dict[str, Any]] = []
    for values in product(*(panel["axes"][name] for name in axis_names)):
        axes = dict(zip(axis_names, values, strict=True))
        row_id = panel["row_id"]
        for name, value in axes.items():
            row_id = row_id.replace(f"${name}", str(value))
        args = [
            axes[value[1:]] if isinstance(value, str) and value.startswith("$") else value
            for value in panel["args"]
        ]
        rows.append(
            {
                "panel": panel["name"],
                "row_id": row_id,
                "module": panel["module"],
                "metadata_function": panel["metadata_function"],
                "args": args,
                "metadata": axes,
            }
        )
    return rows


def expand_report_rows(manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    manifest = manifest or load_manifest()
    rows = [row for panel in manifest["absolute_report"]["panels"] for row in _axis_rows(panel)]
    row_ids = [row["row_id"] for row in rows]
    if len(row_ids) != len(set(row_ids)):
        raise ValueError("absolute-report row IDs must be unique")
    return rows


def expand_report_endpoints(manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    manifest = manifest or load_manifest()
    panel_by_name = {panel["name"]: panel for panel in manifest["absolute_report"]["panels"]}
    endpoints: list[dict[str, Any]] = []
    for row in expand_report_rows(manifest):
        for metric in panel_by_name[row["panel"]]["metrics"]:
            endpoints.append(
                {
                    "id": f"absolute:{row['row_id']}:{metric['slug']}",
                    "panel": row["panel"],
                    "row_id": row["row_id"],
                    "metric_slug": metric["slug"],
                    "module": row["module"],
                    "metadata_function": row["metadata_function"],
                    "args": row["args"],
                    "section": metric["result_path"][0],
                    "metric": metric["result_path"][1],
                    "result_path": metric["result_path"],
                    "sampler_metric": metric["sampler_metric"],
                    **({"fixed_loops": metric["fixed_loops"]} if "fixed_loops" in metric else {}),
                }
            )
    endpoint_ids = [endpoint["id"] for endpoint in endpoints]
    if len(endpoint_ids) != len(set(endpoint_ids)):
        raise ValueError("absolute-report endpoint IDs must be unique")
    return endpoints


def expand_report_cells(manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Expand one vectorized collection cell per public-report row."""

    manifest = manifest or load_manifest()
    panel_by_name = {panel["name"]: panel for panel in manifest["absolute_report"]["panels"]}
    cells: list[dict[str, Any]] = []
    for row in expand_report_rows(manifest):
        metrics = []
        for metric in panel_by_name[row["panel"]]["metrics"]:
            metrics.append(
                {
                    "endpoint_id": f"absolute:{row['row_id']}:{metric['slug']}",
                    "sampler_metric": metric["sampler_metric"],
                    "result_path": metric["result_path"],
                    **({"fixed_loops": metric["fixed_loops"]} if "fixed_loops" in metric else {}),
                }
            )
        cells.append(
            {
                "id": f"absolute-row:{row['row_id']}",
                "panel": row["panel"],
                "row_id": row["row_id"],
                "module": row["module"],
                "metadata_function": row["metadata_function"],
                "args": row["args"],
                "metrics": metrics,
            }
        )
    return cells


def expand_report_comparisons(
    manifest: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    manifest = manifest or load_manifest()
    endpoints = expand_report_endpoints(manifest)
    endpoints_by_row_slug = {
        (endpoint["row_id"], endpoint["metric_slug"]): endpoint["id"] for endpoint in endpoints
    }
    rows_by_panel: dict[str, list[dict[str, Any]]] = {}
    for row in expand_report_rows(manifest):
        rows_by_panel.setdefault(row["panel"], []).append(row)

    comparisons: list[dict[str, Any]] = []
    for template in manifest["absolute_report"]["comparison_templates"]:
        for row in rows_by_panel[template["panel"]]:
            candidate = endpoints_by_row_slug[row["row_id"], template["candidate_slug"]]
            reference = endpoints_by_row_slug[row["row_id"], template["reference_slug"]]
            comparisons.append(
                {
                    "id": f"{template['family']}:{row['row_id']}",
                    "family": template["family"],
                    "row_id": row["row_id"],
                    "candidate_id": candidate,
                    "reference_id": reference,
                    "margin_pct": template["margin_pct"],
                }
            )
    return comparisons
