# Benchmarks

Generated from [`conformance/report.json`](conformance/report.json) on 2026-08-13T21:00:09.826416+00:00.

The report keeps time and token results separate. It does not create a combined score.

## Speed and token Pareto set

![Empirical speed-token Pareto set](docs/assets/benchmarks/pareto-set-change.png)

Pareto status is conservative and calculated independently for each payload shape and record count. A speed dominance edge requires non-overlapping simultaneous intervals. Interval overlap is unresolved, not neutral.

## Codec time

![Codec elapsed times](docs/assets/benchmarks/codec-times.png)

The chart shows encode, decode, and total elapsed time. Each bar is R's arithmetic mean of per-process means, in microseconds.

### Uniform records at 4,096 records

| Codec | Encode (µs) | Decode (µs) | Total (µs) |
|---|---:|---:|---:|
| msgspec-toon | 555.11 | 1,033.01 |  1,588.12 |
| msgspec JSON | 213.32 | 827.35 |  1,040.67 |
| toons (Rust) | 6,642.79 | 3,100.84 |  9,743.63 |
| python-toon | 23,729.70 | 30,228.37 |  53,958.07 |

## End-to-end time

![JSON to TOON to JSON elapsed times](docs/assets/benchmarks/integration-times.png)

The API rows run in one Python process. The CLI row includes two process launches.

## Token count

![Absolute token counts](docs/assets/benchmarks/token-counts.png)

Compact JSON appears in every facet. This gives a direct reference for each shape and size.

### Uniform records at 4,096 records

| Wire format | o200k_base tokens |
|---|---:|
| compact JSON | 97,308 |
| msgspec-toon canonical | 60,455 |
| msgspec-toon indent 1 | 56,359 |
| msgspec-toon indent 4 | 60,455 |
| msgspec-toon tab | 60,456 |
| msgspec-toon pipe | 60,456 |
| toons (Rust) | 121,884 |
| python-toon | 121,884 |

## Method

- The timing estimator is the arithmetic mean across 10 worker processes.
- Each worker reports 3 samples after warm-up.
- The error bars use simultaneous Bonferroni t intervals.
- Confirmatory families use holm within each declared gate family.
- The benchmark never uses the minimum time.
- Report rows are randomized within each complete process panel.
- Python records raw timings; R owns aggregation, intervals, and decisions.
- Token counts are deterministic under the named tokenizer.
- The environment uses Python 3.13.1 and msgspec 0.21.1.
- The build is a release `abi3-py313` build.
- The freshness check rejects stale and instrumented extensions.
- R summaries are in [`conformance/report.json`](conformance/report.json). Raw timings are in `benches/report-performance-raw.json`.
- Reproduce with `uv sync --group bench --locked && make g2 && make public-report`.

Results depend on the machine, payload, and package versions. Compare values from the same generated run.
