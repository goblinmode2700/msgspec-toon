## ADDED Requirements

### Requirement: Open values and scalar unions have an explicit typed policy

The release SHALL declare `object`, non-optional scalar unions, and containers of these
annotations as supported or intentionally rejected. A supported annotation SHALL match equivalent
`msgspec.json` values without an intermediate built-in conversion tree.

An intentional rejection SHALL occur during plan construction. Its stable error SHALL name the
supported alternative when one exists.

#### Scenario: Object policy is executable

- **WHEN** the matrix constructs decoders for `object` and `Any`
- **THEN** each observed result matches its declared support state
- **AND** a refusal for `object` names `Any` as the supported alternative

#### Scenario: Scalar-union policy is executable

- **WHEN** the matrix decodes each member of `int | str` and nested containers of that union
- **THEN** each value matches `msgspec.json` or plan construction rejects the annotation
- **AND** no accepted value selects a different member silently

