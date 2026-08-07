"""The canvas §14 vertical slice: the go/no-go acceptance tests."""

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


TEXT = b"""workers[2]{pid,provider,metadata{alias,region}}:
  9007199254740993,claude,worker-a,west
  80916,claude,worker-b,east"""


class Ascending(msgspec.Struct, frozen=True):
    x: int
    y: int


class Descending(msgspec.Struct, frozen=True):
    """`Ascending`'s field names in the opposite declaration order."""

    y: int
    x: int


class TuplePair(msgspec.Struct, frozen=True):
    pair: tuple[Ascending, Descending]


class TupleTriple(msgspec.Struct, frozen=True):
    triple: tuple[Ascending, Ascending, Descending]


def test_vertical_slice() -> None:
    value = toon.decode(TEXT, type=Document)
    assert isinstance(value, Document)
    assert value.workers[0].pid == 9_007_199_254_740_993
    assert value.workers[0].metadata == Metadata(alias="worker-a", region="west")
    assert value.workers[1] == Worker(
        pid=80916, provider="claude", metadata=Metadata(alias="worker-b", region="east")
    )
    assert toon.encode(value) == TEXT


def test_reusable_decoder_and_encoder() -> None:
    decoder = toon.Decoder(Document)
    encoder = toon.Encoder()
    for _ in range(3):
        value = decoder.decode(TEXT)
        assert encoder.encode(value) == TEXT


class Renamed(msgspec.Struct, rename="camel"):
    worker_id: int
    display_name: str


class RenamedDoc(msgspec.Struct):
    rows: list[Renamed]


def test_renamed_fields_round_trip() -> None:
    text = b"rows[1]{workerId,displayName}:\n  7,seven"
    value = toon.decode(text, type=RenamedDoc)
    assert value.rows[0].worker_id == 7
    assert value.rows[0].display_name == "seven"
    assert toon.encode(value) == text


def test_defaults_and_optional() -> None:
    class Item(msgspec.Struct):
        name: str
        note: str | None = None
        count: int = 3

    value = toon.decode(b"name: a", type=Item)
    assert value == Item(name="a", note=None, count=3)

    value = toon.decode(b"name: a\nnote: null\ncount: 9", type=Item)
    assert value == Item(name="a", note=None, count=9)


def test_missing_required_field_raises() -> None:
    class Item(msgspec.Struct):
        name: str
        count: int

    try:
        toon.decode(b"name: a", type=Item)
    except toon.ValidationError as exc:
        assert exc.code == "missing_field"
    else:
        raise AssertionError("missing field was accepted")


def test_type_mismatch_raises_validation_error() -> None:
    class Item(msgspec.Struct):
        count: int

    try:
        toon.decode(b"count: hello", type=Item)
    except toon.ValidationError as exc:
        assert exc.code == "type_mismatch"
        assert exc.line == 1
    else:
        raise AssertionError("mismatched type was accepted")


def test_unknown_fields_are_skipped() -> None:
    class Item(msgspec.Struct):
        name: str

    value = toon.decode(b"name: a\nextra: 1\nnested:\n  deep: 2", type=Item)
    assert value == Item(name="a")


def test_str_input_decodes() -> None:
    value = toon.decode(TEXT.decode(), type=Document)
    assert value.workers[1].pid == 80916


class KeywordInner(msgspec.Struct, kw_only=True, frozen=True):
    value: int


class KeywordOuter(msgspec.Struct, kw_only=True, frozen=True):
    """Module scope on purpose: `from __future__ import annotations` turns
    `inner: KeywordInner` into a string, and msgspec cannot resolve a class
    defined inside a test function."""

    inner: KeywordInner
    count: int = 3


def test_fixed_tuples_decode_by_position() -> None:
    """A fixed tuple's length is part of its type, not of the document."""
    assert toon.decode(b"[2]: 1,x", type=tuple[int, str]) == (1, "x")
    assert msgspec.json.decode(b'[1,"x"]', type=tuple[int, str]) == (1, "x")

    for wrong in (b"[1]: 1", b"[3]: 1,x,2"):
        with pytest.raises(toon.ValidationError):
            toon.decode(wrong, type=tuple[int, str])

    # Position selects the plan, so a value valid at one index can be invalid
    # at another.
    with pytest.raises(toon.ValidationError):
        toon.decode(b"[2]: x,1", type=tuple[int, str])


def test_fixed_tuples_nest_and_round_trip() -> None:
    class Point(msgspec.Struct, frozen=True):
        at: tuple[int, int]
        label: tuple[str, int]

    value = Point(at=(1, 2), label=("a", 3))
    encoded = toon.encode(value)
    assert toon.decode(encoded, type=Point) == value

    nested = toon.decode(b"[2]:\n  - [2]: 1,a\n  - [2]: 2,b", type=list[tuple[int, str]])
    assert nested == [(1, "a"), (2, "b")]


def test_keyword_only_structs_construct() -> None:
    """kw_only reorders fields and forbids positional construction."""

    class Settings(msgspec.Struct, kw_only=True):
        required: int
        optional: str = "default"

    assert toon.decode(b"required: 1", type=Settings) == msgspec.json.decode(
        b'{"required":1}', type=Settings
    )
    assert toon.decode(b"required: 1\noptional: z", type=Settings) == Settings(
        required=1, optional="z"
    )
    # The construction path is per row, so tabular arrays exercise it repeatedly.
    assert toon.decode(b"[2]{required,optional}:\n  1,p\n  2,q", type=list[Settings]) == [
        Settings(required=1, optional="p"),
        Settings(required=2, optional="q"),
    ]
    with pytest.raises(toon.ValidationError):
        toon.decode(b"optional: z", type=Settings)


def test_keyword_only_structs_nest_and_round_trip() -> None:
    original = KeywordOuter(inner=KeywordInner(value=2))
    assert toon.decode(toon.encode(original), type=KeywordOuter) == original


def test_tuple_positions_do_not_share_a_row_memo() -> None:
    """Each position of a fixed tuple carries its own plan.

    The row memo replays the first row's wire-name to field-index
    resolutions positionally. Two Structs that share field names in opposite
    declaration order resolve the same name to different indices, so a memo
    shared across positions silently swaps the values of every later row —
    a wrong answer, not a refusal. `msgspec.json` is the oracle.
    """
    reference = msgspec.json.decode(b'{"pair":[{"x":1,"y":2},{"x":3,"y":4}]}', type=TuplePair)
    assert reference == TuplePair(pair=(Ascending(x=1, y=2), Descending(y=4, x=3)))

    # Tabular rows: one header, so every row emits an identical key sequence.
    assert toon.decode(b"pair[2]{x,y}:\n  1,2\n  3,4", type=TuplePair) == reference
    # List form reaches the same memo by a different route.
    assert (
        toon.decode(b"pair[2]:\n  - x: 1\n    y: 2\n  - x: 3\n    y: 4", type=TuplePair)
        == reference
    )

    # The divergence appears only at position 3, after two rows agreed.
    assert toon.decode(
        b"triple[3]{x,y}:\n  1,2\n  3,4\n  5,6", type=TupleTriple
    ) == msgspec.json.decode(
        b'{"triple":[{"x":1,"y":2},{"x":3,"y":4},{"x":5,"y":6}]}', type=TupleTriple
    )
