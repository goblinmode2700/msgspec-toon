# typed-codec

## Purpose

The decisive capability: decode TOON text directly into a typed `msgspec.Struct` without
materializing an intermediate tree of Python built-ins, and encode a Struct without a
`to_builtins` copy step. This is Route B from the design of record, taken through the public
Struct constructor rather than private slot offsets (canvas AD-001): a cached type plan is
compiled from `msgspec.inspect` metadata in one Python adapter module (`python/msgspec_toon/_plan.py`,
canvas AD-003), lowered to a Rust `CompiledPlan`, and consumed by a `TypedConsumer` that
builds final scalar values and final collection objects only. Sources: original spec §3–§4,
requirements "Typed decoding builds no intermediate tree", canvas §8–§10, §14.
## Requirements
### Requirement: Typed decoding builds no intermediate tree

Decoding TOON text to a `msgspec.Struct` SHALL construct the target type directly. The
implementation SHALL NOT materialize a complete tree of Python built-in objects and then
convert it. A per-Struct constructor argument frame (one optional final value per declared
field) is permitted; a mapping from wire keys to values is not. This SHALL be demonstrated by
measurement in the same run, not asserted.

#### Scenario: The typed path costs less than the wrapper path

- **WHEN** one document is decoded twice — once through the typed decoder, and once through
  the wrapper shape of decoding to built-ins and calling `msgspec.convert`
- **THEN** the typed decoder is measurably faster
- **AND** the report publishes both figures side by side

#### Scenario: Allocation counts show the tree is absent

- **WHEN** a typed decode of a record array is traced for object allocations
- **THEN** the intermediate `dict` and `list` objects a wrapper would build do not appear
- **AND** the instrumented consumer reports zero intermediate dicts and zero intermediate
  lists for the challenge-shaped payload

### Requirement: Typed encoding reads the Struct directly

Encoding a `msgspec.Struct` SHALL read the instance's fields directly through a cached encode
plan. The implementation SHALL NOT call `msgspec.to_builtins` or an equivalent full-copy step.

#### Scenario: Encoding beats the preparation step it replaces

- **WHEN** one Struct is encoded through the implementation, and `msgspec.to_builtins` is
  timed alone on the same Struct in the same run
- **THEN** the whole encode costs less than the wrapper's preparation step alone

### Requirement: Type plans are compiled once through a single adapter

Type metadata SHALL be read only through the plan-compiler module, which normalizes
`msgspec.inspect` output into an immutable `PlanSpec` IR and passes it to Rust. No parser,
consumer, or encoder code SHALL import `msgspec.inspect`. Plan compilation SHALL be cached per
annotation.

#### Scenario: A Decoder pays plan compilation once

- **WHEN** a `Decoder(Document)` is constructed and used for many decodes
- **THEN** plan compilation runs at construction time only

#### Scenario: Inspection changes are contained

- **WHEN** a future msgspec release renames an inspection attribute
- **THEN** only the plan-compiler module requires change

### Requirement: Tabular rows decode directly into Struct fields

For a tabular array with a (possibly nested) field group header decoded to `list[SomeStruct]`,
each row cell SHALL be converted to its final typed value and placed into the owning Struct's
constructor frame; nested groups SHALL construct the nested Struct first and place it into the
parent frame. Field matching SHALL use the msgspec wire name (`rename` respected), unknown
fields SHALL be skipped without materialization when the target permits them, duplicate keys
SHALL fail in strict mode, missing required fields SHALL fail at the closing boundary, and
defaults or default factories SHALL be realized only for absent fields.

#### Scenario: The challenge-shaped document decodes with no row dicts

- **WHEN** `workers[2]{pid,provider,metadata{alias,region}}:` with two rows is decoded to a
  `Document` holding `list[Worker]` where `Worker.metadata` is a nested `Metadata` Struct
- **THEN** the result is a `Document` whose Workers and Metadatas are fully constructed
- **AND** no per-row `dict` and no per-metadata `dict` is allocated

#### Scenario: A missing required field fails with coordinates

- **WHEN** a decoded object omits a required Struct field
- **THEN** a validation error is raised naming the line of the enclosing value

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
