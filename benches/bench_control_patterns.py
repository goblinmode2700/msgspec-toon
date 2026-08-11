"""Focused timing cases for the msgspec control-pattern program."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

import build_freshness  # noqa: F401
import msgspec
import msgspec_toon as toon
from _timing import DEFAULT_WORKERS, measure, methodology
from _workers import across_workers

LADDER = (4, 64, 512, 4096)


class PlainPet(msgspec.Struct):
    x: int


class PlainRow(msgspec.Struct):
    row_id: int
    pet: PlainPet


class Cat(msgspec.Struct, tag="cat"):
    x: int


class Dog(msgspec.Struct, tag="dog"):
    x: int


class ConcretePet(msgspec.Struct, tag="pet"):
    x: int


class ConcreteRow(msgspec.Struct):
    row_id: int
    pet: ConcretePet


def _rows(records: int, fields: bytes, row: bytes) -> bytes:
    return (
        b"["
        + str(records).encode()
        + b"]{"
        + fields
        + b"}:\n  "
        + b"\n  ".join(row for _ in range(records))
    )


def sample_run(records: int) -> dict[str, Any]:
    ordinary = _rows(records, b"row_id,pet{x}", b"1,2")
    tagged_first = _rows(records, b"type,x", b"cat,2")
    tagged_last = _rows(records, b"x,type", b"2,dog")
    nested_concrete = _rows(records, b"row_id,pet{type,x}", b"1,pet,2")

    ordinary_decoder = toon.Decoder(list[PlainRow])
    tagged_decoder = toon.Decoder(list[Cat | Dog])
    nested_decoder = toon.Decoder(list[ConcreteRow])
    untyped_decoder = toon.Decoder()

    assert len(ordinary_decoder.decode(ordinary)) == records
    assert len(tagged_decoder.decode(tagged_first)) == records
    assert len(tagged_decoder.decode(tagged_last)) == records
    assert len(nested_decoder.decode(nested_concrete)) == records
    assert len(untyped_decoder.decode(nested_concrete)) == records

    return {
        "records": records,
        "decode_us": {
            "ordinary": measure(
                "control.decode.ordinary", lambda: ordinary_decoder.decode(ordinary)
            ).us,
            "tagged_first": measure(
                "control.decode.tagged_first", lambda: tagged_decoder.decode(tagged_first)
            ).us,
            "tagged_last": measure(
                "control.decode.tagged_last", lambda: tagged_decoder.decode(tagged_last)
            ).us,
            "nested_concrete": measure(
                "control.decode.nested_concrete",
                lambda: nested_decoder.decode(nested_concrete),
            ).us,
            "untyped_nested": measure(
                "control.decode.untyped_nested",
                lambda: untyped_decoder.decode(nested_concrete),
            ).us,
        },
    }


def run(records: int, *, workers: int = DEFAULT_WORKERS) -> dict[str, Any]:
    merged, spread = across_workers(
        "bench_control_patterns", "sample_run", [records], workers=workers
    )
    merged["worker_spread_pct"] = spread
    return merged


def main() -> None:
    print(f"python {sys.version.split()[0]}  msgspec {msgspec.__version__}")
    print("timing:", methodology())
    for records in LADDER:
        result = run(records)
        print(f"records={records:>5}  decode us={result['decode_us']}")


if __name__ == "__main__":
    main()
