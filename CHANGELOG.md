# Changelog

## 0.2.0b2

Benchmark visualization.

- Add an empirical speed-token Pareto figure for numeric-heavy and uniform payloads.
- Distinguish workload scaling trajectories from Pareto membership.
- Show how msgspec-toon displaces or expands the previously attainable codec set.
- Use the Pareto figure as the public README and PyPI benchmark summary.
- Preserve codec behavior, support status, and canonical TOON bytes from `0.2.0b1`.

## 0.2.0b1

Native scalar encoding and msgspec API parity.

<!-- release-compatibility:start -->
- Compatibility since `0.1.0b3`: 7 newly supported, 0 removed, 7 total support-status changes, and 0 shared canonical-wire changes.
<!-- release-compatibility:end -->

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
