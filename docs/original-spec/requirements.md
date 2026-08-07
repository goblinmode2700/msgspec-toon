---
usf: 1
type: requirements
id: toon-native-codec
title: toon-native-codec — acceptance requirements
status: proposed
---
# toon-native-codec — requirements

The checkable half of `spec.md`. Requirement names are the stable identity. Each opens with an
italic *State:* line; every requirement below is open, because no implementation exists.

Two requirements decide the challenge: **Conformance is byte-exact against the official fixture
corpus** and **Typed decoding builds no intermediate tree**. The rest are floors. A claimant who
clears the floors but not the two decisive requirements has built a good TOON library, which is
worth having and is not a solution to this problem.

Every threshold below is either an absolute correctness statement or a comparison against a
figure measured in the same run. No threshold is a chosen constant.

## ADDED Requirements

### Requirement: Conformance is byte-exact against the official fixture corpus
*State: open. One of the two decisive requirements.*

The implementation SHALL reproduce the official TOON 4.1 conformance fixtures byte-for-byte on
encode, and SHALL produce the fixtures' declared values on decode, with zero exceptions and zero
declared divergences. The fixture corpus SHALL be pinned to a named specification release or
commit, never tracked from a moving branch.

#### Scenario: The encode corpus reproduces exactly
- **WHEN** every encode fixture in the pinned corpus is encoded
- **THEN** each output is byte-identical to the fixture's expected bytes
- **AND** the report states the corpus release or commit it ran against

#### Scenario: The decode corpus produces the declared values
- **WHEN** every decode fixture in the pinned corpus is decoded
- **THEN** each result equals the fixture's declared value
- **AND** every strict-error fixture raises rather than accepting

### Requirement: Typed decoding builds no intermediate tree
*State: open. The second decisive requirement, and the open research problem.*

Decoding TOON text to a `msgspec.Struct` SHALL construct the target type directly. The
implementation SHALL NOT materialize a complete tree of Python built-in objects and then convert
it. This SHALL be demonstrated by measurement in the same run, not asserted.

#### Scenario: The typed path costs less than the wrapper path
- **WHEN** one document is decoded twice — once through the implementation's typed decoder, and
  once through the wrapper shape of decoding to built-ins and calling `msgspec.convert`
- **THEN** the typed decoder is measurably faster
- **AND** the report publishes both figures side by side

#### Scenario: Allocation counts show the tree is absent
- **WHEN** a typed decode of a record array is traced for object allocations
- **THEN** the intermediate `dict` and `list` objects a wrapper would build do not appear

### Requirement: Typed encoding reads the Struct directly
*State: open.*

Encoding a `msgspec.Struct` to TOON SHALL read the instance directly. The implementation SHALL
NOT call `msgspec.to_builtins` or an equivalent full-copy step before encoding.

#### Scenario: Encoding beats the preparation step it replaces
- **WHEN** one Struct is encoded through the implementation, and `msgspec.to_builtins` is timed
  alone on the same Struct in the same run
- **THEN** the whole encode costs less than the wrapper's preparation step alone

### Requirement: Nested field groups encode as flat rows
*State: open.*

An array of objects whose members share a shape SHALL encode as a tabular array even when a
member field is itself an object, using the specification 4.0 nested field group construct in
the header. Falling back to indented key and value form for such an array SHALL be treated as a
conformance failure, not a degradation.

#### Scenario: One nested field does not collapse the table
- **WHEN** a record array is encoded where every record carries one nested object field
- **THEN** the output opens with a nested field group header
- **AND** each record occupies exactly one delimiter-separated row

### Requirement: Integers round-trip at Python's precision
*State: open. A deliberate hardening over the prior design.*

Integer values SHALL round-trip exactly at Python's precision. The implementation SHALL NOT
reject, truncate, or round an integer because a different language's numeric domain could not
represent it.

#### Scenario: A value beyond the double-precision safe range survives
- **WHEN** an integer larger than 2 to the power 53 is encoded and decoded
- **THEN** the decoded value equals the original exactly
- **AND** no error and no warning is produced

### Requirement: The round trip is lossless in both directions
*State: open.*

For every value in the supported data model, decoding an encoded value SHALL return an equal
value. For every canonical document, encoding a decoded document SHALL return byte-identical
text.

#### Scenario: Value to text to value
- **WHEN** any corpus value is encoded and then decoded
- **THEN** the result equals the original value

#### Scenario: Text to value to text
- **WHEN** any canonical corpus document is decoded and then encoded
- **THEN** the output is byte-identical to the input

### Requirement: The public surface mirrors msgspec's json module
*State: open.*

The public API SHALL mirror `msgspec.json` in name and shape: an `encode` function, a `decode`
function taking a `type` argument, reusable `Encoder` and `Decoder` classes, and `enc_hook` and
`dec_hook` parameters with the same meanings. A reader who knows `msgspec.json` SHALL need no
new concepts to use it.

#### Scenario: A caller substitutes one module for the other
- **WHEN** a program written against `msgspec.json` has its import changed to this module
- **THEN** the program runs unchanged except for the wire format it produces

### Requirement: Strict decoding is the default
*State: open.*

Decoding SHALL reject malformed input by default. Any tolerance for non-conforming input SHALL
be opt-in per call, never the default, and never silent.

#### Scenario: Malformed input raises without a flag
- **WHEN** a document violating the specification is decoded with default arguments
- **THEN** a typed decode error is raised

### Requirement: Errors carry position and never echo the payload
*State: open.*

A decode error SHALL carry the line and, where available, the column at which decoding failed.
It SHALL NOT include the offending source line, any substring of the payload, or any value
derived from payload content.

#### Scenario: A sentinel value never reaches the error text
- **WHEN** a document containing a unique sentinel string fails to decode
- **THEN** the sentinel appears nowhere in the exception message or its attributes
- **AND** the message still names the line where decoding failed

### Requirement: The codec runs in the calling process
*State: open.*

Encoding and decoding SHALL happen inside the calling process. The implementation SHALL NOT
start a subprocess, open a socket, bind a port, resolve a hostname, or read a file during a
conversion.

#### Scenario: A conversion opens nothing
- **WHEN** a conversion runs under a system-call trace
- **THEN** no process creation, no socket, and no file open appears

### Requirement: Decoding streams rather than copying the document
*State: open.*

Decoding SHALL NOT build a full copy of the input before parsing it. Peak additional memory
during a decode SHALL scale with the depth and row width of the document, not with a second
copy of its length.

#### Scenario: Peak memory does not double on a large document
- **WHEN** the largest document on the measurement ladder is decoded under a memory tracer
- **THEN** peak additional memory is materially below the size of a second full copy

### Requirement: Speed floors, measured against the named baselines
*State: open.*

The implementation SHALL be no slower than the fastest existing compiled TOON codec on the same
payload ladder, in both directions, measured in the same run on the same machine. The claimant
SHALL publish the comparison rather than cite this document's figures.

#### Scenario: The comparison runs in one session
- **WHEN** the implementation and the named existing codecs are benchmarked back to back
- **THEN** the implementation is faster or equal at every size in both directions
- **AND** the report names every version it measured against

### Requirement: Wheels install without a toolchain
*State: open.*

The distribution SHALL publish stable-ABI wheels so that installation requires no compiler, no
Rust toolchain, and no network access beyond the package index. The platform set SHALL be the
one the standard Python wheel-building tooling covers by default: macOS on arm64 and x86_64,
Linux on x86_64 and aarch64, and Windows on x86_64.

#### Scenario: A clean machine installs and imports
- **WHEN** the wheel is installed on a machine with no compiler present
- **THEN** the module imports and converts a document successfully

### Requirement: The runtime dependency tree is empty
*State: open.*

The distribution SHALL declare no runtime dependency other than msgspec. Build-time
dependencies are unconstrained.

#### Scenario: The installed tree holds two names
- **WHEN** the distribution is installed into an empty environment
- **THEN** the environment contains the distribution and msgspec, and nothing else

### Requirement: The conformance report is published with the release
*State: open.*

Every release SHALL publish a machine-readable report stating the specification version and
fixture corpus commit it was measured against, the pass and fail counts for encode, decode, and
strict-error fixtures, every known divergence, and the speed comparison. A release without the
report SHALL be treated as unqualified.

#### Scenario: A reader can check the claim without running anything
- **WHEN** the published report is read
- **THEN** it names the corpus commit, the counts, and the divergences
- **AND** any divergence is stated rather than omitted
