#!/usr/bin/env Rscript

suppressPackageStartupMessages(library(jsonlite))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 5) {
  stop(
    "usage: analyze_ab.R RAW.json RESULT.json RAW_SHA256 MANIFEST.json ANALYZER_SHA256",
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
if (!identical(raw$schema_version, 1L) || !identical(raw$kind, "paired_ab_raw")) {
  fail("unsupported raw A/B evidence schema")
}
if (!is.data.frame(raw$endpoints) || !is.data.frame(raw$observations)) {
  fail("raw A/B evidence must contain endpoint and observation tables")
}

family <- raw$family
endpoints <- raw$endpoints
observations <- raw$observations
workers <- raw$workers
warmups <- raw$warmups
if (!is.data.frame(workers) || !is.data.frame(warmups)) {
  fail("raw A/B evidence must contain worker and warmup tables")
}
declared_family <- manifest$families[[family$name]]
if (is.null(declared_family)) {
  fail("raw evidence names an undeclared performance family")
}
fixed_family_fields <- c(
  "description", "regression_margin_pct", "improvement_margin_pct", "gating"
)
for (field in fixed_family_fields) {
  if (!identical(family[[field]], declared_family[[field]])) {
    fail(sprintf("raw evidence changed declared family field: %s", field))
  }
}
for (field in c("alpha", "target_power", "planning_sd_log")) {
  if (!identical(family[[field]], manifest$defaults[[field]])) {
    fail(sprintf("raw evidence changed declared default field: %s", field))
  }
}
declared_members <- declared_family$members
if (identical(declared_members, "*")) {
  if (!all(endpoints$role == "exploratory")) {
    fail("exploratory family contains a confirmatory endpoint")
  }
} else {
  member_ids <- names(declared_members)
  member_roles <- unlist(declared_members, use.names = TRUE)
  observed_roles <- setNames(endpoints$role, endpoints$id)
  if (!identical(member_ids, endpoints$id) ||
      !identical(unname(member_roles), unname(observed_roles[member_ids]))) {
    fail("raw evidence changed the declared endpoint family, role, or order")
  }
}
required_observation_columns <- c(
  "cell_id", "pair", "build", "period", "sample", "loops", "elapsed_ns"
)
if (!all(required_observation_columns %in% names(observations))) {
  fail("raw A/B observations are incomplete")
}
forbidden <- c("mean", "mean_us", "p_value", "significant", "verdict")
if (any(forbidden %in% names(observations))) {
  fail("Python collection evidence contains an inferential aggregate")
}
if (any(observations$loops <= 0) || any(observations$elapsed_ns <= 0)) {
  fail("raw A/B observations must be positive")
}
if (anyDuplicated(endpoints$id)) {
  fail("endpoint IDs are not unique")
}
if (!setequal(unique(observations$cell_id), endpoints$id)) {
  fail("raw observations do not match the declared endpoint set")
}
if (nrow(workers) != family$pairs * 2) {
  fail("raw A/B evidence does not contain two workers per pair")
}
worker_key <- paste(workers$pair, workers$build, sep = "\r")
if (anyDuplicated(worker_key)) {
  fail("raw A/B evidence contains duplicate workers")
}
for (build_name in c("baseline", "current")) {
  rows <- which(workers$build == build_name)
  identities <- paste(
    workers$python[rows],
    workers$package$path[rows],
    workers$package$sha256[rows],
    workers$extension$path[rows],
    workers$extension$sha256[rows],
    workers$extension$instrumented[rows],
    sep = "\r"
  )
  if (length(unique(identities)) != 1) {
    fail(sprintf("raw A/B evidence mixes %s worker identities", build_name))
  }
}
for (pair_index in seq_len(family$pairs) - 1L) {
  rows <- which(workers$pair == pair_index)
  if (!setequal(workers$period[rows], c(1L, 2L))) {
    fail(sprintf("process pair %d does not contain periods one and two", pair_index))
  }
  if (!identical(workers$cell_order[[rows[[1]]]], workers$cell_order[[rows[[2]]]])) {
    fail(sprintf("process pair %d used different endpoint orders", pair_index))
  }
  if (!setequal(workers$cell_order[[rows[[1]]]], endpoints$id)) {
    fail(sprintf("process pair %d did not execute the complete endpoint panel", pair_index))
  }
}
if (nrow(warmups) != nrow(endpoints) * family$pairs * 2 ||
    any(warmups$elapsed_ns <= 0)) {
  fail("raw A/B evidence does not contain every separate positive warmup")
}
expected_count <- nrow(endpoints) * family$pairs * 2 * family$samples_per_process
if (nrow(observations) != expected_count) {
  fail(sprintf("raw A/B evidence has %d observations; expected %d", nrow(observations), expected_count))
}
observation_key <- paste(
  observations$cell_id, observations$pair, observations$build, observations$sample, sep = "\r"
)
if (anyDuplicated(observation_key)) {
  fail("raw A/B evidence contains duplicate observations")
}
sample_counts <- aggregate(
  sample ~ cell_id + pair + build,
  data = observations,
  FUN = length
)
if (nrow(sample_counts) != nrow(endpoints) * family$pairs * 2 ||
    any(sample_counts$sample != family$samples_per_process)) {
  fail("raw A/B evidence has an incomplete sample index")
}
observation_periods <- merge(
  observations[, c("pair", "build", "period")],
  workers[, c("pair", "build", "period")],
  by = c("pair", "build"),
  suffixes = c("_observation", "_worker")
)
if (any(observation_periods$period_observation != observation_periods$period_worker)) {
  fail("raw observation periods do not match their workers")
}

observations$per_call_ns <- observations$elapsed_ns / observations$loops
worker <- aggregate(
  per_call_ns ~ cell_id + pair + build + period,
  data = observations,
  FUN = mean
)

lower_tail <- function(estimate, boundary, standard_error, degrees_freedom) {
  if (!is.finite(standard_error) || standard_error < 1e-15) {
    if (estimate < boundary) return(0)
    if (estimate > boundary) return(1)
    return(0.5)
  }
  pt((estimate - boundary) / standard_error, df = degrees_freedom)
}

interval_family_size <- nrow(endpoints)

analyze_cell <- function(cell_id) {
  rows <- worker[worker$cell_id == cell_id, ]
  baseline <- rows[rows$build == "baseline", c("pair", "period", "per_call_ns")]
  current <- rows[rows$build == "current", c("pair", "period", "per_call_ns")]
  names(baseline)[2:3] <- c("baseline_period", "baseline_ns")
  names(current)[2:3] <- c("current_period", "current_ns")
  paired <- merge(baseline, current, by = "pair", sort = TRUE)
  if (nrow(paired) != family$pairs) {
    fail(sprintf("endpoint %s lacks a complete process pair", cell_id))
  }
  if (any(paired$baseline_period == paired$current_period)) {
    fail(sprintf("endpoint %s has invalid build periods", cell_id))
  }
  paired$log_ratio <- log(paired$current_ns) - log(paired$baseline_ns)
  paired$order_sign <- ifelse(paired$current_period == 2, 1, -1)
  if (sum(paired$order_sign == 1) != sum(paired$order_sign == -1)) {
    fail(sprintf("endpoint %s has unbalanced build order", cell_id))
  }

  fit <- lm(log_ratio ~ order_sign, data = paired)
  coefficients <- summary(fit)$coefficients
  beta <- unname(coef(fit)[["(Intercept)"]])
  order_effect <- unname(coef(fit)[["order_sign"]])
  standard_error <- unname(coefficients["(Intercept)", "Std. Error"])
  degrees_freedom <- df.residual(fit)
  regression_boundary <- log1p(family$regression_margin_pct / 100)
  improvement_boundary <- log1p(-family$improvement_margin_pct / 100)
  p_noninferiority <- lower_tail(beta, regression_boundary, standard_error, degrees_freedom)
  p_regression <- 1 - p_noninferiority
  p_improvement <- lower_tail(beta, improvement_boundary, standard_error, degrees_freedom)
  simultaneous_critical <- qt(
    1 - family$alpha / (2 * interval_family_size),
    df = degrees_freedom
  )

  data.frame(
    id = cell_id,
    estimate_log = beta,
    estimate_pct = 100 * expm1(beta),
    standard_error_log = standard_error,
    degrees_freedom = degrees_freedom,
    order_effect_pct = 100 * expm1(order_effect),
    simultaneous_ci_lower_pct = 100 * expm1(beta - simultaneous_critical * standard_error),
    simultaneous_ci_upper_pct = 100 * expm1(beta + simultaneous_critical * standard_error),
    p_improvement = p_improvement,
    p_noninferiority = p_noninferiority,
    p_regression = p_regression,
    stringsAsFactors = FALSE
  )
}

results <- do.call(rbind, lapply(endpoints$id, analyze_cell))
results <- merge(endpoints[, c("id", "label", "role")], results, by = "id", sort = FALSE)
results <- results[match(endpoints$id, results$id), ]
noninferiority_rows <- which(results$role == "non_inferiority")
improvement_rows <- which(results$role == "improvement")

results$status <- "inconclusive"
results$status[
  results$role == "non_inferiority" &
    results$simultaneous_ci_upper_pct < family$regression_margin_pct
] <- "non_inferior"
results$status[
  results$role != "exploratory" &
    results$simultaneous_ci_lower_pct > family$regression_margin_pct
] <- "regressed"
results$status[
  results$role == "improvement" &
    results$simultaneous_ci_upper_pct < -family$improvement_margin_pct
] <- "improved"
results$status[results$role == "exploratory"] <- "exploratory"

noninferiority_power <- NULL
if (length(noninferiority_rows)) {
  noninferiority_power <- power.t.test(
    n = family$pairs,
    delta = abs(log1p(family$regression_margin_pct / 100)),
    sd = family$planning_sd_log,
    sig.level = family$alpha / (2 * interval_family_size),
    type = "one.sample",
    alternative = "one.sided"
  )$power
}
improvement_power <- NULL
if (length(improvement_rows)) {
  improvement_power <- power.t.test(
    n = family$pairs,
    delta = abs(log1p(-family$improvement_margin_pct / 100)),
    sd = family$planning_sd_log,
    sig.level = family$alpha / (2 * interval_family_size),
    type = "one.sample",
    alternative = "one.sided"
  )$power
}

if (!isTRUE(family$gating)) {
  gate_decision <- "EXPLORATORY"
  failures <- character()
} else {
  improvement_failures <- results$id[
    results$role == "improvement" & results$status != "improved"
  ]
  noninferiority_failures <- results$id[
    results$role == "non_inferiority" &
      !(results$status %in% c("non_inferior", "improved"))
  ]
  failures <- c(improvement_failures, noninferiority_failures)
  gate_decision <- if (length(failures)) "FAIL" else "PASS"
}

output <- list(
  analysis_schema_version = 1,
  engine = "R stats",
  r_version = R.version.string,
  raw_sha256 = raw_sha256,
  analyzer_sha256 = analyzer_sha256,
  run_id = raw$run_id,
  family = family$name,
  alpha = family$alpha,
  adjustment = "simultaneous Bonferroni intervals across the declared family",
  model = "paired log process means with balanced order term",
  gate_decision = gate_decision,
  failure_endpoints = failures,
  planning = list(
    pairs = family$pairs,
    interval_family_size = interval_family_size,
    target_power = family$target_power,
    planning_sd_log = family$planning_sd_log,
    bonferroni_noninferiority_power = noninferiority_power,
    bonferroni_improvement_power = improvement_power
  ),
  endpoints = results
)
write_json(output, output_path, auto_unbox = TRUE, pretty = TRUE, digits = 15, na = "null")
