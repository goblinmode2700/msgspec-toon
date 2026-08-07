# Tasks

## 1. Dependency pin

- [ ] 1.1 Pin `msgspec==0.21.1` in `pyproject.toml`; `uv sync`; confirm tests pass.

## 2. Makefile

- [ ] 2.1 Add `Makefile` with `lint`, `typecheck`, `test`, `check`, `build`, `bench`,
      `report` targets (design.md shapes; exports `PYO3_PYTHON` for `cargo test`).
- [ ] 2.2 Add `mypy` configuration for `python/msgspec_toon` and fix anything it flags.
- [ ] 2.3 Run `make check` clean.

## 3. Timing utility

- [ ] 3.1 Add `benches/_timing.py` (`best_of` + `@timed`), delete the hand-rolled loop
      in `bench_typed.py`, and port `bench_typed.py` and `scripts/release-report.py` to it.

## 4. Incumbent benchmarks

- [ ] 4.1 Add `python-toon==0.1.3` to a benchmark dependency group; check what the
      latest release is and record whether it differs.
- [ ] 4.2 Add `benches/bench_codecs.py`: raw-codec rows (python-toon variants, `toons`
      if installable, msgspec.json context) per design.md matrix, including byte sizes
      per codec.
- [ ] 4.3 Add incumbent-pipeline rows (`encode(to_builtins(...))` /
      `convert(decode(...))`) to the typed benchmark, alongside the existing
      `to_builtins`-alone row.
- [ ] 4.4 Fold the new rows into `scripts/release-report.py` output.

## 5. toons prior art

- [ ] 5.1 Fetch `toons` source at a pinned version; review per design.md target list.
- [ ] 5.2 Write `docs/prior-art/toons.md` (adopted / rejected / misses found).
- [ ] 5.3 File or fix every identified miss in our Rust core; note each in the report's
      known-gaps list if deferred.
