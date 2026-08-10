# Prior art: GitHub Actions benchmark sharding

## Pattern

The pattern is **fan-out/fan-in CI benchmark execution with immutable per-shard
artifacts**. A deterministic manifest assigns complete experimental cells to matrix jobs.
Each job emits raw evidence. One collector rejects an incomplete or mixed run before it
generates a report.

## Survey

| Source | Tier | What it proves | Fit here |
|---|---|---|---|
| This repository's `.github/workflows/wheels.yml` | A: proven locally and in production | A native Actions matrix can build once, identify artifacts by revision and digest, verify them on target-native jobs, collect an exact set, and fail closed before publication. | Port the matrix, immutable-artifact, digest, and collector pattern. |
| GitHub Actions matrix and artifact documentation | A: platform authority | A matrix creates independent jobs, `max-parallel` bounds concurrency, matrix outputs can feed later jobs, and workflow artifacts pass immutable data between jobs. | Adopt the platform primitive. Do not add a scheduler. |
| `msgspec==0.21.1` source and CI in `.git/prior-art/msgspec-0.21.1` | A: upstream implementation | Mature compiled Python projects select benchmark cases explicitly and use Actions matrices and artifacts for independent build/test work. | Port explicit case selection; do not port its benchmark estimator or result model. |

## Verdict

**PORT.** Extend the existing benchmark entry points with deterministic cell selection and
raw-result output. Use a native GitHub Actions matrix for fan-out and the release workflow's
existing verified-artifact collector pattern for fan-in. Keep `benches/_timing.py` as the
only timing implementation.

Do not hand-roll a queue, remote worker protocol, database, scheduler, or cloud control
plane. Do not split one cell's calibration and ten measured workers across hosts. Do not
make cross-host absolute times canonical until a measured qualification phase shows that
the distributed design preserves the report's intended claims.

## Sources

- GitHub, “Running variations of jobs in a workflow”:
  <https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/run-job-variations>
- GitHub, “Store and share data with workflow artifacts”:
  <https://docs.github.com/en/actions/tutorials/store-and-share-data>
- GitHub, “GitHub Actions billing”:
  <https://docs.github.com/en/billing/concepts/product-billing/github-actions>
- GitHub, “Actions limits”:
  <https://docs.github.com/en/actions/reference/limits>
