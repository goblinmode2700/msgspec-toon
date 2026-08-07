# Single entry point for developer checks (openspec: dev-tooling).
#
# The uv-managed CPython's dylib install-name breaks `cargo test` linking,
# so Rust tests link against the Homebrew Python instead.
PYO3_PYTHON := /opt/homebrew/opt/python@3.13/bin/python3.13
export PYO3_PYTHON

COOLDOWN_DAYS := 14

.PHONY: lint typecheck test check build bench report audit relock

lint:
	uv run --no-sync ruff check .
	uv run --no-sync ruff format --check .
	cargo fmt --check
	cargo clippy --all-targets -- -D warnings

typecheck:
	uv run --no-sync mypy python/msgspec_toon

test:
	cargo test
	uv run --no-sync pytest

# Offline-capable by design: the network-dependent cooldown audit is a
# separate target, run in CI and before releases.
check: lint typecheck test

# Build the release wheel and install it — benchmarks measure this wheel,
# never an unoptimized development build.
build:
	uv run --no-sync maturin build --release
	uv pip install --force-reinstall --no-deps target/wheels/*.whl

bench: build
	uv run --no-sync python benches/bench_codecs.py
	uv run --no-sync python benches/bench_typed.py

report: build
	uv run --no-sync python scripts/release-report.py

# Python needs no date plumbing: [tool.uv] exclude-newer = "14 days" makes
# every uv resolution rolling-compliant on its own. This target just
# re-resolves both ecosystems and re-audits.
relock:
	uv lock
	cargo update
	$(MAKE) audit

# Fail if any resolved version in Cargo.lock or uv.lock is younger than
# $(COOLDOWN_DAYS) days (queries crates.io / PyPI; network required).
# This is the enforcement layer Cargo lacks natively, and a belt-and-
# suspenders double check on the uv side.
audit:
	uv run --no-sync python scripts/check-package-ages.py --days $(COOLDOWN_DAYS)
