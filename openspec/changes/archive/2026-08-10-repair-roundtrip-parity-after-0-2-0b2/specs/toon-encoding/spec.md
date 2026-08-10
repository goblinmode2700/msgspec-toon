## ADDED Requirements

### Requirement: Struct wire shape honors msgspec metadata

The encoder SHALL emit the discriminator for a tagged Struct, SHALL use its configured tag-field
name, and SHALL emit an `array_like` Struct as a positional TOON sequence. Arrays of tagged
object-form Structs SHALL retain the discriminator as a tabular column when tabular encoding is
otherwise valid.

#### Scenario: Tagged object round trip

- **WHEN** a tagged Struct is encoded and decoded as its declared tagged union
- **THEN** the discriminator selects the original variant and the decoded value equals the input

#### Scenario: Array-like round trip

- **WHEN** an `array_like` Struct is encoded and decoded as its declared type
- **THEN** the wire value is positional and the decoded value equals the input

### Requirement: Canonical whole floats follow TOON 4.1

The encoder SHALL emit a finite whole float with the canonical integer-looking spelling required
by the pinned TOON 4.1 corpus, and SHALL emit negative zero as `0`. Documentation and generated
support evidence SHALL state that an untyped decode cannot recover the original float category or
the sign of negative zero.

#### Scenario: Whole-float canonicalization is explicit

- **WHEN** `0.0`, `-0.0`, `1.0`, or a large finite whole float is encoded
- **THEN** its bytes match the pinned official fixture rule
- **AND** the published support evidence identifies the untyped result as an integer
