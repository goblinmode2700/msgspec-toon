"""Paired process-panel A/B collection with R-owned inference.

Python calibrates, executes, and persists raw elapsed timings. It does not calculate
performance estimates or decisions. ``benches/analyze_ab.R`` is the sole inference
authority and this entry point consumes its machine-readable decision directly.
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

from _manifest import MANIFEST_PATH, load_manifest, select_family
from _panel import (
    balanced_build_orders,
    calibration_loops,
    file_sha256,
    randomized_cells,
    run_panel,
    validate_ab_raw,
    validate_r_result,
)

REPO = Path(__file__).resolve().parent.parent
GUARD_TAG_FILE = REPO / "benches" / "GUARD_TAG"
DEFAULT_BASELINE_VENV = ".venv-guard"
DEFAULT_CURRENT_VENV = ".venv"
ANALYZER = REPO / "benches" / "analyze_ab.R"


def benchmark_points(
    records: list[int], only: str | None = None
) -> list[tuple[str, str, str, str, str, int]]:
    """Return the legacy tuple view of the manifest-declared A/B endpoints.

    Collection uses named manifest families. This compatibility view keeps the
    public benchmark-shape contract inspectable without duplicating endpoint
    definitions or participating in timing and inference.
    """
    manifest = load_manifest()
    points = [
        (
            template["module"],
            template["section"],
            template["metric"],
            template["sampler_metric"],
            f"{template['label']}@{record_count}",
            record_count,
        )
        for template in manifest["endpoint_templates"]
        if only is None or only == template["label"]
        for record_count in records
    ]
    points.extend(
        (
            endpoint["module"],
            endpoint["section"],
            endpoint["metric"],
            endpoint["sampler_metric"],
            f"{endpoint['label']}@{endpoint['args'][0]}",
            endpoint["args"][0],
        )
        for endpoint in manifest["fixed_endpoints"]
        if only is None or only == endpoint["label"]
    )
    return points


def latest_release_tag() -> str | None:
    if not GUARD_TAG_FILE.is_file():
        return None
    return GUARD_TAG_FILE.read_text(encoding="utf-8").strip() or None


def require_current_guard(venv: str) -> None:
    latest = latest_release_tag()
    if latest is None:
        return
    marker = REPO / venv / "GUARD_TAG"
    built_from = marker.read_text(encoding="utf-8").strip() if marker.exists() else None
    if built_from != latest:
        raise SystemExit(
            f"{venv} was built from {built_from or 'an unrecorded tag'}, but the latest "
            f"release is {latest}. Run `make guard`."
        )


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


def _default_outputs(baseline_venv: str, family: str) -> tuple[Path, Path]:
    role = baseline_venv.removeprefix(".venv-").removeprefix(".venv") or "current"
    suffix = role if family == "release-guard" else f"{role}-{family}"
    return (
        REPO / "benches" / f"ab-{suffix}-raw.json",
        REPO / "benches" / f"ab-{suffix}-r.json",
    )


def _append_worker(
    *,
    evidence: dict[str, Any],
    response: dict[str, Any],
    pair: int,
    build: str,
    period: int,
) -> None:
    evidence["workers"].append(
        {
            "pair": pair,
            "build": build,
            "period": period,
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
        evidence["warmups"].append(
            {
                "cell_id": cell["cell_id"],
                "pair": pair,
                "build": build,
                "period": period,
                "order_index": cell["order_index"],
                "loops": cell["loops"],
                "elapsed_ns": cell["warmup_elapsed_ns"],
            }
        )
        for sample, elapsed_ns in enumerate(cell["elapsed_ns"]):
            evidence["observations"].append(
                {
                    "cell_id": cell["cell_id"],
                    "pair": pair,
                    "build": build,
                    "period": period,
                    "order_index": cell["order_index"],
                    "sample": sample,
                    "loops": cell["loops"],
                    "elapsed_ns": elapsed_ns,
                }
            )


def collect(
    *,
    family: dict[str, Any],
    endpoints: list[dict[str, Any]],
    baseline_python: Path,
    current_python: Path,
    seed: int,
) -> dict[str, Any]:
    target_seconds = family["target_milliseconds"] / 1_000
    samples = family["samples_per_process"]
    print(
        f"calibrating {len(endpoints)} endpoints in one baseline process "
        f"({target_seconds * 1_000:g} ms target)"
    )
    calibration = run_panel(
        baseline_python,
        mode="calibrate",
        cells=endpoints,
        loops_by_cell=None,
        target_seconds=target_seconds,
        samples=samples,
        allow_instrumented=True,
    )
    loops_by_cell = calibration_loops(calibration)
    build_orders = balanced_build_orders(family["pairs"], seed)
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "kind": "paired_ab_raw",
        "run_id": str(uuid.uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        "source_revision": _source_revision(),
        "dependency_lock_sha256": _lock_digest(),
        "manifest_sha256": file_sha256(MANIFEST_PATH),
        "analysis_contract": "Python collects raw timings; R owns inference",
        "seed": seed,
        "family": family,
        "endpoints": endpoints,
        "builds": {
            "baseline": {"python": str(baseline_python), "guard_tag": latest_release_tag()},
            "current": {"python": str(current_python)},
        },
        "calibration": {
            "build": "baseline",
            "worker": calibration,
            "loops_by_cell": loops_by_cell,
        },
        "workers": [],
        "warmups": [],
        "observations": [],
    }

    for pair, order in enumerate(build_orders):
        cells = randomized_cells(endpoints, pair=pair, seed=seed)
        print(f"pair {pair + 1:>2}/{family['pairs']}: {order[0]} then {order[1]}", flush=True)
        for period, build in enumerate(order, start=1):
            python = baseline_python if build == "baseline" else current_python
            response = run_panel(
                python,
                mode="measure",
                cells=cells,
                loops_by_cell=loops_by_cell,
                target_seconds=target_seconds,
                samples=samples,
                allow_instrumented=build == "baseline",
            )
            _append_worker(
                evidence=evidence,
                response=response,
                pair=pair,
                build=build,
                period=period,
            )
    validate_ab_raw(evidence)
    return evidence


def analyze(raw_path: Path, output_path: Path, *, family: str) -> dict[str, Any]:
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
        raise SystemExit(
            "Rscript is required: Python is not permitted to perform inference"
        ) from error
    if process.returncode != 0:
        raise SystemExit(f"R analysis failed:\n{process.stderr[-4000:]}")
    try:
        result = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit("R analysis did not produce valid machine-readable evidence") from error
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    validate_r_result(
        result,
        raw_sha256=raw_sha256,
        family=family,
        endpoint_ids={endpoint["id"] for endpoint in raw["endpoints"]},
        analyzer_sha256=analyzer_sha256,
    )
    return result


def _print_result(result: dict[str, Any]) -> None:
    print(f"\nR decision: {result['gate_decision']}  adjustment={result['adjustment']}")
    print(f"{'endpoint':<43} {'effect':>9} {'interval':>24}  status")
    for endpoint in result["endpoints"]:
        interval = (
            f"[{endpoint['simultaneous_ci_lower_pct']:+.1f},"
            f" {endpoint['simultaneous_ci_upper_pct']:+.1f}]%"
        )
        print(
            f"{endpoint['id']:<43} {endpoint['estimate_pct']:>+8.1f}% "
            f"{interval:>24}  {endpoint['status']}"
        )


def main() -> None:
    manifest = load_manifest()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--family",
        choices=sorted(manifest["families"]),
        default="release-guard",
        help="predeclared endpoint family to collect",
    )
    parser.add_argument("--baseline-venv", default=DEFAULT_BASELINE_VENV)
    parser.add_argument("--current-venv", default=DEFAULT_CURRENT_VENV)
    parser.add_argument(
        "--pairs", type=int, default=None, help="predeclare a different even pair count"
    )
    parser.add_argument("--target-ms", type=float, default=None)
    parser.add_argument("--samples", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--raw-output", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--no-gate",
        action="store_true",
        help="retain the R decision but do not enforce its exit status (story/advisory runs)",
    )
    args = parser.parse_args()

    if not args.no_gate and "guard" in args.baseline_venv:
        require_current_guard(args.baseline_venv)
    family, endpoints = select_family(args.family, manifest)
    if args.pairs is not None:
        family["pairs"] = args.pairs
    if args.target_ms is not None:
        if args.target_ms <= 0:
            raise SystemExit("--target-ms must be positive")
        family["target_milliseconds"] = args.target_ms
    if args.samples is not None:
        if args.samples < 1:
            raise SystemExit("--samples must be positive")
        family["samples_per_process"] = args.samples
    seed = args.seed if args.seed is not None else secrets.randbits(63)

    baseline_python = REPO / args.baseline_venv / "bin" / "python"
    current_python = REPO / args.current_venv / "bin" / "python"
    default_raw, default_output = _default_outputs(args.baseline_venv, args.family)
    output_path = (args.output or default_output).resolve()
    raw_path = (args.raw_output or output_path.with_name(f"{output_path.stem}-raw.json")).resolve()
    if args.raw_output is None and args.output is None:
        raw_path = default_raw.resolve()

    evidence = collect(
        family=family,
        endpoints=endpoints,
        baseline_python=baseline_python,
        current_python=current_python,
        seed=seed,
    )
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    result = analyze(raw_path, output_path, family=args.family)
    _print_result(result)
    print(f"\nraw observations: {raw_path}")
    print(f"R analysis:       {output_path}")

    if not args.no_gate and result["gate_decision"] == "FAIL":
        raise SystemExit("R performance qualification failed")


if __name__ == "__main__":
    main()
