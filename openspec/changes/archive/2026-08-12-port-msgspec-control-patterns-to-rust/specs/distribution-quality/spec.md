## ADDED Requirements

### Requirement: Supported interactions cover the codec state space

Release evidence SHALL test supported features across wire form, nesting position, declared plan
shape, and discriminator outcome. A feature SHALL NOT report support only because each part works
in isolation.

The bounded matrix SHALL include ordinary objects, tabular rows, nested field groups, keyed
tabular values, and positional Structs where applicable. It SHALL include concrete Structs,
tagged unions, recursive positions, and unknown fields where applicable.

#### Scenario: Nested field-group tags are differentially checked

- **WHEN** the support matrix checks a tagged type inside a nested field group
- **THEN** it checks correct, wrong, missing, unknown, and wrong-category tags
- **AND** accepted values and rejected values match equivalent `msgspec.json` cases

#### Scenario: Interaction support requires a round trip

- **WHEN** the matrix declares an encodable value interaction supported
- **THEN** it encodes the value and typed-decodes the emitted document
- **AND** the decoded value equals the original value

### Requirement: Architecture checkpoints are isolated and measured

Each architecture checkpoint SHALL state one falsifiable mechanism before a source change. It
SHALL measure only the relevant cases first. Performance measurements SHALL use the existing
same-session estimator and the preceding public release guard.

A performance candidate SHALL be adopted only when the focused measurement resolves its effect
and all protected controls pass. A rejected candidate SHALL be reverted and recorded with its
falsifier. A correctness or safety change can remain when performance is neutral and no protected
floor regresses.

#### Scenario: A performance candidate has a focused control

- **WHEN** a checkpoint changes decode dispatch, allocation, or frame state
- **THEN** its focused A/B includes the affected typed case and an ordinary typed control
- **AND** it includes an untyped control when the parser path changes

#### Scenario: An encoder decision change preserves bytes

- **WHEN** a checkpoint changes container classification or rendering
- **THEN** the canonical byte and token locks remain unchanged
- **AND** the focused A/B reports the affected encode shapes

#### Scenario: A resolved regression stops the release

- **WHEN** an adopted checkpoint causes a confirmed regression against a protected floor
- **THEN** the checkpoint is reverted or revised
- **AND** `0.3.0b1` is not qualified with that regression

### Requirement: The 0.3.0b1 report identifies the complete program

The `0.3.0b1` report SHALL list each correctness, safety, architecture, and performance
checkpoint. It SHALL identify each checkpoint as adopted, rejected, or deferred. It SHALL include
the evidence that supports each adopted performance statement.

#### Scenario: A reader can reconstruct the program

- **WHEN** a reader opens the `0.3.0b1` report
- **THEN** the report names every checkpoint and its result
- **AND** no rejected or deferred candidate appears as an implemented improvement

