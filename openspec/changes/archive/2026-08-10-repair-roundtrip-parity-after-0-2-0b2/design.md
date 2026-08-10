## Context

See `proposal.md` for motivation. The plan IR already carries Struct tags and `array_like`, but the
Rust encode plan discards them. Native scalar encoding already uses msgspec 0.21.1 normalization;
typed planning rejects the same inspected type families. The parser/consumer boundary, inspection
membrane, stable ABI, zero-container-tree invariant, and canonical fixture bytes remain fixed.

## Goals / Non-Goals

**Goals:**

- Reuse existing plan metadata in both encode shapes and typed scalar dispatch.
- Preserve direct Struct field reads and scalar-only conversion.
- Make the matrix reject future one-direction support claims.

**Non-Goals:**

- Add arbitrary custom-type support, private msgspec layout access, or a second parser.
- Change TOON canonical float spellings to match JSON.
- Open a general performance round; focused correctness checks and existing gates are sufficient.

## Decisions

1. **Port msgspec's Struct shape semantics into the cached Rust encode plan.** Object tags become a
   constant first field; array-like Structs dispatch through the sequence writer; tagged tabular
   rows add a constant discriminator column. This retains direct reads. Calling `to_builtins` was
   rejected because it violates the encoder invariant.
2. **Represent known native types as a distinct `native_scalar` plan kind.** The inspection
   membrane recognizes only msgspec's published inspected type classes. Rust converts the parser
   token to one scalar Python object and calls a composed internal hook backed by public
   `msgspec.convert`. Reusing arbitrary `custom` would make built-in support depend on a user hook
   and would blur payload-safe error handling.
3. **Discard native conversion exception text at the Rust boundary.** Conversion failure becomes
   the codec's static coordinate-bearing type-mismatch fault. User `dec_hook` errors retain their
   existing behavior on the separate custom plan path.
4. **Make round trip an executable property of each supported matrix entry.** The report publishes
   `verified` or `not_applicable`; it does not infer bidirectional support from separate probes.
5. **Classify whole floats as a declared format divergence.** Official fixtures require the current
   bytes, so documentation and a dedicated matrix status are the correct repair.

## Risks / Trade-offs

- **Scalar conversion crosses Rust/Python once per native value** → Keep it off primitive plans and
  use msgspec's public converter for correctness; measure only if it becomes a demonstrated hot
  path.
- **Tagged constants participate in shape discovery** → Store them in the cached plan and reuse
  one pinned object instead of allocating per row.
- **Matrix feature names change release deltas** → Update locked report tests and describe the split
  in release notes rather than preserving a misleading aggregate row.

## Migration Plan

Ship as the next beta patch/minor prerelease after full conformance, allocation, and distribution
gates. Rollback is the prior beta; no stored canonical document becomes invalid.
