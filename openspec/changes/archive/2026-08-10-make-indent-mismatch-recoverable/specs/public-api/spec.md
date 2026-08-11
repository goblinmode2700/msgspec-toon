## ADDED Requirements

### Requirement: Producer and consumer indentation widths must agree

The functional `decode` call and reusable `Decoder` SHALL default `indent_size` to two. An
integer from 1 through 16 SHALL force that indentation unit. A producer that selects a nondefault
`indent` SHALL require its consumer to supply the same `indent_size`; documentation SHALL state
this contract beside the token-saving guidance.

#### Scenario: Matching nondefault widths round trip

- **WHEN** `encode(value, indent=n)` emits a nested or tabular document for `n` equal to 1, 2, or 4
- **AND** decode receives `indent_size=n`
- **THEN** decode returns `value`

#### Scenario: Mismatch tells the caller how to recover

- **WHEN** default decode receives a document whose first structural indentation is one space
- **THEN** it raises a decode error reporting one observed space
- **AND** the error tells the caller to pass the matching `indent_size`

## MODIFIED Requirements

### Requirement: Errors carry position and never echo the payload

A decode or validation error SHALL carry the 1-based line and, where available, column at
which decoding failed, plus a stable machine-readable code. It SHALL NOT include the offending
source line, any substring of the payload, or any scalar, key, or cell value derived from payload
content. It MAY render a structural leading-space count derived only from the first-content
column of a failing line. Internal native faults SHALL store coordinates and schema-known path
parts only; user-facing text SHALL otherwise be formatted from static templates. Struct path
components SHALL come from the compiled plan, never from payload keys.

#### Scenario: A sentinel value never reaches the error text

- **WHEN** a document containing a unique sentinel string fails to decode
- **THEN** the sentinel appears nowhere in `str(exc)`, `repr(exc)`, `exc.args`, or any
  exception attribute
- **AND** the message still names the line where decoding failed

#### Scenario: Error classes remain msgspec-compatible

- **WHEN** a caller catches `msgspec.DecodeError`
- **THEN** this package's `DecodeError` is caught, provided the pinned msgspec version
  supports subclassing; otherwise the package documents its `ValueError`-based fallback
