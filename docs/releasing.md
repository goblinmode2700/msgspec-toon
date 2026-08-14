# Releasing msgspec-toon

The release workflow builds each distribution once, verifies the installed artifacts on their
target runners, and publishes only the complete digest-matched set. Do not upload a locally rebuilt
file under the same version.

The performance manifest fixes each pair count and sampling design. Python records raw timings only.
R owns the estimates, simultaneous Bonferroni intervals, classifications, and gate decisions.
R also plans power for the complete family of confirmatory endpoints. A gating family must meet its
declared familywise power target.

For a non-inferiority endpoint with regression margin `M`, R classifies an established regression
only when the simultaneous interval's lower bound is greater than `M`. It classifies established
non-inferiority only when the upper bound is less than `M`. An interval that contains `M` is
`INCONCLUSIVE`: it is not a regression, does not block a release, and must not be reported as proof
of non-inferiority. A gating improvement endpoint still fails when it does not establish its
predeclared improvement.

## Required repository configuration

Configure a protected GitHub environment named `pypi`. Limit deployment to release maintainers and
version tags as appropriate for the repository.

Configure the `msgspec-toon` project on PyPI with this Trusted Publisher identity:

| Field | Value |
|---|---|
| Owner | `goblinmode2700` |
| Repository | `msgspec-toon` |
| Workflow | `wheels.yml` |
| Environment | `pypi` |

The publication job alone has `id-token: write`. It uses the official PyPA publishing action,
which creates PyPI publish attestations by default. The workflow does not read a PyPI API token.

## Qualification sequence

1. Run `make qualify` locally. It rebuilds the release extension and runs Python and Rust checks,
   the complete TOON corpus, containment and support-matrix tests, and the independent G2
   allocation proof.
2. Push the candidate without a version tag. The `Validate` workflow must pass on the default
   branch.
3. Run the wheel workflow with publication disabled. All twelve wheels and the source distribution
   must build, verify, and enter the combined manifest. The release evidence job then installs the
   verified Linux x86-64 CPython 3.13 ABI3 wheel. The job verifies the installed extension and
   builds the `GUARD_TAG` baseline. Then it runs `make release-performance` under the inference
   contract above.
4. Inspect the release evidence. Its package version, source revision, current-extension digest,
   raw timings, and R analyzer digest must match the candidate. The workflow artifact contains the
   paired guard raw/result files and the absolute-report raw/result files.
5. Create the matching version tag only after the candidate is approved for publication.

The publish job consumes `verified-release` without running a build tool. A failed validation,
build, verification, R-owned guard `FAIL` (an established regression or an unmet improvement
endpoint), absolute-report release gate, evidence, or collection job prevents publication. An
`INCONCLUSIVE` non-inferiority result remains visible in the evidence but is not an established
regression. Run the guard and absolute report serially on one runner. Parallel execution creates
measurement contention.

For a version tag, the GitHub release contains both raw files and both R result files. It also
contains the benchmark-wheel verification record and the combined release manifest.

## Failure and rollback

Do not reuse a package version after any file reaches PyPI. Fix the problem under the next beta
serial. If a published release is unsafe, yank it on PyPI and retain the qualification evidence and
reason. Do not restore the API-token workflow as an automatic fallback when Trusted Publishing is
unavailable.
