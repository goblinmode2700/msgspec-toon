"""Hostile inputs fault; they never panic, abort, or kill the interpreter.

Three v0.2.0 defects motivated this file (`docs/adversarial-review-v0.2.0.md`
F-01/F-02/F-03): a declared array count sized a `Vec` reservation, and neither
header field-group parsing nor encoder shape discovery was bounded by the
codec's nesting limit. Small inputs produced `PanicException` and exit 139.

A panic that unwinds into Python and a stack overflow that raises SIGSEGV are
not observable as exceptions in-process, so every probe runs in a subprocess
and asserts on the exit status as well as the message.
"""

from __future__ import annotations

import subprocess
import sys

import msgspec
import msgspec_toon as toon
import pytest

# Above the codec's shared nesting ceiling (`src/limits.rs`), which the wire
# format never approaches; the pre-fix crash needed ~100,000 levels.
BEYOND_DEPTH_LIMIT = 100_000

# The largest count a header can declare. It is a claim about rows, not a
# measurement of them, so it must never reach an allocator.
UNSATISFIABLE_COUNT = 2**64 - 1


def _run_probe(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", source],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _assert_contained(result: subprocess.CompletedProcess[str]) -> None:
    """The probe caught a codec error and the process exited normally.

    A negative return code is a signal: -11 is the SIGSEGV (shell exit 139)
    that the unbounded recursions produced. Exit 1 with `PanicException` is
    the unwound Rust panic that the unbounded reservation produced.
    """
    assert result.returncode == 0, (
        f"probe did not survive: exit {result.returncode}, {result.stderr[-400:]}"
    )
    assert "PanicException" not in result.stderr
    assert result.stdout.strip() == "CONTAINED", result.stdout


@pytest.mark.parametrize("strict", [True, False])
def test_declared_count_does_not_size_an_allocation(strict: bool) -> None:
    """F-01: `[18446744073709551615]:` panicked with a capacity overflow.

    Either outcome of the count contract is contained — strict rejects the
    mismatch, non-strict keeps the rows it actually found. Only the panic was
    a defect.
    """
    result = _run_probe(
        f"""
import msgspec_toon as toon
try:
    toon.decode(b"[{UNSATISFIABLE_COUNT}]:\\n  - 1\\n", strict={strict})
except toon.DecodeError:
    pass
print("CONTAINED")
"""
    )
    _assert_contained(result)


def test_declared_count_still_governs_validation() -> None:
    """Capping the reservation must not weaken the count contract."""
    document = f"[{UNSATISFIABLE_COUNT}]:\n  - 1\n".encode()
    assert toon.decode(document, strict=False) == [1]
    with pytest.raises(toon.DecodeError):
        toon.decode(document)


def test_oversized_arrays_still_decode() -> None:
    """The reservation cap is a hint, not a limit on real array length."""
    rows = 200_000
    document = b"[%d]:\n" % rows + b"".join(b"  - %d\n" % index for index in range(rows))
    decoded = toon.decode(document)
    assert len(decoded) == rows
    assert decoded[-1] == rows - 1


@pytest.mark.parametrize("strict", [True, False])
def test_nested_field_groups_are_depth_limited(strict: bool) -> None:
    """F-02: deep `{a{a{...}}}` headers exhausted the stack (exit 139)."""
    result = _run_probe(
        f"""
import msgspec_toon as toon
levels = {BEYOND_DEPTH_LIMIT}
document = b"rows[0]{{" + b"a{{" * (levels - 1) + b"x" + b"}}" * levels + b":\\n"
try:
    toon.decode(document, strict={strict})
except toon.DecodeError as error:
    assert error.code == "depth_limit", error.code
    print("CONTAINED")
else:
    print("DECODED")
"""
    )
    _assert_contained(result)


def test_encode_shape_discovery_is_depth_limited() -> None:
    """F-03: shape discovery recursed past the writer's depth check."""
    result = _run_probe(
        f"""
import msgspec, msgspec_toon as toon
value = {{"x": 1}}
for _ in range({BEYOND_DEPTH_LIMIT}):
    value = {{"a": value}}
try:
    toon.encode([value, value])
except msgspec.EncodeError:
    print("CONTAINED")
else:
    print("ENCODED")
"""
    )
    _assert_contained(result)


def test_depth_limited_documents_report_a_static_fault() -> None:
    """In-process shape of the fault, at a depth the stack survives."""
    levels = 400
    document = b"rows[0]{" + b"a{" * (levels - 1) + b"x" + b"}" * levels + b":\n"
    with pytest.raises(toon.DecodeError) as info:
        toon.decode(document)
    assert info.value.code == "depth_limit"
    assert str(info.value) == "nesting depth limit exceeded at line 1, column 1"

    value: object = {"x": 1}
    for _ in range(levels):
        value = {"a": value}
    with pytest.raises(msgspec.EncodeError, match="nesting depth limit exceeded"):
        toon.encode([value, value])


def test_documents_at_the_depth_limit_still_decode() -> None:
    """The ceiling admits everything below it, in both directions."""
    levels = 256
    header = b"rows[1]{" + b"a{" * (levels - 1) + b"x" + b"}" * levels + b":\n"
    decoded = toon.decode(header + b"  1\n")
    innermost = decoded["rows"][0]
    for _ in range(levels - 1):
        innermost = innermost["a"]
    assert innermost == {"x": 1}
