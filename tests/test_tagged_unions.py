"""Tagged Struct unions select a compiled plan before construction."""

from __future__ import annotations

import msgspec
import msgspec_toon as toon
import pytest


class Cat(msgspec.Struct, tag="cat"):
    name: str
    lives: int = 9


class Dog(msgspec.Struct, tag="dog"):
    good: bool
    name: str


class One(msgspec.Struct, tag=1, tag_field="kind"):
    value: int


class Two(msgspec.Struct, tag=2, tag_field="kind"):
    value: int


class Envelope(msgspec.Struct):
    pet: Cat | Dog


class ArrayCat(msgspec.Struct, array_like=True, tag="cat"):
    name: str


class ArrayDog(msgspec.Struct, array_like=True, tag="dog"):
    name: str


@pytest.mark.parametrize(
    ("document", "json_document", "type_"),
    [
        ("type: cat\nname: mio", b'{"type":"cat","name":"mio"}', Cat | Dog),
        ("name: rex\ngood: true\ntype: dog", b'{"name":"rex","good":true,"type":"dog"}', Cat | Dog),
        ("value: 4\nkind: 1", b'{"value":4,"kind":1}', One | Two),
    ],
)
def test_tag_order_and_supported_tag_scalars_match_msgspec_json(
    document: str, json_document: bytes, type_: object
) -> None:
    assert toon.decode(document, type=type_) == msgspec.json.decode(json_document, type=type_)


def test_nested_tagged_union_constructs_selected_variant() -> None:
    document = "pet:\n  name: rex\n  type: dog\n  good: true"
    assert toon.decode(document, type=Envelope) == Envelope(Dog(True, "rex"))


def test_concrete_tagged_struct_validates_a_present_tag() -> None:
    assert toon.decode("name: mio", type=Cat) == Cat("mio")
    with pytest.raises(msgspec.DecodeError):
        toon.decode("type: dog\nname: mio", type=Cat)


def test_tabular_rows_may_select_different_variants() -> None:
    document = "[2]{type,name,good}:\n  cat,mio,true\n  dog,rex,false"
    assert toon.decode(document, type=list[Cat | Dog]) == [Cat("mio"), Dog(False, "rex")]


@pytest.mark.parametrize(
    "document",
    [
        "name: no-tag",
        "type: bird\nname: unknown",
        "type: cat\ntype: dog\nname: SENTINEL",
    ],
)
def test_missing_unknown_and_duplicate_tags_are_static_errors(document: str) -> None:
    with pytest.raises(msgspec.DecodeError) as caught:
        toon.decode(document, type=Cat | Dog)
    assert "bird" not in str(caught.value)
    assert "SENTINEL" not in str(caught.value)


def test_tagged_array_like_union_is_rejected_at_plan_construction() -> None:
    with pytest.raises(toon.TypePlanError) as caught:
        toon.Decoder(ArrayCat | ArrayDog)
    assert caught.value.code == "unsupported_union"
    assert caught.value.path == ()
