from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "benches"))

import msgspec_toon
from bench_key_cardinality import GUARD_KEY_COUNTS, KEY_COUNTS
from payloads import distinct_key_records_tree, irregular_records_tree, nested_mixed_tree


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
    assert any(10 <= count < 100 for count in GUARD_KEY_COUNTS)
    assert any(100 <= count < 1000 for count in GUARD_KEY_COUNTS)
