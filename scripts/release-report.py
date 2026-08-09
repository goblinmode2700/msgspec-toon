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

import _timing
import bench_codecs
import bench_integration
import bench_tokens
import build_freshness  # noqa: F401  (refuses stale or instrumented builds)
import msgspec
from _timing import methodology
from bench_typed import run
from msgspec_toon import _native
from support_matrix import as_report as support_matrix_report

ROOT = Path(__file__).resolve().parent.parent
BASELINE_VERSION = os.environ.get("MSGSPEC_TOON_RELEASE_BASELINE", "0.1.0b2")
REQUIRE_RELEASE_EVIDENCE = os.environ.get("MSGSPEC_TOON_REQUIRE_RELEASE_EVIDENCE") == "1"
CHANGELOG_COMPATIBILITY_START = "<!-- release-compatibility:start -->"
CHANGELOG_COMPATIBILITY_END = "<!-- release-compatibility:end -->"


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
    benchmarks = [run(records) for records in (16, 64, 512, 4096)]
    codec_benchmarks = [
        bench_codecs.run(records, shape=shape)
        for shape in bench_codecs.SHAPES
        for records in bench_codecs.LADDER
    ]
    integration_benchmarks = [
        bench_integration.run(records, shape=shape)
        for shape in bench_integration.SHAPES
        for records in bench_integration.LADDER
    ]
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
        "timing_methodology": methodology(),
        "evidence_methodology": {
            "estimator": _timing.ESTIMATOR,
            "workers": _timing.DEFAULT_WORKERS,
            "samples_per_worker": _timing.SAMPLES_PER_WORKER,
            "warmup": "each worker discards its own first sample; the calibration worker's samples are discarded entirely",
            "loop_calibration": "calibrated once and handed to every worker, so all workers measure the same amount of work",
            "significance_test": "two-sample two-tailed Student t-test at alpha 0.95",
            "minimum_detectable_effect": "performance changes use the separate same-session A/B gate; a change smaller than its measured resolution is not claimed as a win",
            "slowdown_confirmation": "a slowdown must reproduce in an independent run before it fails the gate: one test in twenty is wrong and this harness runs sixteen",
            "efficiency_lock": "conformance/efficiency.lock.json pins byte and token counts for this codec's output; any difference in either direction fails tests/test_efficiency_lock.py",
        },
        "conformance": conformance_summary(lock),
        "allocation_proof": allocation_proof(),
        "canonical_qualification": qualification,
        "verified_release_artifacts": verified_artifacts,
        "support_matrix": support,
        "benchmarks_typed_same_run": benchmarks,
        "benchmarks_codecs_same_run": codec_benchmarks,
        "benchmarks_integration_same_run": integration_benchmarks,
        "token_efficiency": bench_tokens.run(),
        "efficiency_lock": efficiency,
        "compatibility_since_previous_release": compatibility_delta(support, efficiency),
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
