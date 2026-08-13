## ADDED Requirements

### Requirement: Untyped release evidence covers distinct-key scaling

The release guard SHALL measure ordinary-record untyped decode with distinct-key counts in the tens and hundreds.
Each payload SHALL keep the record count, value data, key width, and encoded byte count fixed.
The generated release report SHALL contain decode cost across the complete distinct-key ladder.

The ordinary key path SHALL use hash lookup.
It SHALL NOT scan cached keys for a match.
The release evidence SHALL state the cache lifetime and bound.

#### Scenario: Decode cost scales with cached-key count

- **WHEN** a covered distinct-key cell is significantly slower than the preceding release
- **THEN** the release guard fails after its normal independent confirmation
- **AND** the release cannot publish an unqualified untyped decode improvement

#### Scenario: Release evidence omits key-cardinality coverage

- **WHEN** the release guard omits either required distinct-key cell
- **THEN** release-report generation fails
