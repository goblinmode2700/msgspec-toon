# Tasks

## 1. Dependency pin

- [x] 1.1 Pin `msgspec==0.21.1` in `pyproject.toml`; `uv sync`; confirm tests pass.
      (Landed with the cooldown commit.)

## 2. Makefile

- [x] 2.1 Add `Makefile` with `lint`, `typecheck`, `test`, `check`, `build`, `bench`,
      `report` targets (design.md shapes; exports `PYO3_PYTHON` for `cargo test`).
- [x] 2.2 Add `mypy` configuration for `python/msgspec_toon` and fix anything it flags.
      (Strict mode; three findings fixed.)
- [x] 2.3 Run `make check` clean. (Includes rustfmt across the crate and a clippy
      `-D warnings` fix: `Lines::next` renamed to `advance`.)

## 3. Timing utility

- [x] 3.1 Add `benches/_timing.py` (`best_of` returning a `Timing` with methodology
      parameters), delete the hand-rolled loop in `bench_typed.py`, and port
      `bench_typed.py`, `bench_codecs.py`, and `scripts/release-report.py` to it.

## 4. Incumbent benchmarks

- [x] 4.1 Add `python-toon==0.1.3` and `toons` to the `bench` dependency group.
      Latest python-toon release equals 0.1.3 at measurement time; recorded in the
      report, one row covers both variants.
- [x] 4.2 Add `benches/bench_codecs.py`: raw-codec rows with per-codec byte sizes.
      Result: G5 passes at every size in both directions (2-6.5x vs toons, ~20x vs
      python-toon); our tabular output is 2.9x smaller than both incumbents' fallback
      form, which exceeds compact JSON.
- [x] 4.3 Add incumbent-pipeline rows to the typed benchmark. Result: typed path wins
      19-49x decode, 41-51x encode.
- [x] 4.4 Fold the new rows, versions, methodology, and caveats into
      `scripts/release-report.py` output.

## 5. toons prior art

- [x] 5.1 Fetch `toons` 0.7.0 source (PyPI sdist); review per design.md target list.
- [x] 5.2 Write `docs/prior-art/toons.md` (adopted / rejected / misses found).
- [x] 5.3 Misses found in our core are tracked: two fixture-decidable conformance
      questions (non-finite float encoding, indent-width flexibility) added to the
      report's known-gaps list; the `[N\t]`/`[N|]` delimiter grammar recorded as the
      reference for the existing comma-only gap.

## 6. Package cooldown (applied early, 2026-08-06, with owner approval)

- [x] 6.1 Upgrade uv (0.5.14 → 0.12.2) so duration-valued `exclude-newer` parses.
- [x] 6.2 Add `tool.uv.exclude-newer = "14 days"`; re-lock (evicted zero-day-old
      `ast-serialize 0.7.0` and `librt 0.14.0`, plus `packaging`, `ruff`).
- [x] 6.3 Pin `pyo3 = "=0.29.0"` (0.29.1/0.29.2 inside the window);
      `cargo update -p pyo3 --precise 0.29.0`; full re-test on the downgrade
      (63 tests pass, gates unchanged: G3 all-pass, G4 known miss).
- [x] 6.4 Add `scripts/check-package-ages.py` + Makefile `audit`/`relock` targets;
      `make audit` runs clean.
- [ ] 6.5 When extending the Makefile (task 2.1), keep `audit` out of `make check`
      (network); run it in CI and before releases.
- [ ] 6.6 Lift the pyo3 pin once 0.29.2 ages past 14 days (`make audit` will confirm).
