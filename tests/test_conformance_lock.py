from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "conformance"))

from fetch import LOCK, tree_sha256


def test_fixture_tree_hash_matches_the_platform_independent_lock() -> None:
    assert tree_sha256(ROOT / "conformance" / "fixtures") == LOCK["tree_sha256"]
