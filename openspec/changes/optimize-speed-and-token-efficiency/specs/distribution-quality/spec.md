# distribution-quality (delta)

## ADDED Requirements

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
