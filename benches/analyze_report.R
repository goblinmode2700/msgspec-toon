#!/usr/bin/env Rscript

suppressPackageStartupMessages(library(jsonlite))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 5) {
  stop(
    paste(
      "usage: analyze_report.R RAW.json RESULT.json RAW_SHA256",
      "MANIFEST.json ANALYZER_SHA256"
    ),
    call. = FALSE
  )
}
input_path <- args[[1]]
output_path <- args[[2]]
raw_sha256 <- args[[3]]
manifest_path <- args[[4]]
analyzer_sha256 <- args[[5]]
raw <- fromJSON(input_path, simplifyVector = TRUE)
manifest <- fromJSON(manifest_path, simplifyVector = FALSE)

fail <- function(message) stop(message, call. = FALSE)
if (!identical(raw$schema_version, 1L) || !identical(raw$kind, "absolute_report_raw")) {
  fail("unsupported raw absolute-report evidence schema")
}
if (!is.data.frame(raw$endpoints) || !is.data.frame(raw$observations) ||
    !is.data.frame(raw$comparisons)) {
  fail("raw absolute evidence must contain endpoint, observation, and comparison tables")
}

design <- raw$design
declared <- manifest$absolute_report
design_fields <- if (isTRUE(raw$qualification_override)) {
  c("alpha")
} else {
  c("workers", "samples_per_process", "target_milliseconds", "alpha")
}
for (field in design_fields) {
  if (!identical(design[[field]], declared[[field]])) {
    fail(sprintf("raw absolute evidence changed declared design field: %s", field))
  }
}
endpoints <- raw$endpoints
observations <- raw$observations
comparisons <- raw$comparisons
workers <- raw$workers
warmups <- raw$warmups
if (!is.data.frame(workers) || !is.data.frame(warmups)) {
  fail("raw absolute evidence must contain worker and warmup tables")
}
required_observation_columns <- c("cell_id", "worker", "sample", "loops", "elapsed_ns")
if (!all(required_observation_columns %in% names(observations))) {
  fail("raw absolute observations are incomplete")
}
forbidden <- c("mean", "mean_us", "p_value", "significant", "verdict")
if (any(forbidden %in% names(observations))) {
  fail("Python absolute evidence contains an inferential aggregate")
}
if (any(observations$loops <= 0) || any(observations$elapsed_ns <= 0)) {
  fail("raw absolute observations must be positive")
}
if (anyDuplicated(endpoints$id)) {
  fail("absolute endpoint IDs are not unique")
}
if (!setequal(unique(observations$cell_id), endpoints$id)) {
  fail("raw absolute observations do not match the declared endpoints")
}
if (nrow(workers) != design$workers ||
    !identical(workers$worker, seq_len(design$workers) - 1L)) {
  fail("raw absolute evidence has missing or duplicate workers")
}
identities <- paste(
  workers$python,
  workers$extension$path,
  workers$extension$sha256,
  workers$extension$instrumented,
  sep = "\r"
)
if (length(unique(identities)) != 1) {
  fail("raw absolute evidence mixes worker identities")
}
declared_cells <- raw$calibration$worker$cells$cell_id
for (worker_index in seq_len(design$workers)) {
  if (!setequal(workers$cell_order[[worker_index]], declared_cells)) {
    fail(sprintf("absolute worker %d did not execute the complete row panel", worker_index - 1L))
  }
}
if (nrow(warmups) != nrow(endpoints) * design$workers || any(warmups$elapsed_ns <= 0)) {
  fail("raw absolute evidence does not contain every separate positive warmup")
}
expected_count <- nrow(endpoints) * design$workers * design$samples_per_process
if (nrow(observations) != expected_count) {
  fail(sprintf(
    "raw absolute evidence has %d observations; expected %d",
    nrow(observations), expected_count
  ))
}
observation_key <- paste(
  observations$cell_id, observations$worker, observations$sample, sep = "\r"
)
if (anyDuplicated(observation_key)) {
  fail("raw absolute evidence contains duplicate observations")
}
sample_counts <- aggregate(
  sample ~ cell_id + worker,
  data = observations,
  FUN = length
)
if (nrow(sample_counts) != nrow(endpoints) * design$workers ||
    any(sample_counts$sample != design$samples_per_process)) {
  fail("raw absolute evidence has an incomplete sample index")
}
if (!all(comparisons$candidate_id %in% endpoints$id) ||
    !all(comparisons$reference_id %in% endpoints$id)) {
  fail("absolute comparison references an undeclared endpoint")
}
if (anyDuplicated(comparisons$id)) {
  fail("absolute comparison IDs are not unique")
}

observations$per_call_us <- observations$elapsed_ns / observations$loops / 1000
worker <- aggregate(
  per_call_us ~ cell_id + worker,
  data = observations,
  FUN = mean
)

summarize_cell <- function(cell_id) {
  values <- worker$per_call_us[worker$cell_id == cell_id]
  if (length(values) != design$workers) {
    fail(sprintf("endpoint %s lacks a complete worker panel", cell_id))
  }
  estimate <- mean(values)
  standard_deviation <- sd(values)
  standard_error <- standard_deviation / sqrt(length(values))
  critical <- qt(
    1 - design$alpha / (2 * nrow(endpoints)),
    df = length(values) - 1
  )
  data.frame(
    id = cell_id,
    mean_us = estimate,
    sd_us = standard_deviation,
    cv_pct = 100 * standard_deviation / estimate,
    simultaneous_ci_lower_us = max(0, estimate - critical * standard_error),
    simultaneous_ci_upper_us = estimate + critical * standard_error,
    stringsAsFactors = FALSE
  )
}

summaries <- do.call(rbind, lapply(endpoints$id, summarize_cell))
summary_columns <- c("id", "panel", "row_id", "metric_slug")
summaries <- merge(endpoints[, summary_columns], summaries, by = "id", sort = FALSE)
summaries <- summaries[match(endpoints$id, summaries$id), ]
summaries$relative_to_reference <- NA_real_
key_rows <- which(summaries$panel == "key-cardinality")
if (length(key_rows)) {
  reference <- summaries$mean_us[
    summaries$panel == "key-cardinality" & summaries$metric_slug == "distinct-4"
  ]
  summaries$relative_to_reference[key_rows] <- summaries$mean_us[key_rows] / reference
}

codec_total_map <- data.frame(
  codec_id = c("msgspec_toon", "toons_rust", "python_toon", "msgspec_json_context"),
  encode_slug = c("ours-encode", "toons-encode", "python-toon-encode", "json-encode"),
  decode_slug = c("ours-decode", "toons-decode", "python-toon-decode", "json-decode"),
  stringsAsFactors = FALSE
)
codec_rows <- unique(endpoints$row_id[endpoints$panel == "codecs"])
summarize_total <- function(row_id, codec_index) {
  mapping <- codec_total_map[codec_index, ]
  encode_id <- endpoints$id[
    endpoints$row_id == row_id & endpoints$metric_slug == mapping$encode_slug
  ]
  decode_id <- endpoints$id[
    endpoints$row_id == row_id & endpoints$metric_slug == mapping$decode_slug
  ]
  encode <- worker[worker$cell_id == encode_id, c("worker", "per_call_us")]
  decode <- worker[worker$cell_id == decode_id, c("worker", "per_call_us")]
  names(encode)[[2]] <- "encode_us"
  names(decode)[[2]] <- "decode_us"
  paired <- merge(encode, decode, by = "worker", sort = TRUE)
  values <- paired$encode_us + paired$decode_us
  estimate <- mean(values)
  standard_deviation <- sd(values)
  standard_error <- standard_deviation / sqrt(length(values))
  total_count <- length(codec_rows) * nrow(codec_total_map)
  critical <- qt(1 - design$alpha / (2 * total_count), df = length(values) - 1)
  data.frame(
    id = paste("absolute-total", row_id, mapping$codec_id, sep = ":"),
    row_id = row_id,
    codec_id = mapping$codec_id,
    mean_us = estimate,
    sd_us = standard_deviation,
    cv_pct = 100 * standard_deviation / estimate,
    simultaneous_ci_lower_us = max(0, estimate - critical * standard_error),
    simultaneous_ci_upper_us = estimate + critical * standard_error,
    stringsAsFactors = FALSE
  )
}
derived_summaries <- do.call(rbind, lapply(codec_rows, function(row_id) {
  do.call(rbind, lapply(seq_len(nrow(codec_total_map)), function(index) {
    summarize_total(row_id, index)
  }))
}))

lower_tail <- function(estimate, boundary, standard_error, degrees_freedom) {
  if (!is.finite(standard_error) || standard_error < 1e-15) {
    if (estimate < boundary) return(0)
    if (estimate > boundary) return(1)
    return(0.5)
  }
  pt((estimate - boundary) / standard_error, df = degrees_freedom)
}

analyze_comparison <- function(index) {
  comparison <- comparisons[index, ]
  candidate <- worker[
    worker$cell_id == comparison$candidate_id,
    c("worker", "per_call_us")
  ]
  reference <- worker[
    worker$cell_id == comparison$reference_id,
    c("worker", "per_call_us")
  ]
  names(candidate)[[2]] <- "candidate_us"
  names(reference)[[2]] <- "reference_us"
  paired <- merge(candidate, reference, by = "worker", sort = TRUE)
  if (nrow(paired) != design$workers) {
    fail(sprintf("comparison %s lacks paired workers", comparison$id))
  }
  differences <- log(paired$candidate_us) - log(paired$reference_us)
  estimate <- mean(differences)
  standard_error <- sd(differences) / sqrt(length(differences))
  degrees_freedom <- length(differences) - 1
  boundary <- log1p(comparison$margin_pct / 100)
  p_meets <- lower_tail(estimate, boundary, standard_error, degrees_freedom)
  p_misses <- 1 - p_meets
  critical <- qt(
    1 - design$alpha / (2 * nrow(comparisons)),
    df = degrees_freedom
  )
  data.frame(
    id = comparison$id,
    family = comparison$family,
    row_id = comparison$row_id,
    candidate_id = comparison$candidate_id,
    reference_id = comparison$reference_id,
    margin_pct = comparison$margin_pct,
    estimate_pct = 100 * expm1(estimate),
    simultaneous_ci_lower_pct = 100 * expm1(estimate - critical * standard_error),
    simultaneous_ci_upper_pct = 100 * expm1(estimate + critical * standard_error),
    p_meets_floor = p_meets,
    p_misses_floor = p_misses,
    stringsAsFactors = FALSE
  )
}

comparison_results <- do.call(rbind, lapply(seq_len(nrow(comparisons)), analyze_comparison))
comparison_results$p_meets_floor_adjusted <- NA_real_
comparison_results$p_misses_floor_adjusted <- NA_real_
for (family_name in unique(comparison_results$family)) {
  rows <- which(comparison_results$family == family_name)
  comparison_results$p_meets_floor_adjusted[rows] <- p.adjust(
    comparison_results$p_meets_floor[rows], method = "holm"
  )
  comparison_results$p_misses_floor_adjusted[rows] <- p.adjust(
    comparison_results$p_misses_floor[rows], method = "holm"
  )
}
comparison_results$status <- "inconclusive"
comparison_results$status[
  comparison_results$p_meets_floor_adjusted < design$alpha
] <- "meets_floor"
comparison_results$status[
  comparison_results$p_misses_floor_adjusted < design$alpha
] <- "misses_floor"

family_names <- unique(comparison_results$family)
family_results <- data.frame(
  family = family_names,
  decision = vapply(family_names, function(family_name) {
    statuses <- comparison_results$status[comparison_results$family == family_name]
    if (all(statuses == "meets_floor")) "PASS" else "FAIL"
  }, character(1)),
  stringsAsFactors = FALSE
)

output <- list(
  analysis_schema_version = 1,
  engine = "R stats",
  r_version = R.version.string,
  raw_sha256 = raw_sha256,
  analyzer_sha256 = analyzer_sha256,
  run_id = raw$run_id,
  estimator = "arithmetic mean of per-process means",
  interval = "simultaneous Bonferroni t intervals",
  adjustment = "holm within each declared gate family",
  endpoint_summaries = summaries,
  derived_summaries = derived_summaries,
  worker_estimates = worker,
  comparisons = comparison_results,
  gates = family_results
)
write_json(output, output_path, auto_unbox = TRUE, pretty = TRUE, digits = 15, na = "null")
