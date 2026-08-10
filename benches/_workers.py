"""Spawn the worker processes the estimator averages over.

The parent side of `_timing.py`. One calibration worker chooses the loop counts
and its samples are thrown away; the measurement workers then all measure the
same amount of work, and their per-metric means are averaged here.

Why processes and not threads or loops: the variance this exists to average
over is *between* processes — address layout, allocator state, CPU frequency,
core assignment. Repeating inside one process measures the same lucky
conditions again.
"""

from __future__ import annotations

import json
import os
import pathlib
import statistics
import subprocess
import sys
from typing import Any

REPO = pathlib.Path(__file__).resolve().parent.parent

#: Runs one worker: import the bench module, call its worker-side function,
#: and report both the measurements and any loop counts this process chose.
PROBE = r"""
import json, sys
sys.path.insert(0, "benches")
import _timing
module = __import__(sys.argv[1])
result = getattr(module, sys.argv[2])(*json.loads(sys.argv[3]))
print(json.dumps({"result": result, "loops": _timing.CALIBRATED}))
"""


def _run_probe(module: str, function: str, args: list[Any], loops: dict[str, int] | None) -> dict:
    environment = dict(os.environ)
    if loops is None:
        environment.pop(_LOOPS_ENV, None)
    else:
        environment[_LOOPS_ENV] = json.dumps(loops)
    proc = subprocess.run(
        [sys.executable, "-c", PROBE, module, function, json.dumps(args)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    if proc.returncode != 0:
        raise SystemExit(f"benchmark worker failed:\n{proc.stderr[-2000:]}")
    return json.loads(proc.stdout.splitlines()[-1])


_LOOPS_ENV = "MSGSPEC_TOON_LOOPS"


def _merge(samples: list[Any]) -> Any:
    """Average the numeric leaves; keep non-numeric values from the first worker.

    A float leaf becomes the mean across workers. Everything else — byte counts,
    record counts, notes — is identical in every worker by construction, so the
    first worker's value is taken unchanged.
    """
    first = samples[0]
    if isinstance(first, dict):
        return {key: _merge([sample[key] for sample in samples]) for key in first}
    if isinstance(first, float):
        return round(statistics.fmean(samples), 2)
    return first


def _dispersion(samples: list[Any], path: str = "") -> dict[str, float]:
    """Standard deviation across workers for every float leaf, as a percentage."""
    first = samples[0]
    if isinstance(first, dict):
        out: dict[str, float] = {}
        for key in first:
            child = f"{path}.{key}" if path else str(key)
            out |= _dispersion([sample[key] for sample in samples], child)
        return out
    if isinstance(first, float) and len(samples) > 1:
        mean = statistics.fmean(samples)
        if mean > 0:
            return {path: round(statistics.stdev(samples) / mean * 100, 2)}
    return {}


def across_workers(
    module: str,
    function: str,
    args: list[Any],
    *,
    workers: int,
) -> tuple[Any, dict[str, float]]:
    """Return the mean across workers, plus the per-metric spread between them.

    The first worker only calibrates: its samples are discarded, exactly as
    pyperf does, because a process that also chose the loop counts has done
    different work from the ones that were handed them.
    """
    calibration = _run_probe(module, function, args, loops=None)
    loops = calibration["loops"]
    measured = [_run_probe(module, function, args, loops)["result"] for _ in range(workers)]
    merged = _merge(measured)
    if isinstance(merged, dict):
        # Retain each worker mean. Publication plots use these direct times to
        # calculate confidence intervals around the arithmetic mean.
        merged["worker_observations"] = measured
    return merged, _dispersion(measured)
