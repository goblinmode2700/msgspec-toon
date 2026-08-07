# HANDOFF — state of the world for the next agent

_Last updated: 2026-08-07, at v0.2.0. Read CLAUDE.md (or AGENTS.md, same file) first;
this document is the delta: what is done, what is open, and what the next round —
a **review sweep** — should attack._

## The goal, precisely

Build the **most token-efficient and fastest TOON 4.1 codec for Python**, integrated
natively with **msgspec==0.21.1** the way `msgspec.json` is: the typed path decodes
TOON text directly into `msgspec.Struct` instances with **zero intermediate dict/list
tree**, and encodes Structs without `msgspec.to_builtins`. Both metrics matter and both
are measured: **tokens** (tiktoken `o200k_base`, `benches/bench_tokens.py`) and
**speed** (same-run microbenchmarks, `benches/bench_typed.py` / `bench_codecs.py`,
plus a frozen-baseline A/B harness `benches/ab.py`). Claims exist only as generated
evidence in `conformance/report.json` — never as assertions.

## Where things stand (all verified at v0.2.0)

| claim | state | evidence |
|---|---|---|
| TOON 4.1 conformance | **538/538 fixtures, zero divergences** (corpus pinned+hash-locked at toon-format/spec v4.1.1) | `conformance/run.py`, `fixtures.lock.json` |
| G2 no intermediate tree | **pass** (0 dicts/lists typed; wrapper builds 129) | `_native.alloc_stats()`, `tests/test_typed_allocations.py` |
| G3 typed beats wrapper | **pass at 16/64/512/4096 records** | `bench_typed.py` |
| G5 codec floor | **pass both directions**: 2–6.5× faster than `toons` 0.7.0, ~20× vs `python-toon` 0.1.3 | `bench_codecs.py` |
| vs the real incumbent pipeline | 19–51× faster | `bench_typed.py` incumbent rows |
| Token efficiency (T1) | **pass**: canonical TOON = 0.61–0.64× JSON tokens on record payloads; incumbents = 1.25× JSON | `bench_tokens.py` |
| Tab-delimiter folklore (T2) | **measured false** at noise level; published as a finding | report `token_efficiency.findings` |
| G4 encode vs `to_builtins` alone | **fail, honestly reported**: 2.2× at 16 records, ~10% at 4096. Stable-ABI `getattr` vs msgspec's private C slot reads (canvas risk R-02) | report `known_divergences_and_gaps` |
| Optimizations | 6 adopted with same-session A/B vs frozen `v0.1.0-conformant` wheel: typed decode −15→−24%, untyped decode −10→−21%, encode −4→−8% | `benches/optimization-ledger.json` |

Wire options: `delimiter` (`","`/`"\t"`/`"|"`), `indent`, `indent_size` — exactly TOON
4.1's own option domain, spelled in the wire, defaults byte-identical to canonical.
The old AD-005 blanket prohibition was amended on corpus evidence (see
`openspec/specs/toon-encoding/spec.md`).

## Open items (tracked, not forgotten)

1. **Review sweep — the next round's job.** This codebase was written fast under
   fixture-driven iteration. Nobody has adversarially reviewed it. Priority targets:
   - `src/typed.rs` — the D1 row-memo state machine (cursor/complete/disabled
     transitions across nested structs, skip subtrees, Any subtrees, memo push/pop
     pairing with List frames). Most subtle code in the repo.
   - `src/encode.rs` `unsafe` block in `write_scalar_obj` (exact-type pointer dispatch,
     `cast_unchecked`) and the two `from_utf8_unchecked` uses in `src/pyval.rs` /
     `src/untyped.rs` — verify the validity arguments actually hold on every path
     (especially: quoted-key slices, cells from tab-delimited rows, BOM edge).
   - Non-strict semantics: fall-through and leniency paths are fixture-shaped; look
     for inputs the corpus doesn't cover (e.g. malformed headers in list items,
     keyed rows in non-strict, tab-indent depth arithmetic in `scan.rs`).
   - Error positions: columns are best-effort in places (unescape offsets, value_at
     arithmetic); verify off-by-ones.
   - `benches/ab.py` rigor: subprocess-per-side is same-session but not interleaved;
     consider alternating repetitions to reduce thermal bias (observed ±15% drift on
     hot runs).
   - Payload-safety audit: grep every `format!`/error message for payload-derived
     content (AD-007). Tests cover sentinels; a reviewer should cover the negative
     space.
2. **E3 (fused row templates)** — unattempted encode candidate; hypothesis in
   `benches/optimization-ledger.json`. G4's remaining ~10% gap at 4096 is the target.
3. **Formal profiling** (change task 4.1) — candidates were chosen by inspection and
   validated by A/B; a flamegraph pass may reveal candidates nobody guessed.
4. **pyo3 cooldown pin** — `=0.29.0` lifts when 0.29.2 ages past 14 days
   (~2026-08-19); `make audit` confirms. Then `cargo update -p pyo3` + full re-test.
5. **Typed support ladder** — Tier 1 gaps (tagged unions, `array_like`,
   `forbid_unknown_fields` is done, constraints are parsed but NOT enforced) and all
   of Tier 2 (enums, datetime, UUID, Decimal, dataclasses). `decimal_format`/
   `uuid_format` params are accepted but inert — either implement or fail loudly.
6. **Keyed tabular in the typed path** — decode works via Dict frames for
   `dict[str, Struct]`; the D1 memo doesn't cover keyed rows (hash path). Minor.
7. **Recursive Struct types** — will infinitely recurse in the plan compiler. Detect
   and error cleanly, or support.
8. **openspec changes** — `refine-benchmarks-and-tooling` (16/18) and
   `optimize-speed-and-token-efficiency` (23/24) remain open with only
   deferred/time-gated tasks; archive them (`openspec archive`) when their stragglers
   close. Main specs are already synced.
9. **Wheel matrix + CI** — only local macOS arm64 wheels exist. The canvas §17
   Phase 6 (abi3 wheels for 5 platforms, syscall checks, CI) is untouched.

## Invariants — do not regress these

- **No intermediate tree** in the typed path (G2 counters must stay 0), no
  `to_builtins` anywhere in encode.
- **Errors never carry payload** (AD-007): coordinates + static templates only.
- **Default output byte-identical** across encoder instances; only spec-defined,
  wire-declared options exist.
- **msgspec==0.21.1 exact**; the only module importing `msgspec.inspect` is
  `python/msgspec_toon/_plan.py`.
- **14-day dependency cooldown**: uv enforces natively (`tool.uv.exclude-newer`);
  Rust via pin + `make audit`. Overrides need a commit-message justification.
- **Every perf claim is same-session A/B** vs the frozen baseline; every corpus claim
  is a fresh `conformance/run.py` run. After ANY change: corpus zero failures,
  G2/G3/G5 green, 75 unit tests green (`make check`).
- Parser modules must not import PyO3 (canvas AD-002).

## Commands

```bash
uv sync && uv run maturin build --release && \
  uv pip install --force-reinstall --no-deps target/wheels/*.whl   # build+install
make check        # lint (ruff, rustfmt, clippy -D warnings) + mypy strict + all tests
make bench        # bench_codecs + bench_typed (release wheel, rebuilds first)
uv run python benches/bench_tokens.py                              # token gates
uv run python conformance/run.py                                   # 538-test corpus
make baseline && make ab                                           # frozen-baseline A/B
make report       # regenerate conformance/report.json (the evidence artifact)
make audit        # dependency-age cooldown check (network)
```

Quirk: `cargo test` needs `PYO3_PYTHON=/opt/homebrew/opt/python@3.13/bin/python3.13`
(the Makefile exports it; the uv-managed CPython's dylib install-name breaks test
linking).

## History

`v0.0.1-poc` (Phase 1 vertical slice) → `v0.1.0-conformant` (zero fixture failures,
25 option divergences) → `v0.2.0` (perfect 538/538, options, tokens measured,
optimization round). Full narrative in `git log`; design of record in
`docs/implementation-spec/`; requirements in `openspec/specs/`.
