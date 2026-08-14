from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def report_module() -> ModuleType:
    path = ROOT / "scripts" / "release-report.py"
    spec = importlib.util.spec_from_file_location("release_report_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_compatibility_delta_records_support_changes(
    report_module: ModuleType,
) -> None:
    locked = json.loads((ROOT / "conformance" / "efficiency.lock.json").read_text())
    delta = report_module.compatibility_delta(
        report_module.support_matrix_report(), {"payloads": locked["payloads"]}
    )
    assert delta["support_changes"] == [
        {"feature": "Decimal", "before": "unsupported", "after": "supported"},
        {
            "feature": "Encoder(decimal_format=..., uuid_format=...)",
            "before": "unsupported",
            "after": "supported",
        },
        {"feature": "UUID", "before": "unsupported", "after": "supported"},
        {
            "feature": "array_like Structs",
            "before": "unsupported",
            "after": "supported",
        },
        {"feature": "bytes encode projection", "before": None, "after": "supported"},
        {"feature": "date", "before": None, "after": "supported"},
        {"feature": "datetime", "before": "unsupported", "after": "supported"},
        {"feature": "enum members", "before": "unsupported", "after": None},
        {"feature": "fractional and exponent floats", "before": None, "after": "supported"},
        {"feature": "frozenset encode projection", "before": None, "after": "supported"},
        {"feature": "integer Enum", "before": None, "after": "supported"},
        {
            "feature": "integer, string, boolean, and null scalars",
            "before": None,
            "after": "supported",
        },
        {
            "feature": "interaction: array_like + kw_only",
            "before": None,
            "after": "supported",
        },
        {
            "feature": "interaction: array_like + native scalar",
            "before": None,
            "after": "supported",
        },
        {
            "feature": "interaction: array_like + optional",
            "before": None,
            "after": "supported",
        },
        {
            "feature": "interaction: array_like + recursive",
            "before": None,
            "after": "supported",
        },
        {
            "feature": "interaction: array_like + rename",
            "before": None,
            "after": "supported",
        },
        {
            "feature": "interaction: tagged + array_like",
            "before": None,
            "after": "supported",
        },
        {
            "feature": "interaction: tagged + constraint",
            "before": None,
            "after": "supported",
        },
        {
            "feature": "interaction: tagged + kw_only",
            "before": None,
            "after": "supported",
        },
        {
            "feature": "interaction: tagged + native scalar",
            "before": None,
            "after": "supported",
        },
        {
            "feature": "interaction: tagged + recursive",
            "before": None,
            "after": "supported",
        },
        {
            "feature": "object and containers of object",
            "before": None,
            "after": "supported",
        },
        {
            "feature": "recursive Struct types",
            "before": "unsupported",
            "after": "supported",
        },
        {
            "feature": "scalars (int, float, str, bool, null)",
            "before": "supported",
            "after": None,
        },
        {"feature": "set encode projection", "before": None, "after": "supported"},
        {
            "feature": "strict=False scalar coercion",
            "before": "unsupported",
            "after": "supported",
        },
        {"feature": "string Enum", "before": None, "after": "supported"},
        {
            "feature": "tagged unions",
            "before": "unsupported",
            "after": "supported",
        },
        {"feature": "time", "before": None, "after": "supported"},
        {"feature": "timedelta", "before": None, "after": "supported"},
        {
            "feature": "unions of bool, int, float, and str",
            "before": None,
            "after": "supported",
        },
        {
            "feature": "whole floats and negative zero",
            "before": None,
            "after": "format_divergence",
        },
    ]
    assert delta["wire_output_changes_for_shared_locked_payloads"] == []
    report_module.check_changelog_compatibility(delta)


def test_external_evidence_rejects_revision_mismatch(
    report_module: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "qualification.json"
    path.write_text(
        json.dumps({"schema_version": 1, "version": "0.1.0b3", "source_revision": "b" * 40})
    )
    monkeypatch.setenv("QUALIFICATION_TEST_PATH", str(path))
    with pytest.raises(SystemExit, match="does not match"):
        report_module._external_evidence(
            "QUALIFICATION_TEST_PATH", version="0.1.0b3", revision="a" * 40
        )


def test_release_mode_rejects_missing_component_evidence(
    report_module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(report_module, "REQUIRE_RELEASE_EVIDENCE", True)
    monkeypatch.delenv("MISSING_RELEASE_EVIDENCE", raising=False)
    with pytest.raises(SystemExit, match="missing required release evidence"):
        report_module._external_evidence(
            "MISSING_RELEASE_EVIDENCE", version="0.1.0b3", revision="a" * 40
        )


def test_performance_evidence_check_requires_and_validates_all_four_outputs(
    report_module: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = [tmp_path / name for name in ("guard-raw", "guard-r", "report-raw", "report-r")]
    for path in paths:
        path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(report_module, "RELEASE_GUARD_RAW", paths[0])
    monkeypatch.setattr(report_module, "RELEASE_GUARD_RESULT", paths[1])
    monkeypatch.setattr(report_module, "REPORT_PERFORMANCE_RAW", paths[2])
    monkeypatch.setattr(report_module, "REPORT_PERFORMANCE_RESULT", paths[3])
    validated: list[str] = []
    monkeypatch.setattr(report_module, "release_guard", lambda: validated.append("guard"))
    monkeypatch.setattr(report_module, "performance_report", lambda: validated.append("report"))

    report_module.check_performance_evidence()
    assert validated == ["guard", "report"]

    paths[2].unlink()
    with pytest.raises(SystemExit, match="missing release performance evidence"):
        report_module.check_performance_evidence()


def test_release_guard_requires_nested_and_irregular_untyped_shapes(
    report_module: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_path = tmp_path / "ab-guard-raw.json"
    raw_path.write_text(
        json.dumps(
            {
                "family": {"name": "release-guard"},
                "endpoints": [{"id": "untyped-decode@4096"}],
            }
        )
    )
    path = tmp_path / "ab-guard.json"
    path.write_text(
        json.dumps(
            {
                "analysis_schema_version": 1,
                "engine": "R stats",
                "raw_sha256": report_module.file_sha256(raw_path),
                "analyzer_sha256": report_module.file_sha256(ROOT / "benches" / "analyze_ab.R"),
                "family": "release-guard",
                "adjustment": "simultaneous Bonferroni intervals across the declared family",
                "gate_decision": "PASS",
                "endpoints": [{"id": "untyped-decode@4096"}],
            }
        )
    )
    monkeypatch.setattr(report_module, "validate_ab_raw", lambda raw: None)
    monkeypatch.setattr(report_module, "_validate_release_guard_identity", lambda raw: None)
    monkeypatch.setattr(report_module, "REQUIRE_RELEASE_EVIDENCE", True)
    with pytest.raises(SystemExit, match="lacks required untyped shapes"):
        report_module.release_guard(path, raw_path)


def test_release_guard_preserves_each_required_untyped_shape(
    report_module: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_path = tmp_path / "ab-guard-raw.json"
    raw_path.write_text(
        json.dumps(
            {
                "family": {"name": "release-guard"},
                "endpoints": [
                    {"id": metric}
                    for metric in sorted(report_module.REQUIRED_UNTYPED_GUARD_METRICS)
                ],
            }
        )
    )
    path = tmp_path / "ab-guard.json"
    result = {
        "analysis_schema_version": 1,
        "engine": "R stats",
        "raw_sha256": report_module.file_sha256(raw_path),
        "analyzer_sha256": report_module.file_sha256(ROOT / "benches" / "analyze_ab.R"),
        "family": "release-guard",
        "adjustment": "simultaneous Bonferroni intervals across the declared family",
        "gate_decision": "PASS",
        "endpoints": [
            {"id": metric} for metric in sorted(report_module.REQUIRED_UNTYPED_GUARD_METRICS)
        ],
    }
    path.write_text(json.dumps(result))
    monkeypatch.setattr(report_module, "validate_ab_raw", lambda raw: None)
    monkeypatch.setattr(report_module, "_validate_release_guard_identity", lambda raw: None)
    evidence = report_module.release_guard(path, raw_path)
    assert evidence["analysis"] == result
    assert evidence["required_untyped_shape_metrics"] == sorted(
        report_module.REQUIRED_UNTYPED_GUARD_METRICS
    )

    result["gate_decision"] = "INCONCLUSIVE"
    path.write_text(json.dumps(result))
    evidence = report_module.release_guard(path, raw_path)
    assert evidence["analysis"]["gate_decision"] == "INCONCLUSIVE"


def test_release_guard_rejects_an_exploratory_r_decision(
    report_module: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_path = tmp_path / "ab-guard-raw.json"
    raw_path.write_text(
        json.dumps(
            {
                "family": {"name": "release-guard"},
                "endpoints": [
                    {"id": metric}
                    for metric in sorted(report_module.REQUIRED_UNTYPED_GUARD_METRICS)
                ],
            }
        )
    )
    result_path = tmp_path / "ab-guard-r.json"
    result_path.write_text(
        json.dumps(
            {
                "analysis_schema_version": 1,
                "engine": "R stats",
                "raw_sha256": report_module.file_sha256(raw_path),
                "analyzer_sha256": report_module.file_sha256(ROOT / "benches" / "analyze_ab.R"),
                "family": "release-guard",
                "adjustment": "simultaneous Bonferroni intervals across the declared family",
                "gate_decision": "EXPLORATORY",
                "endpoints": [
                    {"id": metric}
                    for metric in sorted(report_module.REQUIRED_UNTYPED_GUARD_METRICS)
                ],
            }
        )
    )
    monkeypatch.setattr(report_module, "validate_ab_raw", lambda raw: None)
    monkeypatch.setattr(report_module, "_validate_release_guard_identity", lambda raw: None)
    with pytest.raises(SystemExit, match="declared R release decision"):
        report_module.release_guard(result_path, raw_path)


def test_release_guard_identity_binds_revision_candidate_and_guard_tag(
    report_module: ModuleType,
) -> None:
    raw = {
        "source_revision": report_module._source_revision(),
        "builds": {"baseline": {"guard_tag": (ROOT / "benches" / "GUARD_TAG").read_text().strip()}},
        "workers": [
            {
                "build": "current",
                "package": {"sha256": report_module._package_sha256()},
                "extension": {"sha256": report_module._extension_sha256()},
            }
        ],
    }
    report_module._validate_release_guard_identity(raw)

    raw["source_revision"] = "0" * 40
    with pytest.raises(ValueError, match="source revision"):
        report_module._validate_release_guard_identity(raw)


def test_absolute_report_identity_rejects_another_candidate_extension(
    report_module: ModuleType,
) -> None:
    raw = {
        "source_revision": report_module._source_revision(),
        "workers": [
            {
                "package": {"sha256": report_module._package_sha256()},
                "extension": {"sha256": "0" * 64},
            }
        ],
    }
    with pytest.raises(ValueError, match="installed candidate extension"):
        report_module._validate_current_benchmark_identity(raw, label="R-owned performance report")

    raw["workers"][0] = {
        "package": {"sha256": "0" * 64},
        "extension": {"sha256": report_module._extension_sha256()},
    }
    with pytest.raises(ValueError, match="installed candidate package"):
        report_module._validate_current_benchmark_identity(raw, label="R-owned performance report")


def test_verified_manifest_rejects_another_version(
    report_module: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "verified.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_revision": "a" * 40,
                "artifacts": [{"filename": "msgspec_toon-0.1.0b2.tar.gz"}],
            }
        )
    )
    monkeypatch.setenv("MSGSPEC_TOON_VERIFIED_MANIFEST", str(path))
    with pytest.raises(SystemExit, match="outside version"):
        report_module._external_evidence(
            "MSGSPEC_TOON_VERIFIED_MANIFEST", version="0.1.0b3", revision="a" * 40
        )
