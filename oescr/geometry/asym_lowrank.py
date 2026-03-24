
from __future__ import annotations

import numpy as np


def apply_lowrank_asymmetry(
    zone_emissivity: np.ndarray,
    chord_angles_rad: np.ndarray | None,
    mode1_amplitude: np.ndarray | None = None,
) -> np.ndarray:
    if chord_angles_rad is None or mode1_amplitude is None:
        return np.tile(zone_emissivity[None, :], (1, 1))
    # Experimental hook: multiplicative m=1 correction.
    out = []
    for angle in chord_angles_rad:
        factor = 1.0 + mode1_amplitude * np.cos(angle)
        out.append(zone_emissivity * factor)
    return np.asarray(out)
