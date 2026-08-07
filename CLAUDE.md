# CLAUDE.md

This file guides coding agents working in this repository (`AGENTS.md` is a symlink to
this file so Codex and other agents read the same context).

## The goal, precisely

Build the **most token-efficient and fastest TOON 4.1 codec for Python**, natively
integrated with **msgspec==0.21.1** (exact pin): the typed path decodes TOON text
**directly into `msgspec.Struct` instances with zero intermediate dict/list tree**, and
encodes Structs by direct field reads, never `msgspec.to_builtins`. Equivalently: make
`msgspec.toon` exist and behave like `msgspec.json`, not like the wrapper-shaped
`msgspec.toml`. Both metrics are gated and published as generated evidence
(`conformance/report.json`): tokens under named tokenizers (tiktoken `o200k_base`) and
speed as same-run ladders plus frozen-baseline A/B. Never trade conformance, the
zero-intermediate-tree invariant (G2), or payload-safe errors for either metric.

## Current state and next round

Read **`HANDOFF.md`** before doing anything — it is the authoritative state-of-the-world:
what is proven at `v0.2.0` (538/538 corpus, G2/G3/G5/T1 pass, G4 honest miss), the open
items, and the invariants that must not regress. The adversarial review is complete in
`docs/adversarial-review-v0.2.0.md`. It found three P0 containment defects and a bounded
correctness, evidence, and efficiency queue. **The next round is the last-mile loop in
`LAST-MILE.md`.** Use `/last-mile` for iterative work. Fixes must keep `make check`, the
corpus run, and G2/G3/G5 green. Performance changes require same-session A/B.

### Agent continuation contract

- Read `LAST-MILE.md` before code changes.
- Select the first unblocked queue item unless the user names another item.
- Use one falsifiable hypothesis and one focused change per checkpoint.
- Reject changes that regress conformance, G2, G3, G5, or payload safety.
- Keep canonical bytes stable unless the official corpus requires a change.
- Update generated evidence and the handoff before each checkpoint commit.
- Continue until a documented stop condition occurs.
- Do not create another orchestration harness.

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

## Status (2026-08-07): optimized, token-measured, perfect corpus

Since the section below was written, the `optimize-speed-and-token-efficiency` change
landed (23/24 tasks): **G1 is now a perfect 538/538 corpus score with zero declared
divergences** (spec-defined wire options `delimiter`/`indent`/`indent_size` implemented —
the AD-005 amendment is in the toon-encoding spec); **token efficiency is measured**
(`make`-able via `benches/bench_tokens.py`, tiktoken o200k_base: canonical TOON =
0.61–0.64× JSON tokens on the challenge shape, incumbents = 1.25× JSON; the tab-delimiter
folklore measured at noise level and published as a finding); **six speed candidates
adopted with same-session A/B proof** against the frozen `v0.1.0-conformant` baseline
(`make baseline` + `benches/ab.py`): typed decode −15→−24%, untyped decode −10→−21%,
encode −4→−8%. Ledger with hypotheses, deltas, and open candidates (E3, formal profiling)
in `benches/optimization-ledger.json`, embedded in the report. G4 remains the honest R-02
miss (~10% at 4096 after E1/E2). Tag: `v0.2.0`.

## Status (2026-08-06): Phases 0–2 executed; conformance measured

Evidence: `conformance/report.json` (regenerate with `make report`). All measurements
on the installed abi3 release wheel. `make check` / `make bench` / `make audit` are the
entry points.

- **G1 — official 4.1.1 corpus (538 tests, pinned + hash-locked, vendored in
  `conformance/fixtures/`): ZERO failures.** Decode 357/359, encode 156/179,
  strict-error fixtures 83/84 — every non-pass is one of 25 tests requiring encoder
  wire options (`delimiter`, `indentSize`) that AD-005 deliberately does not expose;
  they are published as declared divergences. Run: `uv run python conformance/run.py`.
- **G2 PASS** — typed decode allocates zero builtin dicts/lists while building 129
  Structs and 1 final list on the same document (wrapper: 129 builtin dicts). Counters
  live behind the non-default `alloc-stats` feature in `src/containers.rs`, the only
  module permitted to construct a Python container (`clippy.toml` enforces it). Run
  `make g2`; the release wheel carries no instrumentation.
- **G3 PASS at every size** — typed decode beats untyped + `msgspec.convert`.
- **G5 PASS at every size, both directions** — 2–6.5x faster than `toons` 0.7.0,
  ~20x faster than `python-toon` 0.1.3, with output 2.9x smaller than both (their
  fallback form exceeds compact JSON). The incumbent pipeline
  (`to_builtins`+python-toon / python-toon+`convert`) loses 19–51x.
- **G4 FAIL, reported honestly** — whole direct encode does not beat
  `msgspec.to_builtins` alone (2.3x at 16 records → ~10% at 4096). Canvas risk R-02:
  public stable-ABI `getattr` vs msgspec's private C slot reads. Mitigations already
  applied: static per-class shapes, interned names, single-pass rows, vectorcall,
  pooled frames. Don't mask it; further wins need an upstream (Route A) argument.

Decode grammar is corpus-complete: keyed tabular objects (`k[N:]{f}:`), tab/pipe
delimiters, `[]` literals, nested field groups, non-strict leniencies (malformed-header
fall-through, count tolerance, LWW duplicates), blank-line strictness. Encoder emits
canonical forms incl. keyed tabular, JS-style float spelling, numeric-like string
quoting. Test suite: 32 Rust + 39 Python tests. Remaining gaps: encoder wire options
(deliberate), typed Tier 1/2 long tail, recursive Structs, `indentSize≠2` decode.
