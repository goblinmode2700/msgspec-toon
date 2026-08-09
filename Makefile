# Single entry point for developer checks.
#
# Override when PyO3 must link against a specific Python interpreter.
PYO3_PYTHON ?= $(shell command -v python3.13 || command -v python3)
export PYO3_PYTHON

COOLDOWN_DAYS := 14
QUALIFICATION_DIR := target/qualification
PYTEST_ARGS ?=

# Command seams keep the normal targets readable and let tests prove that every
# qualification component fails closed without running or corrupting a real
# release build. Production and CI never override these defaults.
TEST_RUST ?= cargo test
TEST_PYTHON ?= uv run --no-sync pytest $(PYTEST_ARGS)
CHECK_LINT ?= $(MAKE) lint
CHECK_TYPECHECK ?= $(MAKE) typecheck
CHECK_TEST ?= $(MAKE) test
QUALIFY_PREPARE ?= rm -rf "$(QUALIFICATION_DIR)" && mkdir -p "$(QUALIFICATION_DIR)"
QUALIFY_SYNC ?= uv sync --all-groups --locked
QUALIFY_BUILD ?= $(MAKE) build
QUALIFY_CHECK ?= $(MAKE) check PYTEST_ARGS="--junitxml=$(QUALIFICATION_DIR)/pytest.xml"
QUALIFY_CONFORMANCE ?= $(MAKE) conformance
QUALIFY_G2 ?= $(MAKE) g2
QUALIFY_REPORT ?= uv run --no-sync python scripts/release-report.py --check-changelog
QUALIFY_COPY_EVIDENCE ?= cp conformance/conformance-results.json "$(QUALIFICATION_DIR)/conformance-results.json" && cp conformance/allocation-proof.json "$(QUALIFICATION_DIR)/allocation-proof.json"
QUALIFY_SUMMARY ?= uv run --no-sync python scripts/qualification-summary.py --junit "$(QUALIFICATION_DIR)/pytest.xml" --output "$(QUALIFICATION_DIR)/summary.json"

# Opt-in build against the proposed msgspec Struct C API. The normal project
# environment and dependency pin stay untouched; this profile owns a separate
# source checkout, wheel directory, and virtual environment.
MSGSPEC_FASTPATH_COMMIT := 10c9ac4a8d0a9aacb7854a71f5cf479b47594736
MSGSPEC_FASTPATH_REPO := https://github.com/jcrist/msgspec.git
MSGSPEC_FASTPATH_PATCH := $(CURDIR)/patches/msgspec-0.21.1-struct-c-api.patch
FASTPATH_ROOT := target/fastpath
FASTPATH_MSGSPEC_SRC := $(FASTPATH_ROOT)/msgspec
FASTPATH_MSGSPEC_WHEELS := $(FASTPATH_ROOT)/msgspec-wheels
FASTPATH_TOON_WHEELS := $(FASTPATH_ROOT)/toon-wheels
FASTPATH_VENV := .venv-fastpath
FASTPATH_PYTHON := $(FASTPATH_VENV)/bin/python

.PHONY: lint typecheck test check build conformance qualify bench benchmark-env report public-report audit relock g2 efficiency \
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
	$(TEST_RUST)
	$(TEST_PYTHON)

# Offline-capable by design: the network-dependent cooldown audit is a
# separate target, run in CI and before releases.
check:
	$(CHECK_LINT)
	$(CHECK_TYPECHECK)
	$(CHECK_TEST)

# Build the release extension into the environment that is actually imported.
# `.venv` installs this project editable, so `uv run` resolves
# `python/msgspec_toon/_native.abi3.so` and a separately pip-installed wheel is
# shadowed (and undone by the next re-sync). `maturin develop --release` writes
# the release abi3 build to that path, so what runs is what was measured.
# `benches/build_freshness.py` enforces it rather than trusting it.
build:
	rm -f target/wheels/*.whl
	uv run --no-sync maturin develop --release

conformance:
	uv run --no-sync python conformance/run.py

# One release qualification definition. CI and release workflows invoke this
# target instead of maintaining smaller copies of the command list.
qualify:
	$(QUALIFY_PREPARE)
	$(QUALIFY_SYNC)
	$(QUALIFY_BUILD)
	$(QUALIFY_CHECK)
	$(QUALIFY_CONFORMANCE)
	$(QUALIFY_G2)
	$(QUALIFY_REPORT)
	$(QUALIFY_COPY_EVIDENCE)
	$(QUALIFY_SUMMARY)

benchmark-env:
	uv sync --group bench --locked

bench: benchmark-env build
	uv run --no-sync python benches/bench_codecs.py
	uv run --no-sync python benches/bench_typed.py

report: benchmark-env build
	uv run --no-sync python scripts/release-report.py

# R and its plotting packages are host tools, not project dependencies. This
# target consumes the generated JSON evidence and writes public PNG/Markdown.
public-report: report
	Rscript .github/reporting/render_benchmarks.R conformance/report.json

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

# The efficiency lock: what canonical output costs. Deterministic and offline,
# so it also runs inside `make check` as an ordinary test.
efficiency:
	uv run --no-sync python scripts/efficiency-lock.py

# The G2 proof runs against an instrumented wheel in its own environment, so
# the release wheel every benchmark measures stays free of counters.
g2:
	rm -rf .venv-g2 target/g2-wheels
	UV_PROJECT_ENVIRONMENT=.venv-g2 uv sync --python 3.13 --locked --no-install-project
	uv run --no-sync maturin build --release --features alloc-stats -o target/g2-wheels
	uv pip install --python .venv-g2/bin/python --reinstall --no-deps target/g2-wheels/*.whl
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
