# Changelog

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
