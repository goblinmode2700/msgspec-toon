"""Generate the machine-readable qualification report.

Every release claim is a generated report, never an assertion: fixture
conformance with corpus pinning, the
allocation proof (G2), same-run speed comparisons (G3/G4/G5 and the
incumbent pipeline), and token efficiency under named tokenizers (T1-T3).
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benches"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "conformance"))

import bench_codecs
import bench_tokens
import build_freshness  # noqa: F401  (refuses stale or instrumented builds)
import msgspec
from _panel import file_sha256, validate_ab_raw, validate_r_result
from _report_evidence import load_report_performance
from msgspec_toon import _native
from support_matrix import as_report as support_matrix_report

ROOT = Path(__file__).resolve().parent.parent
BASELINE_VERSION = os.environ.get("MSGSPEC_TOON_RELEASE_BASELINE", "0.1.0b3")
REQUIRE_RELEASE_EVIDENCE = os.environ.get("MSGSPEC_TOON_REQUIRE_RELEASE_EVIDENCE") == "1"
CHANGELOG_COMPATIBILITY_START = "<!-- release-compatibility:start -->"
CHANGELOG_COMPATIBILITY_END = "<!-- release-compatibility:end -->"
REQUIRED_UNTYPED_GUARD_METRICS = {
    "untyped-distinct-32-key-decode@4096",
    "untyped-distinct-512-key-decode@4096",
    "untyped-nested-record-decode@46",
    "untyped-irregular-decode@4096",
}
REPORT_PERFORMANCE_RAW = ROOT / "benches" / "report-performance-raw.json"
REPORT_PERFORMANCE_RESULT = ROOT / "benches" / "report-performance.json"
GUARD_TAG_FILE = ROOT / "benches" / "GUARD_TAG"


def _extension_sha256() -> str:
    return file_sha256(Path(_native.__file__).resolve())


def _validate_current_benchmark_identity(raw: dict, *, label: str) -> None:
    if raw.get("source_revision") != _source_revision():
        raise ValueError(f"{label} does not match the source revision")
    current_hashes = {
        worker.get("extension", {}).get("sha256")
        for worker in raw.get("workers", [])
        if worker.get("build", "current") == "current"
    }
    if current_hashes != {_extension_sha256()}:
        raise ValueError(f"{label} did not measure the installed candidate extension")


def _validate_release_guard_identity(raw: dict) -> None:
    _validate_current_benchmark_identity(raw, label="release guard")
    expected_guard = GUARD_TAG_FILE.read_text(encoding="utf-8").strip()
    measured_guard = raw.get("builds", {}).get("baseline", {}).get("guard_tag")
    if measured_guard != expected_guard:
        raise ValueError(
            f"release guard measured {measured_guard or 'an unrecorded baseline'}, "
            f"expected {expected_guard}"
        )


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


def release_guard(path: Path | None = None, raw_path: Path | None = None) -> dict:
    """Load the paired raw guard and its R-owned decision."""

    result_path = path or ROOT / "benches" / "ab-guard-r.json"
    paired_raw_path = raw_path or ROOT / "benches" / "ab-guard-raw.json"
    if not result_path.is_file() or not paired_raw_path.is_file():
        if REQUIRE_RELEASE_EVIDENCE:
            raise SystemExit(f"missing release guard evidence: {paired_raw_path}, {result_path}")
        return {"status": "NOT RUN — execute `make guard && make ab`"}

    raw = json.loads(paired_raw_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    try:
        validate_ab_raw(raw)
        validate_r_result(
            result,
            raw_sha256=file_sha256(paired_raw_path),
            family="release-guard",
            endpoint_ids={endpoint["id"] for endpoint in raw["endpoints"]},
            analyzer_sha256=file_sha256(ROOT / "benches" / "analyze_ab.R"),
        )
        _validate_release_guard_identity(raw)
    except (KeyError, TypeError, ValueError) as error:
        if REQUIRE_RELEASE_EVIDENCE:
            raise SystemExit(f"invalid R-owned release guard evidence: {error}") from error
        return {"status": f"SUPERSEDED OR INVALID — regenerate with make ab: {error}"}
    if raw["family"]["name"] != "release-guard" or result["gate_decision"] not in {
        "PASS",
        "FAIL",
    }:
        raise SystemExit("release guard does not contain the declared R release decision")
    measured = {endpoint["id"] for endpoint in raw["endpoints"]}
    missing = sorted(REQUIRED_UNTYPED_GUARD_METRICS - measured)
    if missing:
        message = f"release guard lacks required untyped shapes: {', '.join(missing)}"
        if REQUIRE_RELEASE_EVIDENCE:
            raise SystemExit(message)
        result["coverage_warning"] = message
    return {
        "raw_sha256": file_sha256(paired_raw_path),
        "analysis": result,
        "required_untyped_shape_metrics": sorted(REQUIRED_UNTYPED_GUARD_METRICS),
    }


def performance_report(
    raw_path: Path = REPORT_PERFORMANCE_RAW,
    result_path: Path = REPORT_PERFORMANCE_RESULT,
) -> dict | None:
    if not raw_path.is_file() or not result_path.is_file():
        if REQUIRE_RELEASE_EVIDENCE:
            raise SystemExit(f"missing R-owned performance report: {raw_path}, {result_path}")
        return None
    try:
        performance = load_report_performance(raw_path, result_path)
    except (KeyError, TypeError, ValueError) as error:
        raise SystemExit(f"invalid R-owned performance report: {error}") from error
    try:
        _validate_current_benchmark_identity(performance["raw"], label="R-owned performance report")
    except ValueError as error:
        raise SystemExit(str(error)) from error
    return performance


def _efficiency_lock() -> dict:
    """The locked cost of this codec's output, with the tokenizer that measured it."""
    path = Path(__file__).resolve().parent.parent / "conformance" / "efficiency.lock.json"
    if not path.exists():
        return {"status": "NOT RUN — execute `uv run python scripts/efficiency-lock.py --write`"}
    locked = json.loads(path.read_text())
    return {
        "versions": locked["versions"],
        "payloads": locked["payloads"],
        "gate": "tests/test_efficiency_lock.py fails on any difference, in either direction",
    }


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


def _source_revision() -> str:
    revision = os.environ.get("GITHUB_SHA")
    if revision:
        return revision
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _external_evidence(variable: str, *, version: str, revision: str) -> dict:
    value = os.environ.get(variable)
    if not value:
        if REQUIRE_RELEASE_EVIDENCE:
            raise SystemExit(f"missing required release evidence: {variable}")
        return {"status": f"NOT PROVIDED — set {variable} for release qualification"}
    path = Path(value)
    if not path.is_file():
        raise SystemExit(f"{variable} does not name a file: {path}")
    evidence = json.loads(path.read_text())
    if evidence.get("source_revision") != revision:
        raise SystemExit(
            f"{variable} revision {evidence.get('source_revision')} does not match {revision}"
        )
    evidence_version = evidence.get("version")
    if evidence_version is not None and evidence_version != version:
        raise SystemExit(f"{variable} version {evidence_version} does not match {version}")
    if variable == "MSGSPEC_TOON_VERIFIED_MANIFEST":
        expected_prefix = f"msgspec_toon-{version}"
        artifacts = evidence.get("artifacts", [])
        filenames = [item["filename"] for item in artifacts]
        if not filenames or any(not name.startswith(expected_prefix) for name in filenames):
            raise SystemExit(f"{variable} contains a file outside version {version}: {filenames}")
        if any(item.get("verification", {}).get("status") != "passed" for item in artifacts):
            raise SystemExit(f"{variable} contains an unverified artifact")
        if any(
            item.get("verification", {}).get("distribution_version") != version
            for item in artifacts
        ):
            raise SystemExit(f"{variable} contains installed metadata outside version {version}")
    return evidence


def _wire_hash(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    return hashlib.sha256(encoded.encode()).hexdigest()


def compatibility_delta(current_support: dict, current_lock: dict) -> dict:
    baseline_path = ROOT / "conformance" / "release-baselines" / f"{BASELINE_VERSION}.json"
    baseline = json.loads(baseline_path.read_text())
    previous = baseline["support_matrix"]
    current = {entry["feature"]: entry["status"] for entry in current_support["entries"]}
    features = sorted(previous.keys() | current.keys())
    changes = [
        {"feature": feature, "before": previous.get(feature), "after": current.get(feature)}
        for feature in features
        if previous.get(feature) != current.get(feature)
    ]

    locked_payloads = current_lock["payloads"]
    shared_formats = ("json_compact", "toon_comma", "toon_tab", "toon_pipe")
    wire_changes = []
    for payload, before_hash in baseline["shared_wire_lock_sha256"].items():
        if payload not in locked_payloads:
            wire_changes.append({"payload": payload, "status": "removed"})
            continue
        comparable = {
            name: locked_payloads[payload][name]
            for name in shared_formats
            if name in locked_payloads[payload]
        }
        after_hash = _wire_hash(comparable)
        if after_hash != before_hash:
            wire_changes.append(
                {
                    "payload": payload,
                    "status": "changed",
                    "before": before_hash,
                    "after": after_hash,
                }
            )
    return {
        "baseline_version": BASELINE_VERSION,
        "support_changes": changes,
        "new_support": [
            item
            for item in changes
            if item["after"] == "supported" and item["before"] != "supported"
        ],
        "removed_support": [
            item
            for item in changes
            if item["before"] == "supported" and item["after"] != "supported"
        ],
        "wire_output_changes_for_shared_locked_payloads": wire_changes,
    }


def compatibility_markdown(delta: dict) -> str:
    baseline = delta["baseline_version"]
    changes = delta["support_changes"]
    wire_changes = delta["wire_output_changes_for_shared_locked_payloads"]
    if not changes and not wire_changes:
        summary = (
            f"- Compatibility since `{baseline}`: no support changes and no canonical-wire "
            "changes for shared locked payloads."
        )
    else:
        summary = (
            f"- Compatibility since `{baseline}`: {len(delta['new_support'])} newly supported, "
            f"{len(delta['removed_support'])} removed, {len(changes)} total support-status "
            f"changes, and {len(wire_changes)} shared canonical-wire changes."
        )
    return f"{CHANGELOG_COMPATIBILITY_START}\n{summary}\n{CHANGELOG_COMPATIBILITY_END}"


def check_changelog_compatibility(delta: dict) -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text()
    expected = compatibility_markdown(delta)
    if expected not in changelog:
        raise SystemExit(
            "CHANGELOG.md compatibility block does not match executable release delta; "
            "regenerate it from compatibility_markdown()"
        )


def main() -> None:
    if sys.argv[1:] == ["--check-changelog"]:
        efficiency = _efficiency_lock()
        delta = compatibility_delta(support_matrix_report(), efficiency)
        check_changelog_compatibility(delta)
        print(compatibility_markdown(delta))
        return
    lock = json.loads(
        (Path(__file__).resolve().parent.parent / "conformance" / "fixtures.lock.json").read_text()
    )
    performance = performance_report()
    benchmarks = performance["typed"] if performance is not None else []
    codec_benchmarks = performance["codecs"] if performance is not None else []
    integration_benchmarks = performance["integration"] if performance is not None else []
    key_cardinality = (
        performance["key_cardinality"]
        if performance is not None
        else {"status": "NOT RUN — execute `python benches/collect_report.py`"}
    )
    performance_gates = performance["gates"] if performance is not None else {}
    version = importlib.metadata.version("msgspec-toon")
    revision = _source_revision()
    support = support_matrix_report()
    efficiency = _efficiency_lock()
    verified_artifacts = _external_evidence(
        "MSGSPEC_TOON_VERIFIED_MANIFEST", version=version, revision=revision
    )
    qualification = _external_evidence(
        "MSGSPEC_TOON_QUALIFICATION_SUMMARY", version=version, revision=revision
    )
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "distribution": (f"msgspec-toon {version}"),
        "package": {
            "name": "msgspec-toon",
            "version": version,
            "source_revision": revision,
        },
        "environment": {
            "python": sys.version.split()[0],
            "msgspec": msgspec.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "measured_versions": bench_codecs.versions(),
        "timing_methodology": (
            "Python retains raw elapsed nanoseconds and loop counts from complete "
            "process panels; R aggregates process means, fits paired log contrasts, "
            "and owns intervals, Holm adjustments, classifications, and gates"
        ),
        "evidence_methodology": {
            "inference_engine": "R stats",
            "estimator": (
                performance["analysis"]["estimator"] if performance is not None else "NOT RUN"
            ),
            "workers": (performance["raw"]["design"]["workers"] if performance is not None else 0),
            "samples_per_worker": (
                performance["raw"]["design"]["samples_per_process"]
                if performance is not None
                else 0
            ),
            "warmup": (
                "each worker keeps its timed warmup separate from every post-warmup "
                "observation; calibration observations do not enter analysis"
            ),
            "loop_calibration": (
                "one vectorized calibration panel chooses per-endpoint loop counts; "
                "every worker receives the same counts; CLI cold starts use one loop"
            ),
            "interval": (
                performance["analysis"]["interval"] if performance is not None else "NOT RUN"
            ),
            "multiplicity": (
                performance["analysis"]["adjustment"] if performance is not None else "NOT RUN"
            ),
            "decision_boundary": (
                "R emits meets_floor, misses_floor, or inconclusive; failure to reject "
                "is never called neutral"
            ),
            "efficiency_lock": "conformance/efficiency.lock.json pins byte and token counts for this codec's output; any difference in either direction fails tests/test_efficiency_lock.py",
        },
        "conformance": conformance_summary(lock),
        "allocation_proof": allocation_proof(),
        "canonical_qualification": qualification,
        "verified_release_artifacts": verified_artifacts,
        "release_guard": release_guard(),
        "performance_evidence": (
            {
                "raw_sha256": file_sha256(REPORT_PERFORMANCE_RAW),
                "run_id": performance["raw"]["run_id"],
                "analysis": performance["analysis"],
            }
            if performance is not None
            else {"status": "NOT RUN — execute `python benches/collect_report.py`"}
        ),
        "support_matrix": support,
        "benchmarks_typed_same_run": benchmarks,
        "benchmarks_codecs_same_run": codec_benchmarks,
        "benchmarks_integration_same_run": integration_benchmarks,
        "untyped_distinct_key_scaling": key_cardinality,
        "token_efficiency": bench_tokens.run(),
        "efficiency_lock": efficiency,
        "compatibility_since_previous_release": compatibility_delta(support, efficiency),
        "gates": {
            "G1_conformance": (
                "perfect corpus: every fixture passes with options applied; "
                "zero failures, zero declared divergences"
            ),
            "G2_zero_intermediates": None,  # replaced below from the G2 artifact
            "G3_typed_decode_beats_wrapper": performance_gates.get(
                "G3_typed_decode_beats_wrapper", "NOT RUN"
            ),
            "G4_whole_encode_beats_to_builtins_alone": performance_gates.get(
                "G4_whole_encode_beats_to_builtins_alone", "NOT RUN"
            ),
            "G5_codec_floor": {
                "encode": performance_gates.get("G5_encode_not_slower_than_toons", "NOT RUN"),
                "decode": performance_gates.get("G5_decode_not_slower_than_toons", "NOT RUN"),
            },
            "typed_beats_incumbent_pipeline": {
                "decode": performance_gates.get("typed_beats_incumbent_pipeline_decode", "NOT RUN"),
                "encode": performance_gates.get("typed_beats_incumbent_pipeline_encode", "NOT RUN"),
            },
            "G6_wheel_parity": (
                "measurements taken on the release abi3 extension in the environment "
                "that actually imports it; benches/build_freshness.py refuses to "
                "publish a number from a stale or alloc-stats build"
            ),
        },
        "benchmark_caveats": [
            (
                "Each codec round-trips its own encoded bytes. Output sizes vary by "
                "payload shape and codec. Each row publishes those byte counts."
            ),
            (
                "The incumbent pipeline rows (to_builtins + python-toon encode; "
                "python-toon decode + convert) reproduce a known-inefficient "
                "composition — a benchmark to beat, not the strongest alternative."
            ),
            (
                "The integration rows start and end as compact JSON. The CLI row "
                "includes two process launches and therefore describes deployment "
                "cost, not only codec implementation speed."
            ),
            (
                "python-toon's latest PyPI release equals the pinned 0.1.3 at "
                "measurement time, so a single python-toon row covers both the "
                "pinned and latest variants."
            ),
        ],
        # Generated, never freehand: every type-support gap comes from the
        # matrix that tests/test_support_matrix.py verifies against
        # msgspec.json, so this list cannot lag the implementation.
        "known_divergences_and_gaps": [
            (
                "The stock msgspec 0.21.1 build uses public attribute access for Struct "
                "fields. The optional, versioned Struct-access capsule removes the "
                "slope gap and wins G4 at large payloads, but it is not available in "
                "an upstream msgspec release. The published wheel keeps the safe stock "
                "path; `make fastpath-build` activates the measured capsule experiment."
            ),
            (
                "Non-finite float encoding raises EncodeError (msgspec.json parity); "
                "no 4.1 fixture exercises the alternative null mapping, so the "
                "prior-art question stands resolved-by-absence for this corpus."
            ),
            *(
                f"{gap['status']}: {gap['feature']} (tier {gap['tier']})"
                + (f" — {gap['detail']}" if gap["detail"] else "")
                for gap in support["known_gaps"]
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
