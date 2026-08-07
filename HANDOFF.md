# HANDOFF — state of the world for the next agent

_Last updated at v0.3.0. Read CLAUDE.md (or AGENTS.md, same
file) first. Then read `docs/adversarial-review-v0.2.0.md` and `LAST-MILE.md`._

## Next action

Phase A is done (containment: F-01/F-02/F-03). Phase B is done except **F-12**, which is
next: alternate the A/B blocks and publish spread. It is well-motivated now — this
session measured run order alone at 1–3%, larger than several published deltas, and every
row of an instrumented-vs-clean comparison came back with the physically impossible sign.
After that, Phase C (typed correctness) starts at F-04. Use `/last-mile`.

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
| G2 no intermediate tree | **pass, two-sided** (typed: 0 builtin dicts/lists, 129 Structs + 1 final list; wrapper: 129 builtin dicts) | `make g2` → `conformance/allocation-proof.json`, `tests/test_typed_allocations.py` |
| G3 typed beats wrapper | **pass at 16/64/512/4096 records** | `bench_typed.py` |
| G5 codec floor | **pass both directions**: 2–6.5× faster than `toons` 0.7.0, ~20× vs `python-toon` 0.1.3 | `bench_codecs.py` |
| vs the real incumbent pipeline | 19–51× faster | `bench_typed.py` incumbent rows |
| Token efficiency (T1) | **pass**: canonical TOON = 0.61–0.64× JSON tokens on record payloads; incumbents = 1.25× JSON | `bench_tokens.py` |
| Tab-delimiter folklore (T2) | **measured false** at noise level; published as a finding | report `token_efficiency.findings` |
| Type-support boundaries | **generated, not asserted**: 11 supported, 2 parity-rejects, 13 unsupported, 1 inert, 0 silently wrong. `conformance/report.json` carries the live counts; this row is a snapshot | `conformance/support_matrix.py`, `tests/test_support_matrix.py` |
| G4 encode vs `to_builtins` alone | **fail, honestly reported**: 2.16× at 16 records, 1.11× at 4096 (v0.3.0, mean-across-workers). Stable-ABI `getattr` vs msgspec's private C slot reads (canvas risk R-02) | report `known_divergences_and_gaps` |
| Optimizations | 6 adopted, re-qualified under the F-12 harness: typed decode −13→−20%, untyped decode −10→−20%, codec encode −6→−8% — all above the session noise floor. Typed encode at 16/64 records is **below noise and reported as unresolved** | `benches/optimization-ledger.json`, report `speed_ab_latest` |
| A/B rigor | **mean across 10 worker processes** (never a minimum); one metric per block, alternating `B C C B`, t-test at alpha 0.95, per-row minimum detectable effect; a slowdown must reproduce at double power to fail | `benches/ab.py`, `benches/ab-guard.json`, `benches/ab-baseline.json` |
| Regression gates | **token/byte lock** (any drift fails) and **speed gate vs the latest release** (a reproduced slowdown exits non-zero). Both proven to fire by deliberate perturbation | `conformance/efficiency.lock.json`, `make ab` |

Wire options: `delimiter` (`","`/`"\t"`/`"|"`), `indent`, `indent_size` — exactly TOON
4.1's own option domain, spelled in the wire, defaults byte-identical to canonical.
The old AD-005 blanket prohibition was amended on corpus evidence (see
`openspec/specs/toon-encoding/spec.md`).

## Open items (tracked, not forgotten)

1. **G2 evidence — rebuilt (F-05).** Counters moved behind the non-default `alloc-stats`
   feature and into `src/containers.rs`, the only module allowed to construct a Python
   container (enforced by `clippy.toml`, not by convention). `make g2` builds the
   instrumented wheel into `.venv-g2` and generates the proof artifact; the release
   report reads it and refuses to fabricate it. Measured: removing the counters from
   release changed nothing outside noise, so the older G3/G5 margins stand.
2. **Type-support gaps — generated (F-11).** `conformance/support_matrix.py` is the one
   maintained statement of what works, with a probe for this codec and one for
   `msgspec.json` per entry; `tests/test_support_matrix.py` fails when a declaration stops
   matching reality in either direction. The report's gap list is generated from it (4
   freehand entries → 18). Status distinguishes a rejection from a silent divergence.
3. **Build identity — enforced (F-21, new).** `.venv` is an *editable* install, so
   `uv run` imports `python/msgspec_toon/_native.abi3.so`, and a pip-installed wheel is
   shadowed. `make build` is now `maturin develop --release`, and
   `benches/build_freshness.py` refuses to publish a number from a stale or instrumented
   extension. This bit for real: one A/B this session silently measured the previous
   checkpoint's binary.
4. **Containment (P0) — closed.** A declared count no longer sizes an allocation, and one
   shared nesting ceiling (`src/limits.rs`, `MAX_NESTING_DEPTH`) now bounds indentation,
   header field groups, encoder writing, and encoder shape discovery. Depth is a hard
   fault in both strict and non-strict mode. Both OpenSpec capabilities state the limit.
   Same-session A/B showed no cost. The remaining review queue is Phase B onward.
5. **Adversarial review sweep — complete.** The durable findings are in
   `docs/adversarial-review-v0.2.0.md`. The executable queue is in `LAST-MILE.md`.
   The review covered:
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
6. **E3 (fused row templates)** — unattempted encode candidate; hypothesis in
   `benches/optimization-ledger.json`. G4's remaining ~10% gap at 4096 is the target.
7. **Formal profiling** (change task 4.1) — candidates were chosen by inspection and
   validated by A/B; a flamegraph pass may reveal candidates nobody guessed.
8. **pyo3 cooldown pin** — `=0.29.0` lifts when 0.29.2 ages past 14 days
   (~2026-08-19); `make audit` confirms. Then `cargo update -p pyo3` + full re-test.
9. **Typed support ladder** — the authoritative list is now
   `conformance/support_matrix.py`, not this file. Phase C of `LAST-MILE.md` implements
   the Tier 1 items; Tier 2 (enums, datetime, UUID, Decimal, dataclasses) is untouched.
   Note `decimal_format`/`uuid_format` are dropped by the `Encoder` constructor but
   rejected by the `encode()` function — the two entry points disagree.
10. **Keyed tabular in the typed path** — decode works via Dict frames for
   `dict[str, Struct]`; the D1 memo doesn't cover keyed rows (hash path). Minor.
11. **Recursive Struct types** — the plan compiler recurses until `RecursionError`
   (catchable, not a crash). Detect the cycle and error clearly, or support them.
12. **openspec changes** — `refine-benchmarks-and-tooling` (16/18) and
   `optimize-speed-and-token-efficiency` (23/24) remain open with only
   deferred/time-gated tasks; archive them (`openspec archive`) when their stragglers
   close. Main specs are already synced.
13. **Wheel matrix + CI** — only local macOS arm64 wheels exist. The canvas §17
   Phase 6 (abi3 wheels for 5 platforms, syscall checks, CI) is untouched.

## Invariants — do not regress these

- **No intermediate tree** in the typed path (`make g2`: zero builtin containers for a
  target with no `Any`), no `to_builtins` anywhere in encode.
- **Errors never carry payload** (AD-007): coordinates + static templates only.
- **Default output byte-identical** across encoder instances; only spec-defined,
  wire-declared options exist.
- **msgspec==0.21.1 exact**; the only module importing `msgspec.inspect` is
  `python/msgspec_toon/_plan.py`.
- **14-day dependency cooldown**: uv enforces natively (`tool.uv.exclude-newer`);
  Rust via pin + `make audit`. Overrides need a commit-message justification.
- **Every perf claim is same-session A/B** on a build `benches/build_freshness.py` has
  verified is current and uninstrumented, using the mean across worker processes (never a
  minimum), alternating blocks, and a two-sample t-test at alpha 0.95. A change smaller
  than its published minimum detectable effect is reported as no significant difference,
  never as a win. Every corpus claim is a fresh `conformance/run.py` run.
- **Two baselines, two jobs.** `.venv-baseline` (`v0.1.0-conformant`) is the *story*: what
  the optimization round bought, reported and never gated. `.venv-guard` (latest release)
  is the *gate*: `make ab` exits non-zero on a slowdown that reproduces. A distant baseline
  cannot police a regression — measured, a 24% slowdown reads as +2.2% against the story
  baseline. **The guard tag is derived from the latest release, and the gate refuses to run
  against a guard built from an older one**, so "re-cut it at every release" is a check
  rather than a promise: after tagging, run `make guard`.
- **Token and byte counts are locked** in `conformance/efficiency.lock.json`. Any change in
  either direction fails `tests/test_efficiency_lock.py`; update it deliberately and say in
  the commit why the counts moved. After ANY change: corpus zero failures,
  G2/G3/G5 green, 75 unit tests green (`make check`).
- Parser modules must not import PyO3 (canvas AD-002).

## Commands

```bash
uv sync && uv run maturin build --release && \
  uv pip install --force-reinstall --no-deps target/wheels/*.whl   # build+install
make check        # lint (ruff, rustfmt, clippy -D warnings, both feature sets) + mypy + tests
make g2           # instrumented build in .venv-g2: the G2 proof and its artifact
make guard        # build the gate baseline (latest release) into .venv-guard
make ab           # THE SPEED GATE: fails on a reproduced slowdown vs the guard
make ab-story     # report vs the frozen v0.1.0 baseline; never gates
make efficiency   # show any drift in the token/byte lock
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
