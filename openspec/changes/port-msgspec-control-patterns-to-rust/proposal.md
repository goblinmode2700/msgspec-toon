## Why

The current codec has strong data structures but an incomplete control boundary. The parser knows
the TOON wire form, while the typed consumer knows the schema. They do not select each container
plan together.

This gap caused a C7 defect in nested field groups. The same gap also adds dispatch, allocation,
and repeated classification work across decode and encode paths.

## What Changes

- Select each typed container from its wire form and declared plan before construction.
- Keep object-tag state with the container that owns the discriminator.
- Repair concrete tagged Structs and tagged unions inside nested field groups.
- Replace raw plan and field states with typed IDs and explicit field actions.
- Add a shared-grammar structural skip for unknown typed values.
- Reduce duplicate-key ownership when focused evidence identifies an allocation cost.
- Give the encoder one render decision for each container.
- Keep Struct metadata in one encode plan for tags, renames, defaults, and `array_like` behavior.
- Document and check every unsafe boundary, including free-threaded lifetime rules.
- Add schema-known paths to typed runtime errors without payload-derived text.
- Add an executable interaction matrix across wire form, nesting position, and plan shape.
- Adopt each performance change only after a focused same-session A/B resolves its effect.
- Qualify the completed program as `0.3.0b1`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `typed-codec`: typed containers must use local plan selection and unknown-value skipping without
  an intermediate built-in tree.
- `public-api`: typed runtime errors must expose schema-known paths without payload content.
- `distribution-quality`: release evidence must cover feature interactions and each measured
  architecture checkpoint.

## Impact

The program affects the parser and consumer seam, plan IDs, typed frames, and unknown-value
handling. It also affects encoder classification, safety records, error translation, focused
benchmarks, and generated evidence. It adds no runtime dependency and changes no public codec
signature.

Canonical TOON bytes remain fixed. A performance candidate that fails its focused gate is reverted
and recorded. A correctness repair that cannot satisfy the existing floors stops the release for
an explicit owner decision.
