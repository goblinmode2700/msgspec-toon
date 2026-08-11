## Why

Typed decode accepts `Any` and optional unions, but it rejects `object` and non-optional scalar
unions during plan construction. The support matrix and README do not state this boundary.

## What Changes

- Compare `object` and scalar-union behavior with `msgspec==0.21.1`.
- Implement direct typed decode if the plan-selection architecture gives a bounded path.
- Otherwise, declare each refusal and name the supported replacement.
- Cover nested containers that contain these annotations.
- Preserve zero-tree typed decode and all performance floors.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `typed-codec`: `object` and non-optional scalar-union policy must be executable and explicit.
- `distribution-quality`: the support matrix must cover these annotation families and containers.

## Impact

This change can affect plan lowering, scalar selection, union state, matrix evidence, and README
guidance. It changes no wire bytes or runtime dependency.
