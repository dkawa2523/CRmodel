from __future__ import annotations

import numpy as np
import pytest
from scipy import constants as const

from oescr.data.atomic_db import StateRegistry
from oescr.data.cross_section_db import CrossSectionLibrary
from oescr.forward.emissivity import atomic_line_spectrum_zone
from oescr.physics.cr_atomic import AtomicCRSolver
from oescr.physics.rates import RateCalculator


def _solve(cfg: dict, external_densities: dict[str, float]):
    energy_eV = np.asarray([0.0, 1.0])
    solver = AtomicCRSolver(
        cfg,
        StateRegistry(cfg),
        RateCalculator(energy_eV, CrossSectionLibrary()),
    )
    return solver.solve_zone(
        0,
        external_densities,
        np.asarray([1.0, 1.0]),
    )


def test_two_level_cr_matches_closed_form_population_and_balance() -> None:
    ground_density_m3 = 3.0e10
    pump_rate_s_1 = 4.0
    quench_rate_s_1 = 2.0
    radiative_rate_s_1 = 10.0
    cfg = {
        "states": [
            {"id": "G", "species": "X", "energy_eV": 0.0, "solve": False},
            {"id": "U", "species": "X", "energy_eV": 2.0, "solve": True},
        ],
        "reactions": [
            {
                "id": "pump",
                "kind": "first_order",
                "source_state": "G",
                "target_state": "U",
                "coefficient_s-1": pump_rate_s_1,
            },
            {
                "id": "quench",
                "kind": "first_order",
                "source_state": "U",
                "target_state": "G",
                "coefficient_s-1": quench_rate_s_1,
            },
        ],
        "transitions": [
            {
                "id": "U_to_G",
                "upper": "U",
                "lower": "G",
                "wavelength_nm": 500.0,
                "A_s-1": radiative_rate_s_1,
            }
        ],
        "wall": {"model": "none"},
    }

    result = _solve(cfg, {"G": ground_density_m3})
    expected_source_m3_s = ground_density_m3 * pump_rate_s_1
    expected_population_m3 = expected_source_m3_s / (quench_rate_s_1 + radiative_rate_s_1)

    np.testing.assert_allclose(result.matrix, [[quench_rate_s_1 + radiative_rate_s_1]])
    np.testing.assert_allclose(result.rhs, [expected_source_m3_s])
    assert result.populations_m3["U"] == pytest.approx(expected_population_m3)
    assert result.diagnostics.solve_method == "solve"
    assert result.diagnostics.matrix_rank == 1
    assert result.diagnostics.relative_residual < 1.0e-14
    balance = result.state_balances["U"]
    assert balance.total_source_m3_s == pytest.approx(expected_source_m3_s)
    assert balance.total_loss_m3_s == pytest.approx(expected_source_m3_s)
    assert balance.net_m3_s == pytest.approx(0.0, abs=1.0e-5)


def test_three_level_cascade_matches_closed_form_branching_and_photon_rates() -> None:
    ground_density_m3 = 2.0e9
    pump_rate_s_1 = 3.0
    upper_to_middle_s_1 = 4.0
    upper_to_ground_s_1 = 6.0
    middle_to_ground_s_1 = 5.0
    cfg = {
        "states": [
            {"id": "G", "species": "X", "energy_eV": 0.0, "solve": False},
            {"id": "U", "species": "X", "energy_eV": 3.0, "solve": True},
            {"id": "M", "species": "X", "energy_eV": 1.0, "solve": True},
        ],
        "reactions": [
            {
                "id": "pump",
                "kind": "first_order",
                "source_state": "G",
                "target_state": "U",
                "coefficient_s-1": pump_rate_s_1,
            }
        ],
        "transitions": [
            {
                "id": "U_to_M",
                "upper": "U",
                "lower": "M",
                "wavelength_nm": 500.0,
                "A_s-1": upper_to_middle_s_1,
            },
            {
                "id": "U_to_G",
                "upper": "U",
                "lower": "G",
                "wavelength_nm": 600.0,
                "A_s-1": upper_to_ground_s_1,
            },
            {
                "id": "M_to_G",
                "upper": "M",
                "lower": "G",
                "wavelength_nm": 700.0,
                "A_s-1": middle_to_ground_s_1,
            },
        ],
        "wall": {"model": "none"},
    }

    result = _solve(cfg, {"G": ground_density_m3})
    source_m3_s = ground_density_m3 * pump_rate_s_1
    expected_upper_m3 = source_m3_s / (upper_to_middle_s_1 + upper_to_ground_s_1)
    expected_middle_m3 = upper_to_middle_s_1 * expected_upper_m3 / middle_to_ground_s_1

    assert result.populations_m3 == pytest.approx(
        {"U": expected_upper_m3, "M": expected_middle_m3}
    )
    np.testing.assert_allclose(
        result.matrix,
        [
            [upper_to_middle_s_1 + upper_to_ground_s_1, 0.0],
            [-upper_to_middle_s_1, middle_to_ground_s_1],
        ],
    )
    for balance in result.state_balances.values():
        assert balance.net_m3_s == pytest.approx(0.0, abs=1.0e-5)

    wavelength_nm = np.linspace(450.0, 750.0, 30001)
    emission = atomic_line_spectrum_zone(
        cfg,
        StateRegistry(cfg),
        result.populations_m3,
        wavelength_nm,
        zone_context={"G": ground_density_m3},
    )
    photon_rates = {
        float(line["wavelength_nm"]): (
            float(line["integrated_emissivity_W_m3_sr"])
            * 4.0
            * np.pi
            / (const.h * const.c / (float(line["wavelength_nm"]) * 1.0e-9))
        )
        for line in emission["lines"]
    }

    assert photon_rates[500.0] == pytest.approx(upper_to_middle_s_1 * expected_upper_m3)
    assert photon_rates[600.0] == pytest.approx(upper_to_ground_s_1 * expected_upper_m3)
    assert photon_rates[700.0] == pytest.approx(middle_to_ground_s_1 * expected_middle_m3)
    assert photon_rates[500.0] / photon_rates[600.0] == pytest.approx(
        upper_to_middle_s_1 / upper_to_ground_s_1
    )
    assert photon_rates[500.0] + photon_rates[600.0] == pytest.approx(source_m3_s)
    assert photon_rates[700.0] == pytest.approx(photon_rates[500.0])
