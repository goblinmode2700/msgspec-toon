from __future__ import annotations

import copy
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
BENCHES = ROOT / "benches"
sys.path.insert(0, str(BENCHES))

import _panel
import _timing
import _workers
import ab
import collect_report
from _manifest import (
    MANIFEST_PATH,
    expand_endpoints,
    expand_report_cells,
    expand_report_comparisons,
    expand_report_endpoints,
    load_manifest,
    select_family,
)
from _panel import (
    balanced_build_orders,
    file_sha256,
    randomized_cells,
    validate_ab_raw,
    validate_absolute_raw,
    validate_r_result,
)


def _valid_manifest_raw() -> dict[str, Any]:
    family, endpoints = select_family("distinct-key-hotfix")
    pairs = family["pairs"]
    samples = family["samples_per_process"]
    endpoint_ids = [endpoint["id"] for endpoint in endpoints]
    workers: list[dict[str, Any]] = []
    warmups: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    for pair in range(pairs):
        current_period = 2 if pair < pairs // 2 else 1
        for build in ("baseline", "current"):
            period = current_period if build == "current" else 3 - current_period
            workers.append(
                {
                    "pair": pair,
                    "build": build,
                    "period": period,
                    "pid": 1000 + pair * 2 + (build == "current"),
                    "python": "3.13.7",
                    "platform": "test-platform",
                    "machine": "test-machine",
                    "package": {
                        "path": f"/{build}/__init__.py",
                        "sha256": ("c" if build == "baseline" else "d") * 64,
                    },
                    "extension": {
                        "path": f"/{build}/_native.so",
                        "sha256": ("a" if build == "baseline" else "b") * 64,
                        "instrumented": False,
                    },
                    "panel_wall_ns": 1,
                    "cell_order": endpoint_ids,
                }
            )
            for order_index, cell_id in enumerate(endpoint_ids):
                warmups.append(
                    {
                        "cell_id": cell_id,
                        "pair": pair,
                        "build": build,
                        "period": period,
                        "order_index": order_index,
                        "loops": 2,
                        "elapsed_ns": 1000,
                    }
                )
                for sample in range(samples):
                    observations.append(
                        {
                            "cell_id": cell_id,
                            "pair": pair,
                            "build": build,
                            "period": period,
                            "order_index": order_index,
                            "sample": sample,
                            "loops": 2,
                            "elapsed_ns": 1000,
                        }
                    )
    return {
        "schema_version": 1,
        "kind": "paired_ab_raw",
        "manifest_sha256": file_sha256(MANIFEST_PATH),
        "family": family,
        "endpoints": endpoints,
        "workers": workers,
        "warmups": warmups,
        "observations": observations,
    }


def test_manifest_expands_stable_historical_grid_and_bounded_families() -> None:
    manifest = load_manifest()
    endpoints = expand_endpoints(manifest)
    assert len(endpoints) == 100
    assert len({endpoint["id"] for endpoint in endpoints}) == 100

    focused, focused_endpoints = select_family("distinct-key-hotfix", manifest)
    guard, guard_endpoints = select_family("release-guard", manifest)
    exploratory, exploratory_endpoints = select_family("full-exploratory", manifest)
    assert (focused["pairs"], len(focused_endpoints), focused["gating"]) == (20, 4, True)
    assert (guard["pairs"], len(guard_endpoints), guard["gating"]) == (36, 22, True)
    assert (exploratory["pairs"], len(exploratory_endpoints), exploratory["gating"]) == (
        4,
        100,
        False,
    )


def test_absolute_manifest_vectorizes_253_endpoints_into_37_process_rows() -> None:
    endpoints = expand_report_endpoints()
    cells = expand_report_cells()
    assert len(endpoints) == 253
    assert len(cells) == 37
    assert sum(len(cell["metrics"]) for cell in cells) == len(endpoints)
    cli_metrics = [
        metric
        for cell in cells
        for metric in cell["metrics"]
        if metric["sampler_metric"] == "integration.python_toon_cli"
    ]
    assert len(cli_metrics) == 16
    assert {metric["fixed_loops"] for metric in cli_metrics} == {1}
    release_gate_by_family = {
        comparison["family"]: comparison["release_gate"]
        for comparison in expand_report_comparisons()
    }
    assert release_gate_by_family == {
        "G3_typed_decode_beats_wrapper": True,
        "G4_whole_encode_beats_to_builtins_alone": False,
        "G5_decode_not_slower_than_toons": True,
        "G5_encode_not_slower_than_toons": True,
        "typed_beats_incumbent_pipeline_decode": True,
        "typed_beats_incumbent_pipeline_encode": True,
    }


def test_panel_workers_ignore_python_path_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    python = tmp_path / "python"
    python.touch()
    observed: dict[str, Any] = {}

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed["command"] = command
        observed["environment"] = kwargs["env"]
        response = {"mode": "measure", "cells": [{"cell_id": "cell"}]}
        return subprocess.CompletedProcess(command, 0, json.dumps(response), "")

    monkeypatch.setenv("PYTHONPATH", "/shadow-package")
    monkeypatch.setenv("PYTHONHOME", "/shadow-runtime")
    monkeypatch.setattr(_panel.subprocess, "run", run)
    _panel.run_panel(
        python,
        mode="measure",
        cells=[{"id": "cell"}],
        loops_by_cell={"cell": {"metric": 1}},
        target_seconds=0.001,
        samples=1,
        allow_instrumented=False,
    )

    assert observed["command"] == [str(python), "-I", str(_panel.WORKER)]
    assert "PYTHONPATH" not in observed["environment"]
    assert "PYTHONHOME" not in observed["environment"]


def test_build_and_cell_orders_are_balanced_reproducible_and_paired() -> None:
    orders = balanced_build_orders(12, seed=9283)
    assert orders == balanced_build_orders(12, seed=9283)
    assert orders.count(("baseline", "current")) == 6
    assert orders.count(("current", "baseline")) == 6
    cells = [{"id": str(index)} for index in range(12)]
    assert randomized_cells(cells, pair=3, seed=81) == randomized_cells(cells, pair=3, seed=81)
    assert randomized_cells(cells, pair=3, seed=81) != randomized_cells(cells, pair=4, seed=81)


def test_timing_retains_calibration_warmup_and_every_raw_sample() -> None:
    calls = 0

    def operation() -> None:
        nonlocal calls
        calls += 1

    with _timing.collection_context(
        loops=None,
        selected="chosen",
        target_seconds=0.000_001,
        samples=3,
        calibration_only=True,
    ):
        calibrated = _timing.measure("chosen", operation)
        assert calibrated.elapsed_ns == ()
        assert calibrated.warmup_elapsed_ns is None
        assert _timing.CALIBRATED == {"chosen": calibrated.loops}

    with _timing.collection_context(
        loops={"chosen": 2},
        selected="chosen",
        target_seconds=0.000_001,
        samples=3,
    ):
        skipped = _timing.measure("skipped", operation)
        chosen = _timing.measure("chosen", operation)
        raw = _timing.raw_timings()
        assert skipped.elapsed_ns == ()
        assert chosen.loops == 2
        assert chosen.warmup_elapsed_ns is not None
        assert chosen.warmup_elapsed_ns > 0
        assert len(chosen.elapsed_ns) == 3
        assert all(isinstance(value, int) and value > 0 for value in chosen.elapsed_ns)
        assert raw == {
            "chosen": {
                "loops": 2,
                "warmup_elapsed_ns": chosen.warmup_elapsed_ns,
                "elapsed_ns": list(chosen.elapsed_ns),
            }
        }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda raw: raw["observations"].pop(), "observations"),
        (
            lambda raw: raw["observations"][0].__setitem__("mean_us", 1.0),
            "inferential aggregate",
        ),
        (
            lambda raw: raw["workers"][-1]["extension"].__setitem__("sha256", "c" * 64),
            "mixes worker identities",
        ),
        (
            lambda raw: raw["endpoints"][0].__setitem__("role", "exploratory"),
            "changed the declared endpoint family",
        ),
        (
            lambda raw: raw["family"].__setitem__("pairs", raw["family"]["pairs"] + 2),
            "changed declared family field: pairs",
        ),
        (
            lambda raw: raw["family"].__setitem__("target_milliseconds", 50.0),
            "changed declared family field: target_milliseconds",
        ),
        (
            lambda raw: raw["workers"][0].__setitem__(
                "cell_order", list(reversed(raw["workers"][0]["cell_order"]))
            ),
            "same randomized endpoint order",
        ),
    ],
)
def test_raw_contract_rejects_incomplete_mixed_or_posthoc_evidence(
    mutation: Any, message: str
) -> None:
    raw = _valid_manifest_raw()
    mutation(raw)
    with pytest.raises(ValueError, match=message):
        validate_ab_raw(raw)


def test_raw_contract_accepts_complete_predeclared_evidence() -> None:
    validate_ab_raw(_valid_manifest_raw())


def _residuals(pairs: int, scale: float) -> list[float]:
    by_order: dict[int, list[int]] = {1: [], -1: []}
    for pair in range(pairs):
        by_order[1 if pair % 2 == 0 else -1].append(pair)
    values = [0.0] * pairs
    pattern = (-1.0, 0.0, 1.0)
    for indexes in by_order.values():
        centered = [pattern[index % len(pattern)] for index in range(len(indexes))]
        center = sum(centered) / len(centered)
        for pair, value in zip(indexes, centered, strict=True):
            values[pair] = (value - center) * scale
    return values


def _synthetic_files(
    tmp_path: Path,
    endpoints: list[dict[str, str]],
    effects: dict[str, tuple[float, float, float]],
    *,
    pairs: int = 40,
    samples: int = 3,
    gating: bool = True,
) -> tuple[Path, Path, str]:
    defaults = {
        "alpha": 0.05,
        "target_power": 0.8,
        "planning_sd_log": 0.03,
        "samples_per_process": samples,
        "target_milliseconds": 5.0,
    }
    family = {
        "name": "synthetic",
        "description": "synthetic contract fixture",
        "pairs": pairs,
        "regression_margin_pct": 3.0,
        "improvement_margin_pct": 5.0,
        "gating": gating,
        **defaults,
    }
    manifest = {
        "schema_version": 1,
        "defaults": defaults,
        "record_ladder": [],
        "endpoint_templates": [],
        "fixed_endpoints": [],
        "families": {
            "synthetic": {
                "description": family["description"],
                "pairs": pairs,
                "regression_margin_pct": family["regression_margin_pct"],
                "improvement_margin_pct": family["improvement_margin_pct"],
                "gating": gating,
                "members": {endpoint["id"]: endpoint["role"] for endpoint in endpoints},
            }
        },
    }
    observations: list[dict[str, Any]] = []
    workers: list[dict[str, Any]] = []
    warmups: list[dict[str, Any]] = []
    endpoint_ids = [endpoint["id"] for endpoint in endpoints]
    for pair in range(pairs):
        current_period = 2 if pair % 2 == 0 else 1
        for build, period in (
            ("baseline", 3 - current_period),
            ("current", current_period),
        ):
            workers.append(
                {
                    "pair": pair,
                    "build": build,
                    "period": period,
                    "python": "3.13.7",
                    "package": {
                        "path": f"/{build}/__init__.py",
                        "sha256": ("c" if build == "baseline" else "d") * 64,
                    },
                    "extension": {
                        "path": f"/{build}/_native.so",
                        "sha256": ("a" if build == "baseline" else "b") * 64,
                        "instrumented": False,
                    },
                    "cell_order": endpoint_ids,
                }
            )
            warmups.extend(
                {
                    "cell_id": endpoint_id,
                    "pair": pair,
                    "build": build,
                    "period": period,
                    "elapsed_ns": 1,
                }
                for endpoint_id in endpoint_ids
            )
    for endpoint in endpoints:
        beta, order_effect, residual_scale = effects[endpoint["id"]]
        residuals = _residuals(pairs, residual_scale)
        for pair in range(pairs):
            current_period = 2 if pair % 2 == 0 else 1
            sign = 1 if current_period == 2 else -1
            baseline_ns = 1_000_000 * (1 + (pair % 4) * 0.07)
            log_ratio = beta + order_effect * sign + residuals[pair]
            current_ns = baseline_ns * math.exp(log_ratio)
            for build, period, per_call_ns in (
                ("baseline", 3 - current_period, baseline_ns),
                ("current", current_period, current_ns),
            ):
                for sample in range(samples):
                    observations.append(
                        {
                            "cell_id": endpoint["id"],
                            "pair": pair,
                            "build": build,
                            "period": period,
                            "order_index": 0,
                            "sample": sample,
                            "loops": 100,
                            "elapsed_ns": round(per_call_ns * 100),
                        }
                    )
    raw = {
        "schema_version": 1,
        "kind": "paired_ab_raw",
        "run_id": "synthetic-run",
        "family": family,
        "endpoints": endpoints,
        "workers": workers,
        "warmups": warmups,
        "observations": observations,
    }
    raw_path = tmp_path / "raw.json"
    result_path = tmp_path / "result.json"
    manifest_path = tmp_path / "manifest.json"
    raw_path.write_text(json.dumps(raw), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return raw_path, result_path, str(manifest_path)


def _run_r(
    raw_path: Path, result_path: Path, manifest_path: str, *, raw_sha256: str = "synthetic-sha"
) -> dict[str, Any]:
    if shutil.which("Rscript") is None:
        pytest.fail("Rscript is required for the performance evidence contract")
    process = subprocess.run(
        [
            "Rscript",
            str(BENCHES / "analyze_ab.R"),
            str(raw_path),
            str(result_path),
            raw_sha256,
            manifest_path,
            "synthetic-analyzer-sha",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    return json.loads(result_path.read_text(encoding="utf-8"))


def test_r_owns_directional_decisions_order_term_and_insufficient_precision(
    tmp_path: Path,
) -> None:
    endpoints = [
        {"id": "fast", "label": "fast", "role": "improvement"},
        {"id": "safe", "label": "safe", "role": "non_inferiority"},
        {"id": "slow", "label": "slow", "role": "non_inferiority"},
        {"id": "noisy", "label": "noisy", "role": "non_inferiority"},
    ]
    effects = {
        "fast": (-0.10, 0.05, 0.005),
        "safe": (0.00, 0.00, 0.005),
        "slow": (0.10, 0.00, 0.005),
        "noisy": (0.00, 0.00, 0.12),
    }
    raw_path, result_path, manifest_path = _synthetic_files(tmp_path, endpoints, effects)
    result = _run_r(raw_path, result_path, manifest_path)
    rows = {row["id"]: row for row in result["endpoints"]}
    assert result["engine"] == "R stats"
    assert result["adjustment"] == ("simultaneous Bonferroni intervals across the declared family")
    assert result["gate_decision"] == "FAIL"
    assert rows["fast"]["status"] == "improved"
    assert rows["safe"]["status"] == "non_inferior"
    assert rows["slow"]["status"] == "regressed"
    assert rows["noisy"]["status"] == "inconclusive"
    assert rows["fast"]["estimate_pct"] == pytest.approx(100 * math.expm1(-0.10), abs=0.01)
    assert rows["fast"]["order_effect_pct"] == pytest.approx(100 * math.expm1(0.05), abs=0.01)
    assert "neutral" not in json.dumps(result)


def test_simultaneous_family_interval_blocks_a_nominal_only_improvement(
    tmp_path: Path,
) -> None:
    endpoints = [
        {"id": f"endpoint-{index}", "label": f"endpoint {index}", "role": "improvement"}
        for index in range(8)
    ]
    boundary = math.log1p(-0.05)
    effects = {
        endpoint["id"]: (
            boundary - 0.012 if index == 0 else 0.0,
            0.0,
            0.02,
        )
        for index, endpoint in enumerate(endpoints)
    }
    raw_path, result_path, manifest_path = _synthetic_files(
        tmp_path, endpoints, effects, pairs=12, gating=False
    )
    result = _run_r(raw_path, result_path, manifest_path)
    row = result["endpoints"][0]
    assert row["p_improvement"] < 0.05
    assert row["simultaneous_ci_upper_pct"] >= -5.0
    assert row["status"] == "inconclusive"
    assert result["gate_decision"] == "EXPLORATORY"


def test_one_simultaneous_family_spans_mixed_confirmatory_roles(tmp_path: Path) -> None:
    endpoints = [
        {"id": "candidate", "label": "candidate", "role": "improvement"},
        {"id": "control", "label": "control", "role": "non_inferiority"},
    ]
    boundary = math.log1p(-0.05)
    effects = {
        "candidate": (boundary - 0.012, 0.0, 0.02),
        "control": (0.0, 0.0, 0.005),
    }
    raw_path, result_path, manifest_path = _synthetic_files(
        tmp_path, endpoints, effects, pairs=12, gating=False
    )
    result = _run_r(raw_path, result_path, manifest_path)
    row = {item["id"]: item for item in result["endpoints"]}["candidate"]
    assert row["p_improvement"] < 0.05
    assert row["simultaneous_ci_upper_pct"] >= -5.0
    assert row["status"] == "inconclusive"


def test_r_rejects_a_familywise_underpowered_design(tmp_path: Path) -> None:
    endpoints = [
        {"id": f"endpoint-{index}", "label": f"endpoint {index}", "role": "non_inferiority"}
        for index in range(22)
    ]
    effects = {endpoint["id"]: (0.0, 0.0, 0.001) for endpoint in endpoints}
    raw_path, result_path, manifest_path = _synthetic_files(tmp_path, endpoints, effects, pairs=22)
    process = subprocess.run(
        [
            "Rscript",
            str(BENCHES / "analyze_ab.R"),
            str(raw_path),
            str(result_path),
            "synthetic-sha",
            manifest_path,
            "synthetic-analyzer-sha",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode != 0
    assert "underpowered for the complete family" in process.stderr
    assert "requires at least 36 balanced pairs" in process.stderr


def test_r_reports_familywise_power_not_single_endpoint_power(tmp_path: Path) -> None:
    endpoints = [
        {"id": f"endpoint-{index}", "label": f"endpoint {index}", "role": "non_inferiority"}
        for index in range(22)
    ]
    effects = {endpoint["id"]: (0.0, 0.0, 0.001) for endpoint in endpoints}
    raw_path, result_path, manifest_path = _synthetic_files(tmp_path, endpoints, effects, pairs=36)
    result = _run_r(raw_path, result_path, manifest_path)
    planning = result["planning"]
    assert planning["confirmatory_family_size"] == 22
    assert planning["family_target_power"] == 0.8
    assert planning["per_endpoint_power_target"] == pytest.approx(1 - 0.2 / 22)
    assert planning["bonferroni_noninferiority_endpoint_power"] > 0.99
    assert planning["bonferroni_family_power_lower_bound"] > 0.8
    assert planning["minimum_even_pairs"] == 36
    assert planning["power_qualified"] is True


def test_r_absolute_report_owns_summaries_and_floor_decisions(tmp_path: Path) -> None:
    workers = 8
    samples = 3
    endpoints = [
        {
            "id": "fast-candidate",
            "panel": "synthetic",
            "row_id": "fast",
            "metric_slug": "candidate",
        },
        {
            "id": "fast-reference",
            "panel": "synthetic",
            "row_id": "fast",
            "metric_slug": "reference",
        },
        {
            "id": "slow-candidate",
            "panel": "synthetic",
            "row_id": "slow",
            "metric_slug": "candidate",
        },
        {
            "id": "slow-reference",
            "panel": "synthetic",
            "row_id": "slow",
            "metric_slug": "reference",
        },
        {
            "id": "borderline-candidate",
            "panel": "synthetic",
            "row_id": "borderline",
            "metric_slug": "candidate",
        },
        {
            "id": "borderline-reference",
            "panel": "synthetic",
            "row_id": "borderline",
            "metric_slug": "reference",
        },
    ]
    comparisons = [
        {
            "id": "fast-floor",
            "family": "fast-family",
            "row_id": "fast",
            "candidate_id": "fast-candidate",
            "reference_id": "fast-reference",
            "margin_pct": 0.0,
        },
        {
            "id": "slow-floor",
            "family": "slow-family",
            "row_id": "slow",
            "candidate_id": "slow-candidate",
            "reference_id": "slow-reference",
            "margin_pct": 0.0,
        },
        {
            "id": "borderline-floor",
            "family": "borderline-family",
            "row_id": "borderline",
            "candidate_id": "borderline-candidate",
            "reference_id": "borderline-reference",
            "margin_pct": 0.0,
        },
    ]
    observations = []
    values = {
        "fast-candidate": 500_000,
        "fast-reference": 1_000_000,
        "slow-candidate": 2_000_000,
        "slow-reference": 1_000_000,
        "borderline-reference": 1_000_000,
    }
    borderline_deviations = (-0.045, -0.03, -0.015, -0.005, 0.005, 0.015, 0.03, 0.045)
    for endpoint in endpoints:
        for worker in range(workers):
            drift = 1 + (worker - workers / 2) * 0.001
            value = values.get(endpoint["id"])
            if endpoint["id"] == "borderline-candidate":
                value = 1_000_000 * math.exp(-0.021 + borderline_deviations[worker])
            assert value is not None
            for sample in range(samples):
                observations.append(
                    {
                        "cell_id": endpoint["id"],
                        "worker": worker,
                        "sample": sample,
                        "loops": 10,
                        "elapsed_ns": round(value * drift * 10),
                    }
                )
    raw = {
        "schema_version": 1,
        "kind": "absolute_report_raw",
        "run_id": "absolute-synthetic",
        "qualification_override": True,
        "design": {
            "workers": workers,
            "samples_per_process": samples,
            "target_milliseconds": 1.0,
            "alpha": 0.05,
        },
        "endpoints": endpoints,
        "comparisons": comparisons,
        "workers": [
            {
                "worker": worker,
                "python": "3.13.7",
                "package": {
                    "path": "/current/__init__.py",
                    "sha256": "c" * 64,
                },
                "extension": {
                    "path": "/current/_native.so",
                    "sha256": "a" * 64,
                    "instrumented": False,
                },
                "cell_order": ["synthetic-row"],
            }
            for worker in range(workers)
        ],
        "warmups": [
            {"cell_id": endpoint["id"], "worker": worker, "elapsed_ns": 1}
            for endpoint in endpoints
            for worker in range(workers)
        ],
        "calibration": {"worker": {"cells": [{"cell_id": "synthetic-row"}]}},
        "observations": observations,
    }
    manifest = {"absolute_report": {"alpha": 0.05}}
    raw_path = tmp_path / "absolute-raw.json"
    result_path = tmp_path / "absolute-result.json"
    manifest_path = tmp_path / "absolute-manifest.json"
    raw_path.write_text(json.dumps(raw), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    process = subprocess.run(
        [
            "Rscript",
            str(BENCHES / "analyze_report.R"),
            str(raw_path),
            str(result_path),
            "absolute-sha",
            str(manifest_path),
            "synthetic-analyzer-sha",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    result = json.loads(result_path.read_text(encoding="utf-8"))
    gates = {gate["family"]: gate["decision"] for gate in result["gates"]}
    decisions = {row["id"]: row["status"] for row in result["comparisons"]}
    assert result["engine"] == "R stats"
    assert len(result["worker_estimates"]) == len(endpoints) * workers
    assert gates == {
        "fast-family": "PASS",
        "slow-family": "FAIL",
        "borderline-family": "FAIL",
    }
    assert decisions == {
        "fast-floor": "meets_floor",
        "slow-floor": "misses_floor",
        "borderline-floor": "inconclusive",
    }
    borderline = {row["id"]: row for row in result["comparisons"]}["borderline-floor"]
    assert borderline["p_meets_floor"] < 0.05
    assert borderline["simultaneous_ci_upper_pct"] >= 0.0
    summaries = {row["id"]: row for row in result["endpoint_summaries"]}
    assert summaries["fast-candidate"]["mean_us"] == pytest.approx(499.75, abs=0.01)


def test_r_rejects_a_posthoc_family_role_change(tmp_path: Path) -> None:
    endpoints = [{"id": "fast", "label": "fast", "role": "improvement"}]
    raw_path, result_path, manifest_path = _synthetic_files(
        tmp_path, endpoints, {"fast": (-0.10, 0.0, 0.005)}
    )
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw["endpoints"][0]["role"] = "exploratory"
    raw_path.write_text(json.dumps(raw), encoding="utf-8")
    process = subprocess.run(
        [
            "Rscript",
            str(BENCHES / "analyze_ab.R"),
            str(raw_path),
            str(result_path),
            "synthetic-sha",
            manifest_path,
            "synthetic-analyzer-sha",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode != 0
    assert "changed the declared endpoint family" in process.stderr


def test_r_result_digest_and_engine_fail_closed() -> None:
    result = {
        "analysis_schema_version": 1,
        "engine": "R stats",
        "raw_sha256": "abc",
        "analyzer_sha256": "analyzer-abc",
        "family": "focused",
        "adjustment": "simultaneous Bonferroni intervals across the declared family",
        "gate_decision": "PASS",
    }
    validate_r_result(
        result,
        raw_sha256="abc",
        family="focused",
        analyzer_sha256="analyzer-abc",
    )
    for key, value, message in (
        ("raw_sha256", "stale", "digest"),
        ("analyzer_sha256", "stale", "analyzer source digest"),
        ("engine", "Python", "R stats"),
        ("adjustment", "none", "family-wise"),
    ):
        changed = copy.deepcopy(result)
        changed[key] = value
        with pytest.raises(ValueError, match=message):
            validate_r_result(
                changed,
                raw_sha256="abc",
                family="focused",
                analyzer_sha256="analyzer-abc",
            )


def test_missing_r_fails_closed_without_python_inference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_path = tmp_path / "raw.json"
    raw_path.write_text("{}", encoding="utf-8")

    def missing(*args: Any, **kwargs: Any) -> Any:
        raise FileNotFoundError

    monkeypatch.setattr(ab.subprocess, "run", missing)
    with pytest.raises(SystemExit, match="Rscript is required"):
        ab.analyze(raw_path, tmp_path / "result.json", family="focused")


def test_legacy_python_worker_aggregation_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="R owns inference"):
        _workers.across_workers("module", "function", [], workers=10)


def _valid_absolute_raw() -> dict[str, Any]:
    manifest = load_manifest()
    declared = manifest["absolute_report"]
    design = {
        "workers": 2,
        "samples_per_process": 1,
        "target_milliseconds": 0.1,
        "alpha": declared["alpha"],
    }
    endpoints = expand_report_endpoints(manifest)
    cells = expand_report_cells(manifest)
    cell_index_by_row = {cell["row_id"]: index for index, cell in enumerate(cells)}
    workers = []
    warmups = []
    observations = []
    for worker in range(design["workers"]):
        workers.append(
            {
                "worker": worker,
                "python": "3.13.7",
                "package": {
                    "path": "/current/__init__.py",
                    "sha256": "c" * 64,
                },
                "extension": {
                    "path": "/current/_native.so",
                    "sha256": "a" * 64,
                    "instrumented": False,
                },
                "cell_order": [cell["id"] for cell in cells],
            }
        )
        for endpoint in endpoints:
            warmups.append(
                {
                    "cell_id": endpoint["id"],
                    "worker": worker,
                    "elapsed_ns": 1000,
                }
            )
            observations.append(
                {
                    "cell_id": endpoint["id"],
                    "worker": worker,
                    "order_index": cell_index_by_row[endpoint["row_id"]],
                    "sample": 0,
                    "loops": 1,
                    "elapsed_ns": 1000,
                }
            )
    return {
        "schema_version": 1,
        "kind": "absolute_report_raw",
        "manifest_sha256": file_sha256(MANIFEST_PATH),
        "qualification_override": True,
        "design": design,
        "endpoints": endpoints,
        "comparisons": expand_report_comparisons(manifest),
        "workers": workers,
        "warmups": warmups,
        "observations": observations,
    }


def test_absolute_raw_contract_accepts_complete_vectorized_panel() -> None:
    validate_absolute_raw(_valid_absolute_raw())


def test_absolute_raw_contract_rejects_python_aggregate_or_incomplete_panel() -> None:
    aggregate = _valid_absolute_raw()
    aggregate["observations"][0]["mean_us"] = 1.0
    with pytest.raises(ValueError, match="inferential aggregate"):
        validate_absolute_raw(aggregate)

    incomplete = _valid_absolute_raw()
    incomplete["workers"][0]["cell_order"].pop()
    with pytest.raises(ValueError, match="complete panel"):
        validate_absolute_raw(incomplete)


@pytest.mark.parametrize("qualification", [False, True])
def test_absolute_collector_enforces_failed_r_gates_unless_qualifying(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qualification: bool,
) -> None:
    raw_path = tmp_path / "raw.json"
    result_path = tmp_path / "result.json"
    collected: dict[str, Any] = {}

    def fake_collect(**kwargs: Any) -> dict[str, Any]:
        collected.update(kwargs)
        return {
            "qualification_override": kwargs["qualification_override"],
            "comparisons": expand_report_comparisons(),
        }

    monkeypatch.setattr(collect_report, "collect", fake_collect)
    monkeypatch.setattr(
        collect_report,
        "analyze",
        lambda raw, output: {
            "gates": [
                {"family": "G3_typed_decode_beats_wrapper", "decision": "FAIL"},
                {"family": "G5_codec_floor", "decision": "PASS"},
            ]
        },
    )
    argv = ["--raw-output", str(raw_path), "--output", str(result_path)]
    if qualification:
        argv.append("--qualification")

    if qualification:
        collect_report.main(argv)
    else:
        with pytest.raises(SystemExit, match="G3_typed_decode_beats_wrapper"):
            collect_report.main(argv)

    assert collected["qualification_override"] is qualification
    assert json.loads(raw_path.read_text(encoding="utf-8"))["qualification_override"] is (
        qualification
    )


def test_absolute_collector_publishes_but_does_not_enforce_advisory_family(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_path = tmp_path / "raw.json"
    result_path = tmp_path / "result.json"
    monkeypatch.setattr(
        collect_report,
        "collect",
        lambda **kwargs: {
            "qualification_override": kwargs["qualification_override"],
            "comparisons": [
                {
                    "family": "G4_whole_encode_beats_to_builtins_alone",
                    "release_gate": False,
                }
            ],
        },
    )
    monkeypatch.setattr(
        collect_report,
        "analyze",
        lambda raw, output: {
            "gates": [
                {
                    "family": "G4_whole_encode_beats_to_builtins_alone",
                    "decision": "FAIL",
                }
            ]
        },
    )

    collect_report.main(["--raw-output", str(raw_path), "--output", str(result_path)])

    assert raw_path.is_file()
