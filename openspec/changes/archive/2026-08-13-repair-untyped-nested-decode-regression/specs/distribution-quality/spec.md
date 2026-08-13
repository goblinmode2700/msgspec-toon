## ADDED Requirements

### Requirement: Untyped release evidence is shape-specific

The release guard SHALL measure untyped decode for uniform tabular records,
ordinary nested mixed records, and irregular entry-form objects. The generated
evidence SHALL preserve each result separately. A release note SHALL NOT state
an unqualified untyped decode range derived from only one shape.

#### Scenario: An untyped shape becomes slower

- **WHEN** any covered untyped decode shape is significantly slower than the preceding release
- **THEN** the release guard fails after its normal independent confirmation
- **AND** the release note identifies the shape and measured direction if the regression is accepted
