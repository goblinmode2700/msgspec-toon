# dev-tooling (delta)

## ADDED Requirements

### Requirement: A Makefile is the single entry point for developer checks

The repository SHALL provide a `Makefile` whose targets cover both languages:
`lint` (ruff check, ruff format --check, `cargo fmt --check`,
`cargo clippy --all-targets -- -D warnings`), `typecheck` (mypy over
`python/msgspec_toon`), `test` (`cargo test` and `pytest`), `check` (all of the above),
`build` (release wheel via maturin, installed into the project environment), `bench`
(the benchmark scripts against the installed release wheel), and `report`
(`scripts/release-report.py`). The Makefile SHALL export the environment `cargo test`
needs to link a Python (`PYO3_PYTHON`), so a fresh clone can run every target without
tribal knowledge.

#### Scenario: A fresh clone checks clean

- **WHEN** `make check` runs on a fresh clone with the documented toolchain
- **THEN** lint, typecheck, and both test suites run and pass without additional setup
  beyond `uv sync`

#### Scenario: Benchmarks refuse debug builds

- **WHEN** `make bench` runs
- **THEN** it measures the installed release wheel, not an unoptimized development build

### Requirement: The toons codec is reviewed as prior art

The Rust `toons` TOON codec SHALL be reviewed at a pinned version as prior art for this
project's Rust core, covering at minimum: line scanning strategy, delimiter and quoting
handling, number parsing and formatting, tabular detection on encode, error position
model, and PyO3 object-construction techniques. The review SHALL be written to
`docs/prior-art/toons.md` and SHALL list techniques adopted, techniques rejected with
reasons, and misses it exposes in this project's implementation. Because `toons` targets
specification 3.0, the review SHALL also enumerate its known-outdated behaviors (nested
field groups absent, pre-canonical number formatting, `[0]:` empty-array spelling) as
behaviors this project must not inherit. Every identified miss SHALL become a tracked
task, a fix, or a named entry in the report's known-gaps list.

#### Scenario: The review is written and versioned

- **WHEN** `docs/prior-art/toons.md` is read
- **THEN** it names the exact toons version reviewed
- **AND** it contains adopted, rejected, and misses-found lists

#### Scenario: A found miss is not dropped

- **WHEN** the review identifies a miss in this project's Rust core
- **THEN** the miss appears as a fix, a tracked task, or a known-gap entry in the
  qualification report
