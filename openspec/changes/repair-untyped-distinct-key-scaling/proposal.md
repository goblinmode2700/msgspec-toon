# Repair untyped distinct-key scaling

## Why

The `0.3.0b2` ordinary-record key cache scans all cached keys for each key occurrence.
Decode time therefore increases with the number of distinct keys in one document.
The `0.3.0b2` release guard does not vary this payload property.

## What changes

- Use average O(1) hash lookup for repeated ordinary-record keys.
- Add fixed-width payloads that vary distinct-key count without changing document size.
- Add guard points with distinct-key counts in the tens and hundreds.
- Add the complete distinct-key curve to generated release evidence.
- State the cache lifetime and bound in code and release evidence.

## Impact

This change defines the `0.3.0b3` performance hotfix.
Canonical bytes, typed semantics, TOON 4.1 conformance, G2, G3, G5, and payload-safe errors remain protected gates.
