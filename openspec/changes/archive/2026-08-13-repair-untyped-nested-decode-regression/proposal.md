# Repair untyped nested decode regression

## Why

The `0.3.0b1` release guard measured untyped decode only on uniform tabular
records. An outside report found that ordinary nested and irregular payloads
became slower than `0.2.0b5`, while tabular payloads became faster. The release
claim therefore described one shape as if it described the complete surface.

## What changes

- Add fixed release-guard points for a 46-record nested mixed payload and a
  4,096-entry irregular payload.
- Repair repeated-key handling on ordinary object paths without losing the
  adopted tabular or unique-entry improvements.
- Publish each untyped shape result and disclose every covered losing shape.

## Impact

This is a speed-only hotfix. Canonical bytes, typed semantics, TOON 4.1
conformance, G2, G3, G5, and payload-safe errors remain protected gates.
