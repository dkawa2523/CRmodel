from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from ..instrument.capability import instrument_capabilities
from ..instrument.spec import InstrumentSpec
from ..io.pathmap import get_path
from ..io.validators import validate_window_registry
from ..io.yaml_loader import load_yaml, resolve_path
from .gain_model import apply_gain_offset_tilt, fit_gain_offsets_for_instrument
from .priors import prior_residuals
from .window_metrics import (
    compute_window_feature_maps,
    low_signal_window_names,
    window_features,
    window_fit_residuals,
    window_ratio_pair_residuals,
    window_ratio_residuals,
)


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
    _ = case_cfg
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


def gain_tilt_prior_residual(tilt: float, weight: float = 0.0, sigma: float = 1.0) -> np.ndarray:
    if weight <= 0.0:
        return np.zeros(0, dtype=float)
    sigma_eff = max(float(sigma), 1.0e-12)
    return np.asarray([np.sqrt(weight) * float(tilt) / sigma_eff], dtype=float)


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
    window_min_relative_signal = float(obj_cfg.get("window_min_relative_signal", 0.02))

    auto_gain = bool(obj_cfg.get("auto_gain_fit", True))
    auto_offset = bool(obj_cfg.get("auto_offset_fit", True))
    auto_gain_tilt = bool(obj_cfg.get("auto_gain_tilt_fit", False))
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

    gain_tilt_prior_weight = float(obj_cfg.get("gain_tilt_prior_weight", 0.0))
    gain_tilt_prior_sigma = float(obj_cfg.get("gain_tilt_prior_sigma", 1.0))

    residuals = []
    aux: Dict[str, Any] = {
        "gain_offset": {},
        "selected_windows": {},
        "ratio_pairs_used": {},
        "skipped_windows_low_signal": {},
    }

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
            auto_gain_tilt=auto_gain_tilt,
            gain_scope=gain_scope,
        )

        if gain_prior_weight > 0.0 and gain_scope == "instrument" and gain_offset_map:
            shared = next(iter(gain_offset_map.values()))
            residuals.extend(
                gain_prior_residual(
                    float(shared.get("gain", 1.0)),
                    inst_cfg,
                    gain_prior_weight,
                    gain_prior_target,
                    gain_prior_sigma,
                )
            )
        if gain_tilt_prior_weight > 0.0 and gain_scope == "instrument" and gain_offset_map:
            shared = next(iter(gain_offset_map.values()))
            residuals.extend(
                gain_tilt_prior_residual(
                    float(shared.get("tilt", 0.0)),
                    gain_tilt_prior_weight,
                    gain_tilt_prior_sigma,
                )
            )

        for chord_idx, meas in enumerate(meas_list):
            chord_key = f"chord_{chord_idx}"
            pred = pred_by_chord[chord_key]
            pred_y = np.interp(meas.wavelength_nm, pred["wavelength_nm"], pred["intensity"], left=0.0, right=0.0)

            gain_offset = gain_offset_map.get(chord_key, {"gain": 1.0, "offset": 0.0, "tilt": 0.0})
            gain = float(gain_offset.get("gain", 1.0))
            offset = float(gain_offset.get("offset", 0.0))
            tilt = float(gain_offset.get("tilt", 0.0))
            aux["gain_offset"][(inst_id, chord_key)] = {"gain": gain, "offset": offset, "tilt": tilt}

            pred_fit = apply_gain_offset_tilt(
                np.asarray(meas.wavelength_nm, dtype=float),
                np.asarray(pred_y, dtype=float),
                gain=gain,
                tilt=tilt,
                offset=offset,
            )

            scale = np.maximum(np.std(meas.intensity), 1.0e-12)
            residuals.extend(np.sqrt(w_spec) * (pred_fit - meas.intensity) / scale)

            if gain_prior_weight > 0.0 and gain_scope != "instrument":
                residuals.extend(gain_prior_residual(gain, inst_cfg, gain_prior_weight, gain_prior_target, gain_prior_sigma))
            if gain_tilt_prior_weight > 0.0 and gain_scope != "instrument":
                residuals.extend(gain_tilt_prior_residual(tilt, gain_tilt_prior_weight, gain_tilt_prior_sigma))

            pred_feats, meas_feats = compute_window_feature_maps(
                meas.wavelength_nm,
                pred_fit,
                meas.intensity,
                inst_windows,
                default_baseline_mode=baseline_mode,
            )

            low_signal_windows = set(low_signal_window_names(inst_windows, meas_feats, window_min_relative_signal))
            aux["skipped_windows_low_signal"][(inst_id, chord_key)] = sorted(low_signal_windows)

            for w in inst_windows:
                name = str(w.get("name", ""))
                if name in low_signal_windows:
                    continue
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
