"""The public surface mirrors msgspec.json; untyped decode and hooks."""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor

import msgspec
import msgspec._core
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


def test_delimiter_options_round_trip() -> None:
    value = {"tags": ["a,b", "c|d", "plain"], "rows": [{"x": 1, "y": "u,v"}, {"x": 2, "y": "w"}]}
    for delimiter in (",", "\t", "|"):
        encoded = toon.encode(value, delimiter=delimiter)
        assert toon.decode(encoded) == value, delimiter
    tab = toon.encode({"tags": ["a", "b"]}, delimiter="\t")
    assert tab == b"tags[2\t]: a\tb"


def test_indent_options_round_trip() -> None:
    value = {"outer": {"inner": {"deep": 1}}, "rows": [{"x": 1}, {"x": 2}]}
    encoded = toon.encode(value, indent=4)
    assert b"    inner:" in encoded
    assert toon.decode(encoded, indent_size=4) == value


def test_default_options_are_byte_identical() -> None:
    value = {"rows": [{"x": 1, "y": "a"}, {"x": 2, "y": "b"}], "note": "n"}
    assert toon.encode(value) == toon.encode(value, delimiter=",", indent=2)


def test_invalid_options_are_refused() -> None:
    with pytest.raises(TypeError):
        toon.encode({"a": 1}, delimiter=";")
    with pytest.raises(TypeError):
        toon.encode({"a": 1}, indent=0)


def test_unimplemented_encoder_options_fail_loudly() -> None:
    """Silent acceptance is not compatibility.

    A caller who asks for sorted keys and receives insertion order has been
    given a wrong answer. The domain check runs first, so a value msgspec
    itself rejects still raises ValueError — "not a thing" and "not yet" stay
    distinguishable.
    """
    for option in ("order", "decimal_format", "uuid_format"):
        with pytest.raises(ValueError, match=f"`{option}` must be one of"):
            toon.Encoder(**{option: "nonsense"})

    for option, value in (("order", "sorted"), ("order", "deterministic")):
        with pytest.raises(NotImplementedError, match=option):
            toon.Encoder(**{option: value})
    with pytest.raises(NotImplementedError):
        toon.encode({"a": 1}, order="sorted")
    with pytest.raises(NotImplementedError):
        toon.Encoder(decimal_format="number")

    # Defaults stay silent, including when spelled out.
    assert (
        toon.Encoder(order=None, decimal_format="string", uuid_format="canonical").encode(
            {"b": 1, "a": 2}
        )
        == b"b: 1\na: 2"
    )


def test_encoder_discovers_optional_msgspec_c_api() -> None:
    encoder = toon.Encoder()
    expected = "capsule" if hasattr(msgspec._core, "_C_API") else "attribute"
    assert encoder._native._struct_access == expected


def test_unset_struct_field_still_raises_attribute_error() -> None:
    class Pair(msgspec.Struct):
        left: int
        right: int

    value = Pair(1, 2)
    del value.right
    encoder = toon.Encoder()
    message = (
        "Struct field 'right' is unset"
        if encoder._native._struct_access == "capsule"
        else "object has no attribute 'right'"
    )
    with pytest.raises(AttributeError, match=message):
        encoder.encode(value)


@pytest.mark.skipif(
    not hasattr(sys, "_is_gil_enabled") or sys._is_gil_enabled(),
    reason="requires a free-threaded CPython build",
)
def test_capsule_struct_access_is_safe_during_concurrent_mutation() -> None:
    if not hasattr(msgspec._core, "_C_API"):
        pytest.skip("requires the optional msgspec C API")

    class Cell(msgspec.Struct):
        value: int

    cell = Cell(1)
    encoder = toon.Encoder()

    def mutate() -> None:
        for index in range(20_000):
            cell.value = 1 + index % 2

    def encode() -> None:
        for _ in range(20_000):
            assert encoder.encode(cell) in (b"value: 1", b"value: 2")

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(mutate), *(pool.submit(encode) for _ in range(4))]
        for future in futures:
            future.result()
