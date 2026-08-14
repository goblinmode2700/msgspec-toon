"""End-to-end JSON/TOON/JSON integration costs.

This is not a pure codec gate. It measures the work an application pays when
its data starts and ends as compact JSON:

* msgspec-toon decodes JSON and converts both ways in one Python process.
* python-toon performs the same work through its Python API.
* the ``toon`` command performs encode and decode in two child processes.

Rows cross four payload shapes and four sizes. All rows use the repository
timing implementation and its ten-worker mean.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

import build_freshness  # noqa: F401
import msgspec
import msgspec_toon
import toon as python_toon
from _timing import DEFAULT_WORKERS, measure
from _workers import across_workers
from payloads import COMPARATIVE_LADDER, COMPARATIVE_SHAPES, comparative_tree

LADDER = COMPARATIVE_LADDER
SHAPES = COMPARATIVE_SHAPES
TOON_CLI = Path(sys.prefix) / "bin" / "toon"


def metadata_run(records: int, shape: str = "uniform-records") -> dict[str, Any]:
    """Deterministic row metadata collected outside every timed observation."""

    json_bytes = msgspec.json.encode(comparative_tree(shape, records))
    return {"shape": shape, "records": records, "input_json_bytes": len(json_bytes)}


def _msgspec_toon_roundtrip(json_bytes: bytes) -> bytes:
    value = msgspec.json.decode(json_bytes)
    toon_bytes = msgspec_toon.encode(value)
    return msgspec.json.encode(msgspec_toon.decode(toon_bytes))


def _python_toon_roundtrip(json_bytes: bytes) -> bytes:
    value = msgspec.json.decode(json_bytes)
    toon_text = python_toon.encode(value)
    return msgspec.json.encode(python_toon.decode(toon_text))


def _toon_cli_roundtrip(json_bytes: bytes) -> bytes:
    encoded = subprocess.run(
        [str(TOON_CLI), "-", "--encode"],
        input=json_bytes,
        capture_output=True,
        check=True,
    ).stdout
    return subprocess.run(
        [str(TOON_CLI), "-", "--decode"],
        input=encoded,
        capture_output=True,
        check=True,
    ).stdout.strip()


def sample_run(records: int, shape: str = "uniform-records") -> dict[str, Any]:
    json_bytes = msgspec.json.encode(comparative_tree(shape, records))
    expected = msgspec.json.decode(json_bytes)

    for result in (
        _msgspec_toon_roundtrip(json_bytes),
        _python_toon_roundtrip(json_bytes),
        _toon_cli_roundtrip(json_bytes),
    ):
        assert msgspec.json.decode(result) == expected

    return {
        "shape": shape,
        "records": records,
        "input_json_bytes": len(json_bytes),
        "roundtrip_us": {
            "msgspec_toon_in_process": measure(
                "integration.msgspec_toon", lambda: _msgspec_toon_roundtrip(json_bytes)
            ).us,
            "python_toon_in_process": measure(
                "integration.python_toon", lambda: _python_toon_roundtrip(json_bytes)
            ).us,
            "python_toon_two_process_cli": measure(
                "integration.python_toon_cli",
                lambda: _toon_cli_roundtrip(json_bytes),
                target_seconds=0.25,
            ).us,
        },
    }


def run(
    records: int,
    *,
    shape: str = "uniform-records",
    workers: int = DEFAULT_WORKERS,
) -> dict[str, Any]:
    merged, spread = across_workers(
        "bench_integration", "sample_run", [records, shape], workers=workers
    )
    merged["worker_spread_pct"] = spread
    return merged


def main() -> None:
    for shape in SHAPES:
        for records in LADDER:
            print(run(records, shape=shape))


if __name__ == "__main__":
    main()
