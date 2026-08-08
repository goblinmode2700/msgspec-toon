# G4 upstream Struct-view proof

Date: 2026-08-08  
msgspec source: `10c9ac4` (`0.21.1`)  
msgspec-toon source: `3c710d0` (`v0.4.0` plus E9)

## Question

Can an upstream msgspec integration remove the fixed cost that keeps the direct TOON
encoder behind `msgspec.to_builtins` at small payloads?

## Source finding

Yes, in part. msgspec's private `Struct_get_index` reads a field through the class's
`struct_offsets` array. Its MessagePack encoder, JSON encoder, `to_builtins`, `asdict`,
and `astuple` all use that path. msgspec exposes field names and one-field-at-a-time
attribute access publicly, but it exposes no C API or capsule for a zero-allocation
borrowed field view.

The current Rust encoder therefore performs one stable-ABI attribute lookup per leaf.
The rejected `msgspec.structs.astuple` experiment did reach msgspec's slot reader, but it
also paid for a Python call and tuple allocation for every narrow Struct. That experiment
did not test the slot mechanism without the bridge allocation.

## Proof

A disposable exact-source msgspec build exposed the byte offsets already used by
`Struct_get_index`. A disposable msgspec-toon worktree cached those offsets in its normal
per-class encode plan and loaded borrowed field pointers directly. It did not construct a
dict, list, or tuple tree. Raw offsets are an experiment only; they are not a shippable API.

All timings used `benches/_timing.py`: one calibrated loop count, three post-warmup samples
in each of ten independent worker processes, then the mean across workers. The ordinary
and proof builds ran in the same session against the same patched msgspec binary.

| records | public attribute reads (us) | native slots (us) | change | `to_builtins` (us) | proof G4 |
|---:|---:|---:|---:|---:|:---:|
| 4 | 0.66 | 0.55 | -16.7% | 0.33 | fail |
| 8 | 1.06 | 0.84 | -20.8% | 0.58 | fail |
| 16 | 1.88 | 1.41 | -25.0% | 1.09 | fail |
| 64 | 6.14 | 4.39 | -28.5% | 4.43 | pass |
| 512 | 48.54 | 33.71 | -30.6% | 43.76 | pass |
| 4096 | 376.32 | 266.79 | -29.1% | 447.82 | pass |

The proof changes the conclusion: private Struct access is a large slope cost, not the
whole small-payload floor. It crosses `to_builtins` by 64 records. At 16 records, 0.32 us
remains.

A second ten-worker decomposition on the slot build measured:

| records | Python wrapper | native method | root list through wrapper | root list through native | `to_builtins` |
|---:|---:|---:|---:|---:|---:|
| 4 | 0.55 | 0.52 | 0.50 | 0.45 | 0.32 |
| 8 | 0.84 | 0.82 | 0.77 | 0.74 | 0.58 |
| 16 | 1.41 | 1.39 | 1.35 | 1.35 | 1.06 |
| 64 | 4.50 | 4.48 | 4.46 | 4.43 | 4.53 |

The Python exception-translation wrapper costs about 0.02-0.03 us. Root Struct handling
costs about 0.04-0.06 us. Neither explains the residual at 16. A `SmallVec` experiment for
the eagerly collected sequence was also rejected: it moved 16 records from 1.41 to 1.40 us
and regressed 4096 from 266.79 to 293.22 us.

## Prior-art verdict

**Adopt upstream, do not copy private layout into the wheel.** The useful prior art is
msgspec itself: compiled class metadata plus borrowed slot reads. Port that access pattern
through a versioned upstream C capsule while retaining this repository's Rust parser,
TOON shape logic, writer, and one inspection membrane.

A production API must define:

- capsule name and ABI version;
- exact Struct-class validation;
- field count and field-order correspondence;
- unset-field error behavior;
- object lifetime while borrowed pointers are in use;
- CPython free-threaded synchronization semantics.

The proof used raw offsets under the GIL and therefore does not settle the last two items.
A per-field exported function is safer but may return much of the recovered cost through
FFI calls. The next proof should compare a bulk borrowed view or a class-specific offset
view supplied by a versioned capsule, not a Python tuple and not hard-coded private structs.

## Ruling

The statement “whether upstream msgspec can eliminate the gap is unmeasured” is closed.
Upstream access recovers 25-30% on the canonical Struct ladder and closes G4 from 64
records upward. It does not yet close G4 at 4, 8, or 16 records. Production remains on the
public attribute path until msgspec provides a supported ABI or the project explicitly
changes its compatibility constraint.

