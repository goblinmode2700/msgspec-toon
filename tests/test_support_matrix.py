"""The support matrix is a test oracle, not documentation.

Every entry in `conformance/support_matrix.py` declares how this codec behaves
relative to `msgspec.json` on an equivalent document. This file runs both sides
and fails when the declaration stops being true — in either direction. Fixing a
gap without updating the matrix fails here, which is the point: the released
gap list is generated from that module (review F-11).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "conformance"))

from support_matrix import (
    CHECKERS,
    MATRIX,
    PARITY_REJECTS,
    SUPPORTED,
    SupportEntry,
    as_report,
)


@pytest.mark.parametrize("entry", MATRIX, ids=lambda entry: entry.feature)
def test_declared_behavior_is_actual_behavior(entry: SupportEntry) -> None:
    CHECKERS[entry.status](entry)


def test_every_entry_has_a_known_status() -> None:
    for entry in MATRIX:
        assert entry.status in CHECKERS, f"{entry.feature}: unknown status {entry.status!r}"


def test_report_view_lists_every_non_supported_entry() -> None:
    report = as_report()
    assert len(report["entries"]) == len(MATRIX)
    declared_gaps = {
        entry.feature for entry in MATRIX if entry.status not in {SUPPORTED, PARITY_REJECTS}
    }
    assert {gap["feature"] for gap in report["known_gaps"]} == declared_gaps
    # A report that lists no gaps would mean this codec matches msgspec.json
    # everywhere, which is not true yet and must not be claimable by accident.
    assert declared_gaps
