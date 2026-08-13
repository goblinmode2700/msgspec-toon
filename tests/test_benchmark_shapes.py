from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "benches"))

import msgspec_toon
from payloads import irregular_records_tree, nested_mixed_tree


def test_untyped_regression_payloads_are_non_tabular_and_round_trip() -> None:
    for value in (nested_mixed_tree(46), irregular_records_tree(64)):
        wire = msgspec_toon.encode(value)
        assert b"{" not in wire.splitlines()[0]
        assert msgspec_toon.decode(wire) == value
