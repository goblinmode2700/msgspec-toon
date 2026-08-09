"""Re-fetch the pinned fixture corpus and verify it against the lock.

The corpus is vendored in-repo so conformance runs are hermetic; this script
exists to (re)populate or verify it from the pinned upstream commit — never
from a moving branch.
"""

from __future__ import annotations

import hashlib
import io
import json
import pathlib
import sys
import tarfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
LOCK = json.loads((ROOT / "fixtures.lock.json").read_text())


def tree_sha256(root: pathlib.Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.json")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def fetch() -> None:
    commit = LOCK["commit"]
    url = f"https://github.com/{LOCK['repository']}/archive/{commit}.tar.gz"
    print(f"fetching {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "msgspec-toon conformance"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read()
    fixtures = ROOT / "fixtures"
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for member in archive.getmembers():
            parts = pathlib.PurePosixPath(member.path).parts
            if len(parts) < 4 or parts[1:3] != ("tests", "fixtures") or not member.isfile():
                continue
            relative = pathlib.PurePosixPath(*parts[3:])
            target = fixtures / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = archive.extractfile(member)
            assert extracted is not None
            target.write_bytes(extracted.read())
    print(f"vendored into {fixtures}")


def verify() -> int:
    actual = tree_sha256(ROOT / "fixtures")
    expected = LOCK["tree_sha256"]
    if actual != expected:
        print(f"MISMATCH: vendored tree {actual} != locked {expected}")
        return 1
    print(f"verified: {actual} matches lock ({LOCK['tag']} @ {LOCK['commit'][:12]})")
    return 0


if __name__ == "__main__":
    if "--fetch" in sys.argv:
        fetch()
    sys.exit(verify())
