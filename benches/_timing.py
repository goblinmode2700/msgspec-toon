"""The timing primitive that each benchmark sampler uses.

The calibration process selects the loop count for each metric. Each measurement process uses
those counts, keeps its timed warmup separate, and records unaggregated elapsed nanoseconds.

Python does not calculate canonical estimates or decisions. The panel collectors persist raw
observations, and the declared R analyzers own all inference.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

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
    """One worker's unaggregated post-warmup timing batches."""

    loops: int
    elapsed_ns: tuple[int, ...]
    warmup_elapsed_ns: int | None

    @property
    def samples(self) -> int:
        return len(self.elapsed_ns)

    @property
    def microseconds(self) -> float:
        """Compatibility display only; canonical inference consumes ``elapsed_ns`` in R."""
        if not self.elapsed_ns or self.loops <= 0:
            return 0.0
        total_ns = sum(self.elapsed_ns)
        return total_ns / len(self.elapsed_ns) / self.loops / 1_000

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
RAW_TIMINGS: dict[str, Timing] = {}
_TARGET_SECONDS_OVERRIDE: float | None = None
_SAMPLES_OVERRIDE: int | None = None
_CALIBRATION_ONLY = False


def calibrating() -> bool:
    """True when no loop counts were injected, so this process must choose them."""
    return not _LOOPS


def selected_metric() -> str | None:
    """The one metric a panel cell requested, or `None` for a full ladder.

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


def _sample(fn: Callable[[], object], loops: int) -> int:
    start = time.perf_counter_ns()
    for _ in range(loops):
        fn()
    return time.perf_counter_ns() - start


@contextmanager
def collection_context(
    *,
    loops: dict[str, int] | None,
    selected: str | None,
    target_seconds: float,
    samples: int,
    calibration_only: bool = False,
) -> Iterator[None]:
    """Configure one cell inside a long-lived benchmark-panel worker."""

    global _LOOPS, _ONLY, _TARGET_SECONDS_OVERRIDE, _SAMPLES_OVERRIDE, _CALIBRATION_ONLY
    previous = (
        _LOOPS,
        _ONLY,
        _TARGET_SECONDS_OVERRIDE,
        _SAMPLES_OVERRIDE,
        _CALIBRATION_ONLY,
        dict(CALIBRATED),
        dict(RAW_TIMINGS),
    )
    _LOOPS = dict(loops or {})
    _ONLY = selected
    _TARGET_SECONDS_OVERRIDE = target_seconds
    _SAMPLES_OVERRIDE = samples
    _CALIBRATION_ONLY = calibration_only
    CALIBRATED.clear()
    RAW_TIMINGS.clear()
    try:
        yield
    finally:
        (
            _LOOPS,
            _ONLY,
            _TARGET_SECONDS_OVERRIDE,
            _SAMPLES_OVERRIDE,
            _CALIBRATION_ONLY,
            old_calibrated,
            old_raw,
        ) = previous
        CALIBRATED.clear()
        CALIBRATED.update(old_calibrated)
        RAW_TIMINGS.clear()
        RAW_TIMINGS.update(old_raw)


def raw_timings() -> dict[str, dict[str, Any]]:
    """Return JSON-ready raw observations for the active collection context."""

    return {
        name: {
            "loops": timing.loops,
            "warmup_elapsed_ns": timing.warmup_elapsed_ns,
            "elapsed_ns": list(timing.elapsed_ns),
        }
        for name, timing in RAW_TIMINGS.items()
    }


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
        return Timing(loops=0, elapsed_ns=(), warmup_elapsed_ns=None)

    fn()  # warm caches, plans, and any lazily built state

    effective_target = _TARGET_SECONDS_OVERRIDE or target_seconds
    effective_samples = _SAMPLES_OVERRIDE or samples

    loops = _LOOPS.get(name)
    if loops is None:
        loops = _calibrate(fn, effective_target)
        CALIBRATED[name] = loops

    if _CALIBRATION_ONLY:
        timing = Timing(loops=loops, elapsed_ns=(), warmup_elapsed_ns=None)
        RAW_TIMINGS[name] = timing
        return timing

    warmup_elapsed_ns = _sample(fn, loops)
    values = tuple(_sample(fn, loops) for _ in range(effective_samples))
    timing = Timing(
        loops=loops,
        elapsed_ns=values,
        warmup_elapsed_ns=warmup_elapsed_ns,
    )
    RAW_TIMINGS[name] = timing
    return timing
