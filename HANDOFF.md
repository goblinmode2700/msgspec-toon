# HANDOFF — state of the world for the next agent

_Last updated at the qualified S6 typed-decode checkpoint. Read
**`OBJECTIVE.md`** first — it states what this project is
minimizing, the constraints it may not break, and why the optimization has converged. Then
CLAUDE.md (or AGENTS.md, same file), then `LAST-MILE.md`._

## Next action

**The typed-decode qualification stop is cleared.** Checkpoint 33 adopted S4: tabular leaf cells
now use one fused `scalar_field` event. The default consumer implementation remains the original
`key` then `scalar` sequence, while the typed Struct path performs one field lookup, conversion,
duplicate check, and direct placement. Against the exact S3 wheel, typed decode improved 4.4% at
64 records, 5.7% at 512, and 4.1% at 4096. The untyped control was parity at 64 and 4096 and 1.6%
faster at 512, so the change did not move cost into the generic fallback.

Against the immutable phase-8 capability checkpoint, 64 records is now parity; 512 is 5.0%
faster; and 4096 is 3.1% faster. OpenSpec tasks 11.5 and 12.4 are complete. The remaining release
work is task 14.3's full artifact workflow, task 14.4's final evidence/archive checkpoint, and the
authorized publication stop in 14.5. Do not start a larger row-program rewrite without a new
symbolized profile showing a mechanism beyond the accepted fused field events.

Checkpoint 34 adopted S5 after that profile showed nested group opening still paid the generic
`key` then `start_object` plan transition. `start_object_field` now defaults to the old sequence,
while the typed Struct override carries the already resolved child plan directly into frame setup.
Against the exact S4 wheel, typed decode improved 1.6% at 64 records, 1.9% at 512, and 1.1% at
4096. Untyped controls were unchanged. The next measured mechanism is nested Struct return:
Checkpoint 35 then adopted S6: `end_object_field` completes a nested Struct directly into its
known parent field, while every non-Struct, `Any`, skipped, and generic consumer path retains
ordinary `end_object`. Against the exact S5 wheel, typed decode improved 0.8% at 64 records under
a high-power focused run, 1.5% at 512, and 1.1% at 4096. Untyped controls were unchanged.

The post-S6 profile no longer shows `expected_plan_or_fault` as a top stack and reduces generic
`place` to 6 samples. The remaining parser-local candidate is S7: compile the header's recursive
`FieldNode` tree once into a flat, borrowed row-op tape and interpret it for each row. The profile
shows `emit_row_fields` as the largest native self-time (78 samples), but that attribution includes
loop and inlined event work. Adopt S7 only if exact-S6 typed and untyped ladders resolve a win;
otherwise revert it and stop the row-dispatch program.

The capability implementation, sustained fuzzing,
canonical qualification, corpus, G2, G3, G5, release guard, version delta, and generated report
are complete, including OpenSpec tasks 11.5 and 12.4. Against the immutable phase-8 checkpoint,
the pre-S3 source reproduced typed-decode slowdowns at 64 records (+4.8%, MDE 1.1%), 512 (+4.8%,
MDE 1.2%), and 4096 (+3.7%, MDE 1.0%). S3 and S4 together remove all three misses. The complete
release guard against `v0.4.0` passes and shows typed decode 3.6-6.1% faster. The closer phase-8
comparison now also passes the qualification requirement.

Four mechanism-led remedies are accepted: restoring `finish_struct` inlining, fusing tabular
leaf field dispatch, fusing nested field-group opening, and returning nested Structs directly to
their parent field. Four earlier remedies were rejected and reverted: direct references into
the plan arena, merging array-like and object Struct frames, and compile-time strict/permissive
specialization.
A final cold outlining of permissive scalar conversion also failed to remove the effect and was
reverted. The accepted default-Encoder cache and parser preflight split repair separate functional
encode and ordinary parser costs. Do not retry these four designs. Owner publication authority was
explicitly granted; the remaining stop is the full release-artifact qualification workflow.

Current completed evidence: 19 supported, 2 parity rejects, 8 unsupported, zero silent failures;
538/538 corpus and 84/84 strict errors; 259 Python tests passed with 7 expected skips; 39 Rust
tests passed; six G2 probes passed with zero intermediate builtin containers; both 900-second fuzz
targets completed 166.9 million total executions with zero artifacts. `make bench` passes every
G3 and G5 cell and records the known G4 miss through 512 records, with G4 passing at 4096.
`make report` generated `conformance/report.json` for `0.2.0b1`. The 12-wheel-plus-sdist workflow
has not run for this candidate because the closer A/B stop fired first.

The active OpenSpec change remains `qualify-beta-release-and-expand-msgspec-parity`. Tasks 11.5,
12.4, 13.5, 14.1, and 14.2 are complete. Tasks 14.3-14.5 remain open. Do not archive it.

## Previous published checkpoint

**`0.1.0b3` is published and release trust is complete.** Public source revision
`f0546e65b95295f7b27858f7387ee5d73d04f19c` passed the complete publication-disabled
workflow in [GitHub Actions run 31310610453](https://github.com/goblinmode2700/msgspec-toon/actions/runs/31310610453):
12 target-native wheels plus one sdist were built once, digest-bound, installed outside
the checkout, and verified. The generated report records 538/538 conformance, G2, G3,
and G5; the first evidence attempt passed every G5 cell. Publication and GitHub release
jobs were skipped. After explicit owner authorization, tag `v0.1.0b3` triggered
[run 31336808348](https://github.com/goblinmode2700/msgspec-toon/actions/runs/31336808348).
OIDC publication succeeded for exactly 12 wheels and one sdist. All 13 PyPI digests match
the tagged manifest, all provenance objects name `goblinmode2700/msgspec-toon`,
`wheels.yml`, and environment `pypi`, and `pypi-attestations` cryptographically verified
every file. Clean CPython 3.13 ABI3 and CPython 3.14t installs passed typed round trips.

The final GitHub release-attachment job initially failed because it ran without a checkout
or explicit repository context. No package upload failed. The exact tagged-run report and
manifest were attached manually and byte-verified; main commit `7f61585` adds `GH_REPO`
plus a regression test, and its default validation run passed. The GitHub release is marked
prerelease. No API-token fallback was used.

The earlier `67171fb` evidence attempt recorded one strict G5 miss: irregular decode at 512 records
was 477.64 microseconds for msgspec-toon versus 472.82 microseconds for `toons` (1.02%
slower; msgspec-toon worker spread 2.53%). An independent rerun of only the evidence job,
against the same revision and verified artifacts, passed every G5 cell; that row measured
415.91 versus 475.67 microseconds. Both outcomes are part of the handoff. The gate,
payload selection, and mean-across-ten-workers estimator were not changed. The later
`f0546e6` qualification passed G5 on its first evidence attempt.

The active OpenSpec change is
`qualify-beta-release-and-expand-msgspec-parity`. Tasks 1 through 10 are complete. The first
unblocked item is task 11.1: differential tests for array-like Structs. Phase 10 replaced
recursive owned plans with an indexed, identity-keyed graph and a bounded native arena.
Self-recursive and mutually recursive Structs now decode directly, including defaults and
renamed fields. The recursive allocation proof builds zero intermediate dicts or lists. The
512-entry annotation cache remains the only bounded owner, and hostile depth still reports the
static `depth_limit` fault. Same-session A/B found no reproduced typed-decode or cached
Decoder-construction regression. Phase 7 added public
`TypePlanError(TypeError)` with stable codes and schema paths; recursive, nested mapping-key,
unsupported-union, array-like, custom-without-hook, inspection, and native-plan failures no
longer leak implementation exceptions. Task 2.4 uses harmless command seams to
prove all 12 qualification boundaries fail closed and a parsed release-job DAG to prove a
failed validation blocks every downstream job. Capability work starts at task 7 and is
targeted to `0.2.0b1`. Phase 9 added date/time, UUID, exact Decimal, and Enum encoding
before the caller hook. The matrix is 15 supported, 2 parity rejects, 12 unsupported, and
zero silent failures. All beta-2 locked payloads kept their bytes; one new seven-scalar token
fixture was added. Same-session phase-8 A/B rejected two slower designs before the adopted
hook membrane cleared all five focused encode families. Do not archive the change.

**A bounded improvement round was explicitly reopened on 2026-08-07. Read
`OBJECTIVE.md` before planning any work.**

Tokens remain at their constrained optimum: all three tabular fallbacks are spec-required
(T5), so the remaining token levers belong to the caller. The old speed conclusion is now
superseded: symbolized profiles found mechanisms that the previous candidate-driven rounds
did not inspect. H3 still limits what can be claimed, so every new speed candidate remains
conditional on that measured floor.

The earlier three-round loop converged on the candidates it had measured. A later
symbolized profile found new mechanisms and the owner explicitly authorized a bounded
continuation. The ordered queue is now:

1. **C-00 — DONE at checkpoint 10.** Scalar bounds/multiples, Unicode string length,
   Python-regex search, and list/tuple/dict lengths are enforced directly from the compiled
   plan. The generated matrix is now 12 supported, 2 parity-rejects, 13 unsupported,
   0 silently ignored, 0 silently wrong. The first inline-plan representation reproduced a
   2.0% keyed-decode slowdown and was rejected; boxing constraints removed the regression
   on the full release-guard gate.
2. **H3 — DONE at checkpoint 11; the proposed cause was falsified.** A third-path `v0.4.0`
   wheel measured `entry decode@512` at -0.5% against the `v0.4.0` guard, MDE 1.1%, with
   2.5% canary spread. Source-path-driven layout did not reproduce the old positive bias.
   The focused resolution is 1.1% in that session; practical full-ladder resolution remains
   roughly 1–2% on quiet rows and higher where the published per-row MDE says so.

3. **H5 — DONE at checkpoint 12.** Parent Python orchestration is negligible; process
   isolation and discarded warmup are intentional. Metric-unrelated sampler setup was not:
   selecting setup by metric cut a fixed-one-loop `entry decode@512` child from 43.04 ms to
   34.24 ms (-20.5%) without changing the timer or estimator.
4. **P4a — DONE at checkpoint 13.** The generated ladder now measures the public
   functional API. At 16 records, functional decode is 86% slower than reusable decode and
   functional encode is 147% slower; the fixed construction cost fades with payload size.
5. **P4b decode — ADOPTED.** Following msgspec 0.21.1 itself, the existing bounded
   annotation cache now retains an opaque native compiled plan, not Decoder objects. Typed
   Decoder construction fell from ~3.36 us to ~0.21 us; functional decode improved 40% at
   16 records, 16% at 64, and 4.5% at 512 in same-session A/B.
6. **E8 — ADOPTED.** The first-byte split from `serde_toon_format` lets ordinary strings
   skip numeric-state tracking. The >100k differential oracle stayed exact; same-session
   A/B resolved typed encode 3.0–5.3%, entry encode 16.5–17.1%, and untyped encode
   2.7–4.0% faster across 16/64/512/4096 records.
7. **P4c encode-plan reuse — REJECTED.** An opaque native plan behind the existing
   512-entry class cache was source-isolated against checkpoint 15. Functional encode
   moved -1.8/-2.1/+0.3/+0.0%; none resolved. The remaining compilation is not the
   functional encode floor. The prior-art boundary remains recorded in
   `docs/implementation-spec/prior-art-native-codec-2026-08-07.md`.
8. **D7 quote-free cell scan — REJECTED.** A combined `memchr2` quote/delimiter scan was
   equivalent across 411,771 generated rows, but typed and entry decode stayed at parity;
   untyped decode trended slower. The prior two-pass common path remains.
9. **D8 absent-`Any` forwarding — ADOPTED.** Guarding before `AnyEvent` construction and
   outlining the forwarding routine as cold improved typed decode 7.1–10.0% at every size.
   Full support/containment tests, corpus, payload safety, and G2 stayed green.
10. **E9 diagnostic — DONE.** The permanent `wide dict encode` row uses 64 columns with
    rotated insertion order. Baseline cost is stable at 5.5–5.8 us/row from 4 through 512
    rows; source inspection confirms nested linear key membership. `toon-rust` independently
    uses `IndexMap::contains_key` for this check.
11. **E9 hashed dict membership — ADOPTED.** Later rows now probe the first row's actual
    key objects through `PyDict_Contains`, exactly preserving TOON 4.1's same-set/order-may-
    vary rule. Wide dict encode improved 58–68%; ordinary untyped encode improved 31–37%;
    typed Struct encode was parity-to-faster.
12. **G4 upstream mechanism proof — DONE, not shipped.** The disposable raw-offset proof
    improved typed encode 25-30% and beat `to_builtins` from 64 records upward.
13. **G4 upstream capsule shot — DONE, preserved, opt-in workflow active.** A versioned msgspec
    PyCapsule patch (`6391020`) and optional Rust consumer (`aa27f5e`, branch
    `g4-upstream-capsule`) define class/order/lifetime/unset/free-threaded semantics. The
    safe path improves 14-22% and beats `to_builtins` at 512/4096, not 4-64. Both capsule
    and stock fallback pass `make check`, 538/538, and G2; CPython 3.14t concurrent mutation
    testing passes with the GIL disabled. Main now contains the optional consumer, but the
    exact stock 0.21.1 pin still selects `attribute`; `make fastpath-build` creates an
    isolated patched dependency and asserts that the same source selects `capsule`. See
    `docs/implementation-spec/msgspec-upstream-struct-view-g4.md` and its preserved patch.
14. **NEXT:** upstream the msgspec patch, or stop. Do not copy msgspec/CPython private
    layouts into the abi3 wheel. No in-repository mechanism closes the residual 4-64 floor.
15. **H6 is deferred, not an invitation to hand-roll statistics in Python.** Preserve raw
   block data; if this is resumed, use an established bulk-analysis implementation and a
   predeclared family-wise procedure outside the timed worker path.

Then stop. Each candidate is adopted only on same-session A/B and otherwise recorded as
rejected. `OBJECTIVE.md` contains the complete reopened exit condition.

**Do not re-spend these.** Measured dead: the plan-cache mutex (~17ns of ~500ns), per-call
buffer reuse and the `PyBytes` copy (~114ns floor; the copy is not removable under abi3),
and `msgspec.structs.astuple` for encode field reads (9–10 points *slower*). Closed by
spec: encoder tabular-classification changes for token wins. Still live but thin: E4.

`conformance/support_matrix.py` is both the work list and the acceptance test. Use
`/last-mile`.

## The goal, precisely

Build the **most token-efficient and fastest TOON 4.1 codec for Python**, integrated
natively with **msgspec==0.21.1** the way `msgspec.json` is: the typed path decodes
TOON text directly into `msgspec.Struct` instances with **zero intermediate dict/list
tree**, and encodes Structs without `msgspec.to_builtins`. Both metrics matter and both
are measured: **tokens** (tiktoken `o200k_base`, `benches/bench_tokens.py`) and
**speed** (same-run microbenchmarks, `benches/bench_typed.py` / `bench_codecs.py`,
plus a frozen-baseline A/B harness `benches/ab.py`). Claims exist only as generated
evidence in `conformance/report.json` — never as assertions.

## Where things stand (all verified at v0.4.0)

| claim | state | evidence |
|---|---|---|
| TOON 4.1 conformance | **538/538 fixtures, zero divergences** (corpus pinned+hash-locked at toon-format/spec v4.1.1) | `conformance/run.py`, `fixtures.lock.json` |
| G2 no intermediate tree | **pass, two-sided** (typed: 0 builtin dicts/lists, 129 Structs + 1 final list; wrapper: 129 builtin dicts) | `make g2` → `conformance/allocation-proof.json`, `tests/test_typed_allocations.py` |
| G3 typed beats wrapper | **pass at 16/64/512/4096 records** | `bench_typed.py` |
| G5 codec floor | **pass both directions**: 2–6.5× faster than `toons` 0.7.0, ~20× vs `python-toon` 0.1.3 | `bench_codecs.py` |
| vs the real incumbent pipeline | 19–51× faster | `bench_typed.py` incumbent rows |
| Token efficiency (T1) | **pass**: canonical TOON = 0.61–0.64× JSON tokens on record payloads; incumbents = 1.25× JSON | `bench_tokens.py` |
| Token efficiency (T3) | **measured loss, now published**: on **irregular (non-tabular) shapes canonical TOON costs MORE tokens than JSON** — 1.16× at 16, 1.19× at 512 — while producing *fewer* bytes (0.92×/0.94×). Both numbers were already in the lock; the divergence had never been read. TOON tokenizes worse per byte (2.26 vs 2.83 B/token) so it needs ~0.77× bytes just to break even. **The token advantage belongs to the tabular forms, not to TOON** | ledger `token_findings.T3`, `efficiency.lock.json` |
| Token efficiency (T4) | **closed — the indent axis is measured and generated**: `INDENT_AXIS = (1,2,4)` in `bench_tokens.py` with roundtrip assertions. `indent=1` saves on **every** shape, not only entry-heavy ones: uniform@4096 0.621× → **0.579×** vs JSON (60,455 → 56,359 tokens), irregular@512 1.186× → 1.031×. `indent=4` costs bytes and is token-identical to `indent=2`. Canonical stays `indent=2`; this is a caller's option and the lock never moves | ledger `token_findings.T4`, `docs/token-shape-guidance.md` |
| Token efficiency (T5) | **the three tabular-fallback questions are closed**: a row missing a key, an `Optional[Struct]` that is `None` in one row, and an array-valued column are all fallbacks the spec **requires** (TOON 4.1.1 §9.3), and detection is MUST in both directions, so the classifier can be neither more nor less aggressive. No code change recovers tokens there. Corroboration differs and is recorded: the first two are confirmed by named corpus fixtures, the third has **zero fixture coverage** and rests on the spec reading alone | ledger `token_findings.T5` |
| Tab-delimiter folklore (T2) | **measured false** at noise level; published as a finding | report `token_efficiency.findings` |
| Type-support boundaries | **generated, not asserted**: 12 supported, 2 parity-rejects, 13 unsupported, 0 silently ignored, 0 silently wrong. `conformance/report.json` carries the live counts; this row is a snapshot | `conformance/support_matrix.py`, `tests/test_support_matrix.py` |
| G4 encode vs `to_builtins` alone | **still fails as a gate** (it requires every size): 1.94× at 16, 1.54× at 64, 1.23× at 512, **0.97× at 4096** — the crossover first seen after round 1 holds. R-02 is a slope, not the floor it was assumed to be. **Round 2 did not move the small end and explains why**: the direction doc's three leads (plan-cache mutex, buffer reuse, `PyBytes` copy) were profiled and measured dead, and the real fixed cost turned out to live in the *entries* path — which the uniform challenge shape never touches, so G4 on this ladder is unmoved by round 2's large entry-path wins. Closing G4 at 16/64 remains open and now has no known mechanism | report `benchmarks_typed_same_run`, `gates` |
| Optimizations | 6 adopted, re-qualified under the significance-tested harness against `v0.1.0-conformant`: **all 16 metrics resolve as faster** — typed decode −14.3/−17.0/−16.9/−18.1%, untyped decode −11.8/−15.5/−18.2/−17.6%, typed encode −6.4/−6.7/−6.2/−3.4%, untyped encode −8.6/−6.6/−7.2/−6.3%. The two encode rows F-12 could not resolve now resolve | `benches/optimization-ledger.json`, report `speed_ab.baseline` |
| A/B rigor | **mean across 10 worker processes** (never a minimum); one metric per block, alternating `B C C B`, t-test at alpha 0.95, per-row minimum detectable effect; a slowdown must reproduce at double power to fail. **Loop counts are now calibrated once and shared by both sides (H1)** — they used to be chosen independently per block, so two builds near a doubling boundary measured different amounts of work; that produced reproduced false slowdowns of 4–7% at records=64 on *identical source*, now +0.2/+0.6% | `benches/ab.py`, ledger `harness_findings.H1` |
| A/B rigor — H2 largely fixed | **blocks interleave across the ladder**: every `B C C B` position runs across all metric points before the next, so each metric's samples span the whole run and drift enters both sides symmetrically — bias becomes variance the t-test models. No threshold, alpha or block count changed. On identical source: old harness 2 reproduced slowdowns in each of two runs (peak +7.2%), new harness 1 then 0 (peak +1.8%). A canary is reported beside every run and never gates | ledger `harness_findings.H2` |
| A/B rigor — open (H3) | **a ~1.3% build-identity floor survives that ordering cannot reach**: `entry decode@512` reads +1.8/+1.0/+1.3/+1.3% across four *solo* runs against a source-identical guard. Likeliest mechanism: the guard is built in a separate worktree, so embedded path strings shift code layout. **Two builds of identical source are not equally fast.** Next step (untested): build the same source at a third path and compare | ledger `harness_findings.H3` |
| A/B rigor — open (H4) | **the confirmation step can false-negative**: proven by deliberate perturbation, the gate fires — a real 10–20% regression was caught at five of six sizes and failed the run — but `entry decode@4096` flagged at +10.0% and then did *not* reproduce in the solo confirmation. A confirmation that can miss 10% is not one to rely on alone | ledger `harness_findings.H4` |
| Regression gates | **token/byte lock** (any drift fails) and **speed gate vs the latest release** (a reproduced slowdown exits non-zero). Both proven to fire by deliberate perturbation | `conformance/efficiency.lock.json`, `make ab` |
| Release + guard | **v0.4.0 tagged; `.venv-guard` cut from it and codec-identical to HEAD.** `GUARD_TAG` is derived from the latest tag and the gate refuses an older one. Parity runs are now clean or near-clean — see the three A/B rigor rows | `git tag`, `.venv-guard/GUARD_TAG` |
| External review round 2 | **8 patches, all adopted, all on measurement.** vs the v0.3.0 guard on the full 42-metric ladder: entry decode −24.8/−33.2/−58.6/−89.1% at 16/64/512/4096, entry encode −21 to −23%, typed decode −5.8 to −9.3%, typed encode −7.7 to −14.7%, untyped decode −4.0 to −8.8%. Two new metrics (`entry decode`/`entry encode`) and two new ladder sizes (4, 8) landed *before* the candidates that needed them | ledger (R2-B, R2-C, R2-D, P3), `docs/token-shape-guidance.md` |
| External review round 1 | **4 adopted, 1 rejected, all on measurement.** vs the v0.3.0 guard: typed decode −6.0/−9.0/−7.2/−7.7%, typed encode −13.9/−14.9/−15.8/−16.6%, untyped decode −2.7/−2.6/−7.4/−5.2%, untyped encode −7.0/−7.8/−7.4/−7.5%, and keyed decode −19.3/−51.9/−88.4% at 64/512/4096 | `benches/optimization-ledger.json` (D6, P2, E5, D5 adopted; E7 rejected) |

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
   - `benches/ab.py` rigor — **done (F-12)**: blocks alternate, one metric per block,
     with a significance test and a published minimum detectable effect.
   - Payload-safety audit: grep every `format!`/error message for payload-derived
     content (AD-007). Tests cover sentinels; a reviewer should cover the negative
     space.
6. **E3 (fused row templates)** — unattempted encode candidate; hypothesis in
   `benches/optimization-ledger.json`. G4's remaining 1.11× gap at 4096 is the target.
7. **Formal profiling** (change task 4.1) — candidates were chosen by inspection and
   validated by A/B; a flamegraph pass may reveal candidates nobody guessed. It now has a
   concrete first question: a ~2% typed-encode regression against v0.2.0 was measured and
   is *not* explained by the logic added (reverting both encode changes left +1.38%), so
   the remaining candidate is binary layout. That was accepted into the v0.3.0 baseline
   rather than chased; see "the ~2% encode regression" in `LAST-MILE.md`.
8. **pyo3 cooldown pin** — `=0.29.0` lifts when 0.29.2 ages past 14 days
   (~2026-08-19); `make audit` confirms. Then `cargo update -p pyo3` + full re-test.
9. **Typed support ladder** — the authoritative list is now
   `conformance/support_matrix.py`, not this file. Phase C of `LAST-MILE.md` implements
   the Tier 1 items; Tier 2 (enums, datetime, UUID, Decimal, dataclasses) is untouched.
   `order`, `decimal_format` and `uuid_format` now raise `NotImplementedError` for values
   they do not implement, and the same `ValueError` msgspec raises for values outside the
   domain. (An earlier note here claimed the `Encoder` constructor and the `encode()`
   function disagreed about accepting the format options — they do not, and neither does
   msgspec: those options are Encoder-only in `msgspec.json` too.)
10. **Keyed tabular in the typed path** — decode works via Dict frames for
   `dict[str, Struct]`; the D1 memo doesn't cover keyed rows (hash path). Minor.
11. **Recursive Struct types** — the plan compiler recurses until `RecursionError`
   (catchable, not a crash). Detect the cycle and error clearly, or support them.
12. **openspec changes** — `refine-benchmarks-and-tooling` (16/18) and
   `optimize-speed-and-token-efficiency` (23/24) remain open with only
   deferred/time-gated tasks; archive them (`openspec archive`) when their stragglers
   close. Main specs are already synced.
13. **Wheel matrix + CI — qualified for `0.1.0b3`, not published.** The reusable validation
   workflow and release workflow build and verify 12 wheels (CPython 3.13 abi3 and CPython
   3.14t across macOS/Linux/Windows on x86_64/arm64) plus one sdist. Run 31298470572
   verified the exact set target-natively with publication disabled. The remaining release
   boundary is owner configuration and explicit authorization for Trusted Publishing.

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
  G2/G3/G5 green, 88 unit tests green (`make check`), and the efficiency lock unmoved.
- Parser modules must not import PyO3 (canvas AD-002).

## Commands

```bash
uv sync && make build   # maturin develop --release into the env that actually imports it
make fastpath-build # isolated patched-msgspec build; asserts the capsule backend is active
make fastpath-check # lint/typecheck/Rust tests + Python tests/corpus through that build
make fastpath-bench # same-binary capsule-vs-fallback measurement
make fastpath-gates # normal typed G3/G4 ladder; currently fails G4 at 4-64
make check        # lint (ruff, rustfmt, clippy -D warnings, both feature sets) + mypy + tests
make g2           # instrumented build in .venv-g2: the G2 proof and its artifact
make guard        # build the gate baseline (latest release) into .venv-guard
make ab           # THE SPEED GATE: fails on a reproduced slowdown vs the guard
make ab-story     # report vs the frozen v0.1.0 baseline; never gates
make efficiency   # show any drift in the token/byte lock
make bench        # bench_codecs + bench_typed (release wheel, rebuilds first)
uv run python benches/bench_tokens.py                              # token gates
uv run python conformance/run.py                                   # 538-test corpus
make baseline     # build the story baseline (v0.1.0-conformant) for `make ab-story`
make report       # regenerate conformance/report.json (the evidence artifact)
make audit        # dependency-age cooldown check (network)
```

Quirk: `cargo test` needs `PYO3_PYTHON=/opt/homebrew/opt/python@3.13/bin/python3.13`
(the Makefile exports it; the uv-managed CPython's dylib install-name breaks test
linking).

## History

`v0.0.1-poc` (Phase 1 vertical slice) → `v0.1.0-conformant` (zero fixture failures,
25 option divergences) → `v0.2.0` (perfect 538/538, options, tokens measured,
optimization round) → **`v0.3.0`** (containment repairs, an independent G2 proof, the
generated support matrix, the trustworthy-performance-evidence round, and typed
correctness: fixed tuples, `kw_only`, `Literal[int]` no longer accepting booleans,
non-`str` mapping keys refused, inert encoder options failing loudly). Full narrative in
`git log`; design of record in `docs/implementation-spec/`; requirements in
`openspec/specs/`.
