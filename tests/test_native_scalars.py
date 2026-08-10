"""msgspec-native scalar values normalize before the caller's encode hook."""

from __future__ import annotations

import datetime
import decimal
import enum
import uuid
from typing import Any

import msgspec
import msgspec_toon as toon
import pytest


class TextValue(enum.Enum):
    RED = "red"


class IntegerValue(enum.IntEnum):
    TWO = 2


class NativeRow(msgspec.Struct):
    when: datetime.date
    amount: decimal.Decimal


NATIVE_SCALARS = (
    (datetime.date(2026, 8, 9), b'"2026-08-09"'),
    (
        datetime.datetime(2026, 8, 9, 1, 2, 3, 456, datetime.UTC),
        b'"2026-08-09T01:02:03.000456Z"',
    ),
    (datetime.time(1, 2, 3, 456), b'"01:02:03.000456"'),
    (datetime.timedelta(days=2, seconds=3, microseconds=4), b'"P2DT3.000004S"'),
    (uuid.UUID("12345678-1234-5678-1234-567812345678"), b'"12345678-1234-5678-1234-567812345678"'),
    (decimal.Decimal("1.2300"), b'"1.2300"'),
    (TextValue.RED, b"red"),
    (IntegerValue.TWO, b"2"),
)


@pytest.mark.parametrize(("value", "expected"), NATIVE_SCALARS)
def test_native_scalar_canonical_bytes(value: Any, expected: bytes) -> None:
    assert toon.encode(value) == expected


@pytest.mark.parametrize(("value", "expected"), NATIVE_SCALARS)
def test_native_scalar_normalization_precedes_enc_hook(value: Any, expected: bytes) -> None:
    calls: list[Any] = []
    assert toon.encode(value, enc_hook=lambda item: calls.append(item) or "hooked") == expected
    assert calls == []


def test_datetime_family_matches_msgspec_text() -> None:
    for value, expected in NATIVE_SCALARS[:4]:
        assert msgspec.json.encode(value) == expected


def test_decimal_formats_keep_exact_text() -> None:
    value = decimal.Decimal("0.12345678912345678912345678900")
    assert toon.Encoder(decimal_format="string").encode(value) == (
        b'"0.12345678912345678912345678900"'
    )
    assert toon.Encoder(decimal_format="number").encode(value) == (
        b"0.12345678912345678912345678900"
    )
    assert toon.encode(value, decimal_format="number") == b"0.12345678912345678912345678900"


def test_uuid_formats_match_msgspec() -> None:
    value = uuid.UUID("12345678-1234-5678-1234-567812345678")
    assert toon.Encoder(uuid_format="canonical").encode(value) == msgspec.json.Encoder(
        uuid_format="canonical"
    ).encode(value)
    assert toon.Encoder(uuid_format="hex").encode(value) == msgspec.json.Encoder(
        uuid_format="hex"
    ).encode(value)
    assert toon.encode(value, uuid_format="hex") == b'"12345678123456781234567812345678"'


def test_native_scalars_stay_scalar_inside_containers() -> None:
    values = [datetime.date(2026, 8, 9), datetime.date(2026, 8, 10)]
    assert toon.encode({"dates": values}) == b'dates[2]: "2026-08-09","2026-08-10"'


def test_native_scalars_keep_struct_arrays_tabular() -> None:
    values = [
        NativeRow(datetime.date(2026, 8, 9), decimal.Decimal("1.20")),
        NativeRow(datetime.date(2026, 8, 10), decimal.Decimal("2.30")),
    ]
    assert toon.encode(values) == (
        b'[2]{when,amount}:\n  "2026-08-09","1.20"\n  "2026-08-10","2.30"'
    )


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_decimal_number_is_rejected(value: str) -> None:
    with pytest.raises(msgspec.EncodeError, match="non-finite Decimal"):
        toon.encode(decimal.Decimal(value), decimal_format="number")


def test_enc_hook_errors_for_unsupported_values_propagate() -> None:
    marker = RuntimeError("hook marker")

    def fail(value: object) -> object:
        raise marker

    with pytest.raises(RuntimeError) as caught:
        toon.encode(complex(1, 2), enc_hook=fail)
    assert caught.value is marker
