"""Same-session A/B harness: baseline wheel vs current wheel, one session.

Runs a probe module (default: the typed and codec benchmarks) in the baseline
environment (`.venv-baseline`, built by `make baseline` from the frozen tag)
and in the current environment, back to back in this process's session, and
prints paired per-row deltas. Comparisons across sessions are exactly what
this tool exists to forbid: it always runs both sides itself.

Usage: uv run python benches/ab.py [--records 16 64 512 4096]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parent.parent
BASELINE_PYTHON = REPO / ".venv-baseline" / "bin" / "python"
CURRENT_PYTHON = REPO / ".venv" / "bin" / "python"

PROBE = r"""
import json, sys
sys.path.insert(0, "benches")
import bench_typed, bench_codecs
records = json.loads(sys.argv[1])
out = {
    "typed": [bench_typed.run(n) for n in records],
    "codecs": [bench_codecs.run(n) for n in records],
}
print(json.dumps(out))
"""


def run_side(python: pathlib.Path, records: list[int]) -> dict:
    if not python.exists():
        raise SystemExit(
            f"missing interpreter {python} — run `make baseline` first"
            if "baseline" in str(python)
            else f"missing interpreter {python}"
        )
    proc = subprocess.run(
        [str(python), "-c", PROBE, json.dumps(records)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"probe failed under {python}:\n{proc.stderr[-2000:]}")
    return json.loads(proc.stdout.splitlines()[-1])


def delta(current: float, baseline: float) -> str:
    change = (current - baseline) / baseline * 100
    return f"{change:+.1f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, nargs="+", default=[16, 64, 512, 4096])
    arguments = parser.parse_args()

    print("running baseline side (.venv-baseline)...")
    baseline = run_side(BASELINE_PYTHON, arguments.records)
    print("running current side (.venv)...")
    current = run_side(CURRENT_PYTHON, arguments.records)

    pairs = []
    for kind, metric_path in (
        ("typed", ("decode_us", "typed_direct")),
        ("typed", ("encode_us", "typed_direct_whole")),
        ("codecs", ("encode_us", "msgspec_toon")),
        ("codecs", ("decode_us", "msgspec_toon")),
    ):
        section, metric = metric_path
        for base_row, cur_row in zip(baseline[kind], current[kind]):
            b = base_row[section][metric]
            c = cur_row[section][metric]
            label = f"{kind}.{section}.{metric}@{base_row['records']}"
            pairs.append({"metric": label, "baseline_us": b, "current_us": c, "delta": delta(c, b)})
            print(f"{label:<50} baseline={b:>9}  current={c:>9}  {delta(c, b)}")

    out = REPO / "benches" / "ab-latest.json"
    out.write_text(json.dumps({"records": arguments.records, "pairs": pairs}, indent=2) + "\n")
    print(f"\npaired results written to {out}")


if __name__ == "__main__":
    main()
