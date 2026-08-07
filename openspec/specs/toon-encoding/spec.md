# toon-encoding

## Purpose

Encode Python values as canonical TOON 4.1 text, byte-exactly matching the official encode
fixtures. The encoder (`src/encode.rs`, `src/shape.rs`, `src/writer.rs`) walks Python values
directly — for `msgspec.Struct` instances it uses a cached `EncodePlan` and direct field
access, never `msgspec.to_builtins` (canvas AD-004). Default output is fully canonical; the
only wire options are the ones TOON 4.1 itself defines and spells in the wire (delimiter,
indentation width — see the wire-configuration requirement). Sources: original spec §2, §5;
canvas §11.

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

Default output SHALL remain fully canonical and knob-free: two encoders constructed with
default options produce byte-identical output, and no option may alter default output.
The ONLY permitted wire options are those TOON 4.1 itself defines and spells in the wire —
`delimiter` (comma default, tab, pipe; declared in the array header as `[N<d>]` /
`[N:<d>]`) and indentation width — so any conforming reader decodes option-bearing output
without out-of-band knowledge. This supersedes the blanket prohibition, whose premise
(option-bearing output as "bytes another reader will not accept") the official conformance
corpus falsifies: the corpus itself exercises these options. Options beyond the
specification's own (number styles, table-preference toggles, key folding, or any
extension the wire cannot declare) remain prohibited. Value-transformation options
mirroring `msgspec.json` (`enc_hook`, `order`, `decimal_format`, `uuid_format`) remain
permitted as before. Quoting SHALL be parameterized by the active delimiter: a cell quotes
when it contains the active delimiter, not a delimiter that is not in effect.

#### Scenario: Two encoders produce identical bytes

- **WHEN** the same value is encoded by two encoder instances constructed with default
  options
- **THEN** the outputs are byte-identical

#### Scenario: An option is spelled in the wire

- **WHEN** a value is encoded with `delimiter="	"`
- **THEN** the output declares the delimiter in its array headers (`[N	]`)
- **AND** this codec's own decoder decodes it with no options supplied

#### Scenario: The option corpus runs clean

- **WHEN** the pinned conformance corpus runs with fixture options applied
- **THEN** the delimiter and indentation fixtures pass and the declared-divergence count
  is zero

#### Scenario: A non-spec knob is still refused

- **WHEN** a caller requests a wire behavior TOON 4.1 does not define as an option
- **THEN** no such parameter exists on the public surface


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
