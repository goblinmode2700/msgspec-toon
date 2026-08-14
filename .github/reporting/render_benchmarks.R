#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(ggplot2)
  library(grid)
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

analysis <- report$performance_evidence$analysis
if (is.null(analysis) || !identical(analysis$engine, "R stats")) {
  stop("The report lacks validated R-owned performance analysis.")
}

endpoint_interval <- function(row_id, metric_slug) {
  matches <- Filter(function(summary) {
    identical(summary$row_id, row_id) && identical(summary$metric_slug, metric_slug)
  }, analysis$endpoint_summaries)
  if (length(matches) != 1) {
    stop(paste("Missing R endpoint summary:", row_id, metric_slug))
  }
  summary <- matches[[1]]
  c(
    mean = summary$mean_us,
    lower = summary$simultaneous_ci_lower_us,
    upper = summary$simultaneous_ci_upper_us
  )
}

total_interval <- function(row_id, codec_id) {
  matches <- Filter(function(summary) {
    identical(summary$row_id, row_id) && identical(summary$codec_id, codec_id)
  }, analysis$derived_summaries)
  if (length(matches) != 1) {
    stop(paste("Missing R derived total summary:", row_id, codec_id))
  }
  summary <- matches[[1]]
  c(
    mean = summary$mean_us,
    lower = summary$simultaneous_ci_lower_us,
    upper = summary$simultaneous_ci_upper_us
  )
}

uncertainty_aware_pareto <- function(tokens, lower_us, upper_us) {
  vapply(seq_along(tokens), function(index) {
    !any(
      tokens <= tokens[[index]] &
        upper_us < lower_us[[index]] &
        (tokens < tokens[[index]] | upper_us < lower_us[[index]])
    )
  }, logical(1))
}

shape_levels <- c("uniform-records", "string-heavy", "numeric-heavy", "irregular")
record_levels <- c("16", "64", "512", "4096")

codec_ids <- c("msgspec_toon", "msgspec_json_context", "toons_rust", "python_toon")
codec_labels <- c("msgspec-toon", "msgspec JSON", "toons (Rust)", "python-toon")
phase_ids <- c("encode", "decode", "total")
codec_encode_slugs <- c(
  msgspec_toon = "ours-encode",
  msgspec_json_context = "json-encode",
  toons_rust = "toons-encode",
  python_toon = "python-toon-encode"
)
codec_decode_slugs <- c(
  msgspec_toon = "ours-decode",
  msgspec_json_context = "json-decode",
  toons_rust = "toons-decode",
  python_toon = "python-toon-decode"
)

codec_times <- do.call(rbind, lapply(report$benchmarks_codecs_same_run, function(row) {
  do.call(rbind, Map(function(codec_id, codec_label) {
    do.call(rbind, lapply(phase_ids, function(phase) {
      interval <- if (phase == "encode") {
        endpoint_interval(row$performance_row_id, codec_encode_slugs[[codec_id]])
      } else if (phase == "decode") {
        endpoint_interval(row$performance_row_id, codec_decode_slugs[[codec_id]])
      } else {
        total_interval(row$performance_row_id, codec_id)
      }
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
    subtitle = "Bars show R estimates. Error bars are simultaneous family intervals.",
    x = expression(paste("Time (", mu, "s)")),
    y = NULL,
    fill = NULL,
    caption = paste0(
      "Each value is the arithmetic mean across ",
      report$evidence_methodology$workers,
      " worker processes. Intervals use the R-owned multiplicity contract."
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
integration_slugs <- c(
  msgspec_toon_in_process = "ours",
  python_toon_in_process = "python-toon",
  python_toon_two_process_cli = "python-toon-cli"
)
integration_times <- do.call(rbind, lapply(
  report$benchmarks_integration_same_run,
  function(row) {
    do.call(rbind, Map(function(pipeline_id, pipeline_label) {
      interval <- endpoint_interval(
        row$performance_row_id,
        integration_slugs[[pipeline_id]]
      )
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
      " worker processes. Intervals use the R-owned multiplicity contract."
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

pareto_shapes <- c("numeric-heavy", "uniform-records")
pareto_shape_labels <- c(
  "numeric-heavy" = "Numeric-heavy",
  "uniform-records" = "Uniform records"
)
pareto_codec_colors <- c(
  "msgspec-toon" = orange,
  "msgspec JSON" = wine,
  "toons (Rust)" = blue,
  "python-toon" = green
)
pareto_token_formats <- c(
  "compact JSON" = "msgspec JSON",
  "msgspec-toon canonical" = "msgspec-toon",
  "toons (Rust)" = "toons (Rust)",
  "python-toon" = "python-toon"
)

pareto_times <- codec_times[
  codec_times$shape %in% pareto_shapes & codec_times$phase == "total",
  c("shape", "records", "codec", "mean_us", "lower_us", "upper_us")
]
pareto_tokens <- token_counts[
  token_counts$shape %in% pareto_shapes &
    as.character(token_counts$format) %in% names(pareto_token_formats),
  c("shape", "records", "format", "tokens")
]
pareto_tokens$codec <- unname(pareto_token_formats[as.character(pareto_tokens$format)])

pareto_metrics <- merge(
  pareto_times,
  pareto_tokens[c("shape", "records", "codec", "tokens")],
  by = c("shape", "records", "codec")
)
pareto_metrics$shape <- as.character(pareto_metrics$shape)
pareto_metrics$records <- as.numeric(as.character(pareto_metrics$records))
pareto_metrics$codec <- as.character(pareto_metrics$codec)
expected_pareto_rows <- length(pareto_shapes) * length(record_levels) * length(codec_labels)
if (nrow(pareto_metrics) != expected_pareto_rows || anyNA(pareto_metrics)) {
  stop("The Pareto dataset is incomplete. Regenerate the report before plotting.")
}
if (any(pareto_metrics$tokens <= 0) || any(pareto_metrics$lower_us <= 0)) {
  stop("The Pareto plot requires positive token counts and time intervals for log scales.")
}
pareto_metrics$old_pareto <- NA
pareto_metrics$new_pareto <- FALSE

for (shape_value in pareto_shapes) {
  for (record_value in as.numeric(record_levels)) {
    cell <- which(
      pareto_metrics$shape == shape_value &
        pareto_metrics$records == record_value
    )
    pareto_metrics$new_pareto[cell] <- uncertainty_aware_pareto(
      pareto_metrics$tokens[cell],
      pareto_metrics$lower_us[cell],
      pareto_metrics$upper_us[cell]
    )
    old_cell <- cell[pareto_metrics$codec[cell] != "msgspec-toon"]
    pareto_metrics$old_pareto[old_cell] <- uncertainty_aware_pareto(
      pareto_metrics$tokens[old_cell],
      pareto_metrics$lower_us[old_cell],
      pareto_metrics$upper_us[old_cell]
    )
  }
}

pareto_metrics$status <- with(pareto_metrics, ifelse(
  codec == "msgspec-toon" & new_pareto,
  "New Pareto choice",
  ifelse(
    codec == "msgspec-toon" & !new_pareto,
    "New dominated choice",
    ifelse(
      old_pareto & new_pareto,
      "Old Pareto, remains Pareto",
      ifelse(old_pareto & !new_pareto, "Old Pareto, displaced", "Old dominated choice")
    )
  )
))

pareto_status_levels <- c(
  "New Pareto choice",
  "Old Pareto, displaced",
  "Old Pareto, remains Pareto",
  "Old dominated choice",
  "New dominated choice"
)
pareto_metrics$status <- factor(pareto_metrics$status, levels = pareto_status_levels)
pareto_metrics$codec <- factor(pareto_metrics$codec, levels = codec_labels)
pareto_metrics$shape_facet <- factor(
  pareto_metrics$shape,
  levels = pareto_shapes,
  labels = unname(pareto_shape_labels)
)
pareto_metrics <- pareto_metrics[
  order(pareto_metrics$shape_facet, pareto_metrics$codec, pareto_metrics$records),
]

new_choice <- pareto_metrics[pareto_metrics$codec == "msgspec-toon", ]
new_choice$record_label <- comma(new_choice$records)
new_choice$label_x <- new_choice$tokens * 1.08
new_choice$label_y <- new_choice$mean_us * 0.96

displaced <- pareto_metrics[pareto_metrics$status == "Old Pareto, displaced", ]
displacement_arrows <- merge(
  displaced,
  new_choice,
  by = c("shape", "records"),
  suffixes = c("_old", "_new")
)
if (nrow(displacement_arrows)) {
  displacement_arrows$shape_facet <- factor(
    displacement_arrows$shape,
    levels = pareto_shapes,
    labels = unname(pareto_shape_labels)
  )
}

headline_new <- new_choice[new_choice$records == max(new_choice$records), ]
headline_new$note <- ifelse(
  headline_new$shape == "numeric-heavy",
  "same token count\ninterval-separated time",
  "new low-token\nPareto choice"
)
headline_new$note_x <- headline_new$tokens * 0.72
headline_new$note_y <- headline_new$mean_us * 1.55

better_note <- do.call(rbind, lapply(
  split(pareto_metrics, pareto_metrics$shape_facet),
  function(group) data.frame(
    shape_facet = group$shape_facet[[1]],
    x = min(group$tokens),
    y = max(group$upper_us),
    label = "fewer tokens / less time"
  )
))

p_pareto <- ggplot(
  pareto_metrics,
  aes(tokens, mean_us, colour = codec, group = codec)
) +
  geom_path(linewidth = 0.7, alpha = 0.28) +
  geom_errorbar(
    aes(ymin = lower_us, ymax = upper_us, alpha = status),
    width = 0,
    linewidth = 0.45,
    show.legend = FALSE
  ) +
  geom_segment(
    data = displacement_arrows,
    aes(
      x = tokens_old,
      y = mean_us_old,
      xend = tokens_new,
      yend = mean_us_new
    ),
    inherit.aes = FALSE,
    colour = ink,
    linewidth = 0.6,
    linetype = "dashed",
    arrow = arrow(type = "closed", length = unit(0.10, "inches")),
    alpha = 0.72
  ) +
  geom_point(aes(shape = status, alpha = status), size = 3.8, stroke = 1.0) +
  geom_text(
    data = new_choice,
    aes(x = label_x, y = label_y, label = record_label),
    inherit.aes = FALSE,
    colour = orange,
    hjust = 0,
    vjust = 0.5,
    size = 3.1,
    fontface = "bold"
  ) +
  geom_text(
    data = headline_new,
    aes(x = note_x, y = note_y, label = note),
    inherit.aes = FALSE,
    colour = ink,
    hjust = 1,
    vjust = 0,
    size = 3.15,
    lineheight = 0.95
  ) +
  geom_text(
    data = better_note,
    aes(x = x, y = y, label = label),
    inherit.aes = FALSE,
    hjust = 0,
    vjust = 1,
    colour = "#666B70",
    size = 3.3
  ) +
  facet_wrap(vars(shape_facet), nrow = 1) +
  scale_x_log10(
    labels = label_number(big.mark = ","),
    expand = expansion(mult = c(0.10, 0.24))
  ) +
  scale_y_log10(
    labels = label_number(big.mark = ","),
    expand = expansion(mult = c(0.12, 0.18))
  ) +
  scale_colour_manual(values = pareto_codec_colors, name = NULL) +
  scale_shape_manual(
    values = c(
      "New Pareto choice" = 16,
      "Old Pareto, displaced" = 24,
      "Old Pareto, remains Pareto" = 21,
      "Old dominated choice" = 4,
      "New dominated choice" = 1
    ),
    name = "Conservative Pareto status"
  ) +
  scale_alpha_manual(
    values = c(
      "New Pareto choice" = 1.00,
      "Old Pareto, displaced" = 1.00,
      "Old Pareto, remains Pareto" = 0.95,
      "Old dominated choice" = 0.22,
      "New dominated choice" = 0.35
    ),
    guide = "none"
  ) +
  guides(
    colour = guide_legend(
      order = 1,
      nrow = 1,
      override.aes = list(alpha = 1, linewidth = 1.2)
    ),
    shape = guide_legend(
      order = 2,
      nrow = 1,
      override.aes = list(alpha = 1, colour = ink)
    )
  ) +
  labs(
    title = "Uncertainty-aware speed-token Pareto set",
    subtitle = paste0(
      "A timing dominance edge requires non-overlapping simultaneous intervals; ",
      "overlap remains unresolved."
    ),
    x = "Tokens (o200k_base; fewer is better, log scale)",
    y = expression(paste("Encode + decode time (", mu, "s; lower is better, log scale)")),
    caption = paste0(
      "Pareto status is conservative and evaluated by payload shape and record count. ",
      "Lines connect the same implementation across record counts and show workload scaling only;\n",
      "they are not Pareto frontiers and do not imply unmeasured operating points. ",
      "Whiskers are simultaneous R-owned intervals across worker-level total times.\n",
      "Token counts are deterministic for each generated payload."
    )
  ) +
  theme_report() +
  theme(
    panel.grid.major.y = element_line(colour = grid, linewidth = 0.35),
    legend.box = "vertical",
    legend.key.width = unit(1.25, "lines"),
    plot.caption = element_text(colour = "#666B70", size = 8.3, hjust = 0),
    plot.margin = margin(12, 22, 12, 12)
  )
save_plot(p_pareto, "pareto-set-change", 15, 8.4)

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
  "## Speed and token Pareto set",
  "",
  "![Empirical speed-token Pareto set](docs/assets/benchmarks/pareto-set-change.png)",
  "",
  paste0(
    "Pareto status is conservative and calculated independently for each payload shape and ",
    "record count. A speed dominance edge requires non-overlapping simultaneous intervals. ",
    "Interval overlap is unresolved, not neutral."
  ),
  "",
  "## Codec time",
  "",
  "![Codec elapsed times](docs/assets/benchmarks/codec-times.png)",
  "",
  paste0(
    "The chart shows encode, decode, and total elapsed time. Each bar is R's ",
    "arithmetic mean of per-process means, in microseconds."
  ),
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
  paste0("- The error bars use ", report$evidence_methodology$interval, "."),
  paste0("- Confirmatory families use ", report$evidence_methodology$multiplicity, "."),
  "- The benchmark never uses the minimum time.",
  "- Report rows are randomized within each complete process panel.",
  "- Python records raw timings; R owns aggregation, intervals, and decisions.",
  "- Token counts are deterministic under the named tokenizer.",
  paste0(
    "- The environment uses Python ", report$environment$python,
    " and msgspec ", report$environment$msgspec, "."
  ),
  "- The build is a release `abi3-py313` build.",
  "- The freshness check rejects stale and instrumented extensions.",
  paste0(
    "- R summaries are in [`conformance/report.json`](conformance/report.json). ",
    "Raw timings are in `benches/report-performance-raw.json`."
  ),
  "- Reproduce with `uv sync --group bench --locked && make g2 && make public-report`.",
  "",
  "Results depend on the machine, payload, and package versions. Compare values from the same generated run."
)
writeLines(md, "BENCHMARKS.md")
