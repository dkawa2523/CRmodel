from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import numpy as np

from .baseline import evaluate_baseline, normalize_baseline_config
from .lsf import normalize_lsf_config, apply_lsf
from .throughput import evaluate_throughput, normalize_throughput_config


@dataclass
class InstrumentSpec:
    cfg: Dict[str, Any]

    def __post_init__(self) -> None:
        self.cfg = normalize_instrument_config(self.cfg)

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
        dx = float(np.mean(np.diff(coarse))) / oversample
        return np.arange(coarse.min() - padding_nm, coarse.max() + padding_nm + 0.5 * dx, dx)

    def observe(self, fine_wavelength_nm: np.ndarray, fine_intensity: np.ndarray) -> Dict[str, np.ndarray]:
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

        convolved = apply_lsf(self.cfg, fine_wavelength_nm, shifted)
        throughput = evaluate_throughput(self.cfg, fine_wavelength_nm)
        baseline = evaluate_baseline(self.cfg, fine_wavelength_nm)
        gain = float(self.cfg.get("nuisance", {}).get("gain", 1.0))
        fine_obs = gain * convolved * throughput + baseline

        coarse = self.wavelength_grid_nm
        dx = float(np.mean(np.diff(coarse)))
        out = np.zeros_like(coarse)
        for i, wc in enumerate(coarse):
            mask = (fine_wavelength_nm >= wc - dx / 2.0) & (fine_wavelength_nm < wc + dx / 2.0)
            if not np.any(mask):
                out[i] = np.interp(wc, fine_wavelength_nm, fine_obs)
            else:
                out[i] = np.trapezoid(fine_obs[mask], fine_wavelength_nm[mask]) / dx
        return {"wavelength_nm": coarse, "intensity": out}


def normalize_instrument_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(cfg)
    out.setdefault("nuisance", {})
    out["throughput"] = normalize_throughput_config(out)
    out["lsf"] = normalize_lsf_config(out)
    out["baseline"] = normalize_baseline_config(out)
    return out
