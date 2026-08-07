"""Challenge-shaped benchmark payloads: records with one nested object each."""

from __future__ import annotations

import msgspec


class Metadata(msgspec.Struct, frozen=True):
    alias: str
    region: str


class Worker(msgspec.Struct, frozen=True):
    pid: int
    provider: str
    metadata: Metadata


class Document(msgspec.Struct, frozen=True):
    workers: list[Worker]


REGIONS = ("west", "east", "north", "south")


def document(records: int) -> Document:
    return Document(
        workers=[
            Worker(
                pid=20000 + index,
                provider="claude",
                metadata=Metadata(alias=f"worker-{index}", region=REGIONS[index % 4]),
            )
            for index in range(records)
        ]
    )


def toon_text(records: int) -> bytes:
    rows = "\n".join(
        f"  {20000 + i},claude,worker-{i},{REGIONS[i % 4]}" for i in range(records)
    )
    return (
        f"workers[{records}]{{pid,provider,metadata{{alias,region}}}}:\n{rows}"
    ).encode()
