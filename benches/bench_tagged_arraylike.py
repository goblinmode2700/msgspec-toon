"""Focused timing for the tagged array-like decode repair.

The released guard can execute only ``plain``. The candidate additionally
executes ``tagged_concrete`` and ``tagged_union``. All timings route through
the repository's ten-worker mean implementation; no minimum is reported.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

import build_freshness  # noqa: F401
import msgspec
import msgspec_toon as toon
from _timing import DEFAULT_WORKERS, measure, methodology, selected_metric
from _workers import across_workers


class Plain(msgspec.Struct, array_like=True):
    value: int


class TaggedA(msgspec.Struct, array_like=True, tag="a"):
    value: int


class TaggedB(msgspec.Struct, array_like=True, tag="b"):
    value: int


def sample_run(records: int) -> dict[str, Any]:
    selected = selected_metric()
    measuring_all = selected is None
    plain_text = toon.encode([Plain(index) for index in range(records)])
    plain_decoder = toon.Decoder(list[Plain])

    need_tagged = measuring_all or selected in {
        "decode.tagged_concrete",
        "decode.tagged_union",
    }
    if need_tagged:
        concrete_text = toon.encode([TaggedA(index) for index in range(records)])
        union_text = toon.encode(
            [TaggedA(index) if index % 2 == 0 else TaggedB(index) for index in range(records)]
        )
        concrete_decoder = toon.Decoder(list[TaggedA])
        union_decoder = toon.Decoder(list[TaggedA | TaggedB])
    else:
        concrete_text = union_text = b""
        concrete_decoder = union_decoder = None

    return {
        "records": records,
        "decode_us": {
            "plain": measure("decode.arraylike_plain", lambda: plain_decoder.decode(plain_text)).us,
            "tagged_concrete": measure(
                "decode.tagged_concrete",
                lambda: concrete_decoder.decode(concrete_text),  # type: ignore[union-attr]
            ).us,
            "tagged_union": measure(
                "decode.tagged_union",
                lambda: union_decoder.decode(union_text),  # type: ignore[union-attr]
            ).us,
        },
    }


def run(records: int, *, workers: int = DEFAULT_WORKERS) -> dict[str, Any]:
    result, spread = across_workers(
        "bench_tagged_arraylike", "sample_run", [records], workers=workers
    )
    result["worker_spread_pct"] = spread
    return result


if __name__ == "__main__":
    print("timing:", methodology())
    for size in (4, 46, 512, 4096):
        print(run(size))
