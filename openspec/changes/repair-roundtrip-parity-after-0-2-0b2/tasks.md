## 1. Reproduce and Track

- [x] 1.1 Reproduce all five post-release reports against `0.2.0b2`.
- [x] 1.2 Create credited GitHub issues and close the already-resolved JSON benchmark report.
- [x] 1.3 Confirm the official corpus ruling for whole floats and negative zero.

## 2. Struct Encode Parity

- [x] 2.1 Retain `tag`, `tag_field`, and `array_like` in the cached Rust encode plan.
- [x] 2.2 Emit object tags, positional array-like Structs, and tagged tabular rows directly.
- [x] 2.3 Add root, nested, custom-tag-field, and tabular round-trip tests.

## 3. Native Scalar Typed Decode

- [x] 3.1 Lower all eight inspected native scalar families to a distinct plan kind.
- [x] 3.2 Compose public msgspec scalar conversion with user `dec_hook` without enabling arbitrary
  unsupported annotations.
- [x] 3.3 Convert invalid native scalars to payload-safe coordinate-bearing validation faults.
- [x] 3.4 Prove a Struct containing native scalars retains the G2 zero-intermediate-tree invariant.

## 4. Executable Evidence and Documentation

- [x] 4.1 Add mandatory round-trip probes to every supported value-shape matrix entry.
- [x] 4.2 Split the eight native scalar families and integer/float behavior into explicit entries.
- [x] 4.3 Publish round-trip state and a fixture-required format-divergence status in report data.
- [x] 4.4 Document native typed decode and canonical whole-float behavior in the README.
- [x] 4.5 Update release-report assertions and regenerate checked-in evidence.

## 5. Gates and Issue Resolution

- [x] 5.1 Run focused tests, OpenSpec validation, `make check`, the official corpus, and G2/G3/G5.
- [x] 5.2 Update `LAST-MILE.md`, `HANDOFF.md`, and release notes with measured results.
- [ ] 5.3 Post evidence to GitHub issues, close resolved issues, and leave the branch ready for review.
