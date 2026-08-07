# Last-mile execution ledger

This file is the continuation contract for autonomous coding sessions.
Read `CLAUDE.md`, `HANDOFF.md`, and `docs/adversarial-review-v0.2.0.md` first.

## North star

Improve the fastest and most token-efficient TOON 4.1 codec for Python.
Preserve byte-exact conformance, the zero-tree typed path, and payload-safe errors.

```text
valid improvement = measured speed or token gain
                    ∩ 538/538 conformance
                    ∩ G2 zero intermediates
                    ∩ G3 and G5 pass
                    ∩ payload-safe errors
```

Never optimize a proxy when a named gate can measure the result.
Never keep a change because it looks faster.

## Native iteration loop

Use `/last-mile` to run this loop. Do not create another agent harness.

1. Read the three context files named above.
2. Inspect `git status --short`. Preserve unrelated changes.
3. Select the first unblocked work item below.
4. Write one falsifiable hypothesis before code changes.
5. Add the smallest adversarial or differential test that can fail.
6. Make one focused implementation change.
7. Run `make check` and `uv run python conformance/run.py`.
8. Run G2, G3, and G5 when the change touches decoding, encoding, plans, or instrumentation.
9. Run `make baseline && make ab` when the change can affect performance.
10. Run `uv run python benches/bench_tokens.py` when output bytes can change.
11. Reject the change if any protected gate regresses.
12. Record measurements and remaining gaps in generated evidence.
13. Update this ledger and `HANDOFF.md`.
14. Commit one proven checkpoint.
15. Continue with the next unblocked item.

Do not combine correctness repairs with speculative optimization.
Do not cite benchmark numbers from another session.
Do not modify canonical output to improve a selected payload.

## Ordered work queue

### A. Containment repairs — DONE (checkpoint 1)

- [x] F-01 cap array reservation hints without changing declared-count validation.
- [x] F-02 enforce a depth limit for field-group decode.
- [x] F-03 enforce a depth limit during encode shape discovery.
- [x] Add subprocess regression tests for panic and exit-139 inputs.

Exit: hostile inputs return static codec errors. The 538 fixtures still pass.

Hypothesis (falsified as stated — all three defects reproduced): each defect lets a
small input reach a machine resource sized by the payload, so bounding the payload-chosen
quantity converts every crash into a codec fault without touching hot-path throughput.

Result. Reproduced first on the release wheel: F-01 `PanicException: capacity overflow`,
F-02 and F-03 exit 139. All three now raise `DecodeError`/`EncodeError`. Measurements
below are the same-session A/B against `v0.1.0-conformant`; the deltas stay inside the
v0.2.0 envelope, so the caps cost nothing measurable.

```text
gate                        result
────                        ──────
corpus                      538/538, zero divergences
make check                  33 Rust + 52 Python tests, lint/format/clippy/mypy clean
G3                          PASS at 16/64/512/4096
G5                          PASS both directions, every size
G4                          FAIL, unchanged (the known R-02 miss)
A/B typed decode            -13.9 / -19.3 / -18.9 / -21.2 %
A/B untyped decode          -12.5 / -16.0 / -19.1 / -16.7 %
A/B encode (whole/codec)    -2.1 → -5.3 % / -5.3 → -7.4 %
tokens                      T1 and T2 unchanged; canonical bytes untouched
```

Design notes for the next agent:

- One shared ceiling now lives in `src/limits.rs` (`MAX_NESTING_DEPTH`), replacing the two
  parallel `256` constants in `scan.rs` and `encode.rs`. The OpenSpec states it:
  `toon-parsing` "Payload-chosen quantities are bounded", `toon-encoding` "Encoding is
  bounded by the same nesting ceiling". This answers the review's open question — the
  limit counts nesting levels, one ceiling for indentation, field groups, and encoding.
- The field-group gate is a single check in `parse_header`, reading the max depth that
  `find_matching_brace` already counts. Bounding construction bounds every later walk of
  the tree (`leaf_count`, `emit_row_fields`), so no second check was added — the review's
  suggestion to duplicate the limit into those two functions would have been a parallel
  solution.
- Depth is a hard fault in strict *and* non-strict mode, unlike a malformed header. A
  resource limit is not a grammar ambiguity, and this matches `scan.rs`'s existing
  unconditional line-depth fault.
- `Makefile` `build` now clears `target/wheels` first: a stale `0.0.1` wheel made the
  install glob ambiguous and broke `make bench`.
- Not done, deliberately: no depth guard on `plan_from_spec`/`plan_for_nested`. That
  recursion is bounded by the Python plan spec, which hits `RecursionError` in `_plan.py`
  first. Recursive Structs remain open item 7 and need their own cycle detection, not a
  depth cap.

### B. Evidence repairs

- [x] F-05 replace release-wheel allocation counters with independent test instrumentation.
- [x] Rerun G3 and G5 without atomic counter bias.
- [x] F-21 (new) refuse to publish a measurement from a stale or instrumented build.
- [x] F-11 generate the known-gap report from one maintained support matrix.
- [x] F-12 alternate A/B blocks and publish raw repetitions plus spread.

Exit: each performance and G2 claim has independent, same-session evidence. **MET.**

#### Checkpoint 3 — F-11

Hypothesis: the released gap list is not merely incomplete but structurally unable to
stay complete, because prose has no failure mode. Replacing it with a matrix that tests
execute should (a) surface gaps the freehand list omitted and (b) make a stale claim a
test failure.

Confirmed both ways. Every gap the review named was verified by probe before being
written down — none were copied on the review's authority — and the generated list went
from 4 freehand entries to 18. `conformance/support_matrix.py` holds one entry per
feature with a probe for this codec and a probe for `msgspec.json` on the equivalent
document; `tests/test_support_matrix.py` runs all 26 and fails when a declaration stops
being true in *either* direction. It caught a mis-declared entry of mine on its first
run.

Two refinements over the review's framing:

- Status is not binary. `unsupported` (we raise, msgspec accepts) is ranked below
  `silently_ignored` (a parameter accepted and dropped) and `silently_wrong` (both
  succeed and disagree). A rejection is visible to a caller; a wrong value is not.
  Current counts: 8 supported, 11 unsupported, 3 silently ignored, 2 silently wrong.
- A gap is only ours if `msgspec.json` accepts what we reject. The `unsupported` checker
  asserts the reference *succeeds*, so shared behavior can never be logged as our defect.

Corrections to the review's list, found by probing:

- `decimal_format`/`uuid_format` are not "accepted but inert" everywhere: the `Encoder`
  constructor accepts and drops them, while the `encode()` function rejects the same
  names with `TypeError`. The two entry points disagree; that is now one matrix entry.
- Recursive Structs do not crash. `_plan.py` recurses until `RecursionError`, which is
  catchable — bad ergonomics, not a containment defect. Open item 10 stands, but it is
  not a P0.

#### Checkpoint 2 — F-05 and F-21

Hypothesis: the counters were (a) not independent — a zero proved only that the
untyped consumer's call sites went unused — and (b) not free, costing one atomic per
container on the wrapper side of G3 and the untyped side of G5.

(a) CONFIRMED and repaired. (b) FALSIFIED, and the falsification is the more useful
result: measured instrumented-vs-clean at the same commit, every row placed the *clean*
build 0.4–3.6% slower, which cannot be an effect of removing work. The counter cost is
below this harness's resolution, so the published G3/G5 margins were never materially
inflated by it. The sign-consistent penalty on whichever side ran second independently
reproduces F-12 — run order is worth 1–3%, larger than the effect under test.

What replaced the counters:

- `src/containers.rs` is now the only module that constructs a Python container, and
  `clippy.toml` fails the build on `PyDict::new`/`PyList::new`/`PyTuple::new` anywhere
  else. A zero is therefore a statement about the codec rather than about one consumer.
  The lint immediately earned its keep by catching the stats dict in `lib.rs`.
- Counters are behind the non-default `alloc-stats` feature. `make g2` builds an
  instrumented wheel into `.venv-g2` and writes `conformance/allocation-proof.json`;
  the release report reads that artifact and refuses to fabricate it.
- Every assertion is two-sided. Typed decode of the 64-record payload: 0 builtin dicts,
  0 builtin lists, **129 Structs and 1 final list** — a zero alone would also hold if
  nothing had been decoded. Wrapper: 129 builtin dicts, 1 builtin list, 0 Structs.
- An `Any` subtree builds builtin containers on purpose; that case is now a named test,
  so G2 means "no tree nobody asked for" rather than "no tree".

**F-21, found while measuring F-05 and worth the next agent's attention.** `.venv`
installs this project *editable*, so `uv run` imports
`python/msgspec_toon/_native.abi3.so` and any `uv pip install` of a freshly built wheel
is shadowed — and undone by the next re-sync. The first instrumented-vs-clean A/B I ran
this session compared the new instrumented build against a **stale** editable `.so` from
the previous checkpoint, and looked perfectly plausible. Repairs:

- `make build` now runs `maturin develop --release`, writing the release abi3 build to
  the path that is actually imported.
- `benches/build_freshness.py` refuses to publish a number when the editable extension is
  older than `src/*.rs` or when the build carries counters. Both branches are verified to
  fire, not assumed.
- The check applies to the editable artifact only: `.venv-baseline` and `.venv-g2` are
  pinned to other revisions on purpose. `ab.py` records `baseline_instrumented` /
  `current_instrumented` in its artifact instead — and the frozen `v0.1.0-conformant`
  baseline *does* carry the counters, which is now visible in every A/B it produces.

```text
gate                        result
────                        ──────
corpus                      538/538, zero divergences
make check                  33 Rust + 50 Python tests (4 G2 tests skip; they run in make g2)
make g2                     4/4, G2 pass, probe_observed_the_typed_path true
G3                          PASS at 16/64/512/4096
G5                          PASS both directions, every size
G4                          FAIL, unchanged (the known R-02 miss)
A/B typed decode            -11.7 / -19.7 / -15.1 / -20.8 %
A/B untyped decode          -11.8 / -14.9 / -21.4 / -18.1 %
A/B encode (whole/codec)    -2.5 → -5.3 % / -4.6 → -7.9 %
tokens                      unchanged; canonical bytes untouched
```

### C. Typed correctness

- [ ] F-04 preserve exact cell columns without adding an intermediate tree.
- [ ] F-06 differential-test and implement `strict=False` Tier 0 coercions.
- [ ] F-07 distinguish booleans from integer literals.
- [ ] F-08 implement fixed tuples.
- [ ] F-09 support `kw_only` Struct construction on a cold branch.
- [ ] F-10 implement or reject `order` values explicitly.
- [ ] F-13 reject unsupported mapping key plans during decoder construction.

Exit: supported behavior matches `msgspec==0.21.1`. Unsupported behavior fails loudly.

### D. Hot-path hardening

- [ ] F-16 add the D1 transition matrix and debug stack assertions.
- [ ] F-17 add `SAFETY:` proofs and boundary tests for every unsafe block.
- [ ] F-18 bound or specialize the untyped key cache after measurement.
- [ ] F-19 measure wide-object duplicate detection before changing its data structure.
- [ ] F-20 measure wide-dictionary shape checks before changing membership lookup.

Exit: all unsafe and memo invariants have executable tests or local proofs.

### E. Continued efficiency work

- [ ] Run formal profiles for typed decode, untyped decode, Struct encode, and dictionary encode.
- [ ] Rank costs by measured inclusive time.
- [ ] Attempt E3 only if writer overhead is material.
- [ ] Record rejected candidates with their measurements.
- [ ] Keep the canonical token ladder and losing shapes in every report.

Exit: each adopted optimization has a frozen-baseline A/B result and all protected gates pass.

### F. Distribution finish

- [ ] Lift the PyO3 cooldown pin only after its time gate and `make audit` pass.
- [ ] Build the five-platform abi3 wheel matrix.
- [ ] Add CI checks for wheels, syscall restrictions, conformance, and smoke benchmarks.
- [ ] Archive completed OpenSpec changes after their deferred tasks close.

## Stop conditions

Stop the loop and write the exact blocker when any condition occurs:

- A requirement conflicts with the official fixture corpus.
- A proposed optimization requires msgspec private layout access.
- A gate changes outside measured noise and the cause is unknown.
- The work needs a new public wire option or a new dependency.
- The next action can delete evidence, tags, fixtures, or user changes.
- A benchmark does not use the release abi3 wheel.

Do not mark a work item complete from code inspection alone.

## Session handoff

Before each checkpoint commit, record:

- the selected work item and hypothesis.
- the changed files.
- the completed tests and gates.
- the exact same-session measurements.
- the rejected alternatives.
- the next unblocked work item.
- all remaining known gaps.

The last commit must leave `git diff --check` clean.

#### Checkpoint 4 — F-12

Hypothesis: run order, not the code under test, explains a material share of the small
deltas this project publishes, and the old harness could not tell the difference because
it ran all of B and then all of C exactly once.

CONFIRMED, and it cost two published claims their status. `benches/ab.py` now runs
`B C C B` rounds and reports, per metric: the median of the paired ratios, the spread
across pairs, and a **noise floor** — the spread among repeated blocks of the *same*
build, minutes apart. That floor is not a refinement of the delta; it is the smallest
delta the session can distinguish from nothing.

Measured over eight blocks (`--rounds 2`), same-build blocks disagree by 1.7–8.8 pp
depending on metric and size. Consequences:

```text
metric                                  median   noise   verdict
typed decode      @16/64/512/4096      -12.9 to -20.0%   3.6-8.8pp   resolved
untyped decode    @16/64/512/4096      -10.3 to -20.2%   1.7-4.4pp   resolved
codec encode      @16/64/512/4096       -6.3 to  -8.1%   1.7-4.4pp   resolved
typed encode      @512/4096                     -4.8%    2.8-3.8pp   resolved
typed encode      @16                           -5.4%       6.2pp    BELOW NOISE
typed encode      @64                           -4.2%       5.0pp    BELOW NOISE
```

So the project's "encode −4→−8%" claim is real at the larger sizes and **not resolvable
at 16 and 64 records on this machine**. The E1/E2 ledger entries now say so. Every block
is kept in `benches/ab-latest.json` and published in `conformance/report.json` under
`speed_ab_latest`, so a reader sees the repetitions rather than one summary number.

A false start worth recording: my first drift metric compared consecutive same-build
blocks and reported 30–36 pp on two rows. The blocks were real but the metric was wrong —
consecutive pairs across round boundaries are not comparable positions. The floor is now
the full spread among a build's blocks, which is both simpler and harder to fool.

Note for whoever reads the earlier checkpoints: the deltas recorded there came from
single-order runs. The decode figures reproduce under the new instrument; treat the
small encode figures in checkpoints 1 and 2 as unresolved rather than as measurements.
