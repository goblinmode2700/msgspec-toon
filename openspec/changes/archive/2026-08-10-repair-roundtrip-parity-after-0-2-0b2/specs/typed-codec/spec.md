## ADDED Requirements

### Requirement: Encoder-native scalar types decode directly

Typed decode SHALL accept datetime, date, time, timedelta, UUID, Decimal, string Enum, and integer
Enum annotations. It SHALL construct those scalar values while consuming parser scalar events and
SHALL NOT build an intermediate dictionary or list tree. Accepted values and timezone constraints
SHALL match msgspec 0.21.1 for the equivalent scalar input.

#### Scenario: Native scalar Struct round trip

- **WHEN** a Struct field of each supported native scalar type is encoded and typed-decoded
- **THEN** the decoded field equals the original value
- **AND** the typed allocation probe records no intermediate built-in container tree

#### Scenario: Invalid native scalar is payload-safe

- **WHEN** a native scalar cannot be converted to its declared annotation
- **THEN** typed decode raises the package validation error with coordinates
- **AND** the error does not contain the rejected scalar text

### Requirement: Supported value shapes carry round-trip evidence

Every executable support-matrix entry that declares a value shape supported SHALL include and run
a value-to-text-to-typed-value probe. The entry SHALL fail if encoding raises, typed decoding
raises, or the decoded value differs from the input.

#### Scenario: Half-feature cannot report supported

- **WHEN** either encode or typed decode is absent for a declared supported value shape
- **THEN** the support-matrix test fails that entry
