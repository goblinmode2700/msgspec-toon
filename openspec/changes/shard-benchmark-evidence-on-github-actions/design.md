## Context

See `proposal.md` — Why. `scripts/release-report.py` executes 36 timing cells in a serial
list: four typed sizes, four shapes by four sizes for codec comparisons, and four shapes by
four sizes for end-to-end integration. Each cell already delegates calibration and ten
measured processes to `benches/_workers.py`; the estimator is the mean across those workers.

The repository's release workflow already provides the needed distribution primitive. It
builds one identified artifact, fans work out through a GitHub Actions matrix, uploads
immutable results, and collects an exact digest-bound set before publication. GitHub's own
matrix documentation shows the same producer/artifact/consumer pattern and provides
`max-parallel`. The prior-art record is
`docs/implementation-spec/prior-art-github-actions-benchmark-sharding-2026-08-10.md`.

## Goals / Non-Goals

**Goals:**

- Reduce the time from benchmark start to validated report inputs by at least twofold.
- Preserve C9 exactly: one calibration process, ten measured processes, arithmetic mean,
  raw worker observations, and no minimum estimator.
- Make partial, duplicated, stale, or mixed-host-within-cell evidence impossible to publish.
- Reuse native GitHub Actions matrices and the existing artifact collector model.
- Keep local serial execution available as the reference path and developer fallback.

**Non-Goals:**

- Reducing the number of measurements or changing the statistical design.
- Treating different GitHub-hosted VMs as one homogeneous machine.
- Splitting one timing cell or same-session comparison across runners.
- Moving token measurement, R/ggplot rendering, unit tests, conformance, or G2 merely to
  make the matrix larger.
- Adding a remote queue, service, database, custom runner agent, or orchestration harness.
- Provisioning Hetzner, GCP, larger GitHub runners, or self-hosted runners in this change.
- Running untrusted pull-request code on infrastructure that holds credentials or private data.

## Decisions

### 1. The unit of distribution is a complete experimental cell

A cell is one suite, shape, and record-count combination. Its benchmarked implementations,
calibration, warmup, and ten measurement workers execute sequentially on the same runner.
The initial manifest contains 36 cells:

| Suite | Factors | Cells |
|---|---|---:|
| typed | 4 record counts | 4 |
| codec | 4 shapes × 4 record counts | 16 |
| integration | 4 shapes × 4 record counts | 16 |

This preserves common-mode host effects inside every comparison and changes only scheduling.

Alternative: distribute the ten workers of one cell across VMs. Rejected because VM identity
would become part of the estimator and invalidate the same-run comparison.

### 2. Start with twelve Linux shards containing three cells each

A checked-in manifest assigns every cell exactly once to one of twelve `ubuntu-22.04`
standard-runner shards. `max-parallel: 12` bounds concurrency. The assignment is balanced
from measured cell durations, not alphabetical order, so one large integration cell does not
define the critical path.

Alternative: one matrix job per cell. Rejected for the first version because 36 repeated
environment setups add avoidable runner-minutes and increase scheduling variance. The
manifest can change shard count later without changing the evidence schema.

### 3. Build or select one wheel before fan-out

One upstream job produces or selects the exact Linux x86_64 ABI3 release wheel and records
its SHA-256, source revision, package version, and lock-file digest. Every shard installs
that same wheel with the same locked benchmark dependency set. Each cell result repeats those
identities plus its cell ID, runner image, CPU model, kernel, Python version, dependency
versions, loop counts, worker observations, and elapsed time.

Alternative: build independently on every shard. Rejected because compile variation wastes
time and makes artifact identity harder to prove.

### 4. Fan-in validates an exact set before aggregation

Every shard uploads one immutable JSON artifact. The collector derives the expected cell set
from the checked-in manifest and rejects:

- a missing or duplicate shard or cell;
- a cell assigned to a different shard;
- schema, source revision, package version, wheel digest, lock digest, estimator, worker
  count, or sample-count disagreement;
- a cell without all required raw worker observations;
- a cell whose comparators ran on different runner identities.

Only after this check does the existing report assembly consume the 36 results. The
collector writes a canonical ordering, so scheduling order cannot change report bytes except
for declared timestamps and environment fields.

Alternative: concatenate downloaded JSON in the workflow. Rejected because artifact download
digest validation alone does not prove semantic completeness or matching benchmark identity.

### 5. Qualification precedes canonical adoption

The first phase runs a serial control and the distributed path from the same revision and
wheel. Qualification checks exact cell coverage, gate verdicts, bytes, loop-policy metadata,
and raw-observation schema. It also runs a source-identical A/A canary within each shard to
detect a false regression caused by the new execution path.

Absolute times from different matrix VMs are not merged into claims that require one physical
host. Cross-size curves are labelled distributed and non-canonical until three clean workflow
runs show stable gate decisions and no systematic shard-assignment effect. The single-runner
report remains the release source of record until that acceptance record is committed.

Alternative: replace the release report immediately because every cell is internally valid.
Rejected because cross-cell absolute comparisons can still reflect different VM classes or
contention.

### 6. Measure wall time separately from benchmark time

The workflow records benchmark-stage start and fan-in completion timestamps, per-shard setup
and measurement time, total runner-minutes, queue time when observable, and critical-path
shard. Acceptance requires the median benchmark-stage wall time across three runs to be at
least twofold faster than the serial control for the same revision and wheel. Queue time is
reported but excluded because it is not controlled by the implementation.

No timing produced by a benchmark cell includes workflow setup, checkout, download, install,
artifact upload, or fan-in work.

### 7. Use public standard runners with no secret-bearing path

The initial workflow runs on standard GitHub-hosted Linux runners. The public repository does
not incur Actions minute charges for those runners under GitHub's current policy, although
artifact storage remains a resource to bound. Raw artifacts use short retention and contain
only generated benchmark data and environment metadata. No customer data, secret, or
self-hosted runner is involved.

Alternative: use Hetzner now. Deferred because provisioning, isolation, updates, runner
registration, and untrusted-code policy cost more setup time than this first experiment.

## Risks / Trade-offs

- **Different VMs distort cross-cell absolute times** → Keep cells self-contained, fingerprint
  hosts, qualify before adoption, and retain the single-runner canonical path.
- **Matrix queueing erases the expected speedup** → Report queue time separately and use a
  bounded twelve-shard matrix; do not claim a wall-time win until three runs pass the target.
- **Repeated setup increases total compute** → Build once, install one wheel, group three
  balanced cells per shard, and publish total runner-minutes beside wall time.
- **A fast shard can hide missing work** → Derive the exact expected set from the manifest and
  make fan-in fail on missing or duplicate identities.
- **Runner image drift changes results** → Pin the Ubuntu image label, record the resolved image
  metadata, and never compare figures without their environment fingerprint.
- **Artifact storage grows** → Upload compact JSON only and set a short explicit retention.
- **The matrix becomes another harness** → Limit workflow YAML to native matrix and artifact
  plumbing; all cell selection, timing, validation, and aggregation stay in repository code.

## Migration Plan

1. Add the manifest, selectable local cell runner, evidence schema, and fail-closed collector.
2. Prove that running all cells locally through the new interface reproduces the current
   report inputs exactly apart from declared execution metadata.
3. Add the manual GitHub Actions workflow with twelve standard Linux shards and no release
   dependency.
4. Run three paired serial/distributed qualification workflows and publish wall time,
   runner-minutes, completeness, A/A, and gate-equivalence results.
5. If qualification passes, allow release-report generation to consume validated distributed
   evidence. Keep the serial path available for rollback.
6. If qualification fails, retain the artifacts, record the failed hypothesis, and leave the
   canonical release path unchanged.

Rollback removes the workflow trigger and distributed input from release generation. It does
not touch codec code, benchmark math, or the serial report path.
