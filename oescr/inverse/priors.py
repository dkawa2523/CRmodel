
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ..io.pathmap import get_path


def _as_float_array(value: Any) -> np.ndarray:
    arr = np.asarray(value, dtype=float)
    if arr.ndim == 0:
        return arr.reshape(1)
    return arr.reshape(-1)


def _broadcast_prior_array(value: Any, target_shape: tuple[int, ...], field_name: str) -> np.ndarray:
    arr = np.asarray(value, dtype=float)
    if arr.ndim == 0:
        return np.full(target_shape, float(arr), dtype=float)
    if arr.shape != target_shape:
        raise ValueError(f"Prior field '{field_name}' shape {arr.shape} does not match target shape {target_shape}")
    return arr.astype(float, copy=False)


def prior_residuals(case_cfg: Dict[str, Any], inverse_cfg: Dict[str, Any]) -> np.ndarray:
    out: List[float] = []
    pri_cfg = inverse_cfg.get("priors", [])
    for pri in pri_cfg:
        path = pri["path"]
        val_arr = _as_float_array(get_path(case_cfg, path))
        kind = pri.get("type", "gaussian")
        if kind == "gaussian":
            mu = _broadcast_prior_array(pri["mean"], val_arr.shape, "mean")
            sigma = np.maximum(_broadcast_prior_array(pri["sigma"], val_arr.shape, "sigma"), 1.0e-30)
            out.extend(((val_arr - mu) / sigma).tolist())
        elif kind == "log_gaussian":
            mu = _broadcast_prior_array(pri["mean_log10"], val_arr.shape, "mean_log10")
            sigma = np.maximum(
                _broadcast_prior_array(pri["sigma_log10"], val_arr.shape, "sigma_log10"),
                1.0e-30,
            )
            out.extend(((np.log10(np.maximum(val_arr, 1.0e-30)) - mu) / sigma).tolist())
        elif kind == "loguniform":
            # hard bounds are handled elsewhere
            continue
        else:
            raise ValueError(f"Unsupported prior type: {kind}")
    return np.asarray(out, dtype=float)
