"""Same-process proof for msgspec's optional Struct C API.

Both encoders use the same msgspec and msgspec-toon binaries. The module capsule
is hidden only while constructing the attribute-fallback Encoder; the capsule
Encoder copies its function table and every class plan copies its offsets.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

import msgspec
import msgspec._core
import msgspec_toon as toon
from _timing import DEFAULT_WORKERS, measure, methodology
from _workers import across_workers
from payloads import document

LADDER = (4, 8, 16, 64, 512, 4096)


def sample_run(records: int) -> dict[str, Any]:
    capsule = msgspec._core._C_API
    del msgspec._core._C_API
    try:
        attribute_encoder = toon.Encoder()
    finally:
        msgspec._core._C_API = capsule
    capsule_encoder = toon.Encoder()

    assert attribute_encoder._native._struct_access == "attribute"
    assert capsule_encoder._native._struct_access == "capsule"
    value = document(records)
    expected = attribute_encoder.encode(value)
    assert capsule_encoder.encode(value) == expected

    return {
        "records": records,
        "capsule_a_us": measure("struct_capi.capsule_a", lambda: capsule_encoder.encode(value)).us,
        "attribute_a_us": measure(
            "struct_capi.attribute_a", lambda: attribute_encoder.encode(value)
        ).us,
        "attribute_b_us": measure(
            "struct_capi.attribute_b", lambda: attribute_encoder.encode(value)
        ).us,
        "capsule_b_us": measure("struct_capi.capsule_b", lambda: capsule_encoder.encode(value)).us,
        "to_builtins_us": measure("struct_capi.to_builtins", lambda: msgspec.to_builtins(value)).us,
    }


def main() -> None:
    print("timing:", methodology())
    for records in LADDER:
        result, spread = across_workers(
            "bench_struct_capi", "sample_run", [records], workers=DEFAULT_WORKERS
        )
        print(result)
        print("worker_spread_pct:", spread)


if __name__ == "__main__":
    main()
