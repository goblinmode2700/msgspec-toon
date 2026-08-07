"""G2: the typed path allocates no intermediate dict/list tree.

The native module counts every builtin dict/list the untyped consumer builds.
The typed consumer never routes through that path, so its counters stay zero
while the wrapper shape (untyped decode + msgspec.convert) pays one dict per
record plus one per nested object.
"""

from __future__ import annotations

import msgspec
import msgspec_toon as toon
from msgspec_toon import _native


class Metadata(msgspec.Struct, frozen=True):
    alias: str
    region: str


class Worker(msgspec.Struct, frozen=True):
    pid: int
    provider: str
    metadata: Metadata


class Document(msgspec.Struct, frozen=True):
    workers: list[Worker]


RECORDS = 64
TEXT = (
    "workers[%d]{pid,provider,metadata{alias,region}}:\n" % RECORDS
    + "\n".join(f"  {20000 + i},claude,worker-{i},west" for i in range(RECORDS))
).encode()


def test_typed_decode_builds_no_intermediate_tree() -> None:
    decoder = toon.Decoder(Document)
    _native.reset_alloc_stats()
    value = decoder.decode(TEXT)
    dicts, lists = _native.alloc_stats()
    assert isinstance(value, Document)
    assert len(value.workers) == RECORDS
    assert dicts == 0, f"typed decode built {dicts} intermediate dicts"
    assert lists == 0, f"typed decode built {lists} intermediate lists"


def test_wrapper_path_builds_the_tree_the_typed_path_avoids() -> None:
    _native.reset_alloc_stats()
    tree = toon.decode(TEXT)
    dicts, lists = _native.alloc_stats()
    document = msgspec.convert(tree, Document)
    assert len(document.workers) == RECORDS
    # One outer dict, one dict per record, one nested dict per record.
    assert dicts == 1 + RECORDS * 2
    assert lists >= 1
