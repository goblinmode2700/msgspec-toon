"""Format validated R-owned performance evidence for the public report."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from _panel import file_sha256, validate_absolute_raw, validate_r_report_result

ANALYZER = Path(__file__).with_name("analyze_report.R")


def _set_path(target: dict[str, Any], path: list[str], value: Any) -> None:
    current = target
    for key in path[:-1]:
        current = current.setdefault(key, {})
    current[path[-1]] = value


def _row_order(raw: dict[str, Any]) -> list[str]:
    calibration_rows = raw["calibration"]["worker"]["rows"]
    return [row["row_id"] for row in calibration_rows]


def load_report_performance(raw_path: Path, result_path: Path) -> dict[str, Any]:
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    validate_absolute_raw(raw)
    validate_r_report_result(
        result,
        raw_sha256=file_sha256(raw_path),
        analyzer_sha256=file_sha256(ANALYZER),
    )
    if raw.get("qualification_override"):
        raise ValueError("qualification-design evidence cannot feed the public report")
    if result.get("run_id") != raw.get("run_id"):
        raise ValueError("R absolute analysis does not match the collection run")

    endpoints = {endpoint["id"]: endpoint for endpoint in raw["endpoints"]}
    rows = {row_id: copy.deepcopy(row["metadata"]) for row_id, row in raw["rows"].items()}
    for row_id, row in rows.items():
        row["performance_row_id"] = row_id
    summaries = {summary["id"]: summary for summary in result["endpoint_summaries"]}
    if set(summaries) != set(endpoints):
        raise ValueError("R absolute analysis did not summarize the complete endpoint panel")

    for endpoint_id, endpoint in endpoints.items():
        summary = summaries[endpoint_id]
        row = rows[endpoint["row_id"]]
        _set_path(row, endpoint["result_path"], summary["mean_us"])
        row.setdefault("worker_spread_pct", {})[".".join(endpoint["result_path"])] = summary[
            "cv_pct"
        ]

    worker_rows: dict[tuple[str, int], dict[str, Any]] = {}
    for estimate in result["worker_estimates"]:
        endpoint = endpoints[estimate["cell_id"]]
        key = (endpoint["row_id"], estimate["worker"])
        worker_row = worker_rows.setdefault(key, {})
        _set_path(worker_row, endpoint["result_path"], estimate["per_call_us"])
    for row_id, row in rows.items():
        row["worker_observations"] = [
            worker_rows[row_id, worker] for worker in range(raw["design"]["workers"])
        ]

    comparison_results = {comparison["id"]: comparison for comparison in result["comparisons"]}
    if set(comparison_results) != {comparison["id"] for comparison in raw["comparisons"]}:
        raise ValueError("R absolute analysis did not decide every declared comparison")
    gate_results = {gate["family"]: gate["decision"] for gate in result["gates"]}
    expected_gate_families = {comparison["family"] for comparison in raw["comparisons"]}
    if set(gate_results) != expected_gate_families:
        raise ValueError("R absolute analysis did not decide every declared gate family")
    if any(decision not in {"PASS", "FAIL"} for decision in gate_results.values()):
        raise ValueError("R absolute analysis emitted an invalid gate-family decision")
    for comparison in raw["comparisons"]:
        family = comparison["family"]
        row = rows[comparison["row_id"]]
        row.setdefault("gates", {})[family] = (
            comparison_results[comparison["id"]]["status"] == "meets_floor"
        )

    key_row = rows["key-cardinality@4096"]
    key_row["relative_to_smallest"] = {
        endpoint["result_path"][1]: summaries[endpoint["id"]]["relative_to_reference"]
        for endpoint in raw["endpoints"]
        if endpoint["panel"] == "key-cardinality"
    }

    ordered = [rows[row_id] for row_id in _row_order(raw)]
    return {
        "raw": raw,
        "analysis": result,
        "typed": [row for row in ordered if row.get("notes") is not None],
        "codecs": [row for row in ordered if "output_bytes" in row],
        "integration": [
            row for row in ordered if "input_json_bytes" in row and "roundtrip_us" in row
        ],
        "key_cardinality": key_row,
        "gates": gate_results,
    }
