#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import html
import math
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oescr.forward.model import OESCRModel
from oescr.instrument.spec import InstrumentSpec
from oescr.inverse.objectives import (
    load_measurements,
    load_windows,
    residual_vector,
    select_windows_for_instrument,
    window_features,
)
from oescr.inverse.optimize import InverseSolver
from oescr.io.normalize import normalize_case_config
from oescr.io.pathmap import get_path
from oescr.io.yaml_loader import load_yaml, save_yaml


BENCH_ROOT = Path(__file__).resolve().parents[1] / "examples" / "benchmarks"


@dataclass
class ChordSeries:
    wavelength_nm: np.ndarray
    measurement: np.ndarray
    prediction_raw: np.ndarray
    prediction_fit: np.ndarray


def _safe_mean(values: Iterable[float]) -> float:
    seq = [float(v) for v in values]
    return float(sum(seq) / len(seq)) if seq else 0.0


def _safe_corr(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 2 or len(b) < 2:
        return 1.0
    if np.allclose(a, a[0]) or np.allclose(b, b[0]):
        return 1.0
    return float(np.corrcoef(a, b)[0, 1])


def _metric_summary(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"mean": 0.0, "min": 0.0, "max": 0.0}
    arr = np.asarray(values, dtype=float)
    return {"mean": float(arr.mean()), "min": float(arr.min()), "max": float(arr.max())}


def _dominant_window_rows(window_entries: List[Dict[str, Any]], top_n: int = 3) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in window_entries:
        grouped.setdefault(str(item["window_name"]), []).append(item)

    rows: List[Dict[str, Any]] = []
    for name, items in grouped.items():
        sample = items[0]
        rows.append(
            {
                "window_name": name,
                "kind": str(sample["kind"]),
                "family": str(sample["family"]),
                "mean_abs_measurement_area": _safe_mean([abs(float(x["measurement_area"])) for x in items]),
                "mean_area_ratio": _safe_mean([float(x["area_ratio"]) for x in items]),
                "mean_peak_ratio": _safe_mean([float(x["peak_ratio"]) for x in items]),
                "mean_abs_peak_shift_nm": _safe_mean([abs(float(x["peak_shift_nm"])) for x in items]),
            }
        )

    rows.sort(key=lambda x: x["mean_abs_measurement_area"], reverse=True)
    return rows[:top_n]


def _trend_label(values: List[float]) -> str:
    if len(values) < 2:
        return "single-zone"
    diffs = np.diff(np.asarray(values, dtype=float))
    if np.all(diffs <= 0.0):
        return "monotonic decrease from core to edge"
    if np.all(diffs >= 0.0):
        return "monotonic increase from core to edge"
    return "non-monotonic radial structure"


def _group_indices(group: Dict[str, Any], arr: List[Any]) -> List[int]:
    indices_cfg = group.get("indices", "all")
    if indices_cfg in {None, "all", "*"}:
        return list(range(len(arr)))
    return [int(x) for x in indices_cfg]


def _mean_abs_relative_error(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.maximum(np.abs(b), 1.0e-30)
    return float(np.mean(np.abs(a - b) / denom))


def _physical_uncertainty_fraction(scale: str, physical_value: float, opt_space_std: float | None) -> float | None:
    if opt_space_std is None:
        return None
    if scale == "log":
        return float(10.0 ** float(opt_space_std) - 1.0)
    denom = max(abs(float(physical_value)), 1.0e-30)
    return float(abs(float(opt_space_std)) / denom)


def _resolve_benchmark_dir(value: str) -> Path:
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

    chord_metrics: List[Dict[str, Any]] = []
    window_entries: List[Dict[str, Any]] = []
    comparison_series: Dict[Tuple[str, str], ChordSeries] = {}

    inst_cfg_map = {cfg["id"]: cfg for cfg in solver.model._load_instrument_cfgs(case_cfg)}

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

            for window in inst_windows:
                feats_meas = window_features(
                    meas.wavelength_nm,
                    meas.intensity,
                    float(window["center_nm"]),
                    float(window.get("half_width_nm", 1.0)),
                    baseline_mode=str(window.get("baseline_mode", "local_linear")),
                )
                feats_fit = window_features(
                    meas.wavelength_nm,
                    pred_fit,
                    float(window["center_nm"]),
                    float(window.get("half_width_nm", 1.0)),
                    baseline_mode=str(window.get("baseline_mode", "local_linear")),
                )
                area_meas_w = float(feats_meas["area"])
                peak_meas_w = float(feats_meas["peak"])
                area_fit_w = float(feats_fit["area"])
                peak_fit_w = float(feats_fit["peak"])

                window_entries.append(
                    {
                        "scenario": scenario_name,
                        "instrument_id": inst_id,
                        "chord_key": chord_key,
                        "window_name": str(window.get("name", "")),
                        "family": str(window.get("family", "")),
                        "kind": str(window.get("kind", "")),
                        "measurement_area": area_meas_w,
                        "prediction_area": area_fit_w,
                        "area_ratio": area_fit_w / max(abs(area_meas_w), 1.0e-30),
                        "measurement_peak": peak_meas_w,
                        "prediction_peak": peak_fit_w,
                        "peak_ratio": peak_fit_w / max(abs(peak_meas_w), 1.0e-30),
                        "peak_shift_nm": float(feats_fit["peak_wavelength_nm"]) - float(feats_meas["peak_wavelength_nm"]),
                    }
                )

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


def _write_chord_comparison_csv(
    out_dir: Path,
    inst_id: str,
    chord_key: str,
    scenarios: Dict[str, Dict[str, Any]],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{inst_id}_{chord_key}_comparison.csv"

    init_series = scenarios["init"]["comparison_series"][(inst_id, chord_key)]
    opt_series = scenarios["opt"]["comparison_series"][(inst_id, chord_key)]
    truth_series = scenarios["truth"]["comparison_series"][(inst_id, chord_key)]

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "wavelength_nm",
                "measurement",
                "init_raw",
                "init_fit",
                "opt_raw",
                "opt_fit",
                "truth_raw",
                "truth_fit",
            ]
        )
        for idx, wl in enumerate(init_series.wavelength_nm):
            writer.writerow(
                [
                    f"{wl:.8f}",
                    f"{init_series.measurement[idx]:.12e}",
                    f"{init_series.prediction_raw[idx]:.12e}",
                    f"{init_series.prediction_fit[idx]:.12e}",
                    f"{opt_series.prediction_raw[idx]:.12e}",
                    f"{opt_series.prediction_fit[idx]:.12e}",
                    f"{truth_series.prediction_raw[idx]:.12e}",
                    f"{truth_series.prediction_fit[idx]:.12e}",
                ]
            )


def _write_flat_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


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
    inst_cfgs = solver.model._load_instrument_cfgs(case_cfg)
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
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in window_entries:
        grouped.setdefault(str(item["window_name"]), []).append(item)

    rows: List[Dict[str, Any]] = []
    for name, items in grouped.items():
        sample = items[0]
        rows.append(
            {
                "window_name": name,
                "kind": str(sample["kind"]),
                "family": str(sample["family"]),
                "mean_area_ratio": _safe_mean([float(x["area_ratio"]) for x in items]),
                "mean_peak_ratio": _safe_mean([float(x["peak_ratio"]) for x in items]),
                "mean_abs_peak_shift_nm": _safe_mean([abs(float(x["peak_shift_nm"])) for x in items]),
                "mean_abs_measurement_area": _safe_mean([abs(float(x["measurement_area"])) for x in items]),
            }
        )

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


PLOT_COLORS = {
    "measurement": "#111827",
    "init": "#9ca3af",
    "opt": "#2563eb",
    "truth": "#d97706",
    "area": "#2563eb",
    "peak": "#d97706",
    "shift": "#059669",
    "grid": "#e5e7eb",
    "axis": "#374151",
    "window": "#f3f4f6",
}


def _xml(text: Any) -> str:
    return html.escape(str(text), quote=True)


def _fmt_tick(value: float) -> str:
    if value == 0.0:
        return "0"
    aval = abs(value)
    if aval >= 1.0e4 or aval < 1.0e-2:
        return f"{value:.1e}"
    if aval >= 100.0:
        return f"{value:.0f}"
    if aval >= 10.0:
        return f"{value:.1f}"
    return f"{value:.2f}"


def _nice_linear_ticks(vmin: float, vmax: float, count: int = 5) -> List[float]:
    if not math.isfinite(vmin) or not math.isfinite(vmax):
        return [0.0, 1.0]
    if math.isclose(vmin, vmax):
        return [vmin - 1.0, vmin, vmin + 1.0]
    return [float(x) for x in np.linspace(vmin, vmax, count)]


def _extent(values: List[np.ndarray], pad_fraction: float = 0.05, include_zero: bool = False) -> Tuple[float, float]:
    arr = np.concatenate([np.asarray(v, dtype=float).ravel() for v in values if len(v) > 0])
    vmin = float(np.min(arr))
    vmax = float(np.max(arr))
    if include_zero:
        vmin = min(vmin, 0.0)
        vmax = max(vmax, 0.0)
    if math.isclose(vmin, vmax):
        delta = max(abs(vmin) * 0.1, 1.0)
        return vmin - delta, vmax + delta
    pad = (vmax - vmin) * pad_fraction
    return vmin - pad, vmax + pad


def _downsample_xy(x: np.ndarray, y: np.ndarray, max_points: int = 1600) -> Tuple[np.ndarray, np.ndarray]:
    if len(x) <= max_points:
        return x, y
    idx = np.linspace(0, len(x) - 1, max_points).astype(int)
    return x[idx], y[idx]


def _polyline_points(
    x: np.ndarray,
    y: np.ndarray,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    left: float,
    top: float,
    width: float,
    height: float,
) -> str:
    x_use, y_use = _downsample_xy(np.asarray(x, dtype=float), np.asarray(y, dtype=float))
    xr = max(xmax - xmin, 1.0e-30)
    yr = max(ymax - ymin, 1.0e-30)
    pts = []
    for xv, yv in zip(x_use, y_use):
        sx = left + (float(xv) - xmin) / xr * width
        sy = top + height - (float(yv) - ymin) / yr * height
        pts.append(f"{sx:.2f},{sy:.2f}")
    return " ".join(pts)


def _draw_axes(
    lines: List[str],
    left: float,
    top: float,
    width: float,
    height: float,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    x_label: str,
    y_label: str,
    show_x_ticks: bool = True,
) -> None:
    lines.append(f'<rect x="{left:.1f}" y="{top:.1f}" width="{width:.1f}" height="{height:.1f}" fill="white" stroke="{PLOT_COLORS["axis"]}" stroke-width="1"/>')

    for tick in _nice_linear_ticks(ymin, ymax, 5):
        sy = top + height - (tick - ymin) / max(ymax - ymin, 1.0e-30) * height
        lines.append(f'<line x1="{left:.1f}" y1="{sy:.1f}" x2="{left + width:.1f}" y2="{sy:.1f}" stroke="{PLOT_COLORS["grid"]}" stroke-width="1"/>')
        lines.append(f'<text x="{left - 8:.1f}" y="{sy + 4:.1f}" text-anchor="end" font-size="11" fill="{PLOT_COLORS["axis"]}">{_xml(_fmt_tick(tick))}</text>')

    if show_x_ticks:
        for tick in _nice_linear_ticks(xmin, xmax, 6):
            sx = left + (tick - xmin) / max(xmax - xmin, 1.0e-30) * width
            lines.append(f'<line x1="{sx:.1f}" y1="{top:.1f}" x2="{sx:.1f}" y2="{top + height:.1f}" stroke="{PLOT_COLORS["grid"]}" stroke-width="1"/>')
            lines.append(f'<text x="{sx:.1f}" y="{top + height + 16:.1f}" text-anchor="middle" font-size="11" fill="{PLOT_COLORS["axis"]}">{_xml(_fmt_tick(tick))}</text>')

    lines.append(f'<text x="{left + width / 2:.1f}" y="{top + height + 34:.1f}" text-anchor="middle" font-size="12" fill="{PLOT_COLORS["axis"]}">{_xml(x_label)}</text>')
    lines.append(f'<text x="{left - 46:.1f}" y="{top - 8:.1f}" text-anchor="start" font-size="12" fill="{PLOT_COLORS["axis"]}">{_xml(y_label)}</text>')


def _svg_document(width: int, height: int, title: str, body: List[str]) -> str:
    head = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>",
        "text { font-family: Arial, sans-serif; }",
        "</style>",
        f'<rect width="{width}" height="{height}" fill="white"/>',
        f'<text x="24" y="30" font-size="22" font-weight="700" fill="#111827">{_xml(title)}</text>',
    ]
    tail = ["</svg>"]
    return "\n".join(head + body + tail)


def _write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_spectra_overview_svg(
    path: Path,
    benchmark_title: str,
    inst_id: str,
    scenarios: Dict[str, Dict[str, Any]],
) -> None:
    chord_keys = sorted(
        chord_key
        for plot_inst_id, chord_key in scenarios["opt"]["comparison_series"].keys()
        if plot_inst_id == inst_id
    )
    panel_height = 150
    width = 1300
    height = 110 + len(chord_keys) * (panel_height + 35)
    left = 90.0
    plot_width = 1160.0

    body: List[str] = []
    body.append(f'<text x="24" y="56" font-size="14" fill="#4b5563">{_xml(benchmark_title)} / {inst_id}</text>')

    legend_items = [
        ("Measurement", PLOT_COLORS["measurement"], ""),
        ("Init fit", PLOT_COLORS["init"], ' stroke-dasharray="6,4"'),
        ("Opt fit", PLOT_COLORS["opt"], ""),
        ("Truth fit", PLOT_COLORS["truth"], ' stroke-dasharray="2,3"'),
    ]
    lx = 24.0
    ly = 78.0
    for label, color, dash in legend_items:
        body.append(f'<line x1="{lx:.1f}" y1="{ly:.1f}" x2="{lx + 28:.1f}" y2="{ly:.1f}" stroke="{color}" stroke-width="3"{dash}/>')
        body.append(f'<text x="{lx + 36:.1f}" y="{ly + 4:.1f}" font-size="12" fill="#374151">{_xml(label)}</text>')
        lx += 160.0

    for idx, chord_key in enumerate(chord_keys):
        top = 100.0 + idx * (panel_height + 35.0)
        init_series = scenarios["init"]["comparison_series"][(inst_id, chord_key)]
        opt_series = scenarios["opt"]["comparison_series"][(inst_id, chord_key)]
        truth_series = scenarios["truth"]["comparison_series"][(inst_id, chord_key)]
        x = init_series.wavelength_nm
        y_arrays = [
            init_series.measurement,
            init_series.prediction_fit,
            opt_series.prediction_fit,
            truth_series.prediction_fit,
        ]
        xmin, xmax = float(np.min(x)), float(np.max(x))
        ymin, ymax = _extent(y_arrays, pad_fraction=0.05, include_zero=False)

        _draw_axes(body, left, top, plot_width, panel_height, xmin, xmax, ymin, ymax, "Wavelength (nm)", "Intensity", show_x_ticks=True)
        body.append(f'<text x="{left:.1f}" y="{top - 14:.1f}" font-size="13" font-weight="700" fill="#111827">{_xml(chord_key)}</text>')

        series_specs = [
            (init_series.measurement, PLOT_COLORS["measurement"], "", 2.0),
            (init_series.prediction_fit, PLOT_COLORS["init"], ' stroke-dasharray="6,4"', 1.8),
            (opt_series.prediction_fit, PLOT_COLORS["opt"], "", 2.1),
            (truth_series.prediction_fit, PLOT_COLORS["truth"], ' stroke-dasharray="2,3"', 1.8),
        ]
        for y, color, dash, stroke_width in series_specs:
            points = _polyline_points(x, y, xmin, xmax, ymin, ymax, left, top, plot_width, panel_height)
            body.append(f'<polyline fill="none" stroke="{color}" stroke-width="{stroke_width}"{dash} points="{points}"/>')

    _write_text_file(path, _svg_document(width, height, f"Spectral Overlays: {inst_id}", body))


def _write_fit_quality_svg(
    path: Path,
    benchmark_title: str,
    scenario_rows: List[Dict[str, Any]],
    chord_rows: List[Dict[str, Any]],
) -> None:
    width = 1200
    height = 940
    body: List[str] = []
    body.append(f'<text x="24" y="56" font-size="14" fill="#4b5563">{_xml(benchmark_title)}</text>')

    scenarios_order = ["init", "opt", "truth"]
    scenario_map = {row["scenario"]: row for row in scenario_rows}

    # Panel 1: scenario cost
    left = 90.0
    top = 90.0
    plot_width = 420.0
    plot_height = 220.0
    cost_values = [float(scenario_map[name]["cost"]) for name in scenarios_order]
    ymin, ymax = _extent([np.asarray(cost_values, dtype=float)], pad_fraction=0.1, include_zero=False)
    _draw_axes(body, left, top, plot_width, plot_height, -0.5, 2.5, ymin, ymax, "Scenario", "Cost", show_x_ticks=False)
    bar_width = plot_width / 6.0
    for idx, name in enumerate(scenarios_order):
        sx = left + (idx + 0.5) / 3.0 * plot_width - bar_width / 2.0
        sy = top + plot_height - (cost_values[idx] - ymin) / max(ymax - ymin, 1.0e-30) * plot_height
        body.append(f'<rect x="{sx:.1f}" y="{sy:.1f}" width="{bar_width:.1f}" height="{top + plot_height - sy:.1f}" fill="{PLOT_COLORS.get(name, "#2563eb")}"/>')
        body.append(f'<text x="{sx + bar_width / 2:.1f}" y="{top + plot_height + 18:.1f}" text-anchor="middle" font-size="12" fill="#374151">{_xml(name)}</text>')
        body.append(f'<text x="{sx + bar_width / 2:.1f}" y="{sy - 6:.1f}" text-anchor="middle" font-size="11" fill="#111827">{_xml(_fmt_tick(cost_values[idx]))}</text>')
    body.append(f'<text x="{left:.1f}" y="{top - 14:.1f}" font-size="13" font-weight="700" fill="#111827">Objective cost by scenario</text>')

    # Panel 2 and 3: per-chord correlation and nrmse
    chord_order = sorted({str(row["chord_key"]) for row in chord_rows})
    for panel_idx, metric_key, title, y_label in [
        (0, "correlation", "Chord-wise correlation", "Correlation"),
        (1, "nrmse_std", "Chord-wise NRMSE/std", "NRMSE/std"),
    ]:
        panel_left = 90.0
        panel_top = 380.0 + panel_idx * 260.0
        panel_width = 1000.0
        panel_height = 180.0
        values = [float(row[metric_key]) for row in chord_rows]
        ymin2, ymax2 = _extent([np.asarray(values, dtype=float)], pad_fraction=0.1, include_zero=(metric_key != "correlation"))
        if metric_key == "correlation":
            ymin2 = min(ymin2, 0.95)
            ymax2 = max(ymax2, 1.0)
        _draw_axes(body, panel_left, panel_top, panel_width, panel_height, 0.0, float(len(chord_order) - 1), ymin2, ymax2, "Chord index", y_label, show_x_ticks=False)
        body.append(f'<text x="{panel_left:.1f}" y="{panel_top - 14:.1f}" font-size="13" font-weight="700" fill="#111827">{_xml(title)}</text>')

        for chord_idx, chord_key in enumerate(chord_order):
            sx = panel_left + chord_idx / max(len(chord_order) - 1, 1) * panel_width
            body.append(f'<line x1="{sx:.1f}" y1="{panel_top:.1f}" x2="{sx:.1f}" y2="{panel_top + panel_height:.1f}" stroke="{PLOT_COLORS["grid"]}" stroke-width="1"/>')
            body.append(f'<text x="{sx:.1f}" y="{panel_top + panel_height + 16:.1f}" text-anchor="middle" font-size="11" fill="#374151">{_xml(chord_key.replace("chord_", ""))}</text>')

        for scenario_name in scenarios_order:
            series_rows = [row for row in chord_rows if row["scenario"] == scenario_name]
            series_rows.sort(key=lambda x: x["chord_key"])
            x_vals = np.asarray(list(range(len(series_rows))), dtype=float)
            y_vals = np.asarray([float(row[metric_key]) for row in series_rows], dtype=float)
            points = _polyline_points(x_vals, y_vals, 0.0, float(len(chord_order) - 1), ymin2, ymax2, panel_left, panel_top, panel_width, panel_height)
            dash = ' stroke-dasharray="6,4"' if scenario_name == "init" else (' stroke-dasharray="2,3"' if scenario_name == "truth" else "")
            body.append(f'<polyline fill="none" stroke="{PLOT_COLORS.get(scenario_name, "#2563eb")}" stroke-width="2.5"{dash} points="{points}"/>')
            for xv, yv in zip(x_vals, y_vals):
                sx = panel_left + xv / max(len(chord_order) - 1, 1) * panel_width
                sy = panel_top + panel_height - (yv - ymin2) / max(ymax2 - ymin2, 1.0e-30) * panel_height
                body.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="3.5" fill="{PLOT_COLORS.get(scenario_name, "#2563eb")}"/>')

    legend_x = 620.0
    legend_y = 112.0
    for idx, scenario_name in enumerate(scenarios_order):
        yy = legend_y + idx * 22.0
        dash = ' stroke-dasharray="6,4"' if scenario_name == "init" else (' stroke-dasharray="2,3"' if scenario_name == "truth" else "")
        body.append(f'<line x1="{legend_x:.1f}" y1="{yy:.1f}" x2="{legend_x + 24:.1f}" y2="{yy:.1f}" stroke="{PLOT_COLORS.get(scenario_name, "#2563eb")}" stroke-width="3"{dash}/>')
        body.append(f'<text x="{legend_x + 32:.1f}" y="{yy + 4:.1f}" font-size="12" fill="#374151">{_xml(scenario_name)}</text>')

    _write_text_file(path, _svg_document(width, height, "Fit Quality Overview", body))


def _write_parameter_recovery_svg(path: Path, benchmark_title: str, parameter_rows: List[Dict[str, Any]]) -> None:
    n_panels = len(parameter_rows)
    n_cols = 2
    n_rows = int(math.ceil(n_panels / n_cols))
    width = 1200
    panel_width = 480.0
    panel_height = 220.0
    height = 100 + n_rows * 280
    body: List[str] = []
    body.append(f'<text x="24" y="56" font-size="14" fill="#4b5563">{_xml(benchmark_title)}</text>')

    for idx, row in enumerate(parameter_rows):
        col = idx % n_cols
        grid_row = idx // n_cols
        left = 90.0 + col * 560.0
        top = 100.0 + grid_row * 280.0
        x_vals = np.asarray(list(range(len(row["init_values"]))), dtype=float)
        series_map = {
            "init": np.asarray(row["init_values"], dtype=float),
            "opt": np.asarray(row["opt_values"], dtype=float),
            "truth": np.asarray(row["truth_values"], dtype=float),
        }

        scale = str(row.get("scale", "linear"))
        if scale == "log":
            transformed = [np.log10(np.maximum(vals, 1.0e-30)) for vals in series_map.values()]
            ymin, ymax = _extent(transformed, pad_fraction=0.08, include_zero=False)
            y_label = "log10(value)"
        else:
            transformed = list(series_map.values())
            ymin, ymax = _extent(transformed, pad_fraction=0.08, include_zero=False)
            y_label = "value"

        _draw_axes(body, left, top, panel_width, panel_height, 0.0, float(len(x_vals) - 1), ymin, ymax, "Shell index", y_label, show_x_ticks=False)
        body.append(f'<text x="{left:.1f}" y="{top - 14:.1f}" font-size="13" font-weight="700" fill="#111827">{_xml(str(row["group"]))}</text>')
        body.append(
            f'<text x="{left + 160:.1f}" y="{top - 14:.1f}" font-size="11" fill="#4b5563">opt rel err {float(row["opt_mean_abs_rel_error"]):.3f}, uncertainty {float(row["mean_relative_uncertainty"]):.3f}</text>'
        )

        for x_idx in range(len(x_vals)):
            sx = left + x_idx / max(len(x_vals) - 1, 1) * panel_width
            body.append(f'<line x1="{sx:.1f}" y1="{top:.1f}" x2="{sx:.1f}" y2="{top + panel_height:.1f}" stroke="{PLOT_COLORS["grid"]}" stroke-width="1"/>')
            body.append(f'<text x="{sx:.1f}" y="{top + panel_height + 16:.1f}" text-anchor="middle" font-size="11" fill="#374151">{x_idx}</text>')

        for name, vals in series_map.items():
            plot_vals = np.log10(np.maximum(vals, 1.0e-30)) if scale == "log" else vals
            points = _polyline_points(x_vals, plot_vals, 0.0, float(len(x_vals) - 1), ymin, ymax, left, top, panel_width, panel_height)
            dash = ' stroke-dasharray="6,4"' if name == "init" else (' stroke-dasharray="2,3"' if name == "truth" else "")
            body.append(f'<polyline fill="none" stroke="{PLOT_COLORS.get(name, "#2563eb")}" stroke-width="2.5"{dash} points="{points}"/>')
            for xv, yv in zip(x_vals, plot_vals):
                sx = left + xv / max(len(x_vals) - 1, 1) * panel_width
                sy = top + panel_height - (float(yv) - ymin) / max(ymax - ymin, 1.0e-30) * panel_height
                body.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="3.5" fill="{PLOT_COLORS.get(name, "#2563eb")}"/>')

    legend_x = 820.0
    legend_y = 56.0
    for idx, name in enumerate(["init", "opt", "truth"]):
        yy = legend_y + idx * 18.0
        dash = ' stroke-dasharray="6,4"' if name == "init" else (' stroke-dasharray="2,3"' if name == "truth" else "")
        body.append(f'<line x1="{legend_x:.1f}" y1="{yy:.1f}" x2="{legend_x + 24:.1f}" y2="{yy:.1f}" stroke="{PLOT_COLORS.get(name, "#2563eb")}" stroke-width="3"{dash}/>')
        body.append(f'<text x="{legend_x + 30:.1f}" y="{yy + 4:.1f}" font-size="12" fill="#374151">{_xml(name)}</text>')

    _write_text_file(path, _svg_document(width, height, "Parameter Recovery", body))


def _write_window_fidelity_svg(path: Path, benchmark_title: str, window_rows: List[Dict[str, Any]]) -> None:
    rows = window_rows[:8]
    width = 1320
    height = 860
    left = 280.0
    plot_width = 980.0
    body: List[str] = []
    body.append(f'<text x="24" y="56" font-size="14" fill="#4b5563">{_xml(benchmark_title)}</text>')

    # Ratios panel
    top = 100.0
    plot_height = 340.0
    all_ratio_values = [float(row["mean_area_ratio"]) for row in rows] + [float(row["mean_peak_ratio"]) for row in rows]
    xmin = min(min(all_ratio_values), 0.0) - 0.15
    xmax = max(max(all_ratio_values), 1.0) + 0.15
    _draw_axes(body, left, top, plot_width, plot_height, xmin, xmax, -0.5, float(len(rows) - 0.5), "Ratio to measurement", "Window", show_x_ticks=True)
    body.append(f'<text x="{left:.1f}" y="{top - 14:.1f}" font-size="13" font-weight="700" fill="#111827">Window area and peak ratios</text>')
    x_one = left + (1.0 - xmin) / max(xmax - xmin, 1.0e-30) * plot_width
    x_zero = left + (0.0 - xmin) / max(xmax - xmin, 1.0e-30) * plot_width
    body.append(f'<line x1="{x_one:.1f}" y1="{top:.1f}" x2="{x_one:.1f}" y2="{top + plot_height:.1f}" stroke="#dc2626" stroke-width="2" stroke-dasharray="4,4"/>')
    body.append(f'<line x1="{x_zero:.1f}" y1="{top:.1f}" x2="{x_zero:.1f}" y2="{top + plot_height:.1f}" stroke="#9ca3af" stroke-width="1" stroke-dasharray="2,4"/>')
    for idx, row in enumerate(rows):
        cy = top + (idx + 0.5) / len(rows) * plot_height
        area_val = float(row["mean_area_ratio"])
        peak_val = float(row["mean_peak_ratio"])
        for val, color, yoff in [(area_val, PLOT_COLORS["area"], -8.0), (peak_val, PLOT_COLORS["peak"], 8.0)]:
            x0 = left + (min(1.0, val) - xmin) / max(xmax - xmin, 1.0e-30) * plot_width
            x1 = left + (max(1.0, val) - xmin) / max(xmax - xmin, 1.0e-30) * plot_width
            if val < 1.0:
                x0 = left + (val - xmin) / max(xmax - xmin, 1.0e-30) * plot_width
                x1 = left + (1.0 - xmin) / max(xmax - xmin, 1.0e-30) * plot_width
            body.append(f'<rect x="{min(x0, x1):.1f}" y="{cy + yoff - 5:.1f}" width="{abs(x1 - x0):.1f}" height="10" fill="{color}" opacity="0.85"/>')
        body.append(f'<text x="{left - 10:.1f}" y="{cy + 4:.1f}" text-anchor="end" font-size="12" fill="#374151">{_xml(str(row["window_name"]))}</text>')
        body.append(f'<text x="{left + plot_width + 8:.1f}" y="{cy - 4:.1f}" font-size="11" fill="{PLOT_COLORS["area"]}">A {_xml(_fmt_tick(area_val))}</text>')
        body.append(f'<text x="{left + plot_width + 8:.1f}" y="{cy + 10:.1f}" font-size="11" fill="{PLOT_COLORS["peak"]}">P {_xml(_fmt_tick(peak_val))}</text>')

    # Peak shift panel
    top2 = 520.0
    plot_height2 = 220.0
    shift_values = [float(row["mean_abs_peak_shift_nm"]) for row in rows]
    _, ymax_shift = _extent([np.asarray(shift_values, dtype=float)], pad_fraction=0.15, include_zero=True)
    _draw_axes(body, left, top2, plot_width, plot_height2, -0.5, float(len(rows) - 0.5), 0.0, ymax_shift, "Window index", "Abs peak shift (nm)", show_x_ticks=False)
    body.append(f'<text x="{left:.1f}" y="{top2 - 14:.1f}" font-size="13" font-weight="700" fill="#111827">Mean absolute peak shift</text>')
    bar_w = plot_width / max(len(rows) * 1.8, 1.0)
    for idx, row in enumerate(rows):
        value = float(row["mean_abs_peak_shift_nm"])
        sx = left + (idx + 0.5) / len(rows) * plot_width - bar_w / 2.0
        sy = top2 + plot_height2 - value / max(ymax_shift, 1.0e-30) * plot_height2
        body.append(f'<rect x="{sx:.1f}" y="{sy:.1f}" width="{bar_w:.1f}" height="{top2 + plot_height2 - sy:.1f}" fill="{PLOT_COLORS["shift"]}"/>')
        body.append(f'<text x="{sx + bar_w / 2:.1f}" y="{top2 + plot_height2 + 16:.1f}" text-anchor="middle" font-size="11" fill="#374151">{idx + 1}</text>')
        body.append(f'<text x="{sx + bar_w / 2:.1f}" y="{sy - 6:.1f}" text-anchor="middle" font-size="11" fill="#111827">{_xml(_fmt_tick(value))}</text>')

    _write_text_file(path, _svg_document(width, height, "Window Fidelity", body))


def _write_dashboard_html(
    path: Path,
    benchmark_meta: Dict[str, Any],
    scenario_rows: List[Dict[str, Any]],
    plasma_findings: List[str],
    measurement_findings: List[str],
) -> None:
    title = str(benchmark_meta.get("title", benchmark_meta.get("benchmark_id", path.parent.name)))
    benchmark_id = str(benchmark_meta.get("benchmark_id", ""))
    source = str(benchmark_meta.get("source", {}).get("citation", ""))
    html_text = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{_xml(title)} - Analysis Dashboard</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #111827; background: #f8fafc; }}
    h1, h2 {{ margin-bottom: 8px; }}
    .card {{ background: white; border: 1px solid #e5e7eb; border-radius: 12px; padding: 18px; margin-bottom: 18px; }}
    .meta {{ color: #4b5563; font-size: 14px; }}
    .plots img {{ width: 100%; max-width: 1200px; border: 1px solid #e5e7eb; border-radius: 10px; background: white; }}
    ul {{ margin-top: 6px; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 720px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px 10px; text-align: left; font-size: 14px; }}
    th {{ background: #f3f4f6; }}
    a {{ color: #2563eb; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{_xml(title)}</h1>
    <div class="meta">Benchmark ID: {_xml(benchmark_id)}</div>
    <div class="meta">Source: {_xml(source)}</div>
    <div class="meta"><a href="analysis_report.md">Markdown report</a> | <a href="analysis_summary.yaml">YAML summary</a> | <a href="chord_metrics.csv">Chord metrics</a> | <a href="window_metrics.csv">Window metrics</a></div>
  </div>
  <div class="card">
    <h2>Scenario Snapshot</h2>
    <table>
      <tr><th>Scenario</th><th>Cost</th><th>Mean Corr.</th><th>Mean NRMSE/std</th><th>Mean Gain</th></tr>
      {''.join(f"<tr><td>{_xml(row['scenario'])}</td><td>{float(row['cost']):.4f}</td><td>{float(row['mean_correlation']):.4f}</td><td>{float(row['mean_nrmse_std']):.4f}</td><td>{float(row['mean_gain']):.4f}</td></tr>" for row in scenario_rows)}
    </table>
  </div>
  <div class="card">
    <h2>Plasma OES Interpretation</h2>
    <ul>{''.join(f"<li>{_xml(item)}</li>" for item in plasma_findings)}</ul>
  </div>
  <div class="card">
    <h2>Measurement Engineering Interpretation</h2>
    <ul>{''.join(f"<li>{_xml(item)}</li>" for item in measurement_findings)}</ul>
  </div>
  <div class="card plots">
    <h2>Fit Quality</h2>
    <img src="plots/fit_quality.svg" alt="Fit quality plot">
  </div>
  <div class="card plots">
    <h2>Parameter Recovery</h2>
    <img src="plots/parameter_recovery.svg" alt="Parameter recovery plot">
  </div>
  <div class="card plots">
    <h2>Window Fidelity</h2>
    <img src="plots/window_fidelity.svg" alt="Window fidelity plot">
  </div>
  <div class="card plots">
    <h2>Spectral Overlays</h2>
    <img src="plots/spectra_overview.svg" alt="Spectral overlay plot">
  </div>
</body>
</html>
"""
    _write_text_file(path, html_text)


def _forward_window_rows(window_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for item in window_entries:
        scenario = str(item["scenario"])
        if scenario not in {"init", "truth"}:
            continue
        grouped.setdefault((scenario, str(item["window_name"])), []).append(item)

    rows: List[Dict[str, Any]] = []
    for (scenario, window_name), items in grouped.items():
        sample = items[0]
        rows.append(
            {
                "scenario": scenario,
                "window_name": window_name,
                "kind": str(sample["kind"]),
                "family": str(sample["family"]),
                "mean_area_ratio": _safe_mean([float(x["area_ratio"]) for x in items]),
                "mean_peak_ratio": _safe_mean([float(x["peak_ratio"]) for x in items]),
                "mean_abs_peak_shift_nm": _safe_mean([abs(float(x["peak_shift_nm"])) for x in items]),
                "mean_abs_measurement_area": _safe_mean([abs(float(x["measurement_area"])) for x in items]),
            }
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


def _write_forward_spectra_svg(
    path: Path,
    benchmark_title: str,
    inst_id: str,
    scenarios: Dict[str, Dict[str, Any]],
) -> None:
    chord_keys = sorted(
        chord_key
        for plot_inst_id, chord_key in scenarios["init"]["comparison_series"].keys()
        if plot_inst_id == inst_id
    )
    panel_height = 150
    width = 1300
    height = 110 + len(chord_keys) * (panel_height + 35)
    left = 90.0
    plot_width = 1160.0
    body: List[str] = []
    body.append(f'<text x="24" y="56" font-size="14" fill="#4b5563">{_xml(benchmark_title)} / {inst_id}</text>')

    legend_items = [
        ("Measurement", PLOT_COLORS["measurement"], ""),
        ("Init forward", PLOT_COLORS["init"], ' stroke-dasharray="6,4"'),
        ("Truth forward", PLOT_COLORS["truth"], ""),
    ]
    lx = 24.0
    ly = 78.0
    for label, color, dash in legend_items:
        body.append(f'<line x1="{lx:.1f}" y1="{ly:.1f}" x2="{lx + 28:.1f}" y2="{ly:.1f}" stroke="{color}" stroke-width="3"{dash}/>')
        body.append(f'<text x="{lx + 36:.1f}" y="{ly + 4:.1f}" font-size="12" fill="#374151">{_xml(label)}</text>')
        lx += 180.0

    for idx, chord_key in enumerate(chord_keys):
        top = 100.0 + idx * (panel_height + 35.0)
        init_series = scenarios["init"]["comparison_series"][(inst_id, chord_key)]
        truth_series = scenarios["truth"]["comparison_series"][(inst_id, chord_key)]
        x = init_series.wavelength_nm
        y_arrays = [init_series.measurement, init_series.prediction_fit, truth_series.prediction_fit]
        xmin, xmax = float(np.min(x)), float(np.max(x))
        ymin, ymax = _extent(y_arrays, pad_fraction=0.05, include_zero=False)

        _draw_axes(body, left, top, plot_width, panel_height, xmin, xmax, ymin, ymax, "Wavelength (nm)", "Intensity", show_x_ticks=True)
        body.append(f'<text x="{left:.1f}" y="{top - 14:.1f}" font-size="13" font-weight="700" fill="#111827">{_xml(chord_key)}</text>')

        series_specs = [
            (init_series.measurement, PLOT_COLORS["measurement"], "", 2.0),
            (init_series.prediction_fit, PLOT_COLORS["init"], ' stroke-dasharray="6,4"', 1.8),
            (truth_series.prediction_fit, PLOT_COLORS["truth"], "", 2.0),
        ]
        for y, color, dash, stroke_width in series_specs:
            points = _polyline_points(x, y, xmin, xmax, ymin, ymax, left, top, plot_width, panel_height)
            body.append(f'<polyline fill="none" stroke="{color}" stroke-width="{stroke_width}"{dash} points="{points}"/>')

    _write_text_file(path, _svg_document(width, height, f"Forward Spectral Overlays: {inst_id}", body))


def _write_forward_quality_svg(
    path: Path,
    benchmark_title: str,
    scenario_rows: List[Dict[str, Any]],
    chord_rows: List[Dict[str, Any]],
) -> None:
    forward_scenarios = ["init", "truth"]
    scenario_map = {row["scenario"]: row for row in scenario_rows}
    width = 1200
    height = 900
    body: List[str] = []
    body.append(f'<text x="24" y="56" font-size="14" fill="#4b5563">{_xml(benchmark_title)}</text>')

    left = 90.0
    top = 90.0
    plot_width = 420.0
    plot_height = 220.0
    cost_values = [float(scenario_map[name]["cost"]) for name in forward_scenarios]
    ymin, ymax = _extent([np.asarray(cost_values, dtype=float)], pad_fraction=0.1, include_zero=False)
    _draw_axes(body, left, top, plot_width, plot_height, -0.5, 1.5, ymin, ymax, "Scenario", "Cost", show_x_ticks=False)
    bar_width = plot_width / 5.0
    for idx, name in enumerate(forward_scenarios):
        sx = left + (idx + 0.5) / 2.0 * plot_width - bar_width / 2.0
        sy = top + plot_height - (cost_values[idx] - ymin) / max(ymax - ymin, 1.0e-30) * plot_height
        body.append(f'<rect x="{sx:.1f}" y="{sy:.1f}" width="{bar_width:.1f}" height="{top + plot_height - sy:.1f}" fill="{PLOT_COLORS.get(name, "#2563eb")}"/>')
        body.append(f'<text x="{sx + bar_width / 2:.1f}" y="{top + plot_height + 18:.1f}" text-anchor="middle" font-size="12" fill="#374151">{_xml(name)}</text>')
        body.append(f'<text x="{sx + bar_width / 2:.1f}" y="{sy - 6:.1f}" text-anchor="middle" font-size="11" fill="#111827">{_xml(_fmt_tick(cost_values[idx]))}</text>')
    body.append(f'<text x="{left:.1f}" y="{top - 14:.1f}" font-size="13" font-weight="700" fill="#111827">Forward-only objective by scenario</text>')

    panel_specs = [
        ("correlation", "Chord-wise correlation", "Correlation", 380.0),
        ("nrmse_std", "Chord-wise NRMSE/std", "NRMSE/std", 620.0),
    ]
    chord_order = sorted({str(row["chord_key"]) for row in chord_rows if row["scenario"] in forward_scenarios})
    for metric_key, title, y_label, panel_top in panel_specs:
        panel_left = 90.0
        panel_width = 1000.0
        panel_height = 180.0
        metric_rows = [row for row in chord_rows if row["scenario"] in forward_scenarios]
        values = [float(row[metric_key]) for row in metric_rows]
        ymin2, ymax2 = _extent([np.asarray(values, dtype=float)], pad_fraction=0.1, include_zero=(metric_key != "correlation"))
        if metric_key == "correlation":
            ymin2 = min(ymin2, 0.95)
            ymax2 = max(ymax2, 1.0)
        _draw_axes(body, panel_left, panel_top, panel_width, panel_height, 0.0, float(len(chord_order) - 1), ymin2, ymax2, "Chord index", y_label, show_x_ticks=False)
        body.append(f'<text x="{panel_left:.1f}" y="{panel_top - 14:.1f}" font-size="13" font-weight="700" fill="#111827">{_xml(title)}</text>')
        for chord_idx, chord_key in enumerate(chord_order):
            sx = panel_left + chord_idx / max(len(chord_order) - 1, 1) * panel_width
            body.append(f'<line x1="{sx:.1f}" y1="{panel_top:.1f}" x2="{sx:.1f}" y2="{panel_top + panel_height:.1f}" stroke="{PLOT_COLORS["grid"]}" stroke-width="1"/>')
            body.append(f'<text x="{sx:.1f}" y="{panel_top + panel_height + 16:.1f}" text-anchor="middle" font-size="11" fill="#374151">{_xml(chord_key.replace("chord_", ""))}</text>')

        for scenario_name in forward_scenarios:
            series_rows = [row for row in metric_rows if row["scenario"] == scenario_name]
            series_rows.sort(key=lambda x: x["chord_key"])
            x_vals = np.asarray(list(range(len(series_rows))), dtype=float)
            y_vals = np.asarray([float(row[metric_key]) for row in series_rows], dtype=float)
            dash = ' stroke-dasharray="6,4"' if scenario_name == "init" else ""
            points = _polyline_points(x_vals, y_vals, 0.0, float(len(chord_order) - 1), ymin2, ymax2, panel_left, panel_top, panel_width, panel_height)
            body.append(f'<polyline fill="none" stroke="{PLOT_COLORS.get(scenario_name, "#2563eb")}" stroke-width="2.5"{dash} points="{points}"/>')
            for xv, yv in zip(x_vals, y_vals):
                sx = panel_left + xv / max(len(chord_order) - 1, 1) * panel_width
                sy = panel_top + panel_height - (yv - ymin2) / max(ymax2 - ymin2, 1.0e-30) * panel_height
                body.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="3.5" fill="{PLOT_COLORS.get(scenario_name, "#2563eb")}"/>')

    legend_x = 620.0
    legend_y = 112.0
    for idx, scenario_name in enumerate(forward_scenarios):
        yy = legend_y + idx * 22.0
        dash = ' stroke-dasharray="6,4"' if scenario_name == "init" else ""
        body.append(f'<line x1="{legend_x:.1f}" y1="{yy:.1f}" x2="{legend_x + 24:.1f}" y2="{yy:.1f}" stroke="{PLOT_COLORS.get(scenario_name, "#2563eb")}" stroke-width="3"{dash}/>')
        body.append(f'<text x="{legend_x + 32:.1f}" y="{yy + 4:.1f}" font-size="12" fill="#374151">{_xml(scenario_name)}</text>')

    _write_text_file(path, _svg_document(width, height, "Forward Quality Overview", body))


def _write_forward_window_svg(path: Path, benchmark_title: str, forward_window_rows: List[Dict[str, Any]]) -> None:
    names = []
    for row in forward_window_rows:
        name = str(row["window_name"])
        if name not in names:
            names.append(name)
    rows = [next(item for item in forward_window_rows if item["window_name"] == name and item["scenario"] == scenario)
            for name in names
            for scenario in ["init", "truth"]
            if any(item["window_name"] == name and item["scenario"] == scenario for item in forward_window_rows)]

    width = 1320
    height = 860
    left = 280.0
    plot_width = 980.0
    body: List[str] = []
    body.append(f'<text x="24" y="56" font-size="14" fill="#4b5563">{_xml(benchmark_title)}</text>')

    top = 100.0
    plot_height = 340.0
    all_ratio_values = [float(row["mean_area_ratio"]) for row in rows] + [float(row["mean_peak_ratio"]) for row in rows]
    xmin = min(min(all_ratio_values), 0.0) - 0.2
    xmax = max(max(all_ratio_values), 1.0) + 0.2
    _draw_axes(body, left, top, plot_width, plot_height, xmin, xmax, -0.5, float(len(names) - 0.5), "Ratio to measurement", "Window", show_x_ticks=True)
    body.append(f'<text x="{left:.1f}" y="{top - 14:.1f}" font-size="13" font-weight="700" fill="#111827">Forward window area ratios (init vs truth)</text>')
    x_one = left + (1.0 - xmin) / max(xmax - xmin, 1.0e-30) * plot_width
    body.append(f'<line x1="{x_one:.1f}" y1="{top:.1f}" x2="{x_one:.1f}" y2="{top + plot_height:.1f}" stroke="#dc2626" stroke-width="2" stroke-dasharray="4,4"/>')
    for idx, name in enumerate(names):
        cy = top + (idx + 0.5) / len(names) * plot_height
        body.append(f'<text x="{left - 10:.1f}" y="{cy + 4:.1f}" text-anchor="end" font-size="12" fill="#374151">{_xml(name)}</text>')
        for scenario_name, color, yoff in [("init", PLOT_COLORS["init"], -8.0), ("truth", PLOT_COLORS["truth"], 8.0)]:
            row = next((item for item in rows if item["window_name"] == name and item["scenario"] == scenario_name), None)
            if row is None:
                continue
            val = float(row["mean_area_ratio"])
            x0 = left + (min(1.0, val) - xmin) / max(xmax - xmin, 1.0e-30) * plot_width
            x1 = left + (max(1.0, val) - xmin) / max(xmax - xmin, 1.0e-30) * plot_width
            if val < 1.0:
                x0 = left + (val - xmin) / max(xmax - xmin, 1.0e-30) * plot_width
                x1 = left + (1.0 - xmin) / max(xmax - xmin, 1.0e-30) * plot_width
            body.append(f'<rect x="{min(x0, x1):.1f}" y="{cy + yoff - 5:.1f}" width="{abs(x1 - x0):.1f}" height="10" fill="{color}" opacity="0.85"/>')
            body.append(f'<text x="{left + plot_width + 8:.1f}" y="{cy + yoff + 4:.1f}" font-size="11" fill="{color}">{_xml(scenario_name[0].upper())} {_fmt_tick(val)}</text>')

    top2 = 520.0
    plot_height2 = 220.0
    shift_values = [float(row["mean_abs_peak_shift_nm"]) for row in rows]
    _, ymax_shift = _extent([np.asarray(shift_values, dtype=float)], pad_fraction=0.15, include_zero=True)
    _draw_axes(body, left, top2, plot_width, plot_height2, -0.5, float(len(names) - 0.5), 0.0, ymax_shift, "Window index", "Abs peak shift (nm)", show_x_ticks=False)
    body.append(f'<text x="{left:.1f}" y="{top2 - 14:.1f}" font-size="13" font-weight="700" fill="#111827">Forward window peak shift (init vs truth)</text>')
    bar_w = plot_width / max(len(names) * 2.6, 1.0)
    for idx, name in enumerate(names):
        base_x = left + (idx + 0.5) / len(names) * plot_width
        body.append(f'<text x="{base_x:.1f}" y="{top2 + plot_height2 + 16:.1f}" text-anchor="middle" font-size="11" fill="#374151">{idx + 1}</text>')
        for scenario_name, color, shift_index in [("init", PLOT_COLORS["init"], -1), ("truth", PLOT_COLORS["truth"], 1)]:
            row = next((item for item in rows if item["window_name"] == name and item["scenario"] == scenario_name), None)
            if row is None:
                continue
            value = float(row["mean_abs_peak_shift_nm"])
            sx = base_x + shift_index * bar_w * 0.7 - bar_w / 2.0
            sy = top2 + plot_height2 - value / max(ymax_shift, 1.0e-30) * plot_height2
            body.append(f'<rect x="{sx:.1f}" y="{sy:.1f}" width="{bar_w:.1f}" height="{top2 + plot_height2 - sy:.1f}" fill="{color}"/>')

    _write_text_file(path, _svg_document(width, height, "Forward Window Fidelity", body))


def _write_forward_dashboard_html(
    path: Path,
    benchmark_meta: Dict[str, Any],
    scenario_rows: List[Dict[str, Any]],
    plasma_findings: List[str],
    measurement_findings: List[str],
) -> None:
    title = str(benchmark_meta.get("title", benchmark_meta.get("benchmark_id", path.parent.name)))
    benchmark_id = str(benchmark_meta.get("benchmark_id", ""))
    source = str(benchmark_meta.get("source", {}).get("citation", ""))
    html_text = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{_xml(title)} - Forward Dashboard</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #111827; background: #f8fafc; }}
    h1, h2 {{ margin-bottom: 8px; }}
    .card {{ background: white; border: 1px solid #e5e7eb; border-radius: 12px; padding: 18px; margin-bottom: 18px; }}
    .meta {{ color: #4b5563; font-size: 14px; }}
    .plots img {{ width: 100%; max-width: 1200px; border: 1px solid #e5e7eb; border-radius: 10px; background: white; }}
    ul {{ margin-top: 6px; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 720px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px 10px; text-align: left; font-size: 14px; }}
    th {{ background: #f3f4f6; }}
    a {{ color: #2563eb; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{_xml(title)} Forward Dashboard</h1>
    <div class="meta">Benchmark ID: {_xml(benchmark_id)}</div>
    <div class="meta">Source: {_xml(source)}</div>
    <div class="meta"><a href="analysis_report.md">Inverse-oriented report</a> | <a href="analysis_summary.yaml">YAML summary</a> | <a href="chord_metrics.csv">Chord metrics</a> | <a href="window_metrics.csv">Window metrics</a></div>
  </div>
  <div class="card">
    <h2>Forward Scenario Snapshot</h2>
    <table>
      <tr><th>Scenario</th><th>Cost</th><th>Mean Corr.</th><th>Mean NRMSE/std</th><th>Mean Gain</th></tr>
      {''.join(f"<tr><td>{_xml(row['scenario'])}</td><td>{float(row['cost']):.4f}</td><td>{float(row['mean_correlation']):.4f}</td><td>{float(row['mean_nrmse_std']):.4f}</td><td>{float(row['mean_gain']):.4f}</td></tr>" for row in scenario_rows if row['scenario'] in ('init','truth'))}
    </table>
  </div>
  <div class="card">
    <h2>Plasma OES View</h2>
    <ul>{''.join(f"<li>{_xml(item)}</li>" for item in plasma_findings)}</ul>
  </div>
  <div class="card">
    <h2>Measurement Engineering View</h2>
    <ul>{''.join(f"<li>{_xml(item)}</li>" for item in measurement_findings)}</ul>
  </div>
  <div class="card plots">
    <h2>Forward Quality</h2>
    <img src="plots/forward_quality.svg" alt="Forward quality plot">
  </div>
  <div class="card plots">
    <h2>Forward Window Fidelity</h2>
    <img src="plots/forward_window_fidelity.svg" alt="Forward window fidelity plot">
  </div>
  <div class="card plots">
    <h2>Forward Spectral Overlays</h2>
    <img src="plots/forward_spectra_overview.svg" alt="Forward spectral overlays">
  </div>
</body>
</html>
"""
    _write_text_file(path, html_text)


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


def _markdown_table(rows: List[Dict[str, Any]], columns: List[Tuple[str, str]]) -> List[str]:
    header = "| " + " | ".join(label for _, label in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, divider]
    for row in rows:
        cells = []
        for key, _label in columns:
            value = row.get(key, "")
            if isinstance(value, float):
                if math.isnan(value) or math.isinf(value):
                    cells.append(str(value))
                elif abs(value) >= 1.0e4 or (0 < abs(value) < 1.0e-3):
                    cells.append(f"{value:.3e}")
                else:
                    cells.append(f"{value:.4f}")
            elif isinstance(value, list):
                cells.append(", ".join(str(v) for v in value))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def _write_markdown_report(
    path: Path,
    benchmark_meta: Dict[str, Any],
    scenario_rows: List[Dict[str, Any]],
    instrument_rows: List[Dict[str, Any]],
    parameter_rows: List[Dict[str, Any]],
    window_rows: List[Dict[str, Any]],
    plasma_findings: List[str],
    measurement_findings: List[str],
) -> None:
    title = str(benchmark_meta.get("title", benchmark_meta.get("benchmark_id", path.parent.name)))

    lines: List[str] = []
    lines.append(f"# Benchmark Analysis: {title}")
    lines.append("")
    lines.append(f"- Benchmark ID: {benchmark_meta.get('benchmark_id', '')}")
    lines.append(f"- Source: {benchmark_meta.get('source', {}).get('citation', '')}")
    lines.append("")
    lines.append("## Scenario Summary")
    lines.append("")
    lines.extend(
        _markdown_table(
            scenario_rows,
            [
                ("scenario", "Scenario"),
                ("cost", "Cost"),
                ("mean_correlation", "Mean Corr."),
                ("mean_nrmse_std", "Mean NRMSE/std"),
                ("mean_nrmse_range", "Mean NRMSE/range"),
                ("mean_gain", "Mean Gain"),
            ],
        )
    )
    lines.append("")
    lines.append("## Instrument View")
    lines.append("")
    lines.extend(
        _markdown_table(
            instrument_rows,
            [
                ("instrument_id", "Instrument"),
                ("wavelength_min_nm", "Min nm"),
                ("wavelength_max_nm", "Max nm"),
                ("bin_nm", "Bin nm"),
                ("selected_window_count", "Windows"),
                ("gain_mean", "Gain Mean"),
                ("gain_min", "Gain Min"),
                ("gain_max", "Gain Max"),
            ],
        )
    )
    lines.append("")
    lines.append("## Parameter Recovery")
    lines.append("")
    lines.extend(
        _markdown_table(
            parameter_rows,
            [
                ("group", "Group"),
                ("trend", "Radial Trend"),
                ("init_mean_abs_rel_error", "Init Mean Abs Rel Err"),
                ("opt_mean_abs_rel_error", "Opt Mean Abs Rel Err"),
                ("improvement_fraction", "Improvement"),
                ("mean_relative_uncertainty", "Mean Rel. Uncertainty"),
            ],
        )
    )
    lines.append("")
    lines.append("## Window Fidelity")
    lines.append("")
    lines.extend(
        _markdown_table(
            window_rows[:8],
            [
                ("window_name", "Window"),
                ("kind", "Kind"),
                ("mean_area_ratio", "Mean Area Ratio"),
                ("mean_peak_ratio", "Mean Peak Ratio"),
                ("mean_abs_peak_shift_nm", "Mean Abs Peak Shift nm"),
            ],
        )
    )
    lines.append("")
    lines.append("## Plasma OES Interpretation")
    lines.append("")
    for item in plasma_findings:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Measurement Engineering Interpretation")
    lines.append("")
    for item in measurement_findings:
        lines.append(f"- {item}")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def analyze_one(bench_dir: Path, result_dir_name: str, out_name: str) -> Path:
    bench_dir = bench_dir.resolve()
    result_dir = (bench_dir / "runs" / result_dir_name).resolve()
    out_dir = (result_dir / out_name).resolve()
    comparisons_dir = out_dir / "comparisons"
    plots_dir = out_dir / "plots"

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
    )

    chord_rows: List[Dict[str, Any]] = []
    for scenario_name, data in scenarios.items():
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
    _write_flat_csv(
        out_dir / "window_metrics.csv",
        scenarios["opt"]["window_metrics"],
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
    _write_dashboard_html(out_dir / plot_outputs["dashboard"], benchmark_meta, scenario_rows, plasma_findings, measurement_findings)
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
    )

    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser(description="Analyze benchmark spectra, fit quality, and interpretation.")
    ap.add_argument("benchmarks", nargs="+", help="Benchmark directory names under examples/benchmarks or absolute paths")
    ap.add_argument("--result-dir-name", default="inverse_test", help="Directory under runs/ that holds fit_summary.yaml")
    ap.add_argument("--out-name", default="analysis", help="Subdirectory to write analysis outputs into")
    args = ap.parse_args()

    out_dirs: List[Path] = []
    for bench in args.benchmarks:
        out_dir = analyze_one(_resolve_benchmark_dir(bench), args.result_dir_name, args.out_name)
        out_dirs.append(out_dir)
        print(f"Analysis written to: {out_dir}")

    if len(out_dirs) > 1:
        print("Generated analysis directories:")
        for item in out_dirs:
            print(item)


if __name__ == "__main__":
    main()
