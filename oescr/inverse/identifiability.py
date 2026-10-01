
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Sequence

import numpy as np

from .objectives import residual_vector


def finite_difference_jacobian(
    model,
    case_cfg: Dict[str, Any],
    inv_cfg: Dict[str, Any],
    measurements,
    windows,
    params,
    *,
    include_constraints: bool = False,
) -> np.ndarray:
    """Differentiate either measurement data or the complete objective.

    The default is intentionally measurement-only because this module owns
    observability. Callers computing conditional objective curvature must opt
    into priors and regularization explicitly.
    """

    x0 = params.initial_vector(case_cfg)
    r0, _ = residual_vector(
        model,
        deepcopy(case_cfg),
        inv_cfg,
        measurements,
        windows,
        include_constraints=include_constraints,
    )
    J = np.zeros((len(r0), len(x0)), dtype=float)
    for j, x in enumerate(x0):
        dx = 1.0e-4 * max(abs(x), 1.0)
        xp = x0.copy()
        xp[j] += dx
        cfgp = deepcopy(case_cfg)
        params.apply_to_case(cfgp, xp)
        rp, _ = residual_vector(
            model,
            cfgp,
            inv_cfg,
            measurements,
            windows,
            include_constraints=include_constraints,
        )
        J[:, j] = (rp - r0) / dx
    return J


def identifiability_summary(model, case_cfg, inv_cfg, measurements, windows, params) -> Dict[str, Any]:
    J = finite_difference_jacobian(
        model,
        case_cfg,
        inv_cfg,
        measurements,
        windows,
        params,
        include_constraints=False,
    )
    _, aux = residual_vector(
        model,
        deepcopy(case_cfg),
        inv_cfg,
        measurements,
        windows,
        include_constraints=False,
    )
    summary = summarize_jacobian(J, parameter_names=params.names())
    summary["basis"] = "measurement_data_only"
    summary["selected_windows"] = aux.get("selected_windows", {})
    return summary


def summarize_jacobian(
    J: np.ndarray,
    rank_rtol: float = 1.0e-8,
    parameter_names: Sequence[str] | None = None,
    max_direction_components: int = 5,
) -> Dict[str, Any]:
    """Summarize rank and the parameter combinations behind weak directions."""

    matrix = np.asarray(J, dtype=float)
    if matrix.ndim != 2:
        raise ValueError(f"Jacobian must be two-dimensional, got shape {matrix.shape}.")
    n_parameters = int(matrix.shape[1])
    names = list(parameter_names) if parameter_names is not None else [f"parameter_{i}" for i in range(n_parameters)]
    if len(names) != n_parameters:
        raise ValueError(f"Received {len(names)} parameter names for {n_parameters} Jacobian columns.")

    _, compact_singular_values, right_vectors = np.linalg.svd(matrix, full_matrices=True)
    singular_values = np.zeros(n_parameters, dtype=float)
    singular_values[: len(compact_singular_values)] = compact_singular_values
    largest = float(singular_values[0]) if n_parameters else 0.0
    threshold = max(largest * rank_rtol, 1.0e-12)
    rank = int(np.sum(singular_values > threshold))
    weakest = float(singular_values[-1]) if n_parameters else 0.0
    cond = float(largest / weakest) if weakest > threshold else float("inf")
    column_norms = np.linalg.norm(matrix, axis=0) if n_parameters else np.zeros(0, dtype=float)

    directions = []
    for index, (singular_value, vector) in enumerate(zip(singular_values, right_vectors, strict=True)):
        order = np.argsort(np.abs(vector))[::-1][: max(1, max_direction_components)]
        directions.append(
            {
                "index": index,
                "singular_value": float(singular_value),
                "relative_strength": float(singular_value / largest) if largest > 0.0 else 0.0,
                "identifiable": bool(singular_value > threshold),
                "dominant_parameters": [
                    {
                        "name": names[column],
                        "coefficient": float(vector[column]),
                    }
                    for column in order
                    if abs(float(vector[column])) > 1.0e-12
                ],
            }
        )

    return {
        "singular_values": singular_values.tolist(),
        "singular_directions": directions,
        "parameter_column_norms": {
            name: float(norm) for name, norm in zip(names, column_norms, strict=True)
        },
        "inactive_parameters": [
            name for name, norm in zip(names, column_norms, strict=True) if float(norm) <= threshold
        ],
        "condition_number": cond,
        "rank_estimate": rank,
        "rank_threshold": threshold,
        "n_observations": int(matrix.shape[0]),
        "n_parameters": n_parameters,
    }
