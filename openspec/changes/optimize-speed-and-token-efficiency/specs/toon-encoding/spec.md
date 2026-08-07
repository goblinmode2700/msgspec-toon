# toon-encoding (delta)

## MODIFIED Requirements

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

- **WHEN** a value is encoded with `delimiter="\t"`
- **THEN** the output declares the delimiter in its array headers (`[N\t]`)
- **AND** this codec's own decoder decodes it with no options supplied

#### Scenario: The option corpus runs clean

- **WHEN** the pinned conformance corpus runs with fixture options applied
- **THEN** the delimiter and indentation fixtures pass and the declared-divergence count
  is zero

#### Scenario: A non-spec knob is still refused

- **WHEN** a caller requests a wire behavior TOON 4.1 does not define as an option
- **THEN** no such parameter exists on the public surface
