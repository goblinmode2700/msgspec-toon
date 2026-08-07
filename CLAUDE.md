# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

`msgspec_toon` — a native TOON 4.1 codec for Python whose typed path decodes TOON text
**directly into `msgspec.Struct` instances without materializing an intermediate dict/list
tree**, and encodes Structs without `msgspec.to_builtins`. Equivalently: make `msgspec.toon`
exist and behave like `msgspec.json`, not like the wrapper-shaped `msgspec.toml`.

**Public name is `msgspec-toon`.** The local directory name ("toon-millennium-challenge")
is a working title only and must not leak into anything published: if creating a GitHub
repo, name it explicitly (`gh repo create <owner>/msgspec-toon --source=.` — never rely on
`gh`'s directory-name default) and keep the distribution/wheel name `msgspec-toon`.

Why it exists: existing Python TOON codecs are either slow (pure Python), behind the spec
(the Rust `toons` library targets v3.0 and misses nested field groups, so its output can be
*less* token-efficient than JSON), or unfinished. TOON's entire value is the tabular array
with nested field groups (`workers[2]{pid,provider,metadata{alias,region}}:`) — a v4.0
construct. And any wrapper around `msgspec.convert`/`to_builtins` pays more than the codec
saves (measured: the wrapper's preparation step alone exceeds msgspec's whole native encode).

## Where truth lives

- `openspec/specs/` — the authoritative requirements, one capability per directory:
  `toon-parsing`, `toon-encoding`, `typed-codec`, `public-api`, `distribution-quality`.
  Validate with `openspec validate --specs`. Manage changes with the `/opsx:*` commands.
- `docs/implementation-spec/toon-native-codec-implementation-canvas.md` — the engineering
  design of record: architectural decisions AD-001…AD-008, module-by-module code sketches,
  the typed support tiers, benchmark gates G1–G6, phased runbook, and stop conditions.
- `docs/original-spec/` — the original abstract challenge (`spec.md`) and acceptance
  requirements (`requirements.md`). Kept for context; the openspec specs supersede it as
  the working format.

Two requirements decide everything; the rest are floors:
1. **Byte-exact conformance** against the pinned official TOON 4.1 fixture corpus, both
   directions.
2. **Typed decoding builds no intermediate tree** — proven by allocation tracing and
   same-run benchmarks, never asserted.

## Build and test commands

Toolchain: Rust (stable) + PyO3 with `abi3-py313`, maturin build backend, Python ≥ 3.13,
`uv` for all Python environment work (per global doctrine).

```bash
uv sync                                  # create venv with dev deps
uv run maturin develop --release         # build the Rust extension into the venv
uv run pytest                            # run all Python tests
uv run pytest tests/test_typed_roundtrip.py -k vertical_slice   # one test
cargo test                               # Rust unit tests (parser core has no PyO3 dep)
cargo clippy --all-targets -- -D warnings
uv run python benches/bench_typed.py     # typed-path vs wrapper benchmark (gates G3/G4)
```

Benchmarks are same-run comparisons only: never cite figures from a different session, and
bench the release/abi3 build, not a debug build.

## Architecture (the parts that span files)

The pipeline, with no complete builtin tree anywhere between input and target:

```
TOON bytes -> scan.rs (zero-copy line scanner)
           -> parser.rs / header.rs / scalar.rs (structural events, borrowed slices)
           -> Consumer trait (event.rs)
                ├─ UntypedConsumer (untyped.rs)  -> dict/list for type=Any
                └─ TypedConsumer   (typed.rs)    -> final Struct via public constructor
                        ▲ guided by CompiledPlan (plan.rs)
python/msgspec_toon/_plan.py: the ONLY module allowed to import msgspec.inspect;
  lowers annotations to a frozen PlanSpec IR (_types.py) passed into Rust.
encode.rs + shape.rs + writer.rs: reads Struct fields directly via cached EncodePlan,
  classifies arrays for tabular/nested-field-group emission, canonical output only.
python/msgspec_toon/__init__.py: mirrors msgspec.json surface (encode/decode/
  Encoder/Decoder, enc_hook/dec_hook, strict default True), translates native faults.
```

Non-negotiable decisions (full rationale in the canvas):
- **Public constructor, not private slots** (AD-001): Structs are built by calling the
  class; never bind to msgspec's private C layout.
- **Parser knows no Python** (AD-002): parser modules must not import PyO3; keep them
  extractable as a pure-Rust core.
- **One inspection membrane** (AD-003): a msgspec metadata change may touch `_plan.py`
  only.
- **No wire knobs** (AD-005): no delimiter/indent/number-style options, ever. Canonical
  TOON 4.1 is the only output profile.
- **Errors carry coordinates, never payload** (AD-007): faults hold code/line/column/
  schema-known path; tests assert a sentinel from malformed input appears nowhere in the
  exception. Never store payload-derived text in an error.
- **Integers are Python-precision** — round-trip beyond 2**53 exactly; no JavaScript
  numeric domain, no f64 routing except behind a checked range test.
- **In-process only**: no subprocess, socket, or file I/O during a conversion.

Typed support ladder: Tier 0 (challenge shape: scalars, list[T], nested Structs,
Optional, renames, defaults) → Tier 1 (tuples, dicts, literals, tagged unions,
constraints) → Tier 2 (enums, datetime, UUID, Decimal, dataclasses, dec_hook). Document
the matrix; don't claim msgspec.json parity early.

## Status (2026-08-06): Phase 1 vertical slice EXECUTED

The POC is built and measured (see `conformance/report.json`, regenerate with
`uv run python scripts/release-report.py`). Results on the abi3 release wheel:

- **G2 PASS** — typed decode of the challenge payload allocates **zero** intermediate
  dicts/lists (wrapper shape allocates 129 dicts for the same 64-record document).
  Counters live in `_native.alloc_stats()`.
- **G3 PASS at every size** (16→4096 records) — direct typed decode beats untyped
  decode + `msgspec.convert`; at 4 MiB-ish scale building Structs costs the same as
  building the raw dict tree.
- **G4 FAIL, reported honestly** — whole direct encode does not beat
  `msgspec.to_builtins` alone: 2.1x slower at 16 records, ~3% gap at 4096. Cause is
  canvas risk R-02: public stable-ABI `getattr` (~20ns/field) vs msgspec's private C
  slot reads. Already applied: static per-class shape precomputation, interned attr
  names, single-pass row emission, vectorcall construction, pooled row frames. Do not
  mask this; further wins need either wider rows or an upstream (Route A) argument.
- **G1/G5 NOT RUN** — the official 4.1 fixture corpus is not yet fetched/pinned
  (Phase 0 incomplete; `conformance/fixtures.lock.json` says so), and competing
  compiled codecs are not installed here. No conformance claim is made.

Test suite: 25 Rust unit tests (`cargo test` — needs
`PYO3_PYTHON=/opt/homebrew/opt/python@3.13/bin/python3.13`; the uv-managed CPython's
dylib install path breaks test linking) + 38 Python tests (`uv run pytest`).
Known POC gaps: comma delimiter only, no keyed tabular objects, Tier 0 + partial
Tier 1 types only, float canonical form unverified against fixtures, no recursive
Struct support. Next milestones: pin the fixture corpus (Phase 0), then Phase 2
untyped conformance per canvas §17.
