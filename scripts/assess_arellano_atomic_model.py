#!/usr/bin/env python
"""Reproduce the diagnostic-only Ar 763.5/750.4 nm atomic-input assessment."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oescr.data.cross_section_db import CrossSection, CrossSectionLibrary
from oescr.data.provenance import file_sha256
from oescr.io.yaml_loader import load_yaml
from oescr.physics.eedf import druyvesteyn_energy_pdf, maxwell_energy_pdf
from oescr.physics.rates import RateCalculator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE = ROOT / "examples" / "validation" / "arellano_2023_ar_ccp"
BOLTZMANN_CONSTANT_J_K = 1.380649e-23


def _artifact_path(candidate_dir: Path, value: object) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else candidate_dir / path


def _curve_data_sha256(energy_eV: np.ndarray, sigma_m2: np.ndarray) -> str:
    """Hash numeric curve content independently of the LXCat text envelope."""

    values = np.column_stack((energy_eV, sigma_m2)).astype("<f8", copy=False)
    return hashlib.sha256(values.tobytes(order="C")).hexdigest()


def _lxcat_table_start(lines: list[str], process_label: str) -> int:
    try:
        label_index = lines.index(process_label)
    except ValueError as exc:
        raise ValueError(f"LXCat download does not contain process '{process_label}'.") from exc

    table_start = next(
        (index for index in range(label_index + 1, len(lines)) if lines[index].startswith("-----")),
        None,
    )
    if table_start is None:
        raise ValueError(f"LXCat process '{process_label}' has no numeric table.")
    return table_start


def _lxcat_numeric_rows(lines: list[str], process_label: str) -> tuple[np.ndarray, np.ndarray]:
    numeric_rows = [line.split() for line in lines if len(line.split()) == 2]
    if len(numeric_rows) < 2:
        raise ValueError(f"LXCat process '{process_label}' has fewer than two data rows.")
    values = np.asarray(numeric_rows, dtype=float)
    return values[:, 0], values[:, 1]


def _parse_lxcat_curve(lines: list[str], process_label: str, source: Path) -> CrossSection:
    table_start = _lxcat_table_start(lines, process_label)
    table_end = next(
        (index for index in range(table_start + 1, len(lines)) if lines[index].startswith("-----")),
        len(lines),
    )
    energy_array, sigma_array = _lxcat_numeric_rows(lines[table_start + 1 : table_end], process_label)

    if np.any(np.diff(energy_array) <= 0.0) or np.any(sigma_array < 0.0):
        raise ValueError(f"LXCat process '{process_label}' has invalid numeric data.")
    digest = _curve_data_sha256(energy_array, sigma_array)
    return CrossSection(
        energy_eV=energy_array,
        sigma_m2=sigma_array,
        path=f"{source.resolve()}#{process_label}",
        sha256=digest,
        metadata={"curve_data_sha256": digest, "process_label": process_label},
    )


def _load_verified_lxcat_cross_sections(
    download_path: Path,
    reference: Mapping[str, Any],
) -> dict[str, CrossSection]:
    model_id = str(reference["model_id"])
    if not download_path.is_file():
        raise FileNotFoundError(
            f"Download the selected {model_id} processes from www.lxcat.net and pass "
            f"the resulting 'Cross section.txt': {download_path}"
        )
    lines = download_path.read_text(encoding="utf-8").splitlines()
    curves: dict[str, CrossSection] = {}
    artifacts = {str(item["upper_level"]): item for item in reference["artifacts"]}
    for level, artifact in artifacts.items():
        curve = _parse_lxcat_curve(lines, str(artifact["process_label"]), download_path)
        expected_rows = int(artifact["row_count"])
        if len(curve.energy_eV) != expected_rows:
            raise ValueError(
                f"LXCat {model_id}/{level} row-count mismatch: expected {expected_rows}, got {len(curve.energy_eV)}."
            )
        expected_digest = str(artifact["curve_data_sha256"])
        if curve.sha256 != expected_digest:
            raise ValueError(
                f"LXCat {model_id}/{level} numeric digest mismatch: expected {expected_digest}, got {curve.sha256}."
            )
        curves[level] = curve
    return curves


def _branch_fraction(level: Mapping[str, Any], wavelength_nm: float) -> float:
    branches = level["radiative_branches"]
    selected = [
        float(branch["A_s-1"]) for branch in branches if abs(float(branch["wavelength_nm"]) - wavelength_nm) < 0.1
    ]
    if len(selected) != 1:
        raise ValueError(f"Expected one radiative branch near {wavelength_nm} nm.")
    return selected[0] / sum(float(branch["A_s-1"]) for branch in branches)


def _load_anchor_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _eedf_at_mean_energy(
    builder: Callable[[np.ndarray, float], np.ndarray],
    energy_eV: np.ndarray,
    target_mean_eV: float,
) -> tuple[np.ndarray, float, float]:
    """Match EEDF families at mean energy so shape is the varied quantity."""

    lower = max(target_mean_eV / 20.0, 1.0e-6)
    upper = target_mean_eV * 20.0
    for _ in range(80):
        scale = 0.5 * (lower + upper)
        pdf = builder(energy_eV, scale)
        mean = float(np.trapezoid(energy_eV * pdf, energy_eV))
        if mean < target_mean_eV:
            lower = scale
        else:
            upper = scale
    scale = 0.5 * (lower + upper)
    pdf = builder(energy_eV, scale)
    mean = float(np.trapezoid(energy_eV * pdf, energy_eV))
    return pdf, scale, mean


def _rate_from_curve(
    rate_calculator: RateCalculator,
    curve: CrossSection,
    eedf: np.ndarray,
    native_threshold_eV: float,
    energy_shift_eV: float,
) -> float:
    shifted_energy = curve.energy_eV + energy_shift_eV
    sigma = np.interp(
        rate_calculator.energy_eV,
        shifted_energy,
        curve.sigma_m2,
        left=0.0,
        right=0.0,
    )
    sigma[rate_calculator.energy_eV < native_threshold_eV + energy_shift_eV] = 0.0
    integrand = sigma * rate_calculator.electron_velocity_m_s * eedf
    return float(np.trapezoid(integrand, rate_calculator.energy_eV))


def _compare_anchors(
    anchor_rows: list[dict[str, str]],
    model_curves: Mapping[str, Mapping[str, CrossSection]],
) -> list[dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []
    for row in anchor_rows:
        energy_eV = float(row["energy_eV"])
        record: dict[str, Any] = {"energy_eV": energy_eV}
        for level in ("2p1", "2p6"):
            measured = float(row[f"sigma_{level}_m2"])
            predictions = {
                model_id: float(np.interp(energy_eV, curves[level].energy_eV, curves[level].sigma_m2))
                for model_id, curves in model_curves.items()
            }
            record[level] = {
                "chilton_sigma_m2": measured,
                "model_sigma_m2": predictions,
                "model_over_chilton": {model_id: predicted / measured for model_id, predicted in predictions.items()},
            }
        comparisons.append(record)
    return comparisons


def _prediction_sensitivity(
    protocol: Mapping[str, Any],
    metadata: Mapping[str, Any],
    references: Mapping[str, Mapping[str, Any]],
    model_curves: Mapping[str, Mapping[str, CrossSection]],
    branch_2p1: float,
    branch_2p6: float,
) -> tuple[list[dict[str, Any]], list[float]]:
    grid = protocol["energy_grid"]
    energy_eV = np.linspace(
        float(grid["min_eV"]),
        float(grid["max_eV"]),
        int(grid["n_points"]),
    )
    rate_calculator = RateCalculator(energy_eV, CrossSectionLibrary())
    eedf_builders = {
        "maxwellian": maxwell_energy_pdf,
        "druyvesteyn": druyvesteyn_energy_pdf,
    }
    artifacts = {
        model_id: {str(item["upper_level"]): item for item in reference["artifacts"]}
        for model_id, reference in references.items()
    }

    predictions: list[dict[str, Any]] = []
    discrepancy_factors: list[float] = []
    for target_mean_eV in protocol["mean_energy_eV"]:
        for family in protocol["eedf_families"]:
            eedf, shape_scale_eV, actual_mean_eV = _eedf_at_mean_energy(
                eedf_builders[str(family)],
                energy_eV,
                float(target_mean_eV),
            )
            for threshold_basis in protocol["threshold_bases"]:
                ratio_by_model: dict[str, float] = {}
                for model_id, curves in model_curves.items():
                    rates: dict[str, float] = {}
                    shifts: dict[str, float] = {}
                    for level in ("2p1", "2p6"):
                        native_threshold = float(artifacts[model_id][level]["native_threshold_eV"])
                        nist_threshold = float(metadata["atomic_reference"][f"level_{level}"]["energy_eV"])
                        shift = 0.0 if threshold_basis == "native_model" else nist_threshold - native_threshold
                        shifts[level] = shift
                        rates[level] = _rate_from_curve(
                            rate_calculator,
                            curves[level],
                            eedf,
                            native_threshold,
                            shift,
                        )
                    ratio = rates["2p6"] * branch_2p6 / (rates["2p1"] * branch_2p1)
                    ratio_by_model[model_id] = ratio
                    predictions.append(
                        {
                            "cross_section_model": model_id,
                            "mean_energy_eV": actual_mean_eV,
                            "eedf_family": family,
                            "shape_scale_eV": shape_scale_eV,
                            "threshold_basis": threshold_basis,
                            "energy_shift_eV": shifts,
                            "rate_2p1_m3_s": rates["2p1"],
                            "rate_2p6_m3_s": rates["2p6"],
                            "I_763p5_over_I_750p4": ratio,
                        }
                    )
                ratios = list(ratio_by_model.values())
                discrepancy_factors.append(max(ratios) / min(ratios))
    return predictions, discrepancy_factors


def _load_model_inputs(
    metadata: Mapping[str, Any], download_paths: Mapping[str, Path]
) -> tuple[dict[str, Mapping[str, Any]], dict[str, dict[str, CrossSection]]]:
    references = {str(item["model_id"]): item for item in metadata["cross_section_models"]}
    missing_downloads = sorted(set(references) - set(download_paths))
    if missing_downloads:
        raise ValueError(f"Missing LXCat downloads for models: {', '.join(missing_downloads)}")
    curves = {
        model_id: _load_verified_lxcat_cross_sections(download_paths[model_id], reference)
        for model_id, reference in references.items()
    }
    return references, curves


def _load_verified_reference_rows(
    candidate_dir: Path,
    metadata: Mapping[str, Any],
    reference_key: str,
) -> list[dict[str, str]]:
    anchor_meta = metadata[reference_key]["artifact"]
    anchor_path = _artifact_path(candidate_dir, anchor_meta["file"])
    if file_sha256(anchor_path) != str(anchor_meta["sha256"]):
        raise ValueError(f"Reference-artifact hash mismatch: {anchor_path}")
    return _load_anchor_rows(anchor_path)


def _cascade_anchor_sensitivity(candidate_dir: Path, metadata: Mapping[str, Any]) -> dict[str, Any]:
    reference = metadata["cascade_anchor_reference"]
    rows = {
        row["upper_level"]: row
        for row in _load_verified_reference_rows(candidate_dir, metadata, "cascade_anchor_reference")
    }

    def source_factor(level: str, direct_sign: float = 0.0, cascade_sign: float = 0.0) -> float:
        row = rows[level]
        direct = float(row["direct_sigma_m2"]) + direct_sign * float(row["direct_uncertainty_m2"])
        cascade = float(row["cascade_sigma_m2"]) + cascade_sign * float(row["cascade_uncertainty_m2"])
        if direct <= 0.0 or cascade < 0.0:
            raise ValueError(f"Invalid cascade anchor uncertainty interval for {level}.")
        return 1.0 + cascade / direct

    nominal_by_level = {level: source_factor(level) for level in ("2p1", "2p6")}
    minimum_multiplier = source_factor("2p6", 1.0, -1.0) / source_factor("2p1", -1.0, 1.0)
    maximum_multiplier = source_factor("2p6", -1.0, 1.0) / source_factor("2p1", 1.0, -1.0)
    return {
        "source_condition": {
            "electron_energy_eV": float(reference["electron_energy_eV"]),
            "gas_pressure_mTorr": float(reference["gas_pressure_mTorr"]),
        },
        "source_population_multiplier_by_level": nominal_by_level,
        "line_ratio_multiplier_nominal": nominal_by_level["2p6"] / nominal_by_level["2p1"],
        "reported_uncertainty_corner_envelope": {
            "minimum": minimum_multiplier,
            "maximum": maximum_multiplier,
            "probability_interpretation": False,
        },
        "applied_to_eedf_predictions": False,
        "reason": (
            "The monoenergetic 1 mTorr cascade fractions are pressure dependent and do not define "
            "an EEDF-integrated cascade source for the 2-100 Pa discharge."
        ),
    }


def _radiative_rates(metadata: Mapping[str, Any]) -> dict[str, float]:
    return {
        level: sum(
            float(branch["A_s-1"]) for branch in metadata["atomic_reference"][f"level_{level}"]["radiative_branches"]
        )
        for level in ("2p1", "2p6")
    }


def _quenching_state(
    pressure_Pa: float,
    gas_temperature_K: float,
    radiative_rates: Mapping[str, float],
    rate_coefficients: Mapping[str, float],
) -> dict[str, Any]:
    gas_density = pressure_Pa / (BOLTZMANN_CONSTANT_J_K * gas_temperature_K)
    survival = {
        level: radiative_rates[level] / (radiative_rates[level] + rate_coefficients[level] * gas_density)
        for level in ("2p1", "2p6")
    }
    return {
        "gas_temperature_K": gas_temperature_K,
        "gas_density_m3": gas_density,
        "radiative_survival": survival,
        "line_ratio_multiplier": survival["2p6"] / survival["2p1"],
    }


def _quenching_pressure_row(
    pressure_Pa: float,
    temperatures_K: tuple[float, float],
    radiative_rates: Mapping[str, float],
    rate_coefficients: Mapping[str, float],
) -> dict[str, Any]:
    return {
        "pressure_Pa": pressure_Pa,
        "temperature_endpoints": [
            _quenching_state(pressure_Pa, temperature, radiative_rates, rate_coefficients)
            for temperature in temperatures_K
        ],
    }


def _quenching_multipliers(rows: list[dict[str, Any]], maximum_pressure_Pa: float) -> list[float]:
    return [
        float(state["line_ratio_multiplier"])
        for row in rows
        if float(row["pressure_Pa"]) <= maximum_pressure_Pa
        for state in row["temperature_endpoints"]
    ]


def _quenching_sensitivity(candidate_dir: Path, metadata: Mapping[str, Any]) -> dict[str, Any]:
    quenching = metadata["collisional_quenching_reference"]
    rate_coefficients = {key: float(value) for key, value in quenching["rate_coefficients_m3_s"].items()}
    radiative_rates = _radiative_rates(metadata)
    minimum_temperature, maximum_temperature = (
        float(value) for value in metadata["operating_condition"]["gas_temperature_range_K"]
    )
    observation_path = _artifact_path(candidate_dir, metadata["artifact"]["file"])
    pressures = [float(row["pressure_Pa"]) for row in _load_anchor_rows(observation_path)]

    temperatures = (minimum_temperature, maximum_temperature)
    rows = [
        _quenching_pressure_row(pressure, temperatures, radiative_rates, rate_coefficients) for pressure in pressures
    ]

    pressure_limit = float(metadata["observable"]["low_pressure_atomic_check_max_Pa"])
    low_pressure_multipliers = _quenching_multipliers(rows, pressure_limit)
    all_multipliers = _quenching_multipliers(rows, float("inf"))
    return {
        "model": "state-specific neutral-Ar loss added to optically thin radiative loss",
        "rate_coefficients_m3_s": rate_coefficients,
        "radiative_rates_s-1": radiative_rates,
        "pressure_temperature_sweep": rows,
        "low_pressure_maximum_absolute_ratio_shift": max(abs(value - 1.0) for value in low_pressure_multipliers),
        "full_pressure_maximum_absolute_ratio_shift": max(abs(value - 1.0) for value in all_multipliers),
        "coupled_cr_feedback_included": False,
    }


def _low_pressure_ratio_range(candidate_dir: Path, metadata: Mapping[str, Any]) -> tuple[float, float, float]:
    observation_path = _artifact_path(candidate_dir, metadata["artifact"]["file"])
    pressure_limit = float(metadata["observable"]["low_pressure_atomic_check_max_Pa"])
    ratios = [
        float(row["I_763p5_over_I_750p4"])
        for row in _load_anchor_rows(observation_path)
        if float(row["pressure_Pa"]) <= pressure_limit
    ]
    return pressure_limit, min(ratios), max(ratios)


def _cross_section_input_summary(
    references: Mapping[str, Mapping[str, Any]],
    model_curves: Mapping[str, Mapping[str, CrossSection]],
) -> dict[str, Any]:
    return {
        model_id: {
            str(artifact["upper_level"]): {
                "production_process_id": int(artifact["production_process_id"]),
                "curve_data_sha256": model_curves[model_id][str(artifact["upper_level"])].sha256,
                "row_count": len(model_curves[model_id][str(artifact["upper_level"])].energy_eV),
            }
            for artifact in reference["artifacts"]
        }
        for model_id, reference in references.items()
    }


def _model_envelopes(
    sensitivity: list[dict[str, Any]], references: Mapping[str, Mapping[str, Any]]
) -> dict[str, dict[str, float]]:
    envelopes: dict[str, dict[str, float]] = {}
    for model_id in references:
        ratios = [float(row["I_763p5_over_I_750p4"]) for row in sensitivity if row["cross_section_model"] == model_id]
        envelopes[model_id] = {
            "minimum_ratio": min(ratios),
            "maximum_ratio": max(ratios),
        }
    return envelopes


def assess(candidate_dir: Path, download_paths: Mapping[str, Path]) -> dict[str, Any]:
    """Return a no-fit sensitivity assessment; this does not issue a validation verdict."""

    candidate_dir = candidate_dir.resolve()
    metadata = load_yaml(candidate_dir / "source.yaml")
    references, model_curves = _load_model_inputs(metadata, download_paths)
    anchor_comparison = _compare_anchors(
        _load_verified_reference_rows(candidate_dir, metadata, "cross_section_reference"),
        model_curves,
    )

    protocol = metadata["atomic_model_assessment"]
    branch_2p1 = _branch_fraction(
        metadata["atomic_reference"]["level_2p1"],
        float(metadata["observable"]["denominator_wavelength_nm"]),
    )
    branch_2p6 = _branch_fraction(
        metadata["atomic_reference"]["level_2p6"],
        float(metadata["observable"]["numerator_wavelength_nm"]),
    )
    sensitivity, discrepancy_factors = _prediction_sensitivity(
        protocol,
        metadata,
        references,
        model_curves,
        branch_2p1,
        branch_2p6,
    )

    pressure_limit, observed_minimum, observed_maximum = _low_pressure_ratio_range(candidate_dir, metadata)

    predicted_ratios = [float(row["I_763p5_over_I_750p4"]) for row in sensitivity]
    model_envelopes = _model_envelopes(sensitivity, references)
    return {
        "status": "diagnostic_only_not_validation",
        "model": {
            "population_limit": "direct_ground_state_corona",
            "eedf": "mean-energy-matched Maxwellian and Druyvesteyn families",
            "cross_sections": "independent LXCat BSR-500 and NGFSRDW curves verified by numeric digest",
            "cross_section_interpolation": "linear in energy, zero outside support and below declared threshold",
            "radiative_branching": "NIST all-branch fractions",
            "amplitude_tuned_to_observation": False,
        },
        "cross_section_inputs": _cross_section_input_summary(references, model_curves),
        "branch_fractions": {"2p1_to_750p4": branch_2p1, "2p6_to_763p5": branch_2p6},
        "observed_low_pressure_ratio_range": {
            "max_pressure_Pa": pressure_limit,
            "minimum": observed_minimum,
            "maximum": observed_maximum,
        },
        "anchor_comparison": anchor_comparison,
        "cascade_anchor_sensitivity": _cascade_anchor_sensitivity(candidate_dir, metadata),
        "quenching_sensitivity": _quenching_sensitivity(candidate_dir, metadata),
        "prediction_sensitivity": sensitivity,
        "model_discrepancy_summary": {
            "condition_count": len(discrepancy_factors),
            "minimum_maximum_over_minimum_ratio": min(discrepancy_factors),
            "maximum_maximum_over_minimum_ratio": max(discrepancy_factors),
        },
        "sensitivity_envelope": {
            "minimum_ratio": min(predicted_ratios),
            "maximum_ratio": max(predicted_ratios),
            "by_cross_section_model": model_envelopes,
            "overlaps_observed_low_pressure_range": not (
                max(predicted_ratios) < observed_minimum or min(predicted_ratios) > observed_maximum
            ),
        },
        "limitations": [
            "Neither LXCat model source supplies curve uncertainty.",
            "The sparse NGFSRDW curve requires linear interpolation and is not a near-threshold benchmark.",
            "The experiment does not independently supply the EEDF used in this sensitivity sweep.",
            "Maxwellian and Druyvesteyn families bound shape sensitivity only within the declared family set.",
            "The cascade anchor is monoenergetic and pressure specific, so it is not applied to the EEDF-integrated predictions.",
            "Quenching is isolated as a post-source corona loss; coupled stepwise excitation and radiation trapping are omitted.",
            "No pass/fail tolerance is declared because experimental and model-discrepancy uncertainty are open.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument(
        "--bsr-download",
        type=Path,
        required=True,
        help="User-downloaded LXCat 'Cross section.txt' containing production processes 62281/62286.",
    )
    parser.add_argument(
        "--ngfsrdw-download",
        type=Path,
        required=True,
        help="User-downloaded LXCat 'Cross section.txt' containing production processes 2560/2567.",
    )
    parser.add_argument("--output", type=Path, help="Write JSON to this path instead of stdout.")
    args = parser.parse_args()

    rendered = (
        json.dumps(
            assess(
                args.candidate_dir,
                {"bsr_500": args.bsr_download, "ngfsrdw_1998": args.ngfsrdw_download},
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.write_bytes(rendered.encode("utf-8"))


if __name__ == "__main__":
    main()
