from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
from scipy import constants as const

from oescr.data.atomic_db import StateRegistry
from oescr.data.cross_section_db import CrossSectionLibrary
from oescr.forward.model import OESCRModel
from oescr.forward.reporting import forward_diagnostics_payload, write_forward_diagnostics
from oescr.instrument.spec import InstrumentSpec
from oescr.inverse.measurements import (
    load_measurement_csv,
    load_measurements,
    spectrum_residuals,
    whiten_feature_residuals,
)
from oescr.inverse.use_cases import assess_inference_use_case
from oescr.io.normalize import normalize_case_config, normalize_inverse_config
from oescr.io.species_packs import SpeciesPackError
from oescr.io.validators import ConfigSemanticError, validate_case_config, validate_inverse_config
from oescr.io.yaml_loader import load_yaml
from oescr.physics.bands import evaluate_band_components_zone
from oescr.physics.cr_processes import (
    assemble_reaction_process,
    build_state_balances,
    compile_reaction_processes,
    sum_process_contributions,
)
from oescr.physics.quality import DiagnosticPolicyError
from oescr.physics.rates import RateCalculator, resolve_reaction_rate_spec
from oescr.physics.trapping import effective_A
from oescr.physics.wall import effective_wall_loss_rate_s, thermal_speed_m_s

ROOT = Path(__file__).resolve().parents[1]


def _example_case():
    return normalize_case_config(load_yaml(ROOT / "examples" / "case_init_cf4_o2_ar.yaml"))


def test_cross_section_load_records_provenance(tmp_path: Path) -> None:
    path = tmp_path / "valid.csv"
    path.write_text(
        "# source: unit-test\nenergy_eV,sigma_m2\n0.0,0.0\n1.0,1.0e-20\n",
        encoding="utf-8",
    )

    cross_section = CrossSectionLibrary().load(path)

    assert cross_section.metadata["source"] == "unit-test"
    assert len(cross_section.sha256) == 64
    assert cross_section.energy_range_eV == (0.0, 1.0)


@pytest.mark.parametrize(
    "rows, message",
    [
        ("0.0,0.0\n0.0,1.0e-20\n", "strictly increasing"),
        ("0.0,0.0\n1.0,-1.0e-20\n", "negative sigma"),
        ("0.0,0.0\n", "at least two"),
    ],
)
def test_cross_section_load_rejects_invalid_tables(tmp_path: Path, rows: str, message: str) -> None:
    path = tmp_path / "invalid.csv"
    path.write_text(f"energy_eV,sigma_m2\n{rows}", encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        CrossSectionLibrary().load(path)


def test_reaction_requires_exactly_one_rate_source() -> None:
    reaction = {
        "id": "bad",
        "cross_section_file": "one.csv",
        "coefficient_m3_s": 1.0e-15,
    }

    with pytest.raises(ValueError, match="exactly one rate source"):
        resolve_reaction_rate_spec(reaction)


@pytest.mark.parametrize(
    "reaction, external, expected_frequency, expected_unit",
    [
        (
            {
                "id": "electron",
                "kind": "electron_excitation",
                "source_state": "X",
                "target_state": "U",
                "coefficient_m3_s": 2.0,
            },
            {"X": 5.0, "e": 3.0},
            6.0,
            "m^3 s^-1",
        ),
        (
            {
                "id": "first",
                "kind": "first_order",
                "source_state": "X",
                "target_state": "U",
                "coefficient_s-1": 2.0,
            },
            {"X": 5.0},
            2.0,
            "s^-1",
        ),
        (
            {
                "id": "second",
                "kind": "two_body",
                "source_state": "X",
                "target_state": "U",
                "colliders": ["M"],
                "coefficient_m3_s": 2.0,
            },
            {"X": 5.0, "M": 3.0},
            6.0,
            "m^3 s^-1",
        ),
        (
            {
                "id": "third",
                "kind": "three_body",
                "source_state": "X",
                "target_state": "U",
                "colliders": ["M", "M"],
                "coefficient_m6_s": 2.0,
            },
            {"X": 5.0, "M": 3.0},
            18.0,
            "m^6 s^-1",
        ),
    ],
)
def test_compiled_reaction_families_have_explicit_units_and_analytic_rhs(
    reaction: dict,
    external: dict,
    expected_frequency: float,
    expected_unit: str,
) -> None:
    registry = StateRegistry({"states": [{"id": "U", "energy_eV": 1.0, "solve": True}]})
    rate_calculator = RateCalculator(np.asarray([0.0, 1.0]), CrossSectionLibrary())
    process = compile_reaction_processes({"reactions": [reaction]})[0]
    contribution = assemble_reaction_process(
        process,
        registry,
        rate_calculator,
        external,
        np.asarray([1.0, 1.0]),
    )

    assert contribution.coefficient_unit == expected_unit
    assert contribution.effective_frequency_s_1 == expected_frequency
    assert np.allclose(contribution.matrix, 0.0)
    assert np.allclose(contribution.rhs, [expected_frequency * external["X"]])


def test_reaction_contributions_reproduce_matrix_rhs_and_state_budgets() -> None:
    registry = StateRegistry(
        {
            "states": [
                {"id": "A", "energy_eV": 1.0, "solve": True},
                {"id": "B", "energy_eV": 2.0, "solve": True},
            ]
        }
    )
    reaction = {
        "id": "transfer",
        "kind": "two_body",
        "source_state": "A",
        "target_state": "B",
        "colliders": ["M"],
        "coefficient_m3_s": 2.0,
    }
    process = compile_reaction_processes({"reactions": [reaction]})[0]
    contribution = assemble_reaction_process(
        process,
        registry,
        RateCalculator(np.asarray([0.0, 1.0]), CrossSectionLibrary()),
        {"M": 3.0},
        np.asarray([1.0, 1.0]),
    )

    matrix, rhs = sum_process_contributions([contribution], 2)
    balances = build_state_balances([contribution], np.asarray([4.0, 1.0]), registry)

    assert np.allclose(matrix, [[6.0, 0.0], [-6.0, 0.0]])
    assert np.allclose(rhs, [0.0, 0.0])
    assert balances["A"].total_loss_m3_s == 24.0
    assert balances["B"].total_source_m3_s == 24.0


def test_reaction_family_rejects_wrong_coefficient_dimension() -> None:
    reaction = {
        "id": "bad_second_order",
        "kind": "two_body",
        "source_state": "A",
        "colliders": ["M"],
        "coefficient_m6_s": 1.0,
    }

    with pytest.raises(ValueError, match="requires only 'coefficient_m3_s'"):
        compile_reaction_processes({"reactions": [reaction]})


def test_case_rejects_duplicate_state_ids() -> None:
    cfg = _example_case()
    cfg["states"].append(deepcopy(cfg["states"][0]))

    with pytest.raises(ConfigSemanticError, match="Duplicate states id"):
        validate_case_config(cfg)


def test_case_rejects_gas_fractions_that_do_not_sum_to_one() -> None:
    cfg = _example_case()
    cfg["gas_mixture"]["fractions"]["Ar"] = 0.2

    with pytest.raises(ConfigSemanticError, match="must sum to 1.0"):
        validate_case_config(cfg)


def test_case_rejects_nonlinear_solved_state_collider() -> None:
    cfg = _example_case()
    cfg["reactions"].append(
        {
            "id": "nonlinear_quenching",
            "kind": "two_body",
            "source_state": "Ar_2p6",
            "colliders": ["Ar_2p1"],
            "coefficient_m3_s": 1.0e-16,
        }
    )

    with pytest.raises(ConfigSemanticError, match="would make the current CR system nonlinear"):
        validate_case_config(cfg)


def test_effective_bands_require_explicit_empirical_mode() -> None:
    cfg = _example_case()
    cfg["emission_mode"] = "physical"

    with pytest.raises(ConfigSemanticError, match="emission_mode='empirical'"):
        validate_case_config(cfg)


def test_relative_shape_reports_electron_density_gain_confounding() -> None:
    assessment = assess_inference_use_case(
        _example_case(),
        {
            "inference_mode": "relative_shape",
            "fit": {"objective": {"auto_gain_fit": True}},
        },
        ["plasma_state.ne_shells_m3[0]"],
    )

    assert not assessment.absolute_scale_prerequisites_met
    assert assessment.absolute_scale_locally_identifiable is None
    assert any("absolute scale is confounded" in warning for warning in assessment.warnings)


@pytest.mark.parametrize("mode", ["ratio_diagnostic", "actinometry"])
def test_ratio_interpretation_modes_require_an_active_ratio_objective(mode: str) -> None:
    case_cfg = _example_case()
    instrument_id = str(case_cfg["instruments"][0]["id"])
    inverse_cfg = normalize_inverse_config(
        case_cfg,
        {
            "inference_mode": mode,
            "measurements": [{"instrument_id": instrument_id, "file": "unused.csv"}],
            "parameters": [
                {
                    "name": "te_0",
                    "path": "plasma_state.te_shells_eV[0]",
                    "bounds": [1.0, 5.0],
                }
            ],
            "fit": {"objective": {"spectrum_weight": 0.0}},
        },
    )

    with pytest.raises(ConfigSemanticError, match="requires an active ratio objective"):
        validate_inverse_config(case_cfg, inverse_cfg)

    inverse_cfg["fit"]["objective"]["window_ratio_weight"] = 1.0
    validate_inverse_config(case_cfg, inverse_cfg)

    inverse_cfg["fit"]["objective"]["window_ratio_weight"] = 0.0
    inverse_cfg["fit"]["objective"]["window_ratio_pairs"] = [
        {"name": "diagnostic", "numerator": "line_a", "denominator": "line_b"}
    ]
    inverse_cfg["measurements"][0]["feature_covariance"] = {
        "names": ["ratio:diagnostic"],
        "matrix": [[1.0]],
    }
    validate_inverse_config(case_cfg, inverse_cfg)


def test_calibrated_absolute_rejects_fitted_gain() -> None:
    with pytest.raises(ValueError, match="auto_gain_fit=false"):
        assess_inference_use_case(
            _example_case(),
            {
                "inference_mode": "calibrated_absolute",
                "fit": {"objective": {"auto_gain_fit": True}},
            },
            ["plasma_state.ne_shells_m3[0]"],
        )


def test_calibrated_absolute_requires_calibration_and_physical_emitters() -> None:
    case_cfg = _example_case()
    inverse_cfg = {
        "inference_mode": "calibrated_absolute",
        "fit": {"objective": {"auto_gain_fit": False}},
    }
    with pytest.raises(ValueError, match="calibration.absolute=true"):
        assess_inference_use_case(case_cfg, inverse_cfg, [], [{"id": "uvvis"}])

    calibrated = [
        {
            "id": "uvvis",
            "calibration": {
                "kind": "spectral_radiance",
                "absolute": True,
                "input_basis": "spectral_radiance",
                "output_unit": "W_m-2_sr-1_nm-1",
                "reference": "unit-test calibration",
            },
        }
    ]
    with pytest.raises(ValueError, match="empirical effective bands"):
        assess_inference_use_case(case_cfg, inverse_cfg, [], calibrated)


def test_calibrated_absolute_separates_prerequisites_from_local_rank() -> None:
    case_cfg = _example_case()
    case_cfg["bands"] = []
    instrument = {
        "id": "uvvis",
        "calibration": {
            "kind": "spectral_radiance",
            "absolute": True,
            "input_basis": "spectral_radiance",
            "output_unit": "W_m-2_sr-1_nm-1",
            "reference": "unit-test calibration",
        },
    }

    assessment = assess_inference_use_case(
        case_cfg,
        {
            "inference_mode": "calibrated_absolute",
            "fit": {"objective": {"auto_gain_fit": False}},
        },
        ["plasma_state.ne_shells_m3[0]"],
        [instrument],
    )

    assert assessment.absolute_scale_prerequisites_met
    assert assessment.absolute_scale_locally_identifiable is None


def test_measurement_csv_reads_positive_pointwise_sigma(tmp_path: Path) -> None:
    path = tmp_path / "measurement.csv"
    path.write_text(
        "wavelength_nm,intensity,sigma\n500.0,2.0,0.1\n501.0,3.0,0.2\n",
        encoding="utf-8",
    )

    measurement = load_measurement_csv(path)

    assert measurement.sigma is not None
    assert np.allclose(measurement.sigma, [0.1, 0.2])


def test_measurement_covariance_whitens_correlated_residuals(tmp_path: Path) -> None:
    measurement_path = tmp_path / "measurement.csv"
    measurement_path.write_text(
        "wavelength_nm,intensity\n500.0,2.0\n501.0,3.0\n",
        encoding="utf-8",
    )
    covariance_path = tmp_path / "covariance.csv"
    covariance_path.write_text("4.0,1.0\n1.0,9.0\n", encoding="utf-8")

    measurement = load_measurement_csv(measurement_path, covariance_path)
    residual = spectrum_residuals(measurement, np.asarray([4.0, 6.0]))
    expected = np.linalg.solve(np.linalg.cholesky(np.asarray([[4.0, 1.0], [1.0, 9.0]])), [2.0, 3.0])

    assert measurement.covariance is not None
    assert np.allclose(residual, expected)


def test_feature_covariance_whitens_named_window_and_ratio_residuals(tmp_path: Path) -> None:
    measurement_path = tmp_path / "measurement.csv"
    measurement_path.write_text(
        "wavelength_nm,intensity\n500.0,2.0\n501.0,3.0\n",
        encoding="utf-8",
    )
    covariance = np.asarray([[0.04, 0.01], [0.01, 0.09]])
    inverse = {
        "__base_dir__": str(tmp_path),
        "measurements": [
            {
                "instrument_id": "uvvis",
                "file": "measurement.csv",
                "feature_covariance": {
                    "names": ["window:X:area", "ratio:X_to_Y"],
                    "matrix": covariance.tolist(),
                },
            }
        ],
    }

    measurement = load_measurements(inverse)["uvvis"][0]
    residual = whiten_feature_residuals(
        measurement,
        {"window:X:area": 0.2, "ratio:X_to_Y": -0.3},
    )
    expected = np.linalg.solve(np.linalg.cholesky(covariance), [0.2, -0.3])

    assert np.allclose(residual, expected)


def test_absolute_calibration_uncertainty_adds_correlated_measurement_error(tmp_path: Path) -> None:
    measurement_path = tmp_path / "measurement.csv"
    measurement_path.write_text(
        "# output_basis: spectral_radiance_W_m-2_sr-1_nm-1\n"
        "# output_unit: W_m-2_sr-1_nm-1\n"
        "# calibration_reference: expected calibration\n"
        "wavelength_nm,intensity,sigma\n500.0,10.0,1.0\n501.0,20.0,1.0\n",
        encoding="utf-8",
    )
    instrument = {
        "id": "uvvis",
        "calibration": {
            "kind": "spectral_radiance",
            "absolute": True,
            "input_basis": "spectral_radiance",
            "output_unit": "W_m-2_sr-1_nm-1",
            "reference": "expected calibration",
            "relative_standard_uncertainty": 0.1,
        },
    }
    inverse = {
        "__base_dir__": str(tmp_path),
        "inference_mode": "calibrated_absolute",
        "measurements": [{"instrument_id": "uvvis", "file": "measurement.csv"}],
    }

    measurement = load_measurements(inverse, [instrument])["uvvis"][0]
    residual = spectrum_residuals(measurement, np.asarray([12.0, 23.0]))
    covariance = np.eye(2) + np.outer([1.0, 2.0], [1.0, 2.0])
    expected = np.linalg.solve(np.linalg.cholesky(covariance), [2.0, 3.0])

    assert measurement.calibration_relative_standard_uncertainty == 0.1
    assert np.allclose(residual, expected)


def test_absolute_calibration_uncertainty_requires_measurement_noise(tmp_path: Path) -> None:
    measurement_path = tmp_path / "measurement.csv"
    measurement_path.write_text(
        "# output_basis: spectral_radiance_W_m-2_sr-1_nm-1\n"
        "# output_unit: W_m-2_sr-1_nm-1\n"
        "# calibration_reference: expected calibration\n"
        "wavelength_nm,intensity\n500.0,10.0\n501.0,20.0\n",
        encoding="utf-8",
    )
    instrument = {
        "id": "uvvis",
        "calibration": {
            "kind": "spectral_radiance",
            "absolute": True,
            "input_basis": "spectral_radiance",
            "output_unit": "W_m-2_sr-1_nm-1",
            "reference": "expected calibration",
            "relative_standard_uncertainty": 0.1,
        },
    }
    inverse = {
        "__base_dir__": str(tmp_path),
        "inference_mode": "calibrated_absolute",
        "measurements": [{"instrument_id": "uvvis", "file": "measurement.csv"}],
    }

    with pytest.raises(ValueError, match="calibration uncertainty but no pointwise sigma"):
        load_measurements(inverse, [instrument])


def test_absolute_measurement_metadata_must_match_instrument(tmp_path: Path) -> None:
    measurement_path = tmp_path / "measurement.csv"
    measurement_path.write_text(
        "# output_basis: spectral_power_W_nm-1\n"
        "# output_unit: W_nm-1\n"
        "# calibration_reference: wrong calibration\n"
        "wavelength_nm,intensity\n500.0,2.0\n501.0,3.0\n",
        encoding="utf-8",
    )
    instrument = {
        "id": "uvvis",
        "calibration": {
            "kind": "spectral_radiance",
            "absolute": True,
            "input_basis": "spectral_radiance",
            "output_unit": "W_m-2_sr-1_nm-1",
            "reference": "expected calibration",
        },
    }
    inverse = {
        "__base_dir__": str(tmp_path),
        "inference_mode": "calibrated_absolute",
        "measurements": [{"instrument_id": "uvvis", "file": "measurement.csv"}],
    }

    with pytest.raises(ValueError, match="metadata does not match"):
        load_measurements(inverse, [instrument])


def test_instrument_calibration_applies_etendue_and_photon_conversion() -> None:
    common = {
        "id": "calibrated",
        "wavelength_grid_nm": [500.0, 501.0],
        "throughput": 1.0,
        "lsf": {"kind": "gaussian", "fwhm_nm": 0.001},
        "baseline": {"kind": "constant", "offset": 0.0},
        "calibration": {
            "kind": "photoelectron_spectrum",
            "absolute": True,
            "input_basis": "spectral_radiance",
            "output_unit": "photoelectron_nm-1",
            "reference": "unit-test calibration",
            "collection_area_m2": 2.0e-6,
            "collection_solid_angle_sr": 3.0e-4,
            "viewing_factor": 0.5,
            "integration_time_s": 0.02,
            "quantum_efficiency": 0.25,
        },
    }
    instrument = InstrumentSpec(common)
    fine_wavelength = np.linspace(499.0, 502.0, 3001)
    observed = instrument.observe(fine_wavelength, np.ones_like(fine_wavelength))

    photon_energy = const.h * const.c / (500.5e-9)
    expected = 2.0e-6 * 3.0e-4 * 0.5 * 0.02 * 0.25 / photon_energy
    assert np.allclose(observed["intensity"], expected, rtol=2.0e-3)
    assert observed["output_unit"] == "photoelectron_nm-1"


def test_physical_electron_impact_band_has_radiant_power_basis() -> None:
    energy = np.linspace(0.0, 20.0, 101)
    eedf = np.ones_like(energy)
    eedf /= np.trapezoid(eedf, energy)
    wavelength = np.linspace(495.0, 505.0, 1001)
    band = {
        "id": "physical_band",
        "kind": "electron_impact_photon_band",
        "source_density_key": "X",
        "coefficient_m3_s": 2.0e-14,
        "photon_yield": 0.6,
        "branching_ratio": 0.5,
        "profile_kind": "gaussian",
        "center_nm": 500.0,
        "fwhm_nm": 1.0,
    }
    rate_calculator = RateCalculator(energy, CrossSectionLibrary())

    result = evaluate_band_components_zone(
        {"bands": [band]},
        0,
        wavelength,
        {"e": 3.0e16, "X": 4.0e19},
        eedf,
        rate_calculator,
    )["physical_band"]

    photon_rate = 3.0e16 * 4.0e19 * 2.0e-14 * 0.6 * 0.5
    representative_energy = const.h * const.c / (500.0e-9)
    expected = photon_rate * representative_energy / (4.0 * np.pi)
    assert np.isclose(np.trapezoid(result.spectrum, wavelength), expected, rtol=1.0e-5)
    assert result.output_basis == "spectral_radiant_power_W_m-3_sr-1_nm-1"


def test_physical_band_analytic_benchmark() -> None:
    benchmark_dir = ROOT / "examples" / "benchmarks" / "physical_band_analytic"
    benchmark = load_yaml(benchmark_dir / "benchmark.yaml")
    result = OESCRModel.from_yaml(benchmark_dir / benchmark["case"]).predict()
    expected = benchmark["expected"]
    tolerance = float(expected["relative_tolerance"])

    integrated_emissivity = np.trapezoid(result.zone_band_emissivity[0], result.fine_wavelength_nm)
    observed = result.spectra["analytic_radiance"]["chord_0"]
    integrated_radiance = np.trapezoid(observed["intensity"], observed["wavelength_nm"])

    assert result.emission_basis == "spectral_radiant_power_W_m-3_sr-1_nm-1"
    assert result.zone_diagnostics[0].cr.solve_method == "empty"
    assert observed["output_unit"] == "W_m-2_sr-1_nm-1"
    assert np.isclose(
        integrated_emissivity,
        float(expected["integrated_emissivity_W_m3_sr"]),
        rtol=tolerance,
    )
    assert np.isclose(
        integrated_radiance,
        float(expected["central_chord_integrated_radiance_W_m2_sr"]),
        rtol=tolerance,
    )


def test_atomic_line_and_physical_band_conserve_combined_radiant_power() -> None:
    benchmark_dir = ROOT / "examples" / "benchmarks" / "physical_band_analytic"
    benchmark = load_yaml(benchmark_dir / "combined_benchmark.yaml")
    result = OESCRModel.from_yaml(benchmark_dir / benchmark["case"]).predict()
    expected = benchmark["expected"]
    tolerance = float(expected["relative_tolerance"])

    atomic = np.trapezoid(result.zone_atomic_emissivity[0], result.fine_wavelength_nm)
    band = np.trapezoid(result.zone_band_emissivity[0], result.fine_wavelength_nm)
    total = np.trapezoid(result.zone_emissivity[0], result.fine_wavelength_nm)
    observed = result.spectra["combined_radiance"]["chord_0"]
    radiance = np.trapezoid(observed["intensity"], observed["wavelength_nm"])

    assert np.isclose(atomic, float(expected["atomic_line_emissivity_W_m3_sr"]), rtol=tolerance)
    assert np.isclose(band, float(expected["band_emissivity_W_m3_sr"]), rtol=tolerance)
    assert np.isclose(total, atomic + band, rtol=1.0e-12)
    assert np.isclose(total, float(expected["combined_emissivity_W_m3_sr"]), rtol=tolerance)
    assert np.isclose(
        radiance,
        float(expected["central_chord_combined_radiance_W_m2_sr"]),
        rtol=tolerance,
    )
    state_balance = result.zone_diagnostics[0].state_balances["X_excited"]
    assert any(key.startswith("reaction:") for key in state_balance.sources_m3_s)
    assert any(key.startswith("radiative:") for key in state_balance.losses_m3_s)
    assert np.isclose(state_balance.net_m3_s, 0.0, atol=1.0e-6 * state_balance.total_source_m3_s)


def test_singular_cr_system_fails_with_specific_quality_category() -> None:
    benchmark_dir = ROOT / "examples" / "benchmarks" / "physical_band_analytic"
    cfg = load_yaml(benchmark_dir / "case.yaml")
    cfg["states"] = [{"id": "unbalanced", "energy_eV": 1.0, "solve": True}]

    with pytest.raises(DiagnosticPolicyError, match="cr.singular_matrix") as caught:
        OESCRModel(cfg).predict()

    categories = {event.category for event in caught.value.report.events}
    assert "cr.singular_matrix" in categories


def test_quality_report_mode_preserves_failed_result_for_inspection() -> None:
    benchmark_dir = ROOT / "examples" / "benchmarks" / "physical_band_analytic"
    cfg = load_yaml(benchmark_dir / "case.yaml")
    cfg["states"] = [{"id": "unbalanced", "energy_eV": 1.0, "solve": True}]
    cfg.setdefault("diagnostics", {})["quality"] = {"on_error": "report"}

    result = OESCRModel(cfg).predict()

    assert result.quality_report.status == "error"
    assert any(event.category == "cr.singular_matrix" for event in result.quality_report.events)


def test_under_resolved_energy_range_fails_with_eedf_category() -> None:
    benchmark_dir = ROOT / "examples" / "benchmarks" / "physical_band_analytic"
    cfg = load_yaml(benchmark_dir / "case.yaml")
    cfg["energy_grid"]["max_eV"] = 2.0

    with pytest.raises(DiagnosticPolicyError) as caught:
        OESCRModel(cfg).predict()

    categories = {event.category for event in caught.value.report.events}
    assert "eedf.upper_decile_mass" in categories
    assert "eedf.upper_edge_pdf" in categories


def test_explicit_grid_convergence_records_energy_and_wavelength_checks() -> None:
    benchmark_dir = ROOT / "examples" / "benchmarks" / "physical_band_analytic"
    cfg = load_yaml(benchmark_dir / "combined_case.yaml")
    cfg.setdefault("diagnostics", {})["convergence"] = {
        "enabled": True,
        "energy_grid_factor": 2,
        "wavelength_grid_factor": 2,
        "warn_relative_above": 1.0e-3,
        "error_relative_above": 1.0e-2,
    }

    result = OESCRModel(cfg).predict()

    assert result.quality_report.status == "pass"
    assert result.quality_report.convergence["energy_grid"]["refinement_factor"] == 2
    assert result.quality_report.convergence["wavelength_grid"]["refinement_factor"] == 2


def test_forward_diagnostics_payload_and_yaml_include_provenance(tmp_path: Path) -> None:
    benchmark_dir = ROOT / "examples" / "benchmarks" / "physical_band_analytic"
    result = OESCRModel.from_yaml(benchmark_dir / "combined_case.yaml").predict()
    output_path = tmp_path / "diagnostics.yaml"

    payload = forward_diagnostics_payload(result)
    write_forward_diagnostics(result, output_path)
    written = load_yaml(output_path)

    assert payload["quality"]["status"] == "pass"
    assert payload["zones"][0]["state_balances"]["X_excited"]
    assert written["provenance"] == result.provenance


def test_diagnostic_threshold_order_is_validated() -> None:
    cfg = _example_case()
    cfg.setdefault("diagnostics", {})["quality"] = {
        "thresholds": {
            "cr_condition_warn_above": 1.0e15,
            "cr_condition_error_above": 1.0e10,
        }
    }

    with pytest.raises(ConfigSemanticError, match="must be <="):
        validate_case_config(cfg)


def test_legacy_quenching_and_loss_are_normalized_to_reactions() -> None:
    cfg = _example_case()
    cfg["quenching"] = [
        {
            "state": "Ar_2p1",
            "collider": "O2",
            "rate_coefficient_m3_s": 1.5e-16,
        }
    ]
    cfg["losses"] = [{"state": "Ar_2p6", "rate_coefficient_s-1": 4.0e3}]

    normalized = normalize_case_config(cfg)

    assert "quenching" not in normalized
    assert "losses" not in normalized
    quenching, loss = normalized["reactions"][-2:]
    assert quenching["kind"] == "two_body"
    assert quenching["source_state"] == "Ar_2p1"
    assert quenching["colliders"] == ["O2"]
    assert loss["kind"] == "first_order"
    assert loss["coefficient_s-1"] == 4.0e3


def test_unimplemented_trapping_geometry_is_rejected() -> None:
    transition = {
        "A_s-1": 1.0e7,
        "trapping": {"kind": "escape_factor", "shape": "cylinder", "tau0": 1.0},
    }

    with pytest.raises(ValueError, match="not one of"):
        effective_A(transition)


def test_species_pack_adds_namespaced_state_and_provenance(tmp_path: Path) -> None:
    pack_path = tmp_path / "test_species.yaml"
    pack_path.write_text(
        "\n".join(
            [
                "kind: oescr_species_pack",
                "namespace: ignored_by_entry_override",
                "metadata:",
                "  source: unit-test",
                "states:",
                "  - id: X_excited",
                "    species: X",
                "    energy_eV: 1.0",
                "    solve: false",
            ]
        ),
        encoding="utf-8",
    )
    cfg = load_yaml(ROOT / "examples" / "case_init_cf4_o2_ar.yaml")
    cfg.setdefault("species_packs", []).append(
        {"yaml_file": str(pack_path), "namespace": "test"}
    )

    result = OESCRModel(cfg).predict()

    assert "test:X_excited" in result.state_registry.states
    added_pack = next(
        pack for pack in result.provenance["species_packs"] if pack["namespace"] == "test"
    )
    assert added_pack["metadata"]["source"] == "unit-test"


def test_multigas_example_composes_namespaced_packs_and_rebases_data_paths() -> None:
    model = OESCRModel.from_yaml(ROOT / "examples" / "case_truth_cf4_o2_ar.yaml")

    result = model.predict()
    oxygen_pack = next(
        pack for pack in result.provenance["species_packs"] if pack["namespace"] == "oxygen"
    )
    excitation = next(
        reaction
        for reaction in model.cfg["reactions"]
        if reaction["id"] == "oxygen:exc_O_to_3p5P"
    )

    assert "oxygen:O_3p5P" in result.state_registry.states
    assert "O_3p5P" not in result.state_registry.states
    assert excitation["source_state"] == "O"
    assert excitation["target_state"] == "oxygen:O_3p5P"
    assert Path(excitation["cross_section_file"]).is_file()
    assert oxygen_pack["metadata"]["evidence"].startswith("Illustrative")
    assert len(result.provenance["species_packs"]) == 2


def test_species_pack_rejects_duplicate_ids() -> None:
    cfg = load_yaml(ROOT / "examples" / "case_init_cf4_o2_ar.yaml")
    cfg.setdefault("species_packs", []).append(
        {
            "kind": "oescr_species_pack",
            "states": [{"id": "Ar_2p1", "species": "Ar", "energy_eV": 13.48, "solve": True}],
        }
    )

    with pytest.raises(SpeciesPackError, match="Duplicate states id"):
        OESCRModel(cfg)


def test_nonuniform_instrument_grid_uses_local_bin_widths() -> None:
    instrument = InstrumentSpec(
        {
            "id": "nonuniform",
            "wavelength_grid_nm": [500.0, 501.0, 503.0],
            "throughput": 1.0,
            "lsf": {"kind": "gaussian", "fwhm_nm": 0.01},
            "baseline": {"kind": "constant", "offset": 0.0},
        }
    )
    fine_wavelength = np.linspace(494.0, 509.0, 15001)

    observed = instrument.observe(fine_wavelength, np.ones_like(fine_wavelength))

    assert np.allclose(observed["intensity"], 1.0, rtol=2.0e-3, atol=2.0e-3)


def test_wall_loss_requires_mass_and_applies_explicit_flux_factor() -> None:
    with pytest.raises(ValueError, match="requires state mass_amu"):
        thermal_speed_m_s(None, 300.0)

    common = {
        "geometry_cfg": {"chamber_radius_m": 0.1, "chamber_height_m": 0.1},
        "gas_temperature_K": 300.0,
        "state_id": "Ar_meta",
        "species": "Ar",
        "mass_amu": 39.948,
    }
    full = effective_wall_loss_rate_s(
        wall_cfg={"model": "gamma_thermal", "gamma_default": 0.1, "thermal_flux_factor": 1.0},
        **common,
    )
    quarter = effective_wall_loss_rate_s(
        wall_cfg={"model": "gamma_thermal", "gamma_default": 0.1, "thermal_flux_factor": 0.25},
        **common,
    )

    assert np.isclose(quarter, 0.25 * full)
