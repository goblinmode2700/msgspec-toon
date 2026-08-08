"""Token and byte efficiency cannot move without someone saying why.

The fixture corpus proves the encoder still produces correct documents; it says
nothing about whether they got bigger. This is the gate that does. Any drift in
either direction fails: an unexplained improvement means the output changed too,
and canonical bytes are a conformance surface.

Byte counts run everywhere — they need nothing but this package. Token counts
need `tiktoken` and its encoding files, so they are skipped, loudly, in an
environment that cannot load them, rather than turning `make check` into a
network dependency.

Deliberately absent: any assertion that this codec beats another codec. That
comparison lives once in the published ladder under gates T1 and G5, where a
miss is visible as a gate miss. Repeating it here would measure the machine and
grow without bound (the distribution requirement, "Comparative claims are made
once, where a miss is visible").
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "conformance"))

from efficiency import LOCK_PATH, measure, tokenizer_versions

UPDATE_HINT = "if this change was intended, run `uv run python scripts/efficiency-lock.py --write` and say why in the commit"


@pytest.fixture(scope="module")
def locked() -> dict:
    assert LOCK_PATH.exists(), f"no efficiency lock at {LOCK_PATH}"
    return json.loads(LOCK_PATH.read_text())


def _tokenizer_available() -> bool:
    """Any failure means the same thing here: the token half cannot run.

    tiktoken raises whatever the transport or the cache raises when the
    encoding files are absent, so the specific type carries no information the
    caller can act on — the token assertions skip either way and the byte
    assertions, which need nothing, still run.
    """
    try:
        import tiktoken

        tiktoken.get_encoding("o200k_base")
    except Exception:  # noqa: BLE001
        return False
    return True


def test_byte_counts_match_the_lock(locked: dict) -> None:
    current = measure(with_tokens=False)
    drift = []
    for payload, formats in current["payloads"].items():
        for name, entry in formats.items():
            expected = locked["payloads"][payload][name]["bytes"]
            if entry["bytes"] != expected:
                drift.append(
                    f"{payload}/{name}: locked {expected} bytes, measured {entry['bytes']}"
                )
    assert not drift, "canonical output size moved:\n  " + "\n  ".join(drift) + f"\n{UPDATE_HINT}"


def test_every_locked_payload_is_still_measured(locked: dict) -> None:
    """A lock entry that stops being measured is a silent hole in the gate."""
    current = measure(with_tokens=False)
    missing = set(locked["payloads"]) - set(current["payloads"])
    assert not missing, f"locked payloads no longer measured: {sorted(missing)}"


@pytest.mark.skipif(not _tokenizer_available(), reason="tiktoken or its encodings unavailable")
def test_token_counts_match_the_lock(locked: dict) -> None:
    current = measure()
    drift = []
    for payload, formats in current["payloads"].items():
        for name, entry in formats.items():
            expected = locked["payloads"][payload][name]["tokens"]
            if entry["tokens"] != expected:
                drift.append(f"{payload}/{name}: locked {expected}, measured {entry['tokens']}")
    assert not drift, "token cost moved:\n  " + "\n  ".join(drift) + f"\n{UPDATE_HINT}"


@pytest.mark.skipif(not _tokenizer_available(), reason="tiktoken or its encodings unavailable")
def test_tokenizer_change_is_attributable(locked: dict) -> None:
    """A tokenizer upgrade must fail as itself, not as a phantom codec change."""
    assert locked["versions"] == tokenizer_versions(), (
        f"the tokenizer or msgspec version changed: locked {locked['versions']}, "
        f"installed {tokenizer_versions()}. Token counts below are measured under a "
        f"different tokenizer than the lock; {UPDATE_HINT}"
    )
