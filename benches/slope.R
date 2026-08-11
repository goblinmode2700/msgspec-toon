#!/usr/bin/env Rscript

# Advisory E3 model for nested-tag decode. The interleaved A/B harness remains
# the release authority; this script estimates the per-row component from its
# worker-level means and uses HC3 standard errors for unequal variance by size.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 3L) {
  stop("usage: slope.R REPAIR_VS_CPS.json GUARD_VS_CPS.json OUTPUT.json")
}

read_run <- function(path, session, baseline_build) {
  run <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  rows <- lapply(run$results, function(result) {
    records <- as.integer(sub(".*@", "", result$metric))
    rbind(
      data.frame(session, build = baseline_build, records, time_us = unlist(result$baseline_us)),
      data.frame(session, build = "cp_s", records, time_us = unlist(result$current_us))
    )
  })
  do.call(rbind, rows)
}

data <- rbind(
  read_run(args[[1]], "repair_session", "repair"),
  read_run(args[[2]], "guard_session", "v0.2.0b5")
)
data$session <- factor(data$session, levels = c("repair_session", "guard_session"))
data$build <- factor(data$build, levels = c("cp_s", "repair", "v0.2.0b5"))

fit <- lm(time_us ~ session + build + build:records, data = data)
x <- model.matrix(fit)
residual <- residuals(fit)
leverage <- hatvalues(fit)
bread <- solve(crossprod(x))
weights <- (residual / (1 - leverage))^2
hc3 <- bread %*% crossprod(x, x * weights) %*% bread

coefficient <- coef(fit)
critical <- qt(0.975, df.residual(fit))
slope_names <- paste0("build", levels(data$build), ":records")

slope_row <- function(build) {
  name <- paste0("build", build, ":records")
  estimate_us <- unname(coefficient[[name]])
  se_us <- sqrt(hc3[name, name])
  data.frame(
    build = build,
    estimate_ns_per_row = estimate_us * 1000,
    lower_95_ns_per_row = (estimate_us - critical * se_us) * 1000,
    upper_95_ns_per_row = (estimate_us + critical * se_us) * 1000
  )
}

contrast_row <- function(other) {
  cp_name <- "buildcp_s:records"
  other_name <- paste0("build", other, ":records")
  estimate_us <- coefficient[[cp_name]] - coefficient[[other_name]]
  variance <- hc3[cp_name, cp_name] + hc3[other_name, other_name] - 2 * hc3[cp_name, other_name]
  se_us <- sqrt(variance)
  data.frame(
    contrast = paste0("cp_s - ", other),
    estimate_ns_per_row = unname(estimate_us) * 1000,
    lower_95_ns_per_row = unname(estimate_us - critical * se_us) * 1000,
    upper_95_ns_per_row = unname(estimate_us + critical * se_us) * 1000
  )
}

slopes <- do.call(rbind, lapply(levels(data$build), slope_row))
contrasts <- rbind(contrast_row("repair"), contrast_row("v0.2.0b5"))

output <- list(
  method = paste(
    "OLS on worker-process means: time_us ~ session + build + build:records;",
    "HC3 heteroscedasticity-consistent covariance; two A/B sessions joined by",
    "the CP-S build measured in both; advisory only"
  ),
  observations = nrow(data),
  residual_degrees_of_freedom = df.residual(fit),
  adjusted_r_squared = summary(fit)$adj.r.squared,
  slopes = slopes,
  contrasts = contrasts
)

jsonlite::write_json(output, args[[3]], pretty = TRUE, auto_unbox = TRUE, digits = 10)
print(slopes, row.names = FALSE)
print(contrasts, row.names = FALSE)
