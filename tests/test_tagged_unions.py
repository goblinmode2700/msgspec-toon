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


class ArrayEmpty(msgspec.Struct, array_like=True, tag="empty"):
    pass


class ArrayOne(msgspec.Struct, array_like=True, tag=1, tag_field="kind"):
    value: int


class ArrayTwo(msgspec.Struct, array_like=True, tag=2, tag_field="kind"):
    value: int


class ObjectOne(msgspec.Struct, tag=1, tag_field="kind"):
    value: int


class ObjectTwo(msgspec.Struct, tag=2, tag_field="kind"):
    value: int


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


def test_tagged_struct_encode_includes_discriminator_and_round_trips() -> None:
    dog = Dog(True, "rex")
    document = toon.encode(dog)
    assert document == b"type: dog\ngood: true\nname: rex"
    assert toon.decode(document, type=Cat | Dog) == dog


def test_custom_tag_field_encode_round_trips() -> None:
    value = One(4)
    document = toon.encode(value)
    assert document == b"kind: 1\nvalue: 4"
    assert toon.decode(document, type=One | Two) == value


def test_tagged_struct_array_keeps_discriminator_in_tabular_shape() -> None:
    values = [Cat("mio"), Cat("sumi", 8)]
    document = toon.encode(values)
    assert document == b"[2]{type,name,lives}:\n  cat,mio,9\n  cat,sumi,8"
    assert toon.decode(document, type=list[Cat | Dog]) == values


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


@pytest.mark.parametrize(
    ("value", "type_", "document", "json_document"),
    [
        (ArrayEmpty(), ArrayEmpty, b"[1]: empty", b'["empty"]'),
        (ArrayDog("rex"), ArrayDog, b"[2]: dog,rex", b'["dog","rex"]'),
        (ArrayDog("rex"), ArrayCat | ArrayDog, b"[2]: dog,rex", b'["dog","rex"]'),
        (ArrayTwo(4), ArrayOne | ArrayTwo, b"[2]: 2,4", b"[2,4]"),
    ],
)
def test_tagged_array_like_round_trips_like_msgspec_json(
    value: msgspec.Struct, type_: object, document: bytes, json_document: bytes
) -> None:
    assert toon.encode(value) == document
    assert toon.decode(document, type=type_) == value
    assert msgspec.json.decode(json_document, type=type_) == value


def test_tagged_array_like_union_round_trips_when_nested_in_a_list() -> None:
    values = [ArrayCat("mio"), ArrayDog("rex")]
    assert toon.decode(toon.encode(values), type=list[ArrayCat | ArrayDog]) == values


def test_mixed_object_and_array_like_tagged_union_is_rejected() -> None:
    with pytest.raises(toon.TypePlanError) as caught:
        toon.Decoder(Cat | ArrayDog)
    # msgspec.inspect rejects the mixed-shape annotation before the membrane
    # can lower it to our narrower unsupported_union code.
    assert caught.value.code == "unsupported_annotation"
    assert caught.value.path == ()


@pytest.mark.parametrize(
    ("document", "type_"),
    [
        (b"[0]:", ArrayDog),
        (b"[1]: cat", ArrayDog),
        (b"[2]: SENTINEL,rex", ArrayCat | ArrayDog),
        (b"[3]: dog,rex,extra", ArrayDog),
    ],
)
def test_invalid_tagged_array_like_never_reports_internal_error(
    document: bytes, type_: object
) -> None:
    with pytest.raises(msgspec.DecodeError) as caught:
        toon.decode(document, type=type_)
    assert "internal error" not in str(caught.value)
    assert "SENTINEL" not in str(caught.value)


@pytest.mark.parametrize(
    ("document", "json_document", "type_"),
    [
        (b"[2]: true,4", b"[true,4]", ArrayOne | ArrayTwo),
        (b"[2]: 1.0,4", b"[1.0,4]", ArrayOne | ArrayTwo),
        (b"kind: true\nvalue: 4", b'{"kind":true,"value":4}', ObjectOne | ObjectTwo),
        (b"kind: 1.0\nvalue: 4", b'{"kind":1.0,"value":4}', ObjectOne | ObjectTwo),
    ],
)
def test_integer_tag_rejects_python_equal_scalar_categories(
    document: bytes, json_document: bytes, type_: object
) -> None:
    with pytest.raises(msgspec.DecodeError):
        toon.decode(document, type=type_)
    with pytest.raises(msgspec.DecodeError):
        msgspec.json.decode(json_document, type=type_)
