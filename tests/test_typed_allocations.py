"""G2: the typed path builds no builtin dict/list tree.

The counters live in `src/containers.rs`, the single module through which every
Python container in the codec is constructed — a `disallowed-methods` clippy
lint fails the build on any `PyDict::new`/`PyList::new`/`PyTuple::new` outside
it. A zero here is therefore a statement about the codec, not about whether one
consumer's call sites ran.

The counters are compiled out unless the `alloc-stats` feature is on, so this
file skips against the release wheel and runs under `make g2`. That separation
is the point: the release wheel every benchmark measures carries no
instrumentation.

Each assertion below is two-sided. A zero alone is weak evidence — it also
holds if nothing was decoded — so every case pins the positive counts too.
"""

from __future__ import annotations

from typing import Any

import msgspec
import msgspec_toon as toon
import pytest
from msgspec_toon import _native

pytestmark = pytest.mark.skipif(
    not hasattr(_native, "alloc_stats"),
    reason="allocation counters are an `alloc-stats` build; run `make g2`",
)


class Metadata(msgspec.Struct, frozen=True):
    alias: str
    region: str


class Worker(msgspec.Struct, frozen=True):
    pid: int
    provider: str
    metadata: Metadata


class Document(msgspec.Struct, frozen=True):
    workers: list[Worker]


class LooseDocument(msgspec.Struct, frozen=True):
    """A schema that asks for a builtin subtree on purpose."""

    workers: list[Any]


class RecursiveNode(msgspec.Struct):
    value: int
    child: RecursiveNode | None = None


class PositionalNode(msgspec.Struct, array_like=True):
    value: int
    label: str


class TaggedA(msgspec.Struct, tag="a"):
    value: int


class TaggedB(msgspec.Struct, tag="b"):
    value: int


RECORDS = 64
TEXT = (
    f"workers[{RECORDS}]{{pid,provider,metadata{{alias,region}}}}:\n"
    + "\n".join(f"  {20000 + i},claude,worker-{i},west" for i in range(RECORDS))
).encode()


def _stats_for(decode: object) -> dict[str, int]:
    _native.reset_alloc_stats()
    decode()  # type: ignore[operator]
    return dict(_native.alloc_stats())


def test_typed_decode_builds_no_builtin_tree() -> None:
    decoder = toon.Decoder(Document)
    value: Document | None = None

    def decode() -> None:
        nonlocal value
        value = decoder.decode(TEXT)

    stats = _stats_for(decode)

    assert isinstance(value, Document)
    assert len(value.workers) == RECORDS
    # The forbidden containers.
    assert stats["builtin_dicts"] == 0, f"typed decode built {stats['builtin_dicts']} dicts"
    assert stats["builtin_lists"] == 0, f"typed decode built {stats['builtin_lists']} lists"
    # The positive half: the probe demonstrably observed this decode.
    assert stats["final_structs"] == 1 + RECORDS * 2  # Document + Worker + Metadata
    assert stats["final_lists"] == 1  # the one list[Worker] the target declared
    assert stats["final_dicts"] == 0


def test_any_subtree_builds_the_builtin_tree_it_was_asked_for() -> None:
    """G2 is about trees nobody asked for, not about `Any`."""
    decoder = toon.Decoder(LooseDocument)
    value: LooseDocument | None = None

    def decode() -> None:
        nonlocal value
        value = decoder.decode(TEXT)

    stats = _stats_for(decode)

    assert isinstance(value, LooseDocument)
    assert value.workers[0] == {
        "pid": 20000,
        "provider": "claude",
        "metadata": {"alias": "worker-0", "region": "west"},
    }
    # One dict per record plus one per nested object — requested output here,
    # because the field is `Any`.
    assert stats["builtin_dicts"] == RECORDS * 2
    assert stats["final_structs"] == 1
    assert stats["final_lists"] == 1


def test_wrapper_path_builds_the_tree_the_typed_path_avoids() -> None:
    tree: object = None

    def decode() -> None:
        nonlocal tree
        tree = toon.decode(TEXT)

    stats = _stats_for(decode)
    document = msgspec.convert(tree, Document)

    assert len(document.workers) == RECORDS
    # One outer dict, one dict per record, one nested dict per record. These
    # are intermediates: the caller wanted Structs and pays for the tree first.
    assert stats["builtin_dicts"] == 1 + RECORDS * 2
    assert stats["builtin_lists"] >= 1
    assert stats["final_structs"] == 0


def test_untyped_decode_output_is_not_counted_as_a_typed_allocation() -> None:
    """`type=Any` asks for the builtin tree; nothing final is built."""
    stats = _stats_for(lambda: toon.decode(TEXT))
    assert stats["builtin_dicts"] == 1 + RECORDS * 2
    assert stats["final_structs"] == 0
    assert stats["final_lists"] == 0


def test_recursive_typed_decode_builds_only_final_structs() -> None:
    value: RecursiveNode | None = None

    def decode() -> None:
        nonlocal value
        value = toon.decode(
            b"value: 1\nchild:\n  value: 2\n  child:\n    value: 3",
            type=RecursiveNode,
        )

    stats = _stats_for(decode)
    assert value == RecursiveNode(1, RecursiveNode(2, RecursiveNode(3)))
    assert stats["builtin_dicts"] == 0
    assert stats["builtin_lists"] == 0
    assert stats["final_structs"] == 3


def test_array_like_and_tagged_frames_build_only_final_structs() -> None:
    positional_stats = _stats_for(lambda: toon.decode(b"[2]:\n  - 1\n  - x", type=PositionalNode))
    tagged_stats = _stats_for(lambda: toon.decode(b"value: 1\ntype: a", type=TaggedA | TaggedB))
    for stats in (positional_stats, tagged_stats):
        assert stats["builtin_dicts"] == 0
        assert stats["builtin_lists"] == 0
        assert stats["final_structs"] == 1
