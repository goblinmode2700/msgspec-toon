## MODIFIED Requirements

### Requirement: Errors carry position and never echo the payload

A decode or validation error SHALL carry a stable machine-readable code and a 1-based line. It
SHALL carry a column when the decoder knows the column.

A typed runtime error SHALL expose a schema-known path when the compiled plan knows that path.
Struct path parts SHALL come from the compiled plan. Array positions SHALL come from structural
indexes. No path part SHALL come from a payload key or value.

The error SHALL NOT include the source line or any payload substring. It SHALL NOT include a
scalar, key, or cell value from the payload. It can show a structural leading-space count that
comes only from the first-content column.

Native faults SHALL store coordinates and schema-known path parts only. User-facing text SHALL
use static templates for all other content.

#### Scenario: A sentinel value never reaches the error text

- **WHEN** a document containing a unique sentinel string fails to decode
- **THEN** the sentinel appears nowhere in `str(exc)`, `repr(exc)`, `exc.args`, or any exception
  attribute
- **AND** the message still names the line where decoding failed

#### Scenario: Typed nested error exposes a schema path

- **WHEN** typed decode rejects a nested tagged field group
- **THEN** the error exposes the schema path to the nested field
- **AND** the path contains no payload-derived key or value

#### Scenario: Error classes remain msgspec-compatible

- **WHEN** a caller catches `msgspec.DecodeError`
- **THEN** the `DecodeError` from this package is caught, provided the pinned msgspec version supports
  subclassing
- **AND** the package documents its `ValueError` fallback when subclassing is unavailable
