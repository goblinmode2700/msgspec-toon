# Refine benchmarks and tooling

## Why

The Phase 1 POC shipped with benchmark baselines chosen from what was installable in the
moment. That misses the comparisons that actually decide the challenge: the incumbent
Python TOON libraries (`python-toon`, both the 0.1.3 release the design of record measured
and whatever is latest today) and the *actual* incumbent pipeline this project exists to
replace — `python_toon.encode(normalize(obj))` where `normalize` is a `to_builtins`
conversion, and `msgspec.convert(python_toon.decode(buf), type)` on the way back. Timing
loops are also hand-rolled per script, msgspec is range-pinned rather than exact-pinned,
developer checks have no single entry point, and the fastest existing compiled TOON codec
(`toons`, Rust) has not been mined as prior art for parser techniques or gaps in our own
Rust core.

## What changes

1. **Exact-pin msgspec to 0.21.1** in `pyproject.toml` (runtime and plan-compiler surface
   are both version-sensitive; the canvas's compatibility membrane assumes a pinned
   minimum that we should make exact for the POC).
2. **Add a Makefile** as the single entry point for developer checks: ruff (lint +
   format check) and mypy for Python; `cargo fmt --check`, `cargo clippy --all-targets
   -- -D warnings`, and `cargo test` for Rust; plus `test`, `build`, `bench`, and
   `report` targets.
3. **Benchmark against the real incumbents**: `python-toon==0.1.3`, the latest
   `python-toon` release (version recorded at run time), and — when installable — the
   `toons` Rust codec for the G5 codec-floor rows. Keep `msgspec.json` native rows as
   context and keep the `to_builtins`-alone row (G4) alongside.
4. **Benchmark the incumbent pipeline shape** as first-class rows: encode =
   `python_toon.encode(to_builtins(obj))`, decode =
   `msgspec.convert(python_toon.decode(buf), type)`. This is a benchmark to beat, not
   the definition of "the wrapper" — it is known to be inefficient, and the report says
   so rather than treating it as the strongest opponent.
5. **Standardize benchmark timing** into one shared utility (decorator/helper) used by
   every benchmark script — no per-script hand-rolled loops.
6. **Study `toons` as prior art**: review its Rust source at a pinned version and
   document adopted techniques, rejected choices, and any misses it exposes in our
   parser/encoder (it is v3.0-era, so the review must also flag behaviors we must NOT
   inherit).
7. **14-day package cooldown, both ecosystems** (applied 2026-08-06 with owner
   approval via the whiteboard review): Python enforces it natively with
   `tool.uv.exclude-newer = "14 days"` (per-package CVE escape hatch:
   `exclude-newer-package`); Rust — where Cargo has no equivalent — pins the one
   violating family (`pyo3 =0.29.0`) and enforces the window with
   `scripts/check-package-ages.py` via `make audit`. The audit found and evicted two
   transitive packages that were zero days old at audit time.

## Impact

- Modified spec: `distribution-quality` (dependency pin, expanded speed-floor baselines,
  incumbent-pipeline rows, standardized timing, package cooldown).
- New spec: `dev-tooling` (Makefile entry points, prior-art review artifact, cooldown
  audit targets).
- Code: `pyproject.toml`, new `Makefile`, `benches/` (new `_timing.py`, expanded
  `bench_codecs.py`), new `docs/prior-art/toons.md`, new
  `scripts/check-package-ages.py`, dev-dependency additions (`python-toon` variants,
  `toons` if installable).
