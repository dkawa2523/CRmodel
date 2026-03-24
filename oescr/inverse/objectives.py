from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from ..io.pathmap import get_path
from ..io.validators import validate_window_registry
from ..io.yaml_loader import load_yaml, resolve_path
from ..instrument.capability import instrument_capabilities
from ..instrument.spec import InstrumentSpec
from .priors import prior_residuals


@dataclass
class Measurement:
    wavelength_nm: np.ndarray
    intensity: np.ndarray


def load_measurement_csv(path: str | Path) -> Measurement:
    wl = []
    it = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(row for row in f if not row.lstrip().startswith("#"))
        for row in reader:
            wl.append(float(row["wavelength_nm"]))
            it.append(float(row["intensity"]))
    return Measurement(np.asarray(wl, dtype=float), np.asarray(it, dtype=float))


def _measurement_paths(inv_cfg: Dict[str, Any], item: Dict[str, Any]) -> List[Path]:
    if "files_glob" in item:
        pattern = str(item["files_glob"])
        base = Path(inv_cfg.get("__base_dir__", "."))
        return sorted(base.glob(pattern))
    if "files" in item:
        return [resolve_path(inv_cfg, p) for p in item["files"]]
    if "file" in item:
        return [resolve_path(inv_cfg, item["file"])]
    raise ValueError(f"Measurement entry must define file/files/files_glob: {item}")


def load_measurements(case_cfg: Dict[str, Any], inv_cfg: Dict[str, Any]) -> Dict[str, List[Measurement]]:
    out: Dict[str, List[Measurement]] = {}
    for item in inv_cfg.get("measurements", []):
        inst_id = item["instrument_id"]
        paths = _measurement_paths(inv_cfg, item)
        out[inst_id] = [load_measurement_csv(p) for p in paths]
    return out


def load_windows(case_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    diag = case_cfg.get("diagnostics", {})
    wf = diag.get("window_registry")
    if not wf:
        return []
    cfg = load_yaml(resolve_path(case_cfg, wf))
    validate_window_registry(cfg)
    windows = list(cfg.get("windows", []))

    include_names = set(diag.get("window_names", []))
    include_families = set(diag.get("window_families", []))
    exclude_names = set(diag.get("exclude_window_names", []))

    filtered = []
    for w in windows:
        name = str(w.get("name", ""))
        fam = str(w.get("family", ""))
        if include_names and name not in include_names:
            continue
        if include_families and fam not in include_families:
            continue
        if name in exclude_names:
            continue
        filtered.append(w)
    return filtered


def select_windows_for_instrument(
    case_cfg: Dict[str, Any],
    inst_cfg: Dict[str, Any],
    windows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    cap = instrument_capabilities(inst_cfg)
    inst = InstrumentSpec(inst_cfg)
    grid = inst.wavelength_grid_nm
    diag = case_cfg.get("diagnostics", {})
    include_disabled = bool(diag.get("include_disabled_windows", False))
    selected = []
    for w in windows:
        if not include_disabled:
            if "enabled" in w and not bool(w.get("enabled")):
                continue
            if "default_enabled" in w and not bool(w.get("default_enabled")):
                continue
        center = float(w["center_nm"])
        half = float(w.get("half_width_nm", 1.0))
        if center - half < grid.min() or center + half > grid.max():
            continue
        max_bin = w.get("max_bin_nm")
        if max_bin is not None and float(inst_cfg.get("bin_nm", 1.0)) > float(max_bin):
            continue
        if w.get("requires_high_res", False) and not cap["high_res"]:
            continue
        selected.append(w)
    return selected


def fit_gain_offset(y_meas: np.ndarray, y_pred: np.ndarray, allow_offset: bool = True) -> Tuple[float, float]:
    if allow_offset:
        A = np.vstack([y_pred, np.ones_like(y_pred)]).T
        coef, *_ = np.linalg.lstsq(A, y_meas, rcond=None)
        gain = max(float(coef[0]), 1.0e-12)
        offset = float(coef[1])
        return gain, offset
    gain = max(float(np.dot(y_meas, y_pred) / max(np.dot(y_pred, y_pred), 1.0e-30)), 1.0e-12)
    return gain, 0.0


def window_mask(wavelength_nm: np.ndarray, center_nm: float, half_width_nm: float) -> np.ndarray:
    return (wavelength_nm >= center_nm - half_width_nm) & (wavelength_nm <= center_nm + half_width_nm)


def _edge_count(npts: int, frac: float = 0.2) -> int:
    return max(2, min(max(npts // 2, 2), int(np.ceil(npts * frac))))


def fit_local_baseline(
    wavelength_nm: np.ndarray,
    intensity: np.ndarray,
    mode: str = "local_linear",
    edge_fraction: float = 0.2,
) -> np.ndarray:
    if len(wavelength_nm) == 0:
        return np.zeros(0, dtype=float)
    if mode in {"none", "off", "disabled"} or len(wavelength_nm) < 3:
        return np.zeros_like(intensity, dtype=float)

    n_edge = _edge_count(len(wavelength_nm), edge_fraction)
    left = np.arange(0, n_edge)
    right = np.arange(len(wavelength_nm) - n_edge, len(wavelength_nm))
    idx = np.unique(np.concatenate([left, right]))

    if mode in {"flat", "constant"}:
        baseline_level = float(np.mean(intensity[idx]))
        return np.full_like(intensity, baseline_level, dtype=float)

    if len(idx) < 2 or np.allclose(wavelength_nm[idx], wavelength_nm[idx][0]):
        baseline_level = float(np.mean(intensity[idx]))
        return np.full_like(intensity, baseline_level, dtype=float)

    coef = np.polyfit(wavelength_nm[idx], intensity[idx], deg=1)
    return np.polyval(coef, wavelength_nm)


def _window_segment(
    wavelength_nm: np.ndarray,
    intensity: np.ndarray,
    center_nm: float,
    half_width_nm: float,
    baseline_mode: str,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    mask = window_mask(wavelength_nm, center_nm, half_width_nm)
    wl = wavelength_nm[mask]
    it = intensity[mask]
    if len(wl) == 0:
        return wl, it, it
    base = fit_local_baseline(wl, it, mode=baseline_mode)
    return wl, it, it - base


def window_features(
    wavelength_nm: np.ndarray,
    intensity: np.ndarray,
    center_nm: float,
    half_width_nm: float,
    baseline_mode: str = "local_linear",
) -> Dict[str, float]:
    wl, raw, corr = _window_segment(wavelength_nm, intensity, center_nm, half_width_nm, baseline_mode)
    if len(wl) == 0:
        return {"area": 0.0, "peak": 0.0, "peak_wavelength_nm": center_nm}
    area = float(np.trapezoid(corr, wl))
    peak_idx = int(np.argmax(corr))
    return {"area": area, "peak": float(corr[peak_idx]), "peak_wavelength_nm": float(wl[peak_idx])}


def _normalize_window(y: np.ndarray, wl: np.ndarray, mode: str) -> np.ndarray:
    if len(y) == 0:
        return y
    if mode in {"none", "off", "disabled"}:
        return y
    if mode == "area":
        denom = max(abs(float(np.trapezoid(y, wl))), 1.0e-30)
        return y / denom
    if mode == "peak":
        denom = max(abs(float(np.max(y))), 1.0e-30)
        return y / denom
    if mode == "l2":
        denom = max(float(np.linalg.norm(y)), 1.0e-30)
        return y / denom
    raise ValueError(f"Unsupported window normalization mode: {mode}")


def window_fit_residuals(
    wavelength_nm: np.ndarray,
    y_pred: np.ndarray,
    y_meas: np.ndarray,
    center_nm: float,
    half_width_nm: float,
    baseline_mode: str = "local_linear",
    normalization: str = "area",
    local_gain: bool = False,
) -> np.ndarray:
    wl, _, pred_corr = _window_segment(wavelength_nm, y_pred, center_nm, half_width_nm, baseline_mode)
    _, _, meas_corr = _window_segment(wavelength_nm, y_meas, center_nm, half_width_nm, baseline_mode)
    if len(wl) == 0:
        return np.zeros(0, dtype=float)

    pred_work = pred_corr.copy()
    meas_work = meas_corr.copy()
    if local_gain:
        denom = max(float(np.dot(pred_work, pred_work)), 1.0e-30)
        gain = float(np.dot(meas_work, pred_work) / denom)
        pred_work *= gain

    pred_norm = _normalize_window(pred_work, wl, normalization)
    meas_norm = _normalize_window(meas_work, wl, normalization)
    scale = max(float(np.std(meas_norm)), 1.0e-12)
    return (pred_norm - meas_norm) / scale


def compute_window_feature_maps(
    wavelength_nm: np.ndarray,
    y_pred: np.ndarray,
    y_meas: np.ndarray,
    windows: List[Dict[str, Any]],
    default_baseline_mode: str = "local_linear",
) -> Tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, float]]]:
    pred_map: Dict[str, Dict[str, float]] = {}
    meas_map: Dict[str, Dict[str, float]] = {}
    for w in windows:
        name = str(w.get("name", ""))
        baseline_mode = str(w.get("baseline_mode", default_baseline_mode))
        center = float(w["center_nm"])
        half_width = float(w.get("half_width_nm", 1.0))
        pred_map[name] = window_features(
            wavelength_nm,
            y_pred,
            center,
            half_width,
            baseline_mode=baseline_mode,
        )
        meas_map[name] = window_features(
            wavelength_nm,
            y_meas,
            center,
            half_width,
            baseline_mode=baseline_mode,
        )
    return pred_map, meas_map


def _window_metric_value(features: Dict[str, float], metric: str) -> float:
    if metric == "area":
        return abs(float(features["area"]))
    if metric == "peak":
        return abs(float(features["peak"]))
    raise ValueError(f"Unsupported window ratio metric: {metric}")


def window_ratio_residuals(
    windows: List[Dict[str, Any]],
    pred_features: Dict[str, Dict[str, float]],
    meas_features: Dict[str, Dict[str, float]],
    metric: str = "peak",
    reference_window: str | None = None,
    min_relative_signal: float = 0.02,
) -> np.ndarray:
    eligible: List[Tuple[str, float]] = []
    for w in windows:
        name = str(w.get("name", ""))
        if metric == "area" and not bool(w.get("use_area", True)):
            continue
        if metric == "peak" and not bool(w.get("use_peak", True)):
            continue
        meas_value = _window_metric_value(meas_features[name], metric)
        if meas_value <= 0.0:
            continue
        eligible.append((name, meas_value))

    if len(eligible) < 2:
        return np.zeros(0, dtype=float)

    strongest = max(value for _name, value in eligible)
    cutoff = strongest * max(float(min_relative_signal), 0.0)
    eligible_names = [name for name, value in eligible if value >= cutoff]
    if len(eligible_names) < 2:
        return np.zeros(0, dtype=float)

    ref_name = reference_window if reference_window in eligible_names else eligible_names[0]
    if reference_window is None:
        ref_name = max(eligible, key=lambda item: item[1])[0]

    ref_meas = _window_metric_value(meas_features[ref_name], metric)
    ref_pred = _window_metric_value(pred_features[ref_name], metric)
    if ref_meas <= 0.0 or ref_pred <= 0.0:
        return np.zeros(0, dtype=float)

    residuals = []
    for name in eligible_names:
        if name == ref_name:
            continue
        meas_value = _window_metric_value(meas_features[name], metric)
        pred_value = _window_metric_value(pred_features[name], metric)
        if meas_value <= 0.0 or pred_value <= 0.0:
            continue
        residuals.append(np.log(pred_value / ref_pred) - np.log(meas_value / ref_meas))
    return np.asarray(residuals, dtype=float)


def window_ratio_pair_residuals(
    pred_features: Dict[str, Dict[str, float]],
    meas_features: Dict[str, Dict[str, float]],
    ratio_pairs: List[Dict[str, Any]],
    default_metric: str = "peak",
    default_min_relative_signal: float = 0.02,
) -> Dict[int, np.ndarray]:
    if not ratio_pairs:
        return {}

    max_signal_by_metric: Dict[str, float] = {}
    for metric in {"area", "peak"}:
        max_signal_by_metric[metric] = max(
            (_window_metric_value(features, metric) for features in meas_features.values()),
            default=0.0,
        )

    out: Dict[int, np.ndarray] = {}
    for pair_idx, pair in enumerate(ratio_pairs):
        numerator = str(pair["numerator"])
        denominator = str(pair["denominator"])
        metric = str(pair.get("metric", default_metric))
        min_relative_signal = float(pair.get("min_relative_signal", default_min_relative_signal))
        if numerator not in pred_features or denominator not in pred_features:
            continue

        num_meas = _window_metric_value(meas_features[numerator], metric)
        den_meas = _window_metric_value(meas_features[denominator], metric)
        num_pred = _window_metric_value(pred_features[numerator], metric)
        den_pred = _window_metric_value(pred_features[denominator], metric)
        signal_cutoff = max_signal_by_metric.get(metric, 0.0) * max(min_relative_signal, 0.0)

        if min(num_meas, den_meas) <= max(signal_cutoff, 0.0):
            continue
        if min(num_pred, den_pred) <= 0.0:
            continue

        out[pair_idx] = np.asarray([np.log(num_pred / den_pred) - np.log(num_meas / den_meas)], dtype=float)
    return out


def gain_prior_residual(
    gain: float,
    inst_cfg: Dict[str, Any],
    weight: float = 0.0,
    target: float | None = None,
    sigma_log10: float = 1.0,
) -> np.ndarray:
    if weight <= 0.0:
        return np.zeros(0, dtype=float)
    target_value = float(target) if target is not None else float(inst_cfg.get("nuisance", {}).get("gain", 1.0))
    target_value = max(target_value, 1.0e-12)
    sigma = max(float(sigma_log10), 1.0e-12)
    return np.asarray([np.sqrt(weight) * (np.log10(max(gain, 1.0e-12)) - np.log10(target_value)) / sigma], dtype=float)


def fit_gain_offsets_for_instrument(
    inst_id: str,
    meas_list: List[Measurement],
    pred_by_chord: Dict[str, Dict[str, np.ndarray]],
    inst_cfg: Dict[str, Any],
    auto_gain: bool = True,
    auto_offset: bool = True,
    gain_scope: str = "chord",
) -> Dict[str, Dict[str, float]]:
    if not auto_gain:
        gain = float(inst_cfg.get("nuisance", {}).get("gain", 1.0))
        offset = float(inst_cfg.get("baseline", {}).get("offset", 0.0))
        return {
            f"chord_{chord_idx}": {"gain": gain, "offset": offset}
            for chord_idx in range(len(meas_list))
        }

    if gain_scope == "instrument":
        meas_concat = []
        pred_concat = []
        for chord_idx, meas in enumerate(meas_list):
            chord_key = f"chord_{chord_idx}"
            pred = pred_by_chord[chord_key]
            pred_y = np.interp(meas.wavelength_nm, pred["wavelength_nm"], pred["intensity"], left=0.0, right=0.0)
            meas_concat.append(np.asarray(meas.intensity, dtype=float))
            pred_concat.append(np.asarray(pred_y, dtype=float))
        gain, offset = fit_gain_offset(
            np.concatenate(meas_concat),
            np.concatenate(pred_concat),
            allow_offset=auto_offset,
        )
        return {
            f"chord_{chord_idx}": {"gain": gain, "offset": offset}
            for chord_idx in range(len(meas_list))
        }

    out: Dict[str, Dict[str, float]] = {}
    for chord_idx, meas in enumerate(meas_list):
        chord_key = f"chord_{chord_idx}"
        pred = pred_by_chord[chord_key]
        pred_y = np.interp(meas.wavelength_nm, pred["wavelength_nm"], pred["intensity"], left=0.0, right=0.0)
        gain, offset = fit_gain_offset(meas.intensity, pred_y, allow_offset=auto_offset)
        out[chord_key] = {"gain": gain, "offset": offset}
    return out


def residual_vector(
    model,
    case_cfg: Dict[str, Any],
    inv_cfg: Dict[str, Any],
    measurements: Dict[str, List[Measurement]],
    windows: List[Dict[str, Any]],
) -> Tuple[np.ndarray, Dict[str, Any]]:
    fwd = model.predict(case_cfg)
    obj_cfg = inv_cfg.get("fit", {}).get("objective", {})
    w_spec = float(obj_cfg.get("spectrum_weight", 1.0))
    w_window = float(obj_cfg.get("window_fit_weight", 0.0))
    w_area = float(obj_cfg.get("area_weight", 0.3))
    w_peak = float(obj_cfg.get("peak_weight", 0.05))
    auto_gain = bool(obj_cfg.get("auto_gain_fit", True))
    auto_offset = bool(obj_cfg.get("auto_offset_fit", True))
    gain_scope = str(obj_cfg.get("auto_gain_scope", "chord"))
    baseline_mode = str(obj_cfg.get("window_baseline_mode", "local_linear"))
    window_norm = str(obj_cfg.get("window_fit_normalization", "area"))
    window_local_gain = bool(obj_cfg.get("window_fit_local_gain", False))
    w_ratio = float(obj_cfg.get("window_ratio_weight", 0.0))
    ratio_metric = str(obj_cfg.get("window_ratio_metric", "peak"))
    ratio_reference = obj_cfg.get("window_ratio_reference")
    ratio_min_signal = float(obj_cfg.get("window_ratio_min_relative_signal", 0.02))
    ratio_pairs = list(obj_cfg.get("window_ratio_pairs", []))
    gain_prior_weight = float(obj_cfg.get("gain_prior_weight", 0.0))
    gain_prior_target = obj_cfg.get("gain_prior_target")
    gain_prior_sigma = float(obj_cfg.get("gain_prior_sigma_log10", 1.0))

    residuals = []
    aux: Dict[str, Any] = {"gain_offset": {}, "selected_windows": {}, "ratio_pairs_used": {}}

    inst_cfg_map = {c["id"]: c for c in model._load_instrument_cfgs(case_cfg)}

    for inst_id, meas_list in measurements.items():
        pred_by_chord = fwd.spectra[inst_id]
        inst_cfg = inst_cfg_map[inst_id]
        inst_windows = select_windows_for_instrument(case_cfg, inst_cfg, windows)
        aux["selected_windows"][inst_id] = [w.get("name", "") for w in inst_windows]
        gain_offset_map = fit_gain_offsets_for_instrument(
            inst_id,
            meas_list,
            pred_by_chord,
            inst_cfg,
            auto_gain=auto_gain,
            auto_offset=auto_offset,
            gain_scope=gain_scope,
        )
        if gain_prior_weight > 0.0 and gain_scope == "instrument" and gain_offset_map:
            shared = next(iter(gain_offset_map.values()))
            residuals.extend(
                gain_prior_residual(
                    float(shared["gain"]),
                    inst_cfg,
                    gain_prior_weight,
                    gain_prior_target,
                    gain_prior_sigma,
                )
            )

        for chord_idx, meas in enumerate(meas_list):
            chord_key = f"chord_{chord_idx}"
            pred = pred_by_chord[chord_key]
            pred_y = np.interp(meas.wavelength_nm, pred["wavelength_nm"], pred["intensity"], left=0.0, right=0.0)
            gain = float(gain_offset_map[chord_key]["gain"])
            offset = float(gain_offset_map[chord_key]["offset"])
            aux["gain_offset"][(inst_id, chord_key)] = {"gain": gain, "offset": offset}
            pred_fit = gain * pred_y + offset

            scale = np.maximum(np.std(meas.intensity), 1.0e-12)
            residuals.extend(np.sqrt(w_spec) * (pred_fit - meas.intensity) / scale)
            if gain_prior_weight > 0.0 and gain_scope != "instrument":
                residuals.extend(gain_prior_residual(gain, inst_cfg, gain_prior_weight, gain_prior_target, gain_prior_sigma))

            pred_feats, meas_feats = compute_window_feature_maps(
                meas.wavelength_nm,
                pred_fit,
                meas.intensity,
                inst_windows,
                default_baseline_mode=baseline_mode,
            )

            for w in inst_windows:
                name = str(w.get("name", ""))
                center = float(w["center_nm"])
                half_width = float(w.get("half_width_nm", 1.0))
                local_baseline = str(w.get("baseline_mode", baseline_mode))
                local_norm = str(w.get("window_fit_normalization", window_norm))
                local_gain = bool(w.get("window_fit_local_gain", window_local_gain))
                local_w_window = float(w.get("window_fit_weight", w_window))
                local_w_area = float(w.get("area_weight", w_area))
                local_w_peak = float(w.get("peak_weight", w_peak))

                if bool(w.get("use_window_fit", local_w_window > 0.0)) and local_w_window > 0.0:
                    win_res = window_fit_residuals(
                        meas.wavelength_nm,
                        pred_fit,
                        meas.intensity,
                        center,
                        half_width,
                        baseline_mode=local_baseline,
                        normalization=local_norm,
                        local_gain=local_gain,
                    )
                    if len(win_res) > 0:
                        residuals.extend(np.sqrt(local_w_window) * win_res)

                feats_p = pred_feats[name]
                feats_m = meas_feats[name]
                if bool(w.get("use_area", True)) and local_w_area > 0.0:
                    denom = max(abs(feats_m["area"]), 1.0e-30)
                    residuals.append(np.sqrt(local_w_area) * (feats_p["area"] - feats_m["area"]) / denom)
                if bool(w.get("use_peak", True)) and local_w_peak > 0.0:
                    denom = max(abs(feats_m["peak"]), 1.0e-30)
                    residuals.append(np.sqrt(local_w_peak) * (feats_p["peak"] - feats_m["peak"]) / denom)

            if w_ratio > 0.0 or ratio_pairs:
                if ratio_pairs:
                    pair_residual_map = window_ratio_pair_residuals(
                        pred_feats,
                        meas_feats,
                        ratio_pairs,
                        default_metric=ratio_metric,
                        default_min_relative_signal=ratio_min_signal,
                    )
                    aux["ratio_pairs_used"][(inst_id, chord_key)] = [
                        str(ratio_pairs[pair_idx].get("name", f"pair_{pair_idx}"))
                        for pair_idx in sorted(pair_residual_map)
                    ]
                    for pair_idx, pair_res in pair_residual_map.items():
                        pair_weight = float(ratio_pairs[pair_idx].get("weight", w_ratio))
                        if pair_weight > 0.0 and len(pair_res) > 0:
                            residuals.extend(np.sqrt(pair_weight) * pair_res)
                else:
                    ratio_res = window_ratio_residuals(
                        inst_windows,
                        pred_feats,
                        meas_feats,
                        metric=ratio_metric,
                        reference_window=str(ratio_reference) if ratio_reference is not None else None,
                        min_relative_signal=ratio_min_signal,
                    )
                    if len(ratio_res) > 0:
                        residuals.extend(np.sqrt(w_ratio) * ratio_res)

    residuals.extend(prior_residuals(case_cfg, inv_cfg).tolist())

    for reg in inv_cfg.get("fit", {}).get("regularization", {}).get("smooth_arrays", []):
        path = reg.get("path")
        if path is None:
            continue
        arr = np.asarray(get_path(case_cfg, str(path)), dtype=float)
        weight = float(reg.get("weight", 0.1))
        order = int(reg.get("order", 2))
        if len(arr) >= 3 and order == 2:
            curv = arr[:-2] - 2.0 * arr[1:-1] + arr[2:]
            scale = max(np.std(arr), 1.0)
            residuals.extend(np.sqrt(weight) * curv / scale)
        elif len(arr) >= 2 and order == 1:
            grad = np.diff(arr)
            scale = max(np.std(arr), 1.0)
            residuals.extend(np.sqrt(weight) * grad / scale)

    return np.asarray(residuals, dtype=float), aux
