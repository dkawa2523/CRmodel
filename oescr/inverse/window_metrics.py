from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np


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
    wl, _raw, corr = _window_segment(wavelength_nm, intensity, center_nm, half_width_nm, baseline_mode)
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
    wl, _pred_raw, pred_corr = _window_segment(wavelength_nm, y_pred, center_nm, half_width_nm, baseline_mode)
    _wl2, _meas_raw, meas_corr = _window_segment(wavelength_nm, y_meas, center_nm, half_width_nm, baseline_mode)
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


def window_metric_value(features: Dict[str, float], metric: str) -> float:
    if metric == "area":
        return abs(float(features["area"]))
    if metric == "peak":
        return abs(float(features["peak"]))
    raise ValueError(f"Unsupported window ratio metric: {metric}")


def _window_signal_value(features: Dict[str, float]) -> float:
    return max(abs(float(features["area"])), abs(float(features["peak"])))


def low_signal_window_names(
    windows: List[Dict[str, Any]],
    meas_features: Dict[str, Dict[str, float]],
    min_relative_signal: float,
) -> List[str]:
    if min_relative_signal <= 0.0:
        return []

    eligible: List[Tuple[str, float]] = []
    for w in windows:
        name = str(w.get("name", ""))
        feats = meas_features.get(name)
        if feats is None:
            continue
        eligible.append((name, _window_signal_value(feats)))

    if len(eligible) < 2:
        return []

    strongest = max(value for _name, value in eligible)
    if strongest <= 0.0:
        return []

    cutoff = strongest * max(float(min_relative_signal), 0.0)
    return [name for name, value in eligible if value <= cutoff]


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
        meas_value = window_metric_value(meas_features[name], metric)
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

    ref_meas = window_metric_value(meas_features[ref_name], metric)
    ref_pred = window_metric_value(pred_features[ref_name], metric)
    if ref_meas <= 0.0 or ref_pred <= 0.0:
        return np.zeros(0, dtype=float)

    residuals = []
    for name in eligible_names:
        if name == ref_name:
            continue
        meas_value = window_metric_value(meas_features[name], metric)
        pred_value = window_metric_value(pred_features[name], metric)
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
            (window_metric_value(features, metric) for features in meas_features.values()),
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

        num_meas = window_metric_value(meas_features[numerator], metric)
        den_meas = window_metric_value(meas_features[denominator], metric)
        num_pred = window_metric_value(pred_features[numerator], metric)
        den_pred = window_metric_value(pred_features[denominator], metric)
        signal_cutoff = max_signal_by_metric.get(metric, 0.0) * max(min_relative_signal, 0.0)

        if min(num_meas, den_meas) <= max(signal_cutoff, 0.0):
            continue
        if min(num_pred, den_pred) <= 0.0:
            continue

        out[pair_idx] = np.asarray([np.log(num_pred / den_pred) - np.log(num_meas / den_meas)], dtype=float)
    return out
