## MODIFIED Requirements

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
