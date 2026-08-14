"""Native encode parity for Python containers and binary values."""

from __future__ import annotations

import base64
from typing import Any

import msgspec
import msgspec_toon as toon
import pytest


class NativeTypesRow(msgspec.Struct):
    tags: set[str]
    frozen_tags: frozenset[str]
    blob: bytes


class SetSubclass(set[Any]):
    pass


class FrozenSetSubclass(frozenset[Any]):
    pass


class BytesSubclass(bytes):
    pass


class BytearraySubclass(bytearray):
    pass


def projected(value: Any) -> Any:
    """The msgspec value model that TOON can represent on its wire."""
    return msgspec.to_builtins(value)


@pytest.mark.parametrize(
    "value",
    [
        set(),
        {1, 2},
        {"alpha", "beta", "gamma"},
        frozenset(),
        frozenset({1, 2}),
        SetSubclass({1, 2}),
        FrozenSetSubclass({1, 2}),
    ],
)
def test_sets_encode_as_their_msgspec_projection(value: Any) -> None:
    expected = toon.encode(projected(value))
    assert toon.encode(value) == expected
    assert toon.Encoder().encode(value) == expected
    assert toon.decode(expected) == projected(value)


@pytest.mark.parametrize(
    "value",
    [
        b"",
        b"a",
        b"ab",
        b"abc",
        bytes(range(256)),
        # These base64 spellings look like reserved or numeric TOON scalars.
        base64.b64decode("null"),
        base64.b64decode("true"),
        base64.b64decode("1234"),
    ],
)
def test_bytes_encode_as_their_msgspec_projection(value: bytes) -> None:
    expected = toon.encode(projected(value))
    assert toon.encode(value) == expected
    assert toon.Encoder().encode(value) == expected
    assert toon.decode(expected) == projected(value)


@pytest.mark.parametrize(
    "value",
    [{1, 2}, frozenset({1, 2}), b"ab"],
)
def test_native_encode_types_bypass_enc_hook(value: Any) -> None:
    calls: list[Any] = []
    assert toon.encode(value, enc_hook=lambda item: calls.append(item) or "hooked") == toon.encode(
        projected(value)
    )
    assert calls == []


def test_native_encode_types_work_inside_structs() -> None:
    value = NativeTypesRow({"alpha", "beta"}, frozenset({"gamma"}), b"ab")
    assert toon.encode(value) == toon.encode(projected(value))


def test_bytes_are_scalars_inside_compact_arrays() -> None:
    values = [b"ab", b"cd"]
    assert toon.encode(values) == toon.encode([projected(value) for value in values])


@pytest.mark.parametrize("factory", [bytearray, memoryview])
@pytest.mark.parametrize(
    "payload",
    [b"", b"a", b"ab", b"abc", bytes(range(256))],
)
def test_buffer_values_encode_as_their_msgspec_projection(
    factory: type[bytearray | memoryview], payload: bytes
) -> None:
    value = factory(payload)
    expected = toon.encode(payload)
    assert toon.encode(value) == expected
    assert toon.Encoder().encode(value) == expected
    assert toon.decode(expected) == projected(value)


def test_non_contiguous_memoryview_matches_msgspec_refusal() -> None:
    value = memoryview(b"abcdef")[::2]
    with pytest.raises(BufferError, match="not C-contiguous"):
        msgspec.to_builtins(value)
    with pytest.raises(BufferError, match="not C-contiguous"):
        toon.encode(value)


@pytest.mark.parametrize("value", [bytearray(b"ab"), memoryview(b"ab")])
def test_buffer_values_bypass_enc_hook(value: bytearray | memoryview) -> None:
    calls: list[Any] = []
    assert toon.encode(value, enc_hook=lambda item: calls.append(item) or "hooked") == toon.encode(
        b"ab"
    )
    assert calls == []


@pytest.mark.parametrize("value", [bytearray(b"ab"), memoryview(b"ab")])
def test_buffer_values_work_inside_structs(value: bytearray | memoryview) -> None:
    item = NativeTypesRow(set(), frozenset(), value)  # type: ignore[arg-type]
    assert toon.encode(item) == toon.encode(projected(item))


def test_buffer_values_are_scalars_inside_compact_arrays() -> None:
    values = [bytearray(b"ab"), memoryview(b"cd")]
    assert toon.encode(values) == toon.encode([projected(value) for value in values])


@pytest.mark.parametrize("value", [BytesSubclass(b"ab"), BytearraySubclass(b"ab")])
def test_binary_subclasses_remain_refused_with_a_working_hook_route(value: Any) -> None:
    with pytest.raises(msgspec.EncodeError, match=f"unsupported type: {type(value).__name__}"):
        toon.encode(value)
    assert toon.encode(value, enc_hook=lambda item: bytes(item)) == toon.encode(b"ab")


@pytest.mark.parametrize("value", [{1: "a"}, {"outer": {1: "a"}}])
def test_non_string_mapping_key_error_names_conversion_route(value: Any) -> None:
    with pytest.raises(
        msgspec.EncodeError,
        match=r"msgspec\.to_builtins\(\.\.\., str_keys=True\)",
    ):
        toon.encode(value)
