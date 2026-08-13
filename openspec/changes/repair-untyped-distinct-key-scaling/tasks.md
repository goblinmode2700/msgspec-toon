## 1. Reproduce and cover

- [x] 1.1 Reproduce the distinct-key curve with the ten-worker mean.
- [x] 1.2 Add fixed-width payloads with exact distinct-key counts.
- [x] 1.3 Add guard points with key counts in the tens and hundreds.
- [x] 1.4 Require both guard points in generated release evidence.

## 2. Repair

- [x] 2.1 Split address-identity and byte-content key caches.
- [x] 2.2 Remove cache iteration from the ordinary key lookup.
- [x] 2.3 State the decoder-local unbounded cache lifetime.
- [x] 2.4 Preserve tabular, nested-record, and irregular decode performance.

## 3. Qualify

- [x] 3.1 Run `make check`, corpus, G2, G3, and G5.
- [x] 3.2 Run the complete guard against public `v0.3.0b2`.
- [x] 3.3 Generate revision-bound release evidence with the distinct-key curve.
- [x] 3.4 Set the package version and release notes to `0.3.0b3`.
- [ ] 3.5 Prepare release artifacts only after all gates pass.
