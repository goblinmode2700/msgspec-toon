## ADDED Requirements

### Requirement: Native encode refusals name a supported route

An intentional refusal for `set`, `frozenset`, or `bytes` SHALL use a static error code and
message. The message SHALL name a supported projection type or API. It SHALL NOT contain the
rejected value.

#### Scenario: Refusal guidance is payload-safe

- **WHEN** the encoder refuses one of the declared native value families
- **THEN** the error names the supported route
- **AND** no element or byte content appears in any error attribute

