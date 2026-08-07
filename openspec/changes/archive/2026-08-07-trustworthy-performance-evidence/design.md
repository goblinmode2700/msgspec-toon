## Context

See `proposal.md` — Why. Two constraints shape everything below.

First, the measured variance decomposition (four processes, twelve in-process samples each,
encode path):

| Size | Within one process | Between processes |
|---|---|---|
| 16 records | 0.74% CV | 2.4% spread |
| 64 records | 1.07% CV | 4.1% spread, monotonically rising |

The precision is already there; the harness throws it away by comparing across processes
separated by minutes.

Second, the prior-art survey in `docs/prior-art/two-builds-one-process.md`. Every mature
harness — `pyperf`, `criterion.rs`, `hyperfine` — answers between-process variance with
replication plus a significance test. None loads two builds into one process, and the exact
blocker for doing so is documented there (a PyO3 module name is a literal consumed by a
proc-macro attribute, so it cannot be computed per build).

## Goals / Non-Goals

**Goals:**

- An estimator that answers "what does a caller experience" rather than "what is the best
  this machine ever did".
- An A/B design whose null result is informative: a published minimum detectable effect.
- Two gates that fail on silent regression — one deterministic (tokens), one statistical
  (speed).
- Methodology visible in the artifact, so a reader can judge a figure without reading code.

**Non-Goals:**

- Adopting `pyperf` as a dependency. Port the method, not the package: it wants to own the
  process model and the result format, and this project already has a corpus runner, a
  report generator, and a frozen-baseline environment.
- Loading two builds in one process. Surveyed and rejected; revisit only if something needs
  sub-1% resolution (realistically only candidate E3).
- Any new comparative assertion against another codec. Stated as a spec requirement so a
  later round cannot add one absent-mindedly.
- Re-measuring the historical ledger under the new estimator. Old figures get labelled with
  the estimator that produced them; they are not restated.

## Decisions

**D1 — Mean across workers, not minimum across batches.**
`pyperf`'s documented position, and the one adopted here: the minimum rewards whichever run
dodged the scheduler, and has no central-limit behavior to converge on. The mean across
independent processes averages over the things that actually vary between runs — address
layout, allocator state, frequency, core assignment.
*Alternative considered:* median across workers, which is more outlier-robust. Rejected for
now because outliers here are real slow runs a caller would also experience; the standard
deviation is published so a reader can see when the distribution is ugly.
*Consequence:* every published microsecond figure moves. This is a relabelling event, not a
regression, and the report must make the estimator visible for figures to be comparable at
all.

**D2 — Blocks are one metric at one size.**
A block currently measures every size and both suites, so adjacent blocks are minutes apart
and the thermal drift term is large. One metric at one size takes about half a second, so an
alternating pair straddles seconds and drift is common-mode.
*Alternative considered:* keep long blocks and increase round count. Rejected — it multiplies
runtime without shrinking the dominant term.

**D3 — Student t-test at alpha 0.95.**
Matches `pyperf`, so the choice is defensible by precedent rather than invention, and
"significant" has a defined false-positive rate instead of the current compare-median-to-
spread heuristic.
*Alternative considered:* bootstrap confidence interval, as `criterion.rs` uses. Equally
defensible and more robust to non-normality; rejected only because the t-test is simpler to
implement correctly and easier for a reader to check. Worth revisiting if worker
distributions turn out skewed — the retained blocks make that checkable after the fact.

**D4 — The token gate is a lock file, not a threshold.**
Token counts are a deterministic function of bytes and tokenizer, so the honest gate is an
exact snapshot, not a tolerance. A tolerance would silently absorb exactly the drift the
gate exists to catch.
*Both directions fail.* An unexplained improvement means output changed, and canonical bytes
are a conformance surface — the corpus proves fixtures still pass, not that the encoder
still makes the same choices on payloads the corpus does not contain.
*The lock pins the tokenizer version* so an upstream change is attributable rather than
mysterious.
*Alternative considered:* asserting a ratio against JSON. Rejected — that is the T1 gate,
which lives in the ladder, and duplicating it as a test is the comparative-assertion slop
this change explicitly forbids.

**D5 — The speed gate lives in `make ab`, not in `pytest`.**
It needs the frozen baseline environment and takes minutes. `make check` stays offline and
fast; `make ab` becomes a gate that can fail. This preserves the existing separation where
`make baseline` builds an environment and `make check` never touches the network.

**D6 — Failure is asymmetric.**
Only a *significant* slowdown fails. A significant speedup is reported and recorded, never
enforced, because enforcing an improvement turns a benchmark into a ratchet that eventually
fails on a quiet machine.

**D7 — A slowdown must reproduce before it fails the build.** *(added during
implementation; the planning risk register predicted this and the false-positive check
found it.)*
One test at alpha 0.95 is wrong about one time in twenty, and this harness runs sixteen —
roughly a coin flip that some metric reports a spurious slowdown per run. Observed
directly: comparing the current build **against itself**, `typed encode@512` reported
"+1.6% SLOWER" with a 1.4% minimum detectable effect. A gate that fails on a third of
clean runs gets ignored, which is worse than no gate.
So a slowdown triggers an independent confirmation run of that metric alone, and only a
reproduced slowdown fails. Two independent tests at alpha 0.95 put the false-failure rate
near 0.25% per metric, and the cost is paid only when something already looks wrong.
*Alternative considered:* a Bonferroni correction across the sixteen metrics. Rejected for
the reason already recorded under Risks — it raises the detection threshold on exactly the
small effects this change exists to resolve. Confirmation buys the same protection without
spending power.
*Verified after the change:* the same self-comparison returned eight of eight "no
significant difference" and exit 0.

## Risks / Trade-offs

- **Every historical figure becomes non-comparable** → The ledger annotates existing entries
  with the estimator that produced them. No entry is restated under the new estimator
  without re-measurement, and the report names the estimator beside each figure.
- **More worker processes means longer runs** → Blocks shrink to one metric at one size, so
  total work is roughly preserved; if a full run gets slow, the size ladder is the knob, not
  the worker count.
- **The token lock will fire on legitimate encoder changes** → That is the intended behavior.
  The cost is one deliberate lock update per intentional change, with the reason recorded.
  The alternative is a gate that never fires.
- **A t-test assumes roughly normal per-worker means** → Retaining every block makes the
  assumption checkable after the fact rather than assumed; D3 records the bootstrap
  alternative if it fails.
- **Alpha 0.95 across sixteen metrics means false positives** → Confirmed in practice and
  handled by D7: a slowdown must reproduce in an independent run before it fails the gate.
  A multiple-comparison correction is still deliberately not applied, because it would
  raise the detection threshold on the very small effects this change exists to resolve.

## Migration Plan

1. Land the estimator change and re-run every gate. Expect all absolute figures to move; a
   corpus or G2/G3/G5 change at this step means the estimator change broke something and
   must be reverted, since no codec code is touched.
2. Annotate the existing ledger entries with `estimator: min-of-batches` before publishing
   anything under the new estimator, so the two never sit unlabelled in one artifact.
3. Generate the token lock from the current build, in a commit that changes nothing else,
   so the lock's initial values are reviewable as a diff against a known-good state.
4. Turn on the A/B exit code last, once the significance test has been observed to be
   quiet on an unchanged build.

Rollback: each step is independent and revertible; the lock file and the exit code can be
removed without touching the codec.

## Open Questions

- Worker count. `pyperf` defaults to 20; this project's ladder has four sizes and four
  metrics, so the right count is whatever holds a full A/B run inside a few minutes.
  Deferrable: it is a constant to tune once the harness exists, and it changes no spec.
- Whether the frozen baseline should be re-cut at `v0.2.0` now that `v0.1.0-conformant`
  is several rounds behind. Deferrable and separable — it changes what the deltas mean,
  not how they are measured.
