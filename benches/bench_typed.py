"""Benchmark gates G3 and G4: same-run, same-machine comparisons.

G3 — typed decode: the direct typed path must beat untyped decode plus
     msgspec.convert (the wrapper shape).
G4 — typed encode: the whole direct encode must beat msgspec.to_builtins
     alone (the wrapper's preparation step).

Context rows compare against msgspec.json on the equivalent document.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import msgspec
import msgspec_toon as toon
from payloads import Document, document, toon_text


def best_of(fn, *, repeats: int = 7, target_seconds: float = 0.05) -> float:
    """Minimum autoranged per-call time in microseconds."""
    fn()  # warm caches and plans
    number = 1
    while True:
        start = time.perf_counter()
        for _ in range(number):
            fn()
        elapsed = time.perf_counter() - start
        if elapsed >= target_seconds:
            break
        number *= 2
    best = elapsed / number
    for _ in range(repeats - 1):
        start = time.perf_counter()
        for _ in range(number):
            fn()
        elapsed = time.perf_counter() - start
        best = min(best, elapsed / number)
    return best * 1e6


def run(records: int) -> dict:
    text = toon_text(records)
    doc = document(records)
    json_bytes = msgspec.json.encode(doc)

    typed_decoder = toon.Decoder(Document)
    untyped_decoder = toon.Decoder()
    encoder = toon.Encoder()
    json_decoder = msgspec.json.Decoder(Document)

    typed_decode = best_of(lambda: typed_decoder.decode(text))
    untyped_decode = best_of(lambda: untyped_decoder.decode(text))
    wrapper_decode = best_of(
        lambda: msgspec.convert(untyped_decoder.decode(text), Document)
    )
    convert_only = best_of(
        lambda tree=untyped_decoder.decode(text): msgspec.convert(tree, Document)
    )
    json_native_decode = best_of(lambda: json_decoder.decode(json_bytes))

    typed_encode = best_of(lambda: encoder.encode(doc))
    to_builtins_only = best_of(lambda: msgspec.to_builtins(doc))
    json_native_encode = best_of(lambda: msgspec.json.encode(doc))

    return {
        "records": records,
        "toon_bytes": len(text),
        "json_bytes": len(json_bytes),
        "decode_us": {
            "typed_direct": round(typed_decode, 2),
            "untyped_tree": round(untyped_decode, 2),
            "convert_only": round(convert_only, 2),
            "wrapper_tree_plus_convert": round(wrapper_decode, 2),
            "msgspec_json_native": round(json_native_decode, 2),
        },
        "encode_us": {
            "typed_direct_whole": round(typed_encode, 2),
            "to_builtins_alone": round(to_builtins_only, 2),
            "msgspec_json_native": round(json_native_encode, 2),
        },
        "gates": {
            "G3_typed_decode_beats_wrapper": typed_decode < wrapper_decode,
            "G4_whole_encode_beats_to_builtins_alone": typed_encode < to_builtins_only,
        },
    }


def main() -> None:
    print(f"python {sys.version.split()[0]}  msgspec {msgspec.__version__}")
    print("payload: records with one nested object each (the challenge shape)\n")
    all_pass = True
    for records in (16, 64, 512, 4096):
        result = run(records)
        decode = result["decode_us"]
        encode = result["encode_us"]
        gates = result["gates"]
        all_pass &= all(gates.values())
        print(
            f"records={records:>5}  toon={result['toon_bytes']:>7}B  "
            f"json={result['json_bytes']:>7}B"
        )
        print(
            f"  decode us: typed={decode['typed_direct']:>9}  "
            f"wrapper={decode['wrapper_tree_plus_convert']:>9}  "
            f"(untyped={decode['untyped_tree']}, convert={decode['convert_only']}, "
            f"json-native={decode['msgspec_json_native']})"
        )
        print(
            f"  encode us: typed={encode['typed_direct_whole']:>9}  "
            f"to_builtins={encode['to_builtins_alone']:>9}  "
            f"(json-native={encode['msgspec_json_native']})"
        )
        print(
            f"  gates: G3={'PASS' if gates['G3_typed_decode_beats_wrapper'] else 'FAIL'}  "
            f"G4={'PASS' if gates['G4_whole_encode_beats_to_builtins_alone'] else 'FAIL'}\n"
        )
    print("ALL GATES PASS" if all_pass else "GATE FAILURES PRESENT — see rows above")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
