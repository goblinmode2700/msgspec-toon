## ADDED Requirements

### Requirement: Tagged array-like Structs consume a positional discriminator

Typed decode SHALL treat the first element of a tagged `array_like` Struct as its declared
discriminator. For a concrete Struct, the value SHALL be validated before field construction. For
a union whose members are all tagged and array-like, the value SHALL select the compiled member
plan before field construction. Neither path SHALL build an intermediate dictionary or list tree.

#### Scenario: Concrete tagged positional round trip

- **WHEN** a tagged array-like Struct is encoded and decoded as its concrete type
- **THEN** its discriminator is validated and its declared fields retain positional order
- **AND** the decoded Struct equals the input

#### Scenario: Tagged positional union selects a member

- **WHEN** a union of tagged array-like Structs receives a declared discriminator at position zero
- **THEN** the matching Struct is constructed directly
- **AND** the decoded Struct equals the input

#### Scenario: Invalid positional discriminator is a public validation error

- **WHEN** the discriminator is missing, unknown, the wrong scalar category, or followed by too
  many positional values
- **THEN** decode raises the package validation error with coordinates
- **AND** neither the error nor its cause contains `internal error` or payload text
