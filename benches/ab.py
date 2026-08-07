"""Same-session A/B harness: baseline build vs current build, one session.

Runs the typed and codec benchmarks in the baseline environment (`.venv-baseline`,
built by `make baseline` from the frozen tag) and in the current one, and reports
paired deltas. Comparisons across sessions are exactly what this tool exists to
forbid: it always runs both sides itself.

**Blocks alternate.** The obvious design — run all of B, then all of C — confounds
the change under test with whatever the machine does over the next minute. Measured
in this repository: a same-commit comparison of two builds put whichever side ran
second 0.4–3.6% slower on *every* row, a penalty larger than several deltas this
project has published. So each round runs `B C C B`, which cancels a linear drift
in the paired estimates and, as a by-product, measures the drift itself: the two
baseline blocks are the same build in two positions, and their difference is the
harness's own noise floor.

Nothing here reports a single number and calls it the answer. Every block is kept
in the artifact, the reported delta is the median of the paired ratios, and the
spread across pairs is printed beside it. A delta smaller than the drift is not a
result — the output labels those rather than leaving a reader to notice.

The comparison side defaults to the frozen tag's environment, but any two
environments in this repo can be paired — `--baseline-venv .venv-g2` measures what
the G2 instrumentation costs, for example.

Usage: uv run python benches/ab.py [--records 16 64 512 4096]
                                   [--baseline-venv .venv-baseline]
                                   [--rounds 1]
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import statistics
import subprocess

REPO = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_BASELINE_VENV = ".venv-baseline"
CURRENT_PYTHON = REPO / ".venv" / "bin" / "python"

BASELINE = "baseline"
CURRENT = "current"
# One round. Alternating and symmetric: a linear drift over the round cancels in
# the paired ratios, and the two same-side blocks bracket it.
ROUND_PATTERN = (BASELINE, CURRENT, CURRENT, BASELINE)

METRICS = (
    ("typed", "decode_us", "typed_direct"),
    ("typed", "encode_us", "typed_direct_whole"),
    ("codecs", "encode_us", "msgspec_toon"),
    ("codecs", "decode_us", "msgspec_toon"),
)

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


def run_block(python: pathlib.Path, records: list[int], is_baseline: bool) -> dict:
    """Run one block.

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


def metric_value(block: dict, kind: str, section: str, metric: str, records: int) -> float:
    for row in block[kind]:
        if row["records"] == records:
            return float(row[section][metric])
    raise KeyError(f"{kind}.{section}.{metric}@{records} missing from block")


def percent(ratio: float) -> str:
    return f"{(ratio - 1) * 100:+.1f}%"


def spread_percent(values: list[float]) -> float:
    """How far apart the same measurement landed, as a percentage of the best."""
    return (max(values) / min(values) - 1) * 100


def summarize(baselines: list[float], currents: list[float]) -> dict:
    """Pair each current block with the baseline block adjacent to it.

    `B C C B` gives (B1,C1) and (C2,B2): both pairs straddle the midpoint from
    opposite directions, so a drift that grows over the round pushes them in
    opposite directions and the median lands near the true ratio.

    The noise floor is the spread among the *same* build's blocks — one binary
    measured two or more times, minutes apart. It is not a refinement of the
    delta; it is the smallest delta this session can distinguish from nothing.
    """
    pairs = [current / baseline for baseline, current in zip(baselines, currents, strict=True)]
    return {
        "baseline_us": baselines,
        "current_us": currents,
        "paired_ratios": [round(ratio, 5) for ratio in pairs],
        "median_ratio": statistics.median(pairs),
        "pair_spread_pp": (max(pairs) - min(pairs)) * 100,
        "noise_floor_pp": max(spread_percent(baselines), spread_percent(currents)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, nargs="+", default=[16, 64, 512, 4096])
    parser.add_argument(
        "--baseline-venv",
        default=DEFAULT_BASELINE_VENV,
        help="environment to compare against (default: the frozen tag's)",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=1,
        help="B C C B rounds; each adds two paired estimates per metric",
    )
    arguments = parser.parse_args()

    baseline_python = REPO / arguments.baseline_venv / "bin" / "python"
    sequence = list(ROUND_PATTERN) * arguments.rounds
    blocks: dict[str, list[dict]] = {BASELINE: [], CURRENT: []}

    for position, side in enumerate(sequence, start=1):
        python = baseline_python if side == BASELINE else CURRENT_PYTHON
        print(f"block {position}/{len(sequence)}: {side}...")
        blocks[side].append(run_block(python, arguments.records, side == BASELINE))

    if blocks[BASELINE][0]["instrumented"]:
        print(
            f"\nNOTE: {arguments.baseline_venv} carries the alloc-stats counters; "
            "part of any delta is instrumentation the current build no longer has"
        )

    results = []
    print(
        f"\n{'metric':<50} {'median':>8}  {'spread':>7}  {'noise':>7}   verdict",
    )
    for kind, section, metric in METRICS:
        for records in arguments.records:
            label = f"{kind}.{section}.{metric}@{records}"
            summary = summarize(
                [metric_value(b, kind, section, metric, records) for b in blocks[BASELINE]],
                [metric_value(b, kind, section, metric, records) for b in blocks[CURRENT]],
            )
            change_pp = abs(summary["median_ratio"] - 1) * 100
            noise_pp = summary["noise_floor_pp"]
            # A change the harness cannot separate from its own noise is not a
            # result. Saying so is the entire point of this rewrite.
            verdict = "resolved" if change_pp > noise_pp else "BELOW NOISE — not a result"
            summary |= {"metric": label, "verdict": verdict}
            results.append(summary)
            print(
                f"{label:<50} {percent(summary['median_ratio']):>8}  "
                f"{summary['pair_spread_pp']:>6.1f}pp  {noise_pp:>6.1f}pp   {verdict}"
            )

    out = REPO / "benches" / "ab-latest.json"
    out.write_text(
        json.dumps(
            {
                "records": arguments.records,
                "baseline_venv": arguments.baseline_venv,
                "block_sequence": sequence,
                "baseline_instrumented": blocks[BASELINE][0]["instrumented"],
                "current_instrumented": blocks[CURRENT][0]["instrumented"],
                "method": (
                    "alternating B C C B blocks; reported delta is the median of the paired "
                    "ratios, pair_spread_pp is their range, and noise_floor_pp is the spread "
                    "among repeated blocks of the SAME build — the smallest delta this "
                    "session can distinguish from nothing"
                ),
                "results": results,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"\nall blocks written to {out}")


if __name__ == "__main__":
    main()
