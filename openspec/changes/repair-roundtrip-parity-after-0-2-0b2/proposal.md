## Why

Post-release deployment probes found two asymmetric features: the decoder accepted tagged and
array-like Structs that the encoder could not emit, and the encoder emitted eight msgspec-native
scalar families that typed decode rejected. The executable support matrix tested each direction
separately, so it published these half-features as supported.

## What Changes

- Encode Struct tags, custom tag fields, and array-like Structs from the existing compiled plan.
- Decode datetime, date, time, timedelta, UUID, Decimal, Enum, and IntEnum scalar annotations
  through msgspec's public scalar conversion semantics without building an intermediate container
  tree.
- Require a passing value round trip for every supported value-shape entry in the executable
  support matrix, and publish that result in generated evidence.
- Split integer, fractional-float, and TOON-canonical whole-float behavior in the matrix. Document
  the fixture-required `1.0 -> 1` and `-0.0 -> 0` rule instead of changing canonical bytes.
- Retain payload-safe errors, byte-exact TOON 4.1 conformance, G2, and the existing public API.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `toon-encoding`: Struct metadata must affect emitted object, sequence, and tabular shapes; the
  canonical whole-float rule must be explicit.
- `typed-codec`: The encoder-supported native scalar set must decode directly, and supported
  value shapes must carry executable round-trip evidence.
- `distribution-quality`: Generated compatibility evidence must report round-trip verification
  separately from one-direction decode probes.

## Impact

The change modifies the Python inspection membrane and decode-hook composition, Rust encode plans
and typed scalar dispatch, executable conformance evidence, tests, and user documentation. It adds
no runtime dependency and changes no public function signature or canonical corpus byte.
