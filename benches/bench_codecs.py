"""Raw codec comparison: msgspec_toon vs the incumbent TOON codecs.

Rows cross four payload shapes, four sizes, and both directions. Each codec
round-trips its own encoded bytes. The byte sizes are part of the evidence.

Gate G5 (codec floor): no slower than the fastest competing compiled codec
(`toons`, Rust) at every size in both directions.
"""

from __future__ import annotations

import importlib.metadata
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

import build_freshness  # noqa: F401  (refuses stale or instrumented builds)
import msgspec
import msgspec_toon
import toon as python_toon
import toons as toons_rust
from _timing import DEFAULT_WORKERS, measure, methodology, selected_metric
from _workers import across_workers
from payloads import COMPARATIVE_LADDER, COMPARATIVE_SHAPES, comparative_tree

LADDER = COMPARATIVE_LADDER
SHAPES = COMPARATIVE_SHAPES


def sample_run(records: int, shape: str = "uniform-records") -> dict[str, Any]:
    """One worker's measurements; the parent decides the gates from the mean."""
    tree = comparative_tree(shape, records)
    selected = selected_metric()
    measuring_all = selected is None

    ours_bytes = msgspec_toon.encode(tree)
    need_python_toon = measuring_all or selected in {"encode.python_toon", "decode.python_toon"}
    need_toons = measuring_all or selected in {"encode.toons_rust", "decode.toons_rust"}
    need_json = measuring_all or selected in {"encode.json", "decode.json"}
    python_toon_text = python_toon.encode(tree) if need_python_toon else ""
    toons_text = toons_rust.dumps(tree) if need_toons else ""
    json_bytes = msgspec.json.encode(tree) if need_json else b""

    assert msgspec_toon.decode(ours_bytes) == tree
    if need_python_toon:
        assert python_toon.decode(python_toon_text) == tree
    if need_toons:
        assert toons_rust.loads(toons_text) == tree

    ours_encoder = msgspec_toon.Encoder()
    ours_decoder = msgspec_toon.Decoder()

    encode_us = {
        "msgspec_toon": measure("encode.msgspec_toon", lambda: ours_encoder.encode(tree)).us,
        "toons_rust": measure("encode.toons_rust", lambda: toons_rust.dumps(tree)).us,
        "python_toon": measure("encode.python_toon", lambda: python_toon.encode(tree)).us,
        "msgspec_json_context": measure("encode.json", lambda: msgspec.json.encode(tree)).us,
    }
    decode_us = {
        "msgspec_toon": measure("decode.msgspec_toon", lambda: ours_decoder.decode(ours_bytes)).us,
        "toons_rust": measure("decode.toons_rust", lambda: toons_rust.loads(toons_text)).us,
        "python_toon": measure(
            "decode.python_toon", lambda: python_toon.decode(python_toon_text)
        ).us,
        "msgspec_json_context": measure("decode.json", lambda: msgspec.json.decode(json_bytes)).us,
    }
    output_bytes = {
        "msgspec_toon_tabular_4_1": len(ours_bytes),
        "toons_rust_fallback_3_0": len(toons_text.encode()),
        "python_toon_fallback": len(python_toon_text.encode()),
        "json_compact": len(json_bytes),
    }

    return {
        "shape": shape,
        "records": records,
        "output_bytes": output_bytes,
        "encode_us": encode_us,
        "decode_us": decode_us,
    }


def with_gates(result: dict[str, Any]) -> dict[str, Any]:
    """Decide G5 from the aggregated figures, not from one worker."""
    encode_us, decode_us = result["encode_us"], result["decode_us"]
    result["gates"] = {
        "G5_encode_not_slower_than_toons": encode_us["msgspec_toon"] <= encode_us["toons_rust"],
        "G5_decode_not_slower_than_toons": decode_us["msgspec_toon"] <= decode_us["toons_rust"],
    }
    return result


def run(
    records: int,
    *,
    shape: str = "uniform-records",
    workers: int = DEFAULT_WORKERS,
) -> dict[str, Any]:
    """The published figure: the mean across independent worker processes."""
    merged, spread = across_workers("bench_codecs", "sample_run", [records, shape], workers=workers)
    merged["worker_spread_pct"] = spread
    return with_gates(merged)


def versions() -> dict[str, str]:
    return {
        "msgspec-toon": importlib.metadata.version("msgspec-toon"),
        "msgspec": msgspec.__version__,
        "python-toon": importlib.metadata.version("python-toon"),
        "toons": importlib.metadata.version("toons"),
        "python": sys.version.split()[0],
    }


def main() -> None:
    print("versions:", versions())
    print("timing:", methodology())
    print("payloads: four shapes crossed with four record counts\n")
    all_pass = True
    for shape in SHAPES:
        for records in LADDER:
            result = run(records, shape=shape)
            sizes = result["output_bytes"]
            encode = result["encode_us"]
            decode = result["decode_us"]
            gates = result["gates"]
            all_pass &= all(gates.values())
            print(
                f"shape={shape:<15} records={records:>5}  bytes: "
                f"ours={sizes['msgspec_toon_tabular_4_1']} "
                f"toons={sizes['toons_rust_fallback_3_0']} "
                f"python-toon={sizes['python_toon_fallback']} json={sizes['json_compact']}"
            )
            print(
                f"  encode µs: ours={encode['msgspec_toon']:>9}  toons={encode['toons_rust']:>9}  "
                f"python-toon={encode['python_toon']:>10}  (json={encode['msgspec_json_context']})"
            )
            print(
                f"  decode µs: ours={decode['msgspec_toon']:>9}  toons={decode['toons_rust']:>9}  "
                f"python-toon={decode['python_toon']:>10}  (json={decode['msgspec_json_context']})"
            )
            print(
                f"  G5: encode={'PASS' if gates['G5_encode_not_slower_than_toons'] else 'FAIL'}  "
                f"decode={'PASS' if gates['G5_decode_not_slower_than_toons'] else 'FAIL'}\n"
            )
    print("G5 PASSES AT EVERY SIZE" if all_pass else "G5 FAILURES PRESENT — see rows above")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
