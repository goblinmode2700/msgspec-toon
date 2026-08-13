# Token efficiency is a property of the tabular forms

The token advantage is a property of the tabular forms specifically, not of
TOON. This document records why that is, closes the three tabular-fallback
questions against the spec, and publishes the indent axis. All token counts
are tiktoken 0.13.0 / `o200k_base` from `benches/bench_tokens.py`, which is
deterministic — these numbers do not depend on the machine that ran them.

## The mechanism

TOON tokenizes worse *per byte* than JSON: JSON's punctuation is saturated in
the merge table and TOON's indentation and `key: value` runs are not. So the
token ratio is roughly the byte ratio divided by the relative tokenization
density, and TOON needs about a 0.77× byte ratio just to break even on
tokens. Tabular clears that easily (0.37× bytes → 0.61× tokens at 4096
records). Entry-by-entry does not clear it at all: on the irregular payload
TOON produces *smaller output that costs more tokens than JSON* — 0.94×
bytes, 1.19× tokens at 512 records.

| shape (o200k, vs compact JSON) | canonical (indent=2) | indent=1 |
|---|---|---|
| uniform records @16 | 0.640 | 0.597 |
| uniform records @4096 | 0.621 | 0.579 |
| string-heavy @512 | 0.800 | 0.780 |
| numeric-heavy @512 | 0.646 | 0.614 |
| **irregular @16** | **1.158** | **1.029** |
| **irregular @512** | **1.186** | **1.031** |

## The three fallback questions are closed: the spec requires all three

Checked against TOON 4.1.1, `toon-format/spec` @ `62f16b3` (the pinned
conformance commit), §9.3 "Arrays of Objects – Tabular Form":

1. **A row missing a key the others have.** Detection requires "All objects
   have the same set of keys". A sparse row disqualifies the array; §9.4 list
   form is mandatory. Strict decoding independently requires every row's cell
   count to equal the leaf-field count, so a sparse *row* cannot exist on the
   wire either.
2. **`Optional[Struct]` that is `None` in one row.** Named explicitly: a
   column "mixing `null` (a primitive) with objects" is neither
   uniform-primitive nor nested-uniform and "disqualifies the whole array".
   A nested field group cannot be null-filled.
3. **A list-valued column.** Also named explicitly: a column "containing any
   array value or empty object" disqualifies the array.

Detection is MUST in both directions — an eligible array MUST be tabular and
a disqualified one MUST be list form — so the classifier cannot legally be
more aggressive than it is, and every fallback this encoder takes is one the
spec requires. There is no code change that recovers tokens on these shapes.

## What a caller can do

Token shape and decode speed are separate axes. The release guard measures
uniform tabular records, nested mixed records, irregular records, and distinct-key
cardinality. A speed claim for one shape is not generalized to the others.

- **Shape the payload tabular** where possible: uniform records are the
  0.58–0.64× shapes. This is the entire advantage.
- **`indent=1`** is a spec-legal wire option (§12) and saves tokens on every
  measured shape: about 4 points on the tabular ladder (a single leading
  space merges into the first cell's token, two spaces cost their own token
  per row) and 13–15 points on irregular shapes. It does not change the
  canonical default and never moves the efficiency lock.
- **Irregular, non-uniform payloads should stay JSON** when tokens are the
  budget: they cost more tokens than compact JSON at every measured indent,
  indent=1 included. The library says this here rather than letting a user
  discover it, in the same spirit as the G4 reporting.
