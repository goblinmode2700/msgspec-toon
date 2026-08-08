# Changelog

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
