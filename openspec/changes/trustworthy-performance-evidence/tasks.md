## 1. Label the past before changing the estimator

- [x] 1.1 Annotate every existing entry in `benches/optimization-ledger.json` with
      `estimator: "min-of-batches"`, so no artifact ever holds two estimators unlabelled.
- [x] 1.2 Record in the ledger that figures under the two estimators are not comparable and
      that no historical figure will be restated without re-measurement.

## 2. The estimator

- [x] 2.1 Add a worker-process runner to `benches/_timing.py`: calibrate the loop count once,
      spawn N workers, have each discard its first value as warmup, return the mean and
      standard deviation across workers.
- [x] 2.2 Update `methodology()` to name the estimator, worker count, and warmup policy;
      every benchmark script already routes through it, so no script hand-rolls a loop.
- [x] 2.3 Choose the worker count by measuring: pick the smallest count whose reported
      standard deviation stops shrinking materially, and record the measurement that chose it.
- [x] 2.4 Re-run `make check`, the corpus, G2, G3, G5 and confirm nothing but the absolute
      figures moved. A gate change here means the estimator work broke something, since no
      codec code is touched.

## 3. The A/B design

- [x] 3.1 Restructure `benches/ab.py` so one block measures one metric at one payload size.
- [x] 3.2 Alternate blocks and retain every block in `benches/ab-latest.json`.
- [x] 3.3 Implement the two-sample two-tailed t-test at alpha 0.95 and replace the
      median-versus-spread verdict with it.
- [x] 3.4 Compute and publish a per-metric minimum detectable effect so a null result is
      interpretable.
- [x] 3.5 Verify the harness is quiet on an unchanged build: run it against a rebuilt current
      wheel and confirm no metric reports a significant difference.
- [x] 3.6 Re-run the two encode metrics that F-12 could not resolve (16 and 64 records) and
      record whether the new design resolves them.

## 4. The token gate

- [x] 4.1 Generate `conformance/efficiency.lock.json` from the current build: byte and token
      counts for the published payload set, plus tokenizer name and version. Commit it in a
      change that alters nothing else, so the initial values are reviewable.
- [x] 4.2 Add a test that recomputes the counts and fails on any difference in either
      direction, naming the payload and both counts.
- [x] 4.3 Fail loudly and specifically when the installed tokenizer version differs from the
      locked one, so a tokenizer change is never reported as a codec change.
- [x] 4.4 Prove the gate fires: temporarily perturb encoder output, confirm the test fails
      with a useful diff, revert. Do not mark this task done from inspection.
- [x] 4.5 Document the lock-update procedure — a deliberate edit with the reason the counts
      moved — in `LAST-MILE.md`.

## 5. The speed gate

- [x] 5.1 Make `benches/ab.py` exit non-zero when any metric is significantly slower than the
      frozen baseline, naming the metric, size, and effect.
- [x] 5.2 Confirm a difference that fails the significance test does not fail the gate.
- [x] 5.3 Keep `make check` offline and fast; the gate belongs to `make ab`.
- [x] 5.4 Prove this gate fires too: introduce a deliberate slowdown, confirm a non-zero exit,
      revert. Done via the two-baseline split: the same 24% slowdown reads +2.2% "no
      significant difference" against the story baseline (exit 0) and +24.4% SLOWER against
      the guard baseline, reproduced on the confirmation run (exit 1).
- [x] 5.5 Split the baselines: `make baseline` builds the story environment
      (`v0.1.0-conformant`, reported), `make guard` builds the gate environment (`v0.2.0`,
      the latest release). `make ab` gates against the guard; `make ab-story` reports
      against the story baseline and never gates.

## 6. Publish the methodology

- [x] 6.1 Add estimator, worker count, warmup policy, significance test, alpha, and per-metric
      minimum detectable effect to `conformance/report.json`.
- [x] 6.2 Publish the token lock's tokenizer name and version in the report beside the token
      rows.
- [x] 6.3 Update `HANDOFF.md` invariants: performance claims carry a significance verdict, and
      token counts are locked.

## 7. Close the round

- [x] 7.1 Confirm the non-goal held: no new test asserts this codec beats another codec, and
      the comparison still lives only in the ladder under G5 and T1.
- [x] 7.2 Run the full gate set — `make check`, corpus, `make g2`, `make bench`, `make ab`,
      token gate — and record the results in `LAST-MILE.md`.
- [x] 7.3 Update the queue in `LAST-MILE.md` and the next action in `HANDOFF.md`.
- [ ] 7.4 Sync the delta spec into `openspec/specs/distribution-quality/` and archive the
      change.
