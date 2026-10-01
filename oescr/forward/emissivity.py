
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
from scipy import constants as const

from ..data.atomic_db import StateRegistry
from ..physics.trapping import effective_A


def gaussian_line_profile(wavelength_nm: np.ndarray, center_nm: float, fwhm_nm: float) -> np.ndarray:
    sigma = max(float(fwhm_nm) / 2.35482004503, 1.0e-6)
    y = np.exp(-0.5 * ((wavelength_nm - center_nm) / sigma) ** 2)
    area = np.trapezoid(y, wavelength_nm)
    return y / max(area, 1.0e-30)


def atomic_line_spectrum_zone(
    cfg: Dict[str, Any],
    registry: StateRegistry,
    populations_m3: Dict[str, float],
    wavelength_nm: np.ndarray,
    zone_context: Dict[str, float] | None = None,
    *,
    validate_plugins: bool = True,
) -> Dict[str, Any]:
    spec = np.zeros_like(wavelength_nm, dtype=float)
    line_info: List[Dict[str, float]] = []
    for tr in cfg.get("transitions", []):
        upper = tr["upper"]
        if upper not in populations_m3:
            continue
        n_upper = populations_m3[upper]
        Aeff = effective_A(tr, zone_context=zone_context, validate=validate_plugins)
        lam_nm = float(tr["wavelength_nm"])
        lam_m = lam_nm * 1.0e-9
        intrinsic = tr.get("profile", {})
        prof = gaussian_line_profile(
            wavelength_nm,
            lam_nm,
            float(intrinsic.get("fwhm_nm", 0.02)),
        )
        energy_factor = const.h * const.c / max(lam_m, 1.0e-30)
        amp = float(tr.get("amplitude_scale", 1.0)) * n_upper * Aeff * energy_factor / (4.0 * np.pi)
        spec += amp * prof
        line_info.append(
            {
                "wavelength_nm": lam_nm,
                "upper_population_m3": n_upper,
                "Aeff_s-1": Aeff,
                "integrated_emissivity_W_m3_sr": amp,
            }
        )
    return {"spectrum": spec, "lines": line_info}
