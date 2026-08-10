## ADDED Requirements

### Requirement: Msgspec-native scalar values have documented canonical encodings

The encoder SHALL handle the supported msgspec-native scalar set before calling `enc_hook`.
Dates, datetimes, times, and timedeltas SHALL use msgspec 0.21.1's documented ISO 8601
normalization and SHALL be encoded as TOON strings. UUID values SHALL default to the canonical
hyphenated string. Decimal values SHALL default to a string that preserves the Decimal's exact
textual value. Enum values SHALL encode their declared string or integer value through the
corresponding built-in scalar path. Already supported values SHALL retain their existing bytes.

#### Scenario: Native scalars do not require a hook

- **WHEN** a supported date/time, UUID, Decimal, or Enum value is encoded without `enc_hook`
- **THEN** encoding succeeds with its documented canonical TOON scalar representation
- **AND** `enc_hook` is not called

#### Scenario: Decimal precision is preserved by default

- **WHEN** a Decimal with significant trailing zeroes is encoded under the default format
- **THEN** the TOON string preserves its exact decimal text

#### Scenario: Enum values use their declared scalar value

- **WHEN** a string-valued or integer-valued Enum member is encoded
- **THEN** its declared value is encoded through the matching TOON scalar rule

### Requirement: Scalar format options are explicit wire API

`decimal_format` SHALL support the documented `string` and `number` behaviors, and
`uuid_format` SHALL support the documented `canonical` and `hex` behaviors. Unsupported option
values SHALL fail before encoding with a documented package exception. New scalar behavior and
any wire-output change from `0.1.0b2` SHALL be identified in the release notes.

#### Scenario: Decimal number format emits a numeric scalar

- **WHEN** a Decimal is encoded with `decimal_format="number"`
- **THEN** the output is an unquoted TOON number that preserves the Decimal's exact digits

#### Scenario: Unknown format is rejected

- **WHEN** a caller supplies an unsupported Decimal or UUID format
- **THEN** codec construction or the functional call raises the documented package exception
- **AND** no option is accepted and ignored

