## ADDED Requirements

### Requirement: Distributed timing preserves complete same-run cells

Distributed benchmark execution SHALL schedule only complete experimental cells. A cell's
calibration, warmup, measured worker processes, and all implementations used by its same-run
comparison SHALL execute on one runner. Distribution SHALL NOT reduce the configured worker
count, sample count, payload ladder, shape coverage, or statistical gate strength.

#### Scenario: One cell remains one experiment

- **WHEN** a timing cell executes through the distributed path
- **THEN** its raw evidence identifies one runner for calibration, every measured worker, and
  every compared implementation
- **AND** its estimator and sample policy match the canonical serial path

#### Scenario: Sharding does not buy speed by deleting evidence

- **WHEN** the distributed and serial manifests for one revision are compared
- **THEN** they contain the same typed, codec, and integration cell identities
- **AND** every cell contains the required raw worker observations

### Requirement: Distributed evidence is complete and identity-bound

Every distributed result SHALL record its cell and shard identities, source revision, package
version, measured wheel digest, dependency-lock digest, timing schema, estimator, environment
fingerprint, loop counts, and raw worker observations. Aggregation SHALL fail on a missing,
duplicate, stale, mixed, or incompatible result. Scheduling and artifact arrival order SHALL
NOT determine the canonical result order.

#### Scenario: A partial matrix cannot produce a report

- **WHEN** any expected shard or cell artifact is absent or duplicated
- **THEN** aggregation fails and no distributed report is eligible for publication

#### Scenario: Mixed artifacts cannot produce a report

- **WHEN** two result artifacts disagree on source revision, package version, measured wheel
  digest, lock digest, timing schema, estimator, or sample policy
- **THEN** aggregation fails and identifies the incompatible fields without publishing timings

#### Scenario: Completion order does not alter evidence order

- **WHEN** the same complete cell set arrives in a different scheduling order
- **THEN** aggregation emits cells in the manifest's canonical order

### Requirement: Distributed evidence is qualified before release use

The distributed path SHALL NOT replace the single-runner canonical release path until a
committed qualification record shows three complete runs with equivalent cell coverage and
gate decisions, no false regression in source-identical A/A checks, and no systematic
shard-assignment effect that changes a published claim. Before qualification, every distributed
result SHALL identify itself as non-canonical.

#### Scenario: An unqualified distributed run stays experimental

- **WHEN** distributed evidence exists without the required qualification record
- **THEN** it is labelled non-canonical
- **AND** release evidence continues to use the single-runner path

#### Scenario: Qualification protects published decisions

- **WHEN** distributed execution is proposed as a release-evidence source
- **THEN** three complete qualification runs show matching cell coverage and gate decisions
- **AND** source-identical A/A checks report no false regression

### Requirement: Distribution reduces measured evaluation wall time

The distributed benchmark stage SHALL achieve at least a twofold reduction in median wall time
across three runs relative to a serial control measured from the same source revision and wheel.
The evidence SHALL report queue time separately, per-shard setup and measurement time, the
critical path, and total runner-minutes. Workflow setup and transfer time SHALL NOT be included
in codec time measurements.

#### Scenario: The workflow reports the actual trade-off

- **WHEN** a distributed qualification run completes
- **THEN** its evidence reports wall time, queue time when observable, critical-path time, and
  total runner-minutes separately from codec timings

#### Scenario: Concurrency without sufficient benefit is rejected

- **WHEN** the median of three distributed benchmark stages is less than twofold faster than
  the paired serial controls
- **THEN** the distributed path does not become canonical release evidence

### Requirement: The initial distributed path uses bounded public infrastructure

The initial distributed benchmark path SHALL use standard GitHub-hosted Linux runners with an
explicit concurrency bound and short artifact retention. It SHALL process only public or
generated benchmark data and SHALL require no long-lived secret. Self-hosted runners, larger
runners, Hetzner, and GCP SHALL remain outside this change.

#### Scenario: Public benchmark work needs no private runner

- **WHEN** the distributed workflow is inspected
- **THEN** every benchmark shard uses a standard GitHub-hosted Linux runner
- **AND** no benchmark job receives a long-lived credential or private payload
