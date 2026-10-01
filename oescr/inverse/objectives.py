from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as np

from ..instrument.capability import instrument_capabilities
from ..instrument.spec import InstrumentSpec
from ..io.pathmap import get_path
from ..io.validators import validate_window_registry
from ..io.yaml_loader import load_yaml, resolve_path
from .gain_model import apply_gain_offset_tilt, fit_gain_offsets_for_instrument
from .measurements import Measurement, spectrum_residuals, whiten_feature_residuals
from .priors import prior_residuals
from .window_metrics import (
    compute_window_feature_maps,
    low_signal_window_names,
    window_fit_residuals,
    window_ratio_pair_residuals,
    window_ratio_residuals,
)


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
        if max_bin is not None:
            if "bin_nm" in inst_cfg:
                local_bin_nm = float(inst_cfg["bin_nm"])
            else:
                local_grid = grid[(grid >= center - half) & (grid <= center + half)]
                if len(local_grid) < 2:
                    continue
                local_bin_nm = float(np.max(np.diff(local_grid)))
            if local_bin_nm > float(max_bin):
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


@dataclass(frozen=True)
class ObjectiveOptions:
    spectrum_weight: float
    window_fit_weight: float
    area_weight: float
    peak_weight: float
    window_min_relative_signal: float
    auto_gain: bool
    auto_offset: bool
    auto_gain_tilt: bool
    gain_scope: str
    baseline_mode: str
    window_normalization: str
    window_local_gain: bool
    ratio_weight: float
    ratio_metric: str
    ratio_reference: Any
    ratio_min_signal: float
    ratio_pairs: List[Dict[str, Any]]
    gain_prior_weight: float
    gain_prior_target: Any
    gain_prior_sigma: float
    gain_tilt_prior_weight: float
    gain_tilt_prior_sigma: float

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "ObjectiveOptions":
        return cls(
            spectrum_weight=float(cfg.get("spectrum_weight", 1.0)),
            window_fit_weight=float(cfg.get("window_fit_weight", 0.0)),
            area_weight=float(cfg.get("area_weight", 0.3)),
            peak_weight=float(cfg.get("peak_weight", 0.05)),
            window_min_relative_signal=float(cfg.get("window_min_relative_signal", 0.02)),
            auto_gain=bool(cfg.get("auto_gain_fit", True)),
            auto_offset=bool(cfg.get("auto_offset_fit", True)),
            auto_gain_tilt=bool(cfg.get("auto_gain_tilt_fit", False)),
            gain_scope=str(cfg.get("auto_gain_scope", "chord")),
            baseline_mode=str(cfg.get("window_baseline_mode", "local_linear")),
            window_normalization=str(cfg.get("window_fit_normalization", "area")),
            window_local_gain=bool(cfg.get("window_fit_local_gain", False)),
            ratio_weight=float(cfg.get("window_ratio_weight", 0.0)),
            ratio_metric=str(cfg.get("window_ratio_metric", "peak")),
            ratio_reference=cfg.get("window_ratio_reference"),
            ratio_min_signal=float(cfg.get("window_ratio_min_relative_signal", 0.02)),
            ratio_pairs=list(cfg.get("window_ratio_pairs", [])),
            gain_prior_weight=float(cfg.get("gain_prior_weight", 0.0)),
            gain_prior_target=cfg.get("gain_prior_target"),
            gain_prior_sigma=float(cfg.get("gain_prior_sigma_log10", 1.0)),
            gain_tilt_prior_weight=float(cfg.get("gain_tilt_prior_weight", 0.0)),
            gain_tilt_prior_sigma=float(cfg.get("gain_tilt_prior_sigma", 1.0)),
        )


def _gain_prior_terms(
    gain_offset: Dict[str, float],
    inst_cfg: Dict[str, Any],
    options: ObjectiveOptions,
) -> List[float]:
    terms: List[float] = []
    terms.extend(
        gain_prior_residual(
            float(gain_offset.get("gain", 1.0)),
            inst_cfg,
            options.gain_prior_weight,
            options.gain_prior_target,
            options.gain_prior_sigma,
        ).tolist()
    )
    terms.extend(
        gain_tilt_prior_residual(
            float(gain_offset.get("tilt", 0.0)),
            options.gain_tilt_prior_weight,
            options.gain_tilt_prior_sigma,
        ).tolist()
    )
    return terms


def _window_residual_terms(
    measurement: Measurement,
    predicted: np.ndarray,
    windows: List[Dict[str, Any]],
    options: ObjectiveOptions,
    covariance_names: set[str],
) -> tuple[
    List[float],
    Dict[str, float],
    Dict[str, Dict[str, float]],
    Dict[str, Dict[str, float]],
    List[str],
]:
    predicted_features, measured_features = compute_window_feature_maps(
        measurement.wavelength_nm,
        predicted,
        measurement.intensity,
        windows,
        default_baseline_mode=options.baseline_mode,
    )
    low_signal = set(
        low_signal_window_names(
            windows,
            measured_features,
            options.window_min_relative_signal,
        )
    )
    terms: List[float] = []
    feature_residuals: Dict[str, float] = {}
    for window in windows:
        name = str(window.get("name", ""))
        if name in low_signal:
            continue
        center = float(window["center_nm"])
        half_width = float(window.get("half_width_nm", 1.0))
        baseline = str(window.get("baseline_mode", options.baseline_mode))
        normalization = str(window.get("window_fit_normalization", options.window_normalization))
        local_gain = bool(window.get("window_fit_local_gain", options.window_local_gain))
        window_weight = float(window.get("window_fit_weight", options.window_fit_weight))
        area_weight = float(window.get("area_weight", options.area_weight))
        peak_weight = float(window.get("peak_weight", options.peak_weight))

        if bool(window.get("use_window_fit", window_weight > 0.0)) and window_weight > 0.0:
            values = window_fit_residuals(
                measurement.wavelength_nm,
                predicted,
                measurement.intensity,
                center,
                half_width,
                baseline_mode=baseline,
                normalization=normalization,
                local_gain=local_gain,
            )
            terms.extend((np.sqrt(window_weight) * values).tolist())

        predicted_feature = predicted_features[name]
        measured_feature = measured_features[name]
        area_key = f"window:{name}:area"
        if bool(window.get("use_area", True)) and (area_weight > 0.0 or area_key in covariance_names):
            denominator = max(abs(measured_feature["area"]), 1.0e-30)
            area_residual = (predicted_feature["area"] - measured_feature["area"]) / denominator
            feature_residuals[area_key] = area_residual
            if area_weight > 0.0 and area_key not in covariance_names:
                terms.append(np.sqrt(area_weight) * area_residual)
        peak_key = f"window:{name}:peak"
        if bool(window.get("use_peak", True)) and (peak_weight > 0.0 or peak_key in covariance_names):
            denominator = max(abs(measured_feature["peak"]), 1.0e-30)
            peak_residual = (predicted_feature["peak"] - measured_feature["peak"]) / denominator
            feature_residuals[peak_key] = peak_residual
            if peak_weight > 0.0 and peak_key not in covariance_names:
                terms.append(np.sqrt(peak_weight) * peak_residual)
    return terms, feature_residuals, predicted_features, measured_features, sorted(low_signal)


def _ratio_residual_terms(
    windows: List[Dict[str, Any]],
    predicted_features: Dict[str, Dict[str, float]],
    measured_features: Dict[str, Dict[str, float]],
    options: ObjectiveOptions,
    covariance_names: set[str],
) -> tuple[List[float], List[str], Dict[str, float]]:
    if options.ratio_weight <= 0.0 and not options.ratio_pairs:
        return [], [], {}
    if not options.ratio_pairs:
        values = window_ratio_residuals(
            windows,
            predicted_features,
            measured_features,
            metric=options.ratio_metric,
            reference_window=(
                str(options.ratio_reference)
                if options.ratio_reference is not None
                else None
            ),
            min_relative_signal=options.ratio_min_signal,
        )
        return (np.sqrt(options.ratio_weight) * values).tolist(), [], {}

    residual_map = window_ratio_pair_residuals(
        predicted_features,
        measured_features,
        options.ratio_pairs,
        default_metric=options.ratio_metric,
        default_min_relative_signal=options.ratio_min_signal,
    )
    terms: List[float] = []
    names: List[str] = []
    feature_residuals: Dict[str, float] = {}
    for pair_index in sorted(residual_map):
        pair = options.ratio_pairs[pair_index]
        pair_weight = float(pair.get("weight", options.ratio_weight))
        values = residual_map[pair_index]
        pair_name = str(pair.get("name", f"pair_{pair_index}"))
        feature_key = f"ratio:{pair_name}"
        feature_residuals[feature_key] = float(values[0])
        if pair_weight > 0.0 and feature_key not in covariance_names:
            terms.extend((np.sqrt(pair_weight) * values).tolist())
        names.append(pair_name)
    return terms, names, feature_residuals


def _regularization_residuals(case_cfg: Dict[str, Any], inv_cfg: Dict[str, Any]) -> List[float]:
    terms: List[float] = []
    for regularizer in inv_cfg.get("fit", {}).get("regularization", {}).get("smooth_arrays", []):
        path = regularizer.get("path")
        if path is None:
            continue
        values = np.asarray(get_path(case_cfg, str(path)), dtype=float)
        weight = float(regularizer.get("weight", 0.1))
        order = int(regularizer.get("order", 2))
        scale = max(float(np.std(values)), 1.0)
        if len(values) >= 3 and order == 2:
            terms.extend((np.sqrt(weight) * np.diff(values, n=2) / scale).tolist())
        elif len(values) >= 2 and order == 1:
            terms.extend((np.sqrt(weight) * np.diff(values) / scale).tolist())
    return terms


def residual_vector(
    model,
    case_cfg: Dict[str, Any],
    inv_cfg: Dict[str, Any],
    measurements: Dict[str, List[Measurement]],
    windows: List[Dict[str, Any]],
    *,
    include_constraints: bool = True,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Build measurement residuals, optionally followed by prior constraints.

    Optimization and conditional-curvature calculations use the complete
    objective. Local observability must set ``include_constraints=False`` so
    priors and smoothness cannot create artificial measurement rank.
    """

    fwd = model.predict(case_cfg)
    options = ObjectiveOptions.from_config(inv_cfg.get("fit", {}).get("objective", {}))
    residuals: List[float] = []
    aux: Dict[str, Any] = {
        "gain_offset": {},
        "selected_windows": {},
        "ratio_pairs_used": {},
        "skipped_windows_low_signal": {},
        "feature_covariance_used": {},
    }

    inst_cfg_map = {c["id"]: c for c in model.instrument_configs_for(case_cfg)}

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
            auto_gain=options.auto_gain,
            auto_offset=options.auto_offset,
            auto_gain_tilt=options.auto_gain_tilt,
            gain_scope=options.gain_scope,
        )

        if include_constraints and options.gain_scope == "instrument" and gain_offset_map:
            residuals.extend(_gain_prior_terms(next(iter(gain_offset_map.values())), inst_cfg, options))

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

            if options.spectrum_weight > 0.0:
                residuals.extend((np.sqrt(options.spectrum_weight) * spectrum_residuals(meas, pred_fit)).tolist())
            if include_constraints and options.gain_scope != "instrument":
                residuals.extend(_gain_prior_terms(gain_offset, inst_cfg, options))

            covariance_names = (
                set(meas.feature_covariance.names)
                if meas.feature_covariance is not None
                else set()
            )
            window_terms, feature_residuals, pred_feats, meas_feats, low_signal = _window_residual_terms(
                meas,
                pred_fit,
                inst_windows,
                options,
                covariance_names,
            )
            residuals.extend(window_terms)
            aux["skipped_windows_low_signal"][(inst_id, chord_key)] = low_signal
            ratio_terms, pair_names, ratio_feature_residuals = _ratio_residual_terms(
                inst_windows,
                pred_feats,
                meas_feats,
                options,
                covariance_names,
            )
            residuals.extend(ratio_terms)
            aux["ratio_pairs_used"][(inst_id, chord_key)] = pair_names
            feature_residuals.update(ratio_feature_residuals)
            residuals.extend(whiten_feature_residuals(meas, feature_residuals).tolist())
            aux["feature_covariance_used"][(inst_id, chord_key)] = sorted(covariance_names)

    if include_constraints:
        residuals.extend(prior_residuals(case_cfg, inv_cfg).tolist())
        residuals.extend(_regularization_residuals(case_cfg, inv_cfg))
    return np.asarray(residuals, dtype=float), aux
