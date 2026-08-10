"""Generate deterministic cargo-fuzz seeds from locked repository evidence."""

from __future__ import annotations

import hashlib
import json
import pathlib
import struct

ROOT = pathlib.Path(__file__).resolve().parent.parent
DESTINATION = ROOT / "fuzz" / "corpus" / "parser_bytes"
INTEGER_DESTINATION = ROOT / "fuzz" / "corpus" / "integer_list_roundtrip"
FIXTURES = ROOT / "conformance" / "fixtures"
PERMANENT_CASES = (
    b"[18446744073709551615]:",
    b"  depth-jump: true",
    b'key: "unterminated',
)
INTEGER_CASES = (
    (0,),
    (-1, 1),
    (-(2**63), 2**63 - 1),
    tuple(range(-32, 33)),
)


def _sync(destination: pathlib.Path, seeds: list[bytes]) -> tuple[int, int]:
    destination.mkdir(parents=True, exist_ok=True)
    canonical = {hashlib.sha256(data).hexdigest(): data for data in seeds}
    for path in destination.iterdir():
        if path.is_file() and path.name not in canonical:
            path.unlink()
    for digest, data in canonical.items():
        (destination / digest).write_bytes(data)
    return len(canonical), len(seeds)


def main() -> None:
    seeds = list(PERMANENT_CASES)
    for path in sorted(FIXTURES.rglob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for case in document.get("tests", []):
            for name in ("input", "expected"):
                value = case.get(name)
                if isinstance(value, str):
                    seeds.append(value.encode())
    unique, total = _sync(DESTINATION, seeds)
    print(f"wrote {unique} unique deterministic seeds from {total} values to {DESTINATION}")
    integer_seeds = [b"".join(struct.pack("<q", value) for value in case) for case in INTEGER_CASES]
    unique, total = _sync(INTEGER_DESTINATION, integer_seeds)
    print(f"wrote {unique} unique deterministic seeds from {total} values to {INTEGER_DESTINATION}")


if __name__ == "__main__":
    main()
