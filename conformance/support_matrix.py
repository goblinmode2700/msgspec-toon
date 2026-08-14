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
# The wire format deliberately differs from msgspec.json, and the difference
# is required by the pinned TOON corpus rather than being an implementation gap.
FORMAT_DIVERGENCE = "format_divergence"


@dataclass(frozen=True)
class SupportEntry:
    feature: str
    tier: int
    status: str
    ours: Callable[[], Any]
    reference: Callable[[], Any]
    detail: str
    plan_rejection: bool = False
    round_trip: Callable[[], bool] | None = None


def _round_trip(value: Any, type_: Any) -> bool:
    return toon.decode(toon.encode(value), type=type_) == value


def _projection_round_trip(value: Any) -> bool:
    """Whether an encode-only type survives as msgspec's documented builtin form."""
    return toon.decode(toon.encode(value)) == msgspec.to_builtins(value)


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


class Priority(enum.IntEnum):
    HIGH = 2


class BytesSubclass(bytes):
    pass


@dataclass
class PlainDataclass:
    x: int


class Recursive(msgspec.Struct):
    value: int
    child: Recursive | None = None


# Supported-feature interactions are executable rows, not prose. These ten
# pairs came from the post-0.2.0b3 outside-agent cross-product review.
class TaggedArrayCat(msgspec.Struct, tag="cat", array_like=True):
    name: str


class TaggedArrayDog(msgspec.Struct, tag="dog", array_like=True):
    name: str


class TaggedRecursive(msgspec.Struct, tag="tagged_recursive"):
    value: int
    child: TaggedRecursive | None = None


class TaggedNativeScalar(msgspec.Struct, tag="tagged_native"):
    value: datetime.datetime


class TaggedKeywordOnly(msgspec.Struct, tag="tagged_kw", kw_only=True):
    value: int


class TaggedConstrained(msgspec.Struct, tag="tagged_constraint"):
    value: Annotated[int, msgspec.Meta(ge=10)]


class ArrayRecursive(msgspec.Struct, array_like=True):
    value: int
    child: ArrayRecursive | None = None


class ArrayNativeScalar(msgspec.Struct, array_like=True):
    value: datetime.datetime


class ArrayRenamed(msgspec.Struct, array_like=True, rename="camel"):
    user_name: str


class ArrayOptional(msgspec.Struct, array_like=True):
    value: int | None = None


class ArrayKeywordOnly(msgspec.Struct, array_like=True, kw_only=True):
    value: int


MATRIX: tuple[SupportEntry, ...] = (
    # --- Tier 0 -------------------------------------------------------------
    SupportEntry(
        "integer, string, boolean, and null scalars",
        0,
        SUPPORTED,
        lambda: toon.decode(b"a: 1\nc: x\nd: true\ne: null"),
        lambda: msgspec.json.decode(b'{"a":1,"c":"x","d":true,"e":null}'),
        "including integers beyond 2**53, which round-trip exactly",
        round_trip=lambda: _round_trip(
            {"integer": 2**80, "string": "x", "boolean": True, "null": None}, dict[str, Any]
        ),
    ),
    SupportEntry(
        "fractional and exponent floats",
        0,
        SUPPORTED,
        lambda: toon.decode(b"a: 1.5\nb: 1e+100"),
        lambda: msgspec.json.decode(b'{"a":1.5,"b":1e100}'),
        "untyped decode returns float and finite values round-trip exactly",
        round_trip=lambda: _round_trip([0.1, 1.5, 1e100, 5e-324], list[float]),
    ),
    SupportEntry(
        "whole floats and negative zero",
        0,
        FORMAT_DIVERGENCE,
        lambda: (toon.encode([0.0, -0.0, 1.0, float(2**53 + 1)]), type(toon.decode(b"1"))),
        lambda: (msgspec.json.encode([0.0, -0.0, 1.0, float(2**53 + 1)]), float),
        "TOON 4.1 canonicalizes whole floats to integer-looking scalars and -0.0 to 0; "
        "untyped decode therefore returns int, while typed float decode recovers float except "
        "for the sign of negative zero",
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
        round_trip=lambda: _round_trip([Worker(1, Metadata("a", "b"), "c")], list[Worker]),
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
        round_trip=lambda: _round_trip(Worker(1, Metadata("a", "b")), Worker),
    ),
    SupportEntry(
        "field renaming",
        0,
        SUPPORTED,
        lambda: toon.decode(b"userName: x", type=Renamed),
        lambda: msgspec.json.decode(b'{"userName":"x"}', type=Renamed),
        "rename policies are read through the plan compiler",
        round_trip=lambda: _round_trip(Renamed("x"), Renamed),
    ),
    # --- Tier 1: working ----------------------------------------------------
    SupportEntry(
        "dict[str, T]",
        1,
        SUPPORTED,
        lambda: toon.decode(b"a: 1\nb: 2", type=dict[str, int]),
        lambda: msgspec.json.decode(b'{"a":1,"b":2}', type=dict[str, int]),
        "string-keyed mappings only; see the dict[int, T] entry",
        round_trip=lambda: _round_trip({"a": 1, "b": 2}, dict[str, int]),
    ),
    SupportEntry(
        "object and containers of object",
        1,
        SUPPORTED,
        lambda: toon.decode(b"a:\n  b: 1", type=dict[str, object]),
        lambda: msgspec.json.decode(b'{"a":{"b":1}}', type=dict[str, object]),
        "object uses the same requested open-value path as Any; its containers are final output",
        round_trip=lambda: _round_trip([{"a": 1}, "x"], list[object]),
    ),
    SupportEntry(
        "unions of bool, int, float, and str",
        1,
        SUPPORTED,
        lambda: toon.decode(b"[2]: 1,x", type=list[int | str]),
        lambda: msgspec.json.decode(b'[1,"x"]', type=list[int | str]),
        "exact token categories win before widening, so float | int decodes 1 as int",
        round_trip=lambda: _round_trip([1, "x"], list[int | str]),
    ),
    SupportEntry(
        "variable-length tuple",
        1,
        SUPPORTED,
        lambda: toon.decode(b"[2]: 1,2", type=tuple[int, ...]),
        lambda: msgspec.json.decode(b"[1,2]", type=tuple[int, ...]),
        "",
        round_trip=lambda: _round_trip((1, 2), tuple[int, ...]),
    ),
    SupportEntry(
        "set encode projection",
        1,
        SUPPORTED,
        lambda: toon.decode(toon.encode({1, 2})),
        lambda: msgspec.json.decode(msgspec.json.encode({1, 2})),
        "native encode emits an array in interpreter iteration order; the wire does not "
        "retain set identity, so untyped decode returns list",
        round_trip=lambda: _projection_round_trip({1, 2}),
    ),
    SupportEntry(
        "frozenset encode projection",
        1,
        SUPPORTED,
        lambda: toon.decode(toon.encode(frozenset({1, 2}))),
        lambda: msgspec.json.decode(msgspec.json.encode(frozenset({1, 2}))),
        "native encode emits an array in interpreter iteration order; the wire does not "
        "retain frozenset identity, so untyped decode returns list",
        round_trip=lambda: _projection_round_trip(frozenset({1, 2})),
    ),
    SupportEntry(
        "Literal[str]",
        1,
        SUPPORTED,
        lambda: toon.decode(b"a", type=Literal["a", "b"]),
        lambda: msgspec.json.decode(b'"a"', type=Literal["a", "b"]),
        "",
        round_trip=lambda: _round_trip("a", Literal["a", "b"]),
    ),
    SupportEntry(
        "forbid_unknown_fields",
        1,
        SUPPORTED,
        lambda: toon.decode(b"a: 1", type=Strict),
        lambda: msgspec.json.decode(b'{"a":1}', type=Strict),
        "the accepted document round-trips; both reject an unknown field (tests/test_api.py)",
        round_trip=lambda: _round_trip(Strict(1), Strict),
    ),
    # --- Tier 1: gaps -------------------------------------------------------
    SupportEntry(
        "fixed-length tuple",
        1,
        SUPPORTED,
        lambda: toon.decode(b"[2]: 1,x", type=tuple[int, str]),
        lambda: msgspec.json.decode(b'[1,"x"]', type=tuple[int, str]),
        "one plan per position; a length mismatch is a type error",
        round_trip=lambda: _round_trip((1, "x"), tuple[int, str]),
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
        "the plan carries a keyword-name tuple and the class is "
        "constructed through the keyword half of the vectorcall",
        round_trip=lambda: _round_trip(KeywordOnly(x=1), KeywordOnly),
    ),
    SupportEntry(
        "tagged unions",
        1,
        SUPPORTED,
        lambda: toon.decode(b"name: x\ntype: cat", type=Cat | Dog),
        lambda: msgspec.json.decode(b'{"type":"cat","name":"x"}', type=Cat | Dog),
        "object-form only; bounded scalar preflight selects the compiled Struct plan before "
        "construction; tagged array-like unions fail at plan construction",
        round_trip=lambda: _round_trip(Cat("x"), Cat | Dog),
    ),
    SupportEntry(
        "array_like Structs",
        1,
        SUPPORTED,
        lambda: toon.decode(b"[2]:\n  - 1\n  - x", type=Positional),
        lambda: msgspec.json.decode(b'[1,"x"]', type=Positional),
        "positional frames construct the Struct without an intermediate mapping",
        round_trip=lambda: _round_trip(Positional(1, "x"), Positional),
    ),
    # --- Supported feature interactions -----------------------------------
    SupportEntry(
        "interaction: tagged + array_like",
        1,
        SUPPORTED,
        lambda: toon.decode(b"[2]: dog,rex", type=TaggedArrayCat | TaggedArrayDog),
        lambda: msgspec.json.decode(b'["dog","rex"]', type=TaggedArrayCat | TaggedArrayDog),
        "the positional discriminator selects the Struct plan before declared fields",
        round_trip=lambda: _round_trip(TaggedArrayDog("rex"), TaggedArrayCat | TaggedArrayDog),
    ),
    SupportEntry(
        "interaction: tagged + recursive",
        1,
        SUPPORTED,
        lambda: toon.decode(b"type: tagged_recursive\nvalue: 1\nchild: null", type=TaggedRecursive),
        lambda: msgspec.json.decode(
            b'{"type":"tagged_recursive","value":1,"child":null}', type=TaggedRecursive
        ),
        "tag validation and recursive plan references compose",
        round_trip=lambda: _round_trip(TaggedRecursive(1), TaggedRecursive),
    ),
    SupportEntry(
        "interaction: tagged + native scalar",
        2,
        SUPPORTED,
        lambda: toon.decode(
            b'type: tagged_native\nvalue: "2026-01-01T00:00:00Z"', type=TaggedNativeScalar
        ),
        lambda: msgspec.json.decode(
            b'{"type":"tagged_native","value":"2026-01-01T00:00:00Z"}',
            type=TaggedNativeScalar,
        ),
        "tag selection retains native scalar conversion",
        round_trip=lambda: _round_trip(
            TaggedNativeScalar(datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)),
            TaggedNativeScalar,
        ),
    ),
    SupportEntry(
        "interaction: tagged + kw_only",
        1,
        SUPPORTED,
        lambda: toon.decode(b"type: tagged_kw\nvalue: 1", type=TaggedKeywordOnly),
        lambda: msgspec.json.decode(b'{"type":"tagged_kw","value":1}', type=TaggedKeywordOnly),
        "tag validation retains keyword-only constructor placement",
        round_trip=lambda: _round_trip(TaggedKeywordOnly(value=1), TaggedKeywordOnly),
    ),
    SupportEntry(
        "interaction: tagged + constraint",
        1,
        SUPPORTED,
        lambda: toon.decode(b"type: tagged_constraint\nvalue: 10", type=TaggedConstrained),
        lambda: msgspec.json.decode(
            b'{"type":"tagged_constraint","value":10}', type=TaggedConstrained
        ),
        "tag validation retains declared scalar constraints",
        round_trip=lambda: _round_trip(TaggedConstrained(10), TaggedConstrained),
    ),
    SupportEntry(
        "interaction: array_like + recursive",
        1,
        SUPPORTED,
        lambda: toon.decode(b"[2]: 1,null", type=ArrayRecursive),
        lambda: msgspec.json.decode(b"[1,null]", type=ArrayRecursive),
        "positional frames retain bounded recursive references",
        round_trip=lambda: _round_trip(ArrayRecursive(1), ArrayRecursive),
    ),
    SupportEntry(
        "interaction: array_like + native scalar",
        2,
        SUPPORTED,
        lambda: toon.decode(b'[1]: "2026-01-01T00:00:00Z"', type=ArrayNativeScalar),
        lambda: msgspec.json.decode(b'["2026-01-01T00:00:00Z"]', type=ArrayNativeScalar),
        "positional field conversion retains native scalar targets",
        round_trip=lambda: _round_trip(
            ArrayNativeScalar(datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)),
            ArrayNativeScalar,
        ),
    ),
    SupportEntry(
        "interaction: array_like + rename",
        1,
        SUPPORTED,
        lambda: toon.decode(b"[1]: x", type=ArrayRenamed),
        lambda: msgspec.json.decode(b'["x"]', type=ArrayRenamed),
        "rename metadata does not alter positional field order",
        round_trip=lambda: _round_trip(ArrayRenamed("x"), ArrayRenamed),
    ),
    SupportEntry(
        "interaction: array_like + optional",
        1,
        SUPPORTED,
        lambda: toon.decode(b"[1]: null", type=ArrayOptional),
        lambda: msgspec.json.decode(b"[null]", type=ArrayOptional),
        "optional scalar plans retain positional placement",
        round_trip=lambda: _round_trip(ArrayOptional(None), ArrayOptional),
    ),
    SupportEntry(
        "interaction: array_like + kw_only",
        1,
        SUPPORTED,
        lambda: toon.decode(b"[1]: 1", type=ArrayKeywordOnly),
        lambda: msgspec.json.decode(b"[1]", type=ArrayKeywordOnly),
        "positional wire order composes with keyword-only constructor calls",
        round_trip=lambda: _round_trip(ArrayKeywordOnly(value=1), ArrayKeywordOnly),
    ),
    SupportEntry(
        "strict=False scalar coercion",
        1,
        SUPPORTED,
        lambda: toon.decode(b'"1"', type=int, strict=False),
        lambda: msgspec.json.decode(b'"1"', type=int, strict=False),
        "table-driven bool, int, and float conversion matches pinned msgspec 0.21.1",
        round_trip=lambda: _round_trip(1, int),
    ),
    SupportEntry(
        "recursive Struct types",
        1,
        SUPPORTED,
        lambda: toon.decode(b"value: 1\nchild: null", type=Recursive),
        lambda: msgspec.json.decode(b'{"value":1,"child":null}', type=Recursive),
        "identity-keyed graph plans support bounded direct recursive construction",
        round_trip=lambda: _round_trip(Recursive(1), Recursive),
    ),
    SupportEntry(
        "constraints (msgspec.Meta)",
        1,
        SUPPORTED,
        lambda: toon.decode(b"x: 10", type=Constrained),
        lambda: msgspec.json.decode(b'{"x":10}', type=Constrained),
        "numeric bounds and multiples, string length and patterns, and collection length "
        "constraints are enforced; accepted and rejected boundaries are differential-tested",
        round_trip=lambda: _round_trip(Constrained(10), Constrained),
    ),
    SupportEntry(
        "Literal[int]",
        1,
        SUPPORTED,
        lambda: toon.decode(b"2", type=Literal[1, 2]),
        lambda: msgspec.json.decode(b"2", type=Literal[1, 2]),
        "",
        round_trip=lambda: _round_trip(2, Literal[1, 2]),
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
        plan_rejection=True,
    ),
    SupportEntry(
        "Literal[int] rejects a boolean",
        1,
        PARITY_REJECTS,
        lambda: toon.decode(b"true", type=Literal[1]),
        lambda: msgspec.json.decode(b"true", type=Literal[1]),
        "Python equality makes True == 1, so membership now compares "
        "the exact scalar category first",
    ),
    SupportEntry(
        "dict[int, T] and other non-string keys",
        1,
        UNSUPPORTED,
        lambda: toon.decode(b"1: 2", type=dict[int, int]),
        lambda: msgspec.json.decode(b'{"1":2}', type=dict[int, int]),
        "the key plan was compiled and "
        "dropped, so keys stayed strings. Now the Decoder refuses the annotation at "
        "construction instead of returning {'1': 2} where msgspec returns {1: 2}",
        plan_rejection=True,
    ),
    # --- Tier 2 -------------------------------------------------------------
    SupportEntry(
        "string Enum",
        2,
        SUPPORTED,
        lambda: toon.decode(b"red", type=Color),
        lambda: msgspec.json.decode(b'"red"', type=Color),
        "typed decode uses msgspec's public scalar converter without building a container tree",
        round_trip=lambda: _round_trip(Color.RED, Color),
    ),
    SupportEntry(
        "integer Enum",
        2,
        SUPPORTED,
        lambda: toon.decode(b"2", type=Priority),
        lambda: msgspec.json.decode(b"2", type=Priority),
        "typed decode uses the declared integer member value",
        round_trip=lambda: _round_trip(Priority.HIGH, Priority),
    ),
    SupportEntry(
        "datetime",
        2,
        SUPPORTED,
        lambda: toon.decode(b'"2026-01-01T00:00:00Z"', type=datetime.datetime),
        lambda: msgspec.json.decode(b'"2026-01-01T00:00:00Z"', type=datetime.datetime),
        "aware values and msgspec.Meta(tz=...) constraints retain msgspec semantics",
        round_trip=lambda: _round_trip(
            datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC), datetime.datetime
        ),
    ),
    SupportEntry(
        "date",
        2,
        SUPPORTED,
        lambda: toon.decode(b'"2026-08-09"', type=datetime.date),
        lambda: msgspec.json.decode(b'"2026-08-09"', type=datetime.date),
        "native date scalar encode and typed decode",
        round_trip=lambda: _round_trip(datetime.date(2026, 8, 9), datetime.date),
    ),
    SupportEntry(
        "time",
        2,
        SUPPORTED,
        lambda: toon.decode(b'"01:02:03.000456"', type=datetime.time),
        lambda: msgspec.json.decode(b'"01:02:03.000456"', type=datetime.time),
        "msgspec.Meta(tz=...) constraints retain msgspec semantics",
        round_trip=lambda: _round_trip(datetime.time(1, 2, 3, 456), datetime.time),
    ),
    SupportEntry(
        "timedelta",
        2,
        SUPPORTED,
        lambda: toon.decode(b'"P2DT3.000004S"', type=datetime.timedelta),
        lambda: msgspec.json.decode(b'"P2DT3.000004S"', type=datetime.timedelta),
        "native duration scalar encode and typed decode",
        round_trip=lambda: _round_trip(
            datetime.timedelta(days=2, seconds=3, microseconds=4), datetime.timedelta
        ),
    ),
    SupportEntry(
        "UUID",
        2,
        SUPPORTED,
        lambda: toon.decode(b'"12345678-1234-5678-1234-567812345678"', type=uuid.UUID),
        lambda: msgspec.json.decode(b'"12345678-1234-5678-1234-567812345678"', type=uuid.UUID),
        "native UUID scalar encode and typed decode",
        round_trip=lambda: _round_trip(
            uuid.UUID("12345678-1234-5678-1234-567812345678"), uuid.UUID
        ),
    ),
    SupportEntry(
        "Decimal",
        2,
        SUPPORTED,
        lambda: toon.decode(b'"1.5"', type=decimal.Decimal),
        lambda: msgspec.json.decode(b'"1.5"', type=decimal.Decimal),
        "the default string form preserves exact digits and trailing zeroes",
        round_trip=lambda: _round_trip(decimal.Decimal("1.2300"), decimal.Decimal),
    ),
    SupportEntry(
        "bytes encode projection",
        2,
        SUPPORTED,
        lambda: toon.decode(toon.encode(b"ab")),
        lambda: msgspec.json.decode(msgspec.json.encode(b"ab")),
        "native encode uses msgspec-compatible padded base64; the wire retains a string, "
        "so untyped decode returns str",
        round_trip=lambda: _projection_round_trip(b"ab"),
    ),
    SupportEntry(
        "exact bytearray encode projection",
        2,
        SUPPORTED,
        lambda: toon.decode(toon.encode(bytearray(b"ab"))),
        lambda: msgspec.json.decode(msgspec.json.encode(bytearray(b"ab"))),
        "native encode copies the mutable buffer before applying msgspec-compatible padded base64; "
        "untyped decode returns str",
        round_trip=lambda: _projection_round_trip(bytearray(b"ab")),
    ),
    SupportEntry(
        "memoryview encode projection",
        2,
        SUPPORTED,
        lambda: toon.decode(toon.encode(memoryview(b"ab"))),
        lambda: msgspec.json.decode(msgspec.json.encode(memoryview(b"ab"))),
        "native encode copies a C-contiguous view before applying msgspec-compatible padded base64; "
        "untyped decode returns str",
        round_trip=lambda: _projection_round_trip(memoryview(b"ab")),
    ),
    SupportEntry(
        "bytes subclasses",
        2,
        PARITY_REJECTS,
        lambda: toon.encode(BytesSubclass(b"ab")),
        lambda: msgspec.json.encode(BytesSubclass(b"ab")),
        "both encoders refuse subclasses because the subtype can carry semantics not present in "
        "exact bytes",
    ),
    SupportEntry(
        "dataclasses",
        2,
        UNSUPPORTED,
        lambda: toon.decode(b"x: 1", type=PlainDataclass),
        lambda: msgspec.json.decode(b'{"x":1}', type=PlainDataclass),
        "requires declared plan support or an explicit dec_hook",
        plan_rejection=True,
    ),
    # --- public API surface -------------------------------------------------
    SupportEntry(
        "encode(order=...)",
        1,
        UNSUPPORTED,
        lambda: toon.encode({"b": 1, "a": 2}, order="sorted"),
        lambda: msgspec.json.encode({"b": 1, "a": 2}, order="sorted"),
        "an unimplemented value now raises "
        "NotImplementedError instead of returning insertion order. A value msgspec itself "
        "rejects still raises the same ValueError",
    ),
    SupportEntry(
        "Encoder(decimal_format=..., uuid_format=...)",
        2,
        SUPPORTED,
        lambda: (
            toon.Encoder(decimal_format="number").encode(decimal.Decimal("1.2300")),
            toon.Encoder(uuid_format="hex").encode(
                uuid.UUID("12345678-1234-5678-1234-567812345678")
            ),
        ),
        lambda: (
            msgspec.json.Encoder(decimal_format="number").encode(decimal.Decimal("1.2300")),
            msgspec.json.Encoder(uuid_format="hex").encode(
                uuid.UUID("12345678-1234-5678-1234-567812345678")
            ),
        ),
        "both reusable and functional encoders implement each documented format value",
        round_trip=lambda: (
            toon.decode(
                toon.Encoder(decimal_format="number").encode(decimal.Decimal("1.2300")),
                type=decimal.Decimal,
            )
            == decimal.Decimal("1.2300")
            and toon.decode(
                toon.Encoder(uuid_format="hex").encode(
                    uuid.UUID("12345678-1234-5678-1234-567812345678")
                ),
                type=uuid.UUID,
            )
            == uuid.UUID("12345678-1234-5678-1234-567812345678")
        ),
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
    assert entry.round_trip is not None, (
        f"{entry.feature}: supported value shape has no round-trip probe"
    )
    round_trip_error = _raised(entry.round_trip)
    assert round_trip_error is None, (
        f"{entry.feature}: round-trip probe raised {round_trip_error!r}"
    )
    assert entry.round_trip(), f"{entry.feature}: round-trip value changed"


def check_parity_rejects(entry: SupportEntry) -> None:
    ours_error = _raised(entry.ours)
    reference_error = _raised(entry.reference)
    assert ours_error is not None, f"{entry.feature}: declared a rejection but succeeded"
    assert reference_error is not None, (
        f"{entry.feature}: msgspec.json accepts this, so rejecting it is a gap, not parity"
    )


def check_unsupported(entry: SupportEntry) -> None:
    ours_error = _raised(entry.ours)
    assert ours_error is not None, (
        f"{entry.feature}: declared unsupported but succeeded — update the matrix"
    )
    if entry.plan_rejection:
        assert isinstance(ours_error, toon.TypePlanError), (
            f"{entry.feature}: typed plan rejection leaked {type(ours_error).__name__}"
        )
        assert ours_error.code and isinstance(ours_error.path, tuple)
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


def check_format_divergence(entry: SupportEntry) -> None:
    assert _raised(entry.ours) is None
    assert _raised(entry.reference) is None
    assert entry.ours() != entry.reference(), (
        f"{entry.feature}: declared a wire-format divergence but agrees with msgspec.json"
    )


CHECKERS: dict[str, Callable[[SupportEntry], None]] = {
    SUPPORTED: check_supported,
    PARITY_REJECTS: check_parity_rejects,
    UNSUPPORTED: check_unsupported,
    SILENTLY_IGNORED: check_silently_ignored,
    SILENTLY_WRONG: check_silently_wrong,
    FORMAT_DIVERGENCE: check_format_divergence,
}


def as_report() -> dict[str, Any]:
    """The report's view: counts, the full matrix, and the generated gap list."""
    entries = [
        {
            "feature": entry.feature,
            "tier": entry.tier,
            "status": entry.status,
            "detail": entry.detail,
            "round_trip": "verified" if entry.round_trip is not None else "not_applicable",
        }
        for entry in MATRIX
    ]
    matching = {SUPPORTED, PARITY_REJECTS, FORMAT_DIVERGENCE}
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
            "visible to a caller, a wrong value is not. `format_divergence` is a declared, "
            "fixture-locked difference required by TOON 4.1."
        ),
    }
