"""Pinned msgspec 0.21.1 differentials for `strict=False`."""

from __future__ import annotations

import math

import msgspec
import msgspec_toon as toon
import pytest


@pytest.mark.parametrize(
    ("toon_value", "json_value", "type_"),
    [
        ('"true"', b'"true"', bool),
        ('"FALSE"', b'"FALSE"', bool),
        ('"-0"', b'"-0"', bool),
        ("1", b"1", bool),
        ('"-2"', b'"-2"', int),
        ('"1e2"', b'"1e2"', int),
        ('"1.000"', b'"1.000"', int),
        ('"9007199254740993"', b'"9007199254740993"', int),
        ('"9007199254740993.0"', b'"9007199254740993.0"', int),
        ('"1.5"', b'"1.5"', float),
        ("2", b"2", float),
    ],
)
def test_permissive_scalars_match_msgspec_json(
    toon_value: str, json_value: bytes, type_: type
) -> None:
    assert toon.decode(toon_value, type=type_, strict=False) == msgspec.json.decode(
        json_value, type=type_, strict=False
    )


@pytest.mark.parametrize("text", ["NaN", "Infinity", "-Infinity", "INF"])
def test_permissive_nonfinite_float_strings_match(text: str) -> None:
    ours = toon.decode(f'"{text}"', type=float, strict=False)
    reference = msgspec.json.decode(msgspec.json.encode(text), type=float, strict=False)
    if math.isnan(reference):
        assert math.isnan(ours)
    else:
        assert ours == reference


@pytest.mark.parametrize(
    ("document", "type_"),
    [
        ('"1.5"', int),
        ('"2"', bool),
        ("true", int),
        ("1", str),
        ('"01"', int),
        ('"+1"', int),
        ('"1e30"', int),
    ],
)
def test_permissive_rejections_match_msgspec_json(document: str, type_: type) -> None:
    with pytest.raises(msgspec.DecodeError):
        toon.decode(document, type=type_, strict=False)


def test_permissive_conversion_applies_in_nested_positions() -> None:
    assert toon.decode('[3]: "1","2","3"', type=list[int], strict=False) == [1, 2, 3]


def test_strict_mode_is_unchanged() -> None:
    with pytest.raises(msgspec.DecodeError):
        toon.decode('"1"', type=int)
