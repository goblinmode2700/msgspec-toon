## Context

See `proposal.md` for motivation. The current `wheels.yml` already builds twelve wheels and
smoke-tests each one, but its publish job depends directly on build completion, rebuilds no
verification manifest, and authenticates `uv publish` with `PYPI_API_KEY`. `make check` is the
source gate, while corpus, allocation, benchmark, and report commands remain separate.

The Python plan membrane already lowers msgspec inspection objects to frozen `PlanSpec` data.
The IR contains tag and `array_like` metadata, but recursive lowering is not graph-aware and the
native consumer does not implement those plan forms. Encoder option policy is centralized enough
to reject inert values, but functional and reusable signatures are still maintained separately.

All work remains inside C1-C9. In particular, new typed paths may not build an intermediate
Python tree; malformed or recursive inputs stay bounded; errors remain payload-safe; parser
modules remain Python-free; and any hot-path change requires same-session A/B evidence.

## Goals / Non-Goals

**Goals:**

- Promote exactly the artifacts that passed qualification, with a machine-checkable identity
  from source revision through PyPI file.
- Keep the release-trust checkpoint independent of codec feature work so it can protect every
  later beta.
- Extend typed behavior through the plan graph and existing consumers, not entry-point special
  cases.
- Make scalar bytes and option precedence deliberate public API.
- Add bounded native fuzzing as a second safety net beside fixed fixtures.

**Non-Goals:**

- No replacement for uv, maturin, GitHub Actions, PyPA publication, or cargo-fuzz.
- No new runtime dependency and no relaxation of `msgspec==0.21.1`.
- No claim of full `msgspec.json` parity in `0.2.0b1`.
- No new benchmark estimator, test runner, orchestration harness, private msgspec-layout access,
  or change to the optional upstream Struct-access experiment.
- No canonical-byte change for values accepted by `0.1.0b2`.

## Decisions

### 1. Use two public beta checkpoints

`0.1.0b3` contains only release qualification, artifact promotion, Trusted Publishing, and
generated evidence. These are packaging corrections and fit the next beta serial of `0.1.0`.

`0.2.0b1` adds supported inputs, options, and typed forms. Those are backward-compatible public
features, so they require a minor version and restart the beta serial. Internal tags such as
`v0.4.0` describe development checkpoints; they do not replace public package versioning.

Alternative: put all work in `0.1.0b3`. Rejected because it hides a material capability increase
inside a patch-position beta and prevents users from distinguishing trust work from codec API
growth.

### 2. Keep one repository-native qualification entry point

Add `make qualify` as a composition of existing, focused commands: the locked uv sync, `make
check`, the complete corpus run, G2 allocation proof, and generated support/evidence checks.
Containment and support-matrix probes remain ordinary pytest files and are named explicitly in
the emitted result, rather than duplicated into another runner. The Make target emits component
JSON records for the release report but does not replace pytest, Cargo, or the corpus runner.

A reusable GitHub workflow invokes only this entry point. Pull-request/default-branch CI triggers
it directly; the release workflow calls it as a required job. This preserves one command list
without creating a new orchestration harness.

Alternative: copy the commands into each workflow. Rejected because the copied release list is
the gap this change exists to remove.

### 3. Build once, verify separately, promote by digest

The build matrix continues to use maturin-action and uploads one immutable artifact per matrix
cell. Each artifact includes the wheel plus a small manifest containing filename, SHA-256,
source revision, Python ABI, operating system, and architecture.

Verification downloads a built artifact into a clean target-native job. It creates a uv-managed
environment outside the checkout, installs the exact file by path, clears source-path injection,
and asserts that both `msgspec_toon.__file__` and the native module resolve under that
environment's site-packages. Every wheel runs import and codec probes. One CPython 3.13 wheel per
operating system runs a copied test/conformance bundle that intentionally excludes the source
package directory. The sdist is unpacked in a temporary directory, built into a wheel with uv,
installed elsewhere, and smoke-tested.

Successful verification emits a signed-by-workflow manifest with the observed digest. A single
collection job accepts only build and verification pairs with identical identities and digests,
then uploads the combined verified release set. Publication downloads that set and never invokes
a build command.

Alternative: test from the checkout after `pip install`. Rejected because the editable/source
shadowing defect F-21 already demonstrated that this can test the wrong native extension.

### 4. Adopt PyPI Trusted Publishing and the official publisher

The publish job runs on Linux, targets a protected GitHub environment named `pypi`, and alone
receives `id-token: write`. It uses a commit-pinned revision of
`pypa/gh-action-pypi-publish`, leaves attestations enabled, and consumes the verified artifact
directory. `PYPI_API_KEY` is removed from workflow use after the owner registers the repository,
workflow filename, environment, and PyPI project as a Trusted Publisher.

Rollback is fail-closed: before publisher registration, release publication is unavailable; the
token workflow is not retained as an automatic fallback.

Alternative: use uv's token upload. Rejected because it retains a long-lived secret and does not
give this release the requested default PyPA attestation path.

### 5. Extend the existing report instead of creating a release ledger

`scripts/release-report.py` consumes component result files and verified-artifact manifests. It
adds package version, source revision, per-artifact qualification, and a compatibility delta
computed from the current and prior executable support matrices and byte/token locks. The same
JSON drives the concise changelog section and GitHub release asset; there is no second handwritten
support table. Benchmark collection continues to use `benches/_timing.py` exactly as required by
C9.

Alternative: maintain a Markdown release checklist. Rejected as non-executable evidence that can
drift from the artifacts.

### 6. Make the Python option surface data-driven

Define frozen encode/decode option descriptors in the Python API membrane. Each descriptor owns
its public name, default, accepted domain, implementation state, and native forwarding name.
`Encoder`, `Decoder`, `encode`, and `decode` signatures remain explicit for typing and
introspection, but their validation and forwarding are tested against this one descriptor set.
A signature-parity test fails when an entry point omits or silently drops a declared option.

Top-level `decode()` adds `float_hook`. Top-level `encode()` adds `decimal_format` and
`uuid_format` when their native behavior lands. `order=None` remains implemented;
`sorted`/`deterministic` remain deliberate, consistent `NotImplementedError` outcomes until a
separate canonical ordering implementation is proven. This satisfies parity by explicit refusal,
not by pretending an inert option works.

Introduce exported `TypePlanError`, a subclass of `TypeError`, for unsupported annotation graphs.
This keeps ordinary Python compatibility while giving callers a package-owned stable contract.

Alternative: generate Python signatures dynamically. Rejected because it weakens static typing,
documentation, and introspection for negligible duplication; the shared descriptors plus parity
tests police the meaningful behavior.

### 7. Normalize msgspec-native scalars before `enc_hook`

The Rust encoder checks the finite built-in scalar set before falling through to `enc_hook`:

| Python value | Default TOON representation | Non-default option |
|---|---|---|
| `date` | quoted ISO date | none |
| `datetime` | quoted ISO datetime, `Z` normalization as msgspec 0.21.1 | none |
| `time` | quoted ISO time | none |
| `timedelta` | quoted ISO 8601 duration | none |
| `UUID` | quoted canonical hyphenated form | quoted 32-digit hex |
| `Decimal` | quoted exact decimal text | exact unquoted number |
| `Enum` / `IntEnum` | declared string/integer value | none |

Normalization is differentially tested against pinned msgspec 0.21.1, while TOON quoting and
container placement are tested against this codec's own canonical rules. Decimal number output
uses the Decimal's exact coefficient/exponent formatting and never routes through `f64`.

Alternative: implement these through a default Python hook. Rejected because it taxes common
values, makes behavior application-dependent, and reverses msgspec's built-in-before-hook rule.

### 8. Compile annotations as a graph, then lower an arena to Rust

Replace recursive `_lower()` ownership with a compilation context keyed by annotation identity.
Nodes move through `unseen`, `visiting`, and `complete` states. Encountering a `visiting` Struct
emits a bounded reference node rather than recursing. The frozen Python IR becomes an indexed
graph; Rust compiles it into an arena whose child edges are indices. A malformed or unsupported
cycle raises `TypePlanError` with schema-known path components.

The existing 512-entry top-level annotation cache remains the only long-lived cache. One cached
graph owns its reachable type references; no new unbounded global class-retaining cache is added.
Runtime recursive construction consumes the existing depth budget, and recursive overflow uses
the static depth fault.

Alternative: catch `RecursionError` and reword it. Rejected because it leaves unbounded compiler
recursion, cannot support recursive types, and treats an implementation accident as control flow.

### 9. Implement typed forms through plan-directed frames

- `array_like` Structs use the declared field order and the existing constructor frame, with
  sequence length/default validation at the closing boundary.
- Tagged unions compile a tag-value-to-variant dispatch table. Before converting a tagged object,
  a bounded pure-Rust preflight over that object's input range finds and validates the
  schema-known tag field. The selected existing Struct plan then consumes the object normally.
  The preflight stores only coordinates and borrowed spans, never a Python or native value tree.
- `strict=False` is a plan flag consumed by table-driven scalar coercion routines. Differential
  tests define the allowed conversions; errors remain static and payload-safe.
- Non-string mapping keys stay intentional plan-construction failures for `0.2.0b1` unless a
  direct key conversion path is proven without silent collision or payload leakage. The spec
  permits either outcome, and the executable matrix records the decision.

Alternative: add special cases in `decode()` or replay through `msgspec.convert`. Rejected because
it breaks the single inspection membrane and the zero-intermediate-tree invariant.

### 10. Adopt cargo-fuzz with layered budgets

Create cargo-fuzz targets against the pure-Rust parser and a structure-aware codec surface. Seed
corpora are generated from the vendored conformance fixtures and permanent containment cases;
only minimized regressions become tracked corpus files. Pull requests build all targets and run a
short fixed smoke budget. A scheduled workflow uses a longer budget and uploads `fuzz/artifacts`
on failure. Fuzz dependencies remain outside the runtime crate and normal stable build.

Alternative: write a Python random-input loop. Rejected because cargo-fuzz is the standard
libFuzzer integration for Rust, provides shrinking and coverage guidance, and reaches the native
parser without Python exception machinery obscuring failures.

### 11. Prior-art verdict

**Pattern:** verified artifact promotion pipeline with OIDC publication; graph-based typed plan;
native parser property fuzzing.

**Local survey:** this repository's `wheels.yml`, `Makefile`, executable support matrix, F-21
freshness gate, and frozen PlanSpec membrane are the relevant local patterns. No second local
Python/Rust package pipeline was found in the surveyed project roots, so local code is evidence
only, not an alternative framework.

**Mature survey:** PyPI's Trusted Publisher guidance requires job-scoped `id-token: write` and
recommends a protected environment; the official PyPA action generates attestations by default
and explicitly recommends separate build/test/publish jobs joined by uploaded artifacts and
`needs`. PyO3's maturin-action remains the established cross-platform wheel builder. The Rust Fuzz
Book names cargo-fuzz as the recommended Rust fuzz tool and documents bounded CI smoke runs plus
failure-artifact upload. Pinned msgspec 0.21.1 supplies the scalar normalization and inspection
metadata reference.

**Verdict:** adopt the PyPA action, GitHub artifact promotion, maturin-action, and cargo-fuzz;
port msgspec's observable scalar/option semantics and graph metadata into the existing PlanSpec
membrane. Hand-roll only repository-specific glue: digest manifests, plan-arena lowering, and
report aggregation. Do not build a publisher, wheel builder, fuzzer, test runner, or workflow
orchestrator.

## Risks / Trade-offs

- **[PyPI publisher registration is external state]** -> Land and validate the workflow first;
  keep publication disabled until the owner registers the exact repository/workflow/environment.
- **[A reusable workflow cannot protect a misconfigured branch by itself]** -> Document the exact
  required-check name and verify branch protection after the first successful default-branch run.
- **[Full installed-wheel tests can accidentally import source]** -> Run outside the checkout,
  inspect module origins, and omit the package source directory from the test bundle.
- **[Free-threaded and cross-architecture runners may expose target-only failures]** -> Every cell
  gets native smoke verification; failures block the combined artifact set.
- **[Graph plans retain recursive classes]** -> Keep the existing bounded annotation cache only;
  add cache-size and weak-lifetime characterization tests before widening retention.
- **[Tagged-union preflight adds a second structural scan]** -> Restrict it to tagged-union object
  ranges, benchmark the affected ladder in the same session, and reject any unresolved hot-path
  regression.
- **[Decimal number formatting can change tokenization or overflow downstream floats]** -> Preserve
  exact decimal digits, document that numeric consumers choose their own precision domain, and
  lock canonical cases.
- **[Fuzzing can become nondeterministic release theater]** -> PR fuzzing is only a target-build and
  bounded smoke gate; sustained results are retained, minimized, and promoted to deterministic
  regressions.

## Migration Plan

1. Land the `0.1.0b3` qualification workflow with publication disabled. Run canonical validation,
   build the full matrix, verify every artifact, and inspect the combined manifest.
2. Configure the protected `pypi` GitHub environment and PyPI Trusted Publisher for the exact
   owner, repository, workflow filename, and environment. Remove workflow use of
   `PYPI_API_KEY`; keep the secret itself until one attested dry-run or TestPyPI-equivalent proves
   the identity path, then remove it from repository secrets separately.
3. Publish `0.1.0b3` only from the verified set. Confirm all files, attestations, report asset, and
   fresh installs before advancing.
4. Implement `0.2.0b1` in the ordered typed/API/fuzz checkpoints in `tasks.md`. Each checkpoint
   updates the executable matrix and runs C1-C9 gates; hot-path changes also run same-session A/B.
5. Publish `0.2.0b1` through the already-qualified pipeline and verify the generated compatibility
   delta against `0.1.0b3`.

Rollback never deletes published files or reuses a version. Before upload, a failed gate leaves
the release unpublished. After upload, a defect is fixed under the next beta serial; a severely
unsafe release may be yanked on PyPI, with the evidence and reason retained.
