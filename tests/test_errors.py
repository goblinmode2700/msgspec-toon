"""Errors carry position and never echo the payload (AD-007)."""

from __future__ import annotations

import msgspec
import msgspec_toon as toon
import pytest


class Metadata(msgspec.Struct, frozen=True):
    alias: str
    region: str


class Worker(msgspec.Struct, frozen=True):
    pid: int
    provider: str
    metadata: Metadata


class Document(msgspec.Struct, frozen=True):
    workers: list[Worker]


def _assert_no_leak(exc: BaseException, sentinel: str) -> None:
    assert sentinel not in str(exc)
    assert sentinel not in repr(exc)
    assert all(sentinel not in repr(item) for item in exc.args)
    for name in ("line", "column", "code"):
        assert sentinel not in repr(getattr(exc, name, None))


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


def test_validation_error_never_echoes_payload() -> None:
    sentinel = "SENTINEL_5150_DO_NOT_LEAK"
    text = f"workers[1]{{pid,provider,metadata{{alias,region}}}}:\n  {sentinel},x,y,z".encode()

    with pytest.raises(toon.ValidationError) as info:
        toon.decode(text, type=Document)
    _assert_no_leak(info.value, sentinel)
    assert info.value.line == 2


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
