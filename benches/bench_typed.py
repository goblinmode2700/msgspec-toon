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

import build_freshness  # noqa: F401  (refuses stale or instrumented builds)
import msgspec
import msgspec_toon as toon
import toon as python_toon
from _timing import DEFAULT_WORKERS, measure, methodology, selected_metric
from _workers import across_workers
from payloads import (
    Document,
    document,
    entry_document,
    keyed_document,
    keyed_toon_text,
    toon_text,
    wide_dict_document,
)

LADDER = (4, 8, 16, 64, 512, 4096)


def sample_run(records: int) -> dict[str, Any]:
    """One worker's measurements. Gates are computed by the parent, once, from
    the mean across workers — a gate decided per worker would report whichever
    process got lucky."""
    text = toon_text(records)
    keyed_text = keyed_toon_text(records)
    doc = document(records)
    entry_doc = entry_document(records)
    selected = selected_metric()
    measuring_all = selected is None
    json_bytes = (
        msgspec.json.encode(doc) if measuring_all or selected == "decode.json_native" else b""
    )

    typed_decoder = toon.Decoder(Document)
    untyped_decoder = toon.Decoder()
    encoder = toon.Encoder()
    json_decoder = msgspec.json.Decoder(Document)

    # An A/B block requests one metric. Do not heat that block with the
    # unrelated incumbent pipeline or keyed-payload validation; full ladder
    # runs still execute every setup and assertion exactly as before (H5).
    need_incumbent = measuring_all or selected in {"decode.incumbent", "encode.incumbent"}
    incumbent_text = python_toon.encode(msgspec.to_builtins(doc)) if need_incumbent else ""
    if need_incumbent:
        assert msgspec.convert(python_toon.decode(incumbent_text), Document) == doc
    if measuring_all or selected == "decode.keyed_document":
        assert untyped_decoder.decode(keyed_text) == keyed_document(records)

    typed_decode = measure("decode.typed_direct", lambda: typed_decoder.decode(text)).us
    decoder_construction = measure("decode.decoder_construction", lambda: toon.Decoder(Document)).us
    functional_decode = measure("decode.functional", lambda: toon.decode(text, type=Document)).us
    untyped_decode = measure("decode.untyped_tree", lambda: untyped_decoder.decode(text)).us
    keyed_decode = measure("decode.keyed_document", lambda: untyped_decoder.decode(keyed_text)).us
    need_entry = measuring_all or selected in {"decode.entry_document", "encode.entry_document"}
    entry_text = encoder.encode(entry_doc) if need_entry else b""
    if need_entry:
        assert untyped_decoder.decode(entry_text) == entry_doc
    entry_decode = measure("decode.entry_document", lambda: untyped_decoder.decode(entry_text)).us
    entry_encode = measure("encode.entry_document", lambda: encoder.encode(entry_doc)).us
    need_wide = measuring_all or selected == "encode.wide_dict_document"
    wide_doc = wide_dict_document(records) if need_wide else []
    if need_wide:
        assert untyped_decoder.decode(encoder.encode(wide_doc)) == wide_doc
    wide_dict_encode = measure("encode.wide_dict_document", lambda: encoder.encode(wide_doc)).us
    wrapper_decode = measure(
        "decode.wrapper", lambda: msgspec.convert(untyped_decoder.decode(text), Document)
    ).us
    tree = untyped_decoder.decode(text)
    convert_only = measure("decode.convert_only", lambda: msgspec.convert(tree, Document)).us
    incumbent_decode = measure(
        "decode.incumbent", lambda: msgspec.convert(python_toon.decode(incumbent_text), Document)
    ).us
    json_native_decode = measure("decode.json_native", lambda: json_decoder.decode(json_bytes)).us

    typed_encode = measure("encode.typed_direct", lambda: encoder.encode(doc)).us
    functional_encode = measure("encode.functional", lambda: toon.encode(doc)).us
    to_builtins_only = measure("encode.to_builtins", lambda: msgspec.to_builtins(doc)).us
    incumbent_encode = measure(
        "encode.incumbent", lambda: python_toon.encode(msgspec.to_builtins(doc))
    ).us
    json_native_encode = measure("encode.json_native", lambda: msgspec.json.encode(doc)).us

    return {
        "records": records,
        "toon_bytes": len(text),
        "incumbent_pipeline_bytes": len(incumbent_text.encode()),
        "json_bytes": len(json_bytes),
        "decode_us": {
            "typed_direct": typed_decode,
            "functional": functional_decode,
            "untyped_tree": untyped_decode,
            "keyed_document": keyed_decode,
            "entry_document": entry_decode,
            "convert_only": convert_only,
            "wrapper_tree_plus_convert": wrapper_decode,
            "incumbent_pipeline_python_toon_plus_convert": incumbent_decode,
            "msgspec_json_native": json_native_decode,
        },
        "plan_us": {"decoder_construction_cached": decoder_construction},
        "encode_us": {
            "typed_direct_whole": typed_encode,
            "functional": functional_encode,
            "entry_document": entry_encode,
            "wide_dict_document": wide_dict_encode,
            "to_builtins_alone": to_builtins_only,
            "incumbent_pipeline_to_builtins_plus_python_toon": incumbent_encode,
            "msgspec_json_native": json_native_encode,
        },
        "notes": {
            "incumbent_pipeline": (
                "known-inefficient composition (to_builtins + python-toon, "
                "convert + python-toon); a benchmark to beat, not the strongest "
                "alternative"
            ),
        },
    }


def with_gates(result: dict[str, Any]) -> dict[str, Any]:
    """Decide the gates from the aggregated figures, not from one worker."""
    decode, encode = result["decode_us"], result["encode_us"]
    result["gates"] = {
        "G3_typed_decode_beats_wrapper": (
            decode["typed_direct"] < decode["wrapper_tree_plus_convert"]
        ),
        "G4_whole_encode_beats_to_builtins_alone": (
            encode["typed_direct_whole"] < encode["to_builtins_alone"]
        ),
        "typed_beats_incumbent_pipeline_decode": (
            decode["typed_direct"] < decode["incumbent_pipeline_python_toon_plus_convert"]
        ),
        "typed_beats_incumbent_pipeline_encode": (
            encode["typed_direct_whole"] < encode["incumbent_pipeline_to_builtins_plus_python_toon"]
        ),
    }
    return result


def run(records: int, *, workers: int = DEFAULT_WORKERS) -> dict[str, Any]:
    """The published figure: the mean across independent worker processes."""
    merged, spread = across_workers("bench_typed", "sample_run", [records], workers=workers)
    merged["worker_spread_pct"] = spread
    return with_gates(merged)


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
            f"functional={decode['functional']:>9}  "
            f"wrapper={decode['wrapper_tree_plus_convert']:>9}  "
            f"incumbent-pipeline={decode['incumbent_pipeline_python_toon_plus_convert']:>10}  "
            f"(untyped={decode['untyped_tree']}, convert={decode['convert_only']}, "
            f"json-native={decode['msgspec_json_native']})"
        )
        print(
            f"  encode us: typed={encode['typed_direct_whole']:>9}  "
            f"functional={encode['functional']:>9}  "
            f"to_builtins={encode['to_builtins_alone']:>9}  "
            f"incumbent-pipeline={encode['incumbent_pipeline_to_builtins_plus_python_toon']:>10}  "
            f"(json-native={encode['msgspec_json_native']})"
        )
        print(f"  diagnostic encode us: wide-64-column-dicts={encode['wide_dict_document']}")
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
