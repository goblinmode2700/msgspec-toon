# distribution-quality

## Purpose

Packaging, performance floors, and evidence. The distribution is a maturin-built
`abi3-py313` wheel (canvas AD-008) named `msgspec-toon`, runtime-depending on msgspec alone.
Every release claim is a generated report, never an assertion: conformance counts, allocation
proof, and same-run benchmark comparisons (canvas §15–§18; requirements "Speed floors",
"Wheels install without a toolchain", "The runtime dependency tree is empty", "The
conformance report is published with the release").
## Requirements
### Requirement: Speed floors are measured against the named baselines

The implementation SHALL be no slower than the fastest existing compiled TOON codec on the
same payload ladder (1 KiB, 10 KiB, 100 KiB, 1 MiB record arrays), in both directions,
measured in the same run on the same machine against installed release artifacts. Benchmark
gates: G3 — direct typed decode beats untyped decode plus `msgspec.convert`; G4 — whole
direct typed encode beats `msgspec.to_builtins` alone; G5 — no slower than the fastest named
compiled codec at every size in both directions; G6 — the `abi3` wheel itself, not a full-ABI
development build, clears G3–G5. A gate miss SHALL be reported, never masked by payload
selection.

#### Scenario: The comparison runs in one session

- **WHEN** the implementation and the named existing codecs are benchmarked back to back
- **THEN** the implementation is faster or equal at every size in both directions
- **AND** the report names every version it measured against

### Requirement: Wheels install without a toolchain

The distribution SHALL publish stable-ABI (`abi3-py313`) wheels so installation requires no
compiler, no Rust toolchain, and no network beyond the package index, for macOS arm64/x86_64,
Linux x86_64/aarch64, and Windows x86_64.

#### Scenario: A clean machine installs and imports

- **WHEN** the wheel is installed on a machine with no compiler present
- **THEN** the module imports and converts a document successfully

### Requirement: The runtime dependency tree is empty beyond msgspec

The distribution SHALL declare no runtime dependency other than `msgspec>=0.21.1`. Rust crates
are compiled into the extension and appear nowhere in Python metadata. Build-time dependencies
are unconstrained.

#### Scenario: The installed tree holds two names

- **WHEN** the distribution is installed into an empty environment
- **THEN** the environment contains the distribution and msgspec, and nothing else

### Requirement: The conformance report is published with the release

Every release SHALL publish a machine-readable qualification report generated from canonical
test output. The report SHALL state the package version and source revision; TOON specification
version and fixture corpus commit; unit, conformance, containment, support-matrix, and
installed-artifact results; allocation proof; and same-run speed and token evidence. It SHALL
identify new support, removed support, and wire-output changes since the prior public release.
A release without the report SHALL be treated as unqualified.

Benchmarks in the report SHALL record inputs, environment, package versions, raw repeated
measurements, estimator, and observed variation. The report SHALL NOT contain a second
handwritten support table.

#### Scenario: A reader can check the claim without running anything

- **WHEN** the published report is read
- **THEN** it names the package version, source revision, corpus commit, check results, and known
  divergences
- **AND** every installed artifact is represented by target identity and verification result

#### Scenario: Compatibility changes are generated

- **WHEN** the current executable support matrix and wire locks differ from the prior release
- **THEN** the report lists the added, removed, and changed behaviors
- **AND** the changelog summarizes the same generated change set

#### Scenario: Benchmark variation remains inspectable

- **WHEN** the release report contains a performance comparison
- **THEN** it includes the repeated raw observations and variation needed to recompute the claim

### Requirement: The type-support gap list is generated from a verified matrix

The report's type-support gaps SHALL be generated from a single maintained support matrix,
never written freehand. Each matrix entry SHALL declare the behavior of this codec and of
`msgspec.json` on an equivalent document, and a test SHALL execute both and fail when a
declaration stops matching observed behavior — in either direction, so closing a gap without
updating the matrix fails the suite.

Entries SHALL distinguish a rejection from a silent divergence. A parameter accepted and
ignored, or a value accepted and converted differently from `msgspec.json`, SHALL be reported
as such rather than as an unsupported feature: a rejection is visible to a caller and a wrong
value is not.

#### Scenario: A gap cannot outlive its fix

- **WHEN** an unsupported feature starts working
- **AND** the matrix still declares it unsupported
- **THEN** the support-matrix test fails

#### Scenario: Support cannot be claimed without a probe

- **WHEN** the report claims a feature is supported
- **THEN** a matrix entry demonstrates it against `msgspec.json` on an equivalent document

### Requirement: Measurements come from a verified build

A published measurement SHALL come from the release extension in the environment that
actually imports it, and the tooling SHALL verify this rather than assume it. A benchmark
SHALL refuse to run when the extension is older than the sources it was built from, or when
it carries test-only instrumentation.

#### Scenario: A stale extension is refused

- **WHEN** a source file is newer than the built extension the environment imports
- **THEN** the benchmark exits with the rebuild instruction instead of publishing a number

#### Scenario: An instrumented build is refused

- **WHEN** the imported extension carries the allocation counters
- **THEN** the benchmark exits rather than report the timing as a release measurement

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

### Requirement: Reference outputs never override fixtures

Differential testing against the reference TypeScript implementation MAY generate additional
cases, but the official fixture corpus SHALL remain authoritative. A mismatch between the
reference implementation and a fixture SHALL be investigated and reported, not normalized
away. Cross-language numeric cases SHALL include integers outside JavaScript's exact domain.

#### Scenario: A reference divergence is reported

- **WHEN** the reference implementation and a pinned fixture disagree
- **THEN** the report records the divergence with both outputs

### Requirement: Token efficiency is measured against a named tokenizer

The report SHALL publish token counts — the unit TOON's value proposition is stated in —
for every measured wire format at every payload-ladder point, under a named tokenizer
whose name and version appear in the report (primary: tiktoken `o200k_base`; secondary:
`cl100k_base`). Measured formats SHALL include at least: compact JSON, this codec's
canonical output, this codec's tab- and pipe-delimited output, and each installable
incumbent codec's output. The payload set SHALL include the uniform-record ladder plus a
string-heavy and a numeric-heavy variant, so shape-dependence is visible rather than
averaged away. For each point the report SHALL state absolute tokens, the ratio against
compact JSON, and tokens-per-100-bytes.

#### Scenario: Canonical TOON beats JSON in tokens on record payloads

- **WHEN** the uniform-record ladder is tokenized under the primary tokenizer in one run
- **THEN** canonical TOON output costs no more tokens than compact JSON at every point
- **AND** both counts appear in the report with the tokenizer name and version

#### Scenario: The tab delimiter is a measured saving, not folklore

- **WHEN** the same payloads are encoded with the comma and tab delimiters and tokenized
  in one run
- **THEN** the tab-delimited output costs no more tokens than the comma output at every
  ladder point, or the losing points are published as-is

#### Scenario: A losing shape is published

- **WHEN** any measured format loses to JSON in tokens on any payload variant
- **THEN** the report contains that row unchanged — no payload selection hides it

### Requirement: Optimizations are proven against a frozen baseline

Performance-improvement claims SHALL be proven by same-session A/B measurement against a
frozen baseline build (the `v0.1.0-conformant` tag), both sides running the same harness
on the same machine in one session — never by comparison to remembered or previously
published numbers. Every adopted optimization SHALL appear in the report's optimization
ledger with its hypothesis and paired before/after figures; every rejected candidate
SHALL appear with the numbers that rejected it. After each adopted optimization, the
full fixture corpus SHALL report zero failures, the allocation proof SHALL still show
zero intermediates, and gates G3 and G5 SHALL still pass — a speed win that regresses
correctness or the no-tree invariant is a defect.

#### Scenario: An improvement claim carries its paired measurement

- **WHEN** the report claims an optimization improved a metric
- **THEN** the optimization ledger holds a same-session baseline-vs-current pair for
  that metric produced by the A/B harness

#### Scenario: A regression cannot be traded for speed

- **WHEN** a candidate optimization improves a benchmark but causes any fixture failure,
  intermediate allocation, or G3/G5 gate failure
- **THEN** the candidate is rejected and recorded as such in the ledger

### Requirement: Compatibility evidence reports direction and round trip

The generated compatibility report SHALL identify whether each support-matrix entry has a verified
round-trip probe or no applicable round trip. Declared wire-format divergences required by the
pinned corpus SHALL be reported separately from unsupported and silently wrong behavior.

#### Scenario: Generated report exposes round-trip verification

- **WHEN** release evidence is generated
- **THEN** each matrix entry records its round-trip evidence state
- **AND** fixture-required format divergences do not appear as unacknowledged implementation gaps
