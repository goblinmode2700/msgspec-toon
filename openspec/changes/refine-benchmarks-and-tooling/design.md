# Design notes

## Exact pin

`dependencies = ["msgspec==0.21.1"]`. The plan compiler (`_plan.py`) is a compatibility
membrane over an experimental API (`msgspec.inspect`); an exact pin makes the POC's
qualification statement precise. Loosening back to a range is a deliberate future change
that lands together with CI coverage against newer msgspec releases, not a default.

## Makefile

One entry point per concern, composing both languages. Rust side (my call): `cargo fmt
--check`, `cargo clippy --all-targets -- -D warnings`, `cargo test` — the same three
gates the canvas CI design (§18) names for pull requests.

```
make lint       # ruff check + ruff format --check + cargo fmt --check + cargo clippy
make typecheck  # mypy python/
make test       # cargo test + pytest
make check      # lint + typecheck + test
make build      # maturin release wheel + install into .venv
make bench      # benches/bench_codecs.py + benches/bench_typed.py (release wheel only)
make report     # scripts/release-report.py
```

`cargo test` needs a linkable libpython; the Makefile exports
`PYO3_PYTHON=/opt/homebrew/opt/python@3.13/bin/python3.13` (the uv-managed CPython's
dylib install-name breaks test linking; already noted in CLAUDE.md).

## Timing utility

`benches/_timing.py` exposes a single `best_of(fn, *, repeats, target_seconds) -> Timing`
helper (autoranged batches, min-of-repeats, returns microseconds plus the batch count so
reports can state methodology). Every benchmark script imports it; `bench_typed.py`'s
private copy is deleted. A decorator form `@timed` may wrap named benchmark cases so a
script is a flat list of cases, not a hand-rolled harness.

## Benchmark matrix

Rows per payload size (16/64/512/4096 records, challenge shape), all same-run:

| row | encode | decode |
|---|---|---|
| ours typed | `msgspec_toon.Encoder.encode(doc)` | `msgspec_toon.Decoder(T).decode(text)` |
| ours untyped | — | `msgspec_toon.decode(text)` |
| incumbent pipeline | `python_toon.encode(to_builtins(doc))` | `msgspec.convert(python_toon.decode(text), T)` |
| python-toon 0.1.3 raw codec | `python_toon.encode(tree)` | `python_toon.decode(text)` |
| python-toon latest raw codec | same, version recorded | same |
| toons (Rust), if installable | raw codec rows (G5 floor) | raw codec rows |
| msgspec.json native (context) | `msgspec.json.encode(doc)` | `msgspec.json.Decoder(T).decode(json)` |
| to_builtins alone (G4) | `msgspec.to_builtins(doc)` | — |

Two python-toon variants cannot usually be co-installed under one environment; the
harness runs the second variant in a separate uv environment and merges results, with
each row naming the exact installed version. If the latest release equals 0.1.3, one row
suffices and the report says so. Caveat rows: python-toon predates spec 4.x — its output
for the nested-metadata payload will not be byte-identical to ours (fallback form); the
report must record byte sizes per codec so the token-efficiency story stays visible, and
must not treat its output as conformant reference bytes.

## toons prior-art review

Pin the version studied (0.7.0 per the design of record, plus latest if newer). Review
targets: line scanning strategy (memchr/SIMD use), delimiter and quoting handling,
number parse/format paths, tabular-array detection on encode, error position model,
Python object construction techniques (PyO3 patterns, interning, vectorcall), and its
known v3.0-era gaps (nested field groups absent, pre-canonical number formatting, `[0]:`
empty-array spelling) so none of its behaviors leak into ours. Output:
`docs/prior-art/toons.md` with adopted / rejected / misses-found lists; every miss found
in our Rust core becomes a tracked task or fix in this change.
