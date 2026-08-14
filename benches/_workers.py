"""Fail-closed compatibility shim for the retired Python aggregation path.

Benchmark modules still expose historical ``run`` helpers so old imports fail with
an actionable error instead of silently changing semantics. Canonical collection is
``collect_report.py`` or ``ab.py``; both persist raw observations and invoke R.
"""

from __future__ import annotations

from typing import Any, NoReturn


def across_workers(
    module: str,
    function: str,
    args: list[Any],
    *,
    workers: int,
) -> NoReturn:
    del module, function, args, workers
    raise RuntimeError(
        "Python worker aggregation is retired: run benches/collect_report.py for the "
        "absolute panel or benches/ab.py for same-session A/B evidence; R owns inference"
    )
