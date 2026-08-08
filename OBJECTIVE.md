# OBJECTIVE

What this project is trying to do, what it is not allowed to do, and where it
currently stands. Written in plain words on purpose.

`HANDOFF.md` is the live state of the world. This file is the thing that does not
change round to round: the goal and the fence around it.

---

## The objective

```
minimize    tokens(output)                    first priority
then        time(encode) + time(decode)       second priority

subject to  C1 .. C9 below
```

Tokens come first. This codec exists to put data into a language model's context
window. Prefill cost scales with tokens. Codec microseconds do not. A change that
saves 5 percent of tokens beats a change that saves 5 percent of time.

Speed still matters, because a codec nobody can afford to call is a codec nobody
calls. It is second, not equal.

---

## The constraints

These are the fence. A change that breaks one of these fails, no matter how much
it improves the objective. "Faster but non-conformant" is not a trade to consider;
it is a rejected suggestion.

| # | Constraint, in plain words | Where it is proven |
|---|---|---|
| C1 | Output is byte-exact canonical TOON 4.1. All 538 official fixtures pass, both directions. | `conformance/run.py` |
| C2 | Typed decode builds no intermediate dict or list tree. It goes straight from bytes to Structs. | `make g2` |
| C3 | Error messages carry a code, a line and a column, and never any of the user's data. | `tests/test_errors.py` |
| C4 | The parser modules must not import Python. They stay extractable as pure Rust. | reading `src/scan.rs`, `parser.rs`, `header.rs`, `scalar.rs` |
| C5 | Structs are built by calling the class. Never by writing msgspec's private memory layout. | `src/typed.rs` |
| C6 | No input, however malformed, may panic, abort, or kill the process. | `tests/test_containment.py` |
| C7 | Behave the same as `msgspec.json` where we claim support. Where we do not support something, refuse loudly. Never quietly disagree. | `conformance/support_matrix.py` |
| C8 | One implementation per problem. No unnamed number doing policy work. | `clippy.toml`, review |
| C9 | Every claim is measured on this machine and generated into evidence. Nothing is asserted. | `conformance/report.json` |

C7 deserves a sentence of its own, because it carries the project's severity order:
**a wrong answer is worse than a refusal.** A refusal is visible to the caller. A
wrong value is not. Anything that makes us silently disagree with `msgspec.json`
outranks every performance idea on the board.

---

## Current state: the objective has converged

Both things we set out to minimize are now at their constrained optimum. This is
not an opinion; it is what three rounds of measurement produced.

### Tokens: no move left inside C1

We asked whether the encoder could pack more shapes into the cheap tabular form.
The answer, checked against TOON 4.1 section 9.3 and the fixture corpus, is no.
All three shapes that fall back to the expensive form are *required* to fall back,
and detection is mandatory in both directions, so the encoder may not be more
aggressive than it already is.

```
token gradient inside the rules = 0
```

What remains is not ours to spend. It belongs to whoever calls us:

| Lever | Worth | Who decides |
|---|---|---|
| Pass `indent=1` | 4 to 13 percent fewer tokens | the caller |
| Send uniform records, not irregular blobs | 0.62x vs 1.19x against JSON | the caller |

The second row is the important one and it is documented in
`docs/token-shape-guidance.md`: **the token advantage belongs to the tabular
forms, not to TOON.** On irregular data this codec costs *more* tokens than plain
JSON while producing fewer bytes.

### Speed: the remaining wins are smaller than the ruler

| | size |
|---|---|
| What the A/B gate can resolve today (finding H3) | 1.3 to 2.0 percent |
| Largest remaining known win (E4) | about the same |
| Known mechanism for the small-payload encode gap (G4 at 16 and 64) | none |

A win we cannot measure is a win we are not allowed to claim. That is C9 working
as designed, not a bug in it.

### The rounds show the same thing

| Round | What it bought |
|---|---|
| 1 | typed encode 17 percent faster, keyed decode 88 percent faster |
| 2 | entry decode 89 percent faster, entry encode 23 percent faster |
| 3 | nothing. Zero codec changes. The entire round went into fixing the measuring instrument. |

Round 3 is the signal. When a round produces no code change and instead argues
about the ruler, the search has converged.

---

## What is actually left

Two items. Neither one is optimization.

### 1. C7 is broken. Fix it. (item C-00)

Write `Annotated[int, Meta(ge=10)]`. Pass a 5. `msgspec.json` rejects it. We accept
it and hand back a Struct holding a bad value, with no error.

The constraint is lowered into the plan IR and never applied. This is the last
place where we silently disagree with msgspec, and the support matrix has carried
`silently_ignored: 1` for exactly this since the matrix existed.

Done means: the matrix entry flips to `supported`, a differential against
`msgspec.json` covers accepted and rejected values across every constraint kind,
errors still carry no payload text (C3 is the easy one to break here, because a
natural message wants to quote the offending value), and `make ab` shows no cost
on payloads that declare no constraints.

### 2. C9 has a floor. Characterize it, then stop chasing it.

Two builds of identical source are not equally fast. Against a guard built from
the same commit, `entry decode@512` reads consistently 1.0 to 1.8 percent slow
across four solo runs. The likely cause is that the guard is built in a separate
worktree, so path strings embedded in the binary shift the code layout.

One experiment settles it: build the same source at a third path and compare it
against the guard. If it also differs by about a percent, the floor is real and
permanent, and the honest response is to publish it as the gate's resolution
rather than keep hunting it.

---

## Reopened bounded improvement round (2026-08-07)

The previous exit condition was correct for the evidence then available. A new
symbolized profile and public-entry-point profile found mechanisms that the three
review rounds did not measure. The owner explicitly reopened the objective for one
bounded round over those mechanisms. This is a new objective statement, not an
implicit continuation of the old loop.

After C-00 and the H3 floor experiment, execute these checkpoints in order:

1. Add functional `encode()` / `decode()` ladder rows before optimizing their
   construction overhead.
2. Attempt bounded plan/codec reuse only if those rows resolve the overhead; do not
   introduce an unbounded class-retaining cache.
3. Attempt a first-byte specialization of `needs_quote`.
4. Attempt a one-pass quote/delimiter scan in `split_cells_into`.
5. Attempt to move absent-`Any` forwarding off the typed common path.
6. Measure wide-dictionary row-shape validation, then replace quadratic membership
   only if the payload and same-session A/B resolve it.

Each item remains a falsifiable checkpoint: add the metric or differential first,
make one focused change, run the protected gates, adopt only a same-session resolved
win, otherwise revert and record the rejection. E4 list collection is explicitly
deferred because the profile put it below these candidates and probably below H3.

The remaining product backlog is still scope, not optimization:

- `strict=False` scalar coercion (F-06). Not a constraint repair. Nothing is
  silently wrong today; unsupported input refuses loudly. This is a new feature,
  and it is the one that would make model-written TOON usable.
- Tier 2 types, cell-accurate error columns, the multi-platform wheel matrix.

Those are decisions about how far to take the product. They are not this objective
function, and they should be chosen deliberately rather than fallen into because
the loop was still running.

**Exit condition, stated plainly:** the support matrix shows zero `silently_wrong`
and zero `silently_ignored`; the gate's resolution floor is published; and every
candidate in the bounded queue above is either adopted with same-session evidence or
rejected with its falsifier recorded. Further work again requires a new objective.
