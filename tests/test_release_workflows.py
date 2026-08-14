from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

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
RELEASE_PERFORMANCE_COMPONENTS = (
    ("wheel-identity", "RELEASE_PERF_VERIFY"),
    ("guard", "RELEASE_PERF_GUARD"),
    ("paired-r-guard", "RELEASE_PERF_AB"),
    ("absolute-r-report", "RELEASE_PERF_REPORT"),
    ("evidence-contract", "RELEASE_PERF_CHECK"),
)

_YAML_BOOLEAN_TAG = "tag:yaml.org,2002:bool"


class _WorkflowLoader(yaml.SafeLoader):
    pass


_WorkflowLoader.yaml_implicit_resolvers = {
    first: [(tag, pattern) for tag, pattern in resolvers if tag != _YAML_BOOLEAN_TAG]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_WorkflowLoader.add_implicit_resolver(
    _YAML_BOOLEAN_TAG,
    re.compile(r"^(?:true|false)$", re.IGNORECASE),
    list("tTfF"),
)


def _workflow(path: Path) -> dict[str, Any]:
    parsed = yaml.load(path.read_text(encoding="utf-8"), Loader=_WorkflowLoader)
    assert isinstance(parsed, dict)
    assert isinstance(parsed.get("jobs"), dict)
    return parsed


def _steps(workflow: dict[str, Any], job: str) -> dict[str, dict[str, Any]]:
    sequence = workflow["jobs"][job]["steps"]
    named = {step["name"]: step for step in sequence if "name" in step}
    assert len(named) == len([step for step in sequence if "name" in step])
    return named


def _needs(job: dict[str, Any]) -> set[str]:
    value = job.get("needs", [])
    return {value} if isinstance(value, str) else set(value)


def test_validation_is_reusable_and_canonical() -> None:
    workflow = _workflow(VALIDATE)
    triggers = workflow["on"]
    steps = _steps(workflow, "qualification")
    assert {"workflow_call", "pull_request"} <= set(triggers)
    assert triggers["push"]["branches"] == ["main"]
    assert steps["Run canonical qualification"]["run"] == "make qualify"
    assert steps["Set up R inference runtime"]["uses"].startswith("r-lib/actions/setup-r@")


def test_publication_depends_on_verified_artifacts_and_canonical_validation() -> None:
    workflow = _workflow(RELEASE)
    jobs = workflow["jobs"]
    assert jobs["validate"]["uses"] == "./.github/workflows/validate.yml"
    assert _needs(jobs["publish"]) == {"collect", "evidence"}
    collect_steps = _steps(workflow, "collect")
    assert collect_steps["Upload verified release set"]["with"]["name"] == "verified-release"
    publish_steps = _steps(workflow, "publish")
    assert publish_steps["Download verified release set"]["with"]["name"] == "verified-release"
    env_mappings = [
        mapping
        for mapping in (
            workflow.get("env", {}),
            *(job.get("env", {}) for job in jobs.values()),
            *(step.get("env", {}) for job in jobs.values() for step in job.get("steps", [])),
        )
        if isinstance(mapping, dict)
    ]
    assert all("PYPI_API_KEY" not in mapping for mapping in env_mappings)
    assert all("UV_PUBLISH_TOKEN" not in mapping for mapping in env_mappings)


def test_trusted_publishing_identity_is_job_scoped() -> None:
    workflow = _workflow(RELEASE)
    publish = workflow["jobs"]["publish"]
    assert publish["environment"] == "pypi"
    assert publish["permissions"] == {"id-token": "write"}
    publish_steps = _steps(workflow, "publish")
    assert publish_steps["Publish package distributions with attestations"]["uses"] == (
        "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33"
    )
    assert all(
        job == "publish" or details.get("permissions", {}).get("id-token") != "write"
        for job, details in workflow["jobs"].items()
    )


def test_github_release_commands_have_explicit_repository_context() -> None:
    steps = _steps(_workflow(RELEASE), "github-release")
    assert steps["Attach evidence to the GitHub release"]["env"]["GH_REPO"] == (
        "${{ github.repository }}"
    )


def test_github_release_is_created_as_a_prerelease() -> None:
    steps = _steps(_workflow(RELEASE), "github-release")
    commands = [
        shlex.split(line.removesuffix(" || \\"))
        for line in steps["Attach evidence to the GitHub release"]["run"].splitlines()
        if line.strip().startswith("gh release create")
    ]
    assert commands == [
        [
            "gh",
            "release",
            "create",
            "$GITHUB_REF_NAME",
            "--verify-tag",
            "--generate-notes",
            "--prerelease",
        ]
    ]


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


@pytest.mark.parametrize(
    "failed_component", [component for component, _ in RELEASE_PERFORMANCE_COMPONENTS]
)
def test_each_release_performance_component_failure_stops_the_pipeline(
    tmp_path: Path, failed_component: str
) -> None:
    log = tmp_path / "release-performance.log"
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
    for component, variable in RELEASE_PERFORMANCE_COMPONENTS:
        env[variable] = command(component)

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            f"RELEASE_BENCH_PYTHON={sys.executable}",
            "release-performance",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    ordered = [component for component, _ in RELEASE_PERFORMANCE_COMPONENTS]
    failure_index = ordered.index(failed_component)
    assert log.read_text(encoding="utf-8").splitlines() == ordered[: failure_index + 1]


def test_release_performance_executes_identity_collection_and_contract_checks(
    tmp_path: Path,
) -> None:
    log = tmp_path / "release-performance.log"
    probe = tmp_path / "probe.py"
    probe.write_text(
        """import sys
from pathlib import Path

component, log = sys.argv[1:]
with Path(log).open("a", encoding="utf-8") as stream:
    stream.write(component + "\\n")
""",
        encoding="utf-8",
    )
    env = os.environ.copy()
    for component, variable in RELEASE_PERFORMANCE_COMPONENTS:
        env[variable] = " ".join(
            shlex.quote(value) for value in (sys.executable, str(probe), component, str(log))
        )

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            f"RELEASE_BENCH_PYTHON={sys.executable}",
            "release-performance",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        component for component, _ in RELEASE_PERFORMANCE_COMPONENTS
    ]


def test_release_evidence_executes_batched_r_pipeline_on_verified_wheel() -> None:
    workflow = _workflow(RELEASE)
    evidence = _steps(workflow, "evidence")
    assert evidence["Run R-owned release performance evidence"]["run"] == (
        "make release-performance"
    )
    assert evidence["Generate machine-readable release report"]["run"] == (
        ".venv-release/bin/python -I scripts/release-report.py"
    )
    assert evidence["Set up R inference runtime"]["uses"].startswith("r-lib/actions/setup-r@")
    verify_r = _steps(workflow, "verify-wheels")["Set up R inference runtime"]
    assert verify_r["if"] == "matrix.platform.full_test && matrix.python.label == 'abi3'"
    assert verify_r["uses"].startswith("r-lib/actions/setup-r@")
    uploaded = set(evidence["Upload release evidence"]["with"]["path"].splitlines())
    assert {
        "benches/ab-guard-raw.json",
        "benches/ab-guard-r.json",
        "benches/report-performance-raw.json",
        "benches/report-performance.json",
        "release/benchmark-wheel.verified.json",
    } <= uploaded


def test_failed_validation_blocks_every_release_job() -> None:
    workflow = _workflow(RELEASE)
    dependencies = {job: _needs(details) for job, details in workflow["jobs"].items()}
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
    assert all(details.get("if") != "${{ always() }}" for details in workflow["jobs"].values())
