# Optimize speed and token efficiency

## Why

The `v0.1.0-conformant` tag is the first full measurement: zero fixture failures, G2/G3/G5
pass, G4 an honestly-reported miss, and — per the design of record's own open question #4 —
**every efficiency figure so far is bytes, while TOON's entire claim is tokens**. Nothing has
been measured in tokens against a named tokenizer, and no speed number has ever been improved
*against a frozen baseline*: the POC numbers simply are what the first implementation
happened to produce. This change makes both metrics first-class: precise, hypothesis-driven
optimizations with same-session before/after proof, and a token-efficiency benchmark that
finally measures the variable TOON exists for.

It also resolves the standing AD-005 tension on the evidence rather than by taste. The
25 declared conformance divergences all require the `delimiter`/`indentSize` encoder options
— options **defined by TOON 4.1 itself**, which every conforming reader must accept. The
design of record's "no wire knobs" non-goal was premised on option-bearing output being
"bytes that another reader will not accept"; the official corpus falsifies that premise. And
the tab delimiter is TOON's best-known token saver. Supporting the spec-defined options is
therefore simultaneously a token-efficiency optimization and the closure of every remaining
declared divergence.

## What changes

1. **Freeze the baseline.** Copy the `v0.1.0-conformant` qualification report to
   `benches/baseline/`, and build the baseline wheel from that git tag into a separate
   environment so before/after comparisons run in the same session, same machine, same
   harness — never against remembered numbers.
2. **Token-efficiency benchmark** (`benches/bench_tokens.py`): token counts under a named
   tokenizer (tiktoken `o200k_base` primary, `cl100k_base` secondary) for compact JSON,
   our canonical TOON, tab-delimited TOON, and both incumbents' output, across the payload
   ladder plus string-heavy and numeric-heavy payload variants. Published in the report
   with explicit token gates.
3. **Spec-defined encoder options** (`delimiter`, `indent`): opt-in, spelled exactly as
   TOON 4.1 defines them, canonical defaults unchanged. Closes all 25 declared
   divergences → a genuinely zero-divergence corpus run.
4. **Hypothesis-driven speed optimizations**, each with its own A/B measurement (candidate
   list and hypotheses in `design.md`): tabular column-index memoization and row-buffer
   reuse in typed decode, per-column key-string caching in untyped decode, type-pointer
   dispatch caching and output-capacity estimation in encode, quote-free fast paths in the
   scanner/splitter. Adopt only what measures faster; every adopted candidate is listed in
   the report's optimization ledger with its before/after numbers; rejected candidates are
   listed with their numbers too.
5. **Regression guards**: after every adopted candidate, the full corpus (zero failures),
   the allocation proof (G2), and gates G3/G5 must still hold — an optimization that buys
   speed by breaking conformance or the no-tree invariant is a defect, not a win.

## Impact

- Modified spec: `toon-encoding` (wire-options requirement rewritten on corpus evidence).
- Modified/added spec: `distribution-quality` (token-efficiency requirement, frozen-baseline
  optimization-proof requirement).
- Code: `benches/bench_tokens.py`, `benches/baseline/`, A/B harness, encoder option plumbing
  (`Encoder(delimiter=..., indent=...)` mirroring the corpus option spellings), targeted
  Rust changes per adopted candidate; `tiktoken` added to the bench dependency group
  (cooldown-compliant version).
- Report: new `token_efficiency` section, new `optimization_ledger` section, divergence
  count expected to drop 25 → 0.
