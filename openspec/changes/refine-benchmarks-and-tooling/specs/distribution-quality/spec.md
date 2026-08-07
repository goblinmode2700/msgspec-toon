# distribution-quality (delta)

## MODIFIED Requirements

### Requirement: The runtime dependency tree is empty beyond msgspec

The distribution SHALL declare exactly `msgspec==0.21.1` as its only runtime dependency.
The exact pin is deliberate: the plan compiler reads the experimental `msgspec.inspect`
API, and the POC's qualification statement names one msgspec version. Loosening to a
range SHALL be its own change, landed together with CI coverage against the newer
releases it admits. Rust crates are compiled into the extension and appear nowhere in
Python metadata. Build-time dependencies are unconstrained.

#### Scenario: The installed tree holds two names

- **WHEN** the distribution is installed into an empty environment
- **THEN** the environment contains the distribution and msgspec 0.21.1, and nothing else

#### Scenario: A different msgspec version does not resolve

- **WHEN** dependency resolution runs with msgspec pinned elsewhere to another version
- **THEN** resolution fails rather than silently pairing the codec with an unqualified
  msgspec

### Requirement: Speed floors are measured against the named baselines

The implementation SHALL be benchmarked same-run, same-machine, on installed release
artifacts, against the incumbents a caller would actually use today, at every size on
the payload ladder (16, 64, 512, 4096 challenge-shaped records), in both directions:

- **`python-toon==0.1.3`** raw codec rows (the pure-Python library the design of record
  measured);
- **the latest `python-toon` release** raw codec rows, with the installed version
  recorded at run time (one row suffices if latest equals 0.1.3, and the report says so);
- **the `toons` Rust codec**, when installable, as the G5 codec-floor comparison;
- **the incumbent pipeline shape**: encode as `python_toon.encode(normalize(obj))`
  where `normalize` is a `msgspec.to_builtins` conversion, and decode as
  `msgspec.convert(python_toon.decode(buf), type)`. This row is a benchmark to beat,
  not the definition of the wrapper: the report SHALL note it is a known-inefficient
  composition rather than presenting it as the strongest alternative;
- **`msgspec.json` native** rows as context;
- **`msgspec.to_builtins` alone** as the standing G4 comparison.

Benchmark gates remain: G3 — direct typed decode beats untyped decode plus
`msgspec.convert`; G4 — whole direct typed encode beats `msgspec.to_builtins` alone;
G5 — no slower than the fastest named compiled codec at every size in both directions;
G6 — the `abi3` wheel itself clears the gates. Each report row SHALL name the exact
version measured, and per-codec output byte sizes SHALL be recorded so token-efficiency
differences between spec versions stay visible. A gate miss SHALL be reported, never
masked by payload selection. Baseline codecs that predate TOON 4.x SHALL NOT be treated
as sources of conformant reference bytes.

#### Scenario: The comparison runs in one session

- **WHEN** the implementation and the named incumbent codecs are benchmarked back to back
- **THEN** the report contains rows for every installable named baseline at every ladder
  size in both directions
- **AND** every row names the exact version it measured

#### Scenario: The incumbent pipeline is beaten and labeled

- **WHEN** the typed benchmark runs
- **THEN** the incumbent pipeline rows (`encode(to_builtins(...))`,
  `convert(decode(...))`) appear beside the direct typed rows
- **AND** the report labels the pipeline as a known-inefficient composition

#### Scenario: An uninstallable baseline is reported, not omitted silently

- **WHEN** a named baseline cannot be installed in the benchmark environment
- **THEN** the report states which baseline was absent and why

## ADDED Requirements

### Requirement: Dependencies observe a 14-day cooldown

No resolved dependency version, direct or transitive, SHALL be younger than 14 days at
resolution time, in either ecosystem. Python SHALL enforce this natively with
`tool.uv.exclude-newer = "14 days"` — a relative duration, never a hardcoded date.
Rust, where Cargo has no equivalent, SHALL enforce it by pinning any in-window version
(with the reason and lift condition in a comment) and by the lockfile age audit
(`scripts/check-package-ages.py`, run as `make audit`), which SHALL fail on any locked
version younger than the window. Overrides for critical fixes SHALL be explicit and
attributed: `tool.uv.exclude-newer-package` on the Python side, an explicit newer pin
on the Rust side, with the justification in the commit that introduces it.

#### Scenario: A zero-day-old package cannot enter the tree

- **WHEN** dependency resolution runs and a candidate version was uploaded within the
  last 14 days
- **THEN** an older compliant version is selected, or resolution fails — the young
  version is never locked silently

#### Scenario: The audit fails loudly on a young locked version

- **WHEN** `make audit` runs against a lockfile containing a version younger than 14
  days that has no declared override
- **THEN** the audit exits non-zero naming the ecosystem, package, version, and
  release date

#### Scenario: An override is visible, not silent

- **WHEN** a package is admitted inside the window via an override
- **THEN** the audit reports it as an override rather than passing it silently
- **AND** the override's justification is recorded in the commit that added it

### Requirement: Benchmark timing is standardized

All benchmark scripts SHALL time through one shared utility (`benches/_timing.py`)
implementing autoranged batches with minimum-of-repeats, returning both the per-call
time and the methodology parameters used. No benchmark script SHALL hand-roll its own
timing loop. The report SHALL state the methodology once, sourced from the utility.

#### Scenario: One timing implementation

- **WHEN** the benchmark scripts are inspected
- **THEN** every timed measurement routes through the shared utility
- **AND** no script contains a private timing loop
