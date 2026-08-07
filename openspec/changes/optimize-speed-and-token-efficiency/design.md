# Design notes

## Frozen baseline (what "improve past the first run" means)

Baseline identity: git tag `v0.1.0-conformant`, its `conformance/report.json` copied to
`benches/baseline/v0.1.0-conformant-report.json`. Baseline figures at freeze time (Apple
silicon, Python 3.13.1, msgspec 0.21.1, abi3 release wheel; microseconds, min-of-batches):

| records | typed decode | typed encode | to_builtins | untyped encode | untyped decode |
|--------:|-------------:|-------------:|------------:|---------------:|---------------:|
| 16      | 5.96         | 2.44         | 1.05        | 4.88           | 4.93           |
| 64      | 22.58        | 8.31         | 4.38        | 16.99          | 18.45          |
| 512     | 170.08       | 64.66        | 43.54       | 132.75         | 154.09         |
| 4096    | 1458.87      | 515.44       | 439.82      | 1006.19        | 1380.41        |

These numbers are identity, not proof: every claim of improvement re-runs BOTH sides in one
session via the A/B harness. Mechanism: `make baseline` builds the wheel from the baseline
tag into `.venv-baseline/` (uv-managed, same Python), and `benches/ab.py` runs the same
benchmark module in both environments via subprocess in one session, emitting a paired
comparison with per-row deltas. Two same-module wheels cannot be imported into one process;
subprocess-per-side inside one session is the honest workaround.

## Token-efficiency benchmark

- Tokenizer: `tiktoken` — `o200k_base` (primary, named in every report row) and
  `cl100k_base` (secondary). The tokenizer version is recorded; token counts are meaningless
  without it.
- Formats measured per payload: compact JSON (`msgspec.json`), canonical TOON (ours, comma),
  tab-delimited TOON (ours, once the option lands), pipe-delimited TOON, `toons` output,
  `python-toon` output.
- Payloads: the challenge ladder (16/64/512/4096 records) plus two shape variants, because
  token ratios are shape-dependent and a single flattering payload would be gate-gaming:
  - string-heavy (long prose-like field values),
  - numeric-heavy (many numeric columns, short strings).
- Published metrics: absolute tokens, tokens-vs-JSON ratio, tokens-per-100-bytes (to expose
  tokenizer/byte divergence), for every format at every point.

Expected (to be verified, not assumed): canonical tabular TOON beats compact JSON on
uniform-record payloads; tab delimiter beats comma because `\t` merges into preceding-token
boundaries less often than `,` in BPE vocabularies; the incumbents' fallback form loses to
JSON — which is the design of record's §2 story, finally in the right unit.

## Spec-defined encoder options

`Encoder(...)`/`encode(...)` gain `delimiter: str = ","` (accepting `","`, `"\t"`, `"|"` —
the exact option domain of the corpus) and `indent: int = 2`. Wire spelling follows the
grammar the decoder already parses: `[N<d>]` / `[N:<d>]` headers, cells joined by the active
delimiter, quoting rules parameterized by the active delimiter (a cell containing the active
delimiter quotes; a comma under tab delimiter does not). Defaults produce byte-identical
canonical output — the option is additive, and AD-005's spirit survives as: *no knob may
alter default output, and every accepted knob value must be spelled in the wire itself so
any conforming reader decodes it*.

This closes all 25 unsupported-option fixtures (22 encode delimiter, 1 encode indentSize,
2 decode indentSize — decode gains `indent_size` on `Decoder` for the same reason).

## Speed-optimization candidates

Rules of engagement: profile first (`py-spy` for the Python boundary, `cargo flamegraph`
or counter instrumentation for Rust), one candidate per commit, A/B same-session, adopt
only measured wins, corpus + G2 + gates re-verified per adoption. Candidates, each with its
falsifiable hypothesis:

| id | target | change | hypothesis |
|----|--------|--------|------------|
| D1 | typed decode | Memoize wire-key→field-index resolution per tabular array: rows repeat one key sequence, so resolve the header's field tree to plan indices once and replay per row instead of hashing every key event | Largest typed-decode win; hash lookups are per-cell today |
| D2 | typed+untyped decode | Reuse one cells buffer (`SmallVec`) across rows instead of a fresh `Vec` per row | Removes one allocation per row |
| D3 | untyped decode | Cache per-column key `PyString`s per array (one interned string per column, not one fresh string per cell row) | Untyped decode allocates O(rows×cols) key strings today; drops to O(cols) |
| D4 | decode scalars | Skip redundant UTF-8 revalidation on borrowed scalar slices (document validated once) | Small constant win per string cell |
| E1 | encode | Type-pointer dispatch cache in `write_scalar_obj`/`classify`: compare `ob_type` against cached `int`/`str`/`float`/`bool`/`NoneType` pointers before the `is_instance_of` chain | Cuts 3–5 C calls per cell to one pointer compare |
| E2 | encode | Estimate output capacity from row count × sampled row width before writing | Removes buffer regrowth copies on large documents |
| E3 | encode | Fuse per-row indent+delimiter writes into precomputed byte templates per shape | Fewer writer calls per row |
| P1 | parser | Quote-free fast path: `memchr` the delimiter when the row contains no `"` (checked once per row) | Most rows are quote-free; byte-at-a-time scanning is the current cost |
| G4x | encode (stretch) | All of E1–E3 together against `to_builtins` | G4 gap at 4096 was ~10% pre-conformance-features; E1–E3 may close it at large sizes. No promise — measured outcome either way |

Explicitly out of scope: anything touching msgspec private ABI, `msgspec.structs.astuple`
batching (a shallow per-row copy step — against the spirit of the no-copy requirement;
revisit only with an explicit ruling), and unsafe borrows that outlive the GIL scope.

## Gates

- **T1**: canonical TOON ≤ compact JSON tokens on every uniform-record ladder point
  (o200k_base), same run.
- **T2**: tab-delimited TOON ≤ canonical comma TOON tokens on every ladder point, same run.
- **T3**: report publishes tokens for every format × payload with tokenizer name+version;
  a losing point is published, not dropped.
- **O1**: every adopted optimization shows a same-session A/B improvement on its target
  metric at one or more ladder points, with the paired numbers in the optimization ledger.
- **O2**: after each adoption: corpus zero failures, G2 zero intermediates, G3/G5 still
  pass. G4 is re-measured and reported; it is a hoped-for outcome, not a gate of this
  change.
- **C1**: with options landed, the corpus run reports **zero** declared divergences.
