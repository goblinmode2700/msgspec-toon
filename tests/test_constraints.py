"""Constraint behavior is differential against msgspec.json.

Constraints are a correctness boundary, not a parsing feature: values accepted by
the TOON grammar must still be rejected when the target annotation rejects them.
"""

from __future__ import annotations

from typing import Annotated, Any

import msgspec
import msgspec_toon as toon
import pytest

IntClosed = Annotated[int, msgspec.Meta(ge=2, le=8)]
IntOpen = Annotated[int, msgspec.Meta(gt=2, lt=8)]
IntEven = Annotated[int, msgspec.Meta(multiple_of=2)]
FloatHalf = Annotated[float, msgspec.Meta(multiple_of=0.5)]
ShortText = Annotated[str, msgspec.Meta(min_length=2, max_length=4)]
EndsInA = Annotated[str, msgspec.Meta(pattern="a$")]
ShortList = Annotated[list[int], msgspec.Meta(min_length=1, max_length=2)]
ShortTuple = Annotated[tuple[int, ...], msgspec.Meta(min_length=1, max_length=2)]
ShortDict = Annotated[dict[str, int], msgspec.Meta(min_length=1, max_length=2)]


class ConstrainedRow(msgspec.Struct, frozen=True):
    count: IntClosed
    label: EndsInA


class ConstrainedDocument(msgspec.Struct, frozen=True):
    rows: list[ConstrainedRow]
    maybe: IntEven | None = None


@pytest.mark.parametrize(
    ("annotation", "toon_document", "json_document", "expected"),
    [
        (IntClosed, b"2", b"2", 2),
        (IntClosed, b"8", b"8", 8),
        (IntOpen, b"3", b"3", 3),
        (IntOpen, b"7", b"7", 7),
        (IntEven, b"9007199254740994", b"9007199254740994", 9_007_199_254_740_994),
        (FloatHalf, b"1.5", b"1.5", 1.5),
        (ShortText, '"😊😊"'.encode(), '"😊😊"'.encode(), "😊😊"),
        (EndsInA, b"omega", b'"omega"', "omega"),
        (ShortList, b"[2]: 1,2", b"[1,2]", [1, 2]),
        (ShortTuple, b"[2]: 1,2", b"[1,2]", (1, 2)),
        (ShortDict, b"a: 1\nb: 2", b'{"a":1,"b":2}', {"a": 1, "b": 2}),
    ],
)
def test_constraints_accept_like_msgspec_json(
    annotation: Any, toon_document: bytes, json_document: bytes, expected: Any
) -> None:
    assert msgspec.json.decode(json_document, type=annotation) == expected
    assert toon.decode(toon_document, type=annotation) == expected


@pytest.mark.parametrize(
    ("annotation", "toon_document", "json_document"),
    [
        (IntClosed, b"1", b"1"),
        (IntClosed, b"9", b"9"),
        (IntOpen, b"2", b"2"),
        (IntOpen, b"8", b"8"),
        (IntEven, b"5", b"5"),
        (FloatHalf, b"1.25", b"1.25"),
        (ShortText, b"x", b'"x"'),
        (ShortText, b"abcde", b'"abcde"'),
        (EndsInA, b"omega-x", b'"omega-x"'),
        (ShortList, b"[0]:", b"[]"),
        (ShortList, b"[3]: 1,2,3", b"[1,2,3]"),
        (ShortTuple, b"[0]:", b"[]"),
        (ShortTuple, b"[3]: 1,2,3", b"[1,2,3]"),
        (ShortDict, b"", b"{}"),
        (ShortDict, b"a: 1\nb: 2\nc: 3", b'{"a":1,"b":2,"c":3}'),
    ],
)
def test_constraints_reject_like_msgspec_json(
    annotation: Any, toon_document: bytes, json_document: bytes
) -> None:
    with pytest.raises(msgspec.ValidationError):
        msgspec.json.decode(json_document, type=annotation)
    with pytest.raises(toon.ValidationError) as info:
        toon.decode(toon_document, type=annotation)
    assert info.value.code == "constraint"


def test_constraints_apply_inside_tabular_structs_and_optional_unions() -> None:
    accepted = b"rows[2]{count,label}:\n  2,alpha\n  8,beta\nmaybe: 4"
    assert toon.decode(accepted, type=ConstrainedDocument) == ConstrainedDocument(
        rows=[ConstrainedRow(2, "alpha"), ConstrainedRow(8, "beta")], maybe=4
    )

    for rejected in (
        b"rows[1]{count,label}:\n  1,alpha",
        b"rows[1]{count,label}:\n  2,wrong\nmaybe: null",
        b"rows[1]{count,label}:\n  2,alpha\nmaybe: 3",
    ):
        with pytest.raises(toon.ValidationError) as info:
            toon.decode(rejected, type=ConstrainedDocument)
        assert info.value.code == "constraint"


def test_constraint_errors_never_echo_payload() -> None:
    sentinel = "SENTINEL_CONSTRAINT_5501_DO_NOT_LEAK"
    annotation = Annotated[str, msgspec.Meta(pattern="^allowed$")]
    with pytest.raises(toon.ValidationError) as info:
        toon.decode(sentinel.encode(), type=annotation)
    error = info.value
    assert error.code == "constraint"
    assert sentinel not in str(error)
    assert sentinel not in repr(error)
    assert all(sentinel not in repr(item) for item in error.args)


def test_pattern_uses_search_semantics() -> None:
    """msgspec patterns search; they do not implicitly match the whole string."""

    annotation = Annotated[str, msgspec.Meta(pattern="a+")]
    assert toon.decode(b"xxaayy", type=annotation) == "xxaayy"

    anchored = Annotated[str, msgspec.Meta(pattern="^a+$")]
    with pytest.raises(toon.ValidationError):
        toon.decode(b"xxaayy", type=anchored)
