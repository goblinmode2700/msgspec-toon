# Prior art: native codec extension and hot paths

## Pattern

This is a native typed-codec extension problem with two narrower patterns: cached schema
compilation for functional calls, and scan-specialized text parsing/encoding.

## Sources surveyed

- `msgspec` 0.21.1 (`10c9ac4`), especially `src/msgspec/_core.c`: functional JSON calls
  create native per-call state directly. Typed Struct decode reuses `StructInfo` attached to
  the Struct type; `Any` uses a stack type node. Reusable `Encoder` and `Decoder` objects are
  a separate API. Struct-union lookup caching is capped at 64 entries.
- `msgspec-ext` 0.5.1 (`587065b`), especially `settings.py`: builds on public
  `msgspec.Struct`, `Meta`, hooks, `defstruct`, and reusable JSON codecs. Its many unbounded
  class dictionaries, duplicated encoder/decoder maps, and dict-to-JSON-to-Struct bridge are
  not patterns to port into a codec.
- `serde` (`747814f`), especially `serde_core/src/de/mod.rs`: separates format traversal
  from typed construction through `Deserializer`, `Visitor`, `SeqAccess`, and `MapAccess`.
  This validates the existing parser-to-`Consumer` boundary; adopting Serde cannot construct
  Python `msgspec.Struct` objects without a second adapter and ownership model.
- `jaq` (`6e82c3c`), especially `jaq-core/src/val.rs`: its query engine is generic over an
  owned `ValT`, but queries require a value tree. It is useful for a future query product,
  not for this codec's G2 path.
- `toonq` (`b481d69`) and its `serde_toon_format` dependency (`9a8911c`): `toonq` converts
  TOON to `serde_json::Value`, then to `jaq_json::Val`, so it cannot enter the typed codec
  path. The underlying v3.0 codec cannot replace this v4.1 corpus-complete parser, but its
  first-byte string specialization, combined delimiter/quote scans, and precomputed field
  slots independently match candidates E8, D7, and E9.
- CPython 3.13 `json` and `functools`: default codec-object reuse and bounded thread-safe LRU
  are mature patterns, but caching whole codec wrappers is weaker than msgspec's native
  compiled-schema pattern for this extension.

## Verdict

**Port**, do not adopt a codec or query engine.

Take msgspec's split between native functional entry points, local per-call state, and cached
compiled Struct metadata. Keep the existing 512-entry Python annotation cache as the
retention boundary and cache an opaque native compiled plan behind it. Separately port the
three scan/data-layout ideas from `serde_toon_format`, one measured checkpoint at a time.

Reject wrapper-object caches, unbounded global class maps, Serde/jaq value trees, the v3.0
wire implementation, new subprocesses, and any dependency that moves inspection outside
`_plan.py` or compromises G2.
