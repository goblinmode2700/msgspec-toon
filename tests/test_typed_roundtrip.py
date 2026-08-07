"""The canvas §14 vertical slice: the go/no-go acceptance tests."""

from __future__ import annotations

import msgspec
import msgspec_toon as toon


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
