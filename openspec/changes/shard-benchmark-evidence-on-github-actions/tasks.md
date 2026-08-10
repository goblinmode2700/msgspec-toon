## 1. Define the cell and evidence contracts

- [ ] 1.1 Enumerate the current four typed, sixteen codec, and sixteen integration cells in one checked-in manifest with stable IDs and canonical order.
- [ ] 1.2 Define and test a versioned raw-result schema containing artifact identity, environment fingerprint, loop counts, worker observations, and elapsed-time metadata.
- [ ] 1.3 Add a duration-recording mode and use one serial control to assign all 36 cells across twelve balanced three-cell shards.

## 2. Make existing benchmarks selectable

- [ ] 2.1 Add cell selection and raw JSON output to the existing benchmark entry points without adding a second timing implementation.
- [ ] 2.2 Add a local all-cells mode that reconstructs the current report input in manifest order.
- [ ] 2.3 Prove with tests that the new local path preserves worker count, sample policy, loop calibration, raw observations, gates, bytes, and token inputs.

## 3. Build fail-closed fan-in

- [ ] 3.1 Add a collector that derives the expected set from the manifest and rejects missing, duplicate, misplaced, stale, mixed, or schema-incompatible evidence.
- [ ] 3.2 Add adversarial collector tests for partial matrices, duplicate cells, mixed revisions, mixed wheel or lock digests, changed estimator settings, and truncated observations.
- [ ] 3.3 Let `scripts/release-report.py` consume the validated canonical cell union while retaining its current serial execution mode.

## 4. Add the GitHub Actions experiment

- [ ] 4.1 Add a manual workflow that builds or selects one Linux x86_64 ABI3 wheel and records its revision, version, digest, and lock identity.
- [ ] 4.2 Add twelve `ubuntu-22.04` matrix shards with `max-parallel: 12`; install the exact wheel and locked benchmark dependencies in every shard.
- [ ] 4.3 Upload one compact immutable JSON artifact per shard with short retention, then download and validate the exact set in one fan-in job.
- [ ] 4.4 Record benchmark-stage wall time, observable queue time, per-shard setup and measurement time, critical path, and total runner-minutes without mixing workflow overhead into codec times.

## 5. Qualify before adoption

- [ ] 5.1 Add source-identical A/A canaries that execute within a single shard and fail qualification on a false regression.
- [ ] 5.2 Run three paired serial and distributed workflows from the same revision and wheel; compare coverage, raw schema, gate decisions, shard-assignment effects, wall time, and runner-minutes.
- [ ] 5.3 Adopt distributed evidence only if all three runs pass completeness and gate equivalence and the median benchmark-stage wall time is at least twofold faster.
- [ ] 5.4 If qualification passes, connect validated distributed evidence to release report generation while retaining serial rollback; otherwise record the failed hypothesis and leave release generation unchanged.

## 6. Validate and document

- [ ] 6.1 Run strict OpenSpec validation, benchmark contract tests, canonical qualification, and a publication-disabled workflow before enabling any release dependency.
- [ ] 6.2 Update the generated report methodology, `HANDOFF.md`, `LAST-MILE.md`, and the optimization ledger with the qualification result and remaining infrastructure deferrals.
