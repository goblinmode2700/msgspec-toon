# Trustworthy performance evidence

## Why

The harness cannot resolve the changes it is asked to judge, and nothing fails when
efficiency silently regresses. Measured this session: within one process the encode path
varies by 0.74–1.07%, but between processes it varies by 2.4–4.1% and drifts monotonically
as the machine warms (four consecutive baseline blocks at 64 records: 7.399, 7.540, 7.584,
7.699 µs). The instrument's floor therefore exceeds several published deltas, and two
encode claims at 16 and 64 records are currently unresolvable. Separately, `_timing.py`
reports the *minimum* of seven batches, which rewards whichever batch dodged the scheduler
— `pyperf`'s documented position is that the minimum is unstable and biased, and the mean
across many worker processes is the honest estimator. Finally, token efficiency and speed
are *reported* but never *gated*: canonical output could grow 5% and every existing check
would still pass, because the fixture corpus tests conformance, not efficiency.

## What Changes

1. **Estimator: mean across worker processes, not minimum within one.** `benches/_timing.py`
   gains a calibrated worker-process model — calibrate the loop count once, spawn N workers,
   discard each worker's first (warmup) value, report the mean and standard deviation across
   workers. The published methodology string states the estimator by name. **BREAKING** for
   any recorded figure: absolute microseconds will shift, because a mean is not a minimum.
   Historical ledger entries are relabelled with the estimator that produced them rather
   than silently reinterpreted.
2. **A/B blocks get shorter, more numerous, and per-metric.** One block measures one metric
   at one size, so adjacent blocks sit seconds apart instead of minutes and drift becomes
   common-mode. `ab.py` alternates them and keeps every block.
3. **A significance test replaces the median-versus-spread heuristic.** Two-sample
   two-tailed Student t-test at alpha 0.95 (the `pyperf` choice), with "no significant
   difference" as a first-class published outcome and a per-metric minimum detectable
   effect so a null result is interpretable.
4. **NEW GATE — token efficiency cannot regress silently.** A locked snapshot
   (`conformance/efficiency.lock.json`) records byte and token counts for the canonical
   payload set under pinned tokenizers. A test recomputes and compares exactly; any drift
   fails with a diff. The lock pins the tokenizer version too, so an upstream tokenizer
   change is a loud failure rather than a mystery.
5. **NEW GATE — speed cannot regress silently.** `benches/ab.py` exits non-zero when any
   metric is *significantly slower* than the frozen baseline. Noise never fails the gate;
   only a resolved regression does.
6. **The report carries the methodology.** Estimator, worker count, warmup policy,
   significance test and alpha, and per-metric minimum detectable effect all appear in
   `conformance/report.json`.

Explicit non-goal, recorded so a later round does not "helpfully" add it: **no new tests
asserting this codec beats another codec.** G5 (speed floor) and T1 (token floor) already
make that comparison once, on the published ladder, where a miss is visible. Multiplying
comparative assertions into unit tests produces a suite that measures the machine and
flatters the author.

## Capabilities

### New Capabilities

None. Every requirement here belongs to the existing evidence capability.

### Modified Capabilities

- `distribution-quality`: the benchmark estimator and its A/B design become stated
  requirements rather than implementation detail; token efficiency and speed each gain a
  regression gate; the report must publish the methodology and the minimum detectable
  effect alongside each figure.

## Impact

- `benches/_timing.py` — worker-process estimator replaces min-of-batches. Every benchmark
  script consumes it, so all published microsecond figures move.
- `benches/ab.py` — per-metric short blocks, t-test, non-zero exit on a resolved slowdown.
- `benches/bench_tokens.py`, new `conformance/efficiency.lock.json`, new test asserting the
  lock — the token gate.
- `scripts/release-report.py` — publishes estimator, alpha, worker count, and MDE.
- `benches/optimization-ledger.json` — existing entries annotated with the estimator that
  produced them; no figure is restated under the new estimator without re-measurement.
- `Makefile` — `make ab` becomes a gate that can fail; `make check` stays fast and offline.
- Documentation: `LAST-MILE.md` queue, `HANDOFF.md` invariants.
