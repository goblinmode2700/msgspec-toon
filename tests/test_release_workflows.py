from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
VALIDATE = ROOT / ".github" / "workflows" / "validate.yml"
RELEASE = ROOT / ".github" / "workflows" / "wheels.yml"

QUALIFICATION_COMPONENTS = (
    ("prepare", "QUALIFY_PREPARE"),
    ("locked-sync", "QUALIFY_SYNC"),
    ("build", "QUALIFY_BUILD"),
    ("lint", "CHECK_LINT"),
    ("typecheck", "CHECK_TYPECHECK"),
    ("rust-test", "TEST_RUST"),
    ("pytest", "TEST_PYTHON"),
    ("conformance", "QUALIFY_CONFORMANCE"),
    ("g2", "QUALIFY_G2"),
    ("release-report", "QUALIFY_REPORT"),
    ("evidence-copy", "QUALIFY_COPY_EVIDENCE"),
    ("summary", "QUALIFY_SUMMARY"),
)


def _job_dependencies(text: str) -> dict[str, set[str]]:
    jobs: dict[str, set[str]] = {}
    current: str | None = None
    in_jobs = False
    for line in text.splitlines():
        if line == "jobs:":
            in_jobs = True
            continue
        if not in_jobs:
            continue
        job = re.fullmatch(r"  ([a-z][a-z0-9-]*):", line)
        if job:
            current = job.group(1)
            jobs[current] = set()
            continue
        needs = re.fullmatch(r"    needs: (.+)", line)
        if current is None or needs is None:
            continue
        value = needs.group(1).strip()
        if value.startswith("[") and value.endswith("]"):
            value = value[1:-1]
        jobs[current] = {item.strip() for item in value.split(",")}
    return jobs


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


def test_github_release_commands_have_explicit_repository_context() -> None:
    text = RELEASE.read_text(encoding="utf-8")
    assert "GH_REPO: ${{ github.repository }}" in text


@pytest.mark.parametrize(
    "failed_component", [component for component, _ in QUALIFICATION_COMPONENTS]
)
def test_each_qualification_component_failure_stops_the_pipeline(
    tmp_path: Path, failed_component: str
) -> None:
    log = tmp_path / "components.log"
    probe = tmp_path / "probe.py"
    probe.write_text(
        """import os
import sys
from pathlib import Path

component, log = sys.argv[1:]
with Path(log).open("a", encoding="utf-8") as stream:
    stream.write(component + "\\n")
if component == os.environ["FAIL_COMPONENT"]:
    raise SystemExit(97)
""",
        encoding="utf-8",
    )

    def command(component: str) -> str:
        return " ".join(
            shlex.quote(value) for value in (sys.executable, str(probe), component, str(log))
        )

    env = os.environ.copy()
    env["FAIL_COMPONENT"] = failed_component
    for component, variable in QUALIFICATION_COMPONENTS:
        env[variable] = command(component)

    result = subprocess.run(
        ["make", "--no-print-directory", "qualify"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    ordered = [component for component, _ in QUALIFICATION_COMPONENTS]
    failure_index = ordered.index(failed_component)
    assert log.read_text(encoding="utf-8").splitlines() == ordered[: failure_index + 1]


def test_failed_validation_blocks_every_release_job() -> None:
    text = RELEASE.read_text(encoding="utf-8")
    dependencies = _job_dependencies(text)
    blocked = {"validate"}
    while True:
        newly_blocked = {
            job
            for job, needs in dependencies.items()
            if job not in blocked and needs.intersection(blocked)
        }
        if not newly_blocked:
            break
        blocked.update(newly_blocked)

    assert blocked == set(dependencies)
    assert {"collect", "evidence", "publish", "github-release"} <= blocked
    assert "always()" not in text
