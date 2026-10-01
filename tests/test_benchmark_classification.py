from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oescr.analysis.classification import (
    classify_pair_log_error,
    classify_window,
    scenario_accuracy_vs_truth,
    window_pass_rate_by_kind,
)
from oescr.inverse.objectives import residual_vector
from oescr.inverse.optimize import InverseSolver

ROOT = Path(__file__).resolve().parents[1]
NF3_BENCH = ROOT / "examples" / "benchmarks" / "nf3_ar_ccp_clean_2023"


def _load_strict_gate_module():
    script_path = ROOT / "scripts" / "evaluate_strict_gate.py"
    spec = importlib.util.spec_from_file_location("evaluate_strict_gate", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load strict gate script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _skip_count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, dict):
        return sum(_skip_count(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return len(value)
    if isinstance(value, (int, float, np.integer, np.floating)):
        return int(value)
    return int(bool(value))


def test_window_and_pair_classification_rules_are_stable() -> None:
    assert (
        classify_window(
            kind="atomic_line",
            use_area=True,
            use_peak=True,
            area_ratio=1.0,
            peak_ratio=1.1,
            abs_peak_shift_nm=0.1,
            skipped_low_signal=False,
        )
        == "good"
    )
    assert (
        classify_window(
            kind="atomic_line",
            use_area=True,
            use_peak=True,
            area_ratio=1.5,
            peak_ratio=1.1,
            abs_peak_shift_nm=0.1,
            skipped_low_signal=False,
        )
        == "over"
    )
    assert (
        classify_window(
            kind="atomic_line",
            use_area=True,
            use_peak=True,
            area_ratio=0.7,
            peak_ratio=1.1,
            abs_peak_shift_nm=0.1,
            skipped_low_signal=False,
        )
        == "under"
    )
    assert (
        classify_window(
            kind="broadband_window",
            use_area=True,
            use_peak=True,
            area_ratio=1.0,
            peak_ratio=1.0,
            abs_peak_shift_nm=4.0,
            skipped_low_signal=False,
        )
        == "misaligned"
    )
    assert (
        classify_window(
            kind="broadband_window",
            use_area=True,
            use_peak=True,
            area_ratio=1.0,
            peak_ratio=1.0,
            abs_peak_shift_nm=0.1,
            skipped_low_signal=True,
        )
        == "ignored_low_signal"
    )

    assert classify_pair_log_error(0.30) == "numerator_dominant"
    assert classify_pair_log_error(0.00) == "balanced"
    assert classify_pair_log_error(-0.30) == "denominator_dominant"


def test_low_signal_windows_are_skipped_when_threshold_is_raised() -> None:
    case_yaml = NF3_BENCH / "case_init.yaml"
    inverse_yaml = NF3_BENCH / "inverse.yaml"

    solver = InverseSolver.from_yaml(case_yaml, inverse_yaml)
    base_residuals, base_aux = residual_vector(
        solver.model,
        solver.case_cfg,
        solver.inv_cfg,
        solver.measurements,
        solver.windows,
    )

    high_threshold_cfg = copy.deepcopy(solver.inv_cfg)
    high_threshold_cfg.setdefault("fit", {}).setdefault("objective", {})["window_min_relative_signal"] = 0.95
    high_residuals, high_aux = residual_vector(
        solver.model,
        solver.case_cfg,
        high_threshold_cfg,
        solver.measurements,
        solver.windows,
    )

    assert len(base_residuals) > 0
    assert len(high_residuals) > 0
    assert _skip_count(high_aux.get("skipped_windows_low_signal")) > _skip_count(base_aux.get("skipped_windows_low_signal"))


def test_classification_summary_core_logic_aggregates_expected_counts() -> None:
    window_rows = [
        {"scenario": "truth", "instrument_id": "I1", "chord_key": "C1", "window_name": "W1", "kind": "line", "window_class": "good", "quality_pass": True},
        {"scenario": "init", "instrument_id": "I1", "chord_key": "C1", "window_name": "W1", "kind": "line", "window_class": "under", "quality_pass": False},
        {"scenario": "opt", "instrument_id": "I1", "chord_key": "C1", "window_name": "W1", "kind": "line", "window_class": "good", "quality_pass": True},
        {"scenario": "truth", "instrument_id": "I1", "chord_key": "C1", "window_name": "W2", "kind": "broadband", "window_class": "ignored_low_signal", "quality_pass": False},
        {"scenario": "init", "instrument_id": "I1", "chord_key": "C1", "window_name": "W2", "kind": "broadband", "window_class": "ignored_low_signal", "quality_pass": False},
        {"scenario": "opt", "instrument_id": "I1", "chord_key": "C1", "window_name": "W2", "kind": "broadband", "window_class": "ignored_low_signal", "quality_pass": False},
    ]

    accuracy = scenario_accuracy_vs_truth(
        window_rows,
        scenario_field="scenario",
        key_fields=("instrument_id", "chord_key", "window_name"),
        label_field="window_class",
    )
    pass_rate = window_pass_rate_by_kind(window_rows)

    assert accuracy["truth"]["support"] == 1
    assert accuracy["init"]["support"] == 1
    assert accuracy["opt"]["support"] == 1
    assert accuracy["truth"]["accuracy"] == 1.0
    assert accuracy["init"]["accuracy"] == 0.0
    assert accuracy["opt"]["accuracy"] == 1.0
    assert pass_rate["truth"][0]["kind"] == "line"
    assert pass_rate["truth"][0]["pass_rate"] == 1.0
    assert pass_rate["init"][0]["pass_rate"] == 0.0
    assert pass_rate["opt"][0]["pass_rate"] == 1.0


def test_strict_gate_benchmark_delta_helper_computes_expected_deltas() -> None:
    gate = _load_strict_gate_module()
    baseline = {
        "scenario_summary": [{"scenario": "opt", "mean_correlation": 0.991, "mean_nrmse_std": 0.040}],
        "classification_summary": {
            "pair_pattern_accuracy_vs_truth": {"opt": {"accuracy": 0.70}},
            "window_class_accuracy_vs_truth": {"opt": {"accuracy": 0.62}},
            "window_pass_rate_by_kind": {"opt": [{"kind": "atomic_line", "pass_rate": 0.75}]},
        },
    }
    improved = {
        "scenario_summary": [{"scenario": "opt", "mean_correlation": 0.9905, "mean_nrmse_std": 0.041}],
        "classification_summary": {
            "pair_pattern_accuracy_vs_truth": {"opt": {"accuracy": 0.82}},
            "window_class_accuracy_vs_truth": {"opt": {"accuracy": 0.66}},
            "window_pass_rate_by_kind": {"opt": [{"kind": "atomic_line", "pass_rate": 0.80}]},
        },
    }

    result = gate._bench_result("cl2_ar_icp_fuller2001", baseline, improved)
    assert np.isclose(result["pair_acc_delta"], 0.12)
    assert np.isclose(result["window_acc_delta"], 0.04)
    assert np.isclose(result["line_pass_delta"]["atomic_line"], 0.05)
    assert result["mean_correlation_delta"] < 0.0
    assert result["mean_nrmse_std_rel_delta"] > 0.0
