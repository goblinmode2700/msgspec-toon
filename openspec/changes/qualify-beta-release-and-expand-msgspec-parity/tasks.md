## 1. Freeze the beta-2 qualification baseline

- [x] 1.1 Record the exact `0.1.0b2` public artifacts, source revision, wheel target matrix,
      support-matrix output, canonical byte/token lock, and current workflow behavior in generated
      baseline input for release-delta tests.
- [x] 1.2 Add failing tests that demonstrate the present release gaps: a canonical validation
      failure does not block publication, verification can run from the checkout, and the publish
      job still references `PYPI_API_KEY`.
- [x] 1.3 Run `make check`, the complete corpus, G2, G3/G5, and strict OpenSpec validation before
      changing qualification code; record only checks actually run.

## 2. Create the canonical release-validation gate

- [x] 2.1 Add component-result output to existing lint, typecheck, Rust-test, pytest, corpus,
      containment, support-matrix, and G2 commands without replacing their native runners.
- [x] 2.2 Add `make qualify` as the single composition of locked uv setup, `make check`, complete
      corpus, containment/support probes, G2, and release-report prerequisites.
- [x] 2.3 Add a reusable GitHub validation workflow invoked for pull requests, default-branch
      pushes, and release workflow calls; remove any copied smaller validation list.
- [x] 2.4 Prove each required component can fail the canonical job and that a failed validation
      leaves all publication-dependent jobs skipped.

## 3. Separate artifact construction from verification

- [x] 3.1 Refactor the existing wheel and sdist matrix into build-only jobs that upload immutable
      files plus manifests containing filename, SHA-256, source revision, Python ABI, operating
      system, and architecture.
- [x] 3.2 Add target-native clean uv environments that install each wheel by exact path outside
      the checkout, assert Python and native module origins under site-packages, and run import and
      representative encode/decode tests.
- [x] 3.3 Select and document one CPython 3.13 wheel per operating system to run the complete
      Python suite and pinned TOON corpus from a verification bundle that excludes package source.
- [x] 3.4 Build a wheel from the sdist in a clean uv-managed temporary directory, install it in a
      second clean environment, and run the installed-artifact codec probe.
- [x] 3.5 Emit verification manifests and add a collection job that rejects missing matrix cells,
      target mismatches, or build/verification digest mismatches before creating one verified
      release artifact set.
- [x] 3.6 Add workflow tests or fixture-driven manifest tests that prove a stale, substituted,
      partially verified, or source-shadowed artifact cannot reach publication.

## 4. Adopt Trusted Publishing and attestations

- [x] 4.1 Replace token-based `uv publish` with a commit-pinned
      `pypa/gh-action-pypi-publish` step that downloads only the verified release set and performs
      no build.
- [x] 4.2 Restrict `id-token: write` to the publish job, bind that job to the protected `pypi`
      environment, retain default attestations, and restrict execution to intended tags or an
      explicitly authorized manual release.
- [x] 4.3 Document the exact PyPI Trusted Publisher tuple and GitHub environment setup as an
      external owner checkpoint; keep publication disabled until the owner completes it.
- [x] 4.4 After the owner confirms the trusted identity, run a non-production identity/artifact
      qualification if available, then remove repository workflow use of `PYPI_API_KEY`; do not
      retain an automatic token fallback.

## 5. Generate and attach release evidence

- [x] 5.1 Extend `scripts/release-report.py` to consume canonical component results and verified
      artifact manifests and to record package version, source revision, target identity, and
      result for every release file.
- [x] 5.2 Generate new/removed/changed support and canonical-wire entries from the prior and
      current executable matrices and locks; make drift from a handwritten compatibility list a
      test failure.
- [x] 5.3 Include benchmark inputs, environment, package versions, raw repeated observations,
      estimator, and variation without changing `benches/_timing.py` or citing another session.
- [x] 5.4 Attach the machine-readable report to the GitHub release and generate the changelog
      compatibility summary from the same data.
- [x] 5.5 Add failure tests for missing component evidence, revision/version mismatch, incomplete
      artifacts, and unrecomputable benchmark claims.

## 6. Qualify the release-trust checkpoint

- [x] 6.1 Bump all public package version sources to `0.1.0b3`, update the changelog and README,
      and verify wheel/sdist metadata and public links from installed artifacts.
- [x] 6.2 Run strict OpenSpec validation, canonical qualification, the complete twelve-wheel and
      sdist verification matrix, and release-report generation with publication disabled.
- [x] 6.3 Confirm the verified set contains exactly twelve wheels and one sdist, every digest and
      target identity matches, and the proposed publish job would consume no other files.
- [x] 6.4 Stop at the publication checkpoint. Publish `0.1.0b3` only after explicit owner
      authorization and completed PyPI/GitHub trusted-publisher configuration; then verify PyPI
      files, attestations, release evidence, and fresh installs without reusing the version.

## 7. Stabilize typed-plan failures

- [x] 7.1 Add `TypePlanError(TypeError)` to the public API and translate every unsupported plan
      construction failure to a stable code and schema-known path with payload-safe text.
- [x] 7.2 Add differential and containment tests for nested unsupported annotations, recursive
      annotations, mapping keys, and custom types; prove `RecursionError` and native faults never
      leak.
- [x] 7.3 Update the executable support matrix so every typed entry is either supported or
      intentionally rejected and zero entries are silently wrong or silently ignored.
- [x] 7.4 Run `make check`, complete corpus, payload-safety tests, G2, G3/G5, and same-session A/B;
      reject any unresolved regression before continuing.

## 8. Unify functional and reusable option behavior

- [x] 8.1 Add frozen encoder and decoder option descriptors covering names, defaults, accepted
      domains, implementation states, and native forwarding names.
- [x] 8.2 Keep explicit typed signatures but derive validation/forwarding tests from the shared
      descriptors; add signature-parity tests for functional and reusable entry points.
- [x] 8.3 Add `float_hook` to top-level `decode()` and prove equivalent hook invocation, results,
      and propagated hook errors through `decode()` and `Decoder`.
- [x] 8.4 Keep `order="sorted"` and `order="deterministic"` as consistent documented
      `NotImplementedError` outcomes unless a separate ordered-encode checkpoint proves them;
      test that no accepted option is inert.
- [x] 8.5 Run focused API tests, `make check`, corpus, payload safety, G2, G3/G5, and same-session
      functional-entry A/B; adopt only resolved non-regression.

## 9. Encode msgspec-native scalar values

- [x] 9.1 Add failing normalization and canonical-byte tests for date, datetime, time, timedelta,
      UUID, Decimal, string Enum, and integer Enum against pinned msgspec 0.21.1 behavior.
- [x] 9.2 Implement built-in scalar normalization before `enc_hook`, with exact Decimal formatting
      that never routes through `f64`, then add hook-precedence and hook-error tests.
- [x] 9.3 Implement `decimal_format={"string","number"}` and
      `uuid_format={"canonical","hex"}` through both `Encoder` and top-level `encode()`; reject
      every other value consistently.
- [x] 9.4 Extend documentation, executable support matrix, canonical byte/token lock, and generated
      compatibility delta for the newly accepted inputs without changing bytes for beta-2 inputs.
- [x] 9.5 Run `make check`, complete corpus, payload safety, G2, G3/G5, and same-session encode A/B;
      reject any implementation that regresses established payloads beyond the measured gate.

## 10. Compile annotation graphs and support bounded recursion

- [x] 10.1 Add failing graph tests for self-recursive and mutually recursive Structs, unsupported
      cycles, cache bounds, runtime depth overflow, defaults, and renamed recursive fields.
- [x] 10.2 Replace recursive owned lowering with an identity-keyed compilation context and indexed
      frozen PlanSpec graph using explicit `unseen`, `visiting`, and `complete` states.
- [x] 10.3 Compile the Python graph into a native plan arena with bounded reference edges and static
      cycle/depth faults; keep the existing 512-entry annotation cache as the only long-lived
      owner.
- [x] 10.4 Extend direct typed construction for supported recursive Structs and prove zero
      intermediate trees, bounded hostile input, stable type paths, and payload-safe errors.
- [x] 10.5 Run graph differentials, `make check`, complete corpus, containment, G2, G3/G5, and
      same-session decoder-construction/decode A/B; reject unresolved hot-path regression.

## 11. Add array-like and tagged Struct decoding

- [x] 11.1 Add failing differential tests for array-like Struct lengths, defaults, nesting,
      renames, unions, and invalid sequence shapes.
- [x] 11.2 Implement array-like Struct construction through positional plan frames and verify no
      mapping or per-object intermediate container is allocated.
- [x] 11.3 Add failing tagged-union tests for every supported tag scalar, tag order, duplicate or
      missing tags, unknown tags, nested unions, and payload-safe error paths.
- [x] 11.4 Implement tag dispatch from compiled metadata using a bounded pure-Rust preflight over
      the tagged object's input range, then consume the selected Struct plan without a value tree.
- [x] 11.5 Update the executable matrix and run `make check`, complete corpus, containment, G2,
      G3/G5, and same-session typed-decode A/B after each focused form; do not combine unresolved
      array-like and union effects.

## 12. Implement permissive scalar conversion and decide mapping keys

- [x] 12.1 Build a pinned `msgspec.json` differential table for every Tier 0 scalar under
      `strict=False`, including accepted conversions, rejected conversions, integer precision,
      booleans, non-finite numbers, and nested collection positions.
- [x] 12.2 Add a plan conversion-policy flag and table-driven native coercion that preserves static
      payload-safe errors; keep strict mode byte-for-byte and behaviorally unchanged.
- [x] 12.3 Measure non-string mapping-key demand and direct-conversion feasibility. Either implement
      a plan-directed key path with collision/precision tests or retain `TypePlanError` at plan
      construction and document the intentional rejection for `0.2.0b1`.
- [x] 12.4 Update the executable support matrix and run `make check`, complete corpus,
      containment, payload safety, G2, G3/G5, and same-session typed-decode A/B after each focused
      change.

## 13. Add native parser and codec fuzzing

- [x] 13.1 Add pinned cargo-fuzz tooling outside the runtime crate and create an arbitrary-byte
      parser target with a direct valid-UTF-8 path and containment/payload-safety oracles.
- [x] 13.2 Create a structure-aware supported-value target for encode, decode, encode-again,
      value-equivalence, and canonical-byte stability properties.
- [x] 13.3 Seed target corpora from pinned conformance fixtures and permanent containment cases;
      document and test the deterministic seed-generation command.
- [x] 13.4 Add pull-request target builds and bounded smoke runs plus a scheduled sustained run that
      uploads failure artifacts; pin actions and cargo-fuzz versions under the package cooldown
      policy.
- [x] 13.5 Run the sustained budget, minimize every reproducible failure, add each confirmed defect
      as a permanent regression before fixing it, and rerun canonical qualification.

## 14. Qualify the capability checkpoint

- [x] 14.1 Confirm the executable matrix has zero silently wrong and zero silently ignored entries,
      every new scalar/type/API behavior is documented, and beta-2 canonical inputs retain their
      locked bytes.
- [x] 14.2 Bump all public package version sources to `0.2.0b1`; generate the changelog and release
      compatibility evidence against `0.1.0b3` from executable data.
- [x] 14.3 Run strict OpenSpec validation, canonical qualification, complete corpus, containment,
      G2, G3/G5, release-guard A/B, fuzz smoke, full wheel/sdist verification, and report
      generation; record misses without masking them.
- [x] 14.4 Update `HANDOFF.md`, `LAST-MILE.md`, generated evidence, and the optimization ledger
      before the checkpoint commit; archive the OpenSpec change only after every task and delta is
      complete.
- [x] 14.5 Stop at the publication checkpoint. Publish `0.2.0b1` only with explicit owner
      authorization through the trusted, verified-artifact workflow, then verify PyPI files,
      attestations, GitHub release evidence, and fresh installs on representative ABI3 and
      free-threaded targets.
