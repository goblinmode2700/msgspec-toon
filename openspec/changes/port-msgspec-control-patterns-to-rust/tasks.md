## 1. Freeze the Program Baseline

- [x] 1.1 Record the current source revision, `v0.2.0b5` guard, toolchain, and clean-build identity.
- [x] 1.2 Add the confirmed nested field-group tag reproductions to the issue record.
- [x] 1.3 Add focused benchmark cases before any source change.
- [ ] 1.4 Record frame sizes, plan-node sizes, allocations, and symbolized profiles for affected paths.
- [x] 1.5 Run `make check`, the corpus, G2, G3, G5, byte locks, and token locks.

## 2. Build the Interaction Matrix

- [x] 2.1 Add concrete tagged Struct cases for correct, wrong, missing, duplicate, and unknown tags.
- [x] 2.2 Add tagged-union cases for each discriminator outcome and scalar category.
- [x] 2.3 Cross ordinary objects, tabular rows, nested field groups, keyed tabular values, and positional Structs.
- [ ] 2.4 Cross root, child, deeper-child, sibling, adjacent-row, optional, and recursive positions where valid.
- [x] 2.5 Compare each applicable typed result with equivalent `msgspec.json` behavior.
- [x] 2.6 Add value-to-text-to-typed-value probes for each encodable interaction.
- [x] 2.7 Make the matrix fail on the current nested field-group tag defect.
- [x] 2.8 Rerun issue 08 after local selection and record whether its follow-up remains open.

## 3. Add Local Container Selection

- [x] 3.1 Record the hypothesis for a wire-form and declared-plan selection boundary.
- [x] 3.2 Add the smallest parser-owned wire-form and borrowed-probe types.
- [x] 3.3 Add a static consumer selection result for selected, skipped, and rejected containers.
- [x] 3.4 Select a nested concrete tagged Struct before its constructor frame opens.
- [x] 3.5 Select a nested tagged-union member before its constructor frame opens.
- [x] 3.6 Keep tag-category matching equal to `msgspec==0.21.1`.
- [ ] 3.7 Remove consumer-wide object-tag pending state after all object paths use local selection.
- [x] 3.8 Run the focused interaction suite and allocation probes.
- [x] 3.9 Run focused same-session A/B for tagged, ordinary typed, array-like, and untyped controls.
- [x] 3.10 Run all protected gates and record the checkpoint result.
- [x] 3.11 Falsify the outside `RowShape` proposal with a disposable learned-cache CP0 and discard it after it recovered less than half of the nested-tag tax.
- [x] 3.12 Add nested-union, nested-tag-last, nested-quoted-tag, and nested-integer-tag timing contrasts before another codec source change.
- [x] 3.13 Test a minimal production selection memo against the prospectively recorded 4096-row gate; adopt or revert it as one checkpoint.
- [ ] 3.14 If the memo adopts, test a plan-compiled exact-spelling matcher with the current classifier and tag matcher as its complete cold fallback.
- [ ] 3.15 Attribute any remaining nested-tag cost before attempting an inline hot/cold split; otherwise record the measured residual and stop this performance branch.

## 4. Make Plan and Field State Explicit

- [ ] 4.1 Record the hypothesis for distinct plan IDs and field actions.
- [ ] 4.2 Add a private `PlanId` with checked construction at the plan boundary.
- [ ] 4.3 Replace the tag sentinel with explicit field, tag, skip, and reject actions.
- [ ] 4.4 Move plan compilation, lookup, and selection to the typed state model.
- [ ] 4.5 Move frames and recursive edges to `PlanId` in bounded checkpoints.
- [ ] 4.6 Replace the root-plan fallback with plan validation or a static internal fault.
- [ ] 4.7 Run union, recursive, fixed-tuple, row-memo, and malformed-plan tests after each checkpoint.
- [ ] 4.8 Measure type sizes and focused typed decode after each layout change.
- [ ] 4.9 Revert or revise a checkpoint that causes a confirmed protected regression.

## 5. Add Shared-Grammar Structural Skip

- [ ] 5.1 Record a profile-based hypothesis for unknown-subtree event dispatch.
- [ ] 5.2 Add allocation and event-count probes for unknown nested values.
- [ ] 5.3 Implement parser-owned skip or a zero-work target with shared grammar primitives.
- [ ] 5.4 Preserve quote, indentation, duplicate, row-count, width, and depth validation during skip.
- [ ] 5.5 Cover unknown ordinary objects, arrays, tabular rows, keyed rows, and nested field groups.
- [ ] 5.6 Prove that malformed unknown values still fail with payload-safe faults.
- [ ] 5.7 Prove that valid unknown values create no Python container tree.
- [ ] 5.8 Run focused same-session A/B for unknown-heavy, ordinary typed, and untyped controls.
- [ ] 5.9 Adopt only a resolved design that preserves every semantic control.

## 6. Measure and Reduce Duplicate-Key Ownership

- [ ] 6.1 Profile strict wide objects and repeated object rows for key ownership cost.
- [ ] 6.2 Record the allocation count for bare, quoted, escaped, and duplicate keys.
- [ ] 6.3 Stop this checkpoint if the cost does not resolve above the session floor.
- [ ] 6.4 If the cost resolves, implement borrowed keys or exact collision-checked fingerprints.
- [ ] 6.5 Differential-test decoded-key equality across bare, quoted, and escaped spellings.
- [ ] 6.6 Run strict and non-strict duplicate tests, containment tests, and focused A/B.
- [ ] 6.7 Adopt or reject the candidate with its measured falsifier.

## 7. Consolidate Encoder Decisions

- [ ] 7.1 Profile duplicate container classification across root, entry, list-item, keyed, and tabular paths.
- [ ] 7.2 Record one falsifiable render-decision hypothesis for the largest resolved path.
- [ ] 7.3 Define one render decision that carries the selected view and shape witness.
- [ ] 7.4 Make classification and validation use the same witness that rendering consumes.
- [ ] 7.5 Keep the encode plan authoritative for tags, renames, defaults, `array_like`, and access mode.
- [ ] 7.6 Move only the profiled render path in the first checkpoint.
- [ ] 7.7 Move each remaining resolved path in a separate checkpoint.
- [ ] 7.8 Run canonical corpus bytes, byte locks, and token locks after each checkpoint.
- [ ] 7.9 Run focused A/B for uniform, nested, keyed, irregular, tagged, and array-like shapes.
- [ ] 7.10 Reject any consolidation that changes bytes or causes a confirmed protected regression.
- [ ] 7.11 Rerun issue 09 after render consolidation and record whether its follow-up remains open.

## 8. Complete the Unsafe Membrane

- [ ] 8.1 Inventory each unsafe block and its caller-controlled assumptions.
- [ ] 8.2 Document ownership, liveness, stealing, and failure rules at each FFI block.
- [ ] 8.3 Document the free-threaded critical-section rule for Struct offset reads.
- [ ] 8.4 Document or remove each unchecked UTF-8 conversion.
- [ ] 8.5 Document or replace each unchecked plan-arena access.
- [ ] 8.6 Add negative tests for invalid capsule headers, pointers, field counts, and offsets.
- [ ] 8.7 Run the optional capsule path on CPython 3.13 ABI3 and the free-threaded target.
- [ ] 8.8 Measure any safe replacement that changes a hot path.

## 9. Add Schema-Known Runtime Paths

- [ ] 9.1 Record frame-size and error-path baselines before path state changes.
- [ ] 9.2 Define compact schema field and structural index path parts.
- [ ] 9.3 Derive typed paths from compiled plans and structural positions only.
- [ ] 9.4 Expose the path through public decode and validation errors.
- [ ] 9.5 Add nested Struct, list, tuple, union, recursive, and field-group path tests.
- [ ] 9.6 Prove that sentinel payload keys and values cannot enter any path or error attribute.
- [ ] 9.7 Keep path work off untyped decode and successful error-free formatting paths.
- [ ] 9.8 Run frame-size checks and focused same-session typed and untyped A/B.

## 10. Evaluate Mutable-Buffer Borrowing

- [ ] 10.1 Document the current copy cost for bytearray and memoryview input.
- [ ] 10.2 Profile small and large buffers against bytes and string controls.
- [ ] 10.3 Write the stable-ABI exporter lifetime and mutation-safety proof before source changes.
- [ ] 10.4 Stop and retain copying if the proof is incomplete.
- [ ] 10.5 If the proof is complete, implement one bounded borrowed-buffer candidate.
- [ ] 10.6 Add exporter-lifetime, mutation, exception, and subprocess containment tests.
- [ ] 10.7 Run CPython 3.13 ABI3 and free-threaded target tests.
- [ ] 10.8 Adopt or reject the candidate with focused same-session evidence.

## 11. Qualify 0.3.0b1

- [ ] 11.1 Run `make check`, strict OpenSpec validation, the corpus, G2, G3, and G5.
- [ ] 11.2 Run the complete interaction matrix and require zero silent failures.
- [ ] 11.3 Run canonical byte and token locks and require no change.
- [ ] 11.4 Run the complete release-guard A/B and resolve every significant regression.
- [ ] 11.5 Generate the report with each checkpoint marked adopted, rejected, or deferred.
- [ ] 11.6 Update the support matrix, README, benchmark documents, changelog, handoff, and ledger.
- [ ] 11.7 Set the package version to `0.3.0b1` only after all qualification gates pass.
- [ ] 11.8 Build and target-check all wheels plus the source distribution without publication.
- [ ] 11.9 Publish only after the qualified artifact set passes and current owner authority permits publication.
- [ ] 11.10 Archive the OpenSpec change only after release evidence is complete.
