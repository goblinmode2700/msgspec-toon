# Prior art review: `toons` (Rust TOON codec)

**Version reviewed:** 0.7.0 (sdist from PyPI, 2026-05-21; source also at
github.com/alesanfra/toons). Reviewed 2026-08-06 against our Rust core at the
`v0.0.1-poc` tag. `toons` targets TOON **v3.0**; we target **4.1** — several
divergences below are that version gap, not defects, and they are exactly the
behaviors we must not inherit.

Scope reviewed per the dev-tooling spec: line scanning, delimiter/quoting,
number paths, tabular detection on encode, error position model, PyO3
construction techniques. Source: `src/lib.rs`, `src/deserialization.rs`
(1,262 lines), `src/serialization.rs` (1,218 lines).

## Architecture at a glance

Two modules behind a `#[pymodule] mod` block: an untyped parser
(`Parser { lines: Vec<&str>, pos, indent_size, strict, expand_paths }`) doing
recursive descent over a pre-collected line vector, and a recursive
serializer writing into a `String`. Untyped only — dict/list in, dict/list
out; nothing resembling a typed path, so it answers none of our challenge's
hard questions, but its codec internals are worth mining.

## Techniques adopted (or already independently shared)

- **Recursive descent over logical lines** with depth-from-indentation —
  same overall shape as our parser; convergent evolution, kept.
- **Leading-zero numerics classify as strings** (`05` → `"05"`) — identical
  to our `is_integer_literal` rule; corroborates the choice.
- **Quote-aware delimiter scanning** (`find_unquoted_char`,
  `split_by_delimiter`) — same algorithm family as our `find_unquoted` /
  `split_cells`.
- **Delimiter-in-bracket grammar**: `[N\t]` and `[N|]` declare tab/pipe
  delimiters inside the length bracket, comma being the default. This is the
  concrete grammar to implement when we add non-comma delimiters (a known
  Tier gap) — adopted as the reference shape for that work.
- **`[#N]` legacy-header rejection with a targeted message** — a diagnostics
  nicety worth copying when the fixture corpus tells us which legacy forms
  4.1 wants named explicitly.
- **datetime/date/time encoded via `isoformat()`** — a cheap, correct Tier-2
  encode path to reuse when we get there.

## Techniques rejected, with reasons

- **Owned-`String` input** (`loads(s: String)`) plus `input.lines().collect::
  <Vec<&str>>()` — a full document copy at the boundary and a line-index
  vector on top. Violates our streaming requirement; we borrow the CPython
  UTF-8 view and scan incrementally with one-line lookahead.
- **Payload in errors, by design**: `ToonDecodeError` carries `.source` (the
  raw offending line) and message strings interpolate payload fragments
  (`"Invalid array length: {length_str}"`). Directly forbidden by our AD-007;
  our faults carry coordinates and static templates only.
- **Silent data loss on encode**: non-finite floats become `null`, and *any
  unsupported type* becomes `null`. We raise `EncodeError` (but see the
  conformance question below on non-finite floats specifically).
- **Silent precision loss on big integers, both directions**: decode tries
  `parse::<i64>()` then falls through to `parse::<f64>()`, and encode tries
  `extract::<i64>()` then `extract::<f64>()` — an integer beyond ±2^63
  round-trips as a lossy float with no error. Our arbitrary-precision
  `int_from_digits` / exact `str()` fallback exists precisely because of
  this failure class (requirements: "Integers round-trip at Python's
  precision").
- **Wire knobs**: `dumps(indent=, delimiter=, key_folding=, flatten_depth=)`
  and `loads(expand_paths=)` — off-spec dotted-key folding/expansion and
  caller-chosen wire shape. Our AD-005 forbids all of it.
- **`pyo3 = { version = "*" }`** — a wildcard dependency on the FFI boundary
  crate. Ours is pinned (currently `=0.29.0` under the cooldown).
- **v3.0-era behaviors confirmed present and not inherited**: no nested
  field groups (flat `find('{')`/`find('}')` field lists, and its tabular
  detector requires every value primitive, so one nested object collapses
  the table — measured: 1,482 bytes vs our 527 on the 16-record challenge
  payload, worse than JSON's 1,339); float formatting via Rust `Display`
  (`1e-7` renders as `0.0000001`, the exact divergence §7 of the design of
  record observed); no comment lines.

## Misses found in OUR implementation

Per the dev-tooling spec, each becomes a fix, a tracked task, or a named
known-gap entry:

1. **Non-finite float encoding may be spec'd as `null`, not an error.**
   toons maps NaN/Infinity to `null` citing "spec Section 3"; we raise
   `EncodeError` (msgspec.json parity). The 4.1 fixture corpus decides this.
   → recorded in the release report's known-gaps list; resolve in Phase 2
   conformance.
2. **Delimiter grammar confirmed and still unimplemented**: `[N\t]`/`[N|]`
   is the concrete syntax our comma-only parser must eventually accept and
   our strict mode must validate against row delimiters. → already a known
   gap; the grammar reference is now written down here.
3. **Indent-size flexibility**: toons auto-detects indent width (first
   indented line; explicit override) where our scanner hard-codes 2.
   Canonical 4.1 output is 2-space, but whether strict *decode* must accept
   other consistent widths is fixture-decidable. → known-gap entry;
   non-strict mode is the natural home if the corpus allows it.
4. **No misses found** in quoting, duplicate handling, row-width checking,
   or position tracking: our implementation checks strictly more than toons
   does in each of those areas (toons does not validate indentation
   multiples in non-strict, accepts short rows in places we fault, and its
   `.line` attribute clamps to the last line rather than pointing past EOF).

## Bottom line

`toons` is a competent untyped v3.0 codec whose value to us is negative
space: it demonstrates the exact failure modes our requirements were written
against (payload-echoing errors, lossy numeric domains, silent nulls, wire
knobs, format staleness) and supplies one concrete grammar detail (delimiter
brackets) we will need. Nothing in it changes our architecture; two fixture-
decidable conformance questions (non-finite encode, indent flexibility) are
now tracked in the report.
