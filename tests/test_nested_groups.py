"""Nested field groups encode as flat rows; mixed shapes fall back."""

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


def test_one_nested_field_does_not_collapse_the_table() -> None:
    workers = [
        Worker(pid=1, provider="claude", metadata=Metadata(alias="a", region="west")),
        Worker(pid=2, provider="claude", metadata=Metadata(alias="b", region="east")),
    ]
    encoded = toon.encode({"workers": workers})
    lines = encoded.decode().splitlines()
    assert lines[0] == "workers[2]{pid,provider,metadata{alias,region}}:"
    assert lines[1] == "  1,claude,a,west"
    assert lines[2] == "  2,claude,b,east"
    assert len(lines) == 3


def test_dicts_with_uniform_shape_are_tabular_too() -> None:
    rows = [
        {"id": 1, "meta": {"x": "a"}},
        {"id": 2, "meta": {"x": "b"}},
    ]
    encoded = toon.encode({"rows": rows})
    assert encoded.splitlines()[0] == b"rows[2]{id,meta{x}}:"
    assert toon.decode(encoded) == {"rows": rows}


def test_uniform_dict_key_order_may_vary_but_header_uses_first_row() -> None:
    rows = [{"b": 1, "a": 2}, {"a": 3, "b": 4}]
    encoded = toon.encode(rows)
    assert encoded.splitlines()[0] == b"[2]{b,a}:"
    assert toon.decode(encoded) == [{"b": 1, "a": 2}, {"b": 4, "a": 3}]


def test_same_width_different_key_set_falls_back() -> None:
    rows = [{"a": 1, "b": 2}, {"a": 3, "c": 4}]
    encoded = toon.encode(rows)
    assert encoded.splitlines()[0] == b"[2]:"
    assert toon.decode(encoded) == rows


def test_mixed_column_falls_back_to_list_form() -> None:
    rows = [
        {"id": 1, "meta": {"x": "a"}},
        {"id": 2, "meta": None},
    ]
    encoded = toon.encode({"rows": rows})
    text = encoded.decode()
    assert "{" not in text.splitlines()[0], "mixed shapes must not emit a field group header"
    assert toon.decode(encoded) == {"rows": rows}


def test_ragged_dicts_fall_back() -> None:
    rows = [{"a": 1}, {"a": 1, "b": 2}]
    encoded = toon.encode({"rows": rows})
    assert toon.decode(encoded) == {"rows": rows}


def test_doubly_nested_groups() -> None:
    rows = [
        {"id": 1, "outer": {"inner": {"leaf": "x"}, "flat": 1}},
        {"id": 2, "outer": {"inner": {"leaf": "y"}, "flat": 2}},
    ]
    encoded = toon.encode({"rows": rows})
    assert encoded.splitlines()[0] == b"rows[2]{id,outer{inner{leaf},flat}}:"
    assert toon.decode(encoded) == {"rows": rows}
