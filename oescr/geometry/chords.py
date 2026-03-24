
from __future__ import annotations

import numpy as np


def shell_path_length(radius_inner_m: float, radius_outer_m: float, impact_m: float) -> float:
    b = abs(float(impact_m))
    r0 = float(radius_inner_m)
    r1 = float(radius_outer_m)
    if b >= r1:
        return 0.0
    outer = np.sqrt(max(r1 * r1 - b * b, 0.0))
    inner = np.sqrt(max(r0 * r0 - b * b, 0.0)) if b < r0 else 0.0
    return 2.0 * max(outer - inner, 0.0)
