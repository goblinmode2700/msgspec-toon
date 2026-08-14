"""msgspec_toon — a native TOON 4.1 codec with direct msgspec.Struct decoding.

The supported substitution is::

    # before
    from msgspec import json as codec
    # after
    import msgspec_toon as codec
"""

from __future__ import annotations

import datetime
import decimal
import enum
import uuid
from collections.abc import Callable
from typing import Annotated, Any, Final, cast, get_origin

import msgspec

from . import _native  # type: ignore[attr-defined]
from ._exceptions import TypePlanError
from ._options import ENCODER_OPTIONS, validate_python_options
from ._plan import compile_native_plan, compile_plan, encode_plan_for

__all__ = [
    "DecodeError",
    "Decoder",
    "EncodeError",
    "Encoder",
    "TypePlanError",
    "ValidationError",
    "decode",
    "encode",
]

EncodeError: Final = msgspec.EncodeError

_NON_STRING_KEY_ERROR: Final = (
    "object keys must be strings; convert with msgspec.to_builtins(..., str_keys=True)"
)


def _new_encode_error(message: str) -> msgspec.EncodeError:
    """Translate stable native error codes without changing native hot-path layout."""
    if message == "object keys must be strings":
        message = _NON_STRING_KEY_ERROR
    return msgspec.EncodeError(message)


# Stable type identities and the exact-pinned msgspec datetime normalizer.
_NATIVE_SCALAR_TYPES: Final = (
    datetime.datetime,
    datetime.date,
    datetime.time,
    datetime.timedelta,
    uuid.UUID,
    decimal.Decimal,
    enum.Enum,
)
_MSGSPEC_JSON_ENCODE: Final = msgspec.json.encode
_MSGSPEC_CONVERT: Final = msgspec.convert


class _RawScalar(str):
    """Private, exact-type marker for an already formatted TOON scalar."""


_NOT_NATIVE: Final = object()


def _is_native_scalar(value: Any) -> bool:
    return type(value) in (bytes, bytearray, memoryview) or isinstance(value, _NATIVE_SCALAR_TYPES)


class _EncodeHook:
    __slots__ = ("decimal_format", "user_hook", "uuid_format")

    def __init__(
        self,
        user_hook: Callable[[Any], Any] | None,
        decimal_format: str,
        uuid_format: str,
    ) -> None:
        self.user_hook = user_hook
        self.decimal_format = decimal_format
        self.uuid_format = uuid_format

    def __call__(self, value: Any) -> Any:
        normalized = self._normalize(value)
        if normalized is not _NOT_NATIVE:
            return normalized
        if self.user_hook is not None:
            return self.user_hook(value)
        raise msgspec.EncodeError(f"unsupported type: {type(value).__name__}")

    def _normalize(self, value: Any) -> Any:
        value_type = type(value)
        if value_type is bytearray:
            if len(value) > 2**32 - 1:
                raise msgspec.EncodeError("bytes objects longer than 2**32 - 1 are not encodable")
            return bytes(value)
        if value_type is memoryview:
            if not value.c_contiguous:
                raise BufferError("memoryview: underlying buffer is not C-contiguous")
            if value.nbytes > 2**32 - 1:
                raise msgspec.EncodeError("bytes objects longer than 2**32 - 1 are not encodable")
            return value.tobytes()
        if isinstance(
            value,
            (datetime.datetime, datetime.date, datetime.time, datetime.timedelta),
        ):
            return _RawScalar(_MSGSPEC_JSON_ENCODE(value).decode())
        if isinstance(value, uuid.UUID):
            text = value.hex if self.uuid_format == "hex" else str(value)
            return _RawScalar(f'"{text}"')
        if isinstance(value, decimal.Decimal):
            if self.decimal_format == "number":
                if not value.is_finite():
                    raise msgspec.EncodeError(
                        "non-finite Decimal values are not encodable as TOON numbers"
                    )
                return _RawScalar(str(value))
            return _RawScalar(f'"{value}"')
        if isinstance(value, enum.Enum):
            return value.value
        return _NOT_NATIVE


class _DecodeHook:
    __slots__ = ("strict", "user_hook")

    def __init__(self, user_hook: Callable[[type, Any], Any] | None, strict: bool) -> None:
        self.user_hook = user_hook
        self.strict = strict

    def __call__(self, type_: type, value: Any) -> Any:
        if (
            type_ in _NATIVE_SCALAR_TYPES[:-1]
            or (isinstance(type_, type) and issubclass(type_, enum.Enum))
            or get_origin(type_) is Annotated
        ):
            return _MSGSPEC_CONVERT(value, type=type_, strict=self.strict)
        if self.user_hook is not None:
            return self.user_hook(type_, value)
        raise TypeError("unsupported decode type")


_plan_source = cast(Any, encode_plan_for)
_plan_source.__toon_raw_scalar_type__ = _RawScalar
_plan_source.__toon_is_native_scalar__ = _is_native_scalar
_plan_source.__toon_default_encode_hook__ = _EncodeHook(None, "string", "canonical")


class DecodeError(msgspec.DecodeError):
    """A TOON syntax error carrying coordinates but never source text."""

    __slots__ = ("code", "column", "line", "path")

    def __init__(
        self,
        message: str,
        *,
        line: int,
        column: int | None,
        code: str,
        path: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.line = line
        self.column = column
        self.code = code
        self.path = path


class ValidationError(msgspec.ValidationError):
    """A typed decoding error with TOON coordinates."""

    __slots__ = ("code", "column", "line", "path")

    def __init__(
        self,
        message: str,
        *,
        line: int,
        column: int | None,
        code: str,
        path: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.line = line
        self.column = column
        self.code = code
        self.path = path


def _observed_indent(buf: bytes | bytearray | memoryview | str, line: int) -> int | None:
    """Return a structural count only; never retain or format source text."""
    if line < 1:
        return None
    source = buf if isinstance(buf, str) else memoryview(buf).cast("B")
    newline = "\n" if isinstance(source, str) else 10
    space = " " if isinstance(source, str) else 32
    start = 0
    current_line = 1
    for index, value in enumerate(source):
        if current_line == line:
            start = index
            break
        if value == newline:
            current_line += 1
    else:
        if current_line != line:
            return None
        start = len(source)

    indent = 0
    while start + indent < len(source) and source[start + indent] == space:
        indent += 1
    return indent


def _translate_fault(
    exc: _native.NativeFault,
    *,
    buf: bytes | bytearray | memoryview | str | None = None,
) -> BaseException:
    cls = ValidationError if exc.validation else DecodeError
    message = exc.safe_message
    column = exc.column
    if buf is not None and exc.code in {"invalid_indent", "depth_jump", "wrong_array_length"}:
        observed = _observed_indent(buf, exc.line)
        if observed:
            unit = "space" if observed == 1 else "spaces"
            column = observed + 1
            if exc.code == "invalid_indent":
                action = "pass the matching indent_size"
            elif exc.code == "depth_jump":
                action = "indentation increased by more than one level; check indent_size"
            else:
                action = "check indent_size and the declared row count"
            message = (
                f"observed indentation is {observed} {unit}; {action} "
                f"at line {exc.line}, column {column}"
            )
    return cls(
        message,
        line=exc.line,
        column=column,
        code=exc.code,
        path=tuple(exc.path),
    )


class Encoder:
    __slots__ = ("_native",)

    def __init__(
        self,
        *,
        enc_hook: Callable[[Any], Any] | None = None,
        decimal_format: str = "string",
        uuid_format: str = "canonical",
        order: str | None = None,
        delimiter: str = ",",
        indent: int = 2,
    ) -> None:
        validate_python_options(
            ENCODER_OPTIONS,
            {
                "decimal_format": decimal_format,
                "uuid_format": uuid_format,
                "order": order,
            },
        )
        native_hook = (
            None
            if enc_hook is None and decimal_format == "string" and uuid_format == "canonical"
            else _EncodeHook(enc_hook, decimal_format, uuid_format)
        )
        self._native = _native.Encoder(
            enc_hook=native_hook,
            plan_source=encode_plan_for,
            struct_base=msgspec.Struct,
            encode_error=_new_encode_error,
            delimiter=delimiter,
            indent=indent,
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
        indent_size: int = 2,
        dec_hook: Callable[[type, Any], Any] | None = None,
        float_hook: Callable[[str], Any] | None = None,
    ) -> None:
        allow_custom = dec_hook is not None
        graph = None if type is Any else compile_plan(type, allow_custom=allow_custom)
        plan = None if type is Any else compile_native_plan(type, allow_custom=allow_custom)
        needs_native_hook = graph is not None and any(
            node.kind == "native_scalar" for node in graph.nodes
        )
        native_hook = _DecodeHook(dec_hook, strict) if needs_native_hook else dec_hook
        self._type = type
        self._native = _native.Decoder(
            plan=plan,
            strict=strict,
            indent_size=indent_size,
            dec_hook=native_hook,
            float_hook=float_hook,
        )

    def decode(self, buf: bytes | bytearray | memoryview | str) -> Any:
        try:
            return self._native.decode(buf)
        except _native.NativeFault as exc:
            raise _translate_fault(exc, buf=buf) from None


_DEFAULT_ENCODER: Final = Encoder()


def encode(
    obj: Any,
    *,
    enc_hook: Callable[[Any], Any] | None = None,
    decimal_format: str = "string",
    uuid_format: str = "canonical",
    order: str | None = None,
    delimiter: str = ",",
    indent: int = 2,
) -> bytes:
    if (
        enc_hook is None
        and decimal_format == "string"
        and uuid_format == "canonical"
        and order is None
        and delimiter == ","
        and indent == 2
    ):
        return _DEFAULT_ENCODER.encode(obj)
    return Encoder(
        enc_hook=enc_hook,
        decimal_format=decimal_format,
        uuid_format=uuid_format,
        order=order,
        delimiter=delimiter,
        indent=indent,
    ).encode(obj)


def decode(
    buf: bytes | bytearray | memoryview | str,
    *,
    type: Any = Any,
    strict: bool = True,
    indent_size: int = 2,
    dec_hook: Callable[[type, Any], Any] | None = None,
    float_hook: Callable[[str], Any] | None = None,
) -> Any:
    return Decoder(
        type,
        strict=strict,
        indent_size=indent_size,
        dec_hook=dec_hook,
        float_hook=float_hook,
    ).decode(buf)
