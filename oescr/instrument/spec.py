from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

import numpy as np

from .baseline import BASELINE_PLUGINS, evaluate_baseline, normalize_baseline_config
from .calibration import CalibrationTransform
from .lsf import LSF_PLUGINS, apply_lsf, normalize_lsf_config
from .throughput import THROUGHPUT_PLUGINS, evaluate_throughput, normalize_throughput_config


@dataclass
class InstrumentSpec:
    cfg: Dict[str, Any]
    validated: bool = False
    calibration: CalibrationTransform = field(init=False)

    def __post_init__(self) -> None:
        self.cfg = normalize_instrument_config(self.cfg)
        if not self.validated:
            THROUGHPUT_PLUGINS.validate(str(self.cfg["throughput"]["kind"]), self.cfg["throughput"])
            LSF_PLUGINS.validate(str(self.cfg["lsf"]["kind"]), self.cfg["lsf"])
            BASELINE_PLUGINS.validate(str(self.cfg["baseline"]["kind"]), self.cfg["baseline"])
        self.calibration = CalibrationTransform.from_instrument_config(self.cfg)
        self.validated = True

    @property
    def instrument_id(self) -> str:
        return str(self.cfg["id"])

    @property
    def wavelength_grid_nm(self) -> np.ndarray:
        if "wavelength_grid_nm" in self.cfg:
            return np.asarray(self.cfg["wavelength_grid_nm"], dtype=float)
        wmin = float(self.cfg["wavelength_min_nm"])
        wmax = float(self.cfg["wavelength_max_nm"])
        bin_nm = float(self.cfg["bin_nm"])
        return np.arange(wmin, wmax + 0.5 * bin_nm, bin_nm)

    def fine_grid_nm(self, oversample: int = 8, padding_nm: float = 5.0) -> np.ndarray:
        coarse = self.wavelength_grid_nm
        if np.any(np.diff(coarse) <= 0.0):
            raise ValueError("Instrument wavelength grid must be strictly increasing.")
        dx = float(np.min(np.diff(coarse))) / oversample
        return np.arange(coarse.min() - padding_nm, coarse.max() + padding_nm + 0.5 * dx, dx)

    def observe(self, fine_wavelength_nm: np.ndarray, fine_intensity: np.ndarray) -> Dict[str, Any]:
        shift = float(self.cfg.get("nuisance", {}).get("wavelength_shift_nm", 0.0))
        if abs(shift) > 0.0:
            shifted = np.interp(
                fine_wavelength_nm,
                fine_wavelength_nm - shift,
                fine_intensity,
                left=0.0,
                right=0.0,
            )
        else:
            shifted = fine_intensity.copy()

        convolved = apply_lsf(self.cfg, fine_wavelength_nm, shifted, validate=False)
        throughput = evaluate_throughput(self.cfg, fine_wavelength_nm, validate=False)
        calibrated = self.calibration.apply(fine_wavelength_nm, convolved * throughput)
        baseline = evaluate_baseline(self.cfg, fine_wavelength_nm, validate=False)
        gain = float(self.cfg.get("nuisance", {}).get("gain", 1.0))
        fine_obs = gain * calibrated + baseline

        coarse = self.wavelength_grid_nm
        if np.any(np.diff(coarse) <= 0.0):
            raise ValueError("Instrument wavelength grid must be strictly increasing.")
        midpoints = 0.5 * (coarse[:-1] + coarse[1:])
        edges = np.concatenate(
            [
                [coarse[0] - 0.5 * (coarse[1] - coarse[0])],
                midpoints,
                [coarse[-1] + 0.5 * (coarse[-1] - coarse[-2])],
            ]
        )
        out = np.zeros_like(coarse)
        for i, _ in enumerate(coarse):
            left_edge = float(edges[i])
            right_edge = float(edges[i + 1])
            width = float(edges[i + 1] - edges[i])
            mask = (fine_wavelength_nm > left_edge) & (fine_wavelength_nm < right_edge)
            integration_wavelength = np.concatenate(
                ([left_edge], fine_wavelength_nm[mask], [right_edge])
            )
            integration_signal = np.interp(integration_wavelength, fine_wavelength_nm, fine_obs)
            out[i] = np.trapezoid(integration_signal, integration_wavelength) / width
        return {
            "wavelength_nm": coarse,
            "intensity": out,
            "output_basis": self.calibration.output_basis,
            "output_unit": self.calibration.output_unit,
            "calibration_reference": self.calibration.reference,
        }


def normalize_instrument_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(cfg)
    out.setdefault("nuisance", {})
    out["throughput"] = normalize_throughput_config(out)
    out["lsf"] = normalize_lsf_config(out)
    out["baseline"] = normalize_baseline_config(out)
    return out
