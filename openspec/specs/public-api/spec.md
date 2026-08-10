# public-api

## Purpose

The Python surface of the distribution: a thin package named `msgspec_toon` whose shape
mirrors `msgspec.json` so a caller substitutes one module for the other with no new concepts
(canvas §3). Errors carry coordinates and never echo payload (canvas AD-007, §12). The native
module is `msgspec_toon._native` (PyO3); the Python layer holds only the API veneer, the plan
compiler, and error translation.
## Requirements
### Requirement: The public surface mirrors msgspec's json module

The package SHALL export `encode`, `decode`, reusable `Encoder` and `Decoder` classes, and
`DecodeError`, `ValidationError`, `EncodeError`, and `TypePlanError` exception types.
`TypePlanError` SHALL subclass `TypeError`; the other exceptions SHALL retain the same meanings as
`msgspec.json` for documented supported behavior. `decode` SHALL accept `bytes`, `bytearray`,
`memoryview`, and `str` input. Functional calls and reusable objects SHALL derive their options
from one declared option model and SHALL provide equivalent behavior for equivalent options.

#### Scenario: A caller substitutes one module for the other

- **WHEN** a program written against documented supported `msgspec.json` behavior changes its
  import to `import msgspec_toon as codec`
- **THEN** the program runs unchanged except for the wire format it produces

#### Scenario: A reusable Decoder decodes typed documents

- **WHEN** `Decoder(Document).decode(text)` is called
- **THEN** the result is a `Document` instance

#### Scenario: Functional and reusable options agree

- **WHEN** a functional call and a reusable codec receive equivalent supported options and input
- **THEN** they produce equivalent output or equivalent documented errors

### Requirement: Errors carry position and never echo the payload

A decode or validation error SHALL carry the 1-based line and, where available, column at
which decoding failed, plus a stable machine-readable code. It SHALL NOT include the offending
source line, any substring of the payload, or any value derived from payload content. Internal
faults SHALL store coordinates and schema-known path parts only; user-facing text SHALL be
formatted from static templates. Struct path components SHALL come from the compiled plan,
never from payload keys.

#### Scenario: A sentinel value never reaches the error text

- **WHEN** a document containing a unique sentinel string fails to decode
- **THEN** the sentinel appears nowhere in `str(exc)`, `repr(exc)`, `exc.args`, or any
  exception attribute
- **AND** the message still names the line where decoding failed

#### Scenario: Error classes remain msgspec-compatible

- **WHEN** a caller catches `msgspec.DecodeError`
- **THEN** this package's `DecodeError` is caught, provided the pinned msgspec version
  supports subclassing; otherwise the package documents its `ValueError`-based fallback

### Requirement: Hooks match msgspec semantics

`enc_hook` SHALL be called only for otherwise unsupported values during encode; `dec_hook` SHALL
be called for supported custom target types during typed decode; `float_hook` SHALL be accepted
by both top-level `decode()` and reusable `Decoder`. Built-in scalar handling SHALL run before a
caller hook. Hook errors SHALL propagate unchanged.

#### Scenario: enc_hook rescues an unsupported value

- **WHEN** a value of an unsupported type is encoded with an `enc_hook` that converts it to a
  supported one
- **THEN** the output encodes the converted value
- **AND** without the hook the same encode raises `EncodeError`

#### Scenario: float_hook works through both entry points

- **WHEN** the same floating-point input and `float_hook` are passed to `decode()` and `Decoder`
- **THEN** both entry points call the hook and return equivalent values

### Requirement: Accepted options are implemented or rejected consistently

`order="sorted"` and `order="deterministic"` SHALL either implement their documented ordering
or raise the same documented exception from functional and reusable entry points.
`decimal_format` and `uuid_format` SHALL be available consistently wherever encoding options are
accepted after native scalar support lands. No public option SHALL be accepted and ignored.
Documentation SHALL mark every option as implemented, deferred, or unsupported.

#### Scenario: No option is inert

- **WHEN** the executable option matrix invokes every accepted option through every applicable
  entry point
- **THEN** each option changes documented behavior or raises its documented exception
- **AND** no option is reported as silently ignored
