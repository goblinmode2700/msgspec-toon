## MODIFIED Requirements

### Requirement: The scanner is zero-copy and line-incremental

The scanner SHALL iterate lines of the input buffer by borrowing slices; it SHALL NOT build a
second full copy of the document. It SHALL track 1-based line numbers and 1-based columns, strip a
leading UTF-8 BOM on line one only, strip a trailing `\r`, skip blank and `#` comment lines, and
compute indentation depth from leading spaces.

#### Scenario: Peak memory does not double on a large document

- **WHEN** the largest document on the measurement ladder is decoded under a memory tracer
- **THEN** peak additional memory is materially below the size of a second full copy

#### Scenario: Strict mode rejects malformed indentation

- **WHEN** a line is indented with a tab, or with a space count that is not a multiple of the
  configured indent size, and `strict=True`
- **THEN** a decode error is raised carrying the line and first content column
- **AND** a space-indentation error reports the observed leading-space count and names
  `indent_size` as the recovery option
