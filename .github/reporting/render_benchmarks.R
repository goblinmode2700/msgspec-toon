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

ink <- "#202326"
paper <- "#F7F7F5"
grid <- "#D9DBDC"
blue <- "#527EAD"
sky <- "#9BC7E3"
orange <- "#F58518"
wine <- "#7D122D"
green <- "#3A8F63"
mauve <- "#8662A8"

theme_report <- function() {
  theme_minimal(base_family = "sans", base_size = 11) +
    theme(
      plot.background = element_rect(fill = paper, colour = NA),
      panel.background = element_rect(fill = paper, colour = NA),
      panel.grid.minor = element_blank(),
      panel.grid.major.y = element_blank(),
      panel.grid.major.x = element_line(colour = grid, linewidth = 0.35),
      plot.title = element_text(colour = ink, face = "bold", size = 16),
      plot.subtitle = element_text(colour = ink, size = 10.5),
      plot.caption = element_text(colour = "#666B70", size = 8, hjust = 0),
      axis.title = element_text(colour = ink, face = "bold"),
      axis.text = element_text(colour = ink),
      strip.text = element_text(colour = ink, face = "bold"),
      strip.background = element_rect(fill = "#ECEDEB", colour = NA),
      legend.position = "bottom"
    )
}

save_plot <- function(plot, name, width, height) {
  ggsave(
    file.path(out_dir, paste0(name, ".png")),
    plot,
    width = width,
    height = height,
    dpi = 180,
    bg = paper
  )
}

mean_ci <- function(values) {
  values <- unlist(values, use.names = FALSE)
  n <- length(values)
  estimate <- mean(values)
  half_width <- qt(0.975, df = n - 1) * sd(values) / sqrt(n)
  c(mean = estimate, lower = max(0, estimate - half_width), upper = estimate + half_width)
}

shape_levels <- c("uniform-records", "string-heavy", "numeric-heavy", "irregular")
record_levels <- c("16", "64", "512", "4096")

codec_ids <- c("msgspec_toon", "msgspec_json_context", "toons_rust", "python_toon")
codec_labels <- c("msgspec-toon", "msgspec JSON", "toons (Rust)", "python-toon")
phase_ids <- c("encode", "decode", "total")

codec_times <- do.call(rbind, lapply(report$benchmarks_codecs_same_run, function(row) {
  if (is.null(row$worker_observations)) {
    stop("The report has no worker observations. Regenerate the report.")
  }
  do.call(rbind, Map(function(codec_id, codec_label) {
    do.call(rbind, lapply(phase_ids, function(phase) {
      values <- lapply(row$worker_observations, function(worker) {
        if (phase == "encode") return(worker$encode_us[[codec_id]])
        if (phase == "decode") return(worker$decode_us[[codec_id]])
        worker$encode_us[[codec_id]] + worker$decode_us[[codec_id]]
      })
      interval <- mean_ci(values)
      data.frame(
        shape = row$shape,
        records = as.character(row$records),
        codec = codec_label,
        phase = phase,
        mean_us = interval[["mean"]],
        lower_us = interval[["lower"]],
        upper_us = interval[["upper"]]
      )
    }))
  }, codec_ids, codec_labels))
}))
codec_times$shape <- factor(codec_times$shape, levels = shape_levels)
codec_times$records <- factor(codec_times$records, levels = record_levels)
codec_times$codec <- factor(codec_times$codec, levels = rev(codec_labels))
codec_times$phase <- factor(codec_times$phase, levels = rev(phase_ids))

phase_position <- position_dodge(width = 0.78)
p_codec_times <- ggplot(codec_times, aes(mean_us, codec, fill = phase)) +
  geom_col(position = phase_position, width = 0.72) +
  geom_errorbar(
    aes(xmin = lower_us, xmax = upper_us),
    position = phase_position,
    orientation = "y",
    width = 0.16,
    colour = ink,
    linewidth = 0.3
  ) +
  facet_grid(rows = vars(shape), cols = vars(records), scales = "free_x") +
  scale_fill_manual(
    values = c(encode = blue, decode = sky, total = orange),
    breaks = phase_ids,
    labels = c(encode = "encode", decode = "decode", total = "total")
  ) +
  scale_x_continuous(labels = label_number(big.mark = ","), expand = expansion(mult = c(0, 0.05))) +
  labs(
    title = "TOON codec time by shape and size",
    subtitle = "Bars show direct elapsed time. Error bars show 95% confidence intervals.",
    x = expression(paste("Time (", mu, "s)")),
    y = NULL,
    fill = NULL,
    caption = paste0(
      "Each value is the arithmetic mean across ",
      report$evidence_methodology$workers,
      " worker processes. Each record-count column has its own linear time scale."
    )
  ) +
  theme_report()
save_plot(p_codec_times, "codec-times", 15, 11)

integration_ids <- c(
  "msgspec_toon_in_process",
  "python_toon_in_process",
  "python_toon_two_process_cli"
)
integration_labels <- c(
  "msgspec-toon API",
  "python-toon API",
  "python-toon CLI (2 processes)"
)
integration_times <- do.call(rbind, lapply(
  report$benchmarks_integration_same_run,
  function(row) {
    if (is.null(row$worker_observations)) {
      stop("The integration report has no worker observations. Regenerate the report.")
    }
    do.call(rbind, Map(function(pipeline_id, pipeline_label) {
      values <- lapply(row$worker_observations, function(worker) {
        worker$roundtrip_us[[pipeline_id]]
      })
      interval <- mean_ci(values)
      data.frame(
        shape = row$shape,
        records = as.character(row$records),
        pipeline = pipeline_label,
        mean_us = interval[["mean"]],
        lower_us = interval[["lower"]],
        upper_us = interval[["upper"]]
      )
    }, integration_ids, integration_labels))
  }
))
integration_times$shape <- factor(integration_times$shape, levels = shape_levels)
integration_times$records <- factor(integration_times$records, levels = record_levels)
integration_times$pipeline <- factor(
  integration_times$pipeline,
  levels = rev(integration_labels)
)

p_integration_times <- ggplot(integration_times, aes(mean_us, pipeline)) +
  geom_segment(
    aes(x = 1, xend = mean_us, yend = pipeline),
    colour = mauve,
    linewidth = 10,
    lineend = "butt"
  ) +
  geom_errorbar(
    aes(xmin = lower_us, xmax = upper_us),
    orientation = "y",
    width = 0.16,
    colour = ink,
    linewidth = 0.35
  ) +
  facet_grid(rows = vars(shape), cols = vars(records), scales = "free_x") +
  scale_x_log10(labels = label_number(big.mark = ",")) +
  labs(
    title = "JSON to TOON to JSON time",
    subtitle = "The CLI measurement includes two process launches.",
    x = expression(paste("Time (", mu, "s)")),
    y = NULL,
    caption = paste0(
      "Each value is the arithmetic mean across ",
      report$evidence_methodology$workers,
      " worker processes. The logarithmic bars start at 1 microsecond."
    )
  ) +
  theme_report() +
  theme(legend.position = "none")
save_plot(p_integration_times, "integration-times", 15, 10)

token_format_ids <- c(
  "json_compact",
  "toon_comma",
  "toon_comma_indent1",
  "toon_comma_indent4",
  "toon_tab",
  "toon_pipe",
  "toons_rust",
  "python_toon"
)
token_format_labels <- c(
  "compact JSON",
  "msgspec-toon canonical",
  "msgspec-toon indent 1",
  "msgspec-toon indent 4",
  "msgspec-toon tab",
  "msgspec-toon pipe",
  "toons (Rust)",
  "python-toon"
)
token_counts <- do.call(rbind, lapply(report$token_efficiency$rows, function(row) {
  do.call(rbind, Map(function(format_id, format_label) {
    data.frame(
      shape = row$shape,
      records = as.character(row$records),
      format = format_label,
      tokens = row$formats[[format_id]]$tokens[[report$token_efficiency$tokenizers$primary]]
    )
  }, token_format_ids, token_format_labels))
}))
token_counts$shape <- factor(token_counts$shape, levels = shape_levels)
token_counts$records <- factor(token_counts$records, levels = record_levels)
token_counts$format <- factor(token_counts$format, levels = rev(token_format_labels))
json_reference <- token_counts[token_counts$format == "compact JSON", ]

p_token_counts <- ggplot(token_counts, aes(tokens, format)) +
  geom_col(aes(fill = format == "compact JSON"), width = 0.68, show.legend = FALSE) +
  geom_vline(
    data = json_reference,
    aes(xintercept = tokens),
    inherit.aes = FALSE,
    colour = wine,
    linetype = "dashed",
    linewidth = 0.55
  ) +
  facet_grid(rows = vars(shape), cols = vars(records), scales = "free_x") +
  scale_fill_manual(values = c(`TRUE` = wine, `FALSE` = green)) +
  scale_x_continuous(labels = label_number(big.mark = ","), expand = expansion(mult = c(0, 0.05))) +
  labs(
    title = "Token count by shape, size, and wire format",
    subtitle = "The dashed line marks compact JSON in each facet.",
    x = paste0(report$token_efficiency$tokenizers$primary, " tokens"),
    y = NULL,
    caption = paste0(
      "Token counts are deterministic under tiktoken ",
      report$token_efficiency$tokenizers$tiktoken_version,
      ". Each record-count column has its own linear token scale."
    )
  ) +
  theme_report() +
  theme(legend.position = "none", axis.text.y = element_text(size = 7.6))
save_plot(p_token_counts, "token-counts", 15, 12)

fmt <- function(value, digits = 2) {
  format(round(value, digits), nsmall = digits, big.mark = ",")
}

headline_codec <- Filter(
  function(row) row$shape == "uniform-records" && row$records == 4096,
  report$benchmarks_codecs_same_run
)[[1]]
headline_tokens <- Filter(
  function(row) row$shape == "uniform-records" && row$records == 4096,
  report$token_efficiency$rows
)[[1]]

codec_table <- unlist(Map(function(codec_id, codec_label) {
  encode <- headline_codec$encode_us[[codec_id]]
  decode <- headline_codec$decode_us[[codec_id]]
  paste0(
    "| ", codec_label, " | ", fmt(encode), " | ", fmt(decode), " | ",
    " ", fmt(encode + decode), " |"
  )
}, codec_ids, codec_labels))

token_table <- unlist(Map(function(format_id, format_label) {
  paste0(
    "| ", format_label, " | ",
    format(headline_tokens$formats[[format_id]]$tokens[[report$token_efficiency$tokenizers$primary]], big.mark = ","),
    " |"
  )
}, token_format_ids, token_format_labels))

md <- c(
  "# Benchmarks",
  "",
  paste0(
    "Generated from [`conformance/report.json`](conformance/report.json) on ",
    report$generated_at,
    "."
  ),
  "",
  "The report keeps time and token results separate. It does not create a combined score.",
  "",
  "## Codec time",
  "",
  "![Codec elapsed times](docs/assets/benchmarks/codec-times.png)",
  "",
  "The chart shows encode, decode, and total elapsed time. Every value is a direct measurement in microseconds.",
  "",
  "### Uniform records at 4,096 records",
  "",
  "| Codec | Encode (µs) | Decode (µs) | Total (µs) |",
  "|---|---:|---:|---:|",
  codec_table,
  "",
  "## End-to-end time",
  "",
  "![JSON to TOON to JSON elapsed times](docs/assets/benchmarks/integration-times.png)",
  "",
  "The API rows run in one Python process. The CLI row includes two process launches.",
  "",
  "## Token count",
  "",
  "![Absolute token counts](docs/assets/benchmarks/token-counts.png)",
  "",
  "Compact JSON appears in every facet. This gives a direct reference for each shape and size.",
  "",
  "### Uniform records at 4,096 records",
  "",
  paste0("| Wire format | ", report$token_efficiency$tokenizers$primary, " tokens |"),
  "|---|---:|",
  token_table,
  "",
  "## Method",
  "",
  paste0(
    "- The timing estimator is the arithmetic mean across ",
    report$evidence_methodology$workers,
    " worker processes."
  ),
  paste0(
    "- Each worker reports ",
    report$evidence_methodology$samples_per_worker,
    " samples after warm-up."
  ),
  "- The error bars are two-sided 95% Student t confidence intervals across worker means.",
  "- The benchmark never uses the minimum time.",
  "- Codec order is fixed inside each worker. The intervals do not measure order bias.",
  "- Token counts are deterministic under the named tokenizer.",
  paste0(
    "- The environment uses Python ", report$environment$python,
    " and msgspec ", report$environment$msgspec, "."
  ),
  "- The build is a release `abi3-py313` build.",
  "- The freshness check rejects stale and instrumented extensions.",
  "- Raw evidence is in [`conformance/report.json`](conformance/report.json).",
  "- Reproduce with `uv sync --group bench --locked && make g2 && make public-report`.",
  "",
  "Results depend on the machine, payload, and package versions. Compare values from the same generated run."
)
writeLines(md, "BENCHMARKS.md")
