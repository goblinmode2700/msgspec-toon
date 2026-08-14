"""Parent-side helpers for process-replicated benchmark panels."""

from __future__ import annotations

import hashlib
import json
import os
import random
import subprocess
from pathlib import Path
from typing import Any

from _manifest import (
    MANIFEST_PATH,
    expand_report_cells,
    expand_report_comparisons,
    expand_report_endpoints,
    load_manifest,
    select_family,
)

REPO = Path(__file__).resolve().parent.parent
WORKER = Path(__file__).with_name("_panel_worker.py")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def balanced_build_orders(pairs: int, seed: int) -> list[tuple[str, str]]:
    if pairs < 4 or pairs % 2:
        raise ValueError("process-pair count must be an even integer of at least four")
    orders = [
        *(("baseline", "current"),) * (pairs // 2),
        *(("current", "baseline"),) * (pairs // 2),
    ]
    random.Random(seed).shuffle(orders)
    return orders


def randomized_cells(cells: list[dict[str, Any]], *, pair: int, seed: int) -> list[dict[str, Any]]:
    ordered = list(cells)
    random.Random(f"{seed}:{pair}").shuffle(ordered)
    return ordered


def run_panel(
    python: Path,
    *,
    mode: str,
    cells: list[dict[str, Any]],
    loops_by_cell: dict[str, dict[str, int]] | None,
    target_seconds: float,
    samples: int,
    allow_instrumented: bool,
) -> dict[str, Any]:
    if not python.is_file():
        raise SystemExit(f"missing benchmark interpreter: {python}")
    request = {
        "mode": mode,
        "cells": cells,
        "loops_by_cell": loops_by_cell or {},
        "target_seconds": target_seconds,
        "samples": samples,
    }
    environment = {
        key: value for key, value in os.environ.items() if key not in {"PYTHONHOME", "PYTHONPATH"}
    }
    if allow_instrumented:
        environment["MSGSPEC_TOON_MEASURE_INSTRUMENTATION"] = "1"
    process = subprocess.run(
        [str(python), "-I", str(WORKER)],
        cwd=REPO,
        input=json.dumps(request),
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    if process.returncode != 0:
        raise SystemExit(f"panel worker failed under {python}:\n{process.stderr[-4000:]}")
    try:
        response = json.loads(process.stdout.splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise SystemExit(f"panel worker emitted invalid JSON under {python}") from error
    expected = [cell["id"] for cell in cells]
    observed = [cell["cell_id"] for cell in response.get("cells", [])]
    if response.get("mode") != mode or observed != expected:
        raise SystemExit("panel worker returned an incomplete or reordered cell set")
    return response


def calibration_loops(response: dict[str, Any]) -> dict[str, dict[str, int]]:
    if response.get("mode") != "calibrate":
        raise ValueError("loop counts require a calibration response")
    loops: dict[str, dict[str, int]] = {}
    for cell in response["cells"]:
        cell_loops: dict[str, int] = {}
        for timing in cell["timings"]:
            count = timing["loops"]
            if not isinstance(count, int) or count <= 0:
                raise ValueError(f"invalid loop count for {cell['cell_id']}")
            cell_loops[timing["sampler_metric"]] = count
        loops[cell["cell_id"]] = cell_loops
    return loops


def validate_ab_raw(evidence: dict[str, Any]) -> None:
    if evidence.get("schema_version") != 1 or evidence.get("kind") != "paired_ab_raw":
        raise ValueError("unsupported raw A/B evidence schema")
    family = evidence["family"]
    endpoints = evidence["endpoints"]
    observations = evidence["observations"]
    workers = evidence["workers"]
    endpoint_ids = [endpoint["id"] for endpoint in endpoints]
    if len(endpoint_ids) != len(set(endpoint_ids)) or not endpoint_ids:
        raise ValueError("raw evidence requires unique endpoints")

    if evidence.get("manifest_sha256") != file_sha256(MANIFEST_PATH):
        raise ValueError("raw evidence does not match the versioned performance manifest")
    manifest = load_manifest()
    declared_family, declared_endpoints = select_family(family["name"], manifest)
    fixed_family_keys = {
        "name",
        "description",
        "pairs",
        "regression_margin_pct",
        "improvement_margin_pct",
        "gating",
        "alpha",
        "target_power",
        "planning_sd_log",
        "samples_per_process",
        "target_milliseconds",
    }
    for key in fixed_family_keys:
        if family.get(key) != declared_family.get(key):
            raise ValueError(f"raw evidence changed declared family field: {key}")
    if endpoints != declared_endpoints:
        raise ValueError("raw evidence changed the declared endpoint family or order")
    pairs = family["pairs"]
    samples = family["samples_per_process"]
    expected_observations = len(endpoint_ids) * pairs * 2 * samples
    if len(observations) != expected_observations:
        raise ValueError(
            f"raw evidence has {len(observations)} observations, expected {expected_observations}"
        )
    if len(workers) != pairs * 2:
        raise ValueError("raw evidence does not contain exactly two workers per process pair")

    worker_keys = {(worker["pair"], worker["build"]) for worker in workers}
    expected_worker_keys = {
        (pair, build) for pair in range(pairs) for build in ("baseline", "current")
    }
    if worker_keys != expected_worker_keys:
        raise ValueError("raw evidence has missing or duplicate build workers")

    identities: dict[str, set[tuple[str, str, str, str, str, bool]]] = {
        "baseline": set(),
        "current": set(),
    }
    for worker in workers:
        extension = worker.get("extension", {})
        package = worker.get("package", {})
        identity = (
            worker.get("python", ""),
            package.get("path", ""),
            package.get("sha256", ""),
            extension.get("path", ""),
            extension.get("sha256", ""),
            extension.get("instrumented", False),
        )
        if not all(identity[:5]):
            raise ValueError("raw evidence lacks a complete worker identity")
        identities[worker["build"]].add(identity)
    if any(len(build_identities) != 1 for build_identities in identities.values()):
        raise ValueError("raw evidence mixes worker identities within one build")

    periods = {(worker["pair"], worker["build"]): worker["period"] for worker in workers}
    for pair in range(pairs):
        if {periods[pair, "baseline"], periods[pair, "current"]} != {1, 2}:
            raise ValueError("each A/B process pair must contain periods one and two")

    seen: set[tuple[str, int, str, int]] = set()
    for observation in observations:
        key = (
            observation["cell_id"],
            observation["pair"],
            observation["build"],
            observation["sample"],
        )
        if key in seen:
            raise ValueError(f"duplicate raw observation: {key}")
        seen.add(key)
        if observation["cell_id"] not in endpoint_ids:
            raise ValueError("raw observation references an undeclared endpoint")
        if observation["period"] != periods.get((observation["pair"], observation["build"])):
            raise ValueError("raw observation period does not match its worker")
        if observation["loops"] <= 0 or observation["elapsed_ns"] <= 0:
            raise ValueError("raw timing observations must be positive")
        forbidden = {"mean", "mean_us", "p_value", "significant", "verdict"}
        if forbidden.intersection(observation):
            raise ValueError("Python collection evidence contains an inferential aggregate")

    expected_observation_keys = {
        (endpoint_id, pair, build, sample)
        for endpoint_id in endpoint_ids
        for pair in range(pairs)
        for build in ("baseline", "current")
        for sample in range(samples)
    }
    if seen != expected_observation_keys:
        raise ValueError("raw evidence has an incomplete observation index")

    current_periods = [periods[pair, "current"] for pair in range(pairs)]
    if current_periods.count(1) != current_periods.count(2):
        raise ValueError("baseline-first and candidate-first process pairs are not balanced")

    expected_orders: dict[tuple[int, str], list[str]] = {
        (worker["pair"], worker["build"]): worker["cell_order"] for worker in workers
    }
    for pair in range(pairs):
        if expected_orders[pair, "baseline"] != expected_orders[pair, "current"]:
            raise ValueError("paired builds did not use the same randomized endpoint order")
        if set(expected_orders[pair, "baseline"]) != set(endpoint_ids):
            raise ValueError("a measured process did not execute the complete endpoint panel")
    for observation in observations:
        order = expected_orders[observation["pair"], observation["build"]]
        if observation["order_index"] != order.index(observation["cell_id"]):
            raise ValueError("raw observation order does not match its process panel")

    warmups = evidence.get("warmups", [])
    expected_warmups = len(endpoint_ids) * pairs * 2
    if len(warmups) != expected_warmups:
        raise ValueError(f"raw evidence has {len(warmups)} warmups, expected {expected_warmups}")
    if any(warmup.get("elapsed_ns", 0) <= 0 for warmup in warmups):
        raise ValueError("raw evidence must retain every positive warmup separately")


def validate_r_result(
    result: dict[str, Any],
    *,
    raw_sha256: str,
    family: str,
    endpoint_ids: set[str] | None = None,
    endpoint_roles: dict[str, str] | None = None,
    gating: bool | None = None,
    analyzer_sha256: str | None = None,
) -> None:
    if result.get("analysis_schema_version") != 1:
        raise ValueError("unsupported R analysis schema")
    if result.get("raw_sha256") != raw_sha256:
        raise ValueError("R analysis does not match the raw evidence digest")
    if analyzer_sha256 is not None and result.get("analyzer_sha256") != analyzer_sha256:
        raise ValueError("R analysis does not match the analyzer source digest")
    if result.get("family") != family:
        raise ValueError("R analysis does not match the declared family")
    if result.get("engine") != "R stats":
        raise ValueError("performance inference did not come from R stats")
    if result.get("adjustment") != "simultaneous Bonferroni intervals across the declared family":
        raise ValueError("R analysis did not use the declared family-wise adjustment")
    if result.get("gate_decision") not in {
        "PASS",
        "INCONCLUSIVE",
        "FAIL",
        "EXPLORATORY",
    }:
        raise ValueError("R analysis emitted an invalid gate decision")

    endpoints = result.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        raise ValueError("R analysis did not emit endpoint decisions")
    allowed_statuses = {
        "improvement": {"improved", "inconclusive", "regressed"},
        "non_inferiority": {"non_inferior", "inconclusive", "regressed"},
        "exploratory": {"exploratory"},
    }
    analyzed_ids: list[str] = []
    analyzed_roles: dict[str, str] = {}
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            raise ValueError(  # noqa: TRY004
                "R analysis emitted an invalid endpoint decision"
            )
        endpoint_id = endpoint.get("id")
        role = endpoint.get("role")
        status = endpoint.get("status")
        if not isinstance(endpoint_id, str) or not endpoint_id:
            raise ValueError("R analysis emitted an invalid endpoint ID")
        if (
            not isinstance(role, str)
            or not isinstance(status, str)
            or role not in allowed_statuses
            or status not in allowed_statuses[role]
        ):
            raise ValueError(f"R analysis emitted an invalid decision for endpoint {endpoint_id}")
        analyzed_ids.append(endpoint_id)
        analyzed_roles[endpoint_id] = role
    if len(analyzed_ids) != len(set(analyzed_ids)):
        raise ValueError("R analysis emitted duplicate endpoint decisions")
    if endpoint_ids is not None and set(analyzed_ids) != endpoint_ids:
        raise ValueError("R analysis did not decide the complete endpoint family")
    if endpoint_roles is not None and analyzed_roles != endpoint_roles:
        raise ValueError("R analysis changed the declared endpoint roles")

    if gating is None:
        gating = result["gate_decision"] != "EXPLORATORY"
    if not isinstance(gating, bool):
        raise ValueError("R analysis has an invalid gating mode")  # noqa: TRY004
    if gating and any(role == "exploratory" for role in analyzed_roles.values()):
        raise ValueError("gating R analysis contains an exploratory endpoint")

    expected_failures: list[str] = []
    expected_inconclusive: list[str] = []
    if gating:
        expected_failures = [
            endpoint["id"]
            for endpoint in endpoints
            if endpoint["role"] == "improvement" and endpoint["status"] != "improved"
        ]
        expected_failures.extend(
            endpoint["id"]
            for endpoint in endpoints
            if endpoint["status"] == "regressed" and endpoint["id"] not in expected_failures
        )
        for endpoint in endpoints:
            if endpoint["role"] == "non_inferiority" and endpoint["status"] == "inconclusive":
                expected_inconclusive.append(endpoint["id"])
    if result.get("failure_endpoints") != expected_failures:
        raise ValueError("R analysis failure endpoints disagree with endpoint decisions")
    if result.get("inconclusive_endpoints") != expected_inconclusive:
        raise ValueError("R analysis inconclusive endpoints disagree with endpoint decisions")

    expected_gate_decision = "EXPLORATORY"
    if gating:
        if expected_failures:
            expected_gate_decision = "FAIL"
        elif expected_inconclusive:
            expected_gate_decision = "INCONCLUSIVE"
        else:
            expected_gate_decision = "PASS"
    if result["gate_decision"] != expected_gate_decision:
        raise ValueError("R gate decision disagrees with endpoint decisions")


def validate_absolute_raw(evidence: dict[str, Any]) -> None:
    if evidence.get("schema_version") != 1 or evidence.get("kind") != "absolute_report_raw":
        raise ValueError("unsupported raw absolute-report evidence schema")
    if evidence.get("manifest_sha256") != file_sha256(MANIFEST_PATH):
        raise ValueError("absolute evidence does not match the performance manifest")
    manifest = load_manifest()
    if evidence.get("endpoints") != expand_report_endpoints(manifest):
        raise ValueError("absolute evidence changed the declared endpoint panel or order")
    if evidence.get("comparisons") != expand_report_comparisons(manifest):
        raise ValueError("absolute evidence changed the declared comparison families")

    design = evidence["design"]
    declared = manifest["absolute_report"]
    override = evidence.get("qualification_override") is True
    fixed_design_keys = (
        ("alpha",)
        if override
        else (
            "workers",
            "samples_per_process",
            "target_milliseconds",
            "alpha",
        )
    )
    for key in fixed_design_keys:
        if design.get(key) != declared.get(key):
            raise ValueError(f"absolute evidence changed declared design field: {key}")

    endpoints = evidence["endpoints"]
    endpoint_ids = [endpoint["id"] for endpoint in endpoints]
    cell_ids = [cell["id"] for cell in expand_report_cells(manifest)]
    workers = evidence["workers"]
    if len(workers) != design["workers"]:
        raise ValueError("absolute evidence has the wrong number of worker processes")
    if [worker["worker"] for worker in workers] != list(range(design["workers"])):
        raise ValueError("absolute evidence has missing or duplicate worker processes")
    identities = {
        (
            worker.get("python", ""),
            worker.get("package", {}).get("path", ""),
            worker.get("package", {}).get("sha256", ""),
            worker.get("extension", {}).get("path", ""),
            worker.get("extension", {}).get("sha256", ""),
            worker.get("extension", {}).get("instrumented", False),
        )
        for worker in workers
    }
    if len(identities) != 1 or not all(next(iter(identities))[:5]):
        raise ValueError("absolute evidence mixes or omits worker identities")
    for worker in workers:
        if set(worker["cell_order"]) != set(cell_ids):
            raise ValueError("an absolute-report worker did not execute the complete panel")

    endpoint_cell = {
        metric["endpoint_id"]: cell["id"]
        for cell in expand_report_cells(manifest)
        for metric in cell["metrics"]
    }

    observations = evidence["observations"]
    samples = design["samples_per_process"]
    expected_observations = len(endpoints) * design["workers"] * samples
    if len(observations) != expected_observations:
        raise ValueError(
            f"absolute evidence has {len(observations)} observations, "
            f"expected {expected_observations}"
        )
    seen: set[tuple[str, int, int]] = set()
    for observation in observations:
        key = (observation["cell_id"], observation["worker"], observation["sample"])
        if key in seen:
            raise ValueError(f"duplicate absolute observation: {key}")
        seen.add(key)
        if observation["cell_id"] not in endpoint_ids:
            raise ValueError("absolute observation references an undeclared endpoint")
        if observation["worker"] not in range(design["workers"]):
            raise ValueError("absolute observation references an undeclared worker")
        worker_order = workers[observation["worker"]]["cell_order"]
        expected_order_index = worker_order.index(endpoint_cell[observation["cell_id"]])
        if observation["order_index"] != expected_order_index:
            raise ValueError("absolute observation order does not match its process panel")
        if observation["loops"] <= 0 or observation["elapsed_ns"] <= 0:
            raise ValueError("absolute timing observations must be positive")
        forbidden = {"mean", "mean_us", "p_value", "significant", "verdict"}
        if forbidden.intersection(observation):
            raise ValueError("Python absolute evidence contains an inferential aggregate")

    expected_observation_keys = {
        (endpoint_id, worker, sample)
        for endpoint_id in endpoint_ids
        for worker in range(design["workers"])
        for sample in range(samples)
    }
    if seen != expected_observation_keys:
        raise ValueError("absolute evidence has an incomplete observation index")

    warmups = evidence.get("warmups", [])
    expected_warmups = len(endpoints) * design["workers"]
    if len(warmups) != expected_warmups:
        raise ValueError(
            f"absolute evidence has {len(warmups)} warmups, expected {expected_warmups}"
        )
    if any(warmup.get("elapsed_ns", 0) <= 0 for warmup in warmups):
        raise ValueError("absolute evidence must retain every warmup separately")


def validate_r_report_result(
    result: dict[str, Any], *, raw_sha256: str, analyzer_sha256: str | None = None
) -> None:
    if result.get("analysis_schema_version") != 1:
        raise ValueError("unsupported R absolute-report analysis schema")
    if result.get("raw_sha256") != raw_sha256:
        raise ValueError("R absolute analysis does not match the raw evidence digest")
    if analyzer_sha256 is not None and result.get("analyzer_sha256") != analyzer_sha256:
        raise ValueError("R absolute analysis does not match the analyzer source digest")
    if result.get("engine") != "R stats":
        raise ValueError("absolute performance inference did not come from R stats")
    if result.get("adjustment") != (
        "simultaneous Bonferroni intervals within each declared gate family"
    ):
        raise ValueError("absolute R analysis did not use the declared adjustment")
