## ADDED Requirements

### Requirement: The timing estimator is stated and is not a minimum

Published timings SHALL be the mean across independent worker processes, not the minimum
across batches within one process. Each worker SHALL discard its own first measurement as
a warmup, and the loop count SHALL be calibrated once so every worker measures the same
amount of work. The report SHALL name the estimator, the worker count, and the warmup
policy alongside the figures they produced.

A minimum rewards whichever run happened to avoid the scheduler and understates what a
caller experiences; it is also unstable, because the best case has no central-limit
behavior to converge on. A figure produced under one estimator SHALL NOT be restated under
another without re-measurement.

#### Scenario: A published figure names its estimator

- **WHEN** the report states a per-call time
- **THEN** the methodology it carries names the estimator, the worker count, and the
  warmup policy

#### Scenario: A historical figure is not silently reinterpreted

- **WHEN** a figure recorded under a previous estimator appears in the optimization ledger
- **THEN** it is labelled with the estimator that produced it, or re-measured

### Requirement: A/B comparison alternates and tests for significance

A same-session A/B comparison SHALL alternate between the two builds so that machine drift
acts on both sides equally, and SHALL measure one metric at one payload size per block so
that paired blocks are seconds apart rather than minutes. Every block SHALL be retained in
the evidence artifact.

A difference SHALL be reported as a change only when a two-sample two-tailed significance
test at alpha 0.95 rejects the null hypothesis. A difference that fails the test SHALL be
published as "no significant difference" rather than as a small win or loss, and each
metric SHALL carry a minimum detectable effect so that a null result is interpretable.

#### Scenario: A difference smaller than the instrument can resolve is not a result

- **WHEN** the measured difference for a metric fails the significance test
- **THEN** the artifact records no significant difference for that metric, together with
  the minimum detectable effect for that metric at that size

#### Scenario: Drift is measured, not assumed absent

- **WHEN** an A/B run completes
- **THEN** the artifact contains every block, including repeated blocks of the same build,
  from which the run's own variability can be recomputed by a reader

### Requirement: Token efficiency cannot regress silently

The canonical output's byte and token counts for the published payload set SHALL be locked
in a versioned artifact, and a test SHALL recompute them and fail on any difference. The
lock SHALL record the tokenizer name and version, so that a change in the tokenizer is a
failure with a stated cause rather than an unexplained shift in the numbers.

Any change to the lock SHALL be a deliberate edit accompanied by the reason the counts
moved. Both directions SHALL fail the gate: an unexplained improvement is as much a signal
of changed output as a regression, and canonical bytes are a conformance surface.

#### Scenario: Larger canonical output fails the build

- **WHEN** a change increases the byte or token count of canonical output for any locked
  payload
- **THEN** the efficiency test fails and names the payload and both counts

#### Scenario: A tokenizer change is attributable

- **WHEN** the installed tokenizer version differs from the version recorded in the lock
- **THEN** the test fails identifying the version difference, rather than reporting the
  token counts as a codec change

### Requirement: A resolved slowdown fails the benchmark gate

Two comparison baselines SHALL exist and SHALL be kept distinct. The **story** baseline is
the frozen tag the optimization record is written against; it is reported and never gates.
The **guard** baseline is the latest release; it is the only baseline the gate compares
against, and it SHALL be re-cut at every release.

A baseline the current build already outperforms cannot detect a regression: measured, a
24% slowdown against a baseline trailing by 15-20% reads as a 2% difference and fails the
significance test. A gate SHALL therefore not be pointed at the story baseline.

The A/B harness SHALL exit non-zero when any metric is significantly slower than the guard
baseline **and** the slowdown reproduces in an independent confirmation run of greater
statistical power than the test that raised it. A difference that fails the significance
test, or that fails to reproduce, SHALL NOT fail the gate.

The gate SHALL be a separate entry point from the offline developer checks, because it
requires a baseline environment and takes minutes.

#### Scenario: A significant slowdown stops the round

- **WHEN** a metric is slower than the guard baseline, the difference is significant, and it
  reproduces under confirmation
- **THEN** the A/B harness exits non-zero and names the metric, the size, and the effect

#### Scenario: A single significant result is not enough to fail

- **WHEN** a metric reports a significant slowdown that does not reproduce under a
  higher-power confirmation run
- **THEN** the harness records that the slowdown did not reproduce and does not fail

#### Scenario: Noise does not stop the round

- **WHEN** a metric measures slower but the difference fails the significance test
- **THEN** the harness reports no significant difference and does not fail

### Requirement: Comparative claims are made once, where a miss is visible

Comparisons against other codecs SHALL live in the published benchmark ladder and its
named gates, and SHALL NOT be duplicated as assertions in the unit test suite. A unit test
that asserts this codec is faster than another measures the machine it runs on, hides a
gate miss behind an unrelated failure, and grows without bound.

#### Scenario: The comparison has one home

- **WHEN** a comparison against another codec is added
- **THEN** it appears in the benchmark ladder under a named gate, and the unit suite
  contains no equivalent assertion
