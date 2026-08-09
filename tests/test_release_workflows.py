from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VALIDATE = ROOT / ".github" / "workflows" / "validate.yml"
RELEASE = ROOT / ".github" / "workflows" / "wheels.yml"


def test_validation_is_reusable_and_canonical() -> None:
    text = VALIDATE.read_text()
    assert "workflow_call:" in text
    assert "pull_request:" in text
    assert "branches: [main]" in text
    assert "make qualify" in text


def test_publication_depends_on_verified_artifacts_and_canonical_validation() -> None:
    text = RELEASE.read_text()
    assert "uses: ./.github/workflows/validate.yml" in text
    assert "needs: [collect, evidence]" in text
    assert "verified-release" in text
    assert "release_artifacts.py collect" in text
    assert "PYPI_API_KEY" not in text
    assert "UV_PUBLISH_TOKEN" not in text


def test_trusted_publishing_identity_is_job_scoped() -> None:
    text = RELEASE.read_text()
    assert "environment: pypi" in text
    assert "id-token: write" in text
    assert "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33" in text
    assert text.count("id-token: write") == 1
