"""msgspec_toon — a native TOON 4.1 codec with direct msgspec.Struct decoding.

The supported substitution is::

    # before
    from msgspec import json as codec
    # after
    import msgspec_toon as codec
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final, cast

import msgspec

from . import _native  # type: ignore[attr-defined]
from ._plan import compile_plan, encode_plan_for

__all__ = [
    "DecodeError",
    "Decoder",
    "EncodeError",
    "Encoder",
    "ValidationError",
    "decode",
    "encode",
]

EncodeError: Final = msgspec.EncodeError


class DecodeError(msgspec.DecodeError):
    """A TOON syntax error carrying coordinates but never source text."""

    __slots__ = ("code", "column", "line")

    def __init__(
        self,
        message: str,
        *,
        line: int,
        column: int | None,
        code: str,
    ) -> None:
        super().__init__(message)
        self.line = line
        self.column = column
        self.code = code


class ValidationError(msgspec.ValidationError):
    """A typed decoding error with TOON coordinates."""

    __slots__ = ("code", "column", "line")

    def __init__(
        self,
        message: str,
        *,
        line: int,
        column: int | None,
        code: str,
    ) -> None:
        super().__init__(message)
        self.line = line
        self.column = column
        self.code = code


def _translate_fault(exc: _native.NativeFault) -> BaseException:
    cls = ValidationError if exc.validation else DecodeError
    return cls(
        exc.safe_message,
        line=exc.line,
        column=exc.column,
        code=exc.code,
    )


class Encoder:
    __slots__ = ("_native",)

    def __init__(
        self,
        *,
        enc_hook: Callable[[Any], Any] | None = None,
        decimal_format: str | Callable[[Any], Any] = "string",
        uuid_format: str = "canonical",
        order: str | None = None,
    ) -> None:
        self._native = _native.Encoder(
            enc_hook=enc_hook,
            plan_source=encode_plan_for,
            struct_base=msgspec.Struct,
            encode_error=msgspec.EncodeError,
        )

    def encode(self, obj: Any) -> bytes:
        try:
            return cast(bytes, self._native.encode(obj))
        except _native.NativeFault as exc:
            raise _translate_fault(exc) from None


class Decoder:
    __slots__ = ("_native", "_type")

    def __init__(
        self,
        type: Any = Any,
        *,
        strict: bool = True,
        dec_hook: Callable[[type, Any], Any] | None = None,
        float_hook: Callable[[str], Any] | None = None,
    ) -> None:
        plan = None if type is Any else compile_plan(type)
        self._type = type
        self._native = _native.Decoder(
            plan=plan,
            strict=strict,
            dec_hook=dec_hook,
            float_hook=float_hook,
        )

    def decode(self, buf: bytes | bytearray | memoryview | str) -> Any:
        try:
            return self._native.decode(buf)
        except _native.NativeFault as exc:
            raise _translate_fault(exc) from None


def encode(
    obj: Any,
    *,
    enc_hook: Callable[[Any], Any] | None = None,
    order: str | None = None,
) -> bytes:
    return Encoder(enc_hook=enc_hook, order=order).encode(obj)


def decode(
    buf: bytes | bytearray | memoryview | str,
    *,
    type: Any = Any,
    strict: bool = True,
    dec_hook: Callable[[type, Any], Any] | None = None,
) -> Any:
    return Decoder(type, strict=strict, dec_hook=dec_hook).decode(buf)
