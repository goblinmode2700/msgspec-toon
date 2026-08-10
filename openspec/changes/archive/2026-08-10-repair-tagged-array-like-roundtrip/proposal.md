## Why

An outside-agent feature-pair review found that `0.2.0b3` encodes a Struct configured with both
`tag` and `array_like`, but typed decode cannot read those bytes back. A concrete type can return
the generic `internal error`, and a union of tagged array-like variants is rejected during plan
construction. The support matrix tested the two features separately, so both appeared supported.

## What Changes

- Decode the first positional element as a discriminator for a concrete tagged array-like Struct.
- Select the compiled Struct plan from that discriminator for a union whose members are all tagged
  and array-like, matching msgspec 0.21.1.
- Turn saturated or malformed positional states into payload-safe validation errors, never the
  internal-fault contract.
- Add all ten outside-agent supported feature pairs as executable matrix rows with round trips.
- Document the combined behavior and regenerate compatibility evidence.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `typed-codec`: tagged positional Structs and same-shape tagged unions must decode directly.
- `distribution-quality`: supported feature interactions must carry executable round-trip evidence.

## Impact

The change modifies the Python union-plan rule, the Rust typed positional frame, focused tests,
support evidence, and documentation. It changes no canonical encoder bytes, public signature, or
runtime dependency.
