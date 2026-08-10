"""Unsupported annotations fail through one stable, payload-safe contract."""

from __future__ import annotations

from typing import Literal

import msgspec
import msgspec_toon as toon
import pytest
from msgspec_toon import _native
from msgspec_toon._plan import compile_native_plan


class Recursive(msgspec.Struct):
    value: int
    child: Recursive | None = None


class NestedMapping(msgspec.Struct):
    children: list[dict[int, int]]


class SecretCustomType:
    pass


class NestedCustom(msgspec.Struct):
    child: SecretCustomType


class Positional(msgspec.Struct, array_like=True):
    value: int


class Cat(msgspec.Struct, tag="cat"):
    name: str


class Dog(msgspec.Struct, tag="dog"):
    name: str


def _assert_plan_error(
    callable_: object,
    *,
    code: str,
    path: tuple[str, ...],
) -> toon.TypePlanError:
    assert callable(callable_)
    with pytest.raises(toon.TypePlanError) as caught:
        callable_()
    error = caught.value
    assert isinstance(error, TypeError)
    assert error.code == code
    assert error.path == path
    assert error.__cause__ is None
    assert "SecretCustomType" not in str(error)
    return error


def test_type_plan_error_is_public() -> None:
    assert toon.TypePlanError.__module__ == "msgspec_toon._exceptions"


def test_nested_mapping_key_has_schema_path() -> None:
    error = _assert_plan_error(
        lambda: toon.Decoder(NestedMapping),
        code="unsupported_mapping_key",
        path=("children", "[]", "[key]"),
    )
    assert str(error) == (
        "unsupported type annotation at $.children[][key] (unsupported_mapping_key)"
    )


def test_recursive_annotation_compiles_without_recursion_error() -> None:
    decoder = toon.Decoder(Recursive)
    assert decoder.decode("value: 1\nchild: null") == Recursive(1)


def test_inspection_failure_does_not_leak_implementation_message() -> None:
    error = _assert_plan_error(
        lambda: toon.Decoder(Literal["SENTINEL", 1]),
        code="unsupported_annotation",
        path=(),
    )
    assert "not supported" not in str(error)
    assert "SENTINEL" not in str(error)


def test_custom_type_requires_and_uses_dec_hook() -> None:
    _assert_plan_error(
        lambda: toon.Decoder(NestedCustom),
        code="unsupported_custom_type",
        path=("child",),
    )

    decoder = toon.Decoder(
        NestedCustom,
        dec_hook=lambda type_, value: SecretCustomType() if type_ is SecretCustomType else value,
    )
    assert isinstance(decoder.decode(b"child:").child, SecretCustomType)


def test_array_like_decoder_constructs() -> None:
    assert toon.decode("[1]:\n  - 1", type=Positional) == Positional(1)


def test_tagged_union_decoder_constructs() -> None:
    assert toon.decode("type: cat\nname: x", type=Cat | Dog) == Cat("x")


def test_native_plan_compilation_fault_is_contained(monkeypatch: pytest.MonkeyPatch) -> None:
    class Fresh(msgspec.Struct):
        value: int

    compile_native_plan.cache_clear()

    def fail_native_compile(plan: object) -> object:
        raise ValueError("native implementation detail SENTINEL")

    monkeypatch.setattr(_native, "compile_plan", fail_native_compile)
    error = _assert_plan_error(
        lambda: toon.Decoder(Fresh),
        code="invalid_native_plan",
        path=(),
    )
    assert "SENTINEL" not in str(error)
