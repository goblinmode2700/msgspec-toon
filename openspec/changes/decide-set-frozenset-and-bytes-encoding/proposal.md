## Why

The encoder rejects `set`, `frozenset`, and `bytes`, although msgspec projects them into supported
wire values. The support matrix and README do not state this boundary.

## What Changes

- Decide native encoding or deliberate refusal for each type.
- Evaluate `bytes` as msgspec-compatible base64 text.
- Evaluate set-like values against the canonical-output requirement.
- Give a supported projection route for each refusal.
- Preserve canonical bytes for all existing values.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `toon-encoding`: set-like values and bytes must have an explicit canonical policy.
- `public-api`: any refusal must name a supported conversion route without payload text.
- `distribution-quality`: executable evidence must cover all three native value families.

## Impact

This change can affect native scalar classification, sequence views, error guidance, support
evidence, and README guidance. It adds no runtime dependency.
