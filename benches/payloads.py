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
    rows = "\n".join(f"  {20000 + i},claude,worker-{i},{REGIONS[i % 4]}" for i in range(records))
    return (f"workers[{records}]{{pid,provider,metadata{{alias,region}}}}:\n{rows}").encode()


def string_heavy_tree(records: int) -> dict:
    """Prose-like values: long strings dominate the payload."""
    return {
        "articles": [
            {
                "title": f"Weekly operations report number {index} for the western region",
                "summary": (
                    "The deployment completed without incident and latency stayed "
                    "within the agreed budget across all monitored endpoints "
                    f"during window {index}."
                ),
                "author": {"name": f"Reporter {index}", "desk": "operations desk"},
            }
            for index in range(records)
        ]
    }


def numeric_heavy_tree(records: int) -> dict:
    """Many numeric columns, short strings."""
    return {
        "samples": [
            {
                "t": 1_722_000_000 + index,
                "cpu": round(0.1 + (index % 90) / 100, 2),
                "mem": 512 + index,
                "io": index * 37,
                "err": index % 3,
                "node": f"n{index % 8}",
            }
            for index in range(records)
        ]
    }
