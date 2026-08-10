from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _seed_module():
    path = ROOT / "scripts" / "seed_fuzz_corpus.py"
    spec = importlib.util.spec_from_file_location("seed_fuzz_corpus", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fuzz_seed_generation_is_deterministic(tmp_path: Path) -> None:
    module = _seed_module()
    parser_destination = tmp_path / "parser"
    integer_destination = tmp_path / "integer"
    module.DESTINATION = parser_destination
    module.INTEGER_DESTINATION = integer_destination

    module.main()
    first = {
        destination.name: {path.name: path.read_bytes() for path in destination.iterdir()}
        for destination in (parser_destination, integer_destination)
    }
    (parser_destination / "libfuzzer-learned-input").write_bytes(b"learned")
    (integer_destination / "libfuzzer-learned-input").write_bytes(b"learned")
    module.main()
    second = {
        destination.name: {path.name: path.read_bytes() for path in destination.iterdir()}
        for destination in (parser_destination, integer_destination)
    }

    assert first == second
    assert first
    assert all(
        hashlib.sha256(data).hexdigest() == name
        for corpus in first.values()
        for name, data in corpus.items()
    )


def test_fuzz_workflow_pins_toolchain_and_targets() -> None:
    workflow = (ROOT / ".github" / "workflows" / "fuzz.yml").read_text()
    assert 'CARGO_FUZZ_VERSION: "0.13.2"' in workflow
    assert 'NIGHTLY_TOOLCHAIN: "nightly-2026-07-15"' in workflow
    assert "target: [parser_bytes, integer_list_roundtrip]" in workflow
    assert "-max_total_time=20" in workflow
    assert "-max_total_time=900" in workflow


def test_cooldown_audit_includes_fuzz_lock() -> None:
    path = ROOT / "scripts" / "check-package-ages.py"
    spec = importlib.util.spec_from_file_location("check_package_ages", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    packages = set(module.cargo_lock_packages())
    assert ("libfuzzer-sys", "0.4.10") in packages
    assert ("cc", "1.2.50") in packages
    assert ("find-msvc-tools", "0.1.9") in packages
