
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import numpy as np
from scipy.optimize import differential_evolution, least_squares

from ..forward.model import OESCRModel
from ..instrument.capability import all_instruments_low_res
from ..io.normalize import normalize_case_config, normalize_inverse_config
from ..io.validators import validate_case_structural, validate_inverse_config, validate_inverse_structural
from ..io.yaml_loader import load_yaml
from .identifiability import finite_difference_jacobian
from .laplace import covariance_from_jacobian, summarize_covariance
from .objectives import load_measurements, load_windows, residual_vector
from .params import ParameterSet


@dataclass
class FitResult:
    x_opt: np.ndarray
    case_opt: Dict[str, Any]
    cost: float
    success: bool
    message: str
    aux: Dict[str, Any]
    uncertainty: Dict[str, Any] | None = None


class InverseSolver:
    def __init__(self, case_cfg: Dict[str, Any], inv_cfg: Dict[str, Any]) -> None:
        validate_case_structural(case_cfg)
        validate_inverse_structural(inv_cfg)
        case_cfg = normalize_case_config(case_cfg)
        inv_cfg = normalize_inverse_config(case_cfg, inv_cfg)
        validate_inverse_config(case_cfg, inv_cfg)
        self.case_cfg = deepcopy(case_cfg)
        self.inv_cfg = deepcopy(inv_cfg)
        self.model = OESCRModel(self.case_cfg)
        self.params = ParameterSet(self.inv_cfg["parameters"])
        self.measurements = load_measurements(self.case_cfg, self.inv_cfg)
        self.windows = load_windows(self.case_cfg)
        self._enforce_capabilities()

    @classmethod
    def from_yaml(cls, case_path: str | Path, inverse_path: str | Path) -> "InverseSolver":
        case_cfg = load_yaml(case_path)
        inv_cfg = load_yaml(inverse_path)
        return cls(case_cfg, inv_cfg)

    def _enforce_capabilities(self) -> None:
        mode = self.case_cfg.get("plasma_mode", "te")
        if mode == "eedf_tabulated" and all_instruments_low_res(self.model.instrument_cfgs):
            raise ValueError(
                "Low-resolution instruments are restricted to 'te' or 'eedf_bimaxwell' inverse modes."
            )

    def _objective_residual(self, x: np.ndarray) -> np.ndarray:
        cfg = deepcopy(self.case_cfg)
        self.params.apply_to_case(cfg, x)
        r, _ = residual_vector(self.model, cfg, self.inv_cfg, self.measurements, self.windows)
        return r

    def _objective_scalar(self, x: np.ndarray) -> float:
        r = self._objective_residual(x)
        return 0.5 * float(np.dot(r, r))

    def fit(self) -> FitResult:
        x0 = self.params.initial_vector(self.case_cfg)
        lb, ub = self.params.bounds()
        current = x0.copy()

        fit_cfg = self.inv_cfg.get("fit", {})

        if fit_cfg.get("global", {}).get("enabled", True):
            de_cfg = fit_cfg["global"]
            bounds = list(zip(lb, ub))
            result_de = differential_evolution(
                self._objective_scalar,
                bounds=bounds,
                maxiter=int(de_cfg.get("maxiter", 20)),
                popsize=int(de_cfg.get("popsize", 8)),
                polish=False,
                seed=int(de_cfg.get("seed", 0)),
                tol=float(de_cfg.get("tol", 1.0e-3)),
                updating="deferred",
                workers=1,
            )
            current = result_de.x

        if fit_cfg.get("local", {}).get("enabled", True):
            lsq = least_squares(
                self._objective_residual,
                current,
                bounds=(lb, ub),
                x_scale="jac",
                verbose=0,
                max_nfev=int(fit_cfg.get("local", {}).get("max_nfev", 200)),
            )
            x_opt = lsq.x
            success = bool(lsq.success)
            message = str(lsq.message)
        else:
            x_opt = current
            success = True
            message = "Global optimization only."

        case_opt = deepcopy(self.case_cfg)
        self.params.apply_to_case(case_opt, x_opt)
        r_opt, aux = residual_vector(self.model, case_opt, self.inv_cfg, self.measurements, self.windows)
        cost = 0.5 * float(np.dot(r_opt, r_opt))

        uncertainty = None
        if fit_cfg.get("uncertainty", {}).get("laplace", True):
            J = finite_difference_jacobian(self.model, case_opt, self.inv_cfg, self.measurements, self.windows, self.params)
            cov = covariance_from_jacobian(J)
            uncertainty = summarize_covariance(cov, self.params.names())

        return FitResult(
            x_opt=x_opt,
            case_opt=case_opt,
            cost=cost,
            success=success,
            message=message,
            aux=aux,
            uncertainty=uncertainty,
        )
