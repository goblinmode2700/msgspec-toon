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


class UnionRow(msgspec.Struct):
    row_id: int
    pet: Cat | Dog


class IntegerPet(msgspec.Struct, tag=1, tag_field="kind"):
    x: int


class IntegerRow(msgspec.Struct):
    row_id: int
    pet: IntegerPet


def _rows(records: int, fields: bytes, row: bytes) -> bytes:
    return (
        b"["
        + str(records).encode()
        + b"]{"
        + fields
        + b"}:\n  "
        + b"\n  ".join(row for _ in range(records))
    )


def _alternating_rows(records: int, fields: bytes, rows: tuple[bytes, ...]) -> bytes:
    return (
        b"["
        + str(records).encode()
        + b"]{"
        + fields
        + b"}:\n  "
        + b"\n  ".join(rows[index % len(rows)] for index in range(records))
    )


def sample_run(records: int) -> dict[str, Any]:
    ordinary = _rows(records, b"row_id,pet{x}", b"1,2")
    tagged_first = _rows(records, b"type,x", b"cat,2")
    tagged_last = _rows(records, b"x,type", b"2,dog")
    nested_concrete = _rows(records, b"row_id,pet{type,x}", b"1,pet,2")
    nested_union = _alternating_rows(
        records,
        b"row_id,pet{type,x}",
        (b"1,cat,2", b"2,dog,3"),
    )
    nested_tag_last = _rows(records, b"row_id,pet{x,type}", b"1,2,pet")
    nested_quoted_tag = _rows(records, b"row_id,pet{type,x}", b'1,"pet",2')
    nested_int_tag = _rows(records, b"row_id,pet{kind,x}", b"1,1,2")

    ordinary_decoder = toon.Decoder(list[PlainRow])
    tagged_decoder = toon.Decoder(list[Cat | Dog])
    nested_decoder = toon.Decoder(list[ConcreteRow])
    nested_union_decoder = toon.Decoder(list[UnionRow])
    nested_int_decoder = toon.Decoder(list[IntegerRow])
    untyped_decoder = toon.Decoder()

    assert len(ordinary_decoder.decode(ordinary)) == records
    assert len(tagged_decoder.decode(tagged_first)) == records
    assert len(tagged_decoder.decode(tagged_last)) == records
    assert len(nested_decoder.decode(nested_concrete)) == records
    union_values = nested_union_decoder.decode(nested_union)
    assert len(union_values) == records
    assert isinstance(union_values[0].pet, Cat)
    assert isinstance(union_values[1].pet, Dog)
    assert len(nested_decoder.decode(nested_tag_last)) == records
    assert len(nested_decoder.decode(nested_quoted_tag)) == records
    assert len(nested_int_decoder.decode(nested_int_tag)) == records
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
            "nested_union": measure(
                "control.decode.nested_union",
                lambda: nested_union_decoder.decode(nested_union),
            ).us,
            "nested_tag_last": measure(
                "control.decode.nested_tag_last",
                lambda: nested_decoder.decode(nested_tag_last),
            ).us,
            "nested_quoted_tag": measure(
                "control.decode.nested_quoted_tag",
                lambda: nested_decoder.decode(nested_quoted_tag),
            ).us,
            "nested_int_tag": measure(
                "control.decode.nested_int_tag",
                lambda: nested_int_decoder.decode(nested_int_tag),
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
