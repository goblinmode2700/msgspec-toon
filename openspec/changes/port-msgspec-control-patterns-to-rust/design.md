## Context

See `proposal.md` for the reason for this program. The current codec already uses a pure-Rust
parser, borrowed tokens, an immutable plan arena, explicit frames, pooled constructor slots, and
one public Struct constructor call.

The missing part is the control boundary. The parser recognizes a TOON container form, while the
typed consumer derives a plan from separate frame state. Object tags use consumer-wide pending
flags. This split caused the nested field-group tag defect.

The program also covers the remaining gaps from the source audit. These gaps include structural
skip, typed IDs, encoder decision ownership, unsafe contracts, schema paths, and selected
allocation paths.

The constraints in `OBJECTIVE.md` remain authoritative. Canonical bytes, C1 through C9, and the
existing timing estimator remain fixed.

## Goals / Non-Goals

**Goals:**

- Port the schema-directed control pattern from msgspec without copying the C object representation.
- Make the wire form and declared plan meet before each typed container opens.
- Remove invalid combinations from typed state where Rust types can express the rule.
- Use one grammar for selected values and skipped values.
- Use one encoder decision for classification, validation, and rendering.
- Measure each performance mechanism in a small checkpoint before full qualification.

**Non-Goals:**

- Do not change TOON 4.1 grammar or canonical output.
- Do not use msgspec private Struct memory layout.
- Do not add a parser framework, trait object, shared interior mutability, or runtime dependency.
- Do not add internal decode threads or a bytecode virtual machine.
- Do not combine independent mechanisms in one measured checkpoint.
- Do not claim full `msgspec.json` type parity.

## Decisions

### 1. Use an explicit wire-form and plan-selection boundary

The parser will pass a small closed wire-form value at each container boundary. The typed target
will combine that form with the declared plan. The result will identify the selected plan, a skip
action, or a validation fault.

The first implementation slice will cover nested field groups. Later slices can use the same
boundary for ordinary objects, tabular rows, keyed tabular values, and positional Structs.

The parser will remain generic and free of PyO3. The target will own all schema and Python work.
Static dispatch will remain in the scalar loop.

Alternative: add another tag-specific callback. This option is rejected because each feature pair
adds another protocol side channel.

Alternative: replace the complete `Consumer` trait in one change. This option is rejected because
it creates a large correctness and performance step without a narrow falsifier.

### 2. Keep selection state with one container

The selection result will travel directly into the frame for the selected container. Object tags
will stop using consumer-wide `pending_object_plan` and `pending_invalid_tag` state.

The nested field-group probe will use a borrowed view of the header tree and row cells. It will
scan only the cells for that field group. Then the normal decoder will consume those cells once.
The probe will not create a dictionary, list, or owned scalar tree.

Concrete tagged Structs will validate their tag before construction. Tagged unions will select a
member before construction. The selection rules will preserve msgspec scalar categories.

Alternative: recurse through the existing top-level hint callback. This option is rejected because
the callback still names the parent plan during nested preflight.

### 3. Introduce typed plan and field actions in separate checkpoints

A private `PlanId` will distinguish plan identity from field position. A closed field action will
distinguish a declared field, discriminator, skip, and rejection. The design will remove
`usize::MAX` from tag policy.

The migration will start at plan compilation and container selection. Later checkpoints will move
the remaining frame and lookup sites. Each checkpoint must compile and pass the focused semantic
tests before the next checkpoint starts.

Index width will remain `usize`. A narrower integer is a separate data-layout experiment and is
not part of this program.

### 4. Add structural skip through the shared grammar

Unknown typed values currently avoid Python construction but still dispatch all typed events. The
new path will consume unknown subtrees with parser-owned structural logic or a zero-work target.

The skip path will reuse header, indentation, quote, duplicate, row-count, and depth logic. It
will not implement a second permissive grammar. The G2 probes will include nested unknown objects,
arrays, tabular rows, and malformed unknown values.

The checkpoint will compare event dispatch and allocation before and after the change. It will
include an untyped control because parser code changes.

### 5. Measure duplicate-key ownership before changing it

Strict object parsing currently owns bytes for every key. A profile and allocation probe will
first determine whether this cost resolves on wide and repeated objects.

If the cost resolves, the candidate can use borrowed keys or stable fingerprints with exact
collision checks. Escaped and unescaped forms must compare by decoded key bytes. Strict duplicate
behavior cannot change.

If the cost does not resolve, the candidate will be rejected and recorded.

### 6. Give encoding one authoritative render decision

The encoder will produce one render decision for each container. The decision will contain the
selected object or sequence view and any shape witness that rendering needs.

Classification will validate through the same witness that rendering consumes. The encode plan
will remain the only authority for tags, renames, defaults, `array_like`, and field access.

The migration will start with one reproduced shape or profile mechanism. Root, entry, list-item,
keyed, and tabular paths will move in separate checkpoints. Canonical byte locks will run after
each checkpoint.

The rejected decode row-operation virtual machine will not return. An encoder render witness and
a decode virtual machine are different designs.

### 7. Audit unsafe code as a local contract

Each unsafe block will state the borrowed and owned references, pointer lifetime, stealing rules,
failure conversion, and free-threaded critical section where applicable.

Unchecked UTF-8 and arena access will state their local proof. If the proof cannot remain local,
the code will use a checked operation. A safe replacement that changes hot-path work will use a
focused A/B.

The optional msgspec capsule path will run on the existing CPython free-threaded target. No private
offset fallback will enter release wheels.

### 8. Add compact schema paths to runtime faults

Typed frames will derive path parts from compiled schema metadata and structural indexes. Native
faults will store compact path state only when typed decode needs it.

The public error veneer will expose the path without payload keys or values. The design will keep
path work off untyped decode. A frame-size check and focused typed A/B will protect the common path.

### Task 9.1: runtime-path baseline and candidate boundary

The exact pre-change source is `c03f042`. Its diagnostic layout remains `Frame` 56 bytes and
`TypedConsumer<false>` / `TypedConsumer<true>` 360 bytes, both aligned to 8 bytes. A runtime
`Fault` carries only code, line, optional column, and the validation bit. Public decode and
validation exceptions expose no `path`; a nested type mismatch therefore has coordinates but no
schema location.

The candidate will not add path state to `Frame` or `TypedConsumer`. On a typed validation failure
only, the still-live consumer stack will derive a prefix from compiled Struct field names and
structural sequence positions. A field-specific failure whose fused event has no live `awaiting`
slot will append its compiled field name at the fault site. Native `PathPart` values will own only
plan-derived field bytes or numeric indexes. The Python veneer will expose their safe string form
as an immutable tuple. Unknown mapping keys and scalar values are never eligible inputs.

The falsifiers are any growth in `Frame` or `TypedConsumer`, any path construction on successful
decode, any change to untyped decode, any payload sentinel in an exception attribute, or a
confirmed typed/untyped regression under the repository's same-session ten-worker estimator.

### 9. Treat mutable-buffer borrowing as a safety-gated candidate

Bytes and strings already provide borrowed source slices. Bytearray and memoryview inputs copy to
protect mutation and free-threaded lifetimes.

The candidate will proceed only with a stable-ABI buffer lifetime proof. It must hold the exporter
for the complete decode and prevent unsafe mutation races. It must pass CPython 3.13 ABI3 and the
free-threaded target.

If the proof or focused large-buffer measurement fails, the copy remains and the report records the
candidate as rejected.

### 10. Use one interaction design and one timing authority

The semantic matrix will cross these dimensions where they apply:

- wire form: ordinary object, tabular row, nested field group, keyed tabular, and positional Struct.
- plan shape: concrete Struct, tagged union, recursive position, optional value, and unknown field.
- nesting: root, row child, deeper child, sibling, and adjacent row.
- discriminator: correct, wrong, missing, duplicate, unknown, and wrong scalar category.

The focused timing matrix will use one small case and one repeated-row case. It will include the
affected typed case, an ordinary typed control, and an untyped control for parser changes.

`benches/_timing.py` remains the only timing authority. Every A/B uses the mean across ten worker
processes, the preceding release guard, raw repetitions, spread, significance, and the measured
resolution floor.

### 11. Treat issues 08 and 09 as observation gates

The interaction matrix will rerun `object` and non-optional scalar unions after local plan
selection. The encoder matrix will rerun set-like values and bytes after render consolidation.

Each family has a separate follow-up OpenSpec change. A family enters `0.3.0b1` only when an
existing mechanism closes it through a separate measured checkpoint. Otherwise, its follow-up
change remains open with executable evidence and documented refusal.

## Risks / Trade-offs

- **Risk: The selection seam grows the common frame or event size.** → Measure type sizes and the
  ordinary typed control before adoption.
- **Risk: Probe and replay scan a discriminator twice.** → Bound the probe to one container and
  reject any design that scans the selected container more than once before real decode.
- **Risk: Structural skip accepts malformed unknown data.** → Use shared grammar primitives and
  hostile differentials for every skipped container form.
- **Risk: Typed IDs create a large mechanical diff.** → Move one boundary at a time and retain
  checked conversion during migration.
- **Risk: Encoder consolidation changes canonical bytes.** → Run byte and token locks after each
  render-path checkpoint.
- **Risk: Schema paths add hot-path work.** → Derive paths from existing frames and measure frame
  size plus focused decode controls.
- **Risk: Mutable-buffer borrowing is unsafe on free-threaded Python.** → Keep the current copy
  unless the lifetime proof and target matrix pass.
- **Risk: A correct repair conflicts with a performance floor.** → Stop qualification and present
  the measured conflict to the owner. Do not publish a hidden trade.

## Migration Plan

1. Freeze `v0.2.0b5` as the release guard for this program.
2. Add the failing interaction matrix before the first source change.
3. Complete each checkpoint with its focused semantic and timing gates.
4. Revert each rejected performance candidate before the next checkpoint.
5. Run the complete repository gates after every adopted architecture checkpoint.
6. Generate the final report from one clean `0.3.0b1` candidate revision.
7. Qualify all target wheels before any publication action.

Rollback is a checkpoint revert before release. After release, a defect uses the next beta patch.

## Checkpoint 1-3 evidence

The pre-change source revision was `52c743315c3339624d2ca2b66b35340baf18fe98`. The public
release guard is `v0.2.0b5`, revision `6d12753400ce82b6719529da71fa450494e72b1d`. Internal
milestone tags are not public releases, so `benches/GUARD_TAG` is now the single offline pointer
used by the Makefile and A/B harness.

The measurement toolchain was Rust 1.93.1, cargo 1.93.1, uv 0.12.2, CPython 3.13.1, and
`msgspec==0.21.1` on Apple arm64. The release extension was rebuilt before each measurement.

Before source changes, the focused mean-across-ten-worker absolute decode times in microseconds
were:

| records | ordinary | tagged first | tagged last | nested concrete | untyped nested |
|---:|---:|---:|---:|---:|---:|
| 4 | 0.89 | 0.78 | 0.80 | 0.97 | 0.99 |
| 64 | 8.16 | 7.82 | 8.35 | 8.46 | 9.41 |
| 512 | 61.34 | 61.48 | 64.82 | 64.51 | 78.97 |
| 4096 | 575.70 | 505.86 | 534.88 | 619.44 | 705.01 |

The old nested-concrete row did not validate its discriminator. The first correct repair used
Python scalar construction and equality and was 15-27% slower. Native compiled tag metadata
reduced the cost to 7-9%. Ordinary typed, root tagged, and untyped nested controls had no
reproduced regression. All protected semantic gates passed. This cost remains open evidence, not
an accepted performance result.

### Rejected candidate: body-scoped learned selection

An outside research spike proposed compiling the stable header-to-plan relationship once per
tabular body. Its required CP0 was a disposable first-row learned cache for one flat, concrete
nested tag. The experiment passed all 13 focused semantic tests and was then measured only on the
named nested case and its ordinary and untyped controls.

Against the repaired checkpoint `942d7c4`, CP0 improved nested concrete decode by 2.1% at 512 rows
(MDE 2.2%, unresolved) and 3.2% at 4096 rows (MDE 0.9%, significant). The ordinary and untyped
controls were neutral. Against `v0.2.0b5`, however, the CP0 build still reproduced a 4.7% slowdown
at 4096 rows (MDE 1.7%). This recovers less than half of the established 7-9% correctness tax, so
the spike's own falsifier fired. The CP0 patch was discarded. Do not proceed to its leaf-count,
`RowShape`, union-dispatch, keyed-body, or probe-deletion checkpoints without a new profile and a
new mechanism. The internal raw results are `.git/research/cp0-*.json` and are not release
evidence.

### Follow-up experiment: minimal selection memo and compiled tag matcher

The rejected CP0 still resolved one mechanism: its combined body-scoped memo treatment improved
the repaired nested concrete case by 3.2% at 4096 rows, above that session's 0.9% resolution
floor. It did not prove which individual memo operation caused the improvement, and it did not
meet the original requirement to recover at least half of the complete correctness cost.

A new experiment can test a smaller production design. This decision is prospective: it is
recorded before the production candidate is implemented or measured. First, add four contrasts
without changing codec source: nested union rows, tag-last nested rows, quoted nested tags, and
integer nested tags. Then test a minimal body-scoped selection memo without the rejected
`RowShape` interpreter. Adopt it only if the current repaired build improves by at least 2% at
4096 nested-concrete rows, the tag-last and union cases have the predicted direction, and the
ordinary typed and untyped controls remain neutral within the same-session resolution floor.
The 512-row result is expected to be below its prior 2.2% resolution floor and is not an adoption
gate.

If the memo passes, test a plan-compiled spelling matcher as a separate checkpoint. A raw-byte
hot match can select only spellings already accepted by the current exact classifier and tag
comparison. Every hot miss must use the current complete path with the same fault coordinates.
Adopt it only when an affected 4096-row case improves by at least the measured resolution floor
and the quoted cold-path and unaffected controls do not regress beyond that floor. Do not use a
tag-column prepass: it can report a later-row tag fault before an earlier-row field fault and thus
changes observable error order.

The minimal memo adopted. It reuses the existing trusted row-memo cursor and adds no parser
ordinal, callback parameter, or row interpreter. The first row records only the parent field,
declared plan, discriminator field, and raw-cell offset. Later rows still classify and validate
their own discriminator, and tagged unions still select their own member.

Against the preserved repaired-build environment, the higher-power confirmation improved
nested-concrete decode by 4.3% at 512 rows (MDE 1.2%) and 3.4% at 4096 (MDE 1.5%). Nested union
improved 3.7% and 3.3%; tag-last improved 4.6% and 3.5%. The untyped control was neutral at both
sizes. An initial ordinary-control slowdown at 4096 did not reproduce under the harness's
independent confirmation. Tag-last did not improve more than tag-first, so the measurement
supports memoized structural selection but does not support the report's stronger claim that
tag-field scan position multiplies the gain. Raw runs are retained below `.git/research/`.

The separate exact-spelling matcher was tested and reverted. It stored one plan-time exact raw
spelling for ordinary bare string and integer tags, returned immediately on a hit, and ran the
unchanged classifier and tag comparison on every miss. At 4096 rows, nested concrete measured
-3.8% with a 4.9% MDE and nested union +1.5% with a 4.6% MDE; neither resolved. Integer tags
improved 1.5% with a 1.3% MDE, and the quoted cold path was neutral. The untyped 512-row control,
which cannot use a typed plan matcher, reproduced a 1.0% slowdown with a 0.8% MDE. The candidate
therefore failed both the common-case and protected-control conditions. No matcher code remains.

### E3 attribution and stop

E3 used the existing A/B worker outputs, not a new timing harness. Two four-round ladders measured
the repaired build versus CP-S and `v0.2.0b5` versus CP-S at 4, 64, 512, and 4096 rows. CP-S was
the shared build across sessions. An advisory R model fit absolute time as
`time_us ~ session + build + build:records` with HC3 covariance over 128 worker-process means.

The estimated slopes were 151.34 ns/row for CP-S (95% CI 150.35-152.34), 153.80 for the correct
pre-memo repair (152.75-154.85), and 145.38 for `v0.2.0b5` (144.05-146.71). CP-S therefore saves
2.46 ns/row against the correct repair (CI -3.91 to -1.01) while remaining 5.96 ns/row slower than
the release that skipped validation (CI 4.30-7.63). The model is advisory; the interleaved A/B
results remain the performance authority.

Ten-second symbolized macOS profiles used isolated release-optimized builds with DWARF retained.
They were not timed. `select_object_field` self-samples fell from 41/835 on the correct repair to
23/837 on CP-S, which confirms the memo removed structural-selection work. The remaining samples
inside selection include required tag validation, not a separately visible call-overhead bucket.
The dominant surrounding costs are row emission, cell splitting, scalar/Python conversion,
Struct allocation, and garbage collection. An inline hot/cold split has no measured mechanism
large enough to recover the 5.96 ns/row residual and would reopen the binary-layout risk already
seen in CP-T. E4 is not attempted. The residual is accepted as the measured cost of enforcing
nested tags under the current no-VM, public-constructor architecture, and this performance branch
stops.

### Task 3.7: local ordinary-object selection

The applicable pattern is container-local schema selection. msgspec's C decoder carries the
current `TypeNode` through its recursive decode calls. Serde's `Visitor` and `DeserializeSeed`
interfaces likewise attach caller schema state to one deserialization operation. This codec's
nested field-group path already implements the useful local form: selection is returned and
passed directly to the exact child object.

Verdict: **port** that value flow into the existing generic event boundary. Do not adopt a new
dependency, replace the complete `Consumer` trait, or hand-roll a second parser protocol.
`object_scalar_hint` updates an `ObjectSelection` owned by the parser invocation. The parser then
passes it into `start_selected_object` for the exact root, ordinary child, tabular row, keyed row,
or list-item object. The typed consumer has no global pending plan or invalid-tag flags.

The seven-way matrix covers root, child, deeper child, siblings, optional, recursive, and adjacent
objects. Against exact preceding source `f7a0d00`, ordinary and nested-tag decode were neutral at
4, 64, 512, and 4096 rows. Root tagged-union decode was unresolved through 512 and 2.1% faster at
4096 with a 1.9% MDE. This is adopted for state ownership and correctness locality; the resolved
large-row improvement is supporting evidence, not permission to combine phase 4 representation
changes into this checkpoint.

### Task 1.4: phase-4 layout, allocation, and profile baseline

The baseline source is commit `778e3c2`. The toolchain is Rust/Cargo 1.93.1, uv 0.12.2,
CPython 3.13.1, PyO3 0.29.0 with `abi3-py313`, and exact `msgspec==0.21.1` on Apple arm64.
Compiler layout data came from a diagnostic `-Zprint-type-sizes` test build. It did not change
production source.

| Type | Size | Alignment |
|---|---:|---:|
| `TypedConsumer<false>` / `TypedConsumer<true>` | 360 bytes | 8 |
| `Frame` / `Option<Frame>` | 56 bytes | 8 |
| `RowMemo` / `Option<RowMemo>` | 64 bytes | 8 |
| `SequencePlan` | 16 bytes | 8 |
| `TypedObjectSelection` | 24 bytes | 8 |
| `ObjectSelectionResult<TypedObjectSelection>` | 48 bytes | 8 |
| `ObjectProbe` | 32 bytes | 8 |
| `CompiledPlan` | 32 bytes | 8 |
| `PlanNode` | 40 bytes | 8 |
| `PlanKind` | 32 bytes | 8 |
| `StructPlan` | 128 bytes | 8 |
| `FieldPlan` | 56 bytes | 8 |
| `DefaultPlan` | 16 bytes | 8 |
| `UnionPlan` | 32 bytes | 8 |

The current `make g2` instrumented build passes all nine allocation tests. The 64-record typed
probe constructs zero builtin dictionaries and zero builtin lists, one final list, and 129 final
Structs. The wrapper control constructs 129 builtin dictionaries and one builtin list. Tagged,
tagged-array, recursive, and nested-field-group cases also construct only the final values their
declared target requires.

Two retained symbolized profiles cover the affected control paths. The CP-S nested-tag profile
shows `select_object_field` falling from 41/835 to 23/837 samples after the adopted selection memo;
the residual includes required discriminator validation. The exact B1 validating-sink profile
collects 834 main-thread samples during 26,082 decodes: `classify_bare` falls from 106 to 7 and
`emit_row_fields` from 121 to 67, while mandatory `split_cells_into` becomes the largest visible
residual at 365 samples. The B1 profile artifact SHA-256 is
`ae9555113774b06d6a701856d73252cd3f4b296f7f41492b5e02e1e330024bcc`; the CP-S profile
artifact SHA-256 is `98c4728e6b37f670903fb89b85ffc65f09f57046ec3a90bb9881662c830b4ba6`.

These are attribution counts, not timing estimates. They establish the sizes and costs that each
phase-4 checkpoint must compare against. In particular, `PlanId` is allowed no frame growth, and
an explicit field action must not make the 48-byte object-selection result larger without a
separately resolved mechanism.

### Task 4.1: typed-state hypothesis and falsifiers

Raw `usize` currently means both a plan-arena identity and a Struct field position. The tag field
uses `usize::MAX` as a third meaning. The hypothesis is that a private, transparent `PlanId` and a
closed field action remove invalid combinations at compile time without adding runtime work. Plan
validation remains at compilation; successful decode continues to use the validated arena.

The migration is deliberately split. Task 4.2 types only the checked root boundary. Task 4.3
replaces the tag sentinel with explicit field, discriminator, skip, and reject actions. Tasks 4.4
and 4.5 then move selection, frames, and recursive edges in bounded checkpoints. No checkpoint may
combine those changes merely to produce a cleaner final diff.

The representation gate is prospective: `PlanId` must remain one machine word, and the first
checkpoint must keep `CompiledPlan` at 32 bytes, `PlanNode` at 40 bytes, `Frame` at 56 bytes, and
`ObjectSelectionResult<TypedObjectSelection>` at 48 bytes. Each checkpoint must pass malformed-plan,
union, recursive, fixed-tuple, row-memo, and interaction tests. A layout change that enlarges a hot
type or a confirmed focused decode regression is revised or reverted before the next task.

### Task 4.2: checked root `PlanId`

The first migration types only `CompiledPlan.root`. `PlanId::checked` rejects an out-of-range root
during native plan compilation, and runtime code unwraps the already-validated word. Recursive
edges and Struct field positions remain unchanged for their later checkpoints.

The representation gate passes: `PlanId` is 8 bytes; `CompiledPlan` remains 32 bytes, `PlanNode`
40 bytes, `Frame` 56 bytes, and `ObjectSelectionResult<TypedObjectSelection>` 48 bytes. Thirty-nine
Rust tests and 108 focused Python union, recursive, fixed-tuple, row-memo, control-pattern, and
plan-error tests pass.

The same-session exact-source A/B used ten worker blocks per side with the repository estimator.
Typed decode measured +1.6% at 512 rows with a 2.1% MDE and +0.1% at 4096 rows with a 0.9% MDE;
neither difference resolves. The checkpoint is adopted as a zero-layout typed-state boundary.

### Task 4.3: explicit field actions

`StructPlan` now returns one closed action for every wire key: declared field, discriminator tag,
allowed skip, or forbidden reject. The tag policy no longer stores or compares `usize::MAX`.
Row memos cache the same action that normal lookup returns, so trusted and byte-checked replay use
one decision model.

The first direct payload-enum representation was rejected. It was 16 bytes, twice the old map
value width. Ordinary typed decode at 512 rows reproduced a +1.72% slowdown with a 0.89% MDE;
nested-tag decode reproduced +0.69% with a 0.51% MDE. No code from that representation remains.

The adopted revision stores an explicit one-byte kind and a plan-checked `u32` field index in an
8-byte `FieldAction`. An out-of-range field count fails plan compilation. `StructPlan` remains 128
bytes, `RowMemo` 64, `Frame` 56, `PlanNode` 40, and the object-selection result 48. Thirty-nine
Rust tests and 108 focused Python tests pass.

Against exact preceding source, ordinary typed first-pass signals at 512 and 4096 rows did not
survive the required double-power confirmations. The nested-tag run had 16.2% observed canary
spread and resolved neither +2.3% at 512 nor -0.7% at 4096. The checkpoint therefore claims state
clarity and sentinel removal only; it claims no speed change.

### Task 4.4: typed Struct-plan selection

The native plan module is now private to the extension crate. `FieldPlan.value` stores a checked
`PlanId`, and local object selection plus its row memo carry `PlanId` through discriminator
validation. A temporary `node_index` lookup remains only for container graph edges and runtime
frames assigned to task 4.5.

All protected layouts remain fixed: `PlanId` 8 bytes, `FieldPlan` 56, `TypedObjectSelection` 24,
`ObjectSelectionResult<TypedObjectSelection>` 48, `Frame` 56, `PlanNode` 40, and `CompiledPlan`
32. Forty Rust tests and the 108-test focused interaction set pass.

Against exact preceding source, typed decode measured -1.0% at 512 rows with a 1.9% MDE and +0.0%
at 4096 with a 0.6% MDE. Nested-tag decode measured +0.6% at both sizes with MDEs of 4.2% and
3.1%. No difference resolves, so this checkpoint claims typed state only and no speed change.

### Task 4.5: typed container edges and frames

All remaining plan-arena edges now store `PlanId`: list and tuple items, fixed tuple positions,
dictionary key/value plans, union members, and Struct fields. Runtime sequence, dictionary, union,
selection-memo, and expected-plan state carry the same type. The transitional raw-index arena
lookup is removed.

The first complete candidate preserved all semantics and layouts but failed its nested-tag
performance control at 4096 rows: +0.75% with a 0.70% MDE, then +1.35% with a 1.11% MDE on the
required confirmation. The candidate was preserved privately and revised before adoption.

The revised candidate forces the now-typed `resolve_container` boundary inline. A double-power
rerun of the failed cell measured +0.6% with a 1.1% MDE and did not reproduce the regression.
Ordinary typed decode measured -3.2% at 512 rows with an 8.3% MDE and -1.7% at 4096 with a 2.3%
MDE. No speed change is claimed.

`PlanKind` remains 32 bytes, `UnionPlan` 32, `SequencePlan` 16, `Frame` 56, `RowMemo` 64,
`TypedObjectSelection` 24, and the object-selection result 48. Forty Rust tests and the 108-test
focused interaction set pass.

### Task 4.6: compiled container-chain validation

The old `resolve_container` exhaustion case silently returned the root plan. That converted an
invalid or cyclic plan graph into an unrelated schema selection. Plan compilation now rejects
single-member union cycles before a decoder becomes usable. The runtime exhaustion case is a
cold, static internal fault and cannot disclose payload text.

The first candidate returned `Option<PlanId>` from every successful container resolution. It
passed semantic tests and left layouts unchanged, but nested-tag decode at 4096 rows reproduced a
0.78% slowdown with a 0.52% MDE. That per-call branch was rejected. The adopted design validates
the graph once during decoder construction and keeps successful hot-path resolution infallible.

Against exact preceding source, ordinary typed decode measured +0.5% at 512 rows with a 0.8% MDE
and +0.2% at 4096 with a 0.6% MDE; neither resolves. Nested-tag decode produced an initial +1.7%
signal, but the required independent double-power confirmation did not reproduce it. All protected
layouts remain unchanged. The plan tests, 89 focused Python union/recursive/support tests, and the
release build pass.

Phase 4 is complete. Every arena identity and recursive edge uses `PlanId`, field dispatch uses a
closed 8-byte action, invalid root and edge identities fail at compilation, and a malformed
container cycle cannot fall back to the root schema. Confirmed regressions in the first field-action,
frame-migration, and runtime-`Option` candidates were each revised before adoption.

### Tasks 5.1-5.9: shared-grammar validating sink

The profile-based hypothesis was narrow: an allowed unknown nested field group still recursively
classified every cell and dispatched every descendant typed event even though the target schema
had already selected discard. The parser now accepts a container-local `ValidateOnly` disposition.
It retains header parsing, quote-aware cell splitting, row width and count checks, duplicate-field
checks, indentation, and depth limits, but emits no descendant semantic actions. Quoted ignored
cells reuse the authoritative scalar grammar; bare cells need no classification because bare
classification is total and no value is constructed.

The event recorder proves that a three-level ignored field group produces only the enclosing list,
row, and retained-field events. The hostile differential contains 28 cases, including closure,
escape, Unicode surrogate, width, duplicate-header, depth, forbidden-unknown, tagged, `Any`, and
untyped controls. Public tests additionally cross unknown ordinary objects, arrays, tabular rows,
keyed rows, and nested field groups; malformed duplicates, row counts, widths, and quotes still
raise payload-safe public faults.

The instrumented G2 build passes ten allocation tests. Every allowed unknown container form creates
zero builtin dictionaries and zero builtin lists; only the declared final Struct and, for a root
list target, its declared final list are constructed.

Against exact preceding source, the primary 16-leaf ignored-field workload improved 28.14% at 512
rows (MDE 1.14%) and 27.52% at 4096 (MDE 1.33%). The per-leaf slope fell from 7.141 to 4.194
ns/row/leaf, a 41.27% reduction. Ordinary typed, known nested, tagged, union, and untyped controls
had no confirmed regression. Symbolized samples moved out of `classify_bare` and
`emit_row_fields`; mandatory `split_cells_into` became the largest residual. The resolved
validating sink is adopted. No second grammar and no general parser bypass were added.

### Tasks 6.1-6.7: duplicate-key ownership candidate rejected

The strict parser owns one canonical key buffer for every bare, unescaped quoted, escaped, and
duplicate key it encounters. A test-only counter at the exact ownership boundary records two
ownership allocations for two keys in each spelling family, including the second key that proves
a duplicate. The counter compiles out of release builds.

The bounded D1 candidate replaced `FxHashSet<Vec<u8>>` with
`FxHashSet<Cow<'input, [u8]>>`. Bare and unescaped quoted keys borrowed immutable input; escaped
keys retained the existing owned unescape result. `Cow<[u8]>` preserved canonical byte hashing,
exact equality after collisions, and the object-local lifetime. Thirty-one semantic differentials
covered canonical-equivalent spellings, Unicode, empty and 4096-byte keys, nested and list objects,
keyed rows, non-strict last-write-wins, malformed keys, and payload-safe coordinates.

The ownership mechanism resolved for width 8 and 32 bare and quoted objects (7-10% faster), width
128 quoted objects (11.12%, MDE 3.19%), and keyed tabular input (9.09%, MDE 1.05%). Escaped keys
were neutral as predicted. The prospectively required width-128 bare cell measured -5.42% with a
9.50% MDE because one retained worker block expanded the variance. Its improvement did not resolve
above the session floor. No protected slowdown survived confirmation.

The fixed adoption gate required both width-128 bare and quoted primaries to resolve. It therefore
fired: `D1 REJECT - BELOW FLOOR`. The complete safe candidate is retained under private research,
but no `Cow` ownership code remains in production. The checkpoint is complete by rejection; its
threshold was not weakened after observation.

### Tasks 7.1-7.2: encoder decision profile and first hypothesis

Five separate optimized, symbolized samples covered root, entry, list-item, keyed, and tabular
rendering. The keyed and tabular success paths already pass one `Shape` witness from validation to
`write_row_obj`; no duplicate successful shape classification was found there. On irregular root
and entry paths, however, `keyed_shape` remained visible beside `object_pairs`: a dictionary can
build or probe a keyed candidate, reject it, then walk the same object again to build fallback
entries. List-item rendering also builds an entry view but correctly does not reinterpret the item
itself as a keyed block.

The first prospective hypothesis is limited to the dictionary object decision. One decision will
own the selected entry view and, only while viable, the rows needed for a keyed `Shape`. A keyed
success must retain the existing entries and shape witness. A keyed miss must convert the already
collected entries into fallback rendering without a second dictionary walk or a second entry-vector
allocation. Root moves first; entry and list-item call sites move in later checkpoints. Adopt only
if canonical bytes are exact, a late keyed-miss workload improves beyond its session floor, and
keyed-success plus ordinary controls have no confirmed regression.

### Tasks 7.3-7.6: root object render decision

The root dictionary path now produces one closed render decision: fallback entries, or keyed
entries plus the exact `Shape` witness that rendering consumes. It validates string keys and
collects candidate rows during one dictionary walk. If a later value invalidates keyed form, the
already collected entry view becomes the fallback; `object_pairs` does not walk the dictionary a
second time. Struct roots retain their plan-owned field/tag view, so tags, renames, defaults,
`array_like`, attribute access, and optional offset access remain controlled only by `EncodePlan`.

The adversarial 512-entry workload makes 511 values look keyed-compatible and invalidates the
candidate with the last value. Against exact preceding source it improved 4.48% with a 1.11% MDE.
Keyed success measured +1.92% with a 3.40% MDE and did not resolve; the irregular root control
measured -0.02% with a 1.11% MDE. The official corpus remains 538/538 with all 84 strict errors,
and the byte/token efficiency lock is exact. The root checkpoint is adopted; entry and list-item
paths remain unchanged for their separate rulings.

### Tasks 7.7-7.11: remaining encoder-path rulings

The entry path received its own checkpoint against the adopted root source. Generalizing the root
decision to entries slowed the 512-entry late-miss primary by 1.36% with a 0.79% MDE. It also
slowed the already adopted root late-miss control by 6.60% with a 1.28% MDE. The entry keyed-success
cell was unresolved. The candidate was fully reverted. The list-item profile showed entry-view
construction but no duplicate keyed classification, so no unmeasured cleanup candidate was opened.
Keyed and tabular success already consume the `Shape` they validate.

The adopted root candidate was then measured against exact pre-Phase-7 source across all required
512-value shapes. Uniform (-0.07%, MDE 4.91%), nested (+1.35%, 1.61%), keyed (-1.06%, 1.65%),
irregular (+0.42%, 1.48%), tagged (+1.36%, 1.53%), and array-like (+1.72%, 4.65%) were all
unresolved. The official corpus and byte/token locks remain exact. Phase 7 therefore adopts only
the resolved root decision and rejects the harmful entry generalization.

Issue 09 was rerun after consolidation. Direct `set`, `frozenset`, and `bytes` values still raise
`EncodeError`; `msgspec==0.21.1` emits arrays for the set-like values and base64 text for bytes, and
`msgspec.to_builtins` still projects each into an already encodable form. Render consolidation did
not close that policy gap. The separate `decide-set-frozenset-and-bytes-encoding` OpenSpec change
remains open and no support claim enters this release implicitly.

### Tasks 8.1-8.8: unsafe membrane qualification

Every unsafe site now has a local `SAFETY` contract. The contracts cover four classes: parser-
validated ASCII/UTF-8 conversions; checked immutable plan-arena access; CPython vectorcall and
new/borrowed-reference ownership transfer; and exact-type/optional Struct-offset reads. Vectorcall
documents argument and keyword-tuple liveness plus the single new-reference transfer. Exact-type
casts are guarded by immortal CPython type-pointer equality. Offset reads require the exact pinned
class, hold the object's PyO3 critical section on free-threaded CPython, acquire a strong field
reference before leaving it, and never steal the Struct-owned slot.

The optional capsule consumer now bounds Struct field counts at 4096 before constructing a slice.
Negative tests reject wrong ABI versions, short tables, missing functions, null non-empty views,
negative and oversized field counts, and negative offsets. The named-capsule contract remains the
authority for a non-null table pointer and producer-owned view lifetime; production copies offsets
into its plan before returning.

The isolated patched-msgspec path was rebuilt from clean pinned source. On CPython 3.13 ABI3 it
activated capsule access, passed lint/typecheck, 42 default Rust tests, 385 Python tests with 11
expected skips, all 538 corpus cases, and all 84 strict-error fixtures. A repository Makefile defect
was fixed so a fresh fast-path build creates its wheel directory before clearing old wheels.

The same feature and patched msgspec were built specifically for CPython 3.14t. The runtime
reported `sys._is_gil_enabled() == False` and capsule access active. Capsule discovery, deleted-field
handling, and the five-thread same-object mutation/encode stress test all passed. No safe
replacement changed a release hot path: this phase adds contracts, cold validation, tests, and
build reliability only, so task 8.8 required no timing claim.
