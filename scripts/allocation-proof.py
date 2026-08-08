"""Generate the G2 allocation evidence (`conformance/allocation-proof.json`).

Runs only under an `alloc-stats` build — `make g2` builds one into `.venv-g2`
and invokes this script there. The release wheel has no counters, so the
release report reads this artifact instead of measuring one itself: evidence
comes from an instrumented build, timings come from a clean one, and neither
contaminates the other.

Counter semantics are the codec's, not the caller's: `builtin_*` are the
dict/list tree the untyped builder produces. They are requested output when the
target is `Any`, and the intermediate tree the wrapper pipeline pays for when
the caller wanted Structs. G2 is the claim that a target with no `Any` builds
zero of them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "benches"))

import msgspec
import msgspec_toon as toon
from msgspec_toon import _native
from payloads import Document, toon_text

RECORDS = 64


def _measure(decode: Any) -> dict[str, int]:
    _native.reset_alloc_stats()
    decode()
    return dict(_native.alloc_stats())


def main() -> None:
    if not hasattr(_native, "alloc_stats"):
        raise SystemExit(
            "this interpreter has an uninstrumented wheel — run `make g2`, "
            "which builds `--features alloc-stats` into .venv-g2"
        )

    text = toon_text(RECORDS)
    decoder = toon.Decoder(Document)

    typed = _measure(lambda: decoder.decode(text))

    tree: Any = None

    def untyped_decode() -> None:
        nonlocal tree
        tree = toon.decode(text)

    wrapper = _measure(untyped_decode)
    msgspec.convert(tree, Document)

    proof = {
        "payload_records": RECORDS,
        "build": "alloc-stats (instrumented; never the benchmarked wheel)",
        "counter_semantics": {
            "builtin_dicts": "dict built by the untyped builder",
            "builtin_lists": "list built by the untyped builder",
            "final_lists": "list or tuple the target type declared",
            "final_dicts": "dict the target type declared",
            "final_structs": "Struct instance constructed by the typed consumer",
        },
        "typed": typed,
        "wrapper": wrapper,
        "gate_G2_zero_builtin_containers": typed["builtin_dicts"] == 0
        and typed["builtin_lists"] == 0,
        "probe_observed_the_typed_path": typed["final_structs"] > 0,
        "note": (
            "An `Any` field asks for a builtin tree; containers inside an `Any` "
            "subtree are requested output and are not a G2 violation. See "
            "tests/test_typed_allocations.py for that case."
        ),
    }

    out = REPO / "conformance" / "allocation-proof.json"
    out.write_text(json.dumps(proof, indent=2) + "\n")
    print(json.dumps(proof, indent=2))
    print(f"\nwritten to {out}")


if __name__ == "__main__":
    main()
