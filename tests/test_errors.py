"""Errors carry position and never echo the payload (AD-007)."""

from __future__ import annotations

import msgspec
import msgspec_toon as toon
import msgspec_toon._native as native
import pytest


class Metadata(msgspec.Struct, frozen=True):
    alias: str
    region: int


class Worker(msgspec.Struct, frozen=True):
    pid: int
    provider: str
    metadata: Metadata


class Document(msgspec.Struct, frozen=True):
    workers: list[Worker]


class Leaf(msgspec.Struct):
    value: int


class TupleRoot(msgspec.Struct):
    pair: tuple[Leaf, Leaf]


class Cat(msgspec.Struct, tag="cat"):
    value: int


class Dog(msgspec.Struct, tag="dog"):
    value: int


class UnionRoot(msgspec.Struct):
    pet: Cat | Dog


class Node(msgspec.Struct):
    value: int
    child: Node | None = None


def _assert_no_leak(exc: BaseException, sentinel: str) -> None:
    assert sentinel not in str(exc)
    assert sentinel not in repr(exc)
    assert all(sentinel not in repr(item) for item in exc.args)
    for name in ("line", "column", "code", "path"):
        assert sentinel not in repr(getattr(exc, name, None))
    assert sentinel not in repr(getattr(exc, "__dict__", None))


def test_error_never_echoes_payload() -> None:
    sentinel = "SENTINEL_8841_DO_NOT_LEAK"
    malformed = f'workers[1]{{pid}}:\n  "{sentinel}'.encode()

    with pytest.raises(toon.DecodeError) as info:
        toon.decode(malformed, type=Document)
    _assert_no_leak(info.value, sentinel)
    assert info.value.line == 2


def test_untyped_error_never_echoes_payload() -> None:
    sentinel = "SENTINEL_9313_DO_NOT_LEAK"
    malformed = f'key: "{sentinel}'.encode()

    with pytest.raises(toon.DecodeError) as info:
        toon.decode(malformed)
    _assert_no_leak(info.value, sentinel)
    assert info.value.line == 1


def test_indent_diagnostic_reports_only_a_coordinate() -> None:
    sentinel = "SENTINEL_2077_DO_NOT_LEAK"
    malformed = f"outer:\n {sentinel}: 1".encode()

    with pytest.raises(toon.DecodeError) as info:
        toon.decode(malformed)
    _assert_no_leak(info.value, sentinel)
    assert info.value.code == "invalid_indent"
    assert info.value.line == 2
    assert info.value.column == 2
    assert "observed indentation is 1 space" in str(info.value)


def test_validation_error_never_echoes_payload() -> None:
    sentinel = "SENTINEL_5150_DO_NOT_LEAK"
    text = f"workers[1]{{pid,provider,metadata{{alias,region}}}}:\n  {sentinel},x,y,z".encode()

    with pytest.raises(toon.ValidationError) as info:
        toon.decode(text, type=Document)
    _assert_no_leak(info.value, sentinel)
    assert info.value.line == 2


@pytest.mark.parametrize(
    ("document", "type_", "path"),
    [
        (
            b"workers[1]{pid,provider,metadata{alias,region}}:\n  1,x,y,SENTINEL_PATH_VALUE",
            Document,
            ("workers", "[0]", "metadata", "region"),
        ),
        (
            b"pair[2]{value}:\n  1\n  SENTINEL_PATH_VALUE",
            TupleRoot,
            ("pair", "[1]", "value"),
        ),
        (
            b"pet:\n  type: cat\n  value: SENTINEL_PATH_VALUE",
            UnionRoot,
            ("pet", "value"),
        ),
        (
            b"value: 1\nchild:\n  value: SENTINEL_PATH_VALUE\n  child: null",
            Node,
            ("child", "value"),
        ),
    ],
    ids=("field-group-list", "fixed-tuple", "tagged-union", "recursive"),
)
def test_typed_validation_paths_use_schema_and_structural_positions(
    document: bytes, type_: object, path: tuple[str, ...]
) -> None:
    with pytest.raises(toon.ValidationError) as info:
        toon.decode(document, type=type_)
    assert info.value.path == path
    assert "SENTINEL_PATH_VALUE" not in repr(info.value.path)


def test_missing_field_path_comes_from_the_compiled_schema() -> None:
    with pytest.raises(toon.ValidationError) as info:
        toon.decode(b"value: 1\nchild:\n  child: null", type=Node)
    assert info.value.path == ("child", "value")


def test_payload_key_cannot_enter_public_or_native_fault_attributes() -> None:
    class Closed(msgspec.Struct, forbid_unknown_fields=True):
        known: int

    sentinel = "SENTINEL_PATH_KEY"
    decoder = toon.Decoder(Closed)
    document = f"known: 1\n{sentinel}: 2".encode()

    with pytest.raises(toon.ValidationError) as public_info:
        decoder.decode(document)
    _assert_no_leak(public_info.value, sentinel)
    assert public_info.value.path == ()

    with pytest.raises(native.NativeFault) as native_info:
        decoder._native.decode(document)
    for name in ("safe_message", "code", "line", "column", "validation", "path"):
        assert sentinel not in repr(getattr(native_info.value, name, None))


def test_untyped_and_syntax_errors_have_an_empty_path() -> None:
    with pytest.raises(toon.DecodeError) as info:
        toon.decode(b'key: "unclosed')
    assert info.value.path == ()


def test_errors_subclass_msgspec_errors() -> None:
    with pytest.raises(msgspec.DecodeError):
        toon.decode(b'key: "unclosed')
    with pytest.raises(msgspec.ValidationError):
        toon.decode(b"count: notanint", type=dict[str, int])


def test_strict_is_the_default() -> None:
    with pytest.raises(toon.DecodeError):
        toon.decode(b"a:\n\tb: 1")  # tab indentation
    with pytest.raises(toon.DecodeError):
        toon.decode(b"a: 1\na: 2")  # duplicate key
    with pytest.raises(toon.DecodeError):
        toon.decode(b"rows[2]: 1,2,3")  # length mismatch


def test_wrong_row_width_carries_position() -> None:
    with pytest.raises(toon.DecodeError) as info:
        toon.decode(b"rows[2]{a,b}:\n  1,2\n  3")
    assert info.value.code == "wrong_row_width"
    assert info.value.line == 3


def test_non_strict_duplicate_keys_last_write_wins() -> None:
    value = toon.decode(b"a: 1\na: 2", strict=False)
    assert value == {"a": 2}
