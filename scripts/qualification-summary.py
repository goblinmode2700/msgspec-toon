"""Summarize a completed canonical qualification run.

The Make target owns command ordering and exits at the first failure. This file
only checks and aggregates the machine-readable outputs produced by those
existing tools; it is not another test runner.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent


def _json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"missing qualification evidence: {path.relative_to(ROOT)}")
    return json.loads(path.read_text())


def _revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    junit = args.junit
    if not junit.is_file():
        raise SystemExit(f"missing qualification evidence: {junit}")
    root = ElementTree.parse(junit).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        raise SystemExit("pytest JUnit evidence contains no testsuite")
    tests = int(suite.attrib["tests"])
    failures = int(suite.attrib["failures"])
    errors = int(suite.attrib["errors"])
    skipped = int(suite.attrib["skipped"])

    conformance = _json(ROOT / "conformance" / "conformance-results.json")["summary"]
    allocation = _json(ROOT / "conformance" / "allocation-proof.json")
    from msgspec_toon import _native

    summary = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "distribution": "msgspec-toon",
        "version": importlib.metadata.version("msgspec-toon"),
        "source_revision": _revision(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "native_module": str(Path(_native.__file__).resolve()),
        },
        "source_gate": {
            "status": "passed",
            "checks": [
                "ruff check",
                "ruff format --check",
                "mypy",
                "cargo fmt --check",
                "cargo clippy --all-targets -- -D warnings",
                "cargo test",
            ],
        },
        "pytest": {
            "status": "passed" if failures == errors == 0 else "failed",
            "tests": tests,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
            "containment_file": "tests/test_containment.py",
            "support_matrix_file": "tests/test_support_matrix.py",
        },
        "conformance": conformance,
        "allocation_proof": allocation,
    }
    if summary["pytest"]["status"] != "passed":
        raise SystemExit("pytest evidence is not passing")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(f"qualification summary written to {args.output}")


if __name__ == "__main__":
    main()
