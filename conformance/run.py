"""Run the pinned TOON 4.1 fixture corpus against msgspec_toon.

Refuses to execute if the vendored fixture tree does not match the lock.
Every test runs; nothing is silently skipped. Tests whose options this
implementation does not support (non-comma delimiter, non-2 indentSize) are
counted as `unsupported_option` — published, not hidden. Non-strict decode
tests that fail are additionally tallied separately because the corpus
README marks part of that class as optional leniency an implementation MAY
reject; the split keeps the honest number visible either way.

Output: human summary on stdout, machine-readable results in
conformance/conformance-results.json (consumed by scripts/release-report.py).
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import msgspec_toon
from fetch import LOCK, ROOT, tree_sha256


def typed_equal(left: Any, right: Any) -> bool:
    """Equality that refuses cross-type coercion, except int/float.

    JSON fixtures have one number type, so `1e6` cannot declare whether it
    means `1000000` or `1000000.0`; numerically equal ints and floats compare
    equal here. Booleans stay distinct from numbers, strings from everything.
    """
    if isinstance(left, bool) is not isinstance(right, bool):
        return False
    if (
        type(left) is not type(right)
        and not (isinstance(left, int | float) and isinstance(right, int | float))
    ):
        return False
    if isinstance(left, dict):
        return (
            len(left) == len(right)
            and all(
                key in right and typed_equal(value, right[key]) for key, value in left.items()
            )
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            typed_equal(a, b) for a, b in zip(left, right)
        )
    return bool(left == right)


def run_decode(test: dict[str, Any]) -> tuple[str, str]:
    options = test.get("options") or {}
    strict = options.get("strict", True)
    indent_size = options.get("indentSize", 2)
    if indent_size != 2:
        return "unsupported_option", f"indentSize={indent_size}"

    should_error = test.get("shouldError", False)
    try:
        value = msgspec_toon.decode(test["input"], strict=strict)
    except (msgspec_toon.DecodeError, msgspec_toon.ValidationError) as exc:
        if should_error:
            return "pass", ""
        return "fail", f"raised {exc.code}: {exc}"
    except Exception as exc:  # noqa: BLE001 - a wrong exception type is a finding
        return "fail", f"raised non-decode error {type(exc).__name__}: {exc}"
    if should_error:
        return "fail", f"accepted input that must error (got {value!r:.80})"
    if typed_equal(value, test["expected"]):
        return "pass", ""
    return "fail", f"value mismatch: got {value!r:.120}"


def run_encode(test: dict[str, Any]) -> tuple[str, str]:
    options = test.get("options") or {}
    delimiter = options.get("delimiter", ",")
    indent_size = options.get("indentSize", 2)
    if delimiter != ",":
        return "unsupported_option", f"delimiter={delimiter!r}"
    if indent_size != 2:
        return "unsupported_option", f"indentSize={indent_size}"

    should_error = test.get("shouldError", False)
    try:
        output = msgspec_toon.encode(test["input"]).decode()
    except Exception as exc:  # noqa: BLE001 - encode fixtures may expect errors
        if should_error:
            return "pass", ""
        return "fail", f"raised {type(exc).__name__}: {exc}"
    if should_error:
        return "fail", "encoded a value that must error"
    expected = test["expected"]
    if output == expected:
        return "pass", ""
    return "fail", f"byte mismatch: got {output!r:.120} want {expected!r:.120}"


def main() -> int:
    actual = tree_sha256(ROOT / "fixtures")
    if actual != LOCK["tree_sha256"]:
        print(f"REFUSING TO RUN: fixture tree {actual} != locked {LOCK['tree_sha256']}")
        return 2

    results: list[dict[str, Any]] = []
    for category, runner in (("decode", run_decode), ("encode", run_encode)):
        for path in sorted((ROOT / "fixtures" / category).glob("*.json")):
            fixture = json.loads(path.read_text())
            for index, test in enumerate(fixture["tests"]):
                status, detail = runner(test)
                results.append(
                    {
                        "category": category,
                        "file": path.name,
                        "index": index,
                        "name": test.get("name", ""),
                        "strict": (test.get("options") or {}).get("strict", True),
                        "should_error": test.get("shouldError", False),
                        "status": status,
                        "detail": detail,
                    }
                )

    def count(**criteria: Any) -> int:
        return sum(
            1
            for r in results
            if all(r[key] == value for key, value in criteria.items())
        )

    summary = {
        "corpus": {
            "tag": LOCK["tag"],
            "commit": LOCK["commit"],
            "tree_sha256": LOCK["tree_sha256"],
            "total_tests": len(results),
        },
        "decode": {
            "total": count(category="decode"),
            "pass": count(category="decode", status="pass"),
            "fail": count(category="decode", status="fail"),
            "unsupported_option": count(category="decode", status="unsupported_option"),
            "fail_nonstrict_only": count(category="decode", status="fail", strict=False),
        },
        "encode": {
            "total": count(category="encode"),
            "pass": count(category="encode", status="pass"),
            "fail": count(category="encode", status="fail"),
            "unsupported_option": count(category="encode", status="unsupported_option"),
        },
        "strict_error_fixtures": {
            "total": count(should_error=True),
            "pass": count(should_error=True, status="pass"),
        },
    }

    out = ROOT / "conformance-results.json"
    out.write_text(
        json.dumps({"summary": summary, "results": results}, indent=2) + "\n"
    )

    print(f"corpus {LOCK['tag']} @ {LOCK['commit'][:12]} ({len(results)} tests)")
    for section in ("decode", "encode"):
        s = summary[section]
        print(
            f"  {section}: {s['pass']}/{s['total']} pass, {s['fail']} fail, "
            f"{s['unsupported_option']} unsupported-option"
        )
    errors = summary["strict_error_fixtures"]
    print(f"  error fixtures: {errors['pass']}/{errors['total']} raise as required")
    print(f"results written to {out}")

    by_file: dict[str, int] = {}
    for r in results:
        if r["status"] == "fail":
            key = f"{r['category']}/{r['file']}"
            by_file[key] = by_file.get(key, 0) + 1
    if by_file:
        print("\nfailures by file:")
        for key, n in sorted(by_file.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>3}  {key}")

    return 0 if summary["decode"]["fail"] == summary["encode"]["fail"] == 0 else 1


if __name__ == "__main__":
    main_result = main()
    sys.exit(main_result)
