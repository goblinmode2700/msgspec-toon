---
usf: 1
type: spec
id: toon-native-codec
title: A conforming, natively typed TOON codec for Python — an open challenge
status: proposed
---
# toon-native-codec — the design of record

**An open challenge, not an assignment.** No implementation exists. Nobody has been asked to
build one. This document states a problem precisely, states why the obvious routes fail, and
states an unambiguous criterion for a solution. A claimant runs the acceptance suite in
`requirements.md` and publishes the report. That is the whole procedure.

Every number below was measured on 2026-08-05, on Apple silicon, with Python 3.13, msgspec
0.21.1, Node v22.22.3, and the three named codec releases. The measurement scripts are named
where each figure appears. Nothing here is estimated.

## 1 · The problem, stated

> Build a TOON codec for Python that is byte-exactly conformant with TOON specification 4.1,
> and that decodes TOON text directly into a typed `msgspec.Struct` without first building an
> intermediate tree of Python built-in objects.
>
> Equivalently: make `msgspec.toon` exist, and make it as good as `msgspec.json` — not as good
> as `msgspec.toml`.

The second sentence is the whole difficulty, and §3 explains why.

## 2 · Why anyone wants this

TOON is a text serialization designed to cost fewer tokens than JSON when a language model
reads it. Its saving comes almost entirely from one construct: a tabular array, where the field
names are written once in a header and each element is a delimiter-separated row.

```
   the tabular form                             the fallback form
   ────────────────────────────────────────     ──────────────────────────────
   data[2]{pid,provider,alias}:                 data[2]:
     20324,claude,worker-a                        - pid: 20324
     80916,claude,worker-b                          provider: claude
                                                    alias: worker-a
                                                  - pid: 80916
                                                    provider: claude
                                                    alias: worker-b
```

Measured on a real 9-record inventory document with 19 fields per record, one of them a nested
object:

```
   compact JSON                             5,342 bytes
   TOON 4.1, tabular                        3,103 bytes      −41.9%
   TOON 3.0, fallback (one nested field)    5,760 bytes      + 7.8%
```

The tabular form saves 42 percent. The fallback form is worse than the JSON it replaced. The
entire value of the format lives in reaching the table, and reaching the table for
records-with-a-metadata-object is a **specification 4.0 feature** (§4).

That is the first half of the problem. The second half is that a format meant to feed typed
application data to a model is useless if getting the data into the format costs more than the
format saves. That is the msgspec half, and it is the hard one.

## 3 · Why this is hard — three walls

### Wall one · The specification moved, and Python has not followed

TOON's version history, from the specification repository's own changelog:

```
   v3.0   2025-11-24   standardized list-item objects with tabular arrays
   v3.1   2026-05-18   unicode escape sequences
   v3.2   2026-05-20   duplicate key handling, nested array forms
   v3.3   2026-05-21   explicit boolean and null requirements
   v4.0   2026-07-22   comment lines, and NESTED FIELD GROUPS in tabular headers
                       orders[2]{id,customer{name,country},total}
   v4.1   2026-07-26   encoder requirements and conformance fixtures
```

Nested field groups are the construct that lets a record with a nested object stay on one flat
row. That is the 42 percent above. It arrived on 2026-07-22.

The three Python codecs available today:

```
   library                    latest release   claims                     status
   ────────────────────────   ──────────────   ────────────────────────   ────────────────────
   toons (Rust, PyO3)         2026-05-21       "Full TOON v3.0 support"   two majors behind;
                                                                          its release predates
                                                                          v4.0 by two months
   the reference org's        2025-11-08       names no version;          beta; "working
   Python port                (prerelease)     "working towards spec       towards" is its own
                                               compliance"                 word
   the earliest third-party   2025-11-04       none                       dormant; emits a
   pure-Python library                                                     non-conforming
                                                                          tabular header
```

**No Python TOON codec targets 4.1.** Not one. The reference TypeScript package is the only
implementation at 4.1 in any language ecosystem examined.

This wall is the shallow one. It is a matter of work, not of possibility, and it will fall on
its own eventually. It is stated because a solution must clear it, not because it is interesting.

### Wall two · msgspec has no C API, so the fast path is closed to outsiders

msgspec is a compiled serialization library. Its typed decoders read bytes and construct the
target `Struct` inside C, in one pass, with no intermediate dictionary.

That machinery is private. The installed distribution contains exactly one compiled object,
`_core.cpython-313-darwin.so`, and **no header files at all**. There is no public C API, no
exported capsule, and no documented extension point for a new format that wants the same path.

msgspec's own answer for a format it does not implement in C is a pure-Python wrapper. Reading
`msgspec/toml.py`:

```python
   # encode:   msgspec value ─▶ to_builtins ─▶ third-party writer ─▶ bytes
   # decode:   bytes ─▶ third-party reader ─▶ builtin tree ─▶ convert ─▶ Struct
```

`msgspec/yaml.py` is the same shape. So the honest statement is: **msgspec's non-core formats
are wrappers by design, and a third-party TOON codec has no route to be anything else.**

### Wall three · The wrapper tax is larger than the job

Measured with `bench_convert_tax.py` on an 8,896-byte document — 64 records, one nested object
each, the exact shape from §2:

```
   DECODE — bytes to a typed Struct
     native      msgspec.json.Decoder(Document).decode        8.9 us
     untyped     msgspec.json.decode  (builtin tree only)    10.7 us
     convert     msgspec.convert(tree, Document)              5.4 us
     wrapper     decode to a tree, then convert              16.3 us    ◀ 1.8x native

   ENCODE — a typed Struct to bytes
     native      msgspec.json.encode(document)                3.7 us
     to_builtins msgspec.to_builtins(document)                5.0 us    ◀ 135% of the WHOLE
                                                                          native encode, paid
                                                                          before a codec starts
```

Read the encode line again. A wrapper's *preparation step alone* costs more than msgspec's
entire native encode. Whatever a third-party codec then does — however fast, in whatever
language — is added on top of a bill that already exceeds the native path.

So a very fast Rust TOON codec plugged in as a wrapper does not produce a fast typed TOON path.
It produces `msgspec.toml` with better throughput in the middle.

**The three walls compose.** Clearing wall one gives a conforming codec. Clearing walls two and
three gives a codec that is actually worth calling from typed Python. A solution must clear all
three, and the second is the one nobody has a known route through.

## 4 · What a solution looks like

Three routes are visible. None is known to work. A claimant may take any of them, or another.

```
   ROUTE A · UPSTREAM
   Get a native TOON codec into msgspec itself, beside json and msgpack, inside _core.
   ────────────────────────────────────────────────────────────────────────────────────
   clears all three walls completely and permanently.
   the cost is that it is not yours to decide — it needs the maintainer's agreement, a C
   implementation matching that codebase's standard, and a maintenance commitment. it would
   also be the first non-core format msgspec has ever admitted to C, so the argument has to
   be stronger than "it is faster this way."

   ROUTE B · REIMPLEMENT THE TYPE MACHINERY IN RUST
   Read msgspec's type introspection from Python, build the decode plan in Rust, and
   construct the target Struct directly from TOON text.
   ────────────────────────────────────────────────────────────────────────────────────
   msgspec exposes enough to attempt this: `msgspec.inspect` returns a full type description,
   `msgspec.structs` exposes field metadata, and Struct instances are ordinary Python objects
   a Rust extension can allocate and populate.
   the cost is that you are reimplementing a large, subtle, well-tested piece of someone
   else's library — defaults, tagged unions, renaming, constraints, dec_hook, UNSET, and the
   validation error messages — and you inherit the obligation to track it. this is the route
   most likely to produce a working artifact and most likely to rot.

   ROUTE C · MAKE THE WRAPPER TAX DISAPPEAR
   Keep the wrapper shape, but stop paying for the intermediate tree.
   ────────────────────────────────────────────────────────────────────────────────────
   the tree is the cost, not the convert call: convert alone is 5.4 us against a 16.3 us
   wrapper. a codec that hands msgspec something cheaper than a dict-of-dicts — a lazy view,
   a buffer msgspec can already read, a Raw-like construct — might collapse most of it.
   the cost is that this is a research question with an unknown answer. it is also the only
   route that does not require anyone else's permission.
```

A fourth route exists and is explicitly ruled out in §5: moving the conversion out of process.

## 5 · Non-goals, on the record

- **No daemon, no subprocess, no socket, no network.** A prior design for this problem placed
  the reference TypeScript codec behind a local Unix-domain socket. It was measured. An
  in-process Rust codec beat that architecture at every payload size in both directions — 1.2x
  to 5x on encode, 9x to 19x on decode — because the transport was never the expense; the
  JavaScript codec behind it was. That route is closed. See §7.
- **No JavaScript numeric domain.** The same prior design had to reject every integer outside
  ±(2^53 − 1) before parsing, because JavaScript would silently round it. Python has
  arbitrary-precision integers and TOON is text. A solution here must round-trip large integers
  exactly, not reject them. This is a hardening, and it is a requirement, not a preference.
- **No query language.** This is a codec. Filtering, selection, and transformation belong to
  whatever the caller already uses.
- **No new format.** TOON 4.1 as published is the target. A "mostly TOON" output is a failure,
  not a variant.
- **No configuration surface for the wire.** The canonical output profile is fixed. A caller
  choosing a delimiter is a caller producing bytes that another reader will not accept.

## 6 · The acceptance criterion, in one paragraph

A solution is a Python distribution that installs from a wheel with no toolchain present, has no
runtime dependencies beyond msgspec, and passes every requirement in `requirements.md` with a
published report. The two requirements that decide it are **byte-exact conformance against the
official 4.1 fixture corpus in both directions**, and **typed decoding that constructs the
target Struct without materializing a builtin tree**, demonstrated by measurement rather than by
claim. Everything else in that file is a floor, not a goal.

## 7 · The measured landscape a solver inherits

Codec speed, microseconds, minimum of autoranged batches, from `bench_codecs.py` and
`bench_toon_node.mjs`. The payload is a record array; the sizes are the standard ladder.

```
                    pure-Python 0.1.3      Rust 0.7.0 (v3.0)     reference TypeScript 4.1
   ─────────────────────────────────────────────────────────────────────────────────────
   encode   1 KiB              34.1                   10.6                        11.3
   encode  10 KiB             329.6                   99.4                        99.8
   encode 100 KiB           3,031.9                1,011.9                       977.6
   encode   1 MiB          32,114.3               10,482.8                    10,561.6

   decode   1 KiB              70.0                    3.8                        30.0
   decode  10 KiB             648.6                   35.0                       283.2
   decode 100 KiB           6,335.9                  352.6                     2,892.1
   decode   1 MiB          66,467.4                3,876.1                    32,834.6
```

Three facts a solver should take from this table:

1. **A compiled codec is worth roughly 3x on encode and 18x on decode** against the
   pure-Python implementation. That gap is real and already achieved by existing work.
2. **The reference TypeScript encoder ties the Rust one and loses 8x on decode.** Conformance
   and speed are independent axes here. The conforming implementation is not the fast one.
3. **The whole codec difference is tens of microseconds on realistic documents.** Against the
   msgspec integration tax in §3, and against anything a calling program does with the result,
   codec throughput is not where this problem lives. It is stated so a solver does not optimize
   the wrong thing.

Conformance, from a differential run of the Rust codec against the reference encoder: five of
eight constructed payloads byte-identical, and two of four real documents. The three
divergences, all of them real:

```
   nested field groups   reference: data[1]{name,nested{deep}}:     the v4.0 feature; the
                         rust:      data[1]: then indented pairs    42 percent in §2
   number formatting     reference: 1e-7 and 1e+21                  canonical number format
                         rust:      0.0000001 and the expanded      arrived in v1.4 and the
                                    twenty-two-digit literal        rust codec predates it
   empty arrays          reference: []                              a spelling difference,
                         rust:      [0]:                            small but not optional
```

All twelve payloads round-tripped correctly through the Rust codec. It is not broken. It is
**correct against an older specification**, which is a different problem and a harder one to
notice.

## 8 · Open questions for a claimant

These are genuinely open. A solution does not have to answer them, but a good one will.

1. **Does route C have an answer at all?** Is there any representation a third-party codec can
   hand msgspec that reaches a Struct more cheaply than a builtin tree, using only the public
   surface? If the answer is no, that is a publishable result on its own, and it makes the case
   for route A.
2. **How much of the tax is the tree and how much is convert?** The §3 measurement says convert
   is 5.4 of 16.3 microseconds, so roughly two thirds is building and discarding the tree. Is
   that ratio stable across document shapes, or does it invert on deeply nested data?
3. **Can conformance be inherited rather than reimplemented?** The reference implementation is
   TypeScript. Its fixture corpus is published. Is there a route where the corpus, rather than
   the code, is the thing a Rust implementation tracks — and how does that survive v4.2?
4. **What is the honest measurement unit?** Every size figure in this document is BYTES. TOON's
   entire claim is TOKENS. The two correlate but are not the same variable, and no figure here
   has been converted. A solution that reports token counts against a named tokenizer is
   strictly more useful than one that reports bytes.
5. **What happens at v4.2?** The specification had two major revisions in the fourteen days
   before this document was written. Any implementation is a commitment to track a moving
   target. Is there a design that makes conformance data rather than code?

## 9 · Where this document came from

Authored outside the project that wants it, on 2026-08-05, from a measurement session that began
as an evaluation of a proposed local transcoding service and ended by establishing that the
service was solving the wrong problem. The prior design — a hardened local daemon running the
reference TypeScript codec behind a framed binary protocol — is the direct ancestor of §5's
first two non-goals. Its rigor about output sanitizing, canonical output profiles, and pinned
conformance fixtures is preserved in `requirements.md`. Its architecture is not.

The measurement scripts named throughout are the evidence. A reader who does not trust a figure
should re-run the script rather than argue with the number.

## Siblings in this directory

- `requirements.md` — the checkable acceptance requirements.
