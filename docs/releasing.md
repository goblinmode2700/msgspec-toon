# Releasing msgspec-toon

The release workflow builds each distribution once, verifies the installed artifacts on their
target runners, and publishes only the complete digest-matched set. Do not upload a locally rebuilt
file under the same version.

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
   must build, verify, and enter the combined manifest.
4. Inspect the release evidence. Its package version and source revision must match the candidate.
5. Create the matching version tag only after the candidate is approved for publication.

The publish job consumes `verified-release` without running a build tool. A failed validation,
build, verification, evidence, or collection job prevents publication.

## Failure and rollback

Do not reuse a package version after any file reaches PyPI. Fix the problem under the next beta
serial. If a published release is unsafe, yank it on PyPI and retain the qualification evidence and
reason. Do not restore the API-token workflow as an automatic fallback when Trusted Publishing is
unavailable.
