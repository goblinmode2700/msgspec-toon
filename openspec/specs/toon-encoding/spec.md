# toon-encoding

## Purpose

Encode Python values as canonical TOON 4.1 text, byte-exactly matching the official encode
fixtures. The encoder (`src/encode.rs`, `src/shape.rs`, `src/writer.rs`) walks Python values
directly — for `msgspec.Struct` instances it uses a cached `EncodePlan` and direct field
access, never `msgspec.to_builtins` (canvas AD-004). The output profile is fixed by the
specification: there are no delimiter, indentation, number-style, or table-preference options
(canvas AD-005). Sources: original spec §2, §5; canvas §11.

## Requirements

### Requirement: Encode conformance is byte-exact against the official fixture corpus

The encoder SHALL reproduce every encode fixture in the pinned TOON 4.1 corpus byte-for-byte,
with zero exceptions and zero declared divergences.

#### Scenario: The encode corpus reproduces exactly

- **WHEN** every encode fixture in the pinned corpus is encoded
- **THEN** each output is byte-identical to the fixture's expected bytes
- **AND** the report states the corpus release or commit it ran against

### Requirement: Nested field groups encode as flat rows

An array of objects whose members share a shape SHALL encode as a tabular array even when a
member field is itself an object, using the 4.0 nested field group construct in the header.
Falling back to indented key–value form for such an array SHALL be treated as a conformance
failure. The shape classifier SHALL derive tabular eligibility from the encode plans and check
it against runtime values: same concrete row type, no empty nested group, and every leaf a
TOON primitive after hook normalization; otherwise the encoder SHALL fall back exactly as the
specification directs.

#### Scenario: One nested field does not collapse the table

- **WHEN** a record array is encoded where every record carries one nested object field
- **THEN** the output opens with a nested field group header such as
  `workers[2]{pid,provider,metadata{alias,region}}:`
- **AND** each record occupies exactly one delimiter-separated row

#### Scenario: A mixed column falls back

- **WHEN** a record array is encoded where one record's nested field is `None` and another's
  is an object
- **THEN** the encoder emits the specification's non-tabular fallback rather than a malformed
  table

### Requirement: Scalar formatting is canonical

Scalar encoding SHALL follow the 4.1 canonical rules: `bool` checked before `int` (Python
booleans are int subclasses); Python `int` written by exact decimal conversion at arbitrary
precision; finite floats written in the canonical range and notation rules with `-0.0` emitted
as `0`; non-finite floats raising `EncodeError`; strings quoted only when the grammar requires
it, using only the 4.1 escape set. Bounded scalar-sized formatting buffers are permitted; a
full copied object tree or document copy is not.

#### Scenario: Large integers encode exactly

- **WHEN** the integer 9007199254740993 is encoded
- **THEN** the output text is the exact decimal digits `9007199254740993`

#### Scenario: Non-finite floats are rejected

- **WHEN** a value containing `float("nan")` or `float("inf")` is encoded
- **THEN** an `EncodeError` is raised

### Requirement: The wire has no configuration surface

The public API SHALL expose no option that alters the wire: no delimiter choice, no indent
width, no number style, no table-preference toggle. Options that mirror `msgspec.json`
(`enc_hook`, `order`, `decimal_format`, `uuid_format`) MAY exist because they govern value
transformation and ordering, not the wire grammar.

#### Scenario: Two encoders produce identical bytes

- **WHEN** the same value is encoded by two encoder instances constructed with default options
- **THEN** the outputs are byte-identical

### Requirement: Round-trips are lossless in both directions

For every value in the supported data model, decoding an encoded value SHALL return an equal
value. For every canonical document, encoding a decoded document SHALL return byte-identical
text.

#### Scenario: Value to text to value

- **WHEN** any corpus value is encoded and then decoded
- **THEN** the result equals the original value

#### Scenario: Text to value to text

- **WHEN** any canonical corpus document is decoded and then encoded
- **THEN** the output is byte-identical to the input
