"""Benchmark gates G3 and G4, plus the incumbent pipeline: same-run comparisons.

G3 — typed decode: the direct typed path must beat untyped decode plus
     msgspec.convert (the wrapper shape).
G4 — typed encode: the whole direct encode must beat msgspec.to_builtins
     alone (the wrapper's preparation step).

Incumbent pipeline rows reproduce the composition this project replaces —
encode as `python_toon.encode(normalize(obj))` where `normalize` is a
`msgspec.to_builtins` conversion, and decode as
`msgspec.convert(python_toon.decode(text), type)`. It is a known-inefficient
composition: a benchmark to beat, not the strongest alternative.

Context rows compare against msgspec.json on the equivalent document.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

import msgspec
import msgspec_toon as toon
import toon as python_toon
from _timing import best_of, methodology
from payloads import Document, document, toon_text

LADDER = (16, 64, 512, 4096)


def run(records: int) -> dict[str, Any]:
    text = toon_text(records)
    doc = document(records)
    json_bytes = msgspec.json.encode(doc)

    typed_decoder = toon.Decoder(Document)
    untyped_decoder = toon.Decoder()
    encoder = toon.Encoder()
    json_decoder = msgspec.json.Decoder(Document)

    # The incumbent pipeline round-trips its own (fallback-form) text.
    incumbent_text = python_toon.encode(msgspec.to_builtins(doc))
    assert msgspec.convert(python_toon.decode(incumbent_text), Document) == doc

    typed_decode = best_of(lambda: typed_decoder.decode(text)).us
    untyped_decode = best_of(lambda: untyped_decoder.decode(text)).us
    wrapper_decode = best_of(lambda: msgspec.convert(untyped_decoder.decode(text), Document)).us
    tree = untyped_decoder.decode(text)
    convert_only = best_of(lambda: msgspec.convert(tree, Document)).us
    incumbent_decode = best_of(
        lambda: msgspec.convert(python_toon.decode(incumbent_text), Document)
    ).us
    json_native_decode = best_of(lambda: json_decoder.decode(json_bytes)).us

    typed_encode = best_of(lambda: encoder.encode(doc)).us
    to_builtins_only = best_of(lambda: msgspec.to_builtins(doc)).us
    incumbent_encode = best_of(lambda: python_toon.encode(msgspec.to_builtins(doc))).us
    json_native_encode = best_of(lambda: msgspec.json.encode(doc)).us

    return {
        "records": records,
        "toon_bytes": len(text),
        "incumbent_pipeline_bytes": len(incumbent_text.encode()),
        "json_bytes": len(json_bytes),
        "decode_us": {
            "typed_direct": typed_decode,
            "untyped_tree": untyped_decode,
            "convert_only": convert_only,
            "wrapper_tree_plus_convert": wrapper_decode,
            "incumbent_pipeline_python_toon_plus_convert": incumbent_decode,
            "msgspec_json_native": json_native_decode,
        },
        "encode_us": {
            "typed_direct_whole": typed_encode,
            "to_builtins_alone": to_builtins_only,
            "incumbent_pipeline_to_builtins_plus_python_toon": incumbent_encode,
            "msgspec_json_native": json_native_encode,
        },
        "gates": {
            "G3_typed_decode_beats_wrapper": typed_decode < wrapper_decode,
            "G4_whole_encode_beats_to_builtins_alone": typed_encode < to_builtins_only,
            "typed_beats_incumbent_pipeline_decode": typed_decode < incumbent_decode,
            "typed_beats_incumbent_pipeline_encode": typed_encode < incumbent_encode,
        },
        "notes": {
            "incumbent_pipeline": (
                "known-inefficient composition (to_builtins + python-toon, "
                "convert + python-toon); a benchmark to beat, not the strongest "
                "alternative"
            ),
        },
    }


def main() -> None:
    print(f"python {sys.version.split()[0]}  msgspec {msgspec.__version__}")
    print("timing:", methodology())
    print("payload: records with one nested object each (the challenge shape)\n")
    all_pass = True
    for records in LADDER:
        result = run(records)
        decode = result["decode_us"]
        encode = result["encode_us"]
        gates = result["gates"]
        all_pass &= gates["G3_typed_decode_beats_wrapper"]
        all_pass &= gates["G4_whole_encode_beats_to_builtins_alone"]
        print(
            f"records={records:>5}  toon={result['toon_bytes']:>7}B  "
            f"incumbent={result['incumbent_pipeline_bytes']:>7}B  "
            f"json={result['json_bytes']:>7}B"
        )
        print(
            f"  decode us: typed={decode['typed_direct']:>9}  "
            f"wrapper={decode['wrapper_tree_plus_convert']:>9}  "
            f"incumbent-pipeline={decode['incumbent_pipeline_python_toon_plus_convert']:>10}  "
            f"(untyped={decode['untyped_tree']}, convert={decode['convert_only']}, "
            f"json-native={decode['msgspec_json_native']})"
        )
        print(
            f"  encode us: typed={encode['typed_direct_whole']:>9}  "
            f"to_builtins={encode['to_builtins_alone']:>9}  "
            f"incumbent-pipeline={encode['incumbent_pipeline_to_builtins_plus_python_toon']:>10}  "
            f"(json-native={encode['msgspec_json_native']})"
        )
        print(
            f"  gates: G3={'PASS' if gates['G3_typed_decode_beats_wrapper'] else 'FAIL'}  "
            f"G4={'PASS' if gates['G4_whole_encode_beats_to_builtins_alone'] else 'FAIL'}  "
            f"vs-incumbent: decode="
            f"{'PASS' if gates['typed_beats_incumbent_pipeline_decode'] else 'FAIL'} "
            f"encode="
            f"{'PASS' if gates['typed_beats_incumbent_pipeline_encode'] else 'FAIL'}\n"
        )
    print("ALL GATES PASS" if all_pass else "GATE FAILURES PRESENT — see rows above")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
