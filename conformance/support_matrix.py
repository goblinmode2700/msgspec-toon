"""The one maintained statement of what this codec supports.

`conformance/report.json` used to carry a freehand gap list, which is exactly
the kind of prose that lags the implementation: it claimed Tier 0 plus parts of
Tier 1 while fixed tuples, `kw_only` Structs, `strict=False` coercion and seven
other boundaries went unlisted.

So the list is generated from this module, and this module is a test oracle:
`tests/test_support_matrix.py` runs every entry and fails when reality stops
matching the declaration. A gap cannot be quietly fixed without updating the
report, and the report cannot claim support that no probe demonstrates.

Every entry names `msgspec.json`'s behavior on the equivalent document. That is
the bar the public API promises to substitute for, so a gap is only a gap if
msgspec accepts what we reject — and a *silent* divergence, where both succeed
and disagree, is worse than a rejection and is labelled as such.
"""

from __future__ import annotations

import datetime
import decimal
import enum
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, Literal

import msgspec
import msgspec_toon as toon

# --- statuses ---------------------------------------------------------------
# What the pair of probes is expected to show. The checker for each lives in
# CHECKERS; nothing branches on these strings.

SUPPORTED = "supported"
# Both implementations reject the document. That is parity, not a gap: the
# matrix has to be able to say "we are correct to refuse this".
PARITY_REJECTS = "parity_rejects"
UNSUPPORTED = "unsupported"
SILENTLY_IGNORED = "silently_ignored"
SILENTLY_WRONG = "silently_wrong"


@dataclass(frozen=True)
class SupportEntry:
    feature: str
    tier: int
    status: str
    ours: Callable[[], Any]
    reference: Callable[[], Any]
    detail: str


# --- probes -----------------------------------------------------------------


class Metadata(msgspec.Struct, frozen=True):
    alias: str
    region: str


class Worker(msgspec.Struct, frozen=True):
    pid: int
    metadata: Metadata
    provider: str = "claude"


class Renamed(msgspec.Struct, rename="camel"):
    user_name: str


class KeywordOnly(msgspec.Struct, kw_only=True):
    x: int


class Constrained(msgspec.Struct):
    x: Annotated[int, msgspec.Meta(ge=10)]


class Positional(msgspec.Struct, array_like=True):
    a: int
    b: str


class Cat(msgspec.Struct, tag="cat"):
    name: str


class Dog(msgspec.Struct, tag="dog"):
    name: str


class Strict(msgspec.Struct, forbid_unknown_fields=True):
    a: int


class Color(enum.Enum):
    RED = "red"


@dataclass
class PlainDataclass:
    x: int


class Recursive(msgspec.Struct):
    value: int
    child: Recursive | None = None


MATRIX: tuple[SupportEntry, ...] = (
    # --- Tier 0 -------------------------------------------------------------
    SupportEntry(
        "scalars (int, float, str, bool, null)",
        0,
        SUPPORTED,
        lambda: toon.decode(b"a: 1\nb: 1.5\nc: x\nd: true\ne: null"),
        lambda: msgspec.json.decode(b'{"a":1,"b":1.5,"c":"x","d":true,"e":null}'),
        "including integers beyond 2**53, which round-trip exactly",
    ),
    SupportEntry(
        "nested Structs in a tabular array",
        0,
        SUPPORTED,
        lambda: toon.decode(
            b"[1]{pid,metadata{alias,region},provider}:\n  1,a,b,c", type=list[Worker]
        ),
        lambda: msgspec.json.decode(
            b'[{"pid":1,"metadata":{"alias":"a","region":"b"},"provider":"c"}]', type=list[Worker]
        ),
        "the challenge shape: nested field groups keep a record on one row",
    ),
    SupportEntry(
        "Optional and defaults",
        0,
        SUPPORTED,
        lambda: toon.decode(b"pid: 1\nmetadata:\n  alias: a\n  region: b", type=Worker),
        lambda: msgspec.json.decode(
            b'{"pid":1,"metadata":{"alias":"a","region":"b"}}', type=Worker
        ),
        "an omitted field takes its declared default",
    ),
    SupportEntry(
        "field renaming",
        0,
        SUPPORTED,
        lambda: toon.decode(b"userName: x", type=Renamed),
        lambda: msgspec.json.decode(b'{"userName":"x"}', type=Renamed),
        "rename policies are read through the plan compiler",
    ),
    # --- Tier 1: working ----------------------------------------------------
    SupportEntry(
        "dict[str, T]",
        1,
        SUPPORTED,
        lambda: toon.decode(b"a: 1\nb: 2", type=dict[str, int]),
        lambda: msgspec.json.decode(b'{"a":1,"b":2}', type=dict[str, int]),
        "string-keyed mappings only; see the dict[int, T] entry",
    ),
    SupportEntry(
        "variable-length tuple",
        1,
        SUPPORTED,
        lambda: toon.decode(b"[2]: 1,2", type=tuple[int, ...]),
        lambda: msgspec.json.decode(b"[1,2]", type=tuple[int, ...]),
        "",
    ),
    SupportEntry(
        "Literal[str]",
        1,
        SUPPORTED,
        lambda: toon.decode(b"a", type=Literal["a", "b"]),
        lambda: msgspec.json.decode(b'"a"', type=Literal["a", "b"]),
        "",
    ),
    SupportEntry(
        "forbid_unknown_fields",
        1,
        SUPPORTED,
        lambda: toon.decode(b"a: 1", type=Strict),
        lambda: msgspec.json.decode(b'{"a":1}', type=Strict),
        "the accepted document round-trips; both reject an unknown field (tests/test_api.py)",
    ),
    # --- Tier 1: gaps -------------------------------------------------------
    SupportEntry(
        "fixed-length tuple",
        1,
        SUPPORTED,
        lambda: toon.decode(b"[2]: 1,x", type=tuple[int, str]),
        lambda: msgspec.json.decode(b'[1,"x"]', type=tuple[int, str]),
        "review F-08, fixed: one plan per position, and a length mismatch is a type error",
    ),
    SupportEntry(
        "fixed-length tuple rejects a wrong length",
        1,
        PARITY_REJECTS,
        lambda: toon.decode(b"[3]: 1,x,2", type=tuple[int, str]),
        lambda: msgspec.json.decode(b'[1,"x",2]', type=tuple[int, str]),
        "",
    ),
    SupportEntry(
        "kw_only Structs",
        1,
        SUPPORTED,
        lambda: toon.decode(b"x: 1", type=KeywordOnly),
        lambda: msgspec.json.decode(b'{"x":1}', type=KeywordOnly),
        "review F-09, fixed: the plan carries a keyword-name tuple and the class is "
        "constructed through the keyword half of the vectorcall",
    ),
    SupportEntry(
        "tagged unions",
        1,
        UNSUPPORTED,
        lambda: toon.decode(b"type: cat\nname: x", type=Cat | Dog),
        lambda: msgspec.json.decode(b'{"type":"cat","name":"x"}', type=Cat | Dog),
        "",
    ),
    SupportEntry(
        "array_like Structs",
        1,
        UNSUPPORTED,
        lambda: toon.decode(b"[2]: 1,x", type=Positional),
        lambda: msgspec.json.decode(b'[1,"x"]', type=Positional),
        "",
    ),
    SupportEntry(
        "strict=False scalar coercion",
        1,
        UNSUPPORTED,
        lambda: toon.decode(b'"1"', type=int, strict=False),
        lambda: msgspec.json.decode(b'"1"', type=int, strict=False),
        "review F-06: `strict` reaches duplicate handling but not `convert_scalar`",
    ),
    SupportEntry(
        "recursive Struct types",
        1,
        UNSUPPORTED,
        lambda: toon.Decoder(Recursive),
        lambda: msgspec.json.Decoder(Recursive),
        "the plan compiler recurses until RecursionError instead of erroring clearly",
    ),
    SupportEntry(
        "constraints (msgspec.Meta)",
        1,
        SILENTLY_IGNORED,
        lambda: toon.decode(b"x: 1", type=Constrained),
        lambda: msgspec.json.decode(b'{"x":1}', type=Constrained),
        "parsed by the plan compiler and never enforced: a value msgspec rejects is accepted",
    ),
    SupportEntry(
        "Literal[int]",
        1,
        SUPPORTED,
        lambda: toon.decode(b"2", type=Literal[1, 2]),
        lambda: msgspec.json.decode(b"2", type=Literal[1, 2]),
        "",
    ),
    SupportEntry(
        "Literal with mixed member types",
        1,
        UNSUPPORTED,
        lambda: toon.decode(b"1", type=Literal["a", 1]),
        lambda: msgspec.json.decode(b"1", type=Literal["a", 1]),
        "not our defect and not fixable behind the membrane: msgspec.inspect sorts a "
        "Literal's members and raises TypeError on mixed types, so the plan compiler "
        "never sees the annotation, while msgspec.json decodes it without inspect",
    ),
    SupportEntry(
        "Literal[int] rejects a boolean",
        1,
        PARITY_REJECTS,
        lambda: toon.decode(b"true", type=Literal[1]),
        lambda: msgspec.json.decode(b"true", type=Literal[1]),
        "review F-07, fixed: Python equality makes True == 1, so membership now compares "
        "the exact scalar category first",
    ),
    SupportEntry(
        "dict[int, T] and other non-string keys",
        1,
        UNSUPPORTED,
        lambda: toon.decode(b"1: 2", type=dict[int, int]),
        lambda: msgspec.json.decode(b'{"1":2}', type=dict[int, int]),
        "review F-13, downgraded from silently wrong: the key plan was compiled and "
        "dropped, so keys stayed strings. Now the Decoder refuses the annotation at "
        "construction instead of returning {'1': 2} where msgspec returns {1: 2}",
    ),
    # --- Tier 2: absent -----------------------------------------------------
    SupportEntry(
        "enum members",
        2,
        UNSUPPORTED,
        lambda: toon.decode(b"red", type=Color),
        lambda: msgspec.json.decode(b'"red"', type=Color),
        "",
    ),
    SupportEntry(
        "datetime",
        2,
        UNSUPPORTED,
        lambda: toon.decode(b'"2026-01-01T00:00:00Z"', type=datetime.datetime),
        lambda: msgspec.json.decode(b'"2026-01-01T00:00:00Z"', type=datetime.datetime),
        "",
    ),
    SupportEntry(
        "UUID",
        2,
        UNSUPPORTED,
        lambda: toon.decode(b'"12345678-1234-5678-1234-567812345678"', type=uuid.UUID),
        lambda: msgspec.json.decode(b'"12345678-1234-5678-1234-567812345678"', type=uuid.UUID),
        "",
    ),
    SupportEntry(
        "Decimal",
        2,
        UNSUPPORTED,
        lambda: toon.decode(b'"1.5"', type=decimal.Decimal),
        lambda: msgspec.json.decode(b'"1.5"', type=decimal.Decimal),
        "",
    ),
    SupportEntry(
        "dataclasses",
        2,
        UNSUPPORTED,
        lambda: toon.decode(b"x: 1", type=PlainDataclass),
        lambda: msgspec.json.decode(b'{"x":1}', type=PlainDataclass),
        "",
    ),
    # --- public API surface -------------------------------------------------
    SupportEntry(
        "encode(order=...)",
        1,
        SILENTLY_IGNORED,
        lambda: toon.encode({"b": 1, "a": 2}, order="sorted"),
        lambda: msgspec.json.encode({"b": 1, "a": 2}, order="sorted"),
        "review F-10: accepted and never passed to Rust; even `order='garbage'` is accepted, "
        "which msgspec rejects with ValueError",
    ),
    SupportEntry(
        "Encoder(decimal_format=..., uuid_format=...)",
        2,
        SILENTLY_IGNORED,
        lambda: toon.Encoder(decimal_format="number", uuid_format="hex").encode({"a": 1}),
        lambda: msgspec.json.Encoder(decimal_format="number", uuid_format="hex").encode({"a": 1}),
        "accepted by the Encoder constructor and dropped; the encode() function rejects the "
        "same names with TypeError, so the two entry points disagree",
    ),
)


# --- checkers ---------------------------------------------------------------


def _raised(probe: Callable[[], Any]) -> BaseException | None:
    """Any failure counts, including RecursionError from the plan compiler —
    the matrix records how a boundary behaves, not how tidily it fails."""
    try:
        probe()
    except BaseException as error:  # noqa: BLE001
        return error
    return None


def check_supported(entry: SupportEntry) -> None:
    ours_error = _raised(entry.ours)
    assert ours_error is None, f"{entry.feature}: declared supported but raised {ours_error!r}"
    reference_error = _raised(entry.reference)
    if reference_error is None:
        assert entry.ours() == entry.reference(), (
            f"{entry.feature}: declared supported but disagrees with msgspec.json"
        )


def check_parity_rejects(entry: SupportEntry) -> None:
    ours_error = _raised(entry.ours)
    reference_error = _raised(entry.reference)
    assert ours_error is not None, f"{entry.feature}: declared a rejection but succeeded"
    assert reference_error is not None, (
        f"{entry.feature}: msgspec.json accepts this, so rejecting it is a gap, not parity"
    )


def check_unsupported(entry: SupportEntry) -> None:
    assert _raised(entry.ours) is not None, (
        f"{entry.feature}: declared unsupported but succeeded — update the matrix"
    )
    assert _raised(entry.reference) is None, (
        f"{entry.feature}: msgspec.json also rejects this, so it is shared behavior, not a gap"
    )


def check_silently_ignored(entry: SupportEntry) -> None:
    assert _raised(entry.ours) is None, f"{entry.feature}: declared silently ignored but raised"
    reference_error = _raised(entry.reference)
    if reference_error is None:
        assert entry.ours() != entry.reference(), (
            f"{entry.feature}: declared inert but matches msgspec.json — it works, update the matrix"
        )


def check_silently_wrong(entry: SupportEntry) -> None:
    assert _raised(entry.ours) is None, f"{entry.feature}: declared silently wrong but raised"
    assert _raised(entry.reference) is None or entry.status == SILENTLY_WRONG
    reference_error = _raised(entry.reference)
    if reference_error is None:
        assert entry.ours() != entry.reference(), (
            f"{entry.feature}: declared divergent but agrees with msgspec.json"
        )


CHECKERS: dict[str, Callable[[SupportEntry], None]] = {
    SUPPORTED: check_supported,
    PARITY_REJECTS: check_parity_rejects,
    UNSUPPORTED: check_unsupported,
    SILENTLY_IGNORED: check_silently_ignored,
    SILENTLY_WRONG: check_silently_wrong,
}


def as_report() -> dict[str, Any]:
    """The report's view: counts, the full matrix, and the generated gap list."""
    entries = [
        {
            "feature": entry.feature,
            "tier": entry.tier,
            "status": entry.status,
            "detail": entry.detail,
        }
        for entry in MATRIX
    ]
    matching = {SUPPORTED, PARITY_REJECTS}
    gaps = [entry for entry in entries if entry["status"] not in matching]
    return {
        "source": "conformance/support_matrix.py, verified by tests/test_support_matrix.py",
        "reference_implementation": f"msgspec {msgspec.__version__} (msgspec.json)",
        "counts": {
            status: sum(1 for entry in entries if entry["status"] == status) for status in CHECKERS
        },
        "entries": entries,
        "known_gaps": gaps,
        "severity_note": (
            "`silently_wrong` and `silently_ignored` outrank `unsupported`: a rejection is "
            "visible to a caller, a wrong value is not."
        ),
    }
