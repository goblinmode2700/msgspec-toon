"""Raw codec comparison: msgspec_toon vs the incumbent TOON codecs.

Rows per ladder size, both directions, same run. Each codec round-trips its
own encoded bytes — the incumbents predate TOON 4.x and emit the fallback
list form for the challenge shape (no nested field groups), so their byte
sizes differ from ours. That difference is reported, not hidden: parsing a
fatter document is part of what the older format costs.

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
from _timing import best_of, methodology
from payloads import document

LADDER = (16, 64, 512, 4096)


def builtins_tree(records: int) -> Any:
    return msgspec.to_builtins(document(records))


def run(records: int) -> dict[str, Any]:
    tree = builtins_tree(records)

    ours_bytes = msgspec_toon.encode(tree)
    python_toon_text = python_toon.encode(tree)
    toons_text = toons_rust.dumps(tree)
    json_bytes = msgspec.json.encode(tree)

    assert msgspec_toon.decode(ours_bytes) == tree
    assert python_toon.decode(python_toon_text) == tree
    assert toons_rust.loads(toons_text) == tree

    ours_encoder = msgspec_toon.Encoder()
    ours_decoder = msgspec_toon.Decoder()

    encode_us = {
        "msgspec_toon": best_of(lambda: ours_encoder.encode(tree)).us,
        "toons_rust": best_of(lambda: toons_rust.dumps(tree)).us,
        "python_toon": best_of(lambda: python_toon.encode(tree)).us,
        "msgspec_json_context": best_of(lambda: msgspec.json.encode(tree)).us,
    }
    decode_us = {
        "msgspec_toon": best_of(lambda: ours_decoder.decode(ours_bytes)).us,
        "toons_rust": best_of(lambda: toons_rust.loads(toons_text)).us,
        "python_toon": best_of(lambda: python_toon.decode(python_toon_text)).us,
        "msgspec_json_context": best_of(lambda: msgspec.json.decode(json_bytes)).us,
    }
    output_bytes = {
        "msgspec_toon_tabular_4_1": len(ours_bytes),
        "toons_rust_fallback_3_0": len(toons_text.encode()),
        "python_toon_fallback": len(python_toon_text.encode()),
        "json_compact": len(json_bytes),
    }

    return {
        "records": records,
        "output_bytes": output_bytes,
        "encode_us": encode_us,
        "decode_us": decode_us,
        "gates": {
            "G5_encode_not_slower_than_toons": (
                encode_us["msgspec_toon"] <= encode_us["toons_rust"]
            ),
            "G5_decode_not_slower_than_toons": (
                decode_us["msgspec_toon"] <= decode_us["toons_rust"]
            ),
        },
    }


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
    print("payload: challenge shape (records with one nested object each)\n")
    all_pass = True
    for records in LADDER:
        result = run(records)
        sizes = result["output_bytes"]
        encode = result["encode_us"]
        decode = result["decode_us"]
        gates = result["gates"]
        all_pass &= all(gates.values())
        print(
            f"records={records:>5}  bytes: ours={sizes['msgspec_toon_tabular_4_1']} "
            f"toons={sizes['toons_rust_fallback_3_0']} "
            f"python-toon={sizes['python_toon_fallback']} json={sizes['json_compact']}"
        )
        print(
            f"  encode us: ours={encode['msgspec_toon']:>9}  toons={encode['toons_rust']:>9}  "
            f"python-toon={encode['python_toon']:>10}  (json={encode['msgspec_json_context']})"
        )
        print(
            f"  decode us: ours={decode['msgspec_toon']:>9}  toons={decode['toons_rust']:>9}  "
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
