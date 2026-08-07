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

### Requirement: Token efficiency is measured against a named tokenizer

The report SHALL publish token counts — the unit TOON's value proposition is stated in —
for every measured wire format at every payload-ladder point, under a named tokenizer
whose name and version appear in the report (primary: tiktoken `o200k_base`; secondary:
`cl100k_base`). Measured formats SHALL include at least: compact JSON, this codec's
canonical output, this codec's tab- and pipe-delimited output, and each installable
incumbent codec's output. The payload set SHALL include the uniform-record ladder plus a
string-heavy and a numeric-heavy variant, so shape-dependence is visible rather than
averaged away. For each point the report SHALL state absolute tokens, the ratio against
compact JSON, and tokens-per-100-bytes.

#### Scenario: Canonical TOON beats JSON in tokens on record payloads

- **WHEN** the uniform-record ladder is tokenized under the primary tokenizer in one run
- **THEN** canonical TOON output costs no more tokens than compact JSON at every point
- **AND** both counts appear in the report with the tokenizer name and version

#### Scenario: The tab delimiter is a measured saving, not folklore

- **WHEN** the same payloads are encoded with the comma and tab delimiters and tokenized
  in one run
- **THEN** the tab-delimited output costs no more tokens than the comma output at every
  ladder point, or the losing points are published as-is

#### Scenario: A losing shape is published

- **WHEN** any measured format loses to JSON in tokens on any payload variant
- **THEN** the report contains that row unchanged — no payload selection hides it

### Requirement: Optimizations are proven against a frozen baseline

Performance-improvement claims SHALL be proven by same-session A/B measurement against a
frozen baseline build (the `v0.1.0-conformant` tag), both sides running the same harness
on the same machine in one session — never by comparison to remembered or previously
published numbers. Every adopted optimization SHALL appear in the report's optimization
ledger with its hypothesis and paired before/after figures; every rejected candidate
SHALL appear with the numbers that rejected it. After each adopted optimization, the
full fixture corpus SHALL report zero failures, the allocation proof SHALL still show
zero intermediates, and gates G3 and G5 SHALL still pass — a speed win that regresses
correctness or the no-tree invariant is a defect.

#### Scenario: An improvement claim carries its paired measurement

- **WHEN** the report claims an optimization improved a metric
- **THEN** the optimization ledger holds a same-session baseline-vs-current pair for
  that metric produced by the A/B harness

#### Scenario: A regression cannot be traded for speed

- **WHEN** a candidate optimization improves a benchmark but causes any fixture failure,
  intermediate allocation, or G3/G5 gate failure
- **THEN** the candidate is rejected and recorded as such in the ledger
