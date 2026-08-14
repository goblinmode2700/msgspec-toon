"""Collect the absolute performance report as raw batched process panels.

Python records identities, design variables, loop counts, warmups, and elapsed
nanoseconds. ``analyze_report.R`` owns every timing aggregate and gate decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _manifest import (
    MANIFEST_PATH,
    expand_report_cells,
    expand_report_comparisons,
    expand_report_endpoints,
    load_manifest,
)
from _panel import (
    calibration_loops,
    file_sha256,
    randomized_cells,
    run_panel,
    validate_absolute_raw,
    validate_r_report_result,
)

REPO = Path(__file__).resolve().parent.parent
ANALYZER = Path(__file__).with_name("analyze_report.R")
DEFAULT_RAW = Path(__file__).with_name("report-performance-raw.json")
DEFAULT_RESULT = Path(__file__).with_name("report-performance.json")


def _source_revision() -> str:
    process = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return process.stdout.strip()


def _lock_digest() -> str:
    digest = hashlib.sha256()
    for name in ("Cargo.lock", "uv.lock"):
        path = REPO / name
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _rows_by_id(response: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["row_id"]: row for row in response["rows"]}


def _append_worker(evidence: dict[str, Any], response: dict[str, Any], *, worker: int) -> None:
    if _rows_by_id(response) != evidence["rows"]:
        raise ValueError("deterministic report metadata changed between worker processes")
    evidence["workers"].append(
        {
            "worker": worker,
            "pid": response["pid"],
            "python": response["python"],
            "platform": response["platform"],
            "machine": response["machine"],
            "package": response["package"],
            "extension": response["extension"],
            "panel_wall_ns": response["panel_wall_ns"],
            "cell_order": [cell["cell_id"] for cell in response["cells"]],
        }
    )
    for cell in response["cells"]:
        for timing in cell["timings"]:
            evidence["warmups"].append(
                {
                    "cell_id": timing["endpoint_id"],
                    "worker": worker,
                    "order_index": cell["order_index"],
                    "loops": timing["loops"],
                    "elapsed_ns": timing["warmup_elapsed_ns"],
                }
            )
            for sample, elapsed_ns in enumerate(timing["elapsed_ns"]):
                evidence["observations"].append(
                    {
                        "cell_id": timing["endpoint_id"],
                        "worker": worker,
                        "order_index": cell["order_index"],
                        "sample": sample,
                        "loops": timing["loops"],
                        "elapsed_ns": elapsed_ns,
                    }
                )


def collect(
    *,
    python: Path,
    design: dict[str, Any],
    cells: list[dict[str, Any]],
    endpoints: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
    seed: int,
    qualification_override: bool,
) -> dict[str, Any]:
    target_seconds = design["target_milliseconds"] / 1_000
    samples = design["samples_per_process"]
    print(
        f"calibrating {len(endpoints)} endpoints in {len(cells)} vectorized rows "
        f"({target_seconds * 1_000:g} ms target)"
    )
    calibration = run_panel(
        python,
        mode="calibrate",
        cells=cells,
        loops_by_cell=None,
        target_seconds=target_seconds,
        samples=samples,
        allow_instrumented=False,
    )
    loops_by_cell = calibration_loops(calibration)
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "kind": "absolute_report_raw",
        "run_id": str(uuid.uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        "source_revision": _source_revision(),
        "dependency_lock_sha256": _lock_digest(),
        "manifest_sha256": file_sha256(MANIFEST_PATH),
        "analysis_contract": "Python collects raw timings; R owns inference",
        "seed": seed,
        "qualification_override": qualification_override,
        "design": design,
        "endpoints": endpoints,
        "comparisons": comparisons,
        "rows": _rows_by_id(calibration),
        "calibration": {
            "worker": calibration,
            "loops_by_cell": loops_by_cell,
        },
        "workers": [],
        "warmups": [],
        "observations": [],
    }
    for worker in range(design["workers"]):
        ordered_cells = randomized_cells(cells, pair=worker, seed=seed)
        print(f"worker {worker + 1:>2}/{design['workers']}", flush=True)
        response = run_panel(
            python,
            mode="measure",
            cells=ordered_cells,
            loops_by_cell=loops_by_cell,
            target_seconds=target_seconds,
            samples=samples,
            allow_instrumented=False,
        )
        _append_worker(evidence, response, worker=worker)
    validate_absolute_raw(evidence)
    return evidence


def analyze(raw_path: Path, output_path: Path) -> dict[str, Any]:
    raw_sha256 = file_sha256(raw_path)
    analyzer_sha256 = file_sha256(ANALYZER)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        process = subprocess.run(
            [
                "Rscript",
                str(ANALYZER),
                str(raw_path),
                str(output_path),
                raw_sha256,
                str(MANIFEST_PATH),
                analyzer_sha256,
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise SystemExit("Rscript is required: Python cannot summarize timings") from error
    if process.returncode != 0:
        raise SystemExit(f"R absolute-report analysis failed:\n{process.stderr[-4000:]}")
    try:
        result = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit("R did not produce valid absolute-report evidence") from error
    validate_r_report_result(
        result,
        raw_sha256=raw_sha256,
        analyzer_sha256=analyzer_sha256,
    )
    return result


def main() -> None:
    manifest = load_manifest()
    declared_design = dict(manifest["absolute_report"])
    declared_design.pop("panels")
    declared_design.pop("comparison_templates")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, default=REPO / ".venv" / "bin" / "python")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--target-ms", type=float, default=None)
    parser.add_argument("--samples", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULT)
    parser.add_argument(
        "--qualification",
        action="store_true",
        help="allow predeclared design overrides for harness qualification only",
    )
    args = parser.parse_args()
    design = dict(declared_design)
    overrides = {
        "workers": args.workers,
        "target_milliseconds": args.target_ms,
        "samples_per_process": args.samples,
    }
    changed = {key: value for key, value in overrides.items() if value is not None}
    if changed and not args.qualification:
        raise SystemExit(
            "design overrides require --qualification and cannot feed a release report"
        )
    design.update(changed)
    if design["workers"] < 2 or design["samples_per_process"] < 1:
        raise SystemExit("the report requires at least two workers and one sample per process")
    if design["target_milliseconds"] <= 0:
        raise SystemExit("--target-ms must be positive")
    seed = args.seed if args.seed is not None else secrets.randbits(63)
    python = args.python if args.python.is_absolute() else REPO / args.python
    evidence = collect(
        python=python,
        design=design,
        cells=expand_report_cells(manifest),
        endpoints=expand_report_endpoints(manifest),
        comparisons=expand_report_comparisons(manifest),
        seed=seed,
        qualification_override=bool(changed),
    )
    raw_path = args.raw_output.resolve()
    output_path = args.output.resolve()
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    result = analyze(raw_path, output_path)
    decisions = {row["family"]: row["decision"] for row in result["gates"]}
    print(f"R gate decisions: {json.dumps(decisions, sort_keys=True)}")
    print(f"raw observations: {raw_path}")
    print(f"R analysis:       {output_path}")


if __name__ == "__main__":
    main()
