## ADDED Requirements

### Requirement: Typed container selection is local and wire-aware

Typed decode SHALL select each container plan from the declared type and the observed TOON wire
form. The selection SHALL belong only to that container. A nested selection SHALL NOT change the
selection of its parent, sibling, or next row.

A concrete tagged Struct SHALL validate its discriminator before construction. A tagged union
SHALL select its member before construction. Both paths SHALL construct the selected Struct
without an intermediate built-in object tree.

#### Scenario: Nested concrete tag is valid

- **WHEN** a tabular row contains a nested field group with the declared concrete tag
- **THEN** typed decode constructs the nested Struct and its parent
- **AND** the result matches the equivalent `msgspec.json` result

#### Scenario: Nested concrete tag is invalid

- **WHEN** a tabular row contains a nested field group with a different tag
- **THEN** typed decode raises the public validation error
- **AND** no Struct is returned with the wrong declared type

#### Scenario: Nested tagged union selects its member

- **WHEN** a nested field group contains a valid tag for one union member
- **THEN** typed decode constructs that member directly
- **AND** the result matches the equivalent `msgspec.json` result

#### Scenario: Nested selections do not leak

- **WHEN** adjacent rows or sibling field groups contain different valid tags
- **THEN** each container selects its own declared plan
- **AND** no selection changes another container

### Requirement: Unknown typed values skip without materialization

Typed decode SHALL consume an allowed unknown value without constructing its Python value tree.
The skipped value SHALL obey the same grammar, depth limit, duplicate rules, and row-count rules
as a selected value.

#### Scenario: Valid unknown subtree creates no intermediate tree

- **WHEN** a target permits unknown fields and an unknown field contains nested objects and arrays
- **THEN** typed decode returns the declared target fields
- **AND** allocation evidence records no Python container for the unknown subtree

#### Scenario: Invalid unknown subtree still fails

- **WHEN** an unknown subtree violates a syntax or containment rule
- **THEN** typed decode raises the same public fault class as ordinary decode
- **AND** the decoder does not accept the malformed subtree because it is unknown

### Requirement: Typed state has one meaning for each value

Typed decode SHALL keep plan identity, field action, tag state, and container state distinct.
Invalid internal state SHALL produce a static internal fault. It SHALL NOT select the root plan or
another valid plan as a fallback.

#### Scenario: Tag keys cannot become field indexes

- **WHEN** a tagged Struct receives its discriminator field
- **THEN** typed decode treats the key as a discriminator action
- **AND** the key cannot address a constructor field slot

#### Scenario: Invalid plan traversal fails loudly

- **WHEN** native plan state contains an invalid edge or cycle that plan construction forbids
- **THEN** the operation fails with a static internal or plan error
- **AND** the operation does not continue with the root plan

