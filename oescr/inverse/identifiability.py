
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

import numpy as np

from .objectives import residual_vector


def finite_difference_jacobian(model, case_cfg: Dict[str, Any], inv_cfg: Dict[str, Any], measurements, windows, params) -> np.ndarray:
    x0 = params.initial_vector(case_cfg)
    r0, _ = residual_vector(model, deepcopy(case_cfg), inv_cfg, measurements, windows)
    J = np.zeros((len(r0), len(x0)), dtype=float)
    for j, x in enumerate(x0):
        dx = 1.0e-4 * max(abs(x), 1.0)
        xp = x0.copy()
        xp[j] += dx
        cfgp = deepcopy(case_cfg)
        params.apply_to_case(cfgp, xp)
        rp, _ = residual_vector(model, cfgp, inv_cfg, measurements, windows)
        J[:, j] = (rp - r0) / dx
    return J


def identifiability_summary(model, case_cfg, inv_cfg, measurements, windows, params) -> Dict[str, Any]:
    J = finite_difference_jacobian(model, case_cfg, inv_cfg, measurements, windows, params)
    s = np.linalg.svd(J, compute_uv=False)
    cond = float(s[0] / max(s[-1], 1.0e-30)) if len(s) else float("inf")
    return {
        "singular_values": s.tolist(),
        "condition_number": cond,
        "rank_estimate": int(np.sum(s > max(s[0] * 1.0e-8, 1.0e-12))) if len(s) else 0,
        "n_observations": int(J.shape[0]),
        "n_parameters": int(J.shape[1]),
    }
