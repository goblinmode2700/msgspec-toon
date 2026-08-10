## ADDED Requirements

### Requirement: Unsupported annotations fail through a stable typed-plan contract

Every unsupported annotation SHALL fail during plan construction with one documented package
exception, a stable machine-readable code, and a schema-derived path to the failing type.
Recursive annotation discovery SHALL NOT leak `RecursionError`. An unsupported plan SHALL never
reach a decode call site as a partial plan.

#### Scenario: Recursive annotation failure is intentional

- **WHEN** a recursive annotation is not supported by the current release
- **THEN** decoder construction raises the documented package exception
- **AND** neither the exception type nor its cause exposes `RecursionError`

#### Scenario: Unsupported nested type has a stable path

- **WHEN** an unsupported type appears inside a nested Struct field
- **THEN** the error identifies that field through schema-known path components
- **AND** no payload content appears in the error

### Requirement: New typed support extends declarative plan data

Adding a supported annotation SHALL extend the typed plan data or its declared registration.
It SHALL NOT add an annotation-type switch at a decode call site. Tagged Struct unions SHALL use
msgspec tag metadata. `array_like` Structs SHALL decode their documented sequence form. Recursive
plans SHALL use bounded references rather than unbounded plan compilation. Non-string mapping
keys SHALL either decode with an explicit key plan or fail during plan construction.

#### Scenario: Tagged union selects by declared metadata

- **WHEN** a tagged Struct union receives a valid declared tag
- **THEN** the matching Struct variant is constructed directly
- **AND** no intermediate object tree is built

#### Scenario: Array-like Struct uses sequence positions

- **WHEN** an `array_like` Struct receives its documented TOON sequence representation
- **THEN** fields are validated and constructed in declared position order

#### Scenario: Recursive input is bounded

- **WHEN** a supported recursive type receives input deeper than the configured containment limit
- **THEN** decoding fails with the static depth error and leaves the process alive

#### Scenario: Mapping key policy is decided before decoding

- **WHEN** a mapping annotation uses a key plan the release does not support
- **THEN** Decoder construction rejects it with the stable typed-plan exception

## MODIFIED Requirements

### Requirement: Typed support grows by declared tiers

Type support SHALL be implemented and documented in tiers. Tier 0 (challenge-shaped): `None`,
`bool`, `int`, `float`, `str`, `list[T]`, nested Structs, `Optional[T]`, root Struct and root
`list[Struct]`, renamed fields, required/default fields, nested field groups in tabular rows.
Tier 1: tuples, `dict[str, T]`, literals, tagged Struct unions, `forbid_unknown_fields`,
`array_like`, constraints, `UNSET`, recursive Struct plans, and `strict=False` scalar conversion.
Tier 2: enums, datetime family, UUID, Decimal, bytes, named tuples, dataclasses/attrs,
`dec_hook` customs, complex unions, and declared non-string mapping-key plans. A release SHALL
document its executable support matrix and SHALL NOT imply full `msgspec.json` parity before
Tier 2 passes differential tests. Every matrix entry SHALL be supported or intentionally
rejected; no entry may be silently wrong or silently ignored.

#### Scenario: Tier 0 differential-tests against msgspec.json

- **WHEN** equivalent values are decoded through this codec and through `msgspec.json` for
  every Tier 0 type
- **THEN** accepted values match and rejected values raise in both

#### Scenario: Permissive conversion is differentially specified

- **WHEN** a supported Tier 0 scalar is decoded with `strict=False`
- **THEN** acceptance, rejection, and normalized value match `msgspec.json` for an equivalent
  document

#### Scenario: The support matrix has no accidental state

- **WHEN** the executable support matrix runs
- **THEN** every declared feature is observed as supported or intentionally rejected
- **AND** zero entries are silently wrong or silently ignored

