# Adversarial review sweep: `msgspec-toon` v0.2.0

Review basis: `ecfd71f` on `main`, with codec code from tag `v0.2.0` (`d388cd7`).

This review protects three equal requirements:

```text
                    byte-exact TOON 4.1 conformance
                                  ▲
                                  │
          payload safety ◀────────┼────────▶ speed and token efficiency
                                  │
                                  ▼
                    zero intermediate tree
```

An optimization is valid only inside this boundary. A speed gain cannot buy a parser panic,
an incorrect value, incomplete evidence, or a weaker G2 proof.

## Executive finding map

```text
priority  finding                                      status       main requirement
────────  ───────                                      ──────       ────────────────
P0        F-01 declared count controls Vec capacity    CONFIRMED    safety/conformance
P0        F-02 field-group decode can exhaust stack    CONFIRMED    safety/conformance
P0        F-03 encode shape scan can exhaust stack     CONFIRMED    safety/conformance

P1        F-04 cell error columns are not exact        CONFIRMED    error contract
P1        F-05 G2 counter weakens proof and benchmarks CONFIRMED    zero-tree/speed evidence
P1        F-06 strict=False typed coercion is absent   CONFIRMED    msgspec semantics
P1        F-07 Literal[int] accepts bool                CONFIRMED    typed correctness
P1        F-08 fixed tuples are lowered as Custom      CONFIRMED    Tier 1 correctness
P1        F-09 kw_only Struct construction fails       CONFIRMED    Struct correctness
P1        F-10 order is accepted and ignored           CONFIRMED    public API
P1        F-11 release gap list is incomplete          CONFIRMED    evidence quality
P1        F-12 A/B harness has no uncertainty model    CONFIRMED    speed evidence

P2        F-13 mapping key plans are ignored           CONFIRMED    unsupported boundary
P2        F-14 non-strict specification text conflicts CONFIRMED    specification drift
P2        F-15 msgspec dependency range conflicts      CONFIRMED    specification drift
P2        F-16 D1 row memo lacks focused proof tests    RISK         hot-path maintenance
P2        F-17 unsafe validity proofs are implicit     RISK         hot-path maintenance
P2        F-18 untyped key cache is unbounded          RISK         memory/speed
P2        F-19 duplicate checks are quadratic          RISK         parser speed
P2        F-20 dict shape checks scale by C squared    RISK         encoder speed
```

The review found no byte-level corpus regression. The canonical corpus remains 538/538.

## Validation snapshot

```text
make check
  Rust unit tests       32/32  ✓
  Python tests          43/43  ✓
  ruff, rustfmt, clippy, mypy  ✓

conformance/run.py
  decode fixtures      359/359 ✓
  encode fixtures      179/179 ✓
  required errors        84/84 ✓
  total                538/538 ✓
```

These suites do not cover F-01 through F-13. Most official fixtures decode to `Any`.
They do not exercise the full typed support matrix.

## P0: process-containment defects

### F-01: a declared count controls an unbounded allocation hint

```text
input header [N]
       │
       ▼
header.rs parses N as usize
       │
       ├──▶ UntypedConsumer::start_array
       │       Vec::with_capacity(N)
       │
       └──▶ TypedConsumer::start_array
               Vec::with_capacity(N)
                       │
                       ▼
N = usize::MAX → capacity overflow → PanicException
```

Evidence:

- `src/header.rs:139-166` accepts the largest valid `usize`.
- `src/untyped.rs:121-124` reserves the full declared count.
- `src/typed.rs:559-574` reserves the full declared count.
- Both typed and untyped subprocess probes raised `pyo3_runtime.PanicException`.
- The input was only `[18446744073709551615]:` with `strict=False`.

Impact:

- A small payload can cause a native panic.
- Smaller hostile counts can request excessive memory.
- Strict mode allocates before it reports a missing row.
- The behavior bypasses `DecodeError` and the static fault model.

Required correction:

```text
declared_len ───────────────▶ strict count validation
       │
       └──▶ reserve_hint = min(declared_len, SAFE_RESERVE_LIMIT)
```

Use `try_reserve` if a larger reservation remains useful. Convert allocation failures to a
static codec fault. Do not change the declared count used by the parser.

Performance effect: none on normal benchmark sizes. The current capacities remain below a
reasonable limit.

### F-02: nested field groups bypass the parser depth limit

```text
rows[0]{a{a{...{x}...}}}:
            │
            ▼
parse_field_group recursion
            │
            ▼
100,000 groups → process exit 139
```

Evidence:

- `src/header.rs:215-269` recursively parses nested groups without a depth argument.
- `src/scan.rs:15` defines `MAX_DEPTH = 256` for line depth only.
- Inputs with 2,000 and 10,000 nested groups decoded successfully.
- An input with 100,000 nested groups exited with status 139.

The input size was approximately 300 KB. The parser did not return a codec error.

Required correction:

- Pass a group depth through `parse_field_group`.
- Reject a depth greater than the common codec depth limit.
- Return `FaultCode::DepthLimit` with a static message.
- Apply the same limit in `FieldNode::leaf_count` and `emit_row_fields`.

The depth branch is outside the common flat-row path. Its benchmark cost is negligible.

### F-03: encode shape discovery bypasses the encoder depth limit

```text
[deep_uniform_dict, deep_uniform_dict]
                    │
                    ▼
            build_shape recursion
                    │
                    ├─ depth 2,000  → encoded
                    ├─ depth 10,000 → encoded
                    └─ depth 100,000 → process exit 139
```

Evidence:

- `src/encode.rs:638-738` recursively builds nested tabular shapes.
- `MAX_ENCODE_DEPTH` protects `write_entries` and `write_array` only.
- The shape pass runs before those writer checks.

Required correction:

- Add a depth argument to `build_shape`.
- Stop before recursive shape discovery exceeds `MAX_ENCODE_DEPTH`.
- Return a static `EncodeError` instead of falling through after the limit.
- Add the same guard to static Struct shape compilation.

This correction avoids work on hostile shapes. It does not affect flat challenge records.

## P1: correctness and evidence defects

### F-04: tabular and inline cells receive the wrong column

```text
rows[1]{a,child{x,y}}:
  1,2,NOT_INT
  ▲   ▲
  │   actual failing value starts later
  └── reported column = 3 for every cell

vals[3]: 1,2,NOT_INT
▲
└── reported column = 1 for every inline cell
```

Evidence:

- `src/parser.rs:334-342` gives `row.position` to every tabular cell.
- `src/parser.rs:344-351` gives the header position to every inline cell.
- `src/parser.rs:405-420` propagates one position through all nested fields.
- The probes reported line 2, column 3 and line 1, column 1.

The line is correct. The column is not the location where typed conversion failed.

Required correction:

- Preserve each cell start offset during the delimiter scan.
- Add the line start column to that offset.
- Preserve offsets through keyed-row prefix trimming.
- Add cases for quoted cells, escaped cells, tab delimiters, and nested groups.

Performance condition: reuse one cell buffer as D2 does now. Do not allocate a second offset
tree. Measure this change with same-session A/B because cell splitting is a hot path.

### F-05: the G2 counter is not independent and contaminates benchmarks

```text
current gate

UntypedConsumer allocation ──▶ explicit count_dict/count_list ──▶ counter
TypedConsumer allocation   ──▶ no counter calls                 ──▶ zero

zero currently means: "the typed path did not call untyped counters"
zero does not independently mean: "no forbidden container was created"
```

Evidence:

- `src/pyval.rs:19-25` exposes only explicit counter functions.
- Only `src/untyped.rs` calls those functions.
- `tests/test_typed_allocations.py:38-46` reads the same counters after typed decode.
- The design record requires a second test-only instrumented consumer at canvas lines
  1559-1564. That probe does not exist.
- `src/lib.rs:224-245` includes the counters in the release extension.
- Each untyped dictionary or list runs a relaxed atomic increment.

Code review supports the zero-tree claim for the challenge path. The frame types store final
values and shallow constructor buffers. The evidence mechanism remains non-independent.

The release counters also bias speed results:

```text
G3 typed side       no counter operations
G3 wrapper side     one atomic operation per untyped dict/list
G5 untyped decode   one atomic operation per output dict/list
```

The 4,096-record challenge payload adds thousands of atomic operations to the wrapper side.
This overhead is instrumentation, not required codec work. Its size is not measured.

Required correction:

- Add the test-only frame and object counters from the design record.
- Count final lists, final Structs, intermediate lists, and intermediate dictionaries.
- Keep the untyped counter as the wrapper comparison.
- State that `Any` subtrees contain requested final built-in trees.
- Exclude instrumentation from release benchmark wheels.
- Rerun G3 and G5 without counter overhead.

### F-06: `strict=False` does not implement typed scalar coercion

```text
target       input       msgspec.json strict=False    msgspec-toon
──────       ─────       ─────────────────────────    ────────────
int          "1"         1                            ValidationError
bool         "true"      True                         ValidationError
float        "1.5"       1.5                          ValidationError
```

`TypedConsumer.strict` affects duplicate handling. `convert_scalar` does not use it.

This behavior conflicts with the public substitution goal and AD-006. It also leaves a Tier 0
differential requirement untested.

Required correction:

- Define the exact msgspec 0.21.1 coercion table.
- Implement only those coercions when `strict=False`.
- Add differential cases against `msgspec.json` for every Tier 0 scalar.
- Benchmark strict mode separately. Its current fast branches must remain unchanged.

### F-07: `Literal[int]` accepts a boolean

`toon.decode(b"true", type=Literal[1])` returns `True`. `msgspec.json` rejects the value.

Cause: `src/typed.rs:200-213` uses Python equality for literal membership. In Python,
`True == 1` and `False == 0`.

Required correction:

- Match the scalar category before equality.
- Then compare the value.
- Add differential tests for `Literal[0]`, `Literal[1]`, booleans, and strings.

The additional type check applies only to literal plans. It does not affect the challenge path.

### F-08: fixed tuples are lowered as custom types

```text
Python plan compiler               Rust plan compiler
────────────────────               ──────────────────
tuple[int, str]
  kind = tuple_fixed ─────────────▶ unknown kind
                                    │
                                    ▼
                                  Custom(tuple)
                                    │
                                    ▼
                                  ValidationError
```

Evidence:

- `python/msgspec_toon/_plan.py:44-45` emits `tuple_fixed`.
- `src/plan.rs:9-23` has no fixed-tuple variant.
- `src/plan.rs:149-151` lowers an unknown kind as `Custom`.
- The review probe rejected `[2]: 1,x` for `tuple[int, str]`.

Fixed tuples are a declared Tier 1 type. The release report does not list this gap.

Required correction: add a fixed-tuple plan with per-index expected types and exact length
validation. Keep the existing final `PyTuple` construction.

### F-09: `kw_only=True` Struct decoding fails

`toon.decode(b"x: 1", type=KWOnlyStruct)` raises `TypeError: Extra positional arguments provided`.
The equivalent `msgspec.json` decode constructs the Struct.

Cause: `src/typed.rs:266-279` always calls the Struct class with positional vectorcall arguments.

Required correction:

```text
ordinary Struct ──▶ current positional vectorcall hot path
kw_only Struct  ──▶ cached keyword-name tuple + vectorcall keyword path
```

Store the constructor mode in `StructPlan`. Keep the current path unchanged for ordinary
challenge Structs.

### F-10: the public `order` parameter is accepted and ignored

```text
value = {"b": 1, "a": 2}

order              msgspec.json                  msgspec-toon
─────              ────────────                  ────────────
None               insertion order               insertion order
"sorted"           a, b                          b, a
"deterministic"    a, b                          b, a
"garbage"          rejected                      accepted and ignored
```

Evidence: `python/msgspec_toon/__init__.py:85-102` accepts `order` but does not pass it to Rust.

Required correction: implement the msgspec 0.21.1 domain or reject non-`None` values. Silent
acceptance is not compatible behavior. Keep the default insertion-order path allocation-free.

### F-11: `conformance/report.json` omits known gaps

The report claims Tier 0 plus parts of Tier 1. It lists variable tuples, literals, and
`dict[str,T]` as supported.

The report does not list these known boundaries:

- fixed tuples fail.
- literal integer matching accepts booleans.
- `strict=False` scalar coercion is absent.
- `kw_only` Structs fail.
- constraints are parsed but not enforced.
- tagged unions and `array_like` Structs are absent.
- `order` is inert.
- `decimal_format` and `uuid_format` are accepted but inert.
- recursive Struct plans do not fail cleanly.
- non-string mapping key plans are ignored.

The distribution specification requires every known gap in the generated report.

Required correction: generate the gap list from a maintained support matrix. Do not keep a
freehand summary that can lag behind the implementation.

### F-12: the A/B harness does not measure uncertainty

```text
current sequence

baseline process: all sizes and metrics ──▶ current process: all sizes and metrics
        one summary per side                         one summary per side
```

Properties:

- Each metric uses the minimum of seven autoranged batches.
- Baseline always runs before current.
- The harness stores no raw batch distribution.
- The harness calculates no paired interval or run-to-run variance.
- Thermal state and CPU frequency can differ between sides.

Current review experiment at 4,096 records:

```text
sequence       B1=497.27 µs  C1=469.70 µs  C2=481.16 µs  B2=512.03 µs
repeat drift   baseline +2.97%              current +2.44%
paired delta   B1→C1 = -5.54%               B2←C2 = -6.03%
```

This experiment did not invalidate the large-row encode improvement. The paired result changed
by 0.49 percentage points. The design still cannot qualify small deltas without uncertainty.

The handoff records up to ±15% drift on hot runs. That range can exceed the reported E1/E2
encode gains.

Required correction:

- Run an alternating sequence for each metric and size.
- Use at least `B C C B` blocks.
- Store every block result in the evidence artifact.
- Report the median paired log ratio and its spread.
- Separate combined candidates when the expected gain is small.

This change improves evidence quality. It does not change codec performance.

## P2: boundaries, specification drift, and maintenance risks

### F-13: mapping key plans are compiled but ignored

`toon.decode(b"1: 2", type=dict[int, int])` returns `{"1": 2}`.
`msgspec.json` returns `{1: 2}`.

`Frame::Dict` stores only the value plan. `TypedConsumer::key` always creates a Python string.

The declared Tier 1 scope is `dict[str, T]`, not arbitrary keys. The codec must reject an
unsupported key plan instead of returning a value with the wrong type.

Required correction: reject non-string key plans during decoder construction. Add other key
types only with explicit typed conversion and differential tests.

### F-14: non-strict specification text conflicts with the official corpus

The OpenSpec says that `strict=False` never suppresses an error silently. Official fixtures
require silent row removal in at least two cases:

- a keyed entry-depth line without a colon.
- a hash-leading row that becomes a comment.

The parser follows the official corpus. Therefore, the implementation is conformant and the
OpenSpec sentence is false.

Required correction: replace the absolute sentence with an explicit tolerance list. The list
must include every intentional discard and fall-through rule.

### F-15: the msgspec dependency requirement conflicts with the package

```text
AGENTS.md / pyproject.toml / uv.lock     msgspec == 0.21.1
distribution-quality OpenSpec           msgspec >= 0.21.1
```

The exact pin is the project invariant. Change the OpenSpec requirement to `==0.21.1`.

### F-16: the D1 row memo passed review probes but lacks focused proof tests

The review exercised these transitions:

```text
case                                      result
────                                      ──────
identical tabular rows                    ✓
reordered list-form Struct rows           ✓ disables memo, hashes correctly
missing defaulted fields                  ✓
unknown scalar field                      ✓ skipped
unknown object and array subtrees         ✓ balanced skip depth
nested Struct fields                      ✓
Any subtree with different inner shape    ✓ isolated from memo
nested list frames                        ✓ memo push/pop remained balanced
non-strict duplicate fields               ✓ last write won
```

No correctness defect was found in D1.

The coupling remains implicit:

```text
List frame push ⇄ RowMemo push
List frame pop  ⇄ RowMemo pop
Struct below List opens row
Struct below List closes and seals row
```

Required correction:

- Add a focused D1 regression matrix to Python tests.
- Add debug assertions for frame and memo stack alignment.
- Record why shorter rows can keep the memo enabled safely.
- Add keyed-row memo support only after a separate benchmark proves value.

### F-17: the unsafe paths are valid now, but their proofs are implicit

Review result:

```text
site                                      validity argument                         result
────                                      ─────────────────                         ──────
encode.rs exact Py_TYPE dispatch          exact built-in type pointer before cast   valid
encode.rs cast_unchecked<PyString>         PyUnicode_Type equality                   valid
pyval.rs integer UTF-8                     classifier permits ASCII digits/sign       valid
pyval.rs float UTF-8                       classifier permits ASCII numeric grammar    valid
pyval.rs string UTF-8                      document and escapes validated              valid
untyped.rs key UTF-8                       ASCII slicing preserves UTF-8 boundaries   valid
typed.rs vectorcall pointers               argument objects live across the call      valid
```

Quoted keys, tab-delimited cells, and the first-line BOM do not break these arguments.
ASCII delimiter bytes cannot occur inside a UTF-8 continuation byte.

Required correction:

- Add `SAFETY:` comments at each unsafe block.
- Name the producer invariant that makes each conversion valid.
- Add BOM, quoted-key, non-ASCII, escaped-surrogate, and tab-cell regression cases.
- Keep exact-type pointer dispatch. The review found no reason to remove E1.

### F-18: the untyped key cache grows with every distinct key

`UntypedConsumer.key_cache` stores a copied `Vec<u8>` and a pinned `PyString` for each key.
The final dictionary already owns the Python key.

```text
tabular repeated keys     O(columns) cache entries       D3 win
unique object keys        O(keys) duplicate raw storage  memory cost
```

The cache has no size limit and no repeat threshold. A document with many unique keys creates
a second key corpus for the life of the decode.

Required correction: add a bounded policy or cache only keys from tabular headers. Measure
both repeated-row payloads and unique-key payloads before a change.

Current status for `0.3.0b3`: the ordinary lookup scan is removed. The call-local content
cache still has no entry limit. The active
[`repair-untyped-distinct-key-scaling`](../openspec/changes/repair-untyped-distinct-key-scaling/design.md)
design owns the current mechanism and the deferred bounded design.

### F-19: strict duplicate checks use quadratic scans

`parser.rs::note_key` stores keys in a `Vec<Vec<u8>>` and calls `contains` for each key.
`header.rs::parse_field_group` also scans prior fields for each new field.

```text
k unique keys or fields → 1 + 2 + ... + k comparisons → O(k²)
```

Quoted field comparisons also unescape prior names repeatedly. Wide objects and headers can
consume disproportionate CPU time.

Required correction: measure a wide-key ladder. Use a small vector for common objects, then
promote to `FxHashSet` after a measured threshold.

### F-20: dynamic dictionary shape checks scale as rows times columns squared

`src/encode.rs:665-682` checks each row key with a linear search through `first_keys`.

```text
R rows × C keys × linear membership(C) = O(R × C²)
```

The shape pass also reads every dynamic-dictionary leaf before the writer reads it again.
Static Struct shapes avoid this scan, so this finding does not explain the Struct-focused G4
gap. It can affect G5 encode and wide dictionary workloads.

Required correction: profile a wide dictionary ladder. Use a set for shape membership if the
profile shows material cost. Keep first-row order separately for canonical output.

## Payload-safety audit

```text
native Fault fields       code + line + optional column + validation flag
native messages           static summaries + numeric coordinates
payload text in Fault     ∅
schema path storage       not implemented
hook exceptions           propagate unchanged, as the OpenSpec requires
```

The audit found no native payload leak. `format!` calls in parser tests and encoder output do
not enter decode fault messages.

The dynamic unsupported-type name in `EncodeError` comes from the Python class, not encoded
payload content. This behavior does not violate AD-007.

## Non-strict parser review

```text
path                                      review result
────                                      ─────────────
malformed header at root                  fixture-defined fall-through ✓
malformed header in list item             literal-key fall-through ✓
keyed row without colon                   fixture-defined silent skip ✓
duplicate keys                            last-write-wins ✓
declared count mismatch                   actual rows retained ✓
mixed spaces before tab                   deterministic depth result ✓
tab followed by spaces                    spaces ignored after tab, needs explicit docs
```

No new value mismatch was confirmed. The implementation remains fixture-shaped. Add generated
depth cases before changing tab arithmetic.

## Improvement order

```text
phase  change                                      conformance risk  hot-path risk  value
─────  ──────                                      ────────────────  ─────────────  ─────
A      cap reserve hints and add depth limits      low               none           P0
B      add crash and boundary regression tests     low               none           P0
C      make release gap matrix complete            none              none           high
D      repair exact cell coordinates               medium            medium         high
E      add independent G2 instrumentation          none              test-only      high
F      add strict=False differential table         medium            low if branched high
G      fix Literal, tuple, kw_only, order           low               cold-path      medium
H      alternate A/B blocks and store spread       none              none           high
I      profile encode before E3                     none              none           high
J      attempt E3 only with isolated same-run A/B   medium            high           unknown
```

## Performance direction after correctness repairs

```text
decode
  keep D1 memo ──────────────── confirmed correct in reviewed transitions
  keep D2 reused cell buffer ── extend it with offsets, not a second tree
  keep D4 unchecked UTF-8 ───── add explicit safety proofs
  keyed typed rows ──────────── profile before adding a second memo scope

encode
  G4 gap at 4096 ≈ 10%
        │
        ├─ dominant suspected cost: stable-ABI getattr
        ├─ E3 templates: unmeasured, likely attacks writer overhead only
        └─ next evidence: flamegraph before implementation

tokens
  canonical TOON = 0.61–0.64× JSON on challenge records
        │
        ├─ do not change canonical default output
        ├─ do not optimize delimiter folklore
        └─ preserve nested field groups, the source of the token advantage
```

## Exit conditions for the repair round

```text
correctness
  [ ] huge declared counts return a static codec error
  [ ] decode and encode depth probes return a static error
  [ ] typed differential cases match msgspec 0.21.1 for supported types
  [ ] unsupported plans fail during decoder construction
  [ ] exact cell columns pass comma, tab, pipe, quote, and keyed cases

evidence
  [ ] make check passes
  [ ] official corpus remains 538/538
  [ ] G2 has an independent typed-path probe
  [ ] G3 and G5 remain green
  [ ] performance changes have alternating same-session A/B data
  [ ] conformance/report.json lists every remaining gap

performance
  [ ] strict hot paths do not regress outside measured noise
  [ ] canonical bytes and token rows remain unchanged
  [ ] E3 receives a profile-based hypothesis before implementation
```

## Did not fit cleanly

- A hard maximum for a declared array count is not yet selected. The parser needs the count,
  but the consumer does not need an equal reservation.
- The correct column for a nested field-group cell needs one coordinate convention. The current
  event API has only one `Position` per scalar.
- The project does not define whether a depth limit counts groups, fields, or containers. One
  shared limit is simpler, but the OpenSpec must state it.
- The current G2 claim is true by architecture and code review. Its generated proof remains
  weaker than the design record requires.
- E3 can reduce writer calls. Current evidence does not show that writer calls dominate G4.
