"""Integers round-trip at Python's precision — no JavaScript numeric domain."""

from __future__ import annotations

import msgspec_toon as toon


def test_beyond_double_precision_survives() -> None:
    value = 2**53 + 1
    assert toon.decode(toon.encode({"n": value})) == {"n": value}


def test_very_large_integers_round_trip() -> None:
    value = 10**40 + 7
    encoded = toon.encode({"n": value})
    assert str(value).encode() in encoded
    assert toon.decode(encoded) == {"n": value}


def test_negative_large_integers_round_trip() -> None:
    value = -(2**64) - 3
    assert toon.decode(toon.encode({"n": value})) == {"n": value}


import msgspec


class Row(msgspec.Struct):
    n: int


class RowDoc(msgspec.Struct):
    rows: list[Row]


def test_large_integer_in_typed_row() -> None:
    huge = 9007199254740993
    text = f"rows[1]{{n}}:\n  {huge}".encode()
    value = toon.decode(text, type=RowDoc)
    assert value.rows[0].n == huge
    assert toon.encode(value) == text
