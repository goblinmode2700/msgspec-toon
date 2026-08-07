# public-api

## Purpose

The Python surface of the distribution: a thin package named `msgspec_toon` whose shape
mirrors `msgspec.json` so a caller substitutes one module for the other with no new concepts
(canvas §3). Errors carry coordinates and never echo payload (canvas AD-007, §12). The native
module is `msgspec_toon._native` (PyO3); the Python layer holds only the API veneer, the plan
compiler, and error translation.

## Requirements

### Requirement: The public surface mirrors msgspec's json module

The package SHALL export `encode(obj, *, enc_hook=None, order=None) -> bytes`,
`decode(buf, *, type=Any, strict=True, dec_hook=None)`, reusable `Encoder` and `Decoder`
classes, and `DecodeError`, `ValidationError`, `EncodeError` exception types, with the same
meanings as `msgspec.json`. `decode` SHALL accept `bytes`, `bytearray`, `memoryview`, and
`str` input.

#### Scenario: A caller substitutes one module for the other

- **WHEN** a program written against `msgspec.json` changes its import to
  `import msgspec_toon as codec`
- **THEN** the program runs unchanged except for the wire format it produces

#### Scenario: A reusable Decoder decodes typed documents

- **WHEN** `Decoder(Document).decode(text)` is called
- **THEN** the result is a `Document` instance

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

`enc_hook` SHALL be called for otherwise unsupported values during encode; `dec_hook` SHALL be
called for custom target types during typed decode; `float_hook` MAY be provided to intercept
float parsing. Hook errors SHALL propagate unchanged.

#### Scenario: enc_hook rescues an unsupported value

- **WHEN** a value of an unsupported type is encoded with an `enc_hook` that converts it to a
  supported one
- **THEN** the output encodes the converted value
- **AND** without the hook the same encode raises `EncodeError`
