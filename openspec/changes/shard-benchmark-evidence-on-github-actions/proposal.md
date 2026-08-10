## Why

The complete release report currently runs 36 independent timing cells serially on one
machine and takes about 18 minutes. That delay slows every measured optimization loop even
though GitHub Actions can run complete cells concurrently without changing their estimator.

## What Changes

- Add a deterministic benchmark-cell manifest for the four typed, sixteen codec, and
  sixteen integration cells already measured by the release report.
- Run groups of complete cells on a bounded GitHub Actions Linux matrix. Each cell keeps its
  calibration worker, ten measured worker processes, comparators, and raw observations on
  one runner.
- Upload revision- and wheel-bound raw JSON from every shard, then fail closed in one fan-in
  job on missing, duplicate, incompatible, or mixed evidence.
- Generate the existing report from the validated union of shard artifacts. Keep token
  measurement and report rendering in the collector because they do not dominate runtime.
- Qualify the distributed result against the current single-runner path before it can become
  canonical release evidence. Until then, the single-runner report remains authoritative.
- Target at least a twofold reduction in benchmark-stage wall time without reducing worker
  count, samples, payload coverage, or statistical gates.
- Use public standard GitHub-hosted runners only. Hetzner, GCP, larger runners, and
  self-hosted runners are deferred.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `distribution-quality`: distributed benchmark evidence gains completeness, identity,
  same-host cell, qualification, and wall-time requirements.

## Impact

- `.github/workflows/` gains a benchmark workflow or reusable benchmark job built from the
  repository's existing matrix/artifact/collector pattern.
- Benchmark entry points gain cell selection and raw-result output; `benches/_timing.py`
  remains the only estimator.
- `scripts/release-report.py` gains a validated precomputed-evidence input while retaining
  its local serial mode.
- The generated report gains shard identity, environment fingerprints, artifact digests,
  completeness, execution mode, and wall-time metadata.
- No runtime dependency, codec API, canonical byte, corpus, G2, G3, G4, or G5 behavior changes.
