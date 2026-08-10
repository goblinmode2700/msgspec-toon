# native-fuzzing Specification

## Purpose
Continuously explores the native parser and codec state space beyond fixed fixtures while
turning every discovered failure into durable regression evidence.
## Requirements
### Requirement: Arbitrary input is contained by the native parser

A native parser fuzz target SHALL accept arbitrary bytes, with a direct path for valid UTF-8.
No input SHALL cause a panic, abort, memory fault, uncontrolled allocation, or unbounded
recursion. Error objects SHALL retain the payload-safe error contract.

#### Scenario: Hostile bytes remain contained

- **WHEN** the parser target receives arbitrary bytes containing a unique sentinel
- **THEN** the process remains alive and bounded
- **AND** any returned error contains no sentinel text

### Requirement: Structured fuzzing checks codec round-trip properties

A structure-aware target SHALL exercise encode, decode, and encode-again paths over supported
values and options. When decode succeeds, encoding the value and decoding the new bytes SHALL
produce an equivalent supported value. Canonical output for an already canonical value SHALL
remain byte-stable.

#### Scenario: Successful decode survives re-encoding

- **WHEN** a generated supported value is encoded, decoded, encoded again, and decoded again
- **THEN** the two decoded values are equivalent
- **AND** canonical bytes are stable after the first canonical encoding

### Requirement: Fuzzing uses durable corpus and CI layers

Fuzz targets SHALL be seeded from the pinned conformance fixtures and permanent containment
regressions. Pull requests SHALL build every target and run a short smoke budget. A scheduled
workflow SHALL run a sustained budget and retain crash inputs and diagnostic artifacts. Every
confirmed defect SHALL become a permanent minimal regression case before the fix is accepted.

#### Scenario: A fuzz failure becomes permanent evidence

- **WHEN** a fuzz run finds a reproducible defect
- **THEN** the failing input is minimized and added to the permanent regression corpus
- **AND** the workflow retains the original failure artifact for diagnosis

#### Scenario: Pull-request fuzzing stays bounded

- **WHEN** a pull request runs CI
- **THEN** all fuzz targets build and execute within the declared smoke-test budget

