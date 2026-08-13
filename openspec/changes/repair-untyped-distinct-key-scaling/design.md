## Context

The untyped consumer has two key identities.
Tabular fields repeat one borrowed header slice at one address.
Ordinary records repeat equal key bytes at different input addresses.
The `0.3.0b2` cache stores both identities in one enum-keyed `FxHashMap`.
The ordinary path cannot use borrowed byte lookup on that enum.
It scans the complete map instead.

The ten-worker reproduction uses 4,096 two-field records.
It keeps the document size fixed at 117,681 bytes.
The benchmark varies the exact global key count from 4 through 1,024.

## Decisions

### 1. Split the cache by lookup identity

The tabular cache uses an address-and-length key.
The ordinary cache uses `FxHashMap<Vec<u8>, Py<PyString>>`.
`Vec<u8>` supports lookup through a borrowed `[u8]` value.
Therefore, an ordinary cache hit does not allocate or scan the cache.

This design adds no dependency and no process-global state.
The content cache remains unbounded inside one decode call.
The consumer releases the complete cache when that call ends.

### 2. Defer the direct-mapped cache

msgspec uses a 512-slot direct-mapped string cache.
orjson uses a 2,048-entry associative cache.
Both designs bound memory and avoid a map scan.

The `0.3.0b3` change ports the lookup pattern, not the complete cache design.
A direct-mapped cache changes collision, replacement, and free-threaded behavior.
That larger change requires a separate measurement and review.

### 3. Make key cardinality a release factor

The scaling benchmark uses fixed-width key names.
All cells contain the same record count, value data, and encoded byte count.
The permanent guard includes 32-key and 512-key cells.
The generated report contains the complete 4-to-1,024-key curve.

## Falsifier

Reject the repair if a cache lookup still scans cached entries.
Reject the repair if either new guard point becomes slower than `0.3.0b2`.
Reject the repair if any protected shape has a reproduced slowdown.
