## ADDED Requirements

### Requirement: Compatibility evidence reports direction and round trip

The generated compatibility report SHALL identify whether each support-matrix entry has a verified
round-trip probe or no applicable round trip. Declared wire-format divergences required by the
pinned corpus SHALL be reported separately from unsupported and silently wrong behavior.

#### Scenario: Generated report exposes round-trip verification

- **WHEN** release evidence is generated
- **THEN** each matrix entry records its round-trip evidence state
- **AND** fixture-required format divergences do not appear as unacknowledged implementation gaps
