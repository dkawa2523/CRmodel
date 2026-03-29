from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np


def normalized_wavelength_axis(wavelength_nm: np.ndarray) -> np.ndarray:
    wl = np.asarray(wavelength_nm, dtype=float)
    if len(wl) == 0:
        return np.zeros(0, dtype=float)
    center = float(np.mean(wl))
    half_span = max(float(np.ptp(wl)) * 0.5, 1.0e-12)
    return (wl - center) / half_span


def fit_gain_offset(y_meas: np.ndarray, y_pred: np.ndarray, allow_offset: bool = True) -> Tuple[float, float]:
    if allow_offset:
        A = np.vstack([y_pred, np.ones_like(y_pred)]).T
        coef, *_ = np.linalg.lstsq(A, y_meas, rcond=None)
        gain = max(float(coef[0]), 1.0e-12)
        offset = float(coef[1])
        return gain, offset
    gain = max(float(np.dot(y_meas, y_pred) / max(np.dot(y_pred, y_pred), 1.0e-30)), 1.0e-12)
    return gain, 0.0


def fit_gain_offset_tilt(
    wavelength_nm: np.ndarray,
    y_meas: np.ndarray,
    y_pred: np.ndarray,
    allow_offset: bool = True,
    allow_tilt: bool = False,
) -> Tuple[float, float, float]:
    if not allow_tilt:
        gain, offset = fit_gain_offset(y_meas, y_pred, allow_offset=allow_offset)
        return gain, 0.0, offset

    wl_axis = normalized_wavelength_axis(wavelength_nm)
    c_gain = np.asarray(y_pred, dtype=float)
    c_tilt = c_gain * wl_axis
    if allow_offset:
        A = np.vstack([c_gain, c_tilt, np.ones_like(c_gain)]).T
        coef, *_ = np.linalg.lstsq(A, y_meas, rcond=None)
        gain = max(float(coef[0]), 1.0e-12)
        tilt = float(coef[1]) / gain
        offset = float(coef[2])
        return gain, tilt, offset

    A = np.vstack([c_gain, c_tilt]).T
    coef, *_ = np.linalg.lstsq(A, y_meas, rcond=None)
    gain = max(float(coef[0]), 1.0e-12)
    tilt = float(coef[1]) / gain
    return gain, tilt, 0.0


def apply_gain_offset_tilt(
    wavelength_nm: np.ndarray,
    y_pred: np.ndarray,
    gain: float,
    tilt: float = 0.0,
    offset: float = 0.0,
) -> np.ndarray:
    wl_axis = normalized_wavelength_axis(wavelength_nm)
    return float(gain) * (1.0 + float(tilt) * wl_axis) * np.asarray(y_pred, dtype=float) + float(offset)


def fit_gain_offsets_for_instrument(
    inst_id: str,
    meas_list: List[Any],
    pred_by_chord: Dict[str, Dict[str, np.ndarray]],
    inst_cfg: Dict[str, Any],
    auto_gain: bool = True,
    auto_offset: bool = True,
    auto_gain_tilt: bool = False,
    gain_scope: str = "chord",
) -> Dict[str, Dict[str, float]]:
    _ = inst_id
    if not auto_gain:
        gain = float(inst_cfg.get("nuisance", {}).get("gain", 1.0))
        offset = float(inst_cfg.get("baseline", {}).get("offset", 0.0))
        tilt = 0.0
        return {
            f"chord_{chord_idx}": {"gain": gain, "tilt": tilt, "offset": offset}
            for chord_idx in range(len(meas_list))
        }

    if gain_scope == "instrument":
        meas_concat: List[np.ndarray] = []
        pred_concat: List[np.ndarray] = []
        wl_concat: List[np.ndarray] = []
        for chord_idx, meas in enumerate(meas_list):
            chord_key = f"chord_{chord_idx}"
            pred = pred_by_chord[chord_key]
            pred_y = np.interp(meas.wavelength_nm, pred["wavelength_nm"], pred["intensity"], left=0.0, right=0.0)
            meas_concat.append(np.asarray(meas.intensity, dtype=float))
            pred_concat.append(np.asarray(pred_y, dtype=float))
            wl_concat.append(np.asarray(meas.wavelength_nm, dtype=float))
        if not meas_concat:
            return {}
        gain, tilt, offset = fit_gain_offset_tilt(
            np.concatenate(wl_concat),
            np.concatenate(meas_concat),
            np.concatenate(pred_concat),
            allow_offset=auto_offset,
            allow_tilt=auto_gain_tilt,
        )
        return {
            f"chord_{chord_idx}": {"gain": gain, "tilt": tilt, "offset": offset}
            for chord_idx in range(len(meas_list))
        }

    out: Dict[str, Dict[str, float]] = {}
    for chord_idx, meas in enumerate(meas_list):
        chord_key = f"chord_{chord_idx}"
        pred = pred_by_chord[chord_key]
        pred_y = np.interp(meas.wavelength_nm, pred["wavelength_nm"], pred["intensity"], left=0.0, right=0.0)
        gain, tilt, offset = fit_gain_offset_tilt(
            np.asarray(meas.wavelength_nm, dtype=float),
            np.asarray(meas.intensity, dtype=float),
            pred_y,
            allow_offset=auto_offset,
            allow_tilt=auto_gain_tilt,
        )
        out[chord_key] = {"gain": gain, "tilt": tilt, "offset": offset}
    return out
