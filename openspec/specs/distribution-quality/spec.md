# distribution-quality

## Purpose

Packaging, performance floors, and evidence. The distribution is a maturin-built
`abi3-py313` wheel (canvas AD-008) named `msgspec-toon`, runtime-depending on msgspec alone.
Every release claim is a generated report, never an assertion: conformance counts, allocation
proof, and same-run benchmark comparisons (canvas §15–§18; requirements "Speed floors",
"Wheels install without a toolchain", "The runtime dependency tree is empty", "The
conformance report is published with the release").

## Requirements

### Requirement: Speed floors are measured against the named baselines

The implementation SHALL be no slower than the fastest existing compiled TOON codec on the
same payload ladder (1 KiB, 10 KiB, 100 KiB, 1 MiB record arrays), in both directions,
measured in the same run on the same machine against installed release artifacts. Benchmark
gates: G3 — direct typed decode beats untyped decode plus `msgspec.convert`; G4 — whole
direct typed encode beats `msgspec.to_builtins` alone; G5 — no slower than the fastest named
compiled codec at every size in both directions; G6 — the `abi3` wheel itself, not a full-ABI
development build, clears G3–G5. A gate miss SHALL be reported, never masked by payload
selection.

#### Scenario: The comparison runs in one session

- **WHEN** the implementation and the named existing codecs are benchmarked back to back
- **THEN** the implementation is faster or equal at every size in both directions
- **AND** the report names every version it measured against

### Requirement: Wheels install without a toolchain

The distribution SHALL publish stable-ABI (`abi3-py313`) wheels so installation requires no
compiler, no Rust toolchain, and no network beyond the package index, for macOS arm64/x86_64,
Linux x86_64/aarch64, and Windows x86_64.

#### Scenario: A clean machine installs and imports

- **WHEN** the wheel is installed on a machine with no compiler present
- **THEN** the module imports and converts a document successfully

### Requirement: The runtime dependency tree is empty beyond msgspec

The distribution SHALL declare no runtime dependency other than `msgspec>=0.21.1`. Rust crates
are compiled into the extension and appear nowhere in Python metadata. Build-time dependencies
are unconstrained.

#### Scenario: The installed tree holds two names

- **WHEN** the distribution is installed into an empty environment
- **THEN** the environment contains the distribution and msgspec, and nothing else

### Requirement: The conformance report is published with the release

Every release SHALL publish a machine-readable report stating the specification version and
fixture corpus commit it was measured against, the pass and fail counts for encode, decode,
and strict-error fixtures, every known divergence, the allocation proof, and the speed
comparison. A release without the report SHALL be treated as unqualified.

#### Scenario: A reader can check the claim without running anything

- **WHEN** the published report is read
- **THEN** it names the corpus commit, the counts, and the divergences
- **AND** any divergence is stated rather than omitted

### Requirement: Reference outputs never override fixtures

Differential testing against the reference TypeScript implementation MAY generate additional
cases, but the official fixture corpus SHALL remain authoritative. A mismatch between the
reference implementation and a fixture SHALL be investigated and reported, not normalized
away. Cross-language numeric cases SHALL include integers outside JavaScript's exact domain.

#### Scenario: A reference divergence is reported

- **WHEN** the reference implementation and a pinned fixture disagree
- **THEN** the report records the divergence with both outputs
