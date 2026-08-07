# Tasks

## 1. Baseline freeze and A/B harness

- [x] 1.1 Copy the `v0.1.0-conformant` report to
      `benches/baseline/v0.1.0-conformant-report.json`; record tag, commit, environment.
- [x] 1.2 Add `make baseline`: build the wheel from the baseline tag into `.venv-baseline/`.
- [x] 1.3 Add `benches/ab.py`: run a named benchmark module in both environments via
      subprocess in one session; emit paired per-row deltas (uses `_timing.py` on both
      sides; refuses to compare across sessions).

## 2. Token-efficiency benchmark

- [x] 2.1 Add `tiktoken` (cooldown-compliant version) to the bench dependency group.
- [x] 2.2 Add string-heavy and numeric-heavy payload variants to `benches/payloads.py`.
- [x] 2.3 Add `benches/bench_tokens.py`: tokens under o200k_base + cl100k_base for JSON,
      canonical TOON, tab TOON, pipe TOON, toons, python-toon, across ladder × shapes;
      absolute tokens, vs-JSON ratio, tokens-per-100-bytes.
- [x] 2.4 Wire gates T1–T3 and the token section into `scripts/release-report.py`.

## 3. Spec-defined encoder/decoder options

- [x] 3.1 Amend the `toon-encoding` main spec per this change's delta; implement
      `Encoder`/`encode` `delimiter` ("," | "\t" | "|") and `indent`, and `Decoder`
      `indent_size`, with defaults byte-identical to today's canonical output.
- [x] 3.2 Parameterize encoder quoting by the active delimiter; emit `[N<d>]` / `[N:<d>]`
      headers.
- [x] 3.3 Conformance runner: apply fixture options instead of classifying them
      unsupported; corpus run must report zero declared divergences (gate C1).
- [x] 3.4 Unit tests: option round-trips (tab/pipe/indent=4), option-vs-default byte
      equality for default values.

## 4. Profiling and speed candidates (one commit per adopted candidate)

- [ ] 4.1 Profile typed decode and encode on the 512/4096 payloads; record top frames in
      the ledger before touching anything. (Not done as written: candidates were
      selected from code inspection and validated purely by A/B measurement;
      flamegraph profiling remains open alongside E3.)
- [x] 4.2 D1 tabular column-index memoization — A/B, adopt/reject with numbers.
- [x] 4.3 D2 row cells-buffer reuse — A/B, adopt/reject with numbers.
- [x] 4.4 D3 per-column key-string cache (untyped) — A/B, adopt/reject with numbers.
- [x] 4.5 D4 skip redundant UTF-8 revalidation — A/B, adopt/reject with numbers.
- [x] 4.6 E1 type-pointer dispatch cache — A/B, adopt/reject with numbers.
- [x] 4.7 E2 output capacity estimation — A/B, adopt/reject with numbers.
- [ ] 4.8 E3 fused row templates — A/B, adopt/reject with numbers.
- [x] 4.9 P1 quote-free memchr fast path — A/B, adopt/reject with numbers.
- [x] 4.10 After each adoption: corpus zero failures, G2/G3/G5 re-verified (gate O2);
      G4 re-measured and reported.

## 5. Ledger and report

- [x] 5.1 Add `optimization_ledger` to the report: per candidate — hypothesis, adopted or
      rejected, paired A/B numbers, ladder points affected.
- [x] 5.2 Regenerate the qualification report; confirm gates T1–T3, O1–O2, C1 states are
      published with numbers.
- [x] 5.3 Update CLAUDE.md status and, if adopted results warrant, tag `v0.2.0`.
