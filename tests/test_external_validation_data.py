from __future__ import annotations

import csv
import json
from math import isclose
from pathlib import Path

import numpy as np
from scripts.assess_arellano_atomic_model import (
    _cascade_anchor_sensitivity,
    _eedf_at_mean_energy,
    _quenching_sensitivity,
    _rate_from_curve,
)

from oescr.data.cross_section_db import CrossSection, CrossSectionLibrary
from oescr.data.lxcat import load_lxcat_cross_section
from oescr.data.provenance import file_sha256
from oescr.io.normalize import normalize_case_config
from oescr.io.yaml_loader import load_yaml
from oescr.physics.eedf import druyvesteyn_energy_pdf, maxwell_energy_pdf
from oescr.physics.rates import RateCalculator

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "examples" / "validation" / "schuecke_2025_no_uv"
AR_CANDIDATE = ROOT / "examples" / "validation" / "arellano_2023_ar_ccp"


def test_schuecke_candidate_is_immutable_but_not_a_validation_claim() -> None:
    metadata = load_yaml(CANDIDATE / "source.yaml")
    data_file = CANDIDATE / metadata["artifact"]["file"]

    assert file_sha256(data_file) == metadata["artifact"]["sha256"]
    assert metadata["status"] == "dataset_prepared_comparator_pending"
    assert metadata["measurement_basis"] == "volumetric_photon_rate"
    assert metadata["comparison"]["model_input_closure"] == "open"
    assert metadata["held_out"] is True
    assert not (CANDIDATE / "validation.yaml").exists()

    with data_file.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))

    assert len(rows) == 14
    assert [float(row["rf_power_W"]) for row in rows] == sorted(float(row["rf_power_W"]) for row in rows)
    assert {row["pressure_Pa"] for row in rows} == {"10"}
    assert {row["regime_partition"] for row in rows} == {"E", "transition", "H"}


def test_arellano_candidate_is_immutable_but_not_a_validation_claim() -> None:
    metadata = load_yaml(AR_CANDIDATE / "source.yaml")
    data_file = AR_CANDIDATE / metadata["artifact"]["file"]

    assert file_sha256(data_file) == metadata["artifact"]["sha256"]
    assert metadata["status"] == "dataset_prepared_model_closure_pending"
    assert metadata["measurement_basis"] == "relative_intensity"
    assert metadata["calibration"] == "relative_response_corrected"
    assert metadata["comparison"] == {
        "model_input_closure": "conditional",
        "evaluation_data_use": "held_out_only",
    }
    assert metadata["held_out"] is True
    assert not (AR_CANDIDATE / "validation.yaml").exists()

    with data_file.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))

    pressures = [float(row["pressure_Pa"]) for row in rows]
    ratios = [float(row["I_763p5_over_I_750p4"]) for row in rows]
    assert pressures == [2, 4, 7, 10, 15, 20, 30, 40, 50, 60, 80, 100]
    assert all(ratio > 0.0 for ratio in ratios)
    assert max(ratios[:4]) - min(ratios[:4]) < 0.12
    assert ratios[-1] > 5.0


def test_arellano_lines_map_to_the_correct_argon_levels() -> None:
    case = normalize_case_config(load_yaml(ROOT / "examples" / "case_skeleton_nf3_ar.yaml"))
    states = {state["id"]: state for state in case["states"]}
    transitions = {transition["id"]: transition for transition in case["transitions"]}

    assert "Ar_2p2" not in states
    assert states["Ar_2p6"]["energy_eV"] == 13.171778
    assert transitions["Ar750"]["upper"] == "Ar_2p1"
    assert transitions["Ar763"]["upper"] == "Ar_2p6"
    assert transitions["Ar763"]["lower"] == "Ar_1s5"
    assert transitions["Ar763"]["A_s-1"] == 2.44e7


def test_arellano_argon_pack_has_complete_branching_for_selected_levels() -> None:
    case = normalize_case_config(load_yaml(ROOT / "examples" / "case_skeleton_nf3_ar.yaml"))
    transitions = case["transitions"]
    by_upper = {
        upper: [transition for transition in transitions if transition["upper"] == upper]
        for upper in ("Ar_2p1", "Ar_2p6")
    }

    assert {line["id"] for line in by_upper["Ar_2p1"]} == {"Ar667", "Ar750"}
    assert {line["id"] for line in by_upper["Ar_2p6"]} == {"Ar763", "Ar800", "Ar922"}

    total_2p1 = sum(float(line["A_s-1"]) for line in by_upper["Ar_2p1"])
    total_2p6 = sum(float(line["A_s-1"]) for line in by_upper["Ar_2p6"])
    assert total_2p1 == 4.5236e7
    assert total_2p6 == 3.42e7
    assert isclose(2.44e7 / total_2p6, 0.7134502923976608)
    assert isclose(4.5e7 / total_2p1, 0.994782916261385)


def test_chilton_cross_section_anchors_are_immutable_and_si() -> None:
    metadata = load_yaml(AR_CANDIDATE / "source.yaml")
    anchor = metadata["cross_section_reference"]["artifact"]
    data_file = AR_CANDIDATE / anchor["file"]

    assert file_sha256(data_file) == anchor["sha256"]
    with data_file.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))

    assert [float(row["energy_eV"]) for row in rows] == [20.0, 40.0, 100.0]
    assert [float(row["sigma_2p1_m2"]) for row in rows] == [5.0e-22, 3.1e-22, 2.5e-22]
    assert [float(row["sigma_2p6_m2"]) for row in rows] == [3.2e-22, 1.9e-22, 1.0e-22]


def test_chilton_cascade_anchor_is_immutable_and_condition_specific() -> None:
    metadata = load_yaml(AR_CANDIDATE / "source.yaml")
    reference = metadata["cascade_anchor_reference"]
    artifact = reference["artifact"]
    data_file = AR_CANDIDATE / artifact["file"]

    assert file_sha256(data_file) == artifact["sha256"]
    assert reference["electron_energy_eV"] == 40.0
    assert reference["gas_pressure_mTorr"] == 1.0
    assert "not an EEDF-integrated" in reference["scope"]
    with data_file.open(newline="", encoding="utf-8") as stream:
        rows = {row["upper_level"]: row for row in csv.DictReader(stream)}

    assert float(rows["2p1"]["cascade_sigma_m2"]) == 6.3e-23
    assert float(rows["2p6"]["cascade_sigma_m2"]) == 2.0e-22


def test_lxcat_model_references_require_user_download_and_fix_numeric_identity() -> None:
    metadata = load_yaml(AR_CANDIDATE / "source.yaml")
    references = {item["model_id"]: item for item in metadata["cross_section_models"]}

    assert set(references) == {"bsr_500", "ngfsrdw_1998"}
    assert metadata["lxcat_data_handling"]["packaged_with_repository"] is False
    assert "demo.lxcat.net" not in str(references)
    assert all(
        reference["transformation"].endswith("without smoothing or amplitude tuning")
        for reference in references.values()
    )

    expected = {
        "bsr_500": {
            "2p1": (
                62286,
                13.594,
                196,
                "19e01a7e7b97ff819de48de2e499e5103f4d17644a951f2e530709b058dee811",
            ),
            "2p6": (
                62281,
                13.299,
                218,
                "8933a7de6b40ef12fe9117398c7bd4845752d19c2a95b4a23f0df62f4be1b89e",
            ),
        },
        "ngfsrdw_1998": {
            "2p1": (
                2560,
                13.48,
                17,
                "124f52f146c92a81ec42cd5c6afd61d7a2c3e0cf6fb5aeee971dd2c5d8f8a147",
            ),
            "2p6": (
                2567,
                13.172,
                17,
                "a9a02490576b72b391f9b476b9dec5275a04b891d0c26720095417faeffd90ad",
            ),
        },
    }
    for model_id, expected_artifacts in expected.items():
        artifacts = {item["upper_level"]: item for item in references[model_id]["artifacts"]}
        for level, (process_id, threshold_eV, row_count, digest) in expected_artifacts.items():
            artifact = artifacts[level]
            assert artifact["production_process_id"] == process_id
            assert artifact["native_threshold_eV"] == threshold_eV
            assert artifact["row_count"] == row_count
            assert artifact["curve_data_sha256"] == digest

    assert not list(AR_CANDIDATE.glob("bsr_2014_ground_to_4p_*.csv"))
    assert not list(AR_CANDIDATE.glob("ngfsrdw_1998_ground_to_4p_*.csv"))


def test_lxcat_parser_and_mean_energy_matching_are_explicit(tmp_path: Path) -> None:
    source = tmp_path / "Cross section.txt"
    source.write_text(
        "\n".join(
            [
                "DATABASE: unit fixture",
                "EXCITATION",
                "Ar -> Ar(test)",
                " 1.0",
                "PROCESS: E + Ar -> E + Ar(test), Excitation",
                "COLUMNS: Energy (eV) | Cross section (m2)",
                "-----------------------------",
                " 1.0 0.0",
                " 2.0 3.0e-20",
                "-----------------------------",
            ]
        ),
        encoding="utf-8",
    )
    curve = load_lxcat_cross_section(source, "Ar -> Ar(test)")
    assert curve.energy_eV.tolist() == [1.0, 2.0]
    assert curve.sigma_m2.tolist() == [0.0, 3.0e-20]

    grid = np.linspace(0.0, 100.0, 10001)
    for builder in (maxwell_energy_pdf, druyvesteyn_energy_pdf):
        _, _, actual_mean = _eedf_at_mean_energy(builder, grid, 6.0)
        assert isclose(actual_mean, 6.0, rel_tol=1.0e-12)


def test_candidate_rate_integration_zeros_cross_section_below_declared_threshold() -> None:
    grid = np.asarray([0.0, 0.5, 1.0, 1.5])
    rate_calculator = RateCalculator(grid, CrossSectionLibrary())
    curve = CrossSection(
        energy_eV=np.asarray([0.1, 1.5]),
        sigma_m2=np.asarray([1.0, 1.0]),
        path="unit-test",
        sha256="unit-test",
        metadata={},
    )
    eedf_below_threshold = np.asarray([0.0, 1.0, 0.0, 0.0])

    rate = _rate_from_curve(
        rate_calculator,
        curve,
        eedf_below_threshold,
        native_threshold_eV=1.0,
        energy_shift_eV=0.0,
    )

    assert rate == 0.0


def test_arellano_atomic_assessment_is_auditable_but_not_a_verdict() -> None:
    metadata = load_yaml(AR_CANDIDATE / "source.yaml")
    artifact = metadata["atomic_model_assessment"]["artifact"]
    result_path = AR_CANDIDATE / artifact["file"]

    assert file_sha256(result_path) == artifact["sha256"]
    stored = json.loads(result_path.read_text(encoding="utf-8"))
    assert stored["status"] == "diagnostic_only_not_validation"
    assert stored["model"]["amplitude_tuned_to_observation"] is False
    assert stored["cascade_anchor_sensitivity"] == _cascade_anchor_sensitivity(AR_CANDIDATE, metadata)
    assert stored["quenching_sensitivity"] == _quenching_sensitivity(AR_CANDIDATE, metadata)
    assert stored["cross_section_inputs"] == {
        reference["model_id"]: {
            item["upper_level"]: {
                "production_process_id": item["production_process_id"],
                "curve_data_sha256": item["curve_data_sha256"],
                "row_count": item["row_count"],
            }
            for item in reference["artifacts"]
        }
        for reference in metadata["cross_section_models"]
    }

    observed = stored["observed_low_pressure_ratio_range"]
    ratios = [
        row["I_763p5_over_I_750p4"]
        for row in stored["prediction_sensitivity"]
        if row["cross_section_model"] == "bsr_500"
        and row["eedf_family"] == "maxwellian"
        and row["threshold_basis"] == "native_model"
    ]
    assert ratios[0] > observed["maximum"]
    assert all(observed["minimum"] <= ratio <= observed["maximum"] for ratio in ratios[1:])
    assert stored["sensitivity_envelope"]["overlaps_observed_low_pressure_range"] is True

    anchor_ratios = [row["2p1"]["model_over_chilton"]["bsr_500"] for row in stored["anchor_comparison"]]
    assert anchor_ratios == [0.37216895680000006, 0.5692991634838709, 0.6247680000000001]
    discrepancy = stored["model_discrepancy_summary"]
    assert discrepancy["condition_count"] == 24
    assert isclose(discrepancy["minimum_maximum_over_minimum_ratio"], 3.677898278190413)
    assert isclose(discrepancy["maximum_maximum_over_minimum_ratio"], 5.09033647869887)

    cascade = stored["cascade_anchor_sensitivity"]
    assert cascade["applied_to_eedf_predictions"] is False
    assert isclose(cascade["line_ratio_multiplier_nominal"], 1.5866439190835975)
    assert cascade["reported_uncertainty_corner_envelope"] == {
        "maximum": 2.3529411764705888,
        "minimum": 1.1671087533156497,
        "probability_interpretation": False,
    }

    quenching = stored["quenching_sensitivity"]
    assert quenching["rate_coefficients_m3_s"] == {"2p1": 1.6e-17, "2p6": 1.3e-17}
    assert isclose(quenching["low_pressure_maximum_absolute_ratio_shift"], 6.288152652444978e-05)
    assert isclose(quenching["full_pressure_maximum_absolute_ratio_shift"], 0.0006237358878553589)
