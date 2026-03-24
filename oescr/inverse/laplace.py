
from __future__ import annotations

from typing import Any, Dict

import numpy as np


def covariance_from_jacobian(J: np.ndarray) -> np.ndarray:
    H = J.T @ J
    H += np.eye(H.shape[0]) * 1.0e-12
    try:
        return np.linalg.inv(H)
    except np.linalg.LinAlgError:
        return np.linalg.pinv(H)


def summarize_covariance(cov: np.ndarray, param_names: list[str]) -> Dict[str, Any]:
    std = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    corr = cov / np.outer(np.maximum(std, 1.0e-30), np.maximum(std, 1.0e-30))
    return {
        "std_opt_space": {name: float(s) for name, s in zip(param_names, std)},
        "correlation_matrix": corr.tolist(),
    }
