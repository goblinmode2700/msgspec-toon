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

Reordered on the severity ranking this project now publishes: `silently_wrong` outranks
`unsupported`, because a rejection is visible to a caller and a wrong value is not. F-07
and F-13 were the only two silent divergences, so they went first. F-04 stays queued —
it is error-message precision on a hot path, which is lower value and higher risk than
the parity items around it.

- [x] **C-01 a row memo is never shared across positions with different plans.** Found while
      reviewing the D5 candidate from the external round, but pre-existing since D1 landed and
      **shipped wrong in v0.3.0**. The memo replays the first row's wire-name→field-index
      resolutions positionally; a fixed tuple gives every position its own plan, so
      `tuple[Ascending, Descending]` — two Structs sharing field names in opposite declaration
      order — silently swapped the values of every row after the first. Byte comparison did not
      catch it because the *key names* match; only the indices differ. `msgspec.json` returns
      `Descending(y=4, x=3)`, we returned `Descending(y=3, x=4)`. A wrong value, not a refusal,
      which is the top of this project's severity order. Fixed by `RowMemo::for_sequence`, which
      refuses to memoize a `ByPosition` frame — the rule lives in one constructor so no call
      site can forget it. Regression test asserts against `msgspec.json` and was confirmed to
      fail on the unfixed build. Corpus 538/538, lock matches, `make ab` resolved no slowdown.
- [ ] **C-00 enforce constraints (`msgspec.Meta`).** No lettered finding — the adversarial
      review logged it only as "parsed but not enforced" — but it is the **last silent
      divergence in the codec**: `Annotated[int, Meta(ge=10)]` reaches the plan IR and is
      never applied, so a value `msgspec.json` rejects is accepted. Take it first: a wrong
      value returned silently outranks a loud refusal, which is the severity order this
      project's own support matrix encodes.
- [ ] F-06 differential-test and implement `strict=False` Tier 0 coercions.
- [ ] F-04 preserve exact cell columns without adding an intermediate tree. Last, not
      first: it is error-message precision on a hot path, so it carries the most risk and
      the least user-visible value of the three.
- [x] F-07 distinguish booleans from integer literals.
- [x] F-08 implement fixed tuples.
- [x] F-09 support `kw_only` Struct construction on a cold branch.
- [x] F-10 implement or reject `order` values explicitly.
- [x] F-13 reject unsupported mapping key plans during decoder construction.

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

## The guard baseline: enforced, not promised

`make ab` gates against `.venv-guard`, built from the **latest release tag**, which the
Makefile derives (`git tag -l 'v*' --sort=-v:refname | head -1`) rather than hardcodes.
`make guard` records the tag it built into `.venv-guard/GUARD_TAG`, and the gate refuses
to run when that marker does not match the latest tag:

```text
.venv-guard was built from v0.2.0, but the latest release is v0.3.0.
A stale guard cannot detect a regression — run `make guard`.
```

**After cutting any release tag, run `make guard`.** The check turns forgetting into a
loud failure instead of a silent blind spot — which is the failure this project already
measured once: a 24% slowdown against a baseline trailing by 15-20% read as a 2%
difference and passed.

## Efficiency lock: how to update it

`conformance/efficiency.lock.json` records what this codec's output costs — bytes and
tokens, for canonical output and its two delimiter variants, plus compact JSON as the
denominator. `tests/test_efficiency_lock.py` fails on **any** difference, in either
direction: an unexplained improvement means the output changed too, and canonical bytes
are a conformance surface.

When the counts move for a reason:

```bash
uv run python scripts/efficiency-lock.py            # show the drift
uv run python scripts/efficiency-lock.py --write    # accept it
```

The commit that carries a new lock must say **why the counts moved**. A lock updated
without that sentence is indistinguishable from a silent regression, which is the thing
the lock exists to prevent.

Coverage note, learned the hard way: the locked payloads must include a shape the encoder
cannot make tabular. Uniform record arrays become tabular blocks and uniform
object-of-objects become *keyed* tabular blocks; neither reaches the `key: value` entry
writer. Perturbing the key separator moved no locked byte count until `irregular` was
added to the payload matrix. If you add an encoder path, ask which locked payload
exercises it.

## Resolved at v0.3.0: the ~2% encode regression was accepted into the baseline

_Historical. The guard now points at v0.3.0, which contains this regression, so `make ab`
is green again. Kept because the reasoning is the precedent for the next one._

## The ~2% encode regression, and why it was accepted rather than fixed

`typed encode@512` is **+2.1% slower than v0.2.0** (MDE 1.4%, reproduced at double power),
and a focused 16-block run put `typed encode@4096` at **+2.42%** (MDE 1.98%, significant).
The regression is real and it is this round's.

What it is not: attributable to the logic added. Reverting only the two encode-path changes
since v0.2.0 — the `build_shape` depth guard and the capped writer reservation — moved
4096 from +2.42% to +1.38%, still significant. Both run about five times per encode of 4096
records, so neither can cost 1% of a 500 µs call. The residual, and probably the whole
effect, is binary layout and inlining changed by the new modules. That is a known
measurement phenomenon, not a defect with a line number.

**Do not resolve this by weakening the gate.** The three legitimate moves are:

1. Cut a release that includes this round and re-cut the guard from it. The regression is
   then accepted into the baseline explicitly, which is what a release-to-release gate is
   for. Requires a release decision.
2. Take it as the first Phase E profiling question — the flamegraph pass has never run, and
   "2% of encode moved and the logic did not" is a good place to point it.
3. Revert the containment guards, which is not an option: the corpus, the containment
   tests, and G2 all depend on them.

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

#### Checkpoint 5 — F-07 and F-13, the two silent divergences

Hypothesis: both defects return a wrong value where `msgspec.json` either rejects or
returns something else, and both are cold-path, so both can be repaired without touching
the challenge shape's throughput.

Confirmed. `silently_wrong` is now **0** in the support matrix.

- **F-07.** `Literal[1]` accepted `true` because membership used Python equality and
  `True == 1`. Membership now compares the exact scalar category first. msgspec permits
  only None/int/str in a `Literal`, so there is no widening case this wrongly rejects —
  verified against `msgspec.json`, which answers "Expected `int`, got `bool`".
- **F-13.** `dict[int, int]` returned `{"1": 2}` where msgspec returns `{1: 2}`. The key
  plan was compiled and dropped. The plan compiler now refuses a non-`str` key plan with
  a `TypeError` when the **Decoder is constructed**, not when a document happens to
  contain a key — the earliest point the annotation is visible. It downgrades from
  `silently_wrong` to `unsupported`, which is the honest state until keys are typed.

Found while fixing F-07, and not previously known: **`Literal` with mixed member types is
unsupported for a reason outside this codebase.** `msgspec.inspect` sorts a Literal's
members, so `Literal["a", 1]` raises `TypeError: '<' not supported between instances of
'int' and 'str'` before the plan compiler sees anything — while `msgspec.json` decodes it
happily, because its own decoder does not go through `inspect`. AD-003 confines us to
`inspect`, so this cannot be fixed behind the membrane. It is now a matrix entry with
that explanation rather than a mystery.

A new matrix status was needed: `parity_rejects`, for "both implementations refuse this".
Without it the matrix could not express that rejecting `true` for `Literal[1]` is now
*correct*, and a `supported` entry cannot be a rejection.

```text
gate                        result
────                        ──────
corpus                      538/538, zero divergences
make check                  33 Rust + 78 Python tests, clean
matrix                      9 supported, 1 parity-rejects, 13 unsupported, 3 inert, 0 silently wrong
A/B (4 blocks, quiet run)   every row resolved; typed decode -14.1/-19.2/-18.9/-22.7%,
                            untyped decode -11.2/-14.0/-19.2/-17.6%, encode -4.9 to -7.8%
```

Note on the checkpoint-4 below-noise rows: in this quieter session, typed encode at 16
and 64 records resolved (-5.3%, -7.1%) against noise floors of 1.7pp and 0.4pp. Whether a
~5% delta resolves is a property of the session, not a fixed fact about the codec. Both
runs are in the artifacts; neither supersedes the other.

#### Checkpoint 6 — F-08 fixed tuples

Hypothesis: the plan compiler already emits `tuple_fixed` and Rust lowers every unknown
kind to `Custom`, so the missing piece is not parsing but the frame model — a sequence
frame holds one uniform item plan and a fixed tuple needs one plan per position.

Confirmed. Rather than special-case tuples, the frame now names *where a sequence finds
its next element's plan*:

```text
SequencePlan::Uniform(plan)      list[T], tuple[T, ...]   — same answer every time
SequencePlan::ByPosition(plans)  tuple[A, B, C]           — answers by index, and runs out
```

Running out is the whole point: it makes length a property of the type rather than of the
document. One helper turns "no plan for the next element" into a validation error when the
frame is a saturated fixed tuple, and an internal fault otherwise — so an over-long tuple
reports a type error instead of an internal one. Length is also checked when the frame
closes, which catches the short case.

Verified against `msgspec.json`: `[2]: 1,x` → `(1, "x")`; wrong length in either
direction rejected; `[2]: x,1` rejected because position selects the plan. Nested
(`list[tuple[int, str]]`) and Struct-field tuples round-trip.

```text
gate                        result
────                        ──────
corpus                      538/538, zero divergences
make check                  33 Rust + 81 Python tests, clean
make g2                     G2 still zero builtin containers
A/B                         typed decode -13.0/-18.9/-19.3/-20.1% — the SequencePlan
                            indirection costs nothing measurable on the hot path
matrix                      10 supported, 2 parity-rejects, 12 unsupported, 3 inert, 0 silently wrong
```

#### Checkpoint 7 — F-09 kw_only Structs

Hypothesis: construction is always a positional vectorcall, so a `kw_only` class fails
with "Extra positional arguments provided"; giving the plan a cached keyword-name tuple
fixes it without touching the ordinary path.

Confirmed, with one obstacle the review did not mention: **msgspec publishes `kw_only`
nowhere the membrane can see it** — not on `StructConfig` (which exposes `frozen`, `eq`,
`array_like`, `forbid_unknown_fields` and nine others) and not on `msgspec.inspect`. The
constructor signature is the source of truth, so `_plan.py` reads
`inspect.signature(cls)` and records a `keyword_only` flag in the IR. Any keyword-only
parameter triggers it, since passing every argument by keyword is valid for ordinary
parameters too — one branch covers partial cases rather than modelling them separately.

The plan then carries a names tuple built **once at compile time**, and construction
picks the half of the vectorcall to use:

```text
ordinary class   nargs = len(values), kwnames = null      (unchanged hot path)
kw_only class    nargs = 0,           kwnames = names     (cold branch)
```

Verified: simple, defaulted, nested, tabular-array rows (which exercise the construction
path once per row), encode round-trip, and missing-required — all matching
`msgspec.json`.

The keyword-name tuple is built through `containers.rs` like everything else, via a
`new_plan_tuple` constructor documented as machinery rather than decoded output, so the
membrane keeps its "every PyTuple::new lives here" property and G2 counts stay honest.

```text
gate                        result
────                        ──────
corpus                      538/538, zero divergences
make check                  33 Rust + 83 Python tests, clean
make g2                     G2 still zero builtin containers
A/B                         typed decode -12.3/-16.9/-18.2/-19.0%, all resolved — the
                            Option check per constructed Struct costs nothing measurable
matrix                      11 supported, 2 parity-rejects, 11 unsupported, 3 inert, 0 silently wrong
```

A test-authoring note for whoever writes the next differential test: this file uses
`from __future__ import annotations`, so a Struct annotated with a class defined *inside*
a test function fails with `NameError` at decode time — msgspec cannot resolve the string
annotation in a function scope. Define such classes at module level.

#### Checkpoint 8 — F-10 and the inert format options

Hypothesis: three encoder options are accepted and dropped, so a caller who asks for
sorted keys gets insertion order and never learns it. Rejecting an unimplemented value is
strictly better than answering wrongly, and cheaper than implementing key ordering that
nothing in the token or speed story needs.

Done as a single option table rather than three near-identical checks:

```text
option           msgspec accepts                     implemented here
order            None, 'deterministic', 'sorted'     None
decimal_format   'string', 'number'                  'string'
uuid_format      'canonical', 'hex'                  'canonical'
```

The domain check runs first, so a value msgspec itself rejects raises the same
`ValueError` it raises, and only a *valid but unimplemented* value raises
`NotImplementedError`. "Not a thing" and "not yet" stay distinguishable to a caller.
Defaults remain silent, including when spelled out explicitly.

**A correction to the review, and to my own earlier matrix entry.** The review recorded
`decimal_format`/`uuid_format` as "accepted by the Encoder constructor, rejected by
`encode()` — the two entry points disagree", and I copied that framing into the matrix.
It is wrong: `msgspec.json.encode()` also refuses those names (`TypeError: Extra keyword
arguments provided`) because they are Encoder-only in msgspec too. Our surface *matches*
msgspec there. The matrix entry now says so.

`silently_ignored` drops from 3 to **1**. The survivor is **constraints
(`msgspec.Meta`)**: `Annotated[int, Meta(ge=10)]` is parsed by the plan compiler, carried
into the IR, and never enforced, so a value msgspec rejects is accepted. That is the last
silent divergence in the codec and it is not covered by any lettered review finding —
whoever picks it up should treat it as the next correctness item, ahead of F-04.

```text
gate                        result
────                        ──────
corpus                      538/538, zero divergences
make check                  33 Rust + 84 Python tests, clean
matrix                      11 supported, 2 parity-rejects, 13 unsupported, 1 inert, 0 silently wrong
```

No Rust changed, so no A/B was required or cited.

#### Checkpoint 9 — trustworthy-performance-evidence (openspec change)

Planned and applied as an openspec change; artifacts in
`openspec/changes/trustworthy-performance-evidence/`. Two things this round changed, and
three things it discovered by testing rather than by reasoning.

**The estimator.** `_timing.py` reported the minimum of seven batches in one process,
which rewards whichever batch dodged the scheduler and has no central-limit behavior to
converge on. It now reports the **mean across 10 independent worker processes**, each
discarding its own first sample, with the loop count calibrated once and handed to every
worker so they all measure the same work. Every absolute figure moved a few percent; the
historical ledger entries are labelled `estimator: min-of-batches` rather than restated.
The worker count was chosen by measurement, not by copying pyperf's 20: per-worker CV is
0.8-1.4% on a quiet machine, so 10 workers put the standard error at 0.25-0.45% and 25
would buy 0.15pp for 2.5x the runtime.

**The A/B design.** One block now measures one metric at one size, so an alternating pair
straddles seconds instead of minutes. A two-sample t-test at alpha 0.95 replaced the
median-versus-spread heuristic, and every row publishes its minimum detectable effect so
a null result means something. Both encode rows F-12 could not resolve now resolve:
typed encode@16 at -6.4% (MDE 6.2%) and @64 at -6.7% (MDE 1.5%).

**Two gates that did not exist.** `conformance/efficiency.lock.json` pins byte and token
counts for this codec's output; any drift in either direction fails. `make ab` exits
non-zero on a slowdown that reproduces.

Three discoveries, each from a task that refused to accept inspection as proof:

1. **The token gate did not fire when first tested.** Every locked payload was a uniform
   record array, which the encoder emits as a tabular block — and a uniform
   object-of-objects becomes a *keyed* tabular block. Neither ever reaches the
   `key: value` entry writer, so perturbing the key separator moved no locked byte count.
   Fixed by adding an `irregular` shape that defeats both forms; the perturbation now
   fails with `irregular@16/toon_comma: locked 727 bytes, measured 771`.
2. **The speed gate could not fire at all.** Against the frozen `v0.1.0-conformant`
   baseline, a real 24% slowdown (typed decode 139 -> 172 us) read as **+2.2%, "no
   significant difference"** — the current build led that baseline by 15-20%, so a
   catastrophic regression merely erased the lead. Resolved by splitting the roles:
   `.venv-baseline` is the **story** (what the optimization round bought; reported, never
   gated) and `.venv-guard`, built from the latest release, is the **gate**. The same 24%
   slowdown against the guard reads +24.4%, reproduces, and exits 1.
   *The guard must be re-cut at every release or it decays into the same blind spot.*
3. **A same-power confirmation run is not enough.** The first confirmation design re-ran
   at the same block count; `typed encode@4096` flagged at +2.5% and reproduced, then read
   +2.1% with a 2.6% MDE at three rounds. Confirmation now runs at **double** the blocks,
   and it immediately caught a live false positive: `untyped encode@64` flagged at +1.5%
   and did not reproduce.

Also of note: a first attempt at proving the speed gate used `black_box` over 40
additions, which compiled to nothing (137.67 vs 139.03 clean) — the gate was right to stay
quiet, and the lesson is that a "deliberate slowdown" must be verified to be one.

```text
gate                        result
────                        ──────
corpus                      538/538, zero divergences
make check                  33 Rust + 88 Python tests, clean
make g2                     G2 zero builtin containers
make efficiency             lock matches
make ab (gate vs v0.2.0)    16/16 no significant difference, exit 0
make ab-story (vs v0.1.0)   16/16 resolved faster: typed decode -14.3/-17.0/-16.9/-18.1%,
                            untyped decode -11.8/-15.5/-18.2/-17.6%,
                            typed encode -6.4/-6.7/-6.2/-3.4%,
                            untyped encode -8.6/-6.6/-7.2/-6.3%
```

Left open, honestly: a possible ~2% typed-encode regression at 4096 against v0.2.0. It
flagged once, failed to resolve at higher power twice, and is recorded in the ledger as
unresolved — neither claimed nor dismissed.
