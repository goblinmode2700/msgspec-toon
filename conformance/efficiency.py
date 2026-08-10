"""Compute the locked efficiency view: what this codec's output costs.

The fixture corpus proves the encoder still produces *correct* documents. It
says nothing about whether they got bigger. Canonical output could grow five
percent on every record payload and every existing check would still pass —
which is why this exists as a gate rather than a report row.

What is locked, and what deliberately is not:

    locked      this codec's canonical output, and its two spec-defined
                delimiter variants, in bytes and in tokens
    locked      compact JSON, the denominator every ratio is quoted against,
                because msgspec is exact-pinned so its output is ours to hold
    not locked  the incumbent codecs' output — it moves when they release, and
                their releases are not our regression

Tokens are a deterministic function of the bytes and the tokenizer, so the gate
is an exact snapshot rather than a tolerance: a tolerance would absorb exactly
the drift the lock exists to catch. The tokenizer version is recorded so an
upstream tokenizer change fails as itself rather than as a phantom codec change.
"""

from __future__ import annotations

import datetime
import decimal
import enum
import importlib.metadata
import sys
import uuid
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "benches"))

import msgspec
import msgspec_toon
from payloads import token_payload_matrix

LOCK_PATH = REPO / "conformance" / "efficiency.lock.json"
TOKENIZERS = ("o200k_base", "cl100k_base")


class _LockedColor(enum.Enum):
    RED = "red"


def native_scalar_payload() -> list[Any]:
    """A stable wire-and-token lock for the msgspec-native encode surface."""
    return [
        datetime.date(2026, 8, 9),
        datetime.datetime(2026, 8, 9, 1, 2, 3, 456, datetime.UTC),
        datetime.time(1, 2, 3, 456),
        datetime.timedelta(days=2, seconds=3, microseconds=4),
        uuid.UUID("12345678-1234-5678-1234-567812345678"),
        decimal.Decimal("1.2300"),
        _LockedColor.RED,
    ]


def encoded_texts(tree: Any) -> dict[str, str]:
    """Every wire form this project is responsible for."""
    return {
        "json_compact": msgspec.json.encode(tree).decode(),
        "toon_comma": msgspec_toon.encode(tree).decode(),
        "toon_tab": msgspec_toon.encode(tree, delimiter="\t").decode(),
        "toon_pipe": msgspec_toon.encode(tree, delimiter="|").decode(),
    }


def tokenizer_versions() -> dict[str, str]:
    return {
        "tiktoken": importlib.metadata.version("tiktoken"),
        "msgspec": msgspec.__version__,
        "encodings": ",".join(TOKENIZERS),
    }


def measure(*, with_tokens: bool = True) -> dict[str, Any]:
    """Byte counts always; token counts when a tokenizer is available.

    Byte counts need nothing but this package, so they are the half of the gate
    that can run offline in any environment. Token counts need `tiktoken` and
    its encoding files.
    """
    encoders = {}
    if with_tokens:
        import tiktoken

        encoders = {name: tiktoken.get_encoding(name) for name in TOKENIZERS}

    payloads: dict[str, Any] = {}
    for shape, records, tree in token_payload_matrix():
        formats: dict[str, Any] = {}
        for name, text in encoded_texts(tree).items():
            entry: dict[str, Any] = {"bytes": len(text.encode())}
            if encoders:
                entry["tokens"] = {
                    tokenizer: len(encoder.encode(text)) for tokenizer, encoder in encoders.items()
                }
            formats[name] = entry
        payloads[f"{shape}@{records}"] = formats

    formats = {}
    for name, text in encoded_texts(native_scalar_payload()).items():
        entry = {"bytes": len(text.encode())}
        if encoders:
            entry["tokens"] = {
                tokenizer: len(encoder.encode(text)) for tokenizer, encoder in encoders.items()
            }
        formats[name] = entry
    payloads["msgspec-native-scalars@7"] = formats

    return {
        "note": (
            "Locked efficiency snapshot. Any difference fails the gate in either "
            "direction: an unexplained improvement means the output changed too, and "
            "canonical bytes are a conformance surface. Update deliberately, with the "
            "reason the counts moved."
        ),
        "versions": (
            tokenizer_versions()
            if with_tokens
            else {
                "msgspec": msgspec.__version__,
                "encodings": ",".join(TOKENIZERS),
            }
        ),
        "payloads": payloads,
    }
