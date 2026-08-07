"""Same-session A/B harness: baseline wheel vs current wheel, one session.

Runs a probe module (default: the typed and codec benchmarks) in the baseline
environment (`.venv-baseline`, built by `make baseline` from the frozen tag)
and in the current environment, back to back in this process's session, and
prints paired per-row deltas. Comparisons across sessions are exactly what
this tool exists to forbid: it always runs both sides itself.

The comparison side defaults to the frozen tag's environment, but any two
environments in this repo can be paired — `--baseline-venv .venv-g2` measures
what the G2 instrumentation costs, for example.

Usage: uv run python benches/ab.py [--records 16 64 512 4096]
                                   [--baseline-venv .venv-baseline]
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_BASELINE_VENV = ".venv-baseline"
CURRENT_PYTHON = REPO / ".venv" / "bin" / "python"

PROBE = r"""
import json, sys
sys.path.insert(0, "benches")
import bench_typed, bench_codecs
from msgspec_toon import _native
records = json.loads(sys.argv[1])
out = {
    "typed": [bench_typed.run(n) for n in records],
    "codecs": [bench_codecs.run(n) for n in records],
    "instrumented": hasattr(_native, "alloc_stats"),
}
print(json.dumps(out))
"""


def run_side(python: pathlib.Path, records: list[int], is_baseline: bool = False) -> dict:
    """Run one side.

    The current side must be a clean release build — that is the claim being
    made. The baseline side is a historical artifact: `v0.1.0-conformant`
    predates the counters becoming test-only and carries them in release, and
    `.venv-g2` carries them by construction. Those are properties to record in
    the artifact, not reasons to refuse the comparison.
    """
    if not python.exists():
        raise SystemExit(
            f"missing interpreter {python} — run `make baseline` first"
            if "baseline" in str(python)
            else f"missing interpreter {python}"
        )
    environment = dict(os.environ)
    if is_baseline:
        environment["MSGSPEC_TOON_MEASURE_INSTRUMENTATION"] = "1"
    proc = subprocess.run(
        [str(python), "-c", PROBE, json.dumps(records)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    if proc.returncode != 0:
        raise SystemExit(f"probe failed under {python}:\n{proc.stderr[-2000:]}")
    return json.loads(proc.stdout.splitlines()[-1])


def delta(current: float, baseline: float) -> str:
    change = (current - baseline) / baseline * 100
    return f"{change:+.1f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, nargs="+", default=[16, 64, 512, 4096])
    parser.add_argument(
        "--baseline-venv",
        default=DEFAULT_BASELINE_VENV,
        help="environment to compare against (default: the frozen tag's)",
    )
    arguments = parser.parse_args()

    baseline_python = REPO / arguments.baseline_venv / "bin" / "python"
    print(f"running baseline side ({arguments.baseline_venv})...")
    baseline = run_side(baseline_python, arguments.records, is_baseline=True)
    if baseline["instrumented"]:
        print(
            f"NOTE: {arguments.baseline_venv} carries the alloc-stats counters; "
            "part of any delta is instrumentation the current build no longer has"
        )
    print("running current side (.venv)...")
    current = run_side(CURRENT_PYTHON, arguments.records)

    pairs = []
    for kind, metric_path in (
        ("typed", ("decode_us", "typed_direct")),
        ("typed", ("encode_us", "typed_direct_whole")),
        ("codecs", ("encode_us", "msgspec_toon")),
        ("codecs", ("decode_us", "msgspec_toon")),
    ):
        section, metric = metric_path
        for base_row, cur_row in zip(baseline[kind], current[kind]):
            b = base_row[section][metric]
            c = cur_row[section][metric]
            label = f"{kind}.{section}.{metric}@{base_row['records']}"
            pairs.append({"metric": label, "baseline_us": b, "current_us": c, "delta": delta(c, b)})
            print(f"{label:<50} baseline={b:>9}  current={c:>9}  {delta(c, b)}")

    out = REPO / "benches" / "ab-latest.json"
    out.write_text(
        json.dumps(
            {
                "records": arguments.records,
                "baseline_venv": arguments.baseline_venv,
                "baseline_instrumented": baseline["instrumented"],
                "current_instrumented": current["instrumented"],
                "pairs": pairs,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"\npaired results written to {out}")


if __name__ == "__main__":
    main()
