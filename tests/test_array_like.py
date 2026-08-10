"""Array-like Structs use positional plans without a mapping tree."""

from __future__ import annotations

import msgspec
import msgspec_toon as toon
import pytest


class Point(msgspec.Struct, array_like=True, rename={"x": "renamed_x"}):
    x: int
    label: str = "origin"


class Shape(msgspec.Struct):
    points: list[Point]


def test_array_like_full_and_defaulted_values_match_msgspec_json() -> None:
    cases = [
        ("[2]:\n  - 2\n  - east", b'[2,"east"]'),
        ("[1]:\n  - 2", b"[2]"),
    ]
    for document, json_document in cases:
        assert toon.decode(document, type=Point) == msgspec.json.decode(json_document, type=Point)


def test_array_like_nested_in_declared_list() -> None:
    document = "points[2]:\n  - [2]:\n    - 1\n    - a\n  - [1]:\n    - 2"
    assert toon.decode(document, type=Shape) == Shape([Point(1, "a"), Point(2)])


@pytest.mark.parametrize(
    "document",
    [
        "[0]:",
        "[3]:\n  - 1\n  - a\n  - extra",
        "x: 1\nlabel: a",
        "[2]:\n  - wrong\n  - a",
    ],
)
def test_array_like_invalid_shapes_are_rejected(document: str) -> None:
    with pytest.raises(msgspec.DecodeError):
        toon.decode(document, type=Point)
