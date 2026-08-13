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
                                   [--current-venv .venv]
                                   [--rounds 2] [--no-gate]
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import statistics
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from _timing import LOOPS_ENV
from bench_key_cardinality import GUARD_KEY_COUNTS, metric_name, result_key

REPO = pathlib.Path(__file__).resolve().parent.parent
GUARD_TAG_FILE = REPO / "benches" / "GUARD_TAG"
#: The gate measures against the latest release, not the distant frozen tag: a
#: baseline the current build already beats by 15-20% cannot detect a
#: regression. Measured — a 24% typed-decode slowdown read as "+2.2%, no
#: significant difference" against `v0.1.0-conformant`.
DEFAULT_BASELINE_VENV = ".venv-guard"
DEFAULT_CURRENT_VENV = ".venv"

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
    (
        "bench_typed",
        "plan_us",
        "decoder_construction_cached",
        "decode.decoder_construction",
        "decoder construction",
    ),
    ("bench_typed", "decode_us", "typed_direct", "decode.typed_direct", "typed decode"),
    ("bench_typed", "decode_us", "functional", "decode.functional", "functional decode"),
    ("bench_typed", "encode_us", "typed_direct_whole", "encode.typed_direct", "typed encode"),
    ("bench_typed", "encode_us", "functional", "encode.functional", "functional encode"),
    ("bench_typed", "decode_us", "keyed_document", "decode.keyed_document", "keyed decode"),
    ("bench_typed", "decode_us", "entry_document", "decode.entry_document", "entry decode"),
    ("bench_typed", "encode_us", "entry_document", "encode.entry_document", "entry encode"),
    (
        "bench_typed",
        "encode_us",
        "wide_dict_document",
        "encode.wide_dict_document",
        "wide dict encode",
    ),
    ("bench_codecs", "decode_us", "msgspec_toon", "decode.msgspec_toon", "untyped decode"),
    ("bench_codecs", "encode_us", "msgspec_toon", "encode.msgspec_toon", "untyped encode"),
    (
        "bench_control_patterns",
        "decode_us",
        "ordinary",
        "control.decode.ordinary",
        "control ordinary decode",
    ),
    (
        "bench_control_patterns",
        "decode_us",
        "tagged_first",
        "control.decode.tagged_first",
        "control tagged-first decode",
    ),
    (
        "bench_control_patterns",
        "decode_us",
        "tagged_last",
        "control.decode.tagged_last",
        "control tagged-last decode",
    ),
    (
        "bench_control_patterns",
        "decode_us",
        "nested_concrete",
        "control.decode.nested_concrete",
        "control nested-tag decode",
    ),
    # Nested union, tag-last, quoted-tag, and integer-tag rows remain in the
    # standalone control-pattern benchmark and semantic matrix. They cannot
    # enter the release-guard A/B: v0.2.0b5 rejects those repaired forms, so
    # there is no baseline timing population to compare. Their candidate-side
    # costs were measured against exact preceding checkpoints during phases
    # 3-4; the public guard covers only surfaces both releases can execute.
    (
        "bench_control_patterns",
        "decode_us",
        "untyped_nested",
        "control.decode.untyped_nested",
        "control untyped decode",
    ),
)

# Shape-specific points use their natural sizes instead of multiplying across
# the generic record ladder. They close the 0.3.0b1 coverage hole where the
# only untyped guard row was a uniform tabular payload.
FIXED_METRICS = (
    (
        "bench_untyped_shapes",
        "decode_us",
        "nested_records",
        "decode.nested_records",
        "untyped nested-record decode",
        46,
    ),
    (
        "bench_untyped_shapes",
        "decode_us",
        "irregular",
        "decode.irregular",
        "untyped irregular decode",
        4096,
    ),
) + tuple(
    (
        "bench_key_cardinality",
        "decode_us",
        result_key(distinct_keys),
        metric_name(distinct_keys),
        f"untyped distinct-{distinct_keys}-key decode",
        4096,
    )
    for distinct_keys in GUARD_KEY_COUNTS
)


def benchmark_points(
    records: list[int], only: str | None = None
) -> list[tuple[str, str, str, str, str, int]]:
    points = [
        (module, section, metric, sampler_metric, f"{label}@{record_count}", record_count)
        for module, section, metric, sampler_metric, label in METRICS
        if not only or only == label
        for record_count in records
    ]
    points.extend(
        (module, section, metric, sampler_metric, f"{label}@{record_count}", record_count)
        for module, section, metric, sampler_metric, label, record_count in FIXED_METRICS
        if not only or only == label
    )
    return points

# v0.2.0b5 accepted valid nested concrete tags without checking the
# discriminator. The current release performs the required validation, so
# this point compares different work. Keep the measured tax and confirmation
# in every release report, but do not call it a regression against a release
# whose faster behavior was incorrect. Phase E3 attributed and accepted the
# residual; all other common metrics remain gating.
NON_GATING_SEMANTIC_COSTS = {
    "control nested-tag decode": (
        "v0.2.0b5 skipped the required nested discriminator validation; "
        "E3 attributed and accepted the residual correctness cost"
    )
}

#: One block: one bench module's worker-side sampler at one size, reporting the
#: single metric the block exists to measure. `MSGSPEC_TOON_ONLY_METRIC` stops
#: the sampler from also timing every metric the block will discard.
PROBE = r"""
import json, sys
sys.path.insert(0, "benches")
from msgspec_toon import _native
import _timing
module = __import__(sys.argv[1])
result = module.sample_run(int(sys.argv[2]))
print(json.dumps({
    "value": result[sys.argv[3]][sys.argv[4]],
    "instrumented": hasattr(_native, "alloc_stats"),
    "calibrated": _timing.CALIBRATED,
}))
"""


def latest_release_tag() -> str | None:
    """Read the explicit public-release guard tag."""
    if not GUARD_TAG_FILE.is_file():
        return None
    tag = GUARD_TAG_FILE.read_text(encoding="utf-8").strip()
    return tag or None


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
    loops: dict[str, int] | None = None,
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
    if loops:
        environment[LOOPS_ENV] = json.dumps(loops)
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


def calibrate_metric(
    baseline_python: pathlib.Path,
    current_python: pathlib.Path,
    module: str,
    records: int,
    section: str,
    metric: str,
    sampler_metric: str,
) -> dict[str, int]:
    """One discarded block per side, whose only outputs are a warm interpreter
    and the loop count both sides will then measure with.

    Loop counts used to be chosen independently inside every block, by every
    process. `_timing._calibrate` doubles from 1 until it reaches its target,
    so two builds a few percent apart near a boundary land on counts that
    differ by 2x — and then the two sides are no longer measuring the same
    amount of work, which is the one thing an A/B comparison requires. A
    freshly cut guard is additionally cold on its first run, and that run was
    the one choosing its loop count: a guard built moments earlier was
    observed calibrating to 256 loops at 323us where every later run agreed
    on 512 loops at 127us.

    The baseline's counts are the ones adopted, because the baseline is the
    reference the comparison is against; what matters is only that both sides
    use the same ones.
    """
    baseline_block = run_block(
        baseline_python, module, records, section, metric, sampler_metric, True
    )
    run_block(current_python, module, records, section, metric, sampler_metric, False)
    return baseline_block.get("calibrated") or {}


def measure_metric(
    baseline_python: pathlib.Path,
    current_python: pathlib.Path,
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
    loops = calibrate_metric(
        baseline_python, current_python, module, records, section, metric, sampler_metric
    )
    for side in sequence:
        python = baseline_python if side == BASELINE else current_python
        block = run_block(
            python, module, records, section, metric, sampler_metric, side == BASELINE, loops
        )
        samples[side].append(block["value"])
        instrumented |= side == BASELINE and block["instrumented"]
    return compare(samples[BASELINE], samples[CURRENT]), samples, instrumented


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    # 4 and 8 exist because the workload analysis (ROUND-2-DIRECTION.md) says
    # tool results are tens of records; the ladder previously started at 16
    # and equal-weighted sizes the use case rarely sees. Added, not re-weighted:
    # every prior size still runs.
    parser.add_argument("--records", type=int, nargs="+", default=[4, 8, 16, 64, 512, 4096])
    parser.add_argument(
        "--baseline-venv",
        default=DEFAULT_BASELINE_VENV,
        help="environment to compare against (default: the guard, i.e. the latest release)",
    )
    parser.add_argument(
        "--current-venv",
        default=DEFAULT_CURRENT_VENV,
        help="environment for the candidate side (default: the working-tree .venv)",
    )
    parser.add_argument("--rounds", type=int, default=2, help="B C C B rounds per metric")
    parser.add_argument(
        "--only",
        default=None,
        choices=[label for *_, label in METRICS] + [label for *_, label, _ in FIXED_METRICS],
        help="measure one metric, for putting power on a single question",
    )
    parser.add_argument(
        "--no-gate",
        action="store_true",
        help="report only; do not exit non-zero on a significant slowdown",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=None,
        help="write this focused run to a separate JSON file",
    )
    arguments = parser.parse_args()

    # Only the gating run needs a current guard; a story or ad-hoc comparison is
    # deliberately pointed at an old build.
    if not arguments.no_gate and "guard" in arguments.baseline_venv:
        require_current_guard(arguments.baseline_venv)

    baseline_python = REPO / arguments.baseline_venv / "bin" / "python"
    current_python = REPO / arguments.current_venv / "bin" / "python"
    sequence = list(ROUND_PATTERN) * arguments.rounds
    results = []
    baseline_instrumented = False
    regressions = []

    # H2: each metric's blocks used to run consecutively, so its whole sample
    # set occupied one narrow slice of a multi-minute ladder. Any slice-local
    # disturbance — a background wakeup, a thermal step — then landed almost
    # entirely inside one metric's samples, biasing its mean while leaving its
    # within-slice variance (and therefore its printed MDE) small: the gate
    # reported sub-1% confidence on a run whose real floor was ~2%, and
    # certified slowdowns on identical source. The blocks are now interleaved:
    # every block-position of the B C C B pattern runs across ALL metric
    # points before the next position runs anywhere, so each metric's baseline
    # and current samples both span the full run. A local disturbance now
    # touches a few blocks of many metrics instead of most blocks of one, and
    # slow drift enters both sides of every comparison symmetrically — it
    # inflates variance, which the t-test models and the MDE reports, instead
    # of biasing means, which nothing reported. The order is deterministic:
    # no randomisation enters the evidence.
    points = benchmark_points(arguments.records, arguments.only)

    # Calibration pass first (one discarded block per side per point): the
    # loop counts both sides share, and the coldness of a freshly built guard,
    # are both spent here rather than inside anyone's measured window (H1).
    loops_by_point = {}
    for module, section, metric, sampler_metric, name, records in points:
        loops_by_point[name] = calibrate_metric(
            baseline_python, current_python, module, records, section, metric, sampler_metric
        )

    # The canary is one fixed cheap metric measured before, between, and after
    # the interleaved rounds. It never gates anything: it exists so a reader
    # sees the run's observed drift beside its verdicts instead of trusting a
    # number that carries no such caveat.
    canary = points[0]
    canary_reads: list[float] = []

    def read_canary() -> None:
        module, section, metric, sampler_metric, name, records = canary
        block = run_block(
            baseline_python,
            module,
            records,
            section,
            metric,
            sampler_metric,
            True,
            loops_by_point[name],
        )
        canary_reads.append(block["value"])

    samples_by_point: dict[str, dict[str, list[float]]] = {
        name: {BASELINE: [], CURRENT: []} for *_, name, _records in points
    }
    read_canary()
    for position, side in enumerate(sequence):
        if position == len(sequence) // 2:
            read_canary()
        python = baseline_python if side == BASELINE else current_python
        for module, section, metric, sampler_metric, name, records in points:
            block = run_block(
                python,
                module,
                records,
                section,
                metric,
                sampler_metric,
                side == BASELINE,
                loops_by_point[name],
            )
            samples_by_point[name][side].append(block["value"])
            baseline_instrumented |= side == BASELINE and block["instrumented"]
    read_canary()

    canary_drift_pct = (
        (max(canary_reads) - min(canary_reads)) / min(canary_reads) * 100 if canary_reads else 0.0
    )
    print(
        f"observed run drift (canary {canary[4]}, baseline side, start/mid/end): "
        f"{', '.join(f'{value:.2f}us' for value in canary_reads)}  "
        f"spread {canary_drift_pct:.1f}%"
    )

    print(f"{'metric':<28} {'change':>9}  {'MDE':>7}   verdict")
    for module, section, metric, sampler_metric, name, records in points:
        samples = samples_by_point[name]
        test = compare(samples[BASELINE], samples[CURRENT])
        slower = test["significant"] and test["change_pct"] > 0
        label = name.rsplit("@", 1)[0]
        non_gating_reason = NON_GATING_SEMANTIC_COSTS.get(label)

        confirmation = None
        if slower:
            # A single test at alpha 0.95 is wrong one time in twenty, and
            # this harness runs dozens of them. Confirm before failing — at
            # DOUBLE the block count, because a confirmation run at the same
            # power can reproduce a borderline effect by chance twice. The
            # confirmation runs the metric alone, after the ladder: the
            # configuration H2's parity runs showed clean.
            print(f"{name:<28} {test['change_pct']:>+8.1f}%  confirming at 2x blocks...")
            confirmation, _, _ = measure_metric(
                baseline_python,
                current_python,
                sequence * 2,
                module,
                records,
                section,
                metric,
                sampler_metric,
            )
            slower = confirmation["significant"] and confirmation["change_pct"] > 0

        verdict = (
            ("SLOWER" if slower else "faster")
            if test["significant"]
            else "no significant difference"
        )
        if confirmation is not None and not slower:
            verdict = "slowdown did not reproduce"
        if slower and non_gating_reason is not None:
            verdict = "expected correctness cost (non-gating)"
        results.append(
            {
                "metric": name,
                "baseline_us": samples[BASELINE],
                "current_us": samples[CURRENT],
                "verdict": verdict,
                "confirmation": confirmation,
                "gating": non_gating_reason is None,
                "non_gating_reason": non_gating_reason,
                **test,
            }
        )
        if slower and non_gating_reason is None:
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
    if arguments.current_venv != DEFAULT_CURRENT_VENV:
        current_role = (
            arguments.current_venv.removeprefix(".venv-").removeprefix(".venv") or "current"
        )
        role = f"{role}-vs-{current_role}"
    out = arguments.output or (REPO / "benches" / f"ab-{role}.json")
    if not out.is_absolute():
        out = REPO / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "records": arguments.records,
                "baseline_venv": arguments.baseline_venv,
                "current_venv": arguments.current_venv,
                "gated": not arguments.no_gate,
                "block_sequence": sequence,
                "baseline_instrumented": baseline_instrumented,
                "canary": {
                    "metric": points[0][4] if points else None,
                    "reads_us": canary_reads,
                    "spread_pct": canary_drift_pct,
                    "note": (
                        "one fixed metric read on the baseline side before, between, and "
                        "after the interleaved rounds; reported context only, never a gate"
                    ),
                },
                "method": (
                    "one metric at one size per block, B C C B interleaved across all "
                    "metric points — every block-position runs across the whole ladder "
                    "before the next, so each metric's samples span the full run and "
                    "slow drift inflates variance (reported as MDE) instead of biasing "
                    "means; loop counts calibrated once per point up front and shared by "
                    "both sides; two-sample two-tailed t-test at alpha 0.95; a change "
                    "smaller than the reported minimum detectable effect is published as "
                    "no significant difference; a slowdown must reproduce in an "
                    "independent solo confirmation run at double the block count to fail "
                    "the gate"
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
