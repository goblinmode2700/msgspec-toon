## ADDED Requirements

### Requirement: Open-value and scalar-union evidence is separate

The support matrix SHALL include separate entries for `object`, scalar unions, and containers that
hold either annotation. A top-level result SHALL NOT stand in for its nested forms.

#### Scenario: Nested annotation gaps remain visible

- **WHEN** a top-level annotation is supported but its container form is rejected
- **THEN** the report shows separate results for both forms
- **AND** the README states the release boundary

