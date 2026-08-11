"""Parity probes for outside-agent issue 08."""

from __future__ import annotations

from typing import Any

import msgspec
import msgspec_toon as toon
import pytest


class OpenBox(msgspec.Struct):
    payload: object


class UnionNode(msgspec.Struct):
    value: int | str
    child: UnionNode | None = None


@pytest.mark.parametrize(
    ("annotation", "value", "json_document"),
    [
        (Any, {"a": 1}, b'{"a":1}'),
        (object, {"a": 1}, b'{"a":1}'),
        (dict[str, Any], {"a": 1}, b'{"a":1}'),
        (dict[str, object], {"a": 1}, b'{"a":1}'),
        (dict[str, int], {"a": 1}, b'{"a":1}'),
        (dict[str, int | str], {"a": 1, "b": "x"}, b'{"a":1,"b":"x"}'),
        (list[Any], [1, "x"], b'[1,"x"]'),
        (list[object], [1, "x"], b'[1,"x"]'),
        (list[dict[str, str]], [{"a": "x"}], b'[{"a":"x"}]'),
        (list[dict[str, object]], [{"a": 1}], b'[{"a":1}]'),
        (int | None, 1, b"1"),
        (int | str, 1, b"1"),
        (int | str, "x", b'"x"'),
        (list[int | str], [1, "x"], b'[1,"x"]'),
        (tuple[int, str], (1, "x"), b'[1,"x"]'),
    ],
)
def test_object_and_scalar_union_round_trip_matches_msgspec_json(
    annotation: object, value: object, json_document: bytes
) -> None:
    assert msgspec.json.decode(json_document, type=annotation) == value
    assert toon.decode(toon.encode(value), type=annotation) == value


@pytest.mark.parametrize(
    ("annotation", "value", "expected_type"),
    [
        (int | float, 1, int),
        (float | int, 1, int),
        (int | float, 1.5, float),
        (float | str, 1, float),
        (bool | int, True, bool),
        (bool | int, 1, int),
    ],
)
def test_scalar_union_prefers_msgspec_json_category(
    annotation: object, value: object, expected_type: type
) -> None:
    document = toon.encode(value)
    decoded = toon.decode(document, type=annotation)
    assert decoded == value
    assert type(decoded) is expected_type


@pytest.mark.parametrize(
    ("annotation", "document", "expected"),
    [
        (int | float, b'"1"', 1),
        (float | int, b'"1"', 1),
        (int | float, b'"1.5"', 1.5),
        (bool | int, b'"1"', 1),
        (bool | int, b'"true"', True),
        (bool | float, b'"1"', 1.0),
    ],
)
def test_permissive_scalar_union_matches_msgspec_priority(
    annotation: object, document: bytes, expected: object
) -> None:
    json_value = msgspec.json.decode(document, type=annotation, strict=False)
    toon_value = toon.decode(document, type=annotation, strict=False)
    assert toon_value == json_value == expected
    assert type(toon_value) is type(json_value)


def test_object_and_scalar_unions_compose_with_nested_and_recursive_structs() -> None:
    open_value = OpenBox({"items": [1, "x"]})
    recursive = UnionNode(1, UnionNode("x"))
    assert toon.decode(toon.encode(open_value), type=OpenBox) == open_value
    assert toon.decode(toon.encode(recursive), type=UnionNode) == recursive


def test_scalar_union_failure_is_payload_safe() -> None:
    sentinel = "SENTINEL_SCALAR_UNION"
    with pytest.raises(msgspec.DecodeError) as caught:
        toon.decode(f"{sentinel}: 1".encode(), type=int | str)
    assert sentinel not in str(caught.value)
