#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(ggplot2)
  library(jsonlite)
  library(scales)
})

args <- commandArgs(trailingOnly = TRUE)
input <- if (length(args)) args[[1]] else "conformance/report.json"
report <- fromJSON(input, simplifyVector = FALSE)
out_dir <- "docs/assets/benchmarks"
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

# Personal-project chart tokens. The palette and density follow the owner's
# established visual system, but no company identifiers or proprietary assets
# are embedded in this repository.
ink <- "#202326"
paper <- "#F7F7F5"
grid <- "#D9DBDC"
wine <- "#7D122D"
green <- "#3A8F63"
amber <- "#C58A22"
blue <- "#4776B8"
mauve <- "#8662A8"

theme_report <- function() {
  theme_minimal(base_family = "sans", base_size = 11) +
    theme(
      plot.background = element_rect(fill = paper, colour = NA),
      panel.background = element_rect(fill = paper, colour = NA),
      panel.grid.minor = element_blank(),
      panel.grid.major = element_line(colour = grid, linewidth = 0.35),
      plot.title = element_text(colour = ink, face = "bold", size = 16),
      plot.subtitle = element_text(colour = ink, size = 10.5),
      plot.caption = element_text(colour = "#666B70", size = 8, hjust = 0),
      axis.title = element_text(colour = ink, face = "bold"),
      axis.text = element_text(colour = ink),
      strip.text = element_text(colour = ink, face = "bold"),
      legend.position = "bottom",
      legend.title = element_blank()
    )
}

save_plot <- function(plot, name, width = 9, height = 5.5) {
  ggsave(file.path(out_dir, paste0(name, ".png")), plot,
         width = width, height = height, dpi = 180, bg = paper)
}

codec_rows <- do.call(rbind, lapply(report$benchmarks_codecs_same_run, function(row) {
  do.call(rbind, lapply(c("msgspec_toon", "toons_rust", "python_toon"), function(codec) {
    data.frame(
      records = row$records,
      codec = codec,
      direction = c("Encode", "Decode"),
      relative_time = c(
        row$encode_us[[codec]] / row$encode_us$msgspec_toon,
        row$decode_us[[codec]] / row$decode_us$msgspec_toon
      )
    )
  }))
}))
codec_rows$codec <- factor(
  codec_rows$codec,
  levels = c("msgspec_toon", "toons_rust", "python_toon"),
  labels = c("msgspec-toon", "toons (Rust)", "python-toon")
)

p_speed <- ggplot(codec_rows, aes(records, relative_time, colour = codec, group = codec)) +
  geom_hline(yintercept = 1, colour = ink, linewidth = 0.45) +
  geom_line(linewidth = 0.9) +
  geom_point(size = 2.4) +
  facet_wrap(~direction) +
  scale_x_log10(breaks = c(16, 64, 512, 4096), labels = comma) +
  scale_y_log10(labels = label_number(suffix = "x")) +
  scale_colour_manual(values = c(wine, green, amber)) +
  labs(
    title = "Codec speed: time relative to msgspec-toon",
    subtitle = "Lower is faster. Each point is the mean across ten worker processes.",
    x = "Records", y = "Relative time",
    caption = "Source: conformance/report.json. Release abi3 build; same-run comparisons."
  ) + theme_report()
save_plot(p_speed, "codec-speed")

token_formats <- c("toon_comma", "toons_rust", "python_toon")
token_labels <- c("msgspec-toon", "toons (Rust)", "python-toon")
token_rows <- do.call(rbind, lapply(report$token_efficiency$rows, function(row) {
  do.call(rbind, Map(function(fmt, label) {
    data.frame(
      shape = row$shape,
      records = row$records,
      format = label,
      tokens_vs_json = row$formats[[fmt]]$tokens_vs_json
    )
  }, token_formats, token_labels))
}))
token_rows$format <- factor(token_rows$format, levels = token_labels)

p_tokens <- ggplot(token_rows, aes(records, tokens_vs_json, colour = format, group = format)) +
  geom_hline(yintercept = 1, colour = ink, linewidth = 0.55) +
  geom_line(linewidth = 0.85) +
  geom_point(size = 2.3) +
  facet_wrap(~shape, scales = "free_x") +
  scale_x_log10(breaks = c(16, 64, 512, 4096), labels = comma) +
  scale_y_continuous(labels = label_number(suffix = "x", accuracy = 0.01)) +
  scale_colour_manual(values = c(wine, green, amber)) +
  labs(
    title = "Token cost relative to compact JSON",
    subtitle = "Below 1.00x saves tokens. Irregular shapes remain visible because TOON loses there.",
    x = "Records", y = "Tokens / compact JSON tokens",
    caption = paste0("Tokenizer: ", report$token_efficiency$tokenizers$primary,
                     " via tiktoken ", report$token_efficiency$tokenizers$tiktoken_version, ".")
  ) + theme_report()
save_plot(p_tokens, "token-cost-vs-json", 10, 6)

uniform_tokens <- Filter(function(row) row$shape == "uniform-records", report$token_efficiency$rows)
quadrant <- do.call(rbind, Map(function(codec, token) {
  ours <- codec$encode_us$msgspec_toon + codec$decode_us$msgspec_toon
  competitor <- codec$encode_us$toons_rust + codec$decode_us$toons_rust
  data.frame(
    records = codec$records,
    speed_advantage = competitor / ours,
    token_advantage = 1 / token$formats$toon_comma$tokens_vs_json
  )
}, report$benchmarks_codecs_same_run, uniform_tokens))
quadrant$label_x <- quadrant$speed_advantage * c(1.00, 1.025, 0.975, 0.985)
quadrant$label_y <- quadrant$token_advantage + c(0.025, -0.020, 0.035, 0.020)

p_quadrant <- ggplot(quadrant, aes(speed_advantage, token_advantage, label = records)) +
  annotate("rect", xmin = 1, xmax = Inf, ymin = 1, ymax = Inf,
           fill = green, alpha = 0.10) +
  geom_vline(xintercept = 1, colour = ink, linewidth = 0.5) +
  geom_hline(yintercept = 1, colour = ink, linewidth = 0.5) +
  geom_path(colour = wine, linewidth = 0.9) +
  geom_point(colour = wine, fill = paper, shape = 21, size = 4, stroke = 1.2) +
  geom_label(aes(x = label_x, y = label_y), colour = ink, fill = paper,
             linewidth = 0, family = "mono", size = 3) +
  scale_x_log10(labels = label_number(suffix = "x", accuracy = 0.1)) +
  scale_y_continuous(labels = label_number(suffix = "x", accuracy = 0.01)) +
  labs(
    title = "The useful quadrant: faster and fewer tokens",
    subtitle = paste(
      "Uniform nested records. Right: faster round-trip than the fastest competing TOON codec.",
      "Up: fewer o200k_base tokens than compact JSON.", sep = "\n"
    ),
    x = "toons round-trip time / msgspec-toon round-trip time",
    y = "compact JSON tokens / msgspec-toon tokens",
    caption = "Labels are record counts. Green is the desired quadrant (both ratios > 1)."
  ) + theme_report() + theme(legend.position = "none")
save_plot(p_quadrant, "efficiency-quadrant", 9, 5.8)

integration <- do.call(rbind, lapply(report$benchmarks_integration_same_run, function(row) {
  data.frame(
    records = row$records,
    pipeline = c("msgspec-toon in process", "python-toon in process", "python-toon CLI (2 processes)"),
    microseconds = unlist(row$roundtrip_us, use.names = FALSE)
  )
}))
integration$pipeline <- factor(integration$pipeline, levels = unique(integration$pipeline))
p_integration <- ggplot(integration, aes(records, microseconds, colour = pipeline, group = pipeline)) +
  geom_line(linewidth = 0.9) + geom_point(size = 2.4) +
  scale_x_log10(breaks = c(16, 64, 512), labels = comma) +
  scale_y_log10(labels = label_number(suffix = " us", big.mark = ",")) +
  scale_colour_manual(values = c(wine, mauve, blue)) +
  labs(
    title = "JSON -> TOON -> JSON integration cost",
    subtitle = "The CLI row includes two process launches. It is a deployment comparison, not a pure codec gate.",
    x = "Records", y = "Round-trip time (log scale)",
    caption = "Input and output are compact JSON with value-equivalence assertions."
  ) + theme_report()
save_plot(p_integration, "integration-roundtrip")

fmt <- function(x, digits = 2) format(round(x, digits), nsmall = digits, big.mark = ",")
last_codec <- tail(report$benchmarks_codecs_same_run, 1)[[1]]
last_uniform <- tail(uniform_tokens, 1)[[1]]
last_integration <- tail(report$benchmarks_integration_same_run, 1)[[1]]

md <- c(
  "# Benchmarks",
  "",
  paste0("Generated from [`conformance/report.json`](conformance/report.json) on ",
         report$generated_at, "."),
  "",
  "The charts publish both axes that matter: conversion time and tokens versus compact JSON. The JSON token baseline is not inferred from byte size. It is measured with the named tokenizer.",
  "",
  "![Speed and token quadrant](docs/assets/benchmarks/efficiency-quadrant.png)",
  "",
  "## Headline at 4,096 uniform records",
  "",
  "| Measure | Result |",
  "|---|---:|",
  paste0("| Canonical TOON tokens / compact JSON tokens | ", fmt(last_uniform$formats$toon_comma$tokens_vs_json), "x |"),
  paste0("| Round-trip speed / `toons` | ",
         fmt((last_codec$encode_us$toons_rust + last_codec$decode_us$toons_rust) /
             (last_codec$encode_us$msgspec_toon + last_codec$decode_us$msgspec_toon)), "x faster |"),
  paste0("| Output bytes / compact JSON bytes | ",
         fmt(last_codec$output_bytes$msgspec_toon_tabular_4_1 /
             last_codec$output_bytes$json_compact), "x |"),
  "",
  "These rows describe the uniform nested-record shape that TOON 4.1 can tabularize. They do not generalize to every document.",
  "",
  "## Token cost by shape",
  "",
  "![Token cost relative to compact JSON](docs/assets/benchmarks/token-cost-vs-json.png)",
  "",
  "Canonical TOON saves tokens for uniform, string-heavy, and numeric-heavy records. It costs more tokens than compact JSON for the measured irregular documents. Use JSON for those shapes when context-window cost is the priority.",
  "",
  "## Codec speed",
  "",
  "![Codec speed](docs/assets/benchmarks/codec-speed.png)",
  "",
  "Each codec parses its own output. Older codecs emit a larger fallback form for the nested-record payload. The byte count is part of the result and is present in the raw report.",
  "",
  "## Integration cost",
  "",
  "![Integration round-trip](docs/assets/benchmarks/integration-roundtrip.png)",
  "",
  paste0("At ", last_integration$records, " records, JSON -> TOON -> JSON took ",
         fmt(last_integration$roundtrip_us$msgspec_toon_in_process), " us in process with msgspec-toon, ",
         fmt(last_integration$roundtrip_us$python_toon_in_process), " us through the python-toon API, and ",
         fmt(last_integration$roundtrip_us$python_toon_two_process_cli), " us through two CLI processes."),
  "",
  "The CLI row measures a real architectural cost. It is not used as a pure codec performance gate.",
  "",
  "## Method",
  "",
  paste0("- Environment: Python ", report$environment$python, ", msgspec ", report$environment$msgspec,
         ", ", report$environment$platform, "."),
  paste0("- Estimator: mean across ", report$evidence_methodology$workers,
         " worker processes; each worker reports ",
         report$evidence_methodology$samples_per_worker,
         " post-warmup samples. The minimum is not used."),
  paste0("- Tokenizer: tiktoken `", report$token_efficiency$tokenizers$primary, "` ",
         report$token_efficiency$tokenizers$tiktoken_version, "."),
  "- Build: release `abi3-py313`; the freshness check rejects stale or instrumented extensions.",
  "- Raw evidence: [`conformance/report.json`](conformance/report.json).",
  "- Reproduce: `uv sync --group bench --locked && make g2 && make public-report`.",
  "",
  "Benchmark results depend on the machine, payload, and versions. Compare rows from the same generated run."
)
writeLines(md, "BENCHMARKS.md")
