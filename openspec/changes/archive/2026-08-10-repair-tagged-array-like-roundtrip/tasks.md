## 1. Reproduce and Track

- [x] 1.1 Preserve the complete outside-agent issue and token-shape feedback internally.
- [x] 1.2 Open credited GitHub issue 6 with the concrete and union reproduction.
- [x] 1.3 Add failing tests for zero-field, concrete, string-union, integer-union, and malformed
  tagged positional inputs.

## 2. Port msgspec Positional Tag Semantics

- [x] 2.1 Inspect msgspec 0.21.1 C type collection and JSON/MessagePack array decoders.
- [x] 2.2 Permit tagged unions only when every Struct member has the same array-like shape.
- [x] 2.3 Validate a concrete positional discriminator before declared fields.
- [x] 2.4 Select an array-like union member from the first scalar without a built-in tree.
- [x] 2.5 Convert exhausted and malformed positional states from internal faults to validation
  faults.

## 3. Interaction Evidence and Documentation

- [x] 3.1 Add the ten reported supported feature pairs as executable round-trip matrix rows.
- [x] 3.2 Extend the independent G2 probe with tagged array-like union decode.
- [x] 3.3 Document concrete and union tagged array-like behavior in README.
- [x] 3.4 Sync the authoritative specs and regenerate compatibility evidence.

## 4. Gates and Release

- [x] 4.1 Run focused tests, OpenSpec strict validation, `make check`, corpus, and G2.
- [x] 4.2 Run same-session relevant encode/decode timing and confirm canonical token/byte locks.
- [x] 4.3 Update the handoff, last-mile ledger, and GitHub issue with evidence.
- [x] 4.4 Export the public repair and qualify the next beta without publication.
- [x] 4.5 Publish only after the qualified artifact set passes and owner authority remains valid.
