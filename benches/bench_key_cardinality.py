"""Untyped decode cost as the number of distinct ordinary-record keys grows."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

import build_freshness  # noqa: F401  (refuses stale or instrumented builds)
import msgspec_toon
from _timing import DEFAULT_WORKERS, measure, selected_metric
from _workers import across_workers
from payloads import distinct_key_records_tree

KEY_COUNTS = (4, 8, 16, 32, 64, 128, 256, 512, 1024)
GUARD_KEY_COUNTS = (32, 512)


def metric_name(distinct_keys: int) -> str:
    return f"decode.distinct_keys_{distinct_keys}"


def result_key(distinct_keys: int) -> str:
    return f"distinct_keys_{distinct_keys}"


def metadata_run(records: int = 4096) -> dict[str, Any]:
    """Deterministic wire sizes collected outside every timed observation."""

    encoder = msgspec_toon.Encoder()
    wire_bytes = {
        result_key(count): len(encoder.encode(distinct_key_records_tree(records, count)))
        for count in KEY_COUNTS
    }
    smallest = result_key(KEY_COUNTS[0])
    baseline_bytes = wire_bytes[smallest]
    return {
        "records": records,
        "distinct_key_counts": list(KEY_COUNTS),
        "wire_bytes": wire_bytes,
        "wire_relative_to_smallest": {
            result_key(count): round(wire_bytes[result_key(count)] / baseline_bytes, 3)
            for count in KEY_COUNTS
        },
        "cache_policy": (
            "decoder-local content cache; average O(1) hash lookup; "
            "unbounded only for one decode call"
        ),
    }


def sample_run(records: int) -> dict[str, Any]:
    """Measure the cardinality curve in one benchmark worker."""
    only = selected_metric()
    decoder = msgspec_toon.Decoder()
    decode_us: dict[str, float] = {}
    wire_bytes: dict[str, int] = {}

    for distinct_keys in KEY_COUNTS:
        name = metric_name(distinct_keys)
        key = result_key(distinct_keys)
        if only is not None and only != name:
            decode_us[key] = 0.0
            wire_bytes[key] = 0
            continue
        wire = msgspec_toon.encode(distinct_key_records_tree(records, distinct_keys))
        wire_bytes[key] = len(wire)
        decode_us[key] = measure(name, lambda wire=wire: decoder.decode(wire)).us

    return {
        "records": records,
        "distinct_key_counts": list(KEY_COUNTS),
        "wire_bytes": wire_bytes,
        "decode_us": decode_us,
    }


def run(records: int = 4096, *, workers: int = DEFAULT_WORKERS) -> dict[str, Any]:
    result, spread = across_workers(
        "bench_key_cardinality", "sample_run", [records], workers=workers
    )
    smallest = result_key(KEY_COUNTS[0])
    baseline_us = result["decode_us"][smallest]
    baseline_bytes = result["wire_bytes"][smallest]
    result["relative_to_smallest"] = {
        result_key(count): round(result["decode_us"][result_key(count)] / baseline_us, 3)
        for count in KEY_COUNTS
    }
    result["wire_relative_to_smallest"] = {
        result_key(count): round(result["wire_bytes"][result_key(count)] / baseline_bytes, 3)
        for count in KEY_COUNTS
    }
    result["worker_spread_pct"] = spread
    result["cache_policy"] = (
        "decoder-local content cache; average O(1) hash lookup; unbounded only for one decode call"
    )
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
