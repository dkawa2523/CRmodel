from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from oescr.inverse.identifiability import summarize_jacobian
from oescr.inverse.objectives import residual_vector
from oescr.inverse.optimize import InverseSolver

ROOT = Path(__file__).resolve().parents[1]


def test_singular_directions_name_the_unobservable_parameter_combination() -> None:
    jacobian = np.asarray([[1.0, 1.0], [2.0, 2.0]])

    summary = summarize_jacobian(jacobian, parameter_names=["te", "density"])

    assert summary["rank_estimate"] == 1
    assert summary["n_parameters"] == 2
    assert summary["condition_number"] == float("inf")
    weak = summary["singular_directions"][-1]
    assert weak["identifiable"] is False
    assert weak["singular_value"] == pytest.approx(0.0, abs=1.0e-12)
    assert {item["name"] for item in weak["dominant_parameters"]} == {"te", "density"}


def test_measurement_observability_excludes_priors_and_regularization() -> None:
    benchmark = ROOT / "examples" / "benchmarks" / "cl2_ar_icp_fuller2001"
    solver = InverseSolver.from_yaml(benchmark / "case_init.yaml", benchmark / "inverse.yaml")

    data_residual, _ = residual_vector(
        solver.model,
        solver.case_cfg,
        solver.inv_cfg,
        solver.measurements,
        solver.windows,
        include_constraints=False,
    )
    objective_residual, _ = residual_vector(
        solver.model,
        solver.case_cfg,
        solver.inv_cfg,
        solver.measurements,
        solver.windows,
        include_constraints=True,
    )

    assert len(data_residual) > 0
    assert len(objective_residual) > len(data_residual)


def test_parameter_name_count_must_match_jacobian_columns() -> None:
    with pytest.raises(ValueError, match="parameter names"):
        summarize_jacobian(np.eye(2), parameter_names=["only_one"])
