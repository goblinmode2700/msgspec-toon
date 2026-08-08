"""Challenge-shaped benchmark payloads: records with one nested object each."""

from __future__ import annotations

from typing import Any

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


#: The shapes and sizes the token evidence covers: the uniform-record ladder
#: plus a string-heavy and a numeric-heavy variant, so shape-dependence stays
#: visible instead of being averaged away. Defined here, not in a benchmark,
#: because the efficiency lock measures exactly this set.
TOKEN_LADDER = (16, 64, 512, 4096)
TOKEN_VARIANT_SIZES = (16, 512)


def irregular_tree(records: int) -> dict:
    """A shape the encoder cannot make tabular.

    Every other payload here is a uniform record array, which the encoder emits
    as a tabular block, or a uniform object-of-objects, which it emits as a
    *keyed* tabular block. Neither ever reaches the `key: value` entry writer.
    That hole was found by testing rather than by reading: perturbing the key
    separator moved no locked byte count until this shape existed.

    Uniformity is broken deliberately — alternating key sets and a mix of
    scalars, nested objects, and a short inline array — so the encoder falls
    back to writing entries one at a time.
    """
    tree: dict = {"title": "config", "version": records, "enabled": True, "ratio": 0.5}
    for index in range(records):
        if index % 2:
            tree[f"owner_{index}"] = {"name": f"n{index}", "email": f"e{index}"}
        else:
            tree[f"limits_{index}"] = {"soft": index, "hard": index * 2, "unit": "mb"}
    tree["tags"] = [f"tag-{index}" for index in range(min(records, 8))]
    return tree


def keyed_document(records: int) -> dict:
    """A uniform object-of-objects, which the encoder emits as a *keyed*
    tabular block: one header, then `key: cells` per row.

    Every other payload on the speed ladder is an array, whose rows carry no
    keys of their own. Keyed rows are the only shape where the strict-mode
    duplicate-key set grows with the row count, so the cost of resolving that
    set is invisible to the rest of the ladder — a linear scan over it is
    O(rows^2) here and O(1) everywhere else the ladder looks.
    """
    return {
        f"host-{index}": {
            "pid": 20000 + index,
            "provider": "claude",
            "region": REGIONS[index % 4],
        }
        for index in range(records)
    }


def keyed_toon_text(records: int) -> bytes:
    rows = "\n".join(f"  host-{i}: {20000 + i},claude,{REGIONS[i % 4]}" for i in range(records))
    return (f"[{records}:]{{pid,provider,region}}:\n{rows}").encode()


#: One sentence long enough that a `key: value` line's cost is dominated by
#: its value bytes rather than its key. Entry lines this shape are what the
#: line classifier walks in full when deciding header-vs-entry.
ENTRY_SENTENCE = (
    "the deployment completed without incident and latency stayed within "
    "the agreed budget across all monitored endpoints"
)


def entry_document(records: int) -> dict:
    """An object the encoder can only write entry by entry, with long values.

    Every array payload on the ladder is tabular and the keyed payload's rows
    are cells, so no metric exercised the `key: value` entry writer or the
    entry line classifier at document scale — the same class of blindness the
    keyed payload fixed for duplicate keys. Values alternate between long
    strings and small non-uniform objects: the mixed kinds keep the object
    ineligible for keyed tabular form in both directions, and the long values
    make line length matter, which is where a per-line scan's cost lives.
    """
    tree: dict = {}
    for index in range(records):
        if index % 3 == 2:
            tree[f"note_{index}"] = {"text": f"{ENTRY_SENTENCE} {index}", "priority": index % 5}
        else:
            tree[f"status_{index}"] = f"{ENTRY_SENTENCE} during window {index}"
    return tree


def token_payload_matrix() -> list[tuple[str, int, Any]]:
    cases: list[tuple[str, int, Any]] = []
    for records in TOKEN_LADDER:
        cases.append(("uniform-records", records, msgspec.to_builtins(document(records))))
    for records in TOKEN_VARIANT_SIZES:
        cases.append(("string-heavy", records, string_heavy_tree(records)))
        cases.append(("numeric-heavy", records, numeric_heavy_tree(records)))
        cases.append(("irregular", records, irregular_tree(records)))
    return cases
