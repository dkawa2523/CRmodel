from __future__ import annotations

from pathlib import Path

import pytest

from oescr.inverse.optimize import InverseSolver

EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "examples" / "use_cases" / "two_band"


@pytest.mark.parametrize(
    ("inverse_name", "mode"),
    [
        ("inverse_ratio.yaml", "ratio_diagnostic"),
        ("inverse_actinometry.yaml", "actinometry"),
    ],
)
def test_ratio_based_vertical_slices_recover_target_density(
    inverse_name: str,
    mode: str,
) -> None:
    solver = InverseSolver.from_yaml(
        EXAMPLE_DIR / "case_ratio_init.yaml",
        EXAMPLE_DIR / inverse_name,
    )

    fit = solver.fit(record_trace=True)

    assert fit.success
    assert fit.case_opt["plasma_state"]["radicals"]["Target"][0] == pytest.approx(2.0e18, rel=1.0e-6)
    assert fit.assessment is not None
    assert fit.assessment["mode"] == mode
    assert fit.identifiability is not None
    assert fit.identifiability["rank_estimate"] == 1
    assert fit.identifiability["n_observations"] == 1
    assert fit.identifiability["selected_windows"]["two_band_radiance"] == [
        "target_500",
        "actinometer_510",
    ]
    assert fit.optimization_trace is not None
    assert [row["evaluation"] for row in fit.optimization_trace] == list(range(len(fit.optimization_trace)))
    assert fit.optimization_trace[-1]["stage"] == "final"
    assert fit.optimization_trace[-1]["loss"] == pytest.approx(fit.cost)


def test_calibrated_absolute_vertical_slice_recovers_electron_density() -> None:
    solver = InverseSolver.from_yaml(
        EXAMPLE_DIR / "case_absolute_init.yaml",
        EXAMPLE_DIR / "inverse_absolute.yaml",
    )

    fit = solver.fit()

    assert fit.success
    assert fit.case_opt["plasma_state"]["ne_shells_m3"][0] == pytest.approx(3.0e16, rel=1.0e-6)
    assert fit.assessment is not None
    assert fit.assessment["mode"] == "calibrated_absolute"
    assert fit.assessment["absolute_scale_prerequisites_met"]
    assert fit.assessment["absolute_scale_locally_identifiable"]
    assert fit.identifiability is not None
    assert fit.identifiability["rank_estimate"] == 1
    assert fit.calibration_uncertainty == {"two_band_radiance": 0.01}
    assert fit.optimization_trace is None
