## ADDED Requirements

### Requirement: Native encode policy is executable evidence

The support matrix SHALL probe `set`, `frozenset`, and `bytes` separately. A supported type SHALL
include direct encode evidence. A rejected type SHALL include the stable error code and supported
route.

#### Scenario: One type cannot represent the group

- **WHEN** one native family changes support state
- **THEN** its matrix entry changes independently
- **AND** the other two entries retain their observed states

