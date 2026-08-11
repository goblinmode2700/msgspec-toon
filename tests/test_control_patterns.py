"""Cross wire form, nesting, and tagged-plan state."""

from __future__ import annotations

import msgspec
import msgspec_toon as toon
import pytest


class Pet(msgspec.Struct, tag="pet"):
    x: int


class Cat(msgspec.Struct, tag="cat"):
    x: int


class Dog(msgspec.Struct, tag="dog"):
    x: int


class ConcreteRow(msgspec.Struct):
    row_id: int
    pet: Pet


class UnionRow(msgspec.Struct):
    row_id: int
    pet: Cat | Dog


class PairRow(msgspec.Struct):
    left: Cat | Dog
    right: Cat | Dog


class Box(msgspec.Struct):
    pet: Cat | Dog


class DeepRow(msgspec.Struct):
    box: Box


@pytest.mark.parametrize(
    ("toon_document", "json_document", "accepted"),
    [
        (
            b"[1]{row_id,pet{type,x}}:\n  1,pet,2",
            b'[{"row_id":1,"pet":{"type":"pet","x":2}}]',
            True,
        ),
        (
            b"[1]{row_id,pet{x}}:\n  1,2",
            b'[{"row_id":1,"pet":{"x":2}}]',
            True,
        ),
        (
            b"[1]{row_id,pet{type,x}}:\n  1,dog,2",
            b'[{"row_id":1,"pet":{"type":"dog","x":2}}]',
            False,
        ),
    ],
)
def test_nested_concrete_tag_matches_msgspec_json(
    toon_document: bytes, json_document: bytes, accepted: bool
) -> None:
    if accepted:
        assert toon.decode(toon_document, type=list[ConcreteRow]) == msgspec.json.decode(
            json_document, type=list[ConcreteRow]
        )
        return

    with pytest.raises(msgspec.DecodeError):
        toon.decode(toon_document, type=list[ConcreteRow])
    with pytest.raises(msgspec.DecodeError):
        msgspec.json.decode(json_document, type=list[ConcreteRow])


@pytest.mark.parametrize(
    ("toon_document", "json_document", "expected"),
    [
        (
            b"[1]{row_id,pet{type,x}}:\n  1,cat,2",
            b'[{"row_id":1,"pet":{"type":"cat","x":2}}]',
            [UnionRow(1, Cat(2))],
        ),
        (
            b"[1]{row_id,pet{x,type}}:\n  1,2,dog",
            b'[{"row_id":1,"pet":{"x":2,"type":"dog"}}]',
            [UnionRow(1, Dog(2))],
        ),
    ],
)
def test_nested_union_selects_member_in_header_order(
    toon_document: bytes, json_document: bytes, expected: list[UnionRow]
) -> None:
    assert msgspec.json.decode(json_document, type=list[UnionRow]) == expected
    assert toon.decode(toon_document, type=list[UnionRow]) == expected


@pytest.mark.parametrize(
    ("toon_document", "json_document"),
    [
        (
            b"[1]{row_id,pet{x}}:\n  1,2",
            b'[{"row_id":1,"pet":{"x":2}}]',
        ),
        (
            b"[1]{row_id,pet{type,x}}:\n  1,bird,2",
            b'[{"row_id":1,"pet":{"type":"bird","x":2}}]',
        ),
        (
            b"[1]{row_id,pet{type,x}}:\n  1,1,2",
            b'[{"row_id":1,"pet":{"type":1,"x":2}}]',
        ),
    ],
)
def test_nested_union_rejects_invalid_discriminator(
    toon_document: bytes, json_document: bytes
) -> None:
    with pytest.raises(msgspec.DecodeError):
        toon.decode(toon_document, type=list[UnionRow])
    with pytest.raises(msgspec.DecodeError):
        msgspec.json.decode(json_document, type=list[UnionRow])


def test_nested_union_selection_is_local_to_siblings_and_rows() -> None:
    document = b"[2]{left{type,x},right{type,x}}:\n  cat,1,dog,2\n  dog,3,cat,4"
    expected = [PairRow(Cat(1), Dog(2)), PairRow(Dog(3), Cat(4))]
    assert toon.decode(document, type=list[PairRow]) == expected


def test_deep_nested_union_selects_only_its_own_plan() -> None:
    document = b"[1]{box{pet{type,x}}}:\n  cat,2"
    assert toon.decode(document, type=list[DeepRow]) == [DeepRow(Box(Cat(2)))]


def test_keyed_tabular_nested_union_selects_member() -> None:
    document = b"[1:]{row_id,pet{type,x}}:\n  first: 1,dog,2"
    assert toon.decode(document, type=dict[str, UnionRow]) == {"first": UnionRow(1, Dog(2))}


def test_nested_tagged_union_round_trip() -> None:
    value = [UnionRow(1, Cat(2)), UnionRow(2, Dog(3))]
    assert toon.decode(toon.encode(value), type=list[UnionRow]) == value


def test_duplicate_nested_tag_header_is_payload_safe() -> None:
    sentinel = b"SENTINEL_CONTROL_PATTERN"
    document = b"[1]{row_id,pet{type,type,x}}:\n  1,cat,dog," + sentinel
    with pytest.raises(msgspec.DecodeError) as caught:
        toon.decode(document, type=list[UnionRow])
    assert sentinel.decode() not in str(caught.value)
