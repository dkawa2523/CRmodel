#!/usr/bin/env python
from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from oescr import __version__
from oescr.analysis.benchmark_contract import (
    build_analysis_contract,
    build_run_fingerprint,
)
from oescr.analysis.benchmark_metrics import (
    aggregate_window_rows as _aggregate_window_rows,
)
from oescr.analysis.benchmark_metrics import (
    dominant_window_rows as _dominant_window_rows,
)
from oescr.analysis.benchmark_metrics import (
    group_indices as _group_indices,
)
from oescr.analysis.benchmark_metrics import (
    mean_abs_relative_error as _mean_abs_relative_error,
)
from oescr.analysis.benchmark_metrics import (
    physical_uncertainty_fraction as _physical_uncertainty_fraction,
)
from oescr.analysis.benchmark_metrics import (
    safe_corr as _safe_corr,
)
from oescr.analysis.benchmark_metrics import (
    safe_mean as _safe_mean,
)
from oescr.analysis.benchmark_metrics import (
    trend_label as _trend_label,
)
from oescr.analysis.benchmark_model import ChordSeries
from oescr.analysis.benchmark_renderers import (
    write_chord_comparison_csv as _write_chord_comparison_csv,
)
from oescr.analysis.benchmark_renderers import (
    write_dashboard_html as _write_dashboard_html,
)
from oescr.analysis.benchmark_renderers import (
    write_fit_quality_svg as _write_fit_quality_svg,
)
from oescr.analysis.benchmark_renderers import (
    write_flat_csv as _write_flat_csv,
)
from oescr.analysis.benchmark_renderers import (
    write_forward_dashboard_html as _write_forward_dashboard_html,
)
from oescr.analysis.benchmark_renderers import (
    write_forward_quality_svg as _write_forward_quality_svg,
)
from oescr.analysis.benchmark_renderers import (
    write_forward_spectra_svg as _write_forward_spectra_svg,
)
from oescr.analysis.benchmark_renderers import (
    write_forward_window_svg as _write_forward_window_svg,
)
from oescr.analysis.benchmark_renderers import (
    write_markdown_report as _write_markdown_report,
)
from oescr.analysis.benchmark_renderers import (
    write_parameter_recovery_svg as _write_parameter_recovery_svg,
)
from oescr.analysis.benchmark_renderers import (
    write_spectra_overview_svg as _write_spectra_overview_svg,
)
from oescr.analysis.benchmark_renderers import (
    write_window_fidelity_svg as _write_window_fidelity_svg,
)
from oescr.analysis.classification import (
    PAIR_CLASS_LOG_TOL,
    WINDOW_CLASS_THRESHOLDS,
    pair_pattern_label,
    scenario_accuracy_vs_truth,
    window_class_label,
    window_pass_rate_by_kind,
    window_quality_score,
)
from oescr.data.provenance import file_sha256
from oescr.instrument.spec import InstrumentSpec
from oescr.inverse.objectives import (
    residual_vector,
    select_windows_for_instrument,
)
from oescr.inverse.optimize import InverseSolver
from oescr.inverse.window_metrics import window_features
from oescr.io.normalize import normalize_case_config
from oescr.io.pathmap import get_path
from oescr.io.yaml_loader import load_yaml, save_yaml

BENCH_ROOT = Path(__file__).resolve().parents[2] / "examples" / "benchmarks"


def resolve_benchmark_dir(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    candidate = (BENCH_ROOT / value).resolve()
    if candidate.exists():
        return candidate
    return path.resolve()


def _load_truth_case(path: Path) -> Dict[str, Any]:
    return normalize_case_config(load_yaml(path))


def _opt_case_from_fit(solver: InverseSolver, fit_summary: Dict[str, Any]) -> Dict[str, Any]:
    cfg = deepcopy(solver.case_cfg)
    x_opt = np.asarray(fit_summary["x_opt"], dtype=float)
    return solver.params.apply_to_case(cfg, x_opt)


def _scenario_analysis(
    scenario_name: str,
    case_cfg: Dict[str, Any],
    solver: InverseSolver,
    measurements: Dict[str, List[Any]],
    windows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    fwd = solver.model.predict(case_cfg)
    residuals, aux = residual_vector(solver.model, case_cfg, solver.inv_cfg, measurements, windows)
    cost = 0.5 * float(np.dot(residuals, residuals))
    min_relative_signal = float(solver.inv_cfg.get("fit", {}).get("objective", {}).get("window_min_relative_signal", 0.02))

    chord_metrics: List[Dict[str, Any]] = []
    window_entries: List[Dict[str, Any]] = []
    comparison_series: Dict[Tuple[str, str], ChordSeries] = {}

    inst_cfg_map = {cfg["id"]: cfg for cfg in solver.model.instrument_configs_for(case_cfg)}

    for inst_id, meas_list in measurements.items():
        inst_cfg = inst_cfg_map[inst_id]
        inst_windows = select_windows_for_instrument(case_cfg, inst_cfg, windows)
        pred_by_chord = fwd.spectra[inst_id]

        for chord_idx, meas in enumerate(meas_list):
            chord_key = f"chord_{chord_idx}"
            pred = pred_by_chord[chord_key]
            pred_raw = np.interp(meas.wavelength_nm, pred["wavelength_nm"], pred["intensity"], left=0.0, right=0.0)

            gain_offset = aux.get("gain_offset", {}).get((inst_id, chord_key), {"gain": 1.0, "offset": 0.0})
            gain = float(gain_offset["gain"])
            offset = float(gain_offset["offset"])
            pred_fit = gain * pred_raw + offset

            diff = pred_fit - meas.intensity
            rmse = float(np.sqrt(np.mean(diff ** 2)))
            nrmse_std = rmse / max(float(np.std(meas.intensity)), 1.0e-30)
            nrmse_range = rmse / max(float(np.ptp(meas.intensity)), 1.0e-30)
            area_meas = float(np.trapezoid(meas.intensity, meas.wavelength_nm))
            area_fit = float(np.trapezoid(pred_fit, meas.wavelength_nm))

            chord_metrics.append(
                {
                    "scenario": scenario_name,
                    "instrument_id": inst_id,
                    "chord_key": chord_key,
                    "gain": gain,
                    "offset": offset,
                    "correlation": _safe_corr(meas.intensity, pred_fit),
                    "rmse": rmse,
                    "nrmse_std": nrmse_std,
                    "nrmse_range": nrmse_range,
                    "integrated_area_ratio": area_fit / max(abs(area_meas), 1.0e-30),
                }
            )

            comparison_series[(inst_id, chord_key)] = ChordSeries(
                wavelength_nm=np.asarray(meas.wavelength_nm, dtype=float),
                measurement=np.asarray(meas.intensity, dtype=float),
                prediction_raw=np.asarray(pred_raw, dtype=float),
                prediction_fit=np.asarray(pred_fit, dtype=float),
            )

            skipped_windows = set(aux.get("skipped_windows_low_signal", {}).get((inst_id, chord_key), []))
            local_rows: List[Dict[str, Any]] = []
            for window in inst_windows:
                center_nm = float(window["center_nm"])
                half_width_nm = float(window.get("half_width_nm", 1.0))
                feats_meas = window_features(
                    meas.wavelength_nm,
                    meas.intensity,
                    center_nm,
                    half_width_nm,
                    baseline_mode=str(window.get("baseline_mode", "local_linear")),
                )
                feats_fit = window_features(
                    meas.wavelength_nm,
                    pred_fit,
                    center_nm,
                    half_width_nm,
                    baseline_mode=str(window.get("baseline_mode", "local_linear")),
                )
                area_meas_w = float(feats_meas["area"])
                peak_meas_w = float(feats_meas["peak"])
                area_fit_w = float(feats_fit["area"])
                peak_fit_w = float(feats_fit["peak"])

                local_rows.append(
                    {
                        "scenario": scenario_name,
                        "instrument_id": inst_id,
                        "chord_key": chord_key,
                        "window_name": str(window.get("name", "")),
                        "family": str(window.get("family", "")),
                        "kind": str(window.get("kind", "")),
                        "species": str(window.get("species", "")),
                        "center_nm": center_nm,
                        "half_width_nm": half_width_nm,
                        "use_area": bool(window.get("use_area", True)),
                        "use_peak": bool(window.get("use_peak", True)),
                        "measurement_area": area_meas_w,
                        "prediction_area": area_fit_w,
                        "area_ratio": area_fit_w / max(abs(area_meas_w), 1.0e-30),
                        "measurement_peak": peak_meas_w,
                        "prediction_peak": peak_fit_w,
                        "peak_ratio": peak_fit_w / max(abs(peak_meas_w), 1.0e-30),
                        "peak_shift_nm": float(feats_fit["peak_wavelength_nm"]) - float(feats_meas["peak_wavelength_nm"]),
                        "low_signal_skipped": str(window.get("name", "")) in skipped_windows,
                    }
                )

            max_abs_area = max((abs(float(row["measurement_area"])) for row in local_rows), default=0.0)
            max_abs_peak = max((abs(float(row["measurement_peak"])) for row in local_rows), default=0.0)
            for row in local_rows:
                rel_area = abs(float(row["measurement_area"])) / max(max_abs_area, 1.0e-30)
                rel_peak = abs(float(row["measurement_peak"])) / max(max_abs_peak, 1.0e-30)
                row["relative_signal_area"] = rel_area
                row["relative_signal_peak"] = rel_peak
                row["relative_signal"] = max(rel_area, rel_peak)
                row["relative_signal_threshold"] = min_relative_signal
                window_entries.append(row)

    return {
        "cost": cost,
        "aux": aux,
        "chord_metrics": chord_metrics,
        "window_metrics": window_entries,
        "comparison_series": comparison_series,
    }


def _parameter_group_rows(
    solver: InverseSolver,
    truth_cfg: Dict[str, Any],
    opt_cfg: Dict[str, Any],
    fit_summary: Dict[str, Any],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    uncertainty_map = dict(fit_summary.get("uncertainty", {}).get("std_opt_space", {}))

    for group in solver.inv_cfg.get("parameter_groups", []):
        path = str(group["path"])
        name_prefix = str(group.get("name_prefix", path.split(".")[-1]))
        init_arr = list(get_path(solver.case_cfg, path))
        truth_arr = np.asarray(get_path(truth_cfg, path), dtype=float)
        opt_arr = np.asarray(get_path(opt_cfg, path), dtype=float)
        indices = _group_indices(group, init_arr)

        init_vals = np.asarray([float(init_arr[i]) for i in indices], dtype=float)
        truth_vals = np.asarray([float(truth_arr[i]) for i in indices], dtype=float)
        opt_vals = np.asarray([float(opt_arr[i]) for i in indices], dtype=float)

        init_err = _mean_abs_relative_error(init_vals, truth_vals)
        opt_err = _mean_abs_relative_error(opt_vals, truth_vals)
        improvement = (init_err - opt_err) / max(init_err, 1.0e-30)

        param_uncertainties: List[float] = []
        for param in solver.params.params:
            if not param.name.startswith(name_prefix):
                continue
            physical_value = float(get_path(opt_cfg, param.path))
            frac = _physical_uncertainty_fraction(param.scale, physical_value, uncertainty_map.get(param.name))
            if frac is not None:
                param_uncertainties.append(float(frac))

        rows.append(
            {
                "group": name_prefix,
                "path": path,
                "scale": str(group.get("scale", "linear")),
                "trend": _trend_label(opt_vals.tolist()),
                "init_values": [float(x) for x in init_vals],
                "opt_values": [float(x) for x in opt_vals],
                "truth_values": [float(x) for x in truth_vals],
                "init_mean_abs_rel_error": init_err,
                "opt_mean_abs_rel_error": opt_err,
                "improvement_fraction": improvement,
                "mean_relative_uncertainty": _safe_mean(param_uncertainties),
            }
        )

    return rows






def _scenario_overview_rows(scenarios: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for name, data in scenarios.items():
        chord_metrics = data["chord_metrics"]
        rows.append(
            {
                "scenario": name,
                "cost": float(data["cost"]),
                "mean_correlation": _safe_mean([float(x["correlation"]) for x in chord_metrics]),
                "mean_nrmse_std": _safe_mean([float(x["nrmse_std"]) for x in chord_metrics]),
                "mean_nrmse_range": _safe_mean([float(x["nrmse_range"]) for x in chord_metrics]),
                "mean_gain": _safe_mean([float(x["gain"]) for x in chord_metrics]),
            }
        )
    return rows


def _instrument_rows(case_cfg: Dict[str, Any], solver: InverseSolver, scenarios: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    selected_map = scenarios["opt"]["aux"].get("selected_windows", {})
    inst_cfgs = solver.model.instrument_configs_for(case_cfg)
    for inst_cfg in inst_cfgs:
        inst_id = str(inst_cfg["id"])
        inst = InstrumentSpec(inst_cfg)
        gains = [float(x["gain"]) for x in scenarios["opt"]["chord_metrics"] if x["instrument_id"] == inst_id]
        offsets = [float(x["offset"]) for x in scenarios["opt"]["chord_metrics"] if x["instrument_id"] == inst_id]
        rows.append(
            {
                "instrument_id": inst_id,
                "wavelength_min_nm": float(inst.wavelength_grid_nm.min()),
                "wavelength_max_nm": float(inst.wavelength_grid_nm.max()),
                "bin_nm": float(np.mean(np.diff(inst.wavelength_grid_nm))) if len(inst.wavelength_grid_nm) > 1 else 0.0,
                "selected_window_count": len(selected_map.get(inst_id, [])),
                "selected_windows": list(selected_map.get(inst_id, [])),
                "gain_mean": _safe_mean(gains),
                "gain_min": min(gains) if gains else 0.0,
                "gain_max": max(gains) if gains else 0.0,
                "offset_abs_max": max((abs(x) for x in offsets), default=0.0),
            }
        )
    return rows


def _window_quality_rows(window_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = _aggregate_window_rows(window_entries, ("window_name",))
    rows.sort(key=lambda x: x["mean_abs_measurement_area"], reverse=True)
    return rows


def _top_relative_uncertainties(solver: InverseSolver, opt_cfg: Dict[str, Any], fit_summary: Dict[str, Any], top_n: int = 4) -> List[Dict[str, Any]]:
    uncertainty_map = dict(fit_summary.get("uncertainty", {}).get("std_opt_space", {}))
    rows: List[Dict[str, Any]] = []
    for param in solver.params.params:
        std_opt = uncertainty_map.get(param.name)
        frac = _physical_uncertainty_fraction(param.scale, float(get_path(opt_cfg, param.path)), std_opt)
        if frac is None:
            continue
        rows.append(
            {
                "name": param.name,
                "path": param.path,
                "scale": param.scale,
                "relative_uncertainty": float(frac),
            }
        )
    rows.sort(key=lambda x: x["relative_uncertainty"], reverse=True)
    return rows[:top_n]


def _tokenize_text(text: str) -> List[str]:
    return [tok for tok in re.split(r"[^a-z0-9]+", text.lower()) if tok]


def _extract_numbers(text: str) -> List[float]:
    return [float(item) for item in re.findall(r"\d+(?:\.\d+)?", text)]


def _expected_feature_mapping(benchmark_meta: Dict[str, Any], windows: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    expected = list(benchmark_meta.get("expected_features", []))
    if not expected:
        return {}

    stop_tokens = {
        "and",
        "near",
        "with",
        "line",
        "lines",
        "broad",
        "window",
        "between",
        "centered",
        "weaker",
        "emission",
        "ionic",
        "neutral",
        "atomic",
        "separated",
    }
    feature_rows: List[Dict[str, Any]] = []
    for idx, text in enumerate(expected):
        feature_rows.append(
            {
                "feature_id": f"EF{idx + 1}",
                "tokens": {tok for tok in _tokenize_text(str(text)) if tok not in stop_tokens},
                "numbers": _extract_numbers(str(text)),
            }
        )

    out: Dict[str, List[str]] = {}
    for window in windows:
        name = str(window.get("name", ""))
        if not name:
            continue
        center = float(window.get("center_nm", 0.0))
        half_width = float(window.get("half_width_nm", 1.0))
        tokens = set(
            _tokenize_text(
                " ".join(
                    [
                        str(window.get("name", "")),
                        str(window.get("kind", "")),
                        str(window.get("family", "")),
                        str(window.get("species", "")),
                    ]
                )
            )
        )
        matches: List[str] = []
        for feat in feature_rows:
            token_overlap = len(tokens.intersection(feat["tokens"]))
            number_match = any(abs(number - center) <= max(2.0 * half_width, 5.0) for number in feat["numbers"])
            if token_overlap + (2 if number_match else 0) >= 2:
                matches.append(str(feat["feature_id"]))
        out[name] = sorted(set(matches))
    return out


def _metric_values_from_window_row(row: Dict[str, Any], metric: str) -> Tuple[float, float]:
    if metric == "area":
        return abs(float(row["prediction_area"])), abs(float(row["measurement_area"]))
    if metric == "peak":
        return abs(float(row["prediction_peak"])), abs(float(row["measurement_peak"]))
    raise ValueError(f"Unsupported pair metric: {metric}")


def _build_window_classification_rows(
    scenarios: Dict[str, Dict[str, Any]],
    feature_map: Dict[str, List[str]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for scenario_name, data in scenarios.items():
        for item in data["window_metrics"]:
            row = dict(item)
            row["scenario"] = scenario_name
            row["expected_feature_ids"] = ",".join(feature_map.get(str(row.get("window_name", "")), []))
            row["window_class"] = window_class_label(
                kind=str(row.get("kind", "")),
                use_area=bool(row.get("use_area", True)),
                use_peak=bool(row.get("use_peak", True)),
                area_ratio=float(row.get("area_ratio", 0.0)),
                peak_ratio=float(row.get("peak_ratio", 0.0)),
                abs_peak_shift_nm=abs(float(row.get("peak_shift_nm", 0.0))),
                skipped_low_signal=bool(row.get("low_signal_skipped", False)),
            )
            row["quality_pass"] = row["window_class"] == "good"
            row["quality_score"] = window_quality_score(row)
            rows.append(row)
    return rows


def _build_pair_classification_rows(
    window_class_rows: List[Dict[str, Any]],
    ratio_pairs: List[Dict[str, Any]],
    ratio_metric_default: str,
    ratio_min_signal_default: float,
) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
    for row in window_class_rows:
        key = (str(row["scenario"]), str(row["instrument_id"]), str(row["chord_key"]))
        grouped.setdefault(key, []).append(row)

    out_rows: List[Dict[str, Any]] = []
    for (scenario, inst_id, chord_key), rows in grouped.items():
        by_window = {str(item["window_name"]): item for item in rows}
        max_signal_by_metric = {
            "area": max((abs(float(item["measurement_area"])) for item in rows), default=0.0),
            "peak": max((abs(float(item["measurement_peak"])) for item in rows), default=0.0),
        }
        for pair_idx, pair in enumerate(ratio_pairs):
            pair_name = str(pair.get("name", f"pair_{pair_idx}"))
            numerator = str(pair["numerator"])
            denominator = str(pair["denominator"])
            metric = str(pair.get("metric", ratio_metric_default))
            min_relative_signal = float(pair.get("min_relative_signal", ratio_min_signal_default))
            if numerator not in by_window or denominator not in by_window:
                continue

            num_row = by_window[numerator]
            den_row = by_window[denominator]
            pred_num, meas_num = _metric_values_from_window_row(num_row, metric)
            pred_den, meas_den = _metric_values_from_window_row(den_row, metric)
            cutoff = max_signal_by_metric.get(metric, 0.0) * max(min_relative_signal, 0.0)
            supported = min(meas_num, meas_den) > cutoff and min(pred_num, pred_den) > 0.0

            log_ratio_error: float | None = None
            pair_class = "ignored_low_signal"
            measured_ratio = ""
            predicted_ratio = ""
            if supported:
                measured_ratio = meas_num / max(meas_den, 1.0e-30)
                predicted_ratio = pred_num / max(pred_den, 1.0e-30)
                log_ratio_error = float(np.log(predicted_ratio) - np.log(measured_ratio))
                pair_class = pair_pattern_label(log_ratio_error)

            out_rows.append(
                {
                    "scenario": scenario,
                    "instrument_id": inst_id,
                    "chord_key": chord_key,
                    "pair_name": pair_name,
                    "numerator": numerator,
                    "denominator": denominator,
                    "metric": metric,
                    "min_relative_signal": min_relative_signal,
                    "log_ratio_error": log_ratio_error if log_ratio_error is not None else "",
                    "measured_ratio": measured_ratio,
                    "predicted_ratio": predicted_ratio,
                    "pair_class": pair_class,
                    "supported": supported,
                }
            )
    return out_rows


def _build_classification_summary(
    scenarios: Dict[str, Dict[str, Any]],
    benchmark_meta: Dict[str, Any],
    windows: List[Dict[str, Any]],
    ratio_pairs: List[Dict[str, Any]],
    ratio_metric_default: str,
    ratio_min_signal_default: float,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    feature_map = _expected_feature_mapping(benchmark_meta, windows)
    window_rows = _build_window_classification_rows(scenarios, feature_map)
    window_accuracy = scenario_accuracy_vs_truth(
        window_rows,
        scenario_field="scenario",
        key_fields=("instrument_id", "chord_key", "window_name"),
        label_field="window_class",
    )
    for row in window_rows:
        row["truth_window_class"] = str(row.get("truth_label", ""))
        row["class_match_truth"] = bool(row.get("class_match_truth", False))
        if "truth_label" in row:
            del row["truth_label"]

    pair_rows = _build_pair_classification_rows(window_rows, ratio_pairs, ratio_metric_default, ratio_min_signal_default)
    pair_accuracy = scenario_accuracy_vs_truth(
        pair_rows,
        scenario_field="scenario",
        key_fields=("instrument_id", "chord_key", "pair_name"),
        label_field="pair_class",
    )
    for row in pair_rows:
        row["truth_pair_class"] = str(row.get("truth_label", ""))
        row["class_match_truth"] = bool(row.get("class_match_truth", False))
        if "truth_label" in row:
            del row["truth_label"]

    summary = {
        "window_class_accuracy_vs_truth": window_accuracy,
        "window_pass_rate_by_kind": window_pass_rate_by_kind(window_rows),
        "pair_pattern_accuracy_vs_truth": pair_accuracy,
        "pair_support_count": {scenario: int(values["support"]) for scenario, values in pair_accuracy.items()},
        "pair_log_error_tolerance": PAIR_CLASS_LOG_TOL,
        "window_thresholds": WINDOW_CLASS_THRESHOLDS,
    }
    return window_rows, pair_rows, summary














def _forward_window_rows(window_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = _aggregate_window_rows(
        window_entries,
        ("scenario", "window_name"),
        scenario_filter={"init", "truth"},
    )
    rows.sort(key=lambda x: (x["window_name"], x["scenario"]))
    return rows


def _compose_forward_findings(
    scenario_rows: List[Dict[str, Any]],
    dominant_windows_init: List[Dict[str, Any]],
    dominant_windows_truth: List[Dict[str, Any]],
    forward_window_rows: List[Dict[str, Any]],
) -> Tuple[List[str], List[str]]:
    scenario_map = {row["scenario"]: row for row in scenario_rows}
    init_row = scenario_map["init"]
    truth_row = scenario_map["truth"]

    plasma_findings: List[str] = []
    measurement_findings: List[str] = []

    init_dom = ", ".join(f"{row['window_name']} ({row['mean_area_ratio']:.2f})" for row in dominant_windows_init)
    truth_dom = ", ".join(f"{row['window_name']} ({row['mean_area_ratio']:.2f})" for row in dominant_windows_truth)
    plasma_findings.append(f"Initial forward mismatch is dominated by {init_dom}.")
    plasma_findings.append(f"Truth-forward agreement is dominated by {truth_dom}.")

    corr_gain = float(truth_row["mean_correlation"]) - float(init_row["mean_correlation"])
    cost_gain = 100.0 * (float(init_row["cost"]) - float(truth_row["cost"])) / max(float(init_row["cost"]), 1.0e-30)
    if cost_gain > 1.0:
        plasma_findings.append(f"Truth-forward reduces the forward-only objective by {cost_gain:.1f}% and increases mean correlation by {corr_gain:.4f}.")
    else:
        plasma_findings.append(f"Truth-forward stays in the same spectral basin as init; objective change is {cost_gain:.1f}% and mean correlation changes by {corr_gain:.4f}.")

    large_shift_windows = [row for row in forward_window_rows if row["scenario"] == "truth" and float(row["mean_abs_peak_shift_nm"]) > 1.0]
    if large_shift_windows:
        names = ", ".join(str(row["window_name"]) for row in large_shift_windows)
        plasma_findings.append(f"Broad or structured windows with residual shape/centroid mismatch remain in {names}, indicating profile/baseline sensitivity rather than simple line-intensity error.")

    gain_ratio = float(init_row["mean_gain"]) / max(float(truth_row["mean_gain"]), 1.0e-30)
    measurement_findings.append(
        f"Mean gain needed to align init-forward is {float(init_row['mean_gain']):.3f}, while truth-forward needs {float(truth_row['mean_gain']):.3f}; the ratio {gain_ratio:.2f} is the practical absolute-calibration mismatch indicator."
    )
    measurement_findings.append(
        f"Truth-forward mean NRMSE/std is {float(truth_row['mean_nrmse_std']):.4f} versus {float(init_row['mean_nrmse_std']):.4f} for init-forward."
    )
    if any(float(row["mean_area_ratio"]) < 0.0 for row in forward_window_rows):
        measurement_findings.append(
            "Negative signed area ratios on broad windows should be interpreted as local-baseline sensitivity in the integration window, not as negative physical emission."
        )

    return plasma_findings, measurement_findings
















def _compose_plasma_findings(
    benchmark_id: str,
    scenario_rows: List[Dict[str, Any]],
    parameter_rows: List[Dict[str, Any]],
    dominant_windows: List[Dict[str, Any]],
) -> List[str]:
    init_row = next(row for row in scenario_rows if row["scenario"] == "init")
    opt_row = next(row for row in scenario_rows if row["scenario"] == "opt")
    truth_row = next(row for row in scenario_rows if row["scenario"] == "truth")

    findings: List[str] = []

    dom_text = ", ".join(
        f"{row['window_name']} ({row['kind']}, area ratio {row['mean_area_ratio']:.2f})"
        for row in dominant_windows
    )
    findings.append(f"Dominant measured features are {dom_text}.")

    if opt_row["cost"] < init_row["cost"]:
        improvement = 100.0 * (init_row["cost"] - opt_row["cost"]) / max(init_row["cost"], 1.0e-30)
        findings.append(f"The inverse solution reduces the objective cost by {improvement:.1f}% relative to the initial state.")
    else:
        findings.append("The inverse solution does not materially improve the objective cost relative to the initial state.")

    if truth_row["cost"] <= opt_row["cost"] * 1.05:
        findings.append("The truth case remains within the same cost basin as the fitted case, so the fit is consistent with the benchmark physics under noise.")
    else:
        findings.append("The fitted case achieves a lower cost than the truth case, which indicates that the optimizer is fitting noise and nuisance scaling as well as the underlying physics.")

    weak_recovery = [row for row in parameter_rows if row["improvement_fraction"] < 0.1 and row["opt_mean_abs_rel_error"] > 0.05]
    if weak_recovery:
        groups = ", ".join(row["group"] for row in weak_recovery)
        findings.append(
            f"Parameter recovery against the benchmark truth is weak for {groups}; spectral agreement is being achieved mainly through shape matching rather than absolute emissivity recovery."
        )

    trends = ", ".join(f"{row['group']}: {row['trend']}" for row in parameter_rows)
    findings.append(f"Recovered radial trends are {trends}.")

    return findings


def _compose_measurement_findings(
    instrument_rows: List[Dict[str, Any]],
    window_rows: List[Dict[str, Any]],
    top_uncertainties: List[Dict[str, Any]],
) -> List[str]:
    findings: List[str] = []

    for inst in instrument_rows:
        findings.append(
            f"{inst['instrument_id']} covers {inst['wavelength_min_nm']:.1f}-{inst['wavelength_max_nm']:.1f} nm with {inst['bin_nm']:.3f} nm sampling and uses {inst['selected_window_count']} analysis windows."
        )
        findings.append(
            f"Fitted gain spans {inst['gain_min']:.3f}-{inst['gain_max']:.3f} with negligible offsets (max abs offset {inst['offset_abs_max']:.3e})."
        )

    sharp_windows = [row for row in window_rows if "band" not in row["kind"].lower()]
    if sharp_windows:
        mean_peak_shift = _safe_mean([float(row["mean_abs_peak_shift_nm"]) for row in sharp_windows])
        findings.append(
            f"Mean absolute peak shift across narrow features is {mean_peak_shift:.3f} nm, which is the practical wavelength-alignment indicator for the current inverse workflow."
        )

    if any(float(row["mean_area_ratio"]) < 0.0 for row in window_rows):
        findings.append(
            "Signed window-area ratios can become negative for broad bands when local baseline subtraction dominates the integrated residual; treat those entries as a baseline-sensitivity flag rather than a literal negative emissivity."
        )

    if top_uncertainties:
        names = ", ".join(f"{row['name']} ({100.0 * row['relative_uncertainty']:.1f}% rel.)" for row in top_uncertainties)
        findings.append(f"The least constrained fitted quantities are {names}.")

    return findings






def analyze_one(bench_dir: Path, result_dir_name: str, out_name: str) -> Path:
    bench_dir = bench_dir.resolve()
    result_dir = (bench_dir / "runs" / result_dir_name).resolve()
    out_dir = (result_dir / out_name).resolve()
    comparisons_dir = out_dir / "comparisons"
    case_truth = bench_dir / "case_truth.yaml"
    case_init = bench_dir / "case_init.yaml"
    inverse_yaml = bench_dir / "inverse.yaml"
    fit_summary_path = result_dir / "fit_summary.yaml"

    if not fit_summary_path.exists():
        raise FileNotFoundError(f"Missing fit_summary.yaml: {fit_summary_path}")

    solver = InverseSolver.from_yaml(case_init, inverse_yaml)
    fit_summary = load_yaml(fit_summary_path)
    benchmark_meta = load_yaml(bench_dir / "benchmark_meta.yaml")
    truth_cfg = _load_truth_case(case_truth)
    opt_cfg = _opt_case_from_fit(solver, fit_summary)

    scenarios = {
        "init": _scenario_analysis("init", solver.case_cfg, solver, solver.measurements, solver.windows),
        "opt": _scenario_analysis("opt", opt_cfg, solver, solver.measurements, solver.windows),
        "truth": _scenario_analysis("truth", truth_cfg, solver, solver.measurements, solver.windows),
    }

    scenario_rows = _scenario_overview_rows(scenarios)
    instrument_rows = _instrument_rows(opt_cfg, solver, scenarios)
    parameter_rows = _parameter_group_rows(solver, truth_cfg, opt_cfg, fit_summary)
    window_rows = _window_quality_rows(scenarios["opt"]["window_metrics"])
    forward_window_rows = _forward_window_rows(
        scenarios["init"]["window_metrics"] + scenarios["truth"]["window_metrics"]
    )
    dominant_windows = _dominant_window_rows(scenarios["opt"]["window_metrics"])
    dominant_windows_init = _dominant_window_rows(scenarios["init"]["window_metrics"])
    dominant_windows_truth = _dominant_window_rows(scenarios["truth"]["window_metrics"])
    top_uncertainties = _top_relative_uncertainties(solver, opt_cfg, fit_summary)
    obj_cfg = solver.inv_cfg.get("fit", {}).get("objective", {})
    ratio_pairs = list(obj_cfg.get("window_ratio_pairs", []))
    ratio_metric_default = str(obj_cfg.get("window_ratio_metric", "peak"))
    ratio_min_signal_default = float(obj_cfg.get("window_ratio_min_relative_signal", 0.02))
    window_class_rows, pair_class_rows, classification_summary = _build_classification_summary(
        scenarios,
        benchmark_meta,
        solver.windows,
        ratio_pairs,
        ratio_metric_default,
        ratio_min_signal_default,
    )

    plasma_findings = _compose_plasma_findings(
        str(benchmark_meta.get("benchmark_id", bench_dir.name)),
        scenario_rows,
        parameter_rows,
        dominant_windows,
    )
    measurement_findings = _compose_measurement_findings(instrument_rows, window_rows, top_uncertainties)
    forward_plasma_findings, forward_measurement_findings = _compose_forward_findings(
        scenario_rows,
        dominant_windows_init,
        dominant_windows_truth,
        forward_window_rows,
    )

    benchmark_title = str(benchmark_meta.get("title", bench_dir.name))
    plot_outputs = {
        "fit_quality": "plots/fit_quality.svg",
        "parameter_recovery": "plots/parameter_recovery.svg",
        "window_fidelity": "plots/window_fidelity.svg",
        "spectra_overview": "plots/spectra_overview.svg",
        "dashboard": "analysis_dashboard.html",
        "forward_quality": "plots/forward_quality.svg",
        "forward_window_fidelity": "plots/forward_window_fidelity.svg",
        "forward_spectra_overview": "plots/forward_spectra_overview.svg",
        "forward_dashboard": "forward_dashboard.html",
    }

    summary = {
        "benchmark_id": str(benchmark_meta.get("benchmark_id", bench_dir.name)),
        "title": str(benchmark_meta.get("title", bench_dir.name)),
        "source_citation": str(benchmark_meta.get("source", {}).get("citation", "")),
        "analysis_contract": build_analysis_contract(
            benchmark_id=str(benchmark_meta.get("benchmark_id", bench_dir.name)),
            benchmark_meta=benchmark_meta,
            truth_config=truth_cfg,
            measurements=solver.measurements,
            windows=solver.windows,
            objective=obj_cfg,
            metric_definition={
                "window_class_thresholds": WINDOW_CLASS_THRESHOLDS,
                "pair_class_log_tolerance": PAIR_CLASS_LOG_TOL,
            },
        ),
        "run_fingerprint": build_run_fingerprint(
            package_version=__version__,
            case_config=solver.case_cfg,
            inverse_config=solver.inv_cfg,
            fit_summary_sha256=file_sha256(fit_summary_path),
            parameter_names=solver.params.names(),
        ),
        "scenario_summary": scenario_rows,
        "instrument_summary": instrument_rows,
        "parameter_recovery": parameter_rows,
        "window_fidelity": window_rows,
        "forward_window_fidelity": forward_window_rows,
        "dominant_windows": dominant_windows,
        "dominant_windows_init": dominant_windows_init,
        "dominant_windows_truth": dominant_windows_truth,
        "plasma_oes_findings": plasma_findings,
        "measurement_engineering_findings": measurement_findings,
        "forward_plasma_oes_findings": forward_plasma_findings,
        "forward_measurement_engineering_findings": forward_measurement_findings,
        "top_relative_uncertainties": top_uncertainties,
        "classification_summary": classification_summary,
        "plot_outputs": plot_outputs,
    }
    save_yaml(summary, out_dir / "analysis_summary.yaml")

    _write_markdown_report(
        out_dir / "analysis_report.md",
        benchmark_meta,
        scenario_rows,
        instrument_rows,
        parameter_rows,
        window_rows,
        plasma_findings,
        measurement_findings,
        classification_summary,
    )

    chord_rows: List[Dict[str, Any]] = []
    for _scenario_name, data in scenarios.items():
        chord_rows.extend(data["chord_metrics"])
    _write_flat_csv(
        out_dir / "chord_metrics.csv",
        chord_rows,
        [
            "scenario",
            "instrument_id",
            "chord_key",
            "gain",
            "offset",
            "correlation",
            "rmse",
            "nrmse_std",
            "nrmse_range",
            "integrated_area_ratio",
        ],
    )
    class_index = {
        (str(item["scenario"]), str(item["instrument_id"]), str(item["chord_key"]), str(item["window_name"])): item
        for item in window_class_rows
    }
    opt_window_rows: List[Dict[str, Any]] = []
    for row in scenarios["opt"]["window_metrics"]:
        merged = dict(row)
        class_row = class_index.get(
            ("opt", str(row["instrument_id"]), str(row["chord_key"]), str(row["window_name"])),
            {},
        )
        merged["relative_signal"] = class_row.get("relative_signal", "")
        merged["low_signal_skipped"] = class_row.get("low_signal_skipped", "")
        merged["window_class"] = class_row.get("window_class", "")
        merged["quality_pass"] = class_row.get("quality_pass", "")
        merged["quality_score"] = class_row.get("quality_score", "")
        merged["expected_feature_ids"] = class_row.get("expected_feature_ids", "")
        merged["truth_window_class"] = class_row.get("truth_window_class", "")
        merged["class_match_truth"] = class_row.get("class_match_truth", "")
        opt_window_rows.append(merged)

    _write_flat_csv(
        out_dir / "window_metrics.csv",
        opt_window_rows,
        [
            "scenario",
            "instrument_id",
            "chord_key",
            "window_name",
            "family",
            "kind",
            "measurement_area",
            "prediction_area",
            "area_ratio",
            "measurement_peak",
            "prediction_peak",
            "peak_ratio",
            "peak_shift_nm",
            "relative_signal",
            "low_signal_skipped",
            "window_class",
            "quality_pass",
            "quality_score",
            "expected_feature_ids",
            "truth_window_class",
            "class_match_truth",
        ],
    )
    _write_flat_csv(
        out_dir / "classification_window_metrics.csv",
        window_class_rows,
        [
            "scenario",
            "instrument_id",
            "chord_key",
            "window_name",
            "family",
            "kind",
            "species",
            "center_nm",
            "half_width_nm",
            "relative_signal",
            "relative_signal_area",
            "relative_signal_peak",
            "low_signal_skipped",
            "window_class",
            "quality_pass",
            "quality_score",
            "expected_feature_ids",
            "truth_window_class",
            "class_match_truth",
        ],
    )
    _write_flat_csv(
        out_dir / "mixed_pattern_metrics.csv",
        pair_class_rows,
        [
            "scenario",
            "instrument_id",
            "chord_key",
            "pair_name",
            "numerator",
            "denominator",
            "metric",
            "min_relative_signal",
            "log_ratio_error",
            "measured_ratio",
            "predicted_ratio",
            "pair_class",
            "supported",
            "truth_pair_class",
            "class_match_truth",
        ],
    )

    for inst_id, chord_key in scenarios["opt"]["comparison_series"].keys():
        _write_chord_comparison_csv(comparisons_dir, inst_id, chord_key, scenarios)

    _write_fit_quality_svg(out_dir / plot_outputs["fit_quality"], benchmark_title, scenario_rows, chord_rows)
    _write_parameter_recovery_svg(out_dir / plot_outputs["parameter_recovery"], benchmark_title, parameter_rows)
    _write_window_fidelity_svg(out_dir / plot_outputs["window_fidelity"], benchmark_title, window_rows)

    inst_ids = sorted({inst_id for inst_id, _chord_key in scenarios["opt"]["comparison_series"].keys()})
    if inst_ids:
        _write_spectra_overview_svg(out_dir / plot_outputs["spectra_overview"], benchmark_title, inst_ids[0], scenarios)
    _write_dashboard_html(
        out_dir / plot_outputs["dashboard"],
        benchmark_meta,
        scenario_rows,
        plasma_findings,
        measurement_findings,
        classification_summary,
    )
    _write_forward_quality_svg(out_dir / plot_outputs["forward_quality"], benchmark_title, scenario_rows, chord_rows)
    _write_forward_window_svg(out_dir / plot_outputs["forward_window_fidelity"], benchmark_title, forward_window_rows)
    if inst_ids:
        _write_forward_spectra_svg(out_dir / plot_outputs["forward_spectra_overview"], benchmark_title, inst_ids[0], scenarios)
    _write_forward_dashboard_html(
        out_dir / plot_outputs["forward_dashboard"],
        benchmark_meta,
        scenario_rows,
        forward_plasma_findings,
        forward_measurement_findings,
        classification_summary,
    )

    return out_dir
