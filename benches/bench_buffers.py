"""Absolute decode times for the four public input buffer types."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

import build_freshness  # noqa: F401
import msgspec
import msgspec_toon as toon
from _timing import DEFAULT_WORKERS, measure, methodology
from _workers import across_workers

LADDER = (4, 4096)


def sample_run(records: int) -> dict[str, Any]:
    value = [{"id": index, "name": f"row-{index}"} for index in range(records)]
    document = toon.encode(value)
    text = document.decode()
    mutable = bytearray(document)
    view = memoryview(mutable)
    decoder = toon.Decoder()

    assert decoder.decode(document) == value
    assert decoder.decode(text) == value
    assert decoder.decode(mutable) == value
    assert decoder.decode(view) == value

    return {
        "records": records,
        "bytes": len(document),
        "decode_us": {
            "bytes": measure("buffer.decode.bytes", lambda: decoder.decode(document)).us,
            "str": measure("buffer.decode.str", lambda: decoder.decode(text)).us,
            "bytearray": measure("buffer.decode.bytearray", lambda: decoder.decode(mutable)).us,
            "memoryview": measure("buffer.decode.memoryview", lambda: decoder.decode(view)).us,
        },
    }


def run(records: int, *, workers: int = DEFAULT_WORKERS) -> dict[str, Any]:
    merged, spread = across_workers("bench_buffers", "sample_run", [records], workers=workers)
    merged["worker_spread_pct"] = spread
    return merged


def main() -> None:
    print(f"python {sys.version.split()[0]}  msgspec {msgspec.__version__}")
    print("timing:", methodology())
    results = []
    for records in LADDER:
        result = run(records)
        results.append(result)
        print(f"records={records:>5} bytes={result['bytes']:>8} decode µs={result['decode_us']}")
    output = Path(__file__).with_name("buffers-latest.json")
    output.write_text(
        json.dumps(
            {
                "python": sys.version.split()[0],
                "msgspec": msgspec.__version__,
                "method": methodology(),
                "results": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"results written to {output}")


if __name__ == "__main__":
    main()
