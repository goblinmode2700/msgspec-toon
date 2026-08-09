from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "release_artifacts.py"
WHEEL_NAME = "msgspec_toon-0.1.0b3-cp313-abi3-macosx_11_0_arm64.whl"
PLATFORM_TAGS = {
    ("linux", "x86_64"): "manylinux_2_17_x86_64.manylinux2014_x86_64",
    ("linux", "aarch64"): "manylinux_2_17_aarch64.manylinux2014_aarch64",
    ("macos", "x86_64"): "macosx_10_12_x86_64",
    ("macos", "aarch64"): "macosx_11_0_arm64",
    ("windows", "x86_64"): "win_amd64",
    ("windows", "aarch64"): "win_arm64",
}


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def test_manifest_records_immutable_artifact_identity(tmp_path: Path) -> None:
    artifact = tmp_path / WHEEL_NAME
    artifact.write_bytes(b"wheel")
    output = tmp_path / "manifest.json"
    _run(
        "manifest",
        "--artifact",
        str(artifact),
        "--kind",
        "wheel",
        "--python-abi",
        "cp313-abi3",
        "--operating-system",
        "macos",
        "--architecture",
        "aarch64",
        "--revision",
        "a" * 40,
        "--output",
        str(output),
    )
    data = json.loads(output.read_text())
    assert data["artifact"] == {
        "filename": WHEEL_NAME,
        "kind": "wheel",
        "sha256": hashlib.sha256(b"wheel").hexdigest(),
        "size": 5,
    }
    assert data["target"] == {
        "python_abi": "cp313-abi3",
        "operating_system": "macos",
        "architecture": "aarch64",
    }


def test_collect_rejects_an_incomplete_verified_set(tmp_path: Path) -> None:
    artifact = tmp_path / WHEEL_NAME
    artifact.write_bytes(b"wheel")
    verified = {
        "schema_version": 1,
        "source_revision": "a" * 40,
        "artifact": {
            "filename": artifact.name,
            "kind": "wheel",
            "sha256": hashlib.sha256(b"wheel").hexdigest(),
            "size": 5,
        },
        "target": {
            "python_abi": "cp313-abi3",
            "operating_system": "macos",
            "architecture": "aarch64",
        },
        "verification": {"status": "passed", "distribution_version": "0.1.0b3"},
    }
    (tmp_path / "example.verified.json").write_text(json.dumps(verified))
    result = _run(
        "collect",
        "--directory",
        str(tmp_path),
        "--output-directory",
        str(tmp_path / "release"),
        "--output-manifest",
        str(tmp_path / "release.json"),
        check=False,
    )
    assert result.returncode != 0
    assert "incomplete verified set" in result.stderr


def test_collect_accepts_only_the_complete_release_matrix(tmp_path: Path) -> None:
    revision = "a" * 40
    for python_abi, python_tag, abi_tag in (
        ("cp313-abi3", "cp313", "abi3"),
        ("cp314t", "cp314", "cp314t"),
    ):
        for (operating_system, architecture), platform_tag in PLATFORM_TAGS.items():
            filename = f"msgspec_toon-0.1.0b3-{python_tag}-{abi_tag}-{platform_tag}.whl"
            artifact = tmp_path / filename
            content = filename.encode()
            artifact.write_bytes(content)
            verified = {
                "schema_version": 1,
                "source_revision": revision,
                "artifact": {
                    "filename": filename,
                    "kind": "wheel",
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size": len(content),
                },
                "target": {
                    "python_abi": python_abi,
                    "operating_system": operating_system,
                    "architecture": architecture,
                },
                "verification": {
                    "status": "passed",
                    "distribution_version": "0.1.0b3",
                },
            }
            (tmp_path / f"{python_abi}-{operating_system}-{architecture}.verified.json").write_text(
                json.dumps(verified)
            )
    sdist = tmp_path / "msgspec_toon-0.1.0b3.tar.gz"
    sdist.write_bytes(b"sdist")
    (tmp_path / "sdist.verified.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_revision": revision,
                "artifact": {
                    "filename": sdist.name,
                    "kind": "sdist",
                    "sha256": hashlib.sha256(b"sdist").hexdigest(),
                    "size": 5,
                },
                "target": {
                    "python_abi": "source",
                    "operating_system": "source",
                    "architecture": "source",
                },
                "verification": {
                    "status": "passed",
                    "distribution_version": "0.1.0b3",
                },
            }
        )
    )

    output_manifest = tmp_path / "release.json"
    _run(
        "collect",
        "--directory",
        str(tmp_path),
        "--output-directory",
        str(tmp_path / "release"),
        "--output-manifest",
        str(output_manifest),
    )
    result = json.loads(output_manifest.read_text())
    assert result["artifact_count"] == 13
    assert all(item["verification"]["status"] == "passed" for item in result["artifacts"])
    assert all(
        item["verification"]["distribution_version"] == "0.1.0b3" for item in result["artifacts"]
    )
    assert len(list((tmp_path / "release").iterdir())) == 13


def test_manifest_rejects_a_target_that_disagrees_with_the_wheel(tmp_path: Path) -> None:
    artifact = tmp_path / WHEEL_NAME
    artifact.write_bytes(b"wheel")
    result = _run(
        "manifest",
        "--artifact",
        str(artifact),
        "--kind",
        "wheel",
        "--python-abi",
        "cp314t",
        "--operating-system",
        "macos",
        "--architecture",
        "aarch64",
        "--revision",
        "a" * 40,
        "--output",
        str(tmp_path / "manifest.json"),
        check=False,
    )
    assert result.returncode != 0
    assert "ABI tags" in result.stderr


@pytest.mark.parametrize("mutation", ["filename", "digest", "size"])
def test_verify_rejects_substituted_artifacts(tmp_path: Path, mutation: str) -> None:
    artifact = tmp_path / WHEEL_NAME
    artifact.write_bytes(b"wheel")
    manifest = tmp_path / "manifest.json"
    _run(
        "manifest",
        "--artifact",
        str(artifact),
        "--kind",
        "wheel",
        "--python-abi",
        "cp313-abi3",
        "--operating-system",
        "macos",
        "--architecture",
        "aarch64",
        "--revision",
        "a" * 40,
        "--output",
        str(manifest),
    )
    data = json.loads(manifest.read_text())
    if mutation == "filename":
        data["artifact"]["filename"] = "other.whl"
    elif mutation == "digest":
        data["artifact"]["sha256"] = "0" * 64
    else:
        data["artifact"]["size"] = 6
    manifest.write_text(json.dumps(data))
    result = _run(
        "verify",
        "--artifact",
        str(artifact),
        "--manifest",
        str(manifest),
        "--output",
        str(tmp_path / "verified.json"),
        check=False,
    )
    assert result.returncode != 0
