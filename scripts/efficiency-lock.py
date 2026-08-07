"""Write `conformance/efficiency.lock.json`.

Regenerating the lock is a deliberate act, not a build step: the lock exists so
that a change in what this codec's output costs has to be noticed and explained.
Run this only when the counts moved for a reason, and say what the reason was in
the commit that carries the new lock.

    uv run python scripts/efficiency-lock.py            # show the current diff
    uv run python scripts/efficiency-lock.py --write    # accept the new counts
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "conformance"))

from efficiency import LOCK_PATH, measure


def differences(locked: dict, current: dict) -> list[str]:
    if locked.get("versions") != current.get("versions"):
        return [f"versions: locked {locked.get('versions')} != current {current.get('versions')}"]
    out = []
    for payload, formats in current["payloads"].items():
        locked_formats = locked["payloads"].get(payload)
        if locked_formats is None:
            out.append(f"{payload}: not in the lock")
            continue
        for name, entry in formats.items():
            if locked_formats.get(name) != entry:
                out.append(f"{payload}/{name}: locked {locked_formats.get(name)} != {entry}")
    for payload in locked["payloads"]:
        if payload not in current["payloads"]:
            out.append(f"{payload}: in the lock but no longer measured")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="accept the current counts")
    arguments = parser.parse_args()

    current = measure()
    if arguments.write:
        LOCK_PATH.write_text(json.dumps(current, indent=2) + "\n")
        print(f"wrote {LOCK_PATH}")
        return

    if not LOCK_PATH.exists():
        raise SystemExit(f"no lock at {LOCK_PATH} — run with --write to create it")

    drift = differences(json.loads(LOCK_PATH.read_text()), current)
    if not drift:
        print("efficiency lock matches")
        return
    print("efficiency lock DIFFERS:")
    for line in drift:
        print(f"  {line}")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
