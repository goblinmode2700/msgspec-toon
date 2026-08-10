## ADDED Requirements

### Requirement: Supported feature interactions carry round-trip evidence

The executable support matrix SHALL include bounded interaction rows for feature pairs discovered
by compatibility review. Every interaction declared supported SHALL run a value-to-text-to-typed-
value probe and SHALL appear in generated compatibility evidence.

#### Scenario: Tagged and positional interaction cannot hide between rows

- **WHEN** tagged Structs and array-like Structs each have an isolated supported entry
- **THEN** their supported combination has its own round-trip row
- **AND** a one-direction implementation fails the matrix test

#### Scenario: Review cross-product is retained

- **WHEN** release evidence is generated after the 2026-08-10 feature-pair review
- **THEN** all ten reviewed pairs appear as named executable entries
