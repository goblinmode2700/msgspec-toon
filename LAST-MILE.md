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

- [ ] F-05 replace release-wheel allocation counters with independent test instrumentation.
- [ ] Rerun G3 and G5 without atomic counter bias.
- [ ] F-11 generate the known-gap report from one maintained support matrix.
- [ ] F-12 alternate A/B blocks and publish raw repetitions plus spread.

Exit: each performance and G2 claim has independent, same-session evidence.

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
