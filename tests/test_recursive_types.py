"""Graph-plan and direct-construction coverage for recursive Structs."""

from __future__ import annotations

import msgspec
import msgspec_toon as toon
import pytest
from msgspec_toon._plan import compile_plan

type RecursiveAlias = list[RecursiveAlias]


class Node(msgspec.Struct, rename={"value": "v", "child": "next"}):
    value: int
    child: Node | None = None


class Left(msgspec.Struct):
    value: int
    right: Right | None = None


class Right(msgspec.Struct):
    label: str
    left: Left | None = None


def test_self_recursive_graph_uses_one_struct_node() -> None:
    graph = compile_plan(Node)
    root = graph.nodes[graph.root]
    child_union = graph.nodes[root.fields[1].plan]
    recursive_edge = child_union.items[0]
    assert recursive_edge == graph.root
    assert graph.nodes[recursive_edge].python_type is Node


def test_self_recursive_decode_uses_defaults_and_renamed_fields() -> None:
    expected = Node(1, Node(2, Node(3)))
    document = "v: 1\nnext:\n  v: 2\n  next:\n    v: 3"
    assert toon.decode(document, type=Node) == expected
    assert toon.decode(toon.encode(expected), type=Node) == expected


def test_mutually_recursive_structs_decode_directly() -> None:
    document = "value: 1\nright:\n  label: ok\n  left:\n    value: 2"
    assert toon.decode(document, type=Left) == Left(1, Right("ok", Left(2)))


def test_recursive_payload_still_uses_static_depth_fault() -> None:
    lines = ["v: 0"]
    for depth in range(1, 258):
        lines.append("  " * (depth - 1) + "next:")
        lines.append("  " * depth + f"v: {depth}")
    with pytest.raises(msgspec.DecodeError) as caught:
        toon.decode("\n".join(lines), type=Node)
    assert getattr(caught.value, "code", None) == "depth_limit"
    assert "v:" not in str(caught.value)


def test_recursive_annotation_alias_failure_is_contained() -> None:
    with pytest.raises(toon.TypePlanError) as caught:
        toon.Decoder(RecursiveAlias)
    assert caught.value.code == "unsupported_annotation"
    assert caught.value.__cause__ is None


def test_annotation_cache_remains_bounded() -> None:
    compile_plan.cache_clear()
    for index in range(520):
        cls = msgspec.defstruct(f"CacheNode{index}", [("value", int)])
        compile_plan(cls)
    info = compile_plan.cache_info()
    assert info.maxsize == 512
    assert info.currsize == 512
