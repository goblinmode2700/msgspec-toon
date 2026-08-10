## Why

`0.1.0b2` proves source conformance and broad wheel availability, but it does not yet
prove that every published artifact passed the complete qualification suite, and it still
publishes with a long-lived credential. Known typed and public-API gaps also need stable,
intentional behavior before the codec can expand beyond its current support tiers.

This change converts the post-beta-2 maintainer feedback into two release checkpoints. A
patch beta establishes release trust first; a minor beta then adds backward-compatible
msgspec scalar and typed-decoder capabilities without weakening TOON conformance, direct
typed construction, containment, payload-safe errors, or measured performance gates.

## What Changes

- Ship `0.1.0b3` as the release-trust checkpoint:
  - define one canonical validation gate for pull requests, the default branch, and releases;
  - build artifacts once, verify the installed wheel or source distribution in clean
    uv-managed environments, and publish only that verified artifact set;
  - replace the long-lived PyPI token with Trusted Publishing through a protected GitHub
    environment and the official PyPA action, with default publish attestations;
  - generate a version- and revision-bound release evidence report from the canonical checks.
- Ship `0.2.0b1` as the backward-compatible capability checkpoint:
  - encode the documented msgspec-native date/time, UUID, Decimal, and Enum scalar set before
    consulting `enc_hook`;
  - make unsupported typed annotations fail with one stable package exception and a
    schema-derived type path, never `RecursionError` or another implementation detail;
  - add tagged unions, `array_like` Structs, recursive plans, `strict=False` conversion, and a
    deliberate policy for non-string mapping keys through the existing plan IR;
  - derive functional and reusable codec options from one option model, expose `float_hook`
    consistently, and ensure no accepted option is ignored;
  - add native parser and round-trip fuzz targets, short pull-request smoke runs, scheduled
    sustained runs, corpus seeding, and retained failure artifacts.
- Preserve canonical TOON 4.1 bytes for already supported values. Any newly supported scalar
  representation is a new-input capability and is documented as wire API before release.
- Keep the exact `msgspec==0.21.1` runtime pin and all constraints C1-C9.
- No breaking changes are planned. If implementation discovers that an existing accepted
  value must change bytes or meaning, stop and amend this proposal before proceeding.

## Capabilities

### New Capabilities

- `release-qualification`: Canonical validation, installed-artifact verification, verified
  artifact promotion, Trusted Publishing, attestations, and generated release evidence.
- `native-fuzzing`: Parser, encode/decode round-trip, corpus-seeded, and scheduled native fuzz
  qualification with retained regressions.

### Modified Capabilities

- `toon-encoding`: Define canonical wire representations and hook precedence for the supported
  msgspec-native scalar set.
- `typed-codec`: Replace accidental typed failures with a stable contract and extend support
  through plan data for tagged unions, array-like and recursive Structs, permissive conversion,
  and mapping-key policy.
- `public-api`: Unify function and reusable-object option behavior, including `float_hook`,
  ordering, and scalar-format options, with no accepted-but-inert parameters.
- `distribution-quality`: Require release-level compatibility and evidence outputs to be
  generated from canonical checks and attached to the release.

## Impact

- Workflows: `.github/workflows/` gains canonical validation, artifact verification, fuzzing,
  and protected publication stages; the existing wheel workflow is decomposed rather than
  copied.
- Tooling and evidence: `Makefile`, `scripts/release-report.py`, `conformance/report.json`, the
  executable support matrix, and release assets gain installed-artifact and compatibility data.
- Python API and plan membrane: `python/msgspec_toon/__init__.py`, `_plan.py`, and `_types.py`
  gain shared option and type-plan data without adding decode-call-site type ladders.
- Native codec: Rust plan, typed consumer, encoder, scalar, and fuzz-target code gain the
  declared scalar and typed behaviors while retaining the parser/Python boundary.
- Dependencies: production remains `msgspec==0.21.1` only. CI adds pinned build/fuzz actions and
  tools; release authentication removes the repository's need for `PYPI_API_KEY`.
- Versioning: `0.1.0b3` contains trust and evidence work; `0.2.0b1` contains new public codec
  capabilities. Internal optimization checkpoint tags do not determine the public package
  version.
