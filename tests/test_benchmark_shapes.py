from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "benches"))

import msgspec_toon
from ab import benchmark_points
from bench_key_cardinality import KEY_COUNTS
from payloads import (
    distinct_key_records_tree,
    irregular_records_tree,
    nested_mixed_tree,
)


def test_untyped_regression_payloads_are_non_tabular_and_round_trip() -> None:
    for value in (nested_mixed_tree(46), irregular_records_tree(64)):
        wire = msgspec_toon.encode(value)
        assert b"{" not in wire.splitlines()[0]
        assert msgspec_toon.decode(wire) == value


def test_distinct_key_payloads_control_cardinality_and_round_trip() -> None:
    wire_lengths = set()
    for distinct_keys in KEY_COUNTS:
        value = distinct_key_records_tree(4096, distinct_keys)
        assert len({key for row in value for key in row}) == distinct_keys
        wire = msgspec_toon.encode(value)
        wire_lengths.add(len(wire))
        assert b"{" not in wire.splitlines()[0]
        assert msgspec_toon.decode(wire) == value
    assert len(wire_lengths) == 1


def test_distinct_key_guard_covers_tens_and_hundreds() -> None:
    points = [point for point in benchmark_points([4]) if point[0] == "bench_key_cardinality"]
    assert points == [
        (
            "bench_key_cardinality",
            "decode_us",
            "distinct_keys_32",
            "decode.distinct_keys_32",
            "untyped distinct-32-key decode@4096",
            4096,
        ),
        (
            "bench_key_cardinality",
            "decode_us",
            "distinct_keys_512",
            "decode.distinct_keys_512",
            "untyped distinct-512-key decode@4096",
            4096,
        ),
    ]
