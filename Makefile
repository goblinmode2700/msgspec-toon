# Single entry point for developer checks (openspec: dev-tooling).
#
# The uv-managed CPython's dylib install-name breaks `cargo test` linking,
# so Rust tests link against the Homebrew Python instead.
PYO3_PYTHON := /opt/homebrew/opt/python@3.13/bin/python3.13
export PYO3_PYTHON

COOLDOWN_DAYS := 14

# Opt-in build against the proposed msgspec Struct C API. The normal project
# environment and dependency pin stay untouched; this profile owns a separate
# source checkout, wheel directory, and virtual environment.
MSGSPEC_FASTPATH_COMMIT := 10c9ac4a8d0a9aacb7854a71f5cf479b47594736
MSGSPEC_FASTPATH_REPO := https://github.com/jcrist/msgspec.git
MSGSPEC_FASTPATH_PATCH := $(CURDIR)/docs/implementation-spec/patches/0001-feat-expose-versioned-Struct-access-C-API.patch
FASTPATH_ROOT := target/fastpath
FASTPATH_MSGSPEC_SRC := $(FASTPATH_ROOT)/msgspec
FASTPATH_MSGSPEC_WHEELS := $(FASTPATH_ROOT)/msgspec-wheels
FASTPATH_TOON_WHEELS := $(FASTPATH_ROOT)/toon-wheels
FASTPATH_VENV := .venv-fastpath
FASTPATH_PYTHON := $(FASTPATH_VENV)/bin/python

# Two baselines, two jobs. STORY is what the optimization round bought — it is
# reported and never gated, so the ledger keeps its reference point. GUARD is
# the latest release; it is the only thing the gate compares against, because a
# distant baseline cannot detect a regression: measured, a 24% slowdown against
# STORY read as "+2.2%, no significant difference", since the current build led
# that baseline by 15-20%. Re-cut GUARD at every release or it decays into the
# same blind spot.
BASELINE_TAG := v0.1.0-conformant
# Derived, never hardcoded: a guard pinned by hand silently ages into the blind
# spot it exists to prevent. `benches/ab.py` re-derives this and refuses to gate
# against a guard built from an older tag.
GUARD_TAG := $(shell git tag -l 'v*' --sort=-v:refname | head -1)

.PHONY: lint typecheck test check build bench report audit relock baseline guard ab ab-story g2 efficiency \
	fastpath-source fastpath-build fastpath-check fastpath-bench fastpath-gates fastpath-clean

lint:
	uv run --no-sync ruff check .
	uv run --no-sync ruff format --check .
	cargo fmt --check
	cargo clippy --all-targets -- -D warnings
	cargo clippy --all-targets --features alloc-stats -- -D warnings

typecheck:
	uv run --no-sync mypy python/msgspec_toon

test:
	cargo test
	uv run --no-sync pytest

# Offline-capable by design: the network-dependent cooldown audit is a
# separate target, run in CI and before releases.
check: lint typecheck test

# Build the release extension into the environment that is actually imported.
# `.venv` installs this project editable, so `uv run` resolves
# `python/msgspec_toon/_native.abi3.so` and a separately pip-installed wheel is
# shadowed (and undone by the next re-sync). `maturin develop --release` writes
# the release abi3 build to that path, so what runs is what was measured.
# `benches/build_freshness.py` enforces it rather than trusting it.
build:
	rm -f target/wheels/*.whl
	uv run --no-sync maturin develop --release

bench: build
	uv run --no-sync python benches/bench_codecs.py
	uv run --no-sync python benches/bench_typed.py

report: build
	uv run --no-sync python scripts/release-report.py

# Reproduce the upstream capsule experiment without changing `.venv` or the
# publishable `msgspec==0.21.1` dependency. The source is hash-pinned, the patch
# is repository-owned, and both packages are installed as release wheels.
fastpath-source:
	mkdir -p $(FASTPATH_ROOT)
	@if test ! -d "$(FASTPATH_MSGSPEC_SRC)/.git"; then \
		git init "$(FASTPATH_MSGSPEC_SRC)"; \
		git -C "$(FASTPATH_MSGSPEC_SRC)" remote add origin "$(MSGSPEC_FASTPATH_REPO)"; \
	fi
	@if ! git -C "$(FASTPATH_MSGSPEC_SRC)" cat-file -e "$(MSGSPEC_FASTPATH_COMMIT)^{commit}" 2>/dev/null; then \
		git -C "$(FASTPATH_MSGSPEC_SRC)" fetch --depth 1 origin "$(MSGSPEC_FASTPATH_COMMIT)"; \
	fi
	git -C "$(FASTPATH_MSGSPEC_SRC)" checkout --detach "$(MSGSPEC_FASTPATH_COMMIT)"
	@if git -C "$(FASTPATH_MSGSPEC_SRC)" apply --reverse --check "$(MSGSPEC_FASTPATH_PATCH)" 2>/dev/null; then \
		echo "msgspec Struct C API patch already applied"; \
	else \
		git -C "$(FASTPATH_MSGSPEC_SRC)" apply "$(MSGSPEC_FASTPATH_PATCH)"; \
	fi
	@test "$$(git -C "$(FASTPATH_MSGSPEC_SRC)" rev-parse HEAD)" = "$(MSGSPEC_FASTPATH_COMMIT)"
	git -C "$(FASTPATH_MSGSPEC_SRC)" diff --check

fastpath-build: fastpath-source
	SETUPTOOLS_SCM_PRETEND_VERSION=0.21.1 uv build --wheel --clear \
		--out-dir "$(FASTPATH_MSGSPEC_WHEELS)" "$(FASTPATH_MSGSPEC_SRC)"
	uv run --no-sync maturin build --release --locked \
		-o "$(FASTPATH_TOON_WHEELS)"
	UV_PROJECT_ENVIRONMENT="$(FASTPATH_VENV)" uv sync --python 3.13 --all-groups --locked
	uv pip install --python "$(FASTPATH_PYTHON)" --reinstall --no-deps \
		$(FASTPATH_MSGSPEC_WHEELS)/*.whl $(FASTPATH_TOON_WHEELS)/*.whl
	$(FASTPATH_PYTHON) -c "import msgspec, msgspec_toon; assert msgspec.__version__ == '0.21.1'; assert msgspec_toon.Encoder()._native._struct_access == 'capsule'; print('fast path active: msgspec 0.21.1 + capsule')"

fastpath-check: fastpath-build
	$(MAKE) lint typecheck
	cargo test
	$(FASTPATH_PYTHON) -m pytest
	$(FASTPATH_PYTHON) conformance/run.py

fastpath-bench: fastpath-build
	$(FASTPATH_PYTHON) benches/bench_struct_capi.py

fastpath-gates: fastpath-build
	$(FASTPATH_PYTHON) benches/bench_typed.py

fastpath-clean:
	rm -rf "$(FASTPATH_VENV)" "$(FASTPATH_ROOT)"

# Build the frozen-baseline wheel ($(BASELINE_TAG)) into .venv-baseline so
# benches/ab.py can run same-session before/after comparisons.
baseline:
	git worktree remove --force .baseline-src 2>/dev/null || true
	rm -rf .baseline-src .venv-baseline target/baseline-wheels
	git worktree add --detach .baseline-src $(BASELINE_TAG)
	uv venv .venv-baseline --python 3.13
	uv run --no-sync maturin build --release \
		-m .baseline-src/Cargo.toml -o target/baseline-wheels
	uv pip install --python .venv-baseline/bin/python target/baseline-wheels/*.whl \
		python-toon==0.1.3 toons pytest
	git worktree remove --force .baseline-src

# Build the guard wheel ($(GUARD_TAG)) into .venv-guard. This is what the gate
# measures against, so it must track the latest release.
guard:
	git worktree remove --force .guard-src 2>/dev/null || true
	rm -rf .guard-src .venv-guard target/guard-wheels
	git worktree add --detach .guard-src $(GUARD_TAG)
	uv venv .venv-guard --python 3.13
	uv run --no-sync maturin build --release \
		-m .guard-src/Cargo.toml -o target/guard-wheels
	uv pip install --python .venv-guard/bin/python target/guard-wheels/*.whl \
		python-toon==0.1.3 toons pytest
	git worktree remove --force .guard-src
	echo "$(GUARD_TAG)" > .venv-guard/GUARD_TAG
	@echo "guard built from $(GUARD_TAG)"

# The gate: exits non-zero when a metric is significantly slower than the
# latest release and the slowdown reproduces. Needs .venv-guard and takes
# minutes, which is why it is not part of `check`.
ab:
	uv run --no-sync python benches/ab.py

# The story: what the optimization round bought, measured against the frozen
# tag. Reported, never gated — a distant baseline cannot police a regression.
ab-story:
	uv run --no-sync python benches/ab.py --baseline-venv .venv-baseline --no-gate

# The efficiency lock: what canonical output costs. Deterministic and offline,
# so it also runs inside `make check` as an ordinary test.
efficiency:
	uv run --no-sync python scripts/efficiency-lock.py

# The G2 proof runs against an instrumented wheel in its own environment, so
# the release wheel every benchmark measures stays free of counters. Same
# separation as `make baseline`: a second venv, never the working one.
g2:
	rm -rf .venv-g2 target/g2-wheels
	uv venv .venv-g2 --python 3.13
	uv run --no-sync maturin build --release --features alloc-stats -o target/g2-wheels
	uv pip install --python .venv-g2/bin/python target/g2-wheels/*.whl \
		msgspec==0.21.1 python-toon==0.1.3 toons pytest
	.venv-g2/bin/python -m pytest tests/test_typed_allocations.py -q
	.venv-g2/bin/python scripts/allocation-proof.py

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
