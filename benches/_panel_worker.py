"""Execute an ordered benchmark panel in one fresh Python process.

The worker performs collection only. It emits elapsed nanoseconds and loop counts;
all aggregation and inference happen in R.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

import _timing
import msgspec_toon
from msgspec_toon import _native


def _file_identity(path: Path) -> dict[str, str]:
    resolved = path.resolve()
    return {
        "path": str(resolved),
        "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
    }


def _package_identity() -> dict[str, str]:
    return _file_identity(Path(msgspec_toon.__file__))


def _extension_identity() -> dict[str, Any]:
    identity: dict[str, Any] = _file_identity(Path(_native.__file__))
    identity["instrumented"] = hasattr(_native, "alloc_stats")
    return identity


def _run_cell(
    cell: dict[str, Any],
    *,
    loops: dict[str, int] | None,
    target_seconds: float,
    samples: int,
    calibration_only: bool,
    order_index: int,
) -> dict[str, Any]:
    module = importlib.import_module(cell["module"])
    multi_metrics = cell.get("metrics")
    metrics = multi_metrics or [
        {
            "endpoint_id": cell["id"],
            "sampler_metric": cell["sampler_metric"],
            "result_path": [cell["section"], cell["metric"]],
            **({"fixed_loops": cell["fixed_loops"]} if "fixed_loops" in cell else {}),
        }
    ]
    selected = None if multi_metrics else cell["sampler_metric"]
    effective_loops = dict(loops or {})
    if calibration_only:
        effective_loops.update(
            {
                metric["sampler_metric"]: metric["fixed_loops"]
                for metric in metrics
                if "fixed_loops" in metric
            }
        )
    started_ns = time.perf_counter_ns()
    with _timing.collection_context(
        loops=effective_loops,
        selected=selected,
        target_seconds=target_seconds,
        samples=samples,
        calibration_only=calibration_only,
    ):
        result = module.sample_run(*cell["args"])
        raw = _timing.raw_timings()
        calibrated = dict(_timing.CALIBRATED)
    elapsed_ns = time.perf_counter_ns() - started_ns

    expected_metrics = {metric["sampler_metric"] for metric in metrics}
    if set(raw) != expected_metrics:
        raise RuntimeError(
            f"cell {cell['id']} collected {sorted(raw)}, expected {expected_metrics}"
        )
    if calibration_only:
        expected_calibrated = {
            metric["sampler_metric"] for metric in metrics if "fixed_loops" not in metric
        }
        if set(calibrated) != expected_calibrated:
            raise RuntimeError(
                f"cell {cell['id']} calibrated {sorted(calibrated)}, "
                f"expected {sorted(expected_calibrated)}"
            )

    timings = []
    for metric in metrics:
        sampler_metric = metric["sampler_metric"]
        timing = raw[sampler_metric]
        if not calibration_only and len(timing["elapsed_ns"]) != samples:
            raise RuntimeError(f"cell {cell['id']} did not retain every raw sample")
        section, name = metric["result_path"]
        if not calibration_only and result[section][name] <= 0:
            raise RuntimeError(f"cell {cell['id']} reported a non-positive compatibility value")
        timings.append(
            {
                "endpoint_id": metric["endpoint_id"],
                "sampler_metric": sampler_metric,
                "loops": calibrated.get(sampler_metric, timing["loops"]),
                "warmup_elapsed_ns": timing["warmup_elapsed_ns"],
                "elapsed_ns": timing["elapsed_ns"],
            }
        )

    response = {
        "cell_id": cell["id"],
        "order_index": order_index,
        "timings": timings,
        "cell_wall_ns": elapsed_ns,
    }
    if not multi_metrics:
        response.update(timings[0])
    return response


def _row_metadata(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for cell in cells:
        row_id = cell.get("row_id")
        metadata_function = cell.get("metadata_function")
        if row_id is None or metadata_function is None or row_id in seen:
            continue
        module = importlib.import_module(cell["module"])
        metadata = getattr(module, metadata_function)(*cell["args"])
        rows.append({"row_id": row_id, "panel": cell["panel"], "metadata": metadata})
        seen.add(row_id)
    return rows


def main() -> None:
    request = json.load(sys.stdin)
    mode = request["mode"]
    if mode not in {"calibrate", "measure"}:
        raise SystemExit(f"unsupported panel-worker mode: {mode}")
    cells = request["cells"]
    loops_by_cell = request.get("loops_by_cell", {})
    started_ns = time.perf_counter_ns()
    rows = _row_metadata(cells)
    results = [
        _run_cell(
            cell,
            loops=loops_by_cell.get(cell["id"]),
            target_seconds=request["target_seconds"],
            samples=request["samples"],
            calibration_only=mode == "calibrate",
            order_index=index,
        )
        for index, cell in enumerate(cells)
    ]
    response = {
        "schema_version": 1,
        "mode": mode,
        "pid": os.getpid(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "package": _package_identity(),
        "extension": _extension_identity(),
        "panel_wall_ns": time.perf_counter_ns() - started_ns,
        "rows": rows,
        "cells": results,
    }
    print(json.dumps(response, separators=(",", ":")))


if __name__ == "__main__":
    main()
