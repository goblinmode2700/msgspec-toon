# Prior art: measuring two builds of one PyO3 extension against each other

Written 2026-08-06, after the F-12 A/B rework. Motivating question: the harness cannot
resolve a 4-5% encode change at 16 and 64 records, because the variance lives between
processes, not inside them. The tempting fix was to load the frozen baseline and the
current build into one process and alternate batch by batch. This note is why that is
the wrong first move, and what the exact blocker is if we ever do it.

## Measured decomposition (the reason any of this came up)

Four processes, twelve in-process samples each, encode path:

| Size | Within one process (CV) | Between processes |
|---|---|---|
| 16 records | 0.74% | 2.4% spread |
| 64 records | 1.07% | 4.1% spread, monotonically rising |

At n=64 the four process minima climbed 7.399, 7.540, 7.584, 7.699 microseconds over
about a minute. The measurement is precise; the gap between measurements is not.

## Pattern 1: the Rust metaprogramming blocker

Canonical name: **a proc-macro attribute argument must be a literal token, and Rust
expands `env!` / `concat!` after attribute parsing, so a name cannot be computed from
build configuration.**

Verified against the pinned `pyo3 0.29.0` source rather than inferred:

- `pyo3-macros-backend/src/attributes.rs:212` — `NameLitStr::parse` calls
  `input.parse::<LitStr>()`. The argument must be a string *literal*; `env!("X")` is a
  macro invocation and fails to parse.
- `pyo3-macros-backend/src/module.rs:520` — `let pyinit_symbol = format!("PyInit_{name}")`.
  The exported entry point is baked at macro-expansion time from that literal.
- The PyO3 guide states the filename requirement: the module name must match the `.so`
  name or import fails with
  `ImportError: dynamic module does not define module export function (PyInit_...)`.

So the extension's name is fixed per source file, and there is no attribute-level way to
parameterize it.

Ecosystem workarounds for name-from-configuration, in order of weight:

| Approach | Verdict here |
|---|---|
| `#[cfg]`-selected duplicate `#[pymodule]` shims, one per name | The right answer. `#[cfg]` on an item is applied before macro expansion, costs about six lines, needs no dependency |
| `#[cfg_attr(..., pyo3(name = "..."))]` | Unreliable. Attributes *consumed by* a proc macro are not cfg-expanded first; this is why the built-in `cfg_eval` exists |
| `paste!` / `mashup` (dtolnay) | The standard identifier-concatenation crates, and what `concat_idents!` should have been — `concat_idents!` is nightly-only and cannot define new items. Not needed for this shape |
| `build.rs` codegen emitting the shim | Works, heaviest option, hardest to review |

Residual cost even with the cheap answer: the shim must exist in the **baseline** source,
so the frozen `v0.1.0-conformant` tag would have to be patched at build time. `make
baseline` already builds from a throwaway git worktree, so the patch could live there and
be documented as a build-level deviation. The artifact would then no longer be the tag's
own build.

## Pattern 2: what we actually want, and how mature harnesses do it

Canonical name: **paired benchmarking with process-level replication and a significance
test.**

| Project | Approach |
|---|---|
| `pyperf` (psf) | One calibration worker, then ~20 worker *processes*, each warming up and discarding the first value. Comparison via a two-sample two-tailed Student t-test at alpha 0.95; non-significant rows are hidden rather than reported. Ships `pyperf system tune` for jitter |
| `criterion.rs` | Bootstrap confidence intervals, saved baselines, explicit change detection against the stored baseline |
| `hyperfine` | Process-level, warmup runs, outlier detection, statistical summary |
| `asv` | Benchmarks across commits in separate environments |

The convergent finding: every mature harness treats between-process variance as a fact of
life and answers it with **replication plus a significance test**, not by loading two
builds into one process. None of them offers a two-versions-in-one-process mode.

Where that idea does exist, it is explicitly a hack with a hole in exactly our spot:

- `dlmopen` link-map namespaces load one object twice, but the API is glibc-only (absent
  on macOS), caps at 16 namespaces, and breaks when libraries assume process-uniqueness.
- `mitsuhiko/multiversion` rewrites imports to version-encoded names — a documented hack,
  and its README does not address C extension modules at all.

## Verdict

```
PATTERN: paired benchmarking with process-level replication and significance testing
         (blocked sub-pattern: compile-time-literal module name in a proc-macro attribute)
MATURE:  pyperf     — 20 worker processes, calibrated loops, warmup discard, t-test @ 0.95
         criterion  — bootstrap CI, saved baseline, change detection
         hyperfine  — warmups, outlier detection, process-level replication
LOCAL:   benches/_timing.py — min of 7 autoranged batches (the thing being replaced)
         benches/ab.py      — B C C B blocks, median ratio vs an observed spread
VERDICT: port pyperf's methodology into ab.py; do NOT hand-roll the dual-module trick
TAKE:    many short alternating worker processes; discard the warmup value; a real
         significance test (t-test at 0.95, or a bootstrap CI as criterion does) in place
         of the current compare-median-to-spread heuristic
REJECT:  loading two builds in one process — no mature harness does it, macOS lacks
         dlmopen, and it requires patching a frozen release tag to get a second module
         name. Revisit only if something needs sub-1% resolution, e.g. candidate E3
REJECT:  adopting pyperf as a dependency — it wants to own the process model and the
         result format, and this project already has a corpus runner, a report
         generator, and a frozen-baseline environment. Port the method, not the package
```

## Divergence worth deciding separately

`_timing.py` reports the **minimum** of seven batches. `pyperf` deliberately reports the
mean across many processes and argues the minimum is unstable and biased, because it
rewards whichever run happened to dodge the scheduler. Both positions are defensible for
different questions — the minimum estimates the machine's best case, the mean estimates
what a user experiences. The current harness quietly takes the first position. If the
methodology is revisited, that choice should be made deliberately and stated in the
report rather than inherited.

## Sources

- [PyO3 module guide](https://pyo3.rs/main/module)
- [pymodule attribute docs](https://docs.rs/pyo3/latest/pyo3/attr.pymodule.html)
- [pyperf run_benchmark](https://pyperf.readthedocs.io/en/latest/run_benchmark.html)
- [pyperf analyze / compare_to](https://pyperf.readthedocs.io/en/latest/analyze.html)
- [dtolnay/paste](https://docs.rs/paste)
- [dtolnay/mashup](https://github.com/dtolnay/mashup)
- [mitsuhiko/multiversion](https://github.com/mitsuhiko/multiversion)
- [dlopen(3) / dlmopen man page](https://man7.org/linux/man-pages/man3/dlopen.3.html)
- [rust-lang/rust#22250 — process cfg_attr during expansion](https://github.com/rust-lang/rust/issues/22250)
