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

### 0.3.0b3 untyped distinct-key scaling hotfix — QUALIFYING

- [x] Reproduce issue 11 with the ten-worker mean and fixed-size payloads.
- [x] Split address-identity and byte-content key caches.
- [x] Remove cache iteration from ordinary key lookup.
- [x] Add 32-key and 512-key cells to the permanent release guard.
- [x] Add the complete 4-to-1,024-key curve to generated report inputs.
- [x] Pass `make check`, 538/538 corpus, G2, G3, and all sixteen G5 cells.
- [x] Rebuild the guard from public `v0.3.0b2` and run the complete A/B ladder.
- [ ] Generate revision-bound evidence and publish `0.3.0b3`.

Hypothesis: `0.3.0b2` scales with distinct-key count because ordinary key lookup scans
the complete mixed-identity cache. Confirmed. A split content map removes that scan and
uses borrowed `[u8]` hash lookup. The complete 100-point guard reports zero reproduced
regressions. The 32-key and 512-key cells improve 36.8% and 87.9% against public `0.3.0b2`.
The cache is decoder-local and unbounded only for one decode call. A bounded direct-mapped
cache remains a separate design because it changes collision, replacement, and free-threading
semantics.

### 0.3.0b2 untyped nested-record hotfix — COMPLETE

- [x] Reproduce issue 10 with the ten-worker mean on nested and irregular records.
- [x] Add both missing shapes to the permanent release guard and generated report contract.
- [x] Localize repeated-key caching to nested ordinary objects while preserving root-entry and tabular paths.
- [x] Pass `make check`, 538/538 corpus, G2, G3, and all sixteen G5 cells.
- [x] Rebuild the guard from public `v0.3.0b1` and run the complete A/B ladder.
- [x] Generate release-bound evidence, publish `0.3.0b2`, and archive the change.

Hypothesis: `0.3.0b1` regressed ordinary nested records because key caching starts only at a
tabular header. Confirmed: nested mixed records were +7.3% and irregular records +14.9% against
`v0.2.0b5`, both independently confirmed. The adopted amortized cache is scoped to non-tabular
list-record objects. In the canonical complete guard against shipped `v0.3.0b1`, nested records
are neutral at -1.1% (MDE 2.1%) and irregular records are 9.0% faster. The complete 98-point guard
reports no reproduced slowdown.

### 0.3.0b1 control-pattern program — ACTIVE

- [x] Record outside-agent issues 08 and 09 as separate strict OpenSpec changes.
- [x] Freeze the public `v0.2.0b5` guard and add the nested-tag interaction/timing matrix.
- [x] Repair nested concrete and union tag selection with a borrowed local probe.
- [x] Compile tag values to native string or signed-integer metadata.
- [x] Support issue-08 `object` and primitive scalar unions through existing direct paths.
- [x] Run and discard the outside spike's learned-cache CP0 after it recovered less than half of the correctness tax.
- [x] Replace ordinary/root object pending-tag flags with container-local state.
- [x] Complete phases 4-10 in `port-msgspec-control-patterns-to-rust/tasks.md`.
- [x] Accept and publish the measured 5.96 ns/row nested-tag correctness residual.
- [x] Pass the complete release guard with no reproduced protected regression.
- [x] Generate release-bound evidence, target-check the artifact matrix, publish, and archive the change.

Measured checkpoint finding: ordinary typed, root tagged, and untyped nested controls did not show
a reproduced slowdown. Nested concrete tagged rows cost 7-9% against `v0.2.0b5`, which skipped tag
validation. The first Python-equality repair cost 15-27%; native tag metadata removed most, but not
all, of that cost. A disposable learned-cache CP0 tested the body-scoped compilation hypothesis.
It improved the repaired build by 3.2% at 4096 rows but still measured 4.7% slower than
`v0.2.0b5`; 512 rows did not resolve. That is less than half of the 7-9% tax, so the candidate was
discarded under its stated falsifier. A new profile and mechanism are required before more
header-scoped compilation work.

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
- [x] **C-00 enforce constraints (`msgspec.Meta`).** No lettered finding — the adversarial
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

#### Checkpoint 10 — C-00 constraint enforcement

Hypothesis: the compatibility membrane already exposes every constraint needed for
supported scalar and collection plans, so a boxed optional constraint record can enforce
them at scalar conversion or container completion without an intermediate tree and without
a measurable cost on unconstrained payloads.

Confirmed, after one rejected representation. `_plan.py` now lowers length constraints for
lists, variable tuples and dictionaries and compiles patterns once with Python's own regex
search semantics. Rust stores schema values without narrowing Python-precision integers;
numeric comparisons and remainders use Python operations, strings use Unicode character
length, and collection lengths are checked before the final declared container is placed.
Every failure uses the static `constraint` fault and never stores the rejected value.

The first implementation stored the full constraint record inline in every `CompiledPlan`.
The release-guard gate reproduced `keyed decode@512` **+2.0% slower**, so that layout was
rejected. Constraints are now boxed: an unconstrained plan carries one nullable pointer.
A focused 8-block rerun saw +1.9% initially but the double-power confirmation did not
reproduce it; the subsequent full 42-row gate had no reproduced slowdown.

```text
gate                        result
────                        ──────
focused differential        29 passed (accepted and rejected boundaries)
make check                  36 Rust + 118 Python passed; 4 G2-only tests skipped
corpus                      538/538, zero divergences
make g2                     zero builtin containers; 129 Structs + 1 final list
efficiency lock             unchanged
G3                          pass at every size
G5                          pass both directions at every size
G4                          known existing miss at 4..512; pass at 4096
make ab                     no reproduced slowdown across 42 rows
support matrix              12 supported, 2 parity-rejects, 13 unsupported,
                            0 silently ignored, 0 silently wrong
```

Changed: `python/msgspec_toon/_plan.py`, `src/plan.rs`, `src/typed.rs`, `src/error.rs`,
`tests/test_constraints.py`, the generated support matrix/report, and this handoff ledger.
No dependency or canonical byte changed. Next: H3's third-path build-identity experiment.

### D. Hot-path hardening

- [ ] F-16 add the D1 transition matrix and debug stack assertions.
- [ ] F-17 add `SAFETY:` proofs and boundary tests for every unsafe block.
- [ ] F-18 bound the untyped content-key cache after measurement. The `0.3.0b3` hash
      lookup removes scan cost but leaves entries unbounded for one decode call.
- [ ] F-19 measure wide-object duplicate detection before changing its data structure.
- [ ] F-20 measure wide-dictionary shape checks before changing membership lookup.

Exit: all unsafe and memo invariants have executable tests or local proofs.

### E0. External review round — DONE

A five-candidate perf stack arrived from an outside model with correctness verified in a
container and **speed explicitly unmeasured** ("`make guard && make ab` on your machine
before adoption"). That framing was correct and is why this went well: every candidate was
adjudicated by measurement here, and one was rejected.

- [x] **D6 hashed duplicate-key set.** Adopted. Keyed decode −19.3/−51.9/−88.4% at
      64/512/4096. The candidate warned that the ladder could not see it; that was true, so
      the keyed payload landed first.
- [x] **P2 single-pass scalar classifier.** Adopted. Decode −3 to −5%, encode −7% (the
      encode share via `needs_quote`, which E5 then took over). 111,126-token differential.
- [x] **E5 one-pass quoting, span-copy escaping.** Adopted. Typed encode −17% cumulative,
      ~10 points of it E5's. 107,841-pair differential; canonical bytes unmoved.
- [x] **D5 trusted positional replay.** Adopted. Typed decode −3 to −4%, with untyped and
      encode flat as the confining control.
- [x] **E7 struct field tuple (`msgspec.structs.astuple`).** **Rejected on measurement.**
      Applied: typed encode −5.7/−7.5/−6.6/−5.8%. Reverted, nothing else changed:
      −20.4/−16.1/−16.6/−16.5%. It costs ~9–10 points at every size. Its own stated
      falsification condition fired. Not adopted conditionally either: dispatching on field
      count would put a magic number in the hot path and a second field-read implementation
      beside the first. G4 and R-02 are unchanged.

Lesson worth keeping: **a candidate that ships its own falsification condition is worth
more than one that ships a benchmark.** E7 named the exact condition under which it would
lose, which made rejecting it a ten-minute measurement instead of an argument.

### E. Continued efficiency work

- [x] Run symbolized profiles for typed decode and Struct encode at small and large sizes.
- [ ] Complete equivalent symbolized profiles for untyped decode and dictionary encode.
- [x] Rank costs by measured inclusive time. `needs_quote` leads encode;
      `split_cells_into` and absent-`Any` forwarding lead focused decode candidates. E4
      list collection is demoted to roughly 1–2% of sampled stacks.
- [x] **H3:** build source-identical code at a third path and publish the observed
      build-identity resolution floor.
- [x] **H5 A/B block setup:** an only-metric block skips timing unrelated metrics but
      still constructs and round-trips every incumbent payload before the timer. Profile
      the parent and child separately; remove only setup the selected callable cannot use.
      Falsifier: block wall time does not fall, the selected callable/loop/sample policy
      changes, or a source-identical A/B comparison stops reporting parity.
- [x] **P4a functional evidence surface:** add same-run rows for functional `encode()` and
      `decode()`. Hypothesis: constructing a codec and rebuilding/attaching plans on every
      call is a resolvable small-payload cost.
- [x] **P4b native decode-plan reuse:** port msgspec's compiled-Struct-metadata pattern;
      retain opaque native plans behind the existing 512-entry annotation cache, not codec
      wrapper objects.
- [x] **P4c native encode-plan reuse — REJECTED:** remove repeated functional plan compilation without
      a wrapper-object cache or unbounded global class map.
- [ ] **H6 family-wise A/B confirmation — DEFERRED:** 54 rows make isolated alpha-0.05 decisions a
      multiple-comparison family. Two full runs flagged different untouched encode metrics,
      and neither survived a longer focused control. Do not hand-roll this analysis in the
      benchmark harness. Preserve raw blocks and use an established bulk statistical tool
      with a predeclared family-wise procedure if the owner reopens it.
- [x] **E8 quoting specialization:** branch once on the first byte so strings that cannot
      be numeric-like skip numeric-state tracking. Falsifier: the existing >100k quoting
      differential moves or the typed/untyped encode ladder cannot resolve a win.
- [x] **D7 one-pass quote-free cells — REJECTED:** use a combined quote/delimiter search so the
      common quote-free row is scanned once. Falsifier: quoted-heavy control regresses or
      the typed/untyped decode ladder cannot resolve a win.
- [x] **D8 cold Any forwarding:** avoid constructing/forwarding an `AnyEvent` when no
      `Any` subtree is active. Falsifier: Any/dec-hook behavior changes, G2 moves, or typed
      decode cannot resolve a win.
- [x] **E9 wide-dictionary shape:** add the diagnostic payload first, then replace the
      per-key linear search with first-row map membership only if wide rows expose the
      predicted `O(rows * columns^2)` cost without regressing the canonical five-column
      ladder.
- [ ] Record rejected candidates with their measurements.
- [ ] Keep the canonical token ladder and losing shapes in every report.

Exit: each adopted optimization has a frozen-baseline A/B result and all protected gates pass.

#### Checkpoint 11 — H3 third-path resolution experiment

Hypothesis: if source-path-driven binary layout causes the old +1.0 to +1.8% bias on
`entry decode@512`, a third build of identical `v0.4.0` source at a different path will
differ from the `v0.4.0` guard by about one percent with the same persistent sign.

Falsified. The third source lived at `/private/tmp/msgspec-toon-h3-src`, produced a release
abi3 wheel installed in `.venv-h3`, and was compared to `.venv-guard` over 8 blocks per
side. `entry decode@512` measured **-0.5%**, MDE **1.1%**, no significant difference; the
baseline canary spread was 2.5%. Source path is therefore not a confirmed permanent cause
of the older bias. The published focused resolution is 1.1% for this session; the practical
full-ladder floor remains roughly 1–2% on quiet rows and is larger wherever that row's MDE
says so.

`ab.py` now accepts `--current-venv`, making third-build and other immutable-wheel
comparisons explicit without swapping the editable working extension behind its freshness
check. The evidence is `benches/ab-guard-vs-h3.json`. Next: profile the harness's own
Python/orchestration cost, then add functional API rows.

#### Checkpoint 12 — H5 Python harness profile and metric-scoped setup

Hypothesis: `MSGSPEC_TOON_ONLY_METRIC` skipped unrelated timers but not their setup, so an
A/B child still encoded and decoded the slow incumbent payload before timing a completely
different callable. Selecting setup by the same metric name should shorten blocks without
changing process isolation, calibration, loop counts, warmup, samples, or statistics.

Confirmed. Parent cProfile put 3.484 of 3.495 seconds in subprocess polling; JSON,
statistics, and orchestration are negligible. For `entry decode@512`, an ordinary block
took 0.4369 seconds, of which 0.2971 seconds were the three published samples. The 0.1398
second remainder includes one deliberate discarded sample (~0.097 seconds), process/import
cost, and unrelated setup. Child cProfile found about 0.028 seconds in `sample_run` setup,
including a `python-toon` round-trip the selected metric could not use.

After metric-scoping setup, the same child profile put about 0.002 seconds outside
`measure`. In a 20-pair alternating diagnostic with a fixed one-loop entry-decode probe,
mean whole-process time fell from **43.04 ms to 34.24 ms (-20.5%)**. Full sampler paths
still execute every setup/assertion. A source-identical 8-block-per-side comparison remained
parity (+0.3%, no significant difference; noisy 6.7% MDE), recorded in
`benches/ab-h5-parity.json`.

The discarded current-side calibration block remains. It cannot warm a later interpreter,
but it symmetrically faults that build's binary/code pages into the OS cache before the
measured sweeps. Removing independent process launches or the discarded warmup would change
the estimator rather than merely remove overhead, so neither was attempted.

#### Checkpoint 13 — P4a functional API evidence

The reusable-codec ladder did not measure the package-level `encode()` and `decode()` calls,
which construct a codec on every invocation. Added functional rows to both the generated
ten-worker report and the guard A/B metric table without changing codec behavior.

The cost resolves at small payloads. At 16 records, functional decode measured 8.89 us versus
4.77 us reusable (**+86%**), and functional encode measured 4.97 us versus 2.01 us reusable
(**+147%**). At 64 records the premiums were 27% and 42%; at 512 they were 5% and 10%.
At 4096 the difference fell into run noise (decode +0.6%, encode -2.1%). This confirms a
fixed construction/plan-attachment mechanism worth attempting, bounded to the functional
surface. Next: make retention and concurrency semantics explicit, then test one reuse design.

#### Checkpoint 14 — P4b native decode-plan reuse

The first cache design was rejected before implementation. Caching Python Decoder/Encoder
objects would add policy around the codec, and a shared Encoder's native plan map could retain
unbounded runtime Struct classes through an `Any` or container payload.

Reading exact msgspec 0.21.1 source supplied the cleaner pattern: its functional JSON decoder
uses local per-call state and reuses compiled `StructInfo` stored with the Struct type. This
codec now compiles the lowered `PlanSpec` once into an opaque, shareable `NativePlan` behind
the existing 512-entry `compile_plan` retention boundary. Decoder instances clone an `Arc`;
they are not themselves cached. The full survey and adopt/reject boundary are recorded in
`docs/implementation-spec/prior-art-native-codec-2026-08-07.md`.

Typed Decoder construction fell from about **3.36 us to 0.21 us**. A same-session three-round
guard A/B (`benches/ab-p4b-decode.json`) measured functional decode **-40.0% at 16** records,
**-15.7% at 64**, and **-4.5% at 512**. At 4096, -3.0% was just below that run's 3.2% MDE.
Apply the same compiled-metadata principle to encode without introducing a global wrapper
cache. H6 is deferred; focused same-session A/B remains the candidate acceptance evidence.

The full guard exposed a harness defect rather than a stable codec regression. One ladder
failed on typed encode@64 (+3.0%); a six-round focused control measured -0.2%. A second full
ladder did not repeat that row, but failed on functional encode@4096 (+4.8%); its six-round
focused control reported +2.9% with a 7.2% MDE. These encode paths cannot reach the decode
plan, and no flagged row repeated across full runs. With the expanded 54-row family, the
alpha-0.05 plus solo-confirmation policy is no longer adequate. Both controls are retained as
`benches/ab-p4b-*-control.json`; H6 is deferred to raw-data bulk analysis with established
statistical tooling, not another hand-written Python statistics layer.

#### Checkpoint 15 — E8 first-byte quoting specialization

Hypothesis: most emitted strings start with an ordinary nonnumeric byte. Splitting that path
before numeric-state tracking, as `serde_toon_format` does, should remove work from the hot
`needs_quote` scan without changing canonical bytes.

Confirmed. The port remains conservative for this codec's accepted numeric-like spellings:
only a first byte outside `0-9 . e E + -` bypasses numeric tracking, while delimiter, control,
colon, quote, and backslash checks still scan the full string. The existing differential
oracle checked **107,841 string/delimiter pairs with zero divergences**; all 36 Rust tests,
119 Python tests, the 538/538 corpus, payload-safety tests, and G2 passed.

Three-round same-session focused A/B resolved improvements at every size for the reusable
paths: typed encode **-3.0/-4.4/-5.3/-4.2%**, entry encode
**-16.5/-16.7/-17.1/-17.1%**, and untyped encode **-2.7/-3.1/-4.0/-3.2%** at
16/64/512/4096 records. Functional encode was unchanged at 16 (-1.3%, MDE 1.8%) and faster
at 64/512/4096 (**-2.4/-4.6/-4.7%**). Evidence is retained in
`benches/ab-e8-*-encode.json`. Adopted.

#### Checkpoint 16 — P4c native encode-plan reuse rejected

Hypothesis: functional encode recompiles enough immutable Struct field/shape metadata that
retaining an opaque native `Arc<EncodePlan>` behind the existing 512-entry Python class cache
will resolve the small-payload premium without caching Encoder objects or adding an unbounded
global class map.

Falsified. The candidate moved native field interning and static-shape compilation behind the
bounded cache while leaving each Encoder's writer, hooks, options, and encountered-class map
local. A same-session three-round comparison used an immutable checkpoint-15 wheel as the
baseline, so E8 was present on both sides. Functional encode moved **-1.8/-2.1/+0.3/+0.0%**
at 16/64/512/4096 records; every row was below its MDE and reported no significant
difference. The candidate and its cache test were removed. The functional encode floor is
therefore elsewhere; do not re-spend native encode-plan compilation without a new profile.

#### Checkpoint 17 — D7 combined quote/delimiter scan rejected

Hypothesis: replacing the quote-presence pass plus delimiter pass with one `memchr2` scan
will resolve a decode win on quote-free tabular rows. On the first quote, the candidate kept
already-proven delimiters and resumed the old quote-aware scan from the current cell.

The semantic part passed: a differential oracle compared the candidate with the prior
splitter across **411,771** generated rows over comma, pipe, and tab delimiters with zero
divergences; all 37 Rust tests passed. The performance hypothesis did not. Three-round
same-session A/B found no significant improvement on typed or entry decode. Typed was
-0.4/+0.9/-8.9/-0.0% (the +0.9% flag did not reproduce; the -8.9% row had an 18.2% MDE),
and entry was -0.5/-0.6/-0.2/+0.3%. Untyped trended slower at
**+7.0/+2.5/+2.6/+0.8%**, also below each row's MDE. The stated falsifier fired, so both
implementation and oracle were removed. Evidence remains in `benches/ab-d7-*-decode.json`.

#### Checkpoint 18 — D8 cold `Any` forwarding

Hypothesis: the typed consumer's ordinary schema path pays a call and event-dispatch shape
for every parser event even though `any_sub` is almost always `None`. Guarding before
constructing `AnyEvent` and outlining `any_forward` as cold/noinline should reduce hot-path
code and branches while preserving the existing untyped sub-consumer for actual `Any` and
`dec_hook` subtrees.

Confirmed. Six event methods now test `any_sub.is_some()` before constructing an event;
the existing forwarding state machine is unchanged behind the cold branch. Same-session
three-round A/B measured typed decode **-9.0/-10.0/-9.3/-7.1%** at
16/64/512/4096 records, with MDEs of 0.8–1.3%. All 36 Rust tests, 119 Python tests
(including support, containment, `Any`, and hook cases), the 538/538 corpus, payload-safety
checks, and G2 passed. Evidence: `benches/ab-d8-typed-decode.json`. Adopted.

#### Checkpoint 19 — E9 diagnostic and `toon-rust` prior art

Added a permanent `wide dict encode` metric before changing classification. Its payload is
a uniform array of 64-column Python dicts; later rows rotate insertion order, so tabular
eligibility requires key-set membership rather than positional equality. The generated
payload round-trips through canonical tabular output.

Mean-across-ten-worker measurements were stable across row counts: 4/8/16/64/512 rows cost
22.72/44.38/88.30/355.39/2944.27 us, or **5.52–5.75 us per row**. The source mechanism is
the predicted nested scan: every key of every later row calls
`first_keys.iter().any(...)`. The diagnostic therefore isolates the wide-row cost without a
row-count slope confound.

The owner-supplied `toon-format/toon-rust` source was inspected at `2136cb1`. It cannot be
adopted: encode materializes, clones, and normalizes an owned Serde/JSON value tree; decode
uses owned `Vec<char>` tokens and values; its v3 grammar and `i64/u64/f64` numbers violate
TOON 4.1, G2, and Python-precision integers. Its tabular detector does provide direct E9
prior art: first-row keys live in `IndexMap` and later rows use `contains_key`. The detailed
verdict is in `docs/implementation-spec/prior-art-native-codec-2026-08-07.md`.

#### Checkpoint 20 — E9 hashed dictionary membership

The TOON 4.1 specification supplied by the owner confirms the precise rule: every row object
must have the same key set, order per object may vary, and header order comes from the first
object (§9.3). With equal dict lengths, probing every first-row key in each later dict proves
set equality. The candidate therefore stores the first row's actual Python key objects,
checks them with `PyDict_Contains`, and reuses them as column accessors. It removes the nested
UTF-8 extraction/string-comparison scan without changing eligibility or canonical order.

Against the immutable checkpoint-19 wheel, three-round A/B measured wide dict encode
**-58.1/-61.9/-66.9/-67.9/-67.4%** at 4/8/16/64/512 rows. The canonical untyped encode
ladder also improved **-31.5/-37.2/-37.1/-36.9%** at 16/64/512/4096. Typed Struct encode,
which does not use dict membership, was parity at 16 and faster by 1.7–3.3% at the larger
sizes; no control regressed. Two focused tests lock varying insertion order and equal-width
different-key fallback. All 36 Rust tests, 121 Python tests, 538/538 corpus, payload safety,
and G2 passed. Evidence: `benches/ab-e9-*.json`. Adopted.

#### Checkpoint 21 — upstream Struct capsule shot

Hypothesis: a versioned msgspec capsule that exposes the existing per-class Struct offsets,
combined with exact-class validation, critical sections, and strong field references in the
Rust consumer, can retain most of the raw G4 proof's gain without binding the abi3 wheel to
an undocumented layout.

Confirmed for the mechanism, not for the complete gate. The upstream-shaped msgspec patch
is commit `6391020`; the optional consumer is commit `aa27f5e` on branch
`g4-upstream-capsule`. A same-binary ABBA-shaped ten-worker run measured the capsule path
14-22% faster than the attribute fallback. It beats `to_builtins` at 512 and 4096 records,
but remains behind at 4, 8, 16, and 64. Safety therefore consumes part of the disposable
proof's gain and the fixed-cost G4 miss remains.

The capsule header shipped in a built wheel. Both capsule and exact-stock-0.21.1 fallback
configurations passed `make check` and the 538-case corpus; G2 remained green. CPython 3.14t
ran the capsule producer tests and a same-object concurrent mutation/encode stress test with
the GIL disabled. The stock fallback A/B found no reproduced slowdown, although `ab.py`
failed only when constructing an output filename from the supplied absolute venv paths.

Ruling at checkpoint 21 was to preserve the upstream patch and consumer branch without
merging a dormant path. The owner subsequently requested a runnable activation workflow.
Main therefore contains the optional consumer, while ordinary stock-0.21.1 builds retain
the attribute fallback. `make fastpath-build` owns a separate `.venv-fastpath`, fetches the
exact msgspec source commit, applies the repository patch, installs both release wheels,
and fails unless the Encoder reports `capsule`. Upstream acceptance plus a new exact pin
remains the production-default activation gate. The bounded local optimization loop is
stopped again.

### F. Distribution finish

- [ ] Lift the PyO3 cooldown pin only after its time gate and `make audit` pass.
- [x] Build and verify the 12-wheel CPython 3.13 abi3 / CPython 3.14t target matrix plus
  one sdist across macOS, Linux, and Windows on x86_64 and arm64.
- [x] Add reusable canonical validation and release CI for source checks, conformance,
  G2, target-native installed-artifact verification, manifest collection, and evidence.
- [x] Prove every canonical component failure stops the canonical pipeline and a failed
  reusable validation skips all publication-dependent jobs (OpenSpec task 2.4).
- [x] Publish `0.1.0b3` through the registered PyPI Trusted Publisher and protected GitHub
  `pypi` environment; verify all files, attestations, release evidence, and fresh installs.
- [ ] Archive completed OpenSpec changes after their deferred tasks close.

#### Checkpoint 22 — `0.1.0b3` release-trust qualification

Hypothesis: one build-once, verify-target-natively workflow can produce a publication set
whose source, target, digest, installed import origin, version, and codec behavior are all
machine-bound, while a failed or unauthorized run cannot reach PyPI.

Confirmed through the publication-disabled boundary at public source revision
`f0546e65b95295f7b27858f7387ee5d73d04f19c`. GitHub Actions run `31310610453` completed
with 29 successful jobs and two intentional skips: PyPI publication and GitHub release.
The collector accepted exactly 12 wheels and one sdist. Every artifact retained a unique
SHA-256, target identity, clean-environment import origin, installed version `0.1.0b3`,
and passing representative round trip. The qualification report is bound to that same
revision and artifact manifest.

```text
gate / evidence              result
───────────────              ──────
strict OpenSpec validation   pass
source qualification         ruff, mypy, rustfmt, clippy, cargo test: pass
pytest                       156 total: 151 passed, 5 expected skips
official corpus              538/538, zero failures
G2                            pass, zero builtin containers
G3                            pass
artifact set                  12 wheels + 1 sdist, all target-native verification passed
publication                   skipped; no tag and no PyPI upload
```

G5 required one independent confirmation, and both observations remain evidence. Attempt
1 missed only irregular decode at 512 records: msgspec-toon 477.64 microseconds versus
`toons` 472.82 microseconds (1.02% slower; 2.53% msgspec-toon worker spread). Rerunning
only the evidence job against the unchanged source and artifact set passed all 16
shape-by-size cells in both directions; the same row measured 415.91 versus 475.67
microseconds. No payload, gate, estimator, or code changed. The final generated report
therefore records G5 true, while this ledger preserves the first miss instead of hiding it.
After the fail-closed proof changed the public source revision, the full matrix was rerun
instead of reusing those artifacts. The `f0546e6` report passed all G5 cells on its first
evidence attempt and is the current release evidence.

The workflow found and fixed two real Windows portability defects before the passing run:
fixture-tree hashes now use POSIX relative paths, and fixture/report text I/O is explicitly
UTF-8. Regression tests cover the platform-independent lock.

This checkpoint originally stopped for owner authority and external identity configuration.
Checkpoint 23 records their completion. The token fallback was never restored. The
capability tranche now begins at task 7 for `0.2.0b1`.

Task 2.4 closed after this checkpoint without a live destructive release test. The Makefile
now exposes default-preserving command seams for the existing qualification composition.
The test suite replaces every command with an ordered harmless probe, injects a nonzero exit
at each of 12 boundaries, and proves no later command executes. A second test parses the
release workflow dependencies and proves a failed reusable `validate` job transitively
blocks every build, verification, collection, evidence, publication, and GitHub-release
job; it also rejects an `always()` bypass. The normal `make qualify` path then passed with
38 Rust tests, 151 Python passes plus 5 expected skips, 538/538 corpus, and all four G2
allocation tests.

The public fail-closed checkpoint is commit `f0546e6`. Its fresh publication-disabled run
produced exactly 12 wheels plus one sdist with 13 unique digests and passing target-native
verification. A read-only GitHub API check immediately afterward returned zero configured
repository environments. After explicit publication authorization, the `pypi` environment
was created with a custom `v*` tag deployment policy. The owner registered the documented
PyPI Trusted Publisher tuple, and the release below completed without an API-token fallback.

#### Checkpoint 23 — `0.1.0b3` trusted publication

The owner explicitly authorized publication and registered the PyPI Trusted Publisher.
Annotated tag `v0.1.0b3` resolves to qualified revision `f0546e6`. Tagged run
`31336808348` rebuilt and target-native verified 12 wheels plus one sdist, generated the
complete evidence report, and published the exact collected set through OIDC.

PyPI exposes 13 files whose SHA-256 values exactly match the tagged-run manifest. Its
Integrity API returns a publish attestation for every file with repository
`goblinmode2700/msgspec-toon`, workflow `wheels.yml`, and environment `pypi`.
`pypi-attestations verify pypi` cryptographically verified all 13 files. No
`PYPI_API_KEY` or token fallback was used.

Fresh consumer installs passed on CPython 3.13 ABI3 and CPython 3.14t with the GIL
disabled. Both imported from their clean environment, reported version `0.1.0b3`, and
completed a typed decode/encode round trip.

`make guard` was rerun after publication. The internal optimization repository correctly
retains `v0.4.0` as its latest development guard; the public beta version line is separate,
as recorded in the OpenSpec versioning decision.

The workflow finished 30 jobs green and one post-publication attachment job failed: `gh
release` had neither a checkout nor explicit repository context. Package publication was
already complete. The exact report and manifest downloaded from the tagged run were
attached manually and then downloaded and byte-compared. GitHub release `v0.1.0b3` is a
prerelease. Main commit `7f61585` adds `GH_REPO` to the attachment step and a regression
test; default validation run `31338043228` passed.

The release-trust tranche is complete. The next unblocked OpenSpec item is task 7.1,
`TypePlanError`, for the `0.2.0b1` capability checkpoint. Do not archive the change until
tasks 7 through 14 are complete.

#### Checkpoint 24 — stable typed-plan failure membrane

Hypothesis: every plan-construction failure can cross the Python inspection membrane as one
package-owned `TypePlanError(TypeError)` with a stable code and schema-known path, without
changing native plans, canonical bytes, or timed decode behavior.

Confirmed. `TypePlanError` exposes `code` and an immutable tuple `path`; its message is built
only from those schema components. The lowering context detects an active annotation identity
before Python recursion grows, so recursive Structs now fail intentionally without
`RecursionError`. Nested mapping keys, unsupported multi-member unions, array-like Structs,
inspection failures, unsupported custom types without `dec_hook`, and native compilation faults
use the same membrane. A supplied `dec_hook` still enables custom types. The executable support
matrix now marks plan-construction rejections and asserts their exception contract; counts remain
12 supported, 2 parity rejects, 13 unsupported, 0 silently ignored, and 0 silently wrong.

```text
gate                                      result
────                                      ──────
focused API/matrix tests                  57 passed, 1 free-threaded skip
make check                                38 Rust + 160 Python passed; 5 expected skips
official corpus                           538/538, zero failures
payload safety                            stable messages; sentinel and fault-containment tests pass
G2                                        zero builtin containers; 129 Structs + 1 final list
G3                                        pass at 4/8/16/64/512/4096
G5                                        pass every direction, shape, and size
efficiency lock                           exact match
strict OpenSpec                           pass
isolated phase-7 A/B                      no reproduced slowdown across the full metric family
```

The ordinary release-guard run still reports the pre-existing functional-encode regressions
against `v0.4.0` and one keyed-decode@512 regression. Phase 7 cannot reach either timed path, but
that inference was not used as evidence: two immutable wheels were built from the exact current
tree, differing only in `__init__.py`, `_plan.py`, and the new exception module. Their full
same-session comparison reported every functional-decode row and every reusable-decode row at
no significant difference; the sole initial typed-encode slowdown did not reproduce. Evidence:
`benches/ab-phase7-baseline-vs-phase7-current.json`.

Changed for the checkpoint: `python/msgspec_toon/_exceptions.py`, `__init__.py`, `_plan.py`,
`tests/test_type_plan_errors.py`, the executable support matrix, generated report, OpenSpec task
ledger, and handoff ledgers. No dependency, native code, or canonical byte changed. Next: task
8.1, one frozen option descriptor model shared by functional and reusable entry points.

#### Checkpoint 25 — one option model and functional `float_hook`

Hypothesis: explicit public signatures can share one frozen option descriptor model for names,
defaults, domains, implementation state, applicability, and native forwarding without adding
measurable construction cost.

Confirmed after one pre-measurement correction. Exact msgspec 0.21.1 source keeps explicit C
signatures and parses finite option domains once per codec construction. This project ports that
boundary: signatures stay explicit, while frozen Python descriptors drive the parity,
implementation-state, rejection, and forwarding tests. Dynamic signature generation and a new
dependency were rejected. The first draft routed every native option through a generic Python
loop and dictionary. That design put registry bookkeeping on Decoder construction, so it was
removed before measurement. Rust-owned options retain explicit forwarding and native validation;
the descriptor model validates only Python-owned deferred values.

Top-level `decode()` now accepts and forwards `float_hook`. Functional and reusable calls invoke
the hook with the same text and return the same result. Hook errors propagate unchanged.
`order="sorted"` and `order="deterministic"` raise the same `NotImplementedError` through both
encoder entry points. The README documents these outcomes and the deferred Decimal and UUID
formats. No accepted choice can remain inert in the executable descriptor test.

```text
gate                                      result
────                                      ──────
focused option/API tests                  42 passed, 1 free-threaded skip
make check                                38 Rust + 182 Python passed; 5 expected skips
official corpus                           538/538, zero failures
payload safety                            pass
G2                                        zero builtin containers; 129 Structs + 1 final list
G3                                        pass at 4/8/16/64/512/4096
G5                                        pass every direction, shape, and size
efficiency lock                           exact match
strict OpenSpec                           pass
functional encode A/B                     no significant difference at every size
functional decode A/B                     no reproduced slowdown at every size
```

The functional encode comparison reported +0.2/+0.8/+0.5/+0.6/+0.1/-0.2 percent at
4/8/16/64/512/4096 records, all below its 1.2-3.4 percent MDE. Functional decode reported
-0.7/+1.0/+1.0/+0.6/+0.1/-1.2 percent. The initial +1.0 percent flag at 16 records did not
reproduce at double power. Evidence:
`benches/ab-phase7-current-vs-phase8-encode.json` and
`benches/ab-phase7-current-vs-phase8-current.json`.

Changed: `python/msgspec_toon/_options.py`, `__init__.py`, `tests/test_options.py`, README,
OpenSpec tasks, and the handoff ledgers. No native code, dependency, or canonical byte changed.
Next: task 9.1, native scalar encode differentials against msgspec 0.21.1.

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

#### Checkpoint 26 — msgspec-native scalar encoding without a hot-path regression

Hypothesis: msgspec-native date/time, UUID, Decimal, and Enum values can normalize before the
caller hook without widening the established Rust value or encoder context.

The first two Rust-native designs were rejected. Extra context state and cold functions moved
small-payload encode by 7–28 percent. A ninth `Val` variant widened the enum from 24 to 32 bytes
and slowed entry payloads. The adopted design reuses the existing hook membrane. A private exact
string subtype carries preformatted scalar text only on the cold path; exact Decimal text never
passes through `f64`. Default encoders retain `enc_hook=None`. Dynamic shape discovery bypasses
the fallible native probe for exact built-ins and attempts tabular shape before subclass/native
scalar fallback.

```text
gate                                      result
────                                      ──────
focused native scalar/options             47 passed
make check                                39 Rust + 209 Python passed; 5 expected skips
official corpus                           538/538, zero failures
G2                                        zero builtin containers; 129 Structs + 1 final list
G3                                        pass at 4/8/16/64/512/4096
G5                                        pass every direction, shape, and size
G4                                        known miss through 512; pass at 4096
efficiency lock                           exact; beta-2 shared bytes unchanged
strict OpenSpec                           pass
same-session encode A/B                   no reproduced slowdown in five focused families
```

The executable support matrix is now 15 supported, 2 parity rejects, 12 unsupported, 0 silently
ignored, and 0 silently wrong. Preserved A/B artifacts are
`benches/ab-phase8-current-vs-phase9-{typed,functional,entry,untyped,wide}.json`. The higher-power
wide-dict confirmation measured -1.4 percent at 512 and +1.7 percent at 4096, both below MDE.
Next: task 10.1, bounded recursive annotation graph tests.

#### Checkpoint 27 — bounded recursive annotation graphs

Hypothesis: indexed plan edges can add recursive Struct support without an intermediate value
tree or a reproducible typed-decode regression.

The Python membrane now compiles annotations by identity with explicit visiting and complete
states. Its frozen graph uses integer edges. Rust validates those edges once and owns one bounded
arena. The typed consumer carries node indexes, so self-recursion and mutual recursion do not
create recursive owners. Unsupported recursive aliases fail as `TypePlanError`; hostile document
depth still fails with the static `depth_limit` message.

```text
gate                                      result
────                                      ──────
recursive graph tests                     6 passed
make check                                39 Rust + 215 Python passed; 6 expected skips
official corpus                           538/538, zero failures
G2                                        pass; recursive probe: 0 builtin dicts/lists, 3 Structs
same-session Decoder construction A/B     +2.4%, MDE 3.0%; no significant difference
same-session typed decode A/B             no reproduced slowdown at 4/512/4096
```

The executable matrix adds recursive Structs as supported. Next: task 11.1, array-like Struct
differentials.

#### Checkpoint 28 — array-like Structs and object-form tagged unions

Array-like Structs now use positional frames. Object-form tagged unions use bounded scalar
preflight and then consume the selected compiled Struct plan directly. Tagged array-like unions
fail at plan construction. The focused differentials, containment checks, payload-safety checks,
and G2 proof pass. The first preflight implementation slowed ordinary typed decode by 14-23%; the
accepted parser entry split reduced that cost to a residual 3-5%, but did not eliminate it.

#### Checkpoint 29 — permissive scalar policy and mapping-key decision

`strict=False` bool, integer, and float conversion is table-driven against msgspec 0.21.1.
Strict mode remains unchanged. Non-string mapping keys remain an explicit `TypePlanError` for
`0.2.0b1`; no silently wrong string-key result is possible. The support matrix records both
decisions. Compile-time strict/permissive specialization and cold outlining were each measured,
rejected, and fully reverted because neither removed the ordinary typed-decode regression.

#### Checkpoint 30 — native fuzzing

The separate pinned cargo-fuzz workspace has arbitrary-byte parser and structure-aware integer
round-trip targets. Deterministic corpora contain 420 parser seeds and 4 integer seeds. Sustained
900-second runs completed 70,600,192 and 96,297,862 executions respectively, with zero crash
artifacts. The cooldown audit covers both Cargo lockfiles and `uv.lock`.

#### Checkpoint 31 — capability qualification stop

Canonical qualification passes: 39 Rust tests; 259 Python tests with 7 expected skips; 538/538
official fixtures; 84/84 strict-error fixtures; six G2 probes with zero intermediate builtin
containers; strict OpenSpec validation; and the package cooldown audit. G3 and every G5 cell pass.
G4 retains its known miss through 512 records and passes at 4096. The complete release guard
against `v0.4.0` passes, including typed decode 3.6-6.1% faster and functional encode 7.2-79.5%
faster.

The closer feature-checkpoint comparison does not pass. Against the immutable phase-8 wheel,
the final reverted source measured typed decode +2.5% at 4 records (confirmation did not
reproduce), +1.8% at 16 (MDE 3.7%), +4.8% at 64 (MDE 1.1%, reproduced), +4.8% at 512 (MDE
1.2%, reproduced), and +3.7% at 4096 (MDE 1.0%, reproduced). Artifact:
`benches/ab-phase8-current.json`.

Four attempted mechanisms are rejected and absent from source: direct arena references, merged
Struct frames, compile-time strict specialization, and cold permissive-conversion outlining.
Tasks 11.5 and 12.4 therefore remain open. Publication authority exists, but the qualification
stop fires first. Do not tag or publish `0.2.0b1` without a new measured mechanism that closes the
closer regression, or a separately approved OpenSpec change that explicitly revises this gate.

#### Checkpoint 32 — S3 restores ordinary Struct-completion inlining

Hypothesis: array-like Struct support added a second `finish_struct` call site, which changed
LLVM's release inlining decision. The phase-8 binary had no standalone `finish_struct` symbol;
the current binary outlined a 2,064-byte function and called it once per completed Struct row.
Forcing that unchanged body inline should recover a per-row typed-decode cost.

Confirmed. The only source change is `#[inline(always)]` on `finish_struct`. Against an immutable
wheel from the immediately preceding source, an eight-round focused comparison measured typed
decode **-3.3% at 64 records (MDE 1.2%)**, **-2.8% at 512 (MDE 0.6%)**, and **-2.3% at 4096
(MDE 2.1%)**. Every relevant row resolved faster. `make check` passed 39 Rust tests and 259 Python
tests with 7 expected skips; the official corpus remained 538/538 with 84/84 strict errors; all
six G2 probes passed with zero intermediate builtin containers.

Against the immutable phase-8 checkpoint, initial slowdown flags at 64 (+1.6%) and 512 (+1.2%)
did not reproduce under the gate's double-power confirmation. The 4096 row still reproduced at
**+1.8%**, so tasks 11.5 and 12.4 remain open and publication remains stopped. Next: S4, one fused
typed `scalar_field` event for tabular leaves, with the generic key-then-scalar fallback retained
as the semantic oracle during the experiment.

#### Checkpoint 33 — S4 fuses tabular typed scalar-field dispatch

Hypothesis: each tabular leaf cell paid twice for the generic event membrane: `key` selected a
field and stored awaiting state, then `scalar` rediscovered the expected plan and placement. A
single typed event can preserve the generic semantic oracle while removing that repeated state
transition from ordinary Struct rows.

Confirmed. `Consumer::scalar_field` defaults to the original `key` then `scalar` sequence. The
parser calls it only for tabular leaf cells; nested field groups keep the original object events.
The typed Struct override performs the same memoized lookup, duplicate/unknown/tag handling,
conversion, and direct value placement without an awaiting-state round trip.

Against the exact S3 wheel, an eight-round focused A/B measured typed decode **-4.4% at 64
records (MDE 0.9%)**, **-5.7% at 512 (MDE 1.5%)**, and **-4.1% at 4096 (MDE 0.7%)**. An untyped
control was no significant difference at 64 and 4096 and 1.6% faster at 512. Against the immutable
phase-8 capability checkpoint, 64 was no significant difference, while 512 and 4096 were 5.0%
and 3.1% faster. The release regression is closed.

`make check` passed 39 Rust tests and 259 Python tests with 7 expected skips. The official corpus
remained 538/538 with 84/84 strict errors. All six G2 probes passed with zero intermediate builtin
containers. G3 and every G5 cell passed. `make bench` returns nonzero only for the pre-existing G4
encode misses through 512 records; S4 does not touch encode. Artifacts:
`benches/ab-s4-base.json`, `benches/ab-s4-untyped.json`, and
`benches/ab-phase8-current.json`. OpenSpec tasks 11.5 and 12.4 are complete.

#### Checkpoint 34 — S5 fuses nested field-group opening

Hypothesis: after S4 removed the leaf-cell awaiting-state round trip, nested field groups still
paid `key`, then `start_object`, then `expected_plan_or_fault` for every row. Passing the resolved
child plan directly into frame setup should remove this repeated discovery without changing the
generic event contract.

Confirmed. `Consumer::start_object_field` defaults to the original `key` then `start_object`
sequence. The parser uses it only for nested tabular field groups. The typed Struct override keeps
the same memo lookup, duplicate/unknown/tag handling, then opens the child with the resolved plan.

Against the exact S4 wheel, the eight-round focused A/B measured typed decode **-1.6% at 64
records (MDE 0.8%)**, **-1.9% at 512 (MDE 0.7%)**, and **-1.1% at 4096 (MDE 0.8%)**. Every row
resolved faster. The untyped control stayed within its MDE at all three sizes. `make check` passed
39 Rust tests and 259 Python tests with 7 expected skips; the official corpus remained 538/538
with 84/84 strict errors; all six G2 probes passed with zero intermediate builtin containers.
Artifacts: `benches/ab-s5-base.json` and `benches/ab-s5-untyped.json`.

The S4 symbolized 4096-row profile selected this slice: nested `start_object` accounted for 24 of
536 native decode samples, while nested `end_object` accounted for 47 and generic
`expected_plan`/`place` remained visible. S5 changes only opening. S6 may test direct child-return
placement, but it must be a separate frame-layout candidate with its own exact S5 baseline.

#### Checkpoint 35 — S6 fuses nested field-group return

Hypothesis: a nested tabular Struct still closed through generic `end_object` and `place`, even
though the parser knows this close corresponds to the field group opened immediately before it.
A fused close can finish the child and store it through the parent's existing awaiting index
without changing frame layout.

Confirmed. `Consumer::end_object_field` defaults to ordinary `end_object`. The parser uses it
only for nested tabular groups. The typed fast path activates only when the top two frames are
Structs; `Any`, skipped values, Dicts, root rows, and all other shapes retain the original path.

The eight-round exact-S5 ladder measured typed decode **-1.5% at 512 (MDE 1.1%)** and **-1.1% at
4096 (MDE 1.0%)**. Its 64-row samples were noisy, so a separate sixteen-round run put power only
on that decision and resolved **-0.8% (MDE 0.5%)**. Untyped decode remained within MDE at 64,
512, and 4096. `make check` passed 39 Rust tests and 259 Python tests with 7 expected skips; the
corpus remained 538/538 with 84/84 strict errors; all six G2 probes passed.

The post-S6 symbolized profile no longer lists `expected_plan_or_fault` among top stacks and shows
generic `place` at only 6 samples. `emit_row_fields` is now the largest native self-time at 78
samples, beside `split_cells_into` at 70. S7 may compile the recursive header tree once into a
flat borrowed op tape. Its falsifier is no resolved typed or untyped decode win against exact S6;
if it fires, revert S7 and stop. Artifacts: `benches/ab-s6-ladder.json`,
`benches/ab-s6-64-confirmation.json`, and `benches/ab-s6-untyped.json`.

#### Checkpoint 36 — S7 flat row-op tape rejected; program stop

Hypothesis: `emit_row_fields` self-time reflects repeated recursive traversal and dynamic
leaf/group classification of the same header tree on every row. Compiling the borrowed header
tokens once into `StartObject`, `Scalar`, and `EndObject` operations should remove that work.

Falsified for the typed objective. Against the exact S6 wheel, eight-round typed decode was no
significant difference at every size: **+1.5% at 64 (MDE 1.6%)**, **+1.5% at 512 (MDE 3.1%)**,
and **+0.1% at 4096 (MDE 1.9%)**. Untyped decode improved 2.1% at 64 but was parity at 512 and
4096. The large rows, which should best amortize one-time compilation, did not move. The lone
small untyped result does not support the proposed recursive-traversal mechanism and does not
justify the typed trend in the wrong direction.

S7 is fully reverted. Artifacts: `benches/ab-s7-typed.json` and
`benches/ab-s7-untyped.json`. The accepted program is S3 through S6. It recovered the capability
regression and then removed three separately measured tabular event transitions. The post-S6
profile is dominated by cell splitting, scalar classification/conversion, Python string and
Struct construction, and parser loop attribution. No remaining redundant dispatch mechanism is
named. The row-dispatch improvement loop stops here under C9.

#### Checkpoint 37 — `0.2.0b1` publication-disabled artifact qualification

Hypothesis: the capability beta can pass the complete build-once, target-native verification
matrix and bind its generated evidence to one public source revision without reaching a
publication job.

The first public candidate exposed one cross-platform defect and failed closed. Run
`31372177264` built all 13 artifacts, but the Windows x86_64 ABI3 installed-wheel suite found that
`scripts/seed_fuzz_corpus.py` read the official UTF-8 fixtures through the CP1252 locale. The
artifact round trip itself passed. No collection, evidence, publication, or release job ran. The
generator now requests UTF-8 explicitly; internal commit `b5dd2fd` and public commit `222dac4`
contain the fix.

Canonical validation run `31372838214` passed on public revision
`222dac4475fa145e56c73c842e08dde214941c6f`. Publication-disabled run `31372936154` then completed
29 jobs successfully and skipped only PyPI publication and GitHub release attachment. It built
and verified 12 wheels plus one sdist across CPython 3.13 ABI3 and CPython 3.14t on macOS, Linux,
and Windows, x86_64 and arm64. The combined manifest contains 13 unique SHA-256 digests and names
only version `0.2.0b1` and source revision `222dac4`.

The generated report is bound to the same revision and manifest. It records 538/538 official
fixtures, 84/84 strict errors, G2 pass, G3 pass, every G5 cell pass, and the known honest G4 miss.
The exact downloaded report, qualification summary, manifest, and artifacts are retained under
`.git/release-runs/31372936154/`; they are not part of the public repository. OpenSpec task 14.3
is complete. Owner authority permits the task-14.5 trusted publication step; task 14.4 remains
open until post-publication evidence is recorded and the completed change can be archived.

#### Checkpoint 38 — `0.2.0b1` trusted publication

The owner explicitly authorized publication. Annotated tag `v0.2.0b1` names exact qualified
public revision `222dac4475fa145e56c73c842e08dde214941c6f`. Trusted-publishing run
`31376466704` completed 31 jobs successfully: canonical qualification, twelve wheel builds,
twelve target-native wheel verifications, sdist build and verification, exact-set collection,
generated evidence, PyPI publication through OIDC, and GitHub release attachment. The evidence
job ran from `09:56:52Z` to `10:16:20Z` (19 minutes 28 seconds), a hosted-runner control for the
new benchmark-sharding proposal.

PyPI contains exactly twelve wheels and one sdist. All thirteen SHA-256 values match the
workflow's verified manifest with no missing, extra, or mismatched file. Pinned
`pypi-attestations==0.0.30` cryptographically verified all thirteen files against repository
identity `https://github.com/goblinmode2700/msgspec-toon`. Fresh isolated installs passed a typed
Struct encode/decode round trip on CPython 3.13.1 ABI3 and CPython 3.14.7 free-threaded with the
GIL disabled. The GitHub release's `report.json` and `verified-release.json` are byte-identical
to the tagged workflow evidence retained under `.git/release-runs/31376466704/`.

The workflow created the beta release without GitHub's prerelease flag. The public release was
corrected immediately, and public main commit `f4c280b` adds `--prerelease` plus a regression
test; all 18 release-workflow tests pass. This post-tag workflow fix changes no published wheel,
sdist, report, or tag. OpenSpec tasks 14.4 and 14.5 are complete. The capability change's twelve
added and four modified requirements were synced into seven strict-valid authoritative specs,
then the complete change was archived as
`2026-08-10-qualify-beta-release-and-expand-msgspec-parity`. The active change is now the
unimplemented GitHub Actions benchmark-sharding proposal.

#### Checkpoint 39 — post-`0.2.0b2` round-trip parity repair

Five deployment-focused reports were reproduced from the agent-generated issue bundle dated
2026-08-10. Four open GitHub issues track the actionable gaps; the benchmark JSON-baseline report
was already satisfied by `0.2.0b2` and was closed with credit to the reporting agents.

The shared root cause for tagged and array-like Struct encode was plan truncation: Python already
lowered the metadata, but the Rust encode plan discarded it. The repair retains the discriminator
as a constant plan value, includes it in object and tabular output, and routes array-like Structs
through the positional sequence writer. Direct field reads remain intact and no built-in encode
tree was added.

Typed native scalar decode uses a distinct plan kind for datetime, date, time, timedelta, UUID,
Decimal, string Enum, and integer Enum. The inspection membrane reconstructs timezone-constrained
targets. Rust converts one parser scalar, calls msgspec's public scalar converter, and discards
payload-bearing conversion errors before it creates the package validation fault. The arbitrary
custom-type path and user hook semantics remain separate.

The support matrix now requires round-trip probes for supported value shapes. It splits native
scalar families and number categories, and it classifies whole-float behavior as a fixture-required
format divergence. TOON 4.1 requires `1.0 -> 1` and `-0.0 -> 0`; changing those bytes was rejected
under C1. README and tests disclose the untyped integer result and negative-zero sign loss.

Evidence: 39 Rust tests and 285 Python tests pass; 8 environment-specific tests skip. The official
corpus remains 538/538 and 84/84. Seven G2 probes pass, including the new native-scalar Struct,
with zero intermediate built-in containers. The fresh ten-worker report records G2, G3, and G5
pass, the known G4 miss, 26 supported matrix entries, zero silent failures, and zero shared locked
wire changes. Both the bounded OpenSpec change and all authoritative specs validate in strict mode.
Public commit `90ef919` is on `origin/main`, and issues #1, #2, #3, and #5 are closed with the
evidence above. The completed OpenSpec change is archived as
`2026-08-10-repair-roundtrip-parity-after-0-2-0b2`. Public evidence commit `a0a3866` carries the
report and regenerated figures bound to tested package revision `90ef919`.

#### Checkpoint 40 — `0.2.0b3` qualified and published

The round-trip repair was promoted without changing the repaired source. Public release commit
`9aab586f9a85452ac0c2351a3875f0326f2003f3` changes only the Python/Rust package versions and
closes the changelog section. Local `make qualify` passed 285 Python tests with 8 expected skips,
39 Rust tests, the 538/538 official corpus, 84/84 strict-error fixtures, and all seven G2 probes.
Default-branch validation run `31405095549` passed on that exact SHA.

Publication-disabled run `31405238364` built and target-verified twelve wheels plus one sdist,
then generated a release report bound to `0.2.0b3` and `9aab586`. The manifest contained 13 unique
artifacts; G2, G3, and G5 passed and the known G4 miss remained explicit. Only PyPI publication and
release attachment were skipped. The downloaded qualification summary, report, manifest, and
artifacts are retained below `.git/public-origin/.git/release-runs/31405238364/`.

After that gate passed, annotated tag `v0.2.0b3` triggered trusted-publishing run `31407671281`.
All build, target-native verification, exact-set collection, evidence, OIDC publication, and
GitHub prerelease-attachment jobs passed. PyPI contains exactly the trusted run's twelve wheels and
one sdist, with no missing, extra, or mismatched SHA-256 values. Pinned
`pypi-attestations==0.0.30` cryptographically verified every file against repository identity
`https://github.com/goblinmode2700/msgspec-toon`. The GitHub release is marked prerelease and its
two evidence assets match the trusted run's SHA-256 values.

Fresh installations from PyPI, outside the repository cooldown configuration, passed direct
round trips for tagged Structs with datetime, UUID, and Decimal fields and for array-like Structs.
CPython 3.13.1 loaded the ABI3 extension; CPython 3.14.7 free-threaded loaded the cp314t extension
with the GIL disabled. Trusted artifacts, PyPI JSON, and evidence are retained under
`.git/public-origin/.git/release-runs/31407671281/`. The feedback round has reached its stop
condition: every reported issue is closed and no measured optimization lead remains.

#### Checkpoint 41 — tagged array-like decode repair

Outside-agent issue 06 showed that `0.2.0b3` could encode a tagged `array_like` Struct but could
not decode the same bytes. The concrete path treated the discriminator as field zero and could
reach `internal error`; Python plan lowering rejected the union path.

The repair ports the relevant msgspec 0.21.1 C decoder boundary. The first positional scalar is a
discriminator prelude. A concrete plan validates it; a homogeneous tagged array-like union uses
it to select a compiled member plan. Declared field placement starts afterward. Selection matches
the scalar category before equality, so Python's `True == 1` and `1.0 == 1` rules cannot select an
integer tag. Mixed object and positional variants remain a plan error. Construction still uses the
public Struct constructor and allocates no intermediate dictionary or list tree.

The support matrix adds the ten feature pairs from the outside-agent review as executable round
trips. The generated report now records 36 supported entries, 2 parity rejects, 4 unsupported
entries, 1 fixture-required format divergence, and zero silent failures. Canonical bytes and token
counts are unchanged.

Final gates: 39 Rust tests and 308 Python tests pass with 8 expected skips; the official corpus is
538/538 with 84/84 strict-error fixtures; all seven G2 probes pass; all seven authoritative specs
and the active change validate strictly. The complete ten-worker report records G2, G3, and G5
pass and the known G4 miss.

Focused A/B used exact pre-repair commit `1f07cf5`, not the older `v0.4.0` tag. Ordinary
positional decode showed no significant difference at 4, 46, 512, or 4096 records. The 46-record
control was repeated at double power: +1.01%, MDE 3.48%, no significant difference. Candidate
absolute means at 46 records were 4.33 microseconds for untagged positional decode, 5.15
microseconds for concrete tagged positional decode, and 5.79 microseconds for tagged-union
positional decode. No before/after speed claim is possible for the repaired operations because the
baseline could not execute them.

Internal repair commit `1935432` preserves the active OpenSpec change. Public source commit
`bb45915` and release candidate `2d458ab` export only package, test, benchmark, README, changelog,
and generated-evidence surfaces. GitHub issue 6 tracks the repair. Publication-disabled artifact
qualification run `31436015350` is in progress; no `v0.2.0b4` tag exists yet.

#### Checkpoint 42 — `0.2.0b4` qualified, published, and verified

Local canonical qualification passed on public release candidate
`2d458ab19bd0186b8758b4824c266c9d240200a1`. Default-branch validation run `31435888269` then
passed on the same revision. Publication-disabled run `31436015350` completed 29 jobs
successfully and skipped only PyPI publication and GitHub release attachment. It built and
target-verified twelve wheels plus one sdist, collected exactly thirteen unique files, and
generated a report bound to version `0.2.0b4`, revision `2d458ab`, and the verified manifest.

After that gate passed, annotated tag `v0.2.0b4` triggered trusted-publishing run `31438123425`.
Every canonical validation, build, target-native verification, exact-set collection, evidence,
PyPI OIDC publication, and GitHub prerelease-attachment job passed. PyPI contains exactly the
trusted run's twelve wheels and one sdist. There are no missing, extra, or SHA-256-mismatched
files. Pinned `pypi-attestations==0.0.30` verifies all thirteen PEP 740 attestations against
repository identity `https://github.com/goblinmode2700/msgspec-toon`.

Fresh PyPI installs outside the repository cooldown configuration pass concrete and union tagged
`array_like` round trips and reject boolean/float tokens for integer tags. CPython 3.13.1 loads
the ABI3 wheel. CPython 3.14.7 free-threaded loads the cp314t wheel with the GIL disabled. The
GitHub release is a non-draft prerelease. Its `report.json` and `verified-release.json` are
byte-identical to the trusted workflow artifacts.

Public evidence commit `165536b` places the trusted report and regenerated benchmark figures on
`main`; it changes no tagged package artifact. Issue 6 is closed with release and verification
evidence and thanks the outside agents that found the cross-feature hole. Trusted artifacts,
qualification inputs, manifest, report, and release assets are retained below
`.git/public-origin/.git/release-runs/31438123425/`.

#### Checkpoint 43 — issue-07 recoverable indentation mismatch

The outside-agent option-surface review found that `encode(..., indent=1)` emits a document the
default width-two decoder rejects, while the old error did not expose the setting needed to repair
the call. The wire carries no indentation declaration. GitHub issue 7 credits the agents and
tracks the repair. Their triple-feature probes also confirm the issue-06 tagged positional vein is
exhausted.

The report allowed inference or a recoverable error. Automatic inference was implemented first:
omission differed from explicit configuration and scanner state selected the first positive data
indentation once, without copy or retry. Correctness passed, but exact-source A/B against `8f25b9a`
reproduced reusable typed decode 2.0-2.3% slower at 46 records. A same-binary automatic/explicit
control was neutral, and forcing explicit width two on both A/B sides remained slower. With the
cause unresolved, C9 rejected the candidate. A native error-path variant then reproduced
functional decode +2.8% at 46 and was also removed.

The adopted repair changes no Rust source. The Python exception veneer activates only after a
native `invalid_indent`, `depth_jump`, or row-count fault. It scans to the native line coordinate,
counts leading spaces through a zero-copy view, discards the view, and reports only that structural
coordinate plus the recovery action. Source lines, keys, cells, scalar values, and sentinel text
never enter the exception. Bytes, bytearray, memoryview, and str inputs share the behavior.

```text
gate                                      result
────                                      ──────
focused width/error tests                 30 passed
make check                                39 Rust + 322 Python passed; 8 expected skips
official corpus                           538/538; 84/84 strict errors
G2                                        seven probes; zero intermediate builtin trees
efficiency lock                           exact; canonical bytes/tokens unchanged
strict OpenSpec                           seven specs + active change pass
functional decode A/B                     no significant difference at 4/46/512/4096
typed decode A/B                          no significant difference at 4/46/512/4096
untyped decode A/B                        46/4096 flags did not reproduce; all rows pass
```

README states that nondefault `indent` and `indent_size` must agree and documents BOM/CRLF input.
Rejected and adopted timing artifacts are private below `.git/internal-notes/issue-07-benchmarks/`.
Next: public `0.2.0b5` qualification and trusted publication; do not close issue 7 before fresh
artifact and attestation verification.

#### Checkpoint 44 — `0.2.0b5` qualified, published, and verified

Public source commit `2d71d03`, release metadata commit `a2dc4c9`, and lock commit `6d12753`
exported only the issue-07 package, tests, documentation, and release surfaces. Local canonical
qualification passed 39 Rust tests, 322 Python tests with 8 expected skips, the 538/538 official
corpus, 84/84 strict-error fixtures, and all seven G2 probes. Default-branch validation run
`31443406791` passed on release revision `6d12753400ce82b6719529da71fa450494e72b1d`.

Publication-disabled run `31443504775` then completed every applicable job successfully. It built
and target-verified twelve wheels plus one sdist, collected exactly thirteen unique files, and
generated a report bound to version `0.2.0b5`, revision `6d12753`, and the verified manifest. Only
PyPI publication and GitHub release attachment were structurally skipped.

Annotated tag `v0.2.0b5` triggered trusted-publishing run `31445176169`. Canonical validation,
fresh builds, target-native verification, exact-set collection, the complete ten-worker report,
PyPI OIDC publication, and GitHub prerelease attachment all passed. PyPI exposes exactly the
trusted manifest's thirteen files with no missing, extra, or SHA-256-mismatched artifacts. Pinned
`pypi-attestations==0.0.30` cryptographically verifies all thirteen PEP 740 attestations against
`https://github.com/goblinmode2700/msgspec-toon`.

Fresh installs outside the repository cooldown configuration passed on CPython 3.13.1 ABI3 and
CPython 3.14.7 free-threaded with the GIL disabled. Both typed round-tripped widths one and four
when configured explicitly and produced the new observed-indentation recovery message under the
default width. The GitHub release is a non-draft prerelease; its report and manifest are
byte-identical to trusted workflow artifacts.

Public evidence commit `98c67de` carries the trusted report and regenerated R figures. Validation
run `31446911918` passed on it. Issue 7 is closed with the evidence above and thanks the outside
agents who found the option-surface mismatch. Trusted candidate and publication artifacts remain
under `.git/public-origin/.git/release-runs/31443504775/` and `31445176169/`. The feedback round has
reached its stop condition.

#### Checkpoint 45 — minimal nested-tag selection memo adopted

The schema-compiled tag-matcher spike split the nested-tag correctness cost into structural
selection and tag validation. Before codec source changed, four timing contrasts were added for
nested unions, tag-last groups, quoted tags, and integer tags. A prospective gate required at
least a 2% improvement at 4096 nested-concrete rows with ordinary and untyped controls protected.

The candidate reuses the existing trusted row-memo cursor. The first row records the parent field,
declared plan, discriminator field, and raw-cell offset. Later rows bypass repeated header-to-plan
and discriminator-location work. They do not bypass correctness: each row still classifies and
validates its own tag, and each union row independently selects its member. No row program, parser
ordinal, extra callback argument, Python container, or payload-derived error state was added.

The higher-power A/B against the preserved repaired build measured nested concrete -4.3% at 512
(MDE 1.2%) and -3.4% at 4096 (MDE 1.5%); nested union measured -3.7%/-3.3%; tag-last measured
-4.6%/-3.5%. Untyped decode was neutral. An initial ordinary 4096 slowdown did not reproduce.
Tag-last matched rather than exceeded tag-first, so the stronger scan-position multiplier theory
is not supported. Raw A/B artifacts remain private under `.git/research/e1-*.json`.

`make check` passed 39 Rust tests and 366 Python tests with 10 expected skips before two focused
memo-revalidation regressions were added. The official corpus
passed 538/538 with 84/84 strict errors. All nine G2 probes passed with zero intermediate builtin
containers, the byte/token lock tests passed, G3 and G5 passed at every size, and the known G4
small-payload misses remained. Next: test the plan-compiled exact-spelling
matcher as a separate checkpoint with the present classifier and tag comparison as the complete
cold fallback.

#### Checkpoint 46 — exact-spelling tag matcher rejected

The candidate compiled one exact raw spelling per ordinary bare string or integer tag. A hit
bypassed scalar classification and exact tag comparison. Every miss used the unchanged complete
path, so quoted spellings, escaped strings, `-0`, wrong categories, and faults retained current
semantics. The focused semantic suite passed 41 tests.

At 4096 rows, nested concrete measured -3.8% with a 4.9% MDE and nested union +1.5% with a 4.6%
MDE; neither result resolved. Integer tags improved -1.5% with a 1.3% MDE. The quoted cold path
was neutral. The untyped 512-row control reproduced +1.0% slower with a 0.8% MDE even though it
cannot use a typed plan. This is binary-layout collateral and violates the protected-control gate.
The matcher was fully reverted. Raw results remain under `.git/research/e2-*.json`.

#### Checkpoint 47 — E3 attributes and accepts the nested-tag residual

E3 changed no codec source. The existing A/B harness collected four-round nested-concrete ladders
for the correct repaired build versus CP-S and for `v0.2.0b5` versus CP-S. A benchmark-only repair
made metric selection skip unrelated assertions, allowing an older guard to measure the selected
case without executing newer union diagnostics.

`benches/slope.R` fits absolute microseconds from 128 worker-process means with a session effect,
build-specific record slopes, and HC3 covariance. CP-S is 151.34 ns/row (95% CI
150.35-152.34), the correct repair is 153.80 (152.75-154.85), and `v0.2.0b5` is 145.38
(144.05-146.71). The CP-S-minus-repair contrast is -2.46 ns/row (CI -3.91 to -1.01). The
CP-S-minus-release contrast is +5.96 ns/row (CI 4.30-7.63). The interleaved A/B remains the
release authority; this model is attribution only.

Symbolized ten-second macOS profiles were collected from isolated release-optimized builds with
symbols retained. They were not used for timing claims. `select_object_field` self-samples fall
from 41/835 on the repair to 23/837 on CP-S. The remaining selection work includes the required
per-row tag check. Row emission, cell splitting, scalar/Python conversion, Struct allocation, and
GC remain larger surrounding costs. No separate call-overhead bucket supports CP-T2, and CP-T
already demonstrated binary-layout collateral. The inline split is not attempted. The remaining
5.96 ns/row versus `v0.2.0b5` is accepted as the measured correctness cost under the present
architecture. Private raw A/B, model output, workload, and profiles are under `.git/research/e3-*`.
Final `make check` passed 39 Rust tests and 368 Python tests with 10 expected skips. Strict
OpenSpec validation passed.

#### Checkpoint 48 — object preflight selection becomes container-local

Pattern: container-local schema selection. The exact msgspec C decoder carries its current
`TypeNode` through the recursive decode call, Serde carries caller state through a visitor or
seed, and this codec's nested field-group path already returns selection directly to one object.
The adopted verdict is to port that value flow into ordinary/root preflight, not to replace the
`Consumer` trait or add another callback side channel.

`object_scalar_hint` now updates parser-owned `ObjectSelection`. The parser passes that value to
`start_selected_object` for the exact root, ordinary child, tabular row, keyed row, or list-item
object. `TypedConsumer` no longer contains `pending_object_plan` or `pending_invalid_tag`.
Selection, invalid-tag, skip, and nested-field results cannot outlive or cross the parser call
that owns their container. The parser remains generic and PyO3-free.

A seven-case locality matrix covers root, child, deeper child, siblings, optional, recursive, and
adjacent list objects. Same-session four-round A/B against exact preceding source `f7a0d00` found
ordinary decode neutral at 4-4096 rows and nested-tag decode neutral at every size. Root
tagged-union decode was unresolved through 512 and 2.1% faster at 4096 with a 1.9% MDE. Raw runs
are private under `.git/research/s37-*.json`.

`make check` passed 39 Rust tests and 375 Python tests with 10 expected skips. Corpus conformance
passed 538/538 with 84/84 strict errors. All nine G2 probes passed, the efficiency lock matched,
and strict OpenSpec validation passed. No canonical byte, token, Python API, dependency, or unsafe
boundary changed. Next: task 4.1, define the bounded `PlanId` and field-action hypothesis before
changing representation.

#### Checkpoint 49 — narrow upstream builder proposed; old offset path constrained

The direct-Struct research uncovered and repaired a lifecycle defect before publication: an
opaque builder that owns its Struct class must participate in cyclic GC, or a class attribute can
form an uncollectable class-to-builder-to-class cycle. The corrected current-main msgspec patch
uses `HAVE_GC`, traverse, clear, and untrack-before-clear deallocation. It keeps private layouts
inside msgspec and exposes one versioned capability: prepare an opaque token, then consume
declared-order owned field references to build the final Struct.

Draft PR `msgspec/msgspec#1153` is public and linked from issue 958 and PR 961. The focused API
suite passes seven tests. Upstream main passes 6,387 tests with 143 skips on CPython 3.13 and 6,369
tests with 155 skips on CPython 3.14t. The installed header is present in both wheel and sdist.
The downstream TOON corpus passes 538/538 with 84/84 strict errors. A matched current-main A/B
resolves S12 near 5%; S1 needs doubled sampling; S6 is unresolved on confirmation. Production
does not use this proposal and remains pinned to stock msgspec 0.21.1.

The earlier encoder-offset capsule is a separate rejected-layout experiment. It now compiles only
with the non-default `experimental-struct-offset-capi` Cargo feature. Default wheels always use
public attribute access. `make fastpath-build` alone enables the feature and clears its generated
TOON wheel directory before rebuilding, so a stale release cannot create conflicting package
URLs. Default `make check` passes 38 Rust tests and 375 Python tests with 10 skips. Feature tests
pass 40 Rust tests. `make fastpath-check` activates the capsule, passes the same Python suite, and
passes the 538/538 corpus with 84/84 strict errors. No canonical bytes, tokens, dependency pin, or
public Python API changed.
