# Changelog

## Unreleased

## 0.3.0b3

Untyped distinct-key scaling hotfix.

- Replace the ordinary-record cache scan with average O(1) hash lookup by key bytes.
- Keep separate decoder-local caches for borrowed address identity and owned key content.
- Add fixed-size key-cardinality evidence from 4 through 1,024 distinct keys.
- Add permanent 32-key and 512-key release-guard cells.
- Improve 4,096-record decode by 36.8% at 32 keys and 87.9% at 512 keys against `0.3.0b2`.
- Keep nested and irregular untyped decode neutral against `0.3.0b2`.
- State that the content cache is unbounded only for one decode call.
- Preserve canonical bytes, token counts, conformance, G2, G3, and G5.

## 0.3.0b2

Untyped nested-record performance hotfix.

- Add nested mixed records and irregular records to the permanent release guard.
- Reuse Python key strings across nested ordinary objects without caching unique root-entry keys.
- Remove the nested-record regression: 46 records are neutral at -1.1% with a 2.1% MDE in the complete guard.
- Improve untyped decode by 9.0% on 4,096 irregular records against `0.3.0b1` in the complete guard.
- Correct the `0.3.0b1` untyped speed claim: its 2-8% gain described only uniform tabular records.
- Preserve canonical bytes, token counts, conformance, G2, G3, and G5.

## 0.3.0b1

Typed correctness, explicit state, and localized hot paths.

<!-- release-compatibility:start -->
- Compatibility since `0.1.0b3`: 27 newly supported, 1 removed, 30 total support-status changes, and 0 shared canonical-wire changes.
<!-- release-compatibility:end -->

- Report the observed leading-space count when decode receives the wrong `indent_size`.
- Keep the specification default of two and require producer/consumer widths to agree.
- Round-trip nested mappings, tables, and typed Structs at widths 1, 2, and 4 when configured.
- Document UTF-8 BOM and CRLF input acceptance.
- Preserve canonical bytes, token counts, G2, and official explicit-width fixture behavior.
- Validate concrete tags and select tagged-union members inside nested field groups.
- Decode `object` through the requested open-value path.
- Decode unions of bool, int, float, and str with msgspec-compatible category priority.
- Pin the performance guard to the preceding public release instead of internal milestone tags.
- Replace implicit typed-plan sentinels with checked `PlanId` and explicit field actions.
- Validate unknown subtrees with the shared grammar without building Python containers.
- Add schema-known paths to typed validation errors without exposing payload values.
- Document and test every native unsafe boundary, including the optional free-threaded capsule path.
- Improve entry decode by 9-24%, keyed decode by 9-11%, entry encode by 11-15%, and untyped decode by 2-8% against `v0.2.0b5` in the complete release guard.
- Keep canonical TOON bytes, token counts, G2, G3, and G5 unchanged or passing.

## 0.2.0b4

Tagged positional decode parity and feature-interaction evidence.

- Decode tagged array-like Structs by concrete type and tagged union.
- Validate or select the positional discriminator before declared field construction.
- Convert malformed or exhausted tagged positional states to public validation errors.
- Add executable round trips for all ten feature pairs from the outside-agent review.
- Preserve canonical bytes, token counts, G2, and the public-constructor boundary.

## 0.2.0b3

Round-trip parity and executable support evidence.

<!-- release-compatibility:start -->
- Compatibility since `0.1.0b3`: 15 newly supported, 1 removed, 18 total support-status changes, and 0 shared canonical-wire changes.
<!-- release-compatibility:end -->

- Encode tagged Struct discriminators and array-like Structs from msgspec metadata.
- Decode datetime, date, time, timedelta, UUID, Decimal, string Enum, and integer Enum values.
- Require a value round trip for each supported value-shape entry in the support matrix.
- Split integer, fractional-float, and whole-float behavior in generated evidence.
- Document the TOON 4.1 rules that encode `1.0` as `1` and `-0.0` as `0`.

## 0.2.0b2

Benchmark visualization.

- Add an empirical speed-token Pareto figure for numeric-heavy and uniform payloads.
- Distinguish workload scaling trajectories from Pareto membership.
- Show how msgspec-toon displaces or expands the previously attainable codec set.
- Use the Pareto figure as the public README and PyPI benchmark summary.
- Preserve codec behavior, support status, and canonical TOON bytes from `0.2.0b1`.

## 0.2.0b1

Native scalar encoding and msgspec API parity.

- Compatibility since `0.1.0b3`: 7 newly supported, 0 removed, 7 total support-status changes, and 0 shared canonical-wire changes.

- Encode date, datetime, time, timedelta, UUID, Decimal, and Enum values before `enc_hook`.
- Support exact Decimal number output and UUID hex output in both encoder entry points.
- Preserve all locked canonical bytes shared with `0.1.0b3`.
- Decode self-recursive and mutually recursive Structs through bounded graph plans.
- Decode array-like Structs through positional frames.
- Select tagged Struct union variants before direct construction.
- Match msgspec 0.21.1 permissive bool, integer, and float scalar conversion.

## 0.1.0b3

Release qualification and provenance.

- Compatibility since `0.1.0b2`: no support changes and no canonical-wire changes for shared locked payloads.

- Run one canonical validation gate for pull requests, the default branch, and releases.
- Build distributions once, verify installed artifacts on their target runners, and publish only
  the digest-matched verified set.
- Build the source distribution in a clean uv-managed environment before release.
- Use PyPI Trusted Publishing with short-lived GitHub OIDC credentials and default attestations.
- Generate version- and revision-bound release evidence from canonical checks and artifact
  manifests.
- Preserve codec behavior and canonical TOON bytes from beta 2.

## 0.1.0b2

Release and documentation polish.

- Fix PyPI links to benchmark, conformance, and license files.
- Explain TOON and msgspec before the usage guide.
- Publish wheels for Linux, macOS, and Windows on x86-64 and ARM64.
- Publish CPython 3.14 free-threaded wheels alongside the CPython 3.13 ABI3 wheels.

## 0.1.0b1

First public beta.

- Pass all 538 pinned TOON 4.1.1 corpus fixtures.
- Decode directly into `msgspec.Struct` values without an intermediate tree.
- Encode Struct fields without `msgspec.to_builtins`.
- Publish same-run speed, token, allocation, and conformance evidence.
- Provide an isolated build for the proposed msgspec Struct-access capsule.

## Unpublished alpha work

The local development tags before this beta recorded proof-of-concept,
conformance, hardening, and optimization checkpoints. They were not public
package releases and are not part of the public tag history.
