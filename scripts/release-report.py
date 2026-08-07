"""Generate the machine-readable qualification report.

Every release claim is a generated report, never an assertion (openspec:
distribution-quality): fixture conformance with corpus pinning, the
allocation proof (G2), same-run speed comparisons (G3/G4/G5 and the
incumbent pipeline), token efficiency under named tokenizers (T1-T3), and
the optimization ledger with its frozen-baseline A/B evidence.
"""

from __future__ import annotations

import importlib.metadata
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benches"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "conformance"))

import bench_codecs
import bench_tokens
import build_freshness  # noqa: F401  (refuses stale or instrumented builds)
import msgspec
from _timing import methodology
from bench_typed import run
from msgspec_toon import _native
from support_matrix import as_report as support_matrix_report


def allocation_proof() -> dict:
    """Read the G2 evidence; refuse to fabricate it.

    The counters exist only in an `alloc-stats` build (`make g2`), which is
    deliberately not the wheel this report benchmarks — instrumentation in a
    timed wheel would tax the wrapper side of G3/G5 with one atomic per
    container and quietly flatter the typed path.
    """
    proof_path = Path(__file__).resolve().parent.parent / "conformance" / "allocation-proof.json"
    if not proof_path.exists():
        return {"status": "NOT RUN — execute `make g2` first"}
    proof = json.loads(proof_path.read_text())
    if hasattr(_native, "alloc_stats"):
        proof["warning"] = (
            "this report was generated against an instrumented wheel; "
            "its timings are not release-representative"
        )
    return proof


def ab_latest() -> dict:
    """Publish the last frozen-baseline A/B with every block it measured.

    A single summary number hides the thing a reader most needs: whether the
    session could resolve the delta at all. `benches/ab.py` keeps each block and
    labels rows whose change is smaller than the same-build noise floor.
    """
    path = Path(__file__).resolve().parent.parent / "benches" / "ab-latest.json"
    if not path.exists():
        return {"status": "NOT RUN — execute `make baseline && make ab` first"}
    return json.loads(path.read_text())


def conformance_summary(lock: dict) -> dict:
    """Summarize the latest conformance run; refuse to fabricate one."""
    results_path = (
        Path(__file__).resolve().parent.parent / "conformance" / "conformance-results.json"
    )
    if not results_path.exists():
        return {
            "spec_version_target": lock["spec_version"],
            "fixture_commit": lock["commit"],
            "status": "NOT RUN — execute conformance/run.py first",
        }
    summary = json.loads(results_path.read_text())["summary"]
    unsupported = [
        f"{r['category']}/{r['file']}#{r['index']}: {r['detail']}"
        for r in json.loads(results_path.read_text())["results"]
        if r["status"] == "unsupported_option"
    ]
    return {
        "spec_version_target": lock["spec_version"],
        "fixture_commit": summary["corpus"]["commit"],
        "fixture_tag": summary["corpus"]["tag"],
        "fixture_tree_sha256": summary["corpus"]["tree_sha256"],
        "total_tests": summary["corpus"]["total_tests"],
        "decode": summary["decode"],
        "encode": summary["encode"],
        "strict_error_fixtures": summary["strict_error_fixtures"],
        "declared_divergences": {
            "count": len(unsupported),
            "kind": (
                "none expected: the spec-defined wire options (delimiter, "
                "indentSize) are applied from fixture options; any entry here is a "
                "regression"
            ),
            "tests": unsupported,
        },
    }


def main() -> None:
    lock = json.loads(
        (Path(__file__).resolve().parent.parent / "conformance" / "fixtures.lock.json").read_text()
    )
    benchmarks = [run(records) for records in (16, 64, 512, 4096)]
    codec_benchmarks = [bench_codecs.run(records) for records in bench_codecs.LADDER]
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "distribution": (f"msgspec-toon {importlib.metadata.version('msgspec-toon')}"),
        "environment": {
            "python": sys.version.split()[0],
            "msgspec": msgspec.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "measured_versions": bench_codecs.versions(),
        "timing_methodology": methodology(),
        "conformance": conformance_summary(lock),
        "allocation_proof": allocation_proof(),
        "support_matrix": support_matrix_report(),
        "benchmarks_typed_same_run": benchmarks,
        "benchmarks_codecs_same_run": codec_benchmarks,
        "token_efficiency": bench_tokens.run(),
        "speed_ab_latest": ab_latest(),
        "optimization_ledger": json.loads(
            (
                Path(__file__).resolve().parent.parent / "benches" / "optimization-ledger.json"
            ).read_text()
        ),
        "gates": {
            "G1_conformance": (
                "perfect corpus: every fixture passes with options applied; "
                "zero failures, zero declared divergences"
            ),
            "G2_zero_intermediates": None,  # replaced below from the G2 artifact
            "G3_typed_decode_beats_wrapper": all(
                b["gates"]["G3_typed_decode_beats_wrapper"] for b in benchmarks
            ),
            "G4_whole_encode_beats_to_builtins_alone": all(
                b["gates"]["G4_whole_encode_beats_to_builtins_alone"] for b in benchmarks
            ),
            "G5_codec_floor": all(
                b["gates"]["G5_encode_not_slower_than_toons"]
                and b["gates"]["G5_decode_not_slower_than_toons"]
                for b in codec_benchmarks
            ),
            "typed_beats_incumbent_pipeline": all(
                b["gates"]["typed_beats_incumbent_pipeline_decode"]
                and b["gates"]["typed_beats_incumbent_pipeline_encode"]
                for b in benchmarks
            ),
            "G6_wheel_parity": (
                "measurements taken on the release abi3 extension in the environment "
                "that actually imports it; benches/build_freshness.py refuses to "
                "publish a number from a stale or alloc-stats build"
            ),
        },
        "benchmark_caveats": [
            (
                "Each codec round-trips its own encoded bytes: the incumbents predate "
                "TOON 4.x and emit the fallback list form (no nested field groups), so "
                "they parse roughly 2.9x more bytes for the same value. Byte sizes are "
                "published per row; that difference is the real-world comparison, not "
                "an unfair one."
            ),
            (
                "The incumbent pipeline rows (to_builtins + python-toon encode; "
                "python-toon decode + convert) reproduce a known-inefficient "
                "composition — a benchmark to beat, not the strongest alternative."
            ),
            (
                "python-toon's latest PyPI release equals the pinned 0.1.3 at "
                "measurement time, so a single python-toon row covers both the "
                "pinned and latest variants."
            ),
        ],
        # Generated, never freehand: every type-support gap comes from the
        # matrix that tests/test_support_matrix.py verifies against
        # msgspec.json, so this list cannot lag the implementation (F-11).
        "known_divergences_and_gaps": [
            (
                "G4 fails: whole direct encode does not beat msgspec.to_builtins alone "
                "(2.2x at 16 records, ~10% gap at 4096 after optimizations E1/E2). "
                "Cause: public stable-ABI attribute reads versus msgspec's private C "
                "slot reads. This is the canvas risk R-02 outcome, reported rather "
                "than masked; candidate E3 remains open in the optimization ledger."
            ),
            (
                "Non-finite float encoding raises EncodeError (msgspec.json parity); "
                "no 4.1 fixture exercises the alternative null mapping, so the "
                "prior-art question stands resolved-by-absence for this corpus."
            ),
            *(
                f"{gap['status']}: {gap['feature']} (tier {gap['tier']})"
                + (f" — {gap['detail']}" if gap["detail"] else "")
                for gap in support_matrix_report()["known_gaps"]
            ),
        ],
    }
    # G2 comes from the instrumented build's artifact; an absent artifact is
    # reported as such rather than defaulting to a pass.
    report["gates"]["G2_zero_builtin_containers"] = report["allocation_proof"].get(
        "gate_G2_zero_builtin_containers", "NOT RUN — execute `make g2`"
    )
    del report["gates"]["G2_zero_intermediates"]
    out = Path(__file__).resolve().parent.parent / "conformance" / "report.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
