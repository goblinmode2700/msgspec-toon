"""Create and verify immutable release-artifact manifests.

This is repository-specific glue around GitHub artifact promotion. It does not
build, install, test, or publish distributions. Those jobs stay separate so the
file that reaches PyPI is byte-for-byte the file tested on its target runner.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib.metadata
import json
import platform
import shutil
import sys
import sysconfig
import zipfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
EXPECTED_WHEELS = 12
EXPECTED_SDISTS = 1
PLATFORMS = {
    ("linux", "x86_64"),
    ("linux", "aarch64"),
    ("macos", "x86_64"),
    ("macos", "aarch64"),
    ("windows", "x86_64"),
    ("windows", "aarch64"),
}
PYTHON_ABIS = {"cp313-abi3", "cp314t"}
EXPECTED_TARGETS = {
    ("wheel", abi, operating_system, architecture)
    for abi in PYTHON_ABIS
    for operating_system, architecture in PLATFORMS
} | {("sdist", "source", "source", "source")}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if data.get("schema_version") != SCHEMA_VERSION:
        raise SystemExit(f"unsupported manifest schema in {path}")
    return data


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _wheel_tags(filename: str) -> tuple[str, str, str]:
    if not filename.endswith(".whl"):
        raise SystemExit(f"wheel artifact has a non-wheel filename: {filename}")
    parts = filename.removesuffix(".whl").split("-")
    if len(parts) < 5:
        raise SystemExit(f"invalid wheel filename: {filename}")
    return parts[-3], parts[-2], parts[-1]


def _artifact_version(filename: str) -> str:
    prefix = "msgspec_toon-"
    if not filename.startswith(prefix):
        raise SystemExit(f"unexpected distribution filename: {filename}")
    suffix = filename.removeprefix(prefix)
    if filename.endswith(".whl"):
        return suffix.split("-", 1)[0]
    if filename.endswith(".tar.gz"):
        return suffix.removesuffix(".tar.gz")
    raise SystemExit(f"unsupported distribution filename: {filename}")


def _validate_declared_target(artifact: dict[str, Any], target: dict[str, str]) -> None:
    identity = (
        artifact["kind"],
        target["python_abi"],
        target["operating_system"],
        target["architecture"],
    )
    if identity not in EXPECTED_TARGETS:
        raise SystemExit(f"unexpected release target identity: {identity}")
    if artifact["kind"] == "sdist":
        if not artifact["filename"].endswith(".tar.gz"):
            raise SystemExit(f"sdist artifact has an invalid filename: {artifact['filename']}")
        return

    python_tag, abi_tag, platform_tag = _wheel_tags(artifact["filename"])
    expected_python, expected_abi = {
        "cp313-abi3": ("cp313", "abi3"),
        "cp314t": ("cp314", "cp314t"),
    }[target["python_abi"]]
    if (python_tag, abi_tag) != (expected_python, expected_abi):
        raise SystemExit(
            f"wheel ABI tags {(python_tag, abi_tag)} do not match {target['python_abi']}"
        )
    os_marker = {"linux": "manylinux", "macos": "macosx", "windows": "win_"}[
        target["operating_system"]
    ]
    arch_marker = {
        ("linux", "x86_64"): "x86_64",
        ("linux", "aarch64"): "aarch64",
        ("macos", "x86_64"): "x86_64",
        ("macos", "aarch64"): "arm64",
        ("windows", "x86_64"): "amd64",
        ("windows", "aarch64"): "arm64",
    }[(target["operating_system"], target["architecture"])]
    if os_marker not in platform_tag or arch_marker not in platform_tag:
        raise SystemExit(
            f"wheel platform tag {platform_tag} does not match "
            f"{target['operating_system']}/{target['architecture']}"
        )


def _runtime_target() -> tuple[str, str]:
    operating_system = {"linux": "linux", "darwin": "macos", "win32": "windows"}.get(sys.platform)
    if operating_system is None:
        raise SystemExit(f"unsupported verification operating system: {sys.platform}")
    machine = platform.machine().lower()
    architecture = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "aarch64": "aarch64",
        "arm64": "aarch64",
    }.get(machine)
    if architecture is None:
        raise SystemExit(f"unsupported verification architecture: {machine}")
    return operating_system, architecture


def _validate_runtime_target(target: dict[str, str]) -> None:
    if target["python_abi"] == "source":
        return
    runtime_os, runtime_arch = _runtime_target()
    declared = (target["operating_system"], target["architecture"])
    if (runtime_os, runtime_arch) != declared:
        raise SystemExit(
            f"verification runner {(runtime_os, runtime_arch)} does not match target {declared}"
        )
    version = sys.version_info[:2]
    gil_disabled = bool(sysconfig.get_config_var("Py_GIL_DISABLED"))
    if target["python_abi"] == "cp313-abi3" and version != (3, 13):
        raise SystemExit(f"cp313-abi3 verification requires Python 3.13, got {version}")
    if target["python_abi"] == "cp314t" and (version != (3, 14) or not gil_disabled):
        raise SystemExit(
            "cp314t verification requires free-threaded Python 3.14; "
            f"got version={version}, gil_disabled={gil_disabled}"
        )


def _verify_installed_files(artifact: Path, distribution: importlib.metadata.Distribution) -> None:
    if not artifact.name.endswith(".whl"):
        return
    prefix = Path(sys.prefix).resolve()
    verified_files = 0
    verified_native = False
    with zipfile.ZipFile(artifact) as wheel:
        record_names = [name for name in wheel.namelist() if name.endswith(".dist-info/RECORD")]
        if len(record_names) != 1:
            raise SystemExit(f"wheel must contain one RECORD file: {artifact.name}")
        rows = csv.reader(wheel.read(record_names[0]).decode("utf-8").splitlines())
        for relative, encoded_digest, encoded_size in rows:
            if not encoded_digest:
                continue
            algorithm, separator, expected_digest = encoded_digest.partition("=")
            if algorithm != "sha256" or not separator:
                raise SystemExit(f"unsupported RECORD digest for {relative}: {encoded_digest}")
            installed = Path(distribution.locate_file(relative)).resolve()
            if not installed.is_relative_to(prefix) or not installed.is_file():
                raise SystemExit(
                    f"wheel file is not installed under the benchmark prefix: {relative}"
                )
            content = installed.read_bytes()
            actual_digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=")
            if actual_digest.decode("ascii") != expected_digest:
                raise SystemExit(f"installed file differs from verified wheel: {relative}")
            if encoded_size and len(content) != int(encoded_size):
                raise SystemExit(f"installed file size differs from verified wheel: {relative}")
            verified_files += 1
            normalized_relative = relative.replace("\\", "/")
            verified_native |= normalized_relative.startswith("msgspec_toon/_native")
    if verified_files == 0 or not verified_native:
        raise SystemExit("verified wheel RECORD does not cover the native extension")


def _verify_installed_artifact(
    artifact: Path, *, expected_version: str
) -> tuple[Path, Path, dict[str, Any]]:
    distribution = importlib.metadata.distribution("msgspec-toon")
    installed_version = distribution.version
    if installed_version != expected_version:
        raise SystemExit(
            f"installed distribution version {installed_version} does not match {expected_version}"
        )
    _verify_installed_files(artifact, distribution)

    import msgspec_toon
    from msgspec_toon import _native

    package_path = Path(msgspec_toon.__file__).resolve()
    native_path = Path(_native.__file__).resolve()
    prefix = Path(sys.prefix).resolve()
    if not package_path.is_relative_to(prefix) or not native_path.is_relative_to(prefix):
        raise SystemExit(
            "installed-artifact verification imported outside the clean environment: "
            f"package={package_path}, native={native_path}, prefix={prefix}"
        )
    wire = msgspec_toon.encode({"x": 1, "items": [1, 2]})
    if msgspec_toon.decode(wire) != {"x": 1, "items": [1, 2]}:
        raise SystemExit("representative installed-artifact round trip failed")
    return (
        package_path,
        native_path,
        {
            "status": "passed",
            "distribution_version": installed_version,
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "gil_enabled": getattr(sys, "_is_gil_enabled", lambda: True)(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "package_path": str(package_path),
            "native_path": str(native_path),
        },
    )


def manifest(args: argparse.Namespace) -> None:
    artifact = args.artifact.resolve()
    if not artifact.is_file():
        raise SystemExit(f"artifact does not exist: {artifact}")
    artifact_data = {
        "filename": artifact.name,
        "kind": args.kind,
        "sha256": _sha256(artifact),
        "size": artifact.stat().st_size,
    }
    target = {
        "python_abi": args.python_abi,
        "operating_system": args.operating_system,
        "architecture": args.architecture,
    }
    _validate_declared_target(artifact_data, target)
    _write(
        args.output,
        {
            "schema_version": SCHEMA_VERSION,
            "artifact": artifact_data,
            "target": target,
            "source_revision": args.revision,
        },
    )


def verify(args: argparse.Namespace) -> None:
    manifest_data = _read(args.manifest)
    artifact = args.artifact.resolve()
    expected = manifest_data["artifact"]
    target = manifest_data["target"]
    _validate_declared_target(expected, target)
    if artifact.name != expected["filename"]:
        raise SystemExit(f"filename mismatch: {artifact.name} != {expected['filename']}")
    digest = _sha256(artifact)
    if digest != expected["sha256"]:
        raise SystemExit(f"digest mismatch for {artifact.name}")
    if artifact.stat().st_size != expected["size"]:
        raise SystemExit(f"size mismatch for {artifact.name}")
    _validate_runtime_target(target)
    _, _, verification = _verify_installed_artifact(
        artifact, expected_version=_artifact_version(artifact.name)
    )

    _write(
        args.output,
        {
            **manifest_data,
            "verification": verification,
        },
    )


def verify_release_wheel(args: argparse.Namespace) -> None:
    manifest_data = _read(args.manifest)
    runtime_os, runtime_arch = _runtime_target()
    matches = [
        item
        for item in manifest_data.get("artifacts", [])
        if item.get("kind") == "wheel"
        and item.get("target")
        == {
            "python_abi": args.python_abi,
            "operating_system": runtime_os,
            "architecture": runtime_arch,
        }
    ]
    if len(matches) != 1:
        raise SystemExit(
            "verified release must contain exactly one benchmark wheel for "
            f"{args.python_abi}/{runtime_os}/{runtime_arch}; found {len(matches)}"
        )
    expected = matches[0]
    target = expected["target"]
    _validate_declared_target(expected, target)
    source_verification = expected.get("verification", {})
    expected_version = _artifact_version(expected["filename"])
    if source_verification.get("status") != "passed":
        raise SystemExit(f"benchmark wheel is not verified: {expected['filename']}")
    if source_verification.get("distribution_version") != expected_version:
        raise SystemExit(
            f"benchmark wheel verification has a different version: {expected['filename']}"
        )
    artifact = args.directory.resolve() / expected["filename"]
    if not artifact.is_file():
        raise SystemExit(f"verified benchmark wheel does not exist: {artifact}")
    if _sha256(artifact) != expected["sha256"]:
        raise SystemExit(f"verified benchmark wheel digest mismatch: {artifact.name}")
    if artifact.stat().st_size != expected["size"]:
        raise SystemExit(f"verified benchmark wheel size mismatch: {artifact.name}")
    _validate_runtime_target(target)
    _, _, verification = _verify_installed_artifact(artifact, expected_version=expected_version)
    _write(
        args.output,
        {
            "schema_version": SCHEMA_VERSION,
            "source_revision": manifest_data["source_revision"],
            "artifact": {key: expected[key] for key in ("filename", "kind", "sha256", "size")},
            "target": target,
            "source_verification": source_verification,
            "benchmark_verification": verification,
        },
    )


def collect(args: argparse.Namespace) -> None:
    manifests = [_read(path) for path in sorted(args.directory.rglob("*.verified.json"))]
    if not manifests:
        raise SystemExit("no verified manifests found")

    revisions = {item["source_revision"] for item in manifests}
    if len(revisions) != 1:
        raise SystemExit(f"verified artifacts span source revisions: {sorted(revisions)}")

    identities: set[tuple[str, str, str, str]] = set()
    wheels = 0
    sdists = 0
    versions: set[str] = set()
    output_files: list[dict[str, Any]] = []
    args.output_directory.mkdir(parents=True, exist_ok=True)
    for item in manifests:
        verification = item.get("verification", {})
        if verification.get("status") != "passed":
            raise SystemExit(f"artifact is not verified: {item['artifact']['filename']}")
        artifact_info = item["artifact"]
        target = item["target"]
        _validate_declared_target(artifact_info, target)
        filename_version = _artifact_version(artifact_info["filename"])
        installed_version = verification.get("distribution_version")
        if installed_version != filename_version:
            raise SystemExit(
                f"installed distribution version {installed_version} does not match "
                f"artifact version {filename_version} for {artifact_info['filename']}"
            )
        versions.add(filename_version)
        identity = (
            artifact_info["kind"],
            target["python_abi"],
            target["operating_system"],
            target["architecture"],
        )
        if identity in identities:
            raise SystemExit(f"duplicate target identity: {identity}")
        identities.add(identity)

        candidates = list(args.directory.rglob(artifact_info["filename"]))
        if len(candidates) != 1:
            raise SystemExit(
                f"expected one file named {artifact_info['filename']}, found {len(candidates)}"
            )
        source = candidates[0]
        if _sha256(source) != artifact_info["sha256"]:
            raise SystemExit(f"collected digest mismatch: {source.name}")
        shutil.copy2(source, args.output_directory / source.name)
        output_files.append({**artifact_info, "target": target, "verification": verification})
        wheels += artifact_info["kind"] == "wheel"
        sdists += artifact_info["kind"] == "sdist"

    if wheels != EXPECTED_WHEELS or sdists != EXPECTED_SDISTS:
        raise SystemExit(
            f"incomplete verified set: {wheels} wheels, {sdists} sdists; "
            f"expected {EXPECTED_WHEELS} and {EXPECTED_SDISTS}"
        )
    if identities != EXPECTED_TARGETS:
        missing = sorted(EXPECTED_TARGETS - identities)
        unexpected = sorted(identities - EXPECTED_TARGETS)
        raise SystemExit(
            f"release target matrix mismatch: missing={missing}, unexpected={unexpected}"
        )
    if len(versions) != 1:
        raise SystemExit(f"verified artifacts span distribution versions: {sorted(versions)}")
    _write(
        args.output_manifest,
        {
            "schema_version": SCHEMA_VERSION,
            "source_revision": revisions.pop(),
            "artifact_count": len(output_files),
            "artifacts": sorted(output_files, key=lambda value: value["filename"]),
        },
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)

    create = commands.add_parser("manifest")
    create.add_argument("--artifact", type=Path, required=True)
    create.add_argument("--kind", choices=("wheel", "sdist"), required=True)
    create.add_argument("--python-abi", required=True)
    create.add_argument("--operating-system", required=True)
    create.add_argument("--architecture", required=True)
    create.add_argument("--revision", required=True)
    create.add_argument("--output", type=Path, required=True)
    create.set_defaults(func=manifest)

    check = commands.add_parser("verify")
    check.add_argument("--artifact", type=Path, required=True)
    check.add_argument("--manifest", type=Path, required=True)
    check.add_argument("--output", type=Path, required=True)
    check.set_defaults(func=verify)

    release_check = commands.add_parser("verify-release-wheel")
    release_check.add_argument("--directory", type=Path, required=True)
    release_check.add_argument("--manifest", type=Path, required=True)
    release_check.add_argument("--python-abi", choices=("cp313-abi3", "cp314t"), required=True)
    release_check.add_argument("--output", type=Path, required=True)
    release_check.set_defaults(func=verify_release_wheel)

    merge = commands.add_parser("collect")
    merge.add_argument("--directory", type=Path, required=True)
    merge.add_argument("--output-directory", type=Path, required=True)
    merge.add_argument("--output-manifest", type=Path, required=True)
    merge.set_defaults(func=collect)
    return root


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
