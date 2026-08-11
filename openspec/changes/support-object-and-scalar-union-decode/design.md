## Context

The `0.3.0b1` control program adds explicit plan selection. This follow-up uses that boundary as
an observation point. It does not assume that the new architecture makes every union safe.

## Goals / Non-Goals

**Goals:**

- Decide `object`, scalar unions, and containers of those annotations with executable evidence.
- Implement a direct path only when it preserves zero-tree decode and deterministic selection.
- Give a useful plan error for every remaining refusal.

**Non-Goals:**

- Do not add a generic Python tree followed by `msgspec.convert`.
- Do not guess between union members after lossy coercion.
- Do not claim support from plan construction alone.

## Decisions

### 1. Evaluate this change after local container selection

The `0.3.0b1` interaction matrix will rerun issue 08 after the selection checkpoint. If the new
state model closes the gap directly, implementation can enter that release as a separate
checkpoint.

### 2. Treat `object` as an open-value policy decision

The first candidate will reuse the `Any` event path only if `msgspec.json` gives the same accepted
values and normalized Python types. G2 will distinguish requested final containers from an
unrequested intermediate tree.

### 3. Select scalar unions by token category before conversion

A supported scalar union will use the parser token category and compiled members. It will not try
each Python conversion until one succeeds. Ambiguous coercion remains unsupported unless the
pinned msgspec behavior defines one result.

## Checkpoint result

The complete issue table failed before this checkpoint and passes after it. `object` lowers to the
existing open-value plan. Built-in containers on that path are requested output, so they do not
violate G2. Primitive scalar unions compile only for bool, int, float, str, and None. Rust tries an
exact token category before a widening conversion. Thus, `float | int` decodes an integer token as
an int, while `float | str` can widen an integer token to float because no int member exists.

The remaining unsupported-union rules do not change. Mixed object/scalar unions and untagged
container unions still fail during plan construction. They require a wire-form selection policy
that this checkpoint does not guess.

## Risks / Trade-offs

- **Risk: `object` changes the meaning of the G2 count.** → Mark requested open-value containers as
  final output and keep wrapper intermediates distinct.
- **Risk: scalar selection disagrees in non-strict mode.** → Differential-test strict and
  non-strict behavior before support.
- **Risk: more union branches slow the common path.** → Keep the path behind a compiled union kind
  and run focused same-session A/B.
