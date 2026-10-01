from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import numpy as np
from scipy.optimize import differential_evolution, least_squares

from ..forward.model import OESCRModel
from ..instrument.calibration import CalibrationTransform
from ..instrument.capability import all_instruments_low_res
from ..io.normalize import normalize_case_config, normalize_inverse_config
from ..io.validators import validate_case_structural, validate_inverse_config, validate_inverse_structural
from ..io.yaml_loader import load_yaml
from ..physics.eedf import eedf_model_kind
from .identifiability import finite_difference_jacobian, summarize_jacobian
from .laplace import covariance_from_jacobian, summarize_covariance
from .measurements import load_measurements
from .objectives import load_windows, residual_vector
from .params import ParameterSet
from .use_cases import assess_inference_use_case


@dataclass
class FitResult:
    x_opt: np.ndarray
    case_opt: Dict[str, Any]
    cost: float
    success: bool
    message: str
    aux: Dict[str, Any]
    uncertainty: Dict[str, Any] | None = None
    identifiability: Dict[str, Any] | None = None
    assessment: Dict[str, Any] | None = None
    calibration_uncertainty: Dict[str, float] | None = None
    optimization_trace: list[Dict[str, Any]] | None = None


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
        instrument_cfgs = self.model.instrument_configs_for()
        self.assessment = assess_inference_use_case(
            self.case_cfg,
            self.inv_cfg,
            (parameter.path for parameter in self.params.params),
            instrument_cfgs,
        )
        self.measurements = load_measurements(self.inv_cfg, instrument_cfgs)
        self.windows = load_windows(self.case_cfg)
        self._enforce_capabilities()

    @classmethod
    def from_yaml(cls, case_path: str | Path, inverse_path: str | Path) -> "InverseSolver":
        case_cfg = load_yaml(case_path)
        inv_cfg = load_yaml(inverse_path)
        return cls(case_cfg, inv_cfg)

    def _enforce_capabilities(self) -> None:
        if eedf_model_kind(self.case_cfg) == "eedf_tabulated" and all_instruments_low_res(
            self.model.instrument_configs_for()
        ):
            raise ValueError("Low-resolution instruments are restricted to 'te' or 'eedf_bimaxwell' inverse modes.")

    def _objective_residual(self, x: np.ndarray) -> np.ndarray:
        cfg = deepcopy(self.case_cfg)
        self.params.apply_to_case(cfg, x)
        r, _ = residual_vector(self.model, cfg, self.inv_cfg, self.measurements, self.windows)
        return r

    def _objective_scalar(self, x: np.ndarray) -> float:
        r = self._objective_residual(x)
        return 0.5 * float(np.dot(r, r))

    def fit(self, *, record_trace: bool = False) -> FitResult:
        x0 = self.params.initial_vector(self.case_cfg)
        lb, ub = self.params.bounds()
        current = x0.copy()
        optimization_trace: list[Dict[str, Any]] = []

        def recorded_residual(x: np.ndarray, stage: str) -> np.ndarray:
            residual = self._objective_residual(x)
            if record_trace:
                optimization_trace.append(
                    {
                        "evaluation": len(optimization_trace),
                        "stage": stage,
                        "loss": 0.5 * float(np.dot(residual, residual)),
                        "x": np.asarray(x, dtype=float).tolist(),
                    }
                )
            return residual

        def global_objective(x: np.ndarray) -> float:
            residual = recorded_residual(x, "global")
            return 0.5 * float(np.dot(residual, residual))

        def local_objective(x: np.ndarray) -> np.ndarray:
            return recorded_residual(x, "local")

        fit_cfg = self.inv_cfg.get("fit", {})

        if fit_cfg.get("global", {}).get("enabled", True):
            de_cfg = fit_cfg["global"]
            bounds = list(zip(lb, ub, strict=True))
            result_de = differential_evolution(
                global_objective,
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
                local_objective,
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
        if record_trace:
            optimization_trace.append(
                {
                    "evaluation": len(optimization_trace),
                    "stage": "final",
                    "loss": cost,
                    "x": np.asarray(x_opt, dtype=float).tolist(),
                }
            )

        uncertainty = None
        identifiability = None
        calculate_laplace = bool(fit_cfg.get("uncertainty", {}).get("laplace", True))
        ident_cfg = fit_cfg.get("identifiability", {})
        calculate_identifiability = bool(ident_cfg.get("enabled", True))
        if calculate_identifiability:
            data_jacobian = finite_difference_jacobian(
                self.model,
                case_opt,
                self.inv_cfg,
                self.measurements,
                self.windows,
                self.params,
                include_constraints=False,
            )
            identifiability = summarize_jacobian(
                data_jacobian,
                rank_rtol=float(ident_cfg.get("rank_rtol", 1.0e-8)),
                parameter_names=self.params.names(),
            )
            identifiability["basis"] = "measurement_data_only"
            identifiability["selected_windows"] = aux.get("selected_windows", {})
            full_rank = identifiability["rank_estimate"] == identifiability["n_parameters"]
            if self.assessment.mode == "calibrated_absolute":
                self.assessment.absolute_scale_locally_identifiable = full_rank
            if not full_rank:
                self.assessment.warnings.append(
                    "The fitted Jacobian is rank deficient; at least one parameter combination is not locally identifiable."
                )
        if calculate_laplace:
            objective_jacobian = finite_difference_jacobian(
                self.model,
                case_opt,
                self.inv_cfg,
                self.measurements,
                self.windows,
                self.params,
                include_constraints=True,
            )
            cov = covariance_from_jacobian(objective_jacobian)
            uncertainty = summarize_covariance(cov, self.params.names())

        return FitResult(
            x_opt=x_opt,
            case_opt=case_opt,
            cost=cost,
            success=success,
            message=message,
            aux=aux,
            uncertainty=uncertainty,
            identifiability=identifiability,
            assessment=self.assessment.as_dict(),
            calibration_uncertainty={
                str(instrument["id"]): CalibrationTransform.from_instrument_config(
                    instrument
                ).relative_standard_uncertainty
                for instrument in self.model.instrument_configs_for()
            },
            optimization_trace=optimization_trace if record_trace else None,
        )
