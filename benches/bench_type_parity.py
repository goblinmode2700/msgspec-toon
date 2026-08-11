"""Focused absolute timings for issue-08 typed parity."""

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

LADDER = (4, 64, 512, 4096)


def sample_run(records: int) -> dict[str, Any]:
    integers = list(range(records))
    mixed: list[int | str] = [index if index % 2 == 0 else f"v{index}" for index in range(records)]

    integer_document = toon.encode(integers)
    mixed_document = toon.encode(mixed)
    int_decoder = toon.Decoder(list[int])
    union_decoder = toon.Decoder(list[int | str])
    object_decoder = toon.Decoder(list[object])
    any_decoder = toon.Decoder(list[Any])

    assert union_decoder.decode(mixed_document) == mixed
    assert object_decoder.decode(mixed_document) == mixed

    return {
        "records": records,
        "decode_us": {
            "int_control": measure(
                "parity.decode.int", lambda: int_decoder.decode(integer_document)
            ).us,
            "scalar_union": measure(
                "parity.decode.scalar_union", lambda: union_decoder.decode(mixed_document)
            ).us,
            "object": measure(
                "parity.decode.object", lambda: object_decoder.decode(mixed_document)
            ).us,
            "any_control": measure(
                "parity.decode.any", lambda: any_decoder.decode(mixed_document)
            ).us,
        },
    }


def run(records: int, *, workers: int = DEFAULT_WORKERS) -> dict[str, Any]:
    merged, spread = across_workers("bench_type_parity", "sample_run", [records], workers=workers)
    merged["worker_spread_pct"] = spread
    return merged


def main() -> None:
    print(f"python {sys.version.split()[0]}  msgspec {msgspec.__version__}")
    print("timing:", methodology())
    results = []
    for records in LADDER:
        result = run(records)
        results.append(result)
        print(f"records={records:>5}  decode µs={result['decode_us']}")
    output = Path(__file__).with_name("type-parity-latest.json")
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
