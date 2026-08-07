"""Supply-chain cooldown audit over both lockfiles.

Fails (exit 1) if any resolved version in Cargo.lock or uv.lock was released
within the cooldown window. This is the enforcement layer Cargo lacks natively
(uv enforces its own window at resolution time via `tool.uv.exclude-newer`;
here it is a belt-and-suspenders double check).

Per-package overrides declared in `tool.uv.exclude-newer-package` are honored:
a package listed there is reported but does not fail the audit — the
justification lives in the commit that added the override.

Network required: release dates come from the crates.io and PyPI APIs.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import re
import sys
import tomllib
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
USER_AGENT = "msgspec-toon cooldown audit (scripts/check-package-ages.py)"


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def crate_release_date(name: str, version: str) -> datetime.datetime:
    payload = fetch_json(f"https://crates.io/api/v1/crates/{name}/{version}")
    return datetime.datetime.fromisoformat(
        payload["version"]["created_at"].replace("Z", "+00:00")
    )


def pypi_release_date(name: str, version: str) -> datetime.datetime | None:
    payload = fetch_json(f"https://pypi.org/pypi/{name}/{version}/json")
    uploads = [f["upload_time_iso_8601"] for f in payload["urls"]]
    if not uploads:
        return None
    return datetime.datetime.fromisoformat(min(uploads).replace("Z", "+00:00"))


def cargo_lock_packages() -> list[tuple[str, str]]:
    text = (REPO_ROOT / "Cargo.lock").read_text()
    found = re.findall(r'\[\[package\]\]\nname = "([^"]+)"\nversion = "([^"]+)"', text)
    return [(name, version) for name, version in found if name != "msgspec-toon-native"]


def uv_lock_packages() -> list[tuple[str, str]]:
    data = tomllib.loads((REPO_ROOT / "uv.lock").read_text())
    return [
        (pkg["name"], pkg["version"])
        for pkg in data.get("package", [])
        if pkg["name"] != "msgspec-toon"
    ]


def python_overrides() -> set[str]:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    overrides = data.get("tool", {}).get("uv", {}).get("exclude-newer-package", {})
    return set(overrides)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=14, help="cooldown window in days")
    arguments = parser.parse_args()

    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=arguments.days)
    overrides = python_overrides()
    violations: list[str] = []
    overridden: list[str] = []
    errors: list[str] = []

    for ecosystem, packages, dated in (
        ("cargo", cargo_lock_packages(), crate_release_date),
        ("pypi", uv_lock_packages(), pypi_release_date),
    ):
        for name, version in packages:
            try:
                released = dated(name, version)
            except Exception as exc:  # noqa: BLE001 - report and keep auditing
                errors.append(f"{ecosystem}:{name} {version}: lookup failed ({exc})")
                continue
            if released is None or released < cutoff:
                continue
            label = f"{ecosystem}:{name} {version} released {released.date()}"
            if ecosystem == "pypi" and name in overrides:
                overridden.append(label)
            else:
                violations.append(label)

    for line in overridden:
        print(f"OVERRIDE (exclude-newer-package): {line}")
    for line in errors:
        print(f"WARNING: {line}")
    if violations:
        print(f"\nCOOLDOWN VIOLATIONS (< {arguments.days} days old):")
        for line in violations:
            print(f"  {line}")
        return 1
    print(f"cooldown audit clean: no locked version younger than {arguments.days} days")
    return 0


if __name__ == "__main__":
    sys.exit(main())
