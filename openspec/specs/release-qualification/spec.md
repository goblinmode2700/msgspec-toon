# release-qualification Specification

## Purpose
Qualifies the exact Python artifacts offered to users and permits publication only after
source, installed-artifact, identity, and evidence gates all succeed.
## Requirements
### Requirement: One canonical validation gate protects every integration path

The project SHALL define one canonical validation command or reusable workflow. Pull requests,
pushes to the default branch, and release builds SHALL invoke that same definition. The gate
SHALL run Python lint and format checks, static typing, the complete Python suite, Rust format
and lint checks with warnings denied, Rust tests, the complete pinned TOON corpus, hostile-input
containment, and the executable support matrix. Python dependency installation SHALL use the
locked uv environment.

#### Scenario: A pull request and release use the same gate

- **WHEN** the workflow definitions for a pull request and a release are inspected
- **THEN** both depend on the same canonical validation definition
- **AND** neither contains a smaller copied command list

#### Scenario: Any validation failure blocks release work

- **WHEN** one canonical validation check fails
- **THEN** no release artifact can reach the publication job

### Requirement: Built artifacts are verified without source-checkout shadowing

Every wheel SHALL be installed into a clean environment for its target Python ABI, operating
system, and architecture before publication. Every wheel SHALL pass an import and representative
encode/decode test. At least one installed wheel per operating system SHALL run the complete
Python suite and pinned TOON corpus. The source distribution SHALL build a wheel successfully in
a clean uv-managed environment. Verification SHALL prove that imports resolve from the installed
artifact and not from the repository checkout.

#### Scenario: A target wheel is identified and tested

- **WHEN** a wheel verification job completes
- **THEN** its evidence records the wheel filename, Python ABI, operating system, and architecture
- **AND** the imported native module resolves inside the clean installed environment

#### Scenario: The source distribution reproduces a wheel

- **WHEN** the source distribution is installed in a clean uv-managed build environment
- **THEN** it produces an installable wheel and passes the representative codec test

### Requirement: Publication promotes the verified artifact set without rebuilding

Artifact construction, verification, and publication SHALL be distinct jobs. The publication
job SHALL consume exactly the wheel and source-distribution files that verification approved,
SHALL verify their recorded digests, and SHALL NOT rebuild them. Publication SHALL occur only for
an intended version tag or an explicitly authorized manual release event.

#### Scenario: Publication receives only verified files

- **WHEN** the publication job starts
- **THEN** every input file has a matching verification record and digest
- **AND** no build tool runs in the publication job

#### Scenario: Partial matrix failure prevents a partial release

- **WHEN** any build or verification matrix entry fails
- **THEN** no file from that workflow run is uploaded to PyPI

### Requirement: PyPI publication uses short-lived trusted identity

PyPI publication SHALL use GitHub Actions OpenID Connect through a protected GitHub environment
and the official PyPA publishing action. Only the publication job SHALL receive `id-token: write`.
The repository SHALL NOT require a long-lived PyPI API token. Default PyPI publish attestations
SHALL remain enabled for every release file.

#### Scenario: A release carries file attestations

- **WHEN** a version is published to PyPI
- **THEN** every wheel and source distribution has a PyPI publish attestation
- **AND** the workflow used no repository API-token secret

#### Scenario: Non-publication jobs cannot mint the release identity

- **WHEN** the workflow permissions are inspected
- **THEN** only the protected publication job has `id-token: write`

