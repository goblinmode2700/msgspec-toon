"""The public surface mirrors msgspec.json; untyped decode and hooks."""

from __future__ import annotations

import msgspec
import msgspec_toon as toon
import pytest


def test_untyped_decode_builds_builtins() -> None:
    text = b"name: demo\ncount: 3\nnested:\n  ok: true\ntags[2]: a,b"
    value = toon.decode(text)
    assert value == {"name": "demo", "count": 3, "nested": {"ok": True}, "tags": ["a", "b"]}


def test_untyped_round_trip() -> None:
    value = {
        "name": "demo",
        "count": 3,
        "ratio": 1.5,
        "ok": True,
        "missing": None,
        "nested": {"deep": "x"},
        "tags": ["a", "b"],
    }
    assert toon.decode(toon.encode(value)) == value


def test_scalar_round_trips() -> None:
    for value in [None, True, False, 0, -7, 1.5, "plain", "needs quoting: yes", ""]:
        assert toon.decode(toon.encode(value)) == value


def test_quoted_strings_survive() -> None:
    tricky = ["a,b", "10:30", "true", "null", "05", "- item", "#comment", " padded ", 'q"q']
    encoded = toon.encode({"values": tricky})
    assert toon.decode(encoded) == {"values": tricky}


def test_root_list_of_records_is_tabular() -> None:
    rows = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
    encoded = toon.encode(rows)
    assert encoded == b"[2]{a,b}:\n  1,x\n  2,y"
    assert toon.decode(encoded) == rows


def test_enc_hook_rescues_unsupported_values() -> None:
    with pytest.raises(msgspec.EncodeError):
        toon.encode({"when": complex(1, 2)})

    encoded = toon.encode({"when": complex(1, 2)}, enc_hook=lambda value: str(value)[1:-1])
    assert toon.decode(encoded) == {"when": "1+2j"}


class Point:
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y


class PointDoc(msgspec.Struct):
    point: Point


def test_dec_hook_builds_custom_types() -> None:
    def dec_hook(cls: type, value: object) -> object:
        if cls is Point and isinstance(value, dict):
            return Point(**value)
        raise NotImplementedError

    value = toon.decode(b"point:\n  x: 1\n  y: 2", type=PointDoc, dec_hook=dec_hook)
    assert (value.point.x, value.point.y) == (1, 2)


def test_non_finite_floats_raise_encode_error() -> None:
    with pytest.raises(msgspec.EncodeError):
        toon.encode({"bad": float("nan")})
    with pytest.raises(msgspec.EncodeError):
        toon.encode({"bad": float("inf")})


def test_empty_containers() -> None:
    # Canonical empty array is the literal `[]`; `[0]:` stays decodable.
    assert toon.encode({"empty_list": []}) == b"empty_list: []"
    assert toon.decode(b"empty_list: []") == {"empty_list": []}
    assert toon.decode(b"empty_list[0]:") == {"empty_list": []}
    assert toon.encode([]) == b"[]"
    assert toon.decode(b"[]") == []
    assert toon.encode({"empty_obj": {}}) == b"empty_obj:"
    assert toon.decode(b"empty_obj:") == {"empty_obj": {}}
    assert toon.decode(b"") == {}


def test_keyed_tabular_round_trip() -> None:
    value = {
        "servers": {
            "alpha": {"host": "a.example.com", "port": 8080},
            "beta": {"host": "b.example.com", "port": 9090},
        }
    }
    encoded = toon.encode(value)
    assert encoded == (
        b"servers[2:]{host,port}:\n  alpha: a.example.com,8080\n  beta: b.example.com,9090"
    )
    assert toon.decode(encoded) == value


def test_dict_target_type() -> None:
    value = toon.decode(b"a: 1\nb: 2", type=dict[str, int])
    assert value == {"a": 1, "b": 2}


def test_bytearray_and_memoryview_inputs() -> None:
    text = b"a: 1"
    assert toon.decode(bytearray(text)) == {"a": 1}
    assert toon.decode(memoryview(text)) == {"a": 1}


def test_comments_are_skipped() -> None:
    value = toon.decode(b"# heading\na: 1\n# note\nb: 2")
    assert value == {"a": 1, "b": 2}
