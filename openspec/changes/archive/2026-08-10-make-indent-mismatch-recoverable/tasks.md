## 1. Reproduce and Track

- [x] 1.1 Preserve the complete outside-agent round-three feedback and token measurements.
- [x] 1.2 Open credited GitHub issue 7 with the nested and tabular reproductions.
- [x] 1.3 Add failing width-matrix tests and explicit mismatch controls.

## 2. Adjudicate and Repair

- [x] 2.1 Implement and test one-pass automatic inference without a copy or retry.
- [x] 2.2 Reject inference after the exact-source typed-decode A/B regression reproduces.
- [x] 2.3 Report the first content column and observed leading-space count on the existing
  invalid-indentation error path.
- [x] 2.4 Preserve matching-width behavior across typed/untyped and functional/reusable decode.

## 3. Documentation and Evidence

- [x] 3.1 Document the matching-width contract, indent=1 token trade-off, and UTF-8 BOM acceptance.
- [x] 3.2 Preserve official fixture behavior, payload safety, and the focused rejected-candidate
  measurements.
- [x] 3.3 Sync the authoritative specs and regenerate support/report evidence.

## 4. Gates and Release

- [x] 4.1 Run focused tests, strict OpenSpec validation, `make check`, corpus, G2, and efficiency
  lock.
- [x] 4.2 Run only relevant same-session decode timing and confirm the adopted error-only repair is
  neutral.
- [x] 4.3 Update HANDOFF, LAST-MILE, and GitHub issue 7 with evidence; archive and commit the change.
- [x] 4.4 Export and qualify the next beta without publication.
- [x] 4.5 Publish under existing owner authority only after qualification passes; verify PyPI files,
  attestations, GitHub release evidence, and fresh installs before closing issue 7.
