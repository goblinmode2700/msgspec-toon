"""Same-session A/B harness: baseline build vs current build, one session.

Design, in one paragraph. A block measures **one metric at one payload size**,
so it runs in about a second and an adjacent pair of blocks straddles seconds
rather than minutes — machine drift then acts on both sides almost equally and
cancels in the difference. Blocks alternate `B C C B`, which is symmetric under
a linear drift. A difference is called only when a two-sample two-tailed
Student t-test at alpha 0.95 rejects the null, the same test and alpha `pyperf`
uses; anything else is published as "no significant difference" with the
minimum detectable effect beside it, so a null result is interpretable rather
than merely unexciting.

Why not simply run both and subtract: measured in this repository, the same
build measured in two processes minutes apart differs by 2.4-4.1%, with the
second run systematically slower as the machine warms. That confound is larger
than several deltas this project has published.

The harness **fails** (non-zero exit) when a metric is significantly *slower*
than the baseline **twice**. One test at alpha 0.95 is wrong about one time in
twenty; across sixteen metrics that is a coin-flip chance of a spurious failure
per run, and a gate that cries wolf gets ignored. So a slowdown triggers an
independent confirmation run of that metric alone, and only a slowdown that
reproduces fails the build. Measured: comparing this build against itself, one
of eight metrics reported a slowdown on the first pass and none survived
confirmation. A significant speed-up is reported, never enforced: a gate that
demands improvement becomes a ratchet that eventually fails on a quiet
machine.

Usage: uv run python benches/ab.py [--records 16 64 512 4096]
                                   [--baseline-venv .venv-baseline]
                                   [--rounds 2] [--no-gate]
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import statistics
import subprocess

REPO = pathlib.Path(__file__).resolve().parent.parent
#: The gate measures against the latest release, not the distant frozen tag: a
#: baseline the current build already beats by 15-20% cannot detect a
#: regression. Measured — a 24% typed-decode slowdown read as "+2.2%, no
#: significant difference" against `v0.1.0-conformant`.
DEFAULT_BASELINE_VENV = ".venv-guard"
CURRENT_PYTHON = REPO / ".venv" / "bin" / "python"

BASELINE = "baseline"
CURRENT = "current"
#: Symmetric under a linear drift: each side is equidistant from the round's
#: midpoint, so a trend over the round biases neither.
ROUND_PATTERN = (BASELINE, CURRENT, CURRENT, BASELINE)

#: Two-tailed t critical values at alpha 0.95 by degrees of freedom. A table
#: beats a SciPy dependency for the handful of sizes this harness uses.
T_CRITICAL_95 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    18: 2.101,
    20: 2.086,
    24: 2.064,
    30: 2.042,
}
T_CRITICAL_LARGE = 1.960

#: (bench module, result section, result key, sampler metric name, label).
#: The sampler's metric name is listed, not derived from the result key: they
#: differ for half of these, and deriving it produced blocks that measured
#: nothing and reported a mean of zero.
METRICS = (
    ("bench_typed", "decode_us", "typed_direct", "decode.typed_direct", "typed decode"),
    ("bench_typed", "encode_us", "typed_direct_whole", "encode.typed_direct", "typed encode"),
    ("bench_typed", "decode_us", "keyed_document", "decode.keyed_document", "keyed decode"),
    ("bench_codecs", "decode_us", "msgspec_toon", "decode.msgspec_toon", "untyped decode"),
    ("bench_codecs", "encode_us", "msgspec_toon", "encode.msgspec_toon", "untyped encode"),
)

#: One block: one bench module's worker-side sampler at one size, reporting the
#: single metric the block exists to measure. `MSGSPEC_TOON_ONLY_METRIC` stops
#: the sampler from also timing every metric the block will discard.
PROBE = r"""
import json, sys
sys.path.insert(0, "benches")
from msgspec_toon import _native
module = __import__(sys.argv[1])
result = module.sample_run(int(sys.argv[2]))
print(json.dumps({
    "value": result[sys.argv[3]][sys.argv[4]],
    "instrumented": hasattr(_native, "alloc_stats"),
}))
"""


def latest_release_tag() -> str | None:
    """The tag the guard must be built from, derived rather than remembered."""
    proc = subprocess.run(
        ["git", "tag", "-l", "v*", "--sort=-v:refname"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    tags = [line for line in proc.stdout.splitlines() if line.strip()]
    return tags[0] if tags else None


def require_current_guard(venv: str) -> None:
    """Refuse to gate against a guard built from an older release.

    The guard's whole job is to sit close enough to the current build that a
    regression shows up. A guard left at an old tag decays into exactly the
    blind spot it exists to prevent — measured once already: a 24% slowdown
    against a baseline trailing by 15-20% read as a 2% difference. So the tag
    is checked, not promised.
    """
    latest = latest_release_tag()
    if latest is None:
        return
    marker = REPO / venv / "GUARD_TAG"
    built_from = marker.read_text().strip() if marker.exists() else None
    if built_from != latest:
        raise SystemExit(
            f"{venv} was built from {built_from or 'an unrecorded tag'}, but the latest "
            f"release is {latest}. A stale guard cannot detect a regression — run "
            f"`make guard`."
        )


def t_critical(degrees_of_freedom: int) -> float:
    if degrees_of_freedom in T_CRITICAL_95:
        return T_CRITICAL_95[degrees_of_freedom]
    if degrees_of_freedom > 30:
        return T_CRITICAL_LARGE
    return max(value for key, value in T_CRITICAL_95.items() if key <= degrees_of_freedom)


def compare(baseline: list[float], current: list[float]) -> dict:
    """Two-sample two-tailed test at alpha 0.95, plus the effect it can detect.

    The minimum detectable effect is the half-width of the interval on the
    difference, against the baseline mean: a true change smaller than this
    cannot be told from noise by this run, which is exactly what a null result
    needs beside it to mean anything.
    """
    baseline_mean, current_mean = statistics.fmean(baseline), statistics.fmean(current)
    if baseline_mean <= 0 or current_mean <= 0:
        raise SystemExit(
            "a block reported zero: the sampler metric name does not match anything the "
            "bench module measures, so nothing was timed"
        )
    if len(baseline) < 2 or len(current) < 2:
        return {
            "change_pct": (current_mean / baseline_mean - 1) * 100,
            "significant": False,
            "minimum_detectable_effect_pct": float("inf"),
        }
    standard_error = (
        statistics.variance(baseline) / len(baseline) + statistics.variance(current) / len(current)
    ) ** 0.5
    critical = t_critical(len(baseline) + len(current) - 2)
    difference = current_mean - baseline_mean
    return {
        "change_pct": difference / baseline_mean * 100,
        "significant": bool(standard_error > 0 and abs(difference) > critical * standard_error),
        "minimum_detectable_effect_pct": critical * standard_error / baseline_mean * 100,
    }


def run_block(
    python: pathlib.Path,
    module: str,
    records: int,
    section: str,
    metric: str,
    sampler_metric: str,
    is_baseline: bool,
) -> dict:
    """Run one block.

    The current side must be a clean release build — that is the claim being
    made. The baseline side is a historical artifact whose properties are
    recorded rather than policed: `v0.1.0-conformant` predates the counters
    becoming test-only and carries them in release.
    """
    if not python.exists():
        target = "guard" if "guard" in str(python) else "baseline"
        raise SystemExit(f"missing interpreter {python} — run `make {target}` first")
    environment = dict(os.environ)
    environment["MSGSPEC_TOON_ONLY_METRIC"] = sampler_metric
    if is_baseline:
        environment["MSGSPEC_TOON_MEASURE_INSTRUMENTATION"] = "1"
    proc = subprocess.run(
        [str(python), "-c", PROBE, module, str(records), section, metric],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    if proc.returncode != 0:
        raise SystemExit(f"probe failed under {python}:\n{proc.stderr[-2000:]}")
    return json.loads(proc.stdout.splitlines()[-1])


def measure_metric(
    baseline_python: pathlib.Path,
    sequence: list[str],
    module: str,
    records: int,
    section: str,
    metric: str,
    sampler_metric: str,
) -> tuple[dict, dict[str, list[float]], bool]:
    """Run the full alternating sequence for one metric and test it."""
    samples: dict[str, list[float]] = {BASELINE: [], CURRENT: []}
    instrumented = False
    for side in sequence:
        python = baseline_python if side == BASELINE else CURRENT_PYTHON
        block = run_block(
            python, module, records, section, metric, sampler_metric, side == BASELINE
        )
        samples[side].append(block["value"])
        instrumented |= side == BASELINE and block["instrumented"]
    return compare(samples[BASELINE], samples[CURRENT]), samples, instrumented


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, nargs="+", default=[16, 64, 512, 4096])
    parser.add_argument(
        "--baseline-venv",
        default=DEFAULT_BASELINE_VENV,
        help="environment to compare against (default: the guard, i.e. the latest release)",
    )
    parser.add_argument("--rounds", type=int, default=2, help="B C C B rounds per metric")
    parser.add_argument(
        "--only",
        default=None,
        choices=[label for *_, label in METRICS],
        help="measure one metric, for putting power on a single question",
    )
    parser.add_argument(
        "--no-gate",
        action="store_true",
        help="report only; do not exit non-zero on a significant slowdown",
    )
    arguments = parser.parse_args()

    # Only the gating run needs a current guard; a story or ad-hoc comparison is
    # deliberately pointed at an old build.
    if not arguments.no_gate and "guard" in arguments.baseline_venv:
        require_current_guard(arguments.baseline_venv)

    baseline_python = REPO / arguments.baseline_venv / "bin" / "python"
    sequence = list(ROUND_PATTERN) * arguments.rounds
    results = []
    baseline_instrumented = False
    regressions = []

    print(f"{'metric':<28} {'change':>9}  {'MDE':>7}   verdict")
    for module, section, metric, sampler_metric, label in METRICS:
        if arguments.only and arguments.only != label:
            continue
        for records in arguments.records:
            name = f"{label}@{records}"
            test, samples, instrumented = measure_metric(
                baseline_python, sequence, module, records, section, metric, sampler_metric
            )
            baseline_instrumented |= instrumented
            slower = test["significant"] and test["change_pct"] > 0

            confirmation = None
            if slower:
                # A single test at alpha 0.95 is wrong one time in twenty, and
                # this harness runs sixteen of them. Confirm before failing —
                # at DOUBLE the block count, because a confirmation run at the
                # same power can reproduce a borderline effect by chance twice.
                # Observed: typed encode@4096 flagged at +2.5% over two rounds
                # and came back "no significant difference" at three.
                print(f"{name:<28} {test['change_pct']:>+8.1f}%  confirming at 2x blocks...")
                confirmation, _, _ = measure_metric(
                    baseline_python, sequence * 2, module, records, section, metric, sampler_metric
                )
                slower = confirmation["significant"] and confirmation["change_pct"] > 0

            verdict = (
                ("SLOWER" if slower else "faster")
                if test["significant"]
                else "no significant difference"
            )
            if confirmation is not None and not slower:
                verdict = "slowdown did not reproduce"
            results.append(
                {
                    "metric": name,
                    "baseline_us": samples[BASELINE],
                    "current_us": samples[CURRENT],
                    "verdict": verdict,
                    "confirmation": confirmation,
                    **test,
                }
            )
            if slower:
                regressions.append(name)
            print(
                f"{name:<28} {test['change_pct']:>+8.1f}%  "
                f"{test['minimum_detectable_effect_pct']:>6.1f}%   {verdict}"
            )

    if baseline_instrumented:
        print(
            f"\nNOTE: {arguments.baseline_venv} carries the alloc-stats counters; "
            "part of any delta is instrumentation the current build no longer has"
        )

    # Named for the environment measured against, so the gate run and the story
    # run do not overwrite each other and a reader can tell them apart.
    role = arguments.baseline_venv.removeprefix(".venv-").removeprefix(".venv") or "current"
    out = REPO / "benches" / f"ab-{role}.json"
    out.write_text(
        json.dumps(
            {
                "records": arguments.records,
                "baseline_venv": arguments.baseline_venv,
                "gated": not arguments.no_gate,
                "block_sequence": sequence,
                "baseline_instrumented": baseline_instrumented,
                "method": (
                    "one metric at one size per block, alternating B C C B; two-sample "
                    "two-tailed t-test at alpha 0.95; a change smaller than the reported "
                    "minimum detectable effect is published as no significant difference; "
                    "a slowdown must reproduce in an independent confirmation run at double "
                    "the block count to fail the gate, because one test in twenty is wrong, "
                    "this runs sixteen, and a same-power confirmation can reproduce a "
                    "borderline effect twice by chance"
                ),
                "results": results,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"\nall blocks written to {out}")

    if regressions and not arguments.no_gate:
        raise SystemExit(
            f"\nSIGNIFICANT SLOWDOWN vs {arguments.baseline_venv}, reproduced on a "
            f"confirmation run: {', '.join(regressions)}"
        )


if __name__ == "__main__":
    main()
