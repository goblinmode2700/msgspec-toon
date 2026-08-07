"""The one timing implementation every benchmark script routes through.

Methodology: warm the callable once, autorange the batch size until a batch
takes at least `target_seconds`, then report the minimum per-call time across
`repeats` batches. Minimum-of-batches is the standard noise-rejection choice
for microbenchmarks: it measures the fastest the machine actually ran the
code, which is the quantity same-run comparisons need.

No benchmark script hand-rolls its own loop (openspec: distribution-quality,
"Benchmark timing is standardized").
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

DEFAULT_REPEATS = 7
DEFAULT_TARGET_SECONDS = 0.05


@dataclass(frozen=True, slots=True)
class Timing:
    """A measurement plus the methodology parameters that produced it."""

    microseconds: float
    batch_size: int
    repeats: int
    target_seconds: float

    @property
    def us(self) -> float:
        return round(self.microseconds, 2)


def methodology() -> str:
    return (
        f"minimum per-call time across {DEFAULT_REPEATS} autoranged batches; "
        f"batch size grows until one batch takes >= {DEFAULT_TARGET_SECONDS}s; "
        "callable warmed once before measurement"
    )


def best_of(
    fn: Callable[[], object],
    *,
    repeats: int = DEFAULT_REPEATS,
    target_seconds: float = DEFAULT_TARGET_SECONDS,
) -> Timing:
    fn()  # warm caches, plans, and JITs of any kind

    number = 1
    while True:
        start = time.perf_counter()
        for _ in range(number):
            fn()
        elapsed = time.perf_counter() - start
        if elapsed >= target_seconds:
            break
        number *= 2

    best = elapsed / number
    for _ in range(repeats - 1):
        start = time.perf_counter()
        for _ in range(number):
            fn()
        elapsed = time.perf_counter() - start
        best = min(best, elapsed / number)

    return Timing(
        microseconds=best * 1e6,
        batch_size=number,
        repeats=repeats,
        target_seconds=target_seconds,
    )
