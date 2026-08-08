"""The one timing implementation every benchmark script routes through.

Estimator: **the mean across independent worker processes**, not the minimum
across batches inside one. A minimum rewards whichever batch happened to dodge
the scheduler, understates what a caller experiences, and has no central-limit
behavior to converge on — `pyperf` argues the point at length and this project
agrees. Measured here before the change: inside one process the encode path
varies by 0.74-1.07%, but between processes it varies by 2.4-4.1% and drifts as
the machine warms. Averaging over processes averages over the things that
actually differ between runs: address layout, allocator state, CPU frequency,
core assignment.

Three roles, selected by environment so the same script serves all three:

    calibration worker   picks the loop count per named metric and reports it
    measurement worker   measures with the given loop counts, discarding its
                         own first sample as a warmup
    parent               spawns the workers and averages their samples

The loop count is calibrated once and handed to every worker, so all workers
measure the same amount of work and their means are comparable.

No benchmark script hand-rolls a loop (openspec: distribution-quality,
"Benchmark timing is standardized", "The timing estimator is stated and is not
a minimum").
"""

from __future__ import annotations

import json
import os
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass

ESTIMATOR = "mean-across-workers"
DEFAULT_WORKERS = 10
SAMPLES_PER_WORKER = 3
DEFAULT_TARGET_SECONDS = 0.05

#: Loop counts chosen by the calibration worker, injected into measurement
#: workers. Absent in the calibration worker, which is what tells it to
#: calibrate.
LOOPS_ENV = "MSGSPEC_TOON_LOOPS"

#: When set, `measure` runs only the named metric and reports zero for the rest.
#: The A/B harness measures one metric per block but calls a sampler that
#: computes them all — without this, every typed-encode block also times the
#: python-toon incumbent at ~30ms a call, which is the whole cost of the block.
#: Only that harness sets it; a full benchmark run leaves it unset.
ONLY_ENV = "MSGSPEC_TOON_ONLY_METRIC"


@dataclass(frozen=True, slots=True)
class Timing:
    """One worker's contribution: the mean of its post-warmup samples."""

    microseconds: float
    loops: int
    samples: int

    @property
    def us(self) -> float:
        return round(self.microseconds, 2)


def methodology() -> str:
    return (
        f"estimator: {ESTIMATOR} — the loop count is calibrated once, then "
        f"{DEFAULT_WORKERS} independent worker processes each discard their first "
        f"sample as a warmup and report the mean of {SAMPLES_PER_WORKER} samples; the "
        "published figure is the mean across workers, with the standard deviation "
        "across workers alongside it. The minimum is deliberately not used: it "
        "reports the best case the machine ever reached, not what a caller sees"
    )


def _injected_loops() -> dict[str, int]:
    raw = os.environ.get(LOOPS_ENV)
    return json.loads(raw) if raw else {}


_LOOPS: dict[str, int] = _injected_loops()
_ONLY: str | None = os.environ.get(ONLY_ENV) or None
#: Loop counts this process chose, reported back when calibrating.
CALIBRATED: dict[str, int] = {}


def calibrating() -> bool:
    """True when no loop counts were injected, so this process must choose them."""
    return not _LOOPS


def selected_metric() -> str | None:
    """The one metric an A/B block requested, or `None` for a full ladder.

    Samplers use this only to skip setup that the selected callable cannot
    reach. The timed callable, loop calibration, warmup, and samples remain in
    `measure`, unchanged.
    """
    return _ONLY


def _calibrate(fn: Callable[[], object], target_seconds: float) -> int:
    loops = 1
    while True:
        start = time.perf_counter()
        for _ in range(loops):
            fn()
        if time.perf_counter() - start >= target_seconds:
            return loops
        loops *= 2


def _sample(fn: Callable[[], object], loops: int) -> float:
    start = time.perf_counter()
    for _ in range(loops):
        fn()
    return (time.perf_counter() - start) / loops


def measure(
    name: str,
    fn: Callable[[], object],
    *,
    samples: int = SAMPLES_PER_WORKER,
    target_seconds: float = DEFAULT_TARGET_SECONDS,
) -> Timing:
    """Measure one named metric in this worker.

    `name` is what the calibration worker keys its loop count on, so it must be
    stable across processes — the same metric must carry the same name in every
    worker or they will not be measuring the same amount of work.
    """
    if _ONLY is not None and name != _ONLY:
        return Timing(microseconds=0.0, loops=0, samples=0)

    fn()  # warm caches, plans, and any lazily built state

    loops = _LOOPS.get(name)
    if loops is None:
        loops = _calibrate(fn, target_seconds)
        CALIBRATED[name] = loops

    _sample(fn, loops)  # warmup sample, discarded (pyperf's rule)
    values = [_sample(fn, loops) for _ in range(samples)]
    return Timing(
        microseconds=statistics.fmean(values) * 1e6,
        loops=loops,
        samples=samples,
    )
