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


def test_current_compatibility_delta_records_native_scalar_support(
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
        {"feature": "date", "before": None, "after": "supported"},
        {"feature": "datetime", "before": "unsupported", "after": "supported"},
        {"feature": "enum members", "before": "unsupported", "after": None},
        {"feature": "fractional and exponent floats", "before": None, "after": "supported"},
        {"feature": "integer Enum", "before": None, "after": "supported"},
        {
            "feature": "integer, string, boolean, and null scalars",
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
