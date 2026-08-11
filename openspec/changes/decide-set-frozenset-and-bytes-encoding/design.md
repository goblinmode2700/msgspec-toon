## Context

The `0.3.0b1` encoder program creates one render decision for each container. This follow-up uses
that decision point to evaluate set-like values and bytes.

## Goals / Non-Goals

**Goals:**

- Give `set`, `frozenset`, and `bytes` one documented and executable policy each.
- Preserve canonical output and the existing direct encoder path.
- Implement support only when the wire representation is stable.

**Non-Goals:**

- Do not call `msgspec.to_builtins` inside the encoder.
- Do not emit process-dependent order under a canonical profile.
- Do not change existing scalar or sequence bytes.

## Decisions

### 1. Evaluate bytes as a native scalar

The bytes candidate will use the same base64 value as `msgspec==0.21.1`. The encoder will write
that text through the existing TOON string rules. It will not build an intermediate Python string.

### 2. Require a canonical ruling for set-like values

Native support requires a deterministic element order that works for every supported element
type. If no conformant order exists, the encoder will reject the value and name a list projection.

Matching the current process iteration order is not sufficient because canonical bytes must be
stable across processes.

### 3. Evaluate this change after encoder decision consolidation

The `0.3.0b1` encoder checkpoints will rerun issue 09. A type can enter that release only through a
separate byte-locked and measured checkpoint.

## Risks / Trade-offs

- **Risk: base64 work adds an allocation.** → Measure direct Rust encoding against the supported
  projection path and preserve exact msgspec bytes.
- **Risk: set sorting changes value semantics or rejects mixed types.** → Reject native set support
  unless one total canonical order is specified.
- **Risk: a new sequence view changes existing output.** → Run corpus, byte locks, and token locks.
