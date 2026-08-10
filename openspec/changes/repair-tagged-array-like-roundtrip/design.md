## Context

The encoder correctly emits a tagged array-like Struct as `[tag, field0, ...]`. The decoder's
positional frame currently interprets element zero as `field0`. A zero-field Struct therefore
reaches an impossible placement state, a one-field string Struct silently treats its tag as the
field, and longer values exhaust the field plan and return `internal error`. Python plan lowering
also rejects any union containing an array-like Struct.

msgspec 0.21.1 provides the direct prior art in `src/msgspec/_core.c`. Its type collector permits
tagged Struct unions only when every member has the same `array_like` status and builds a tag
lookup. Its JSON and MessagePack decoders consume array element zero to validate a concrete tag or
select a union member, then enter the shared field decoder with positional index one.

## Goals / Non-Goals

**Goals:**

- Port msgspec's discriminator-prelude state transition into the existing typed consumer.
- Preserve direct public-constructor Struct construction and G2.
- Make feature interactions executable release evidence.
- Remove the generic internal fault from every malformed tagged positional path.

**Non-Goals:**

- Change encoder bytes, add a second parser, or use msgspec private layouts.
- Quote rejected payload values in errors.
- Reopen the general performance loop.

## Decisions

1. **Represent the unresolved union as a typed frame.** `ArrayStructUnion` holds only compiled plan
   IDs. Its first scalar is converted once, compared with constant plan tags, and replaces the
   frame with the selected `ArrayStruct`. It builds no list or dictionary.
2. **Represent concrete tag validation as frame state.** `tag_pending` makes the first scalar a
   discriminator rather than a declared field. After equality succeeds, ordinary field placement
   is unchanged.
3. **Match scalar category before tag equality.** String tokens can select string tags and integer
   tokens can select exact integer tags. Boolean and floating tokens cannot select integer tags,
   even though Python equality treats `True`, `1.0`, and `1` as equal. This ports msgspec's typed
   tag lookup rather than Python's generic equality semantics.
4. **Allow only same-shape unions.** The inspection membrane accepts all-object or all-array-like
   tagged Struct unions, and continues to reject a mix, mirroring msgspec's rule.
5. **Fail impossible positional states as type mismatches.** Missing tags, unknown tags, container
   tags, and extra values are caller validation failures. They do not expose `internal error`.
6. **Publish the tested feature-pair cross-product.** The ten reported interactions become named
   support rows. This is bounded evidence, not an attempt to generate an unlimited combinatorial
   matrix.

## Risks / Trade-offs

- **One tag comparison before field decode** is required by the wire shape and matches msgspec.
- **Union selection scans a small compiled member list.** The existing object-form path does the
  same. No cache or new dependency is justified without measured evidence.
- **More matrix rows change compatibility counts.** The report should show these as supported
  evidence additions, not API additions.

## Migration Plan

Ship as the next beta patch serial after the full correctness, allocation, timing, distribution,
and trusted-publication gates. Earlier canonical documents remain valid.
