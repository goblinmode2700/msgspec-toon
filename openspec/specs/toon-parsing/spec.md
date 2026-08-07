# toon-parsing

## Purpose

Parse TOON 4.1 text into structural events with byte-exact conformance to the pinned
specification fixture corpus. The parser is the Rust core (`src/scan.rs`, `src/header.rs`,
`src/scalar.rs`, `src/parser.rs`, `src/event.rs`) and knows nothing about Python or msgspec:
it emits borrowed Rust events into a `Consumer` trait shared by the untyped, typed, and
validation consumers (canvas AD-002). Sources: `docs/original-spec/spec.md` §1–§3,
`docs/implementation-spec/toon-native-codec-implementation-canvas.md` §5–§7.

## Requirements

### Requirement: Decode conformance is exact against the official fixture corpus

The parser SHALL produce the declared value for every decode fixture in the pinned TOON 4.1
conformance corpus, and SHALL raise for every strict-error fixture. The corpus SHALL be pinned
to a named release or commit in `conformance/fixtures.lock.json`; the runner SHALL refuse to
execute against an unpinned or mismatched fixture tree.

#### Scenario: Decode fixtures produce declared values

- **WHEN** every decode fixture in the pinned corpus is decoded with `type=Any`
- **THEN** each result equals the fixture's declared value
- **AND** every strict-error fixture raises rather than accepting

#### Scenario: The runner refuses a moving corpus

- **WHEN** the checked-out fixture tree does not match the lock file's commit or tree hash
- **THEN** the conformance runner exits with an error instead of running

### Requirement: The scanner is zero-copy and line-incremental

The scanner SHALL iterate lines of the input buffer by borrowing slices; it SHALL NOT build a
second full copy of the document. It SHALL track 1-based line numbers and 1-based columns,
strip a leading UTF-8 BOM on line one only, strip a trailing `\r`, skip blank and `#` comment
lines, and compute indentation depth from leading spaces.

#### Scenario: Peak memory does not double on a large document

- **WHEN** the largest document on the measurement ladder is decoded under a memory tracer
- **THEN** peak additional memory is materially below the size of a second full copy

#### Scenario: Strict mode rejects malformed indentation

- **WHEN** a line is indented with a tab, or with a space count that is not a multiple of the
  indent size, and `strict=True`
- **THEN** a decode error is raised carrying the line and column of the violation

### Requirement: Headers support tabular arrays and nested field groups

The header parser SHALL parse `key[N]{fields}:` headers, including the specification 4.0
nested field group construct `{a,b{c,d}}`, delimiter selection (comma, tab, pipe), declared
lengths, and keyed tabular forms. Nested field groups are core grammar, not an extension.

#### Scenario: A nested field group header parses to a field tree

- **WHEN** the header `workers[2]{pid,provider,metadata{alias,region}}:` is parsed
- **THEN** the result declares length 2 and a field tree with `metadata` carrying two children

#### Scenario: Strict mode rejects duplicate fields

- **WHEN** a header declares the same field name twice within one group and `strict=True`
- **THEN** a decode error is raised

### Requirement: Rows enforce declared shape in strict mode

In strict mode the parser SHALL verify that each tabular row carries exactly the leaf count
declared by the header's field tree, and that the array holds exactly the declared number of
rows.

#### Scenario: A short row fails

- **WHEN** a table declares three leaf fields and a row supplies two cells
- **THEN** a decode error is raised naming the offending line

#### Scenario: A row-count mismatch fails

- **WHEN** a table declares `[2]` and three rows follow
- **THEN** a decode error is raised

### Requirement: Scalars classify from borrowed bytes and preserve integer precision

Scalar tokens SHALL be classified from borrowed byte slices (`null`, `true`, `false`, integer,
float, bare string, quoted string) without first constructing a Python string. Integer values
SHALL round-trip exactly at Python's precision: the implementation SHALL NOT reject, truncate,
or round an integer because a different language's numeric domain could not represent it, and
SHALL NOT route integers through `f64` except as a fast path guarded by a checked range test.

#### Scenario: A value beyond the double-precision safe range survives

- **WHEN** an integer larger than 2**53 is decoded
- **THEN** the resulting Python `int` equals the source digits exactly
- **AND** no error and no warning is produced

### Requirement: Payload-chosen quantities are bounded

A document chooses two quantities that would otherwise size a machine resource: how deeply it
nests, and how many elements an array header declares. Both SHALL be bounded so that a
document can be rejected, never allowed to exhaust the native stack or the allocator.

Decoding SHALL enforce one nesting ceiling covering line indentation depth and header
field-group depth, and SHALL raise a `depth_limit` decode error when a document exceeds it.
The ceiling SHALL apply in strict and non-strict mode alike: a resource limit is not a grammar
ambiguity, so it SHALL NOT fall through to the non-strict malformed-header tolerance.

A declared array count SHALL NOT size an allocation. The declared count SHALL continue to
govern length validation exactly as before; only the up-front reservation derived from it is
capped.

#### Scenario: A document deeper than the ceiling is rejected

- **WHEN** a document nests field groups or indentation beyond the codec's nesting ceiling
- **AND** it is decoded in either strict or non-strict mode
- **THEN** a decode error with code `depth_limit` is raised carrying line and column
- **AND** the process does not panic, abort, or exit on a signal

#### Scenario: An unsatisfiable declared count allocates nothing

- **WHEN** a header declares an array length near the largest representable count
- **THEN** decoding either raises the ordinary length-mismatch error (strict) or retains the
  rows actually present (non-strict)
- **AND** no allocation is attempted for the declared count

#### Scenario: Arrays larger than the reservation cap still decode

- **WHEN** a document contains an array with more elements than the reservation cap
- **THEN** every element decodes and the result length equals the element count

### Requirement: Parsing runs in the calling process with no I/O

Decoding SHALL happen inside the calling process. It SHALL NOT start a subprocess, open a
socket, bind a port, resolve a hostname, or read a file during a conversion.

#### Scenario: A conversion opens nothing

- **WHEN** a conversion runs under a system-call trace
- **THEN** no process creation, no socket, and no file open appears

### Requirement: Strict decoding is the default

Decoding SHALL reject malformed input by default. `strict=False` SHALL enable only a
documented set of parser tolerances; it SHALL never suppress an error silently.

#### Scenario: Malformed input raises without a flag

- **WHEN** a document violating the specification is decoded with default arguments
- **THEN** a typed decode error is raised
