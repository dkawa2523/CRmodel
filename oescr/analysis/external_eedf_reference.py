"""Compare OESCR rate integrals with immutable external EEDF references.

The external solver is intentionally not launched here.  It produces an EEDF
and process-resolved rate table independently; this module verifies their
identity, imports the tabulated EEDF through the public OESCR calculation
units, and evaluates the same cross-section curves on a declared grid.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from oescr.data.cross_section_db import CrossSectionLibrary
from oescr.data.provenance import file_sha256
from oescr.io.yaml_loader import load_yaml, resolve_path
from oescr.physics.eedf import summarize_eedf, tabulated_energy_pdf
from oescr.physics.rates import RateCalculator

REFERENCE_FORMAT = "oescr_external_eedf_rate_reference/v1"


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping.")
    return value


def _sequence(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty list.")
    return value


def _reference_file(config: Mapping[str, Any], spec: Mapping[str, Any], name: str) -> Path:
    path = resolve_path(config, str(spec["path"]))
    if path is None or not path.is_file():
        raise FileNotFoundError(f"{name} file is missing: {path}")
    actual = file_sha256(path)
    expected = str(spec["sha256"])
    if actual != expected:
        raise ValueError(f"{name} SHA-256 mismatch: expected {expected}, got {actual}")
    return path


def _reference_inputs(
    config: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any], Path, Path]:
    reference = _mapping(config.get("reference"), "reference")
    producer = _mapping(reference.get("producer"), "reference.producer")
    for field in ("name", "version", "command"):
        if not str(producer.get(field, "")).strip():
            raise ValueError(f"reference.producer.{field} must be recorded.")
    if producer.get("imports_oescr") is not False:
        raise ValueError("External reference producer must declare imports_oescr: false.")

    provenance = _mapping(reference.get("provenance"), "reference.provenance")
    required_provenance = (
        "cross_section_database",
        "dataset_name",
        "retrieved_on",
        "native_file_sha256",
        "conversion_command",
    )
    for field in required_provenance:
        if not str(provenance.get(field, "")).strip():
            raise ValueError(f"reference.provenance.{field} must be recorded.")

    eedf_spec = _mapping(reference.get("eedf_file"), "reference.eedf_file")
    if eedf_spec.get("distribution") != "energy_pdf_eV-1":
        raise ValueError(
            "External EEDF must use distribution: energy_pdf_eV-1; convert EEPF in the external workflow."
        )
    rates_spec = _mapping(reference.get("rates_file"), "reference.rates_file")
    return (
        producer,
        provenance,
        _reference_file(config, eedf_spec, "external EEDF"),
        _reference_file(config, rates_spec, "external rate table"),
    )


def _read_csv(path: Path, required: set[str], name: str) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(line for line in stream if not line.lstrip().startswith("#"))
        fields = set(reader.fieldnames or ())
        if not required.issubset(fields):
            missing = ", ".join(sorted(required - fields))
            raise ValueError(f"{name} is missing columns: {missing}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{name} contains no data rows.")
    return rows


def _load_eedf_rows(path: Path) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    rows = _read_csv(
        path,
        {"condition_id", "energy_eV", "energy_pdf_eV_inv"},
        "external EEDF",
    )
    grouped: dict[str, list[tuple[float, float]]] = {}
    for row in rows:
        grouped.setdefault(row["condition_id"], []).append(
            (float(row["energy_eV"]), float(row["energy_pdf_eV_inv"]))
        )

    result: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for condition_id, points in grouped.items():
        result[condition_id] = _validated_eedf_curve(condition_id, points)
    return result


def _validated_eedf_curve(
    condition_id: str, points: list[tuple[float, float]]
) -> tuple[np.ndarray, np.ndarray]:
    energy = np.asarray([point[0] for point in points], dtype=float)
    pdf = np.asarray([point[1] for point in points], dtype=float)
    if len(energy) < 2:
        raise ValueError(f"EEDF condition '{condition_id}' must contain at least two rows.")
    if not np.all(np.isfinite(energy)) or not np.all(np.isfinite(pdf)):
        raise ValueError(f"EEDF condition '{condition_id}' contains non-finite values.")
    if np.any(energy < 0.0) or np.any(pdf < 0.0):
        raise ValueError(f"EEDF condition '{condition_id}' contains negative values.")
    if np.any(np.diff(energy) <= 0.0):
        raise ValueError(f"EEDF condition '{condition_id}' energy must be strictly increasing.")
    return energy, pdf


def _load_rate_rows(path: Path) -> dict[tuple[str, str], float]:
    rows = _read_csv(
        path,
        {"condition_id", "process_id", "rate_coefficient_m3_s"},
        "external rate table",
    )
    result: dict[tuple[str, str], float] = {}
    for row in rows:
        key = row["condition_id"], row["process_id"]
        if key in result:
            raise ValueError(f"External rate table contains duplicate row {key}.")
        value = float(row["rate_coefficient_m3_s"])
        if not np.isfinite(value) or value < 0.0:
            raise ValueError(f"External rate {key} must be finite and non-negative.")
        result[key] = value
    return result


def _relative_error(actual: float, expected: float) -> float:
    if expected == 0.0:
        return 0.0 if actual == 0.0 else float("inf")
    return abs(actual - expected) / abs(expected)


def _evaluation_grid(config: Mapping[str, Any]) -> np.ndarray:
    spec = _mapping(config.get("evaluation_grid"), "evaluation_grid")
    grid = np.linspace(
        float(spec["min_eV"]),
        float(spec["max_eV"]),
        int(spec["n_points"]),
    )
    if len(grid) < 2 or grid[0] < 0.0 or grid[-1] <= grid[0]:
        raise ValueError("evaluation_grid must define at least two increasing non-negative points.")
    return grid


def _conditions(config: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    conditions = [_validated_condition(item) for item in _sequence(config.get("conditions"), "conditions")]
    ids = [str(condition["id"]) for condition in conditions]
    if len(set(ids)) != len(ids):
        raise ValueError("conditions must have unique IDs.")
    return conditions


def _validated_condition(raw: Any) -> Mapping[str, Any]:
    condition = _mapping(raw, "condition")
    condition_id = str(condition["id"])
    reduced_field = float(condition["reduced_field_Td"])
    mixture = _mapping(condition["gas_mixture"], "gas_mixture")
    fractions = np.asarray([float(value) for value in mixture.values()])
    valid_field = np.isfinite(reduced_field) and reduced_field > 0.0
    valid_mixture = (
        bool(mixture)
        and np.all(np.isfinite(fractions))
        and np.all(fractions >= 0.0)
        and np.isclose(float(np.sum(fractions)), 1.0, rtol=0.0, atol=1.0e-9)
    )
    if not (valid_field and valid_mixture):
        raise ValueError(
            f"Condition '{condition_id}' requires positive E/N and gas fractions summing to one."
        )
    return condition


def _process_inputs(
    config: Mapping[str, Any],
    library: CrossSectionLibrary,
) -> tuple[list[tuple[str, str]], dict[str, dict[str, Any]]]:
    inputs: list[tuple[str, str]] = []
    provenance: dict[str, dict[str, Any]] = {}
    for raw_process in _sequence(config.get("processes"), "processes"):
        process = _mapping(raw_process, "process")
        process_id = str(process["id"])
        if process_id in provenance:
            raise ValueError(f"Duplicate process ID: {process_id}")
        external_process_id = str(process.get("external_process_id", "")).strip()
        native_row_count = int(process.get("native_row_count", 0))
        if not external_process_id or native_row_count < 2:
            raise ValueError(
                f"Process '{process_id}' requires external_process_id and native_row_count >= 2."
            )
        cs_path = resolve_path(config, str(process["cross_section_file"]))
        if cs_path is None:
            raise ValueError(f"Process '{process_id}' has no cross-section path.")
        cs = library.load(cs_path)
        expected_hash = str(process["cross_section_sha256"])
        if cs.sha256 != expected_hash:
            raise ValueError(
                f"Cross section '{process_id}' SHA-256 mismatch: expected {expected_hash}, got {cs.sha256}"
            )
        inputs.append((process_id, str(cs_path)))
        provenance[process_id] = {
            "external_process_id": external_process_id,
            "native_row_count": native_row_count,
            "cross_section_sha256": cs.sha256,
        }
    return inputs, provenance


def _require_complete_rate_matrix(
    rates: Mapping[tuple[str, str], float],
    condition_ids: list[str],
    process_inputs: list[tuple[str, str]],
) -> None:
    expected = {
        (condition_id, process_id)
        for condition_id in condition_ids
        for process_id, _ in process_inputs
    }
    if set(rates) == expected:
        return
    missing = sorted(expected - set(rates))
    extra = sorted(set(rates) - expected)
    raise ValueError(f"External rate rows do not match manifest; missing={missing}, extra={extra}")


def _evaluate_eedf(
    condition: Mapping[str, Any],
    source_curve: tuple[np.ndarray, np.ndarray],
    grid: np.ndarray,
    acceptance: Mapping[str, Any],
) -> tuple[dict[str, Any], np.ndarray]:
    condition_id = str(condition["id"])
    source_energy, source_pdf = source_curve
    if grid[0] > source_energy[0] or grid[-1] < source_energy[-1]:
        raise ValueError(
            f"evaluation_grid does not span EEDF condition '{condition_id}' "
            f"({source_energy[0]}--{source_energy[-1]} eV)."
        )
    source = summarize_eedf(source_energy, source_pdf)
    if source.normalization <= 0.0:
        raise ValueError(f"EEDF condition '{condition_id}' has non-positive normalization.")
    imported_pdf = tabulated_energy_pdf(grid, source_energy, source_pdf)
    imported = summarize_eedf(grid, imported_pdf)
    source_normalized = source_pdf / source.normalization
    imported_on_source = np.interp(source_energy, grid, imported_pdf)
    eedf_relative_l1 = float(
        np.trapezoid(np.abs(imported_on_source - source_normalized), source_energy)
    )
    normalization_error = abs(source.normalization - 1.0)
    mean_error = _relative_error(imported.mean_energy_eV, source.mean_energy_eV)
    passed = (
        normalization_error <= float(acceptance["eedf_normalization_abs_error_max"])
        and mean_error <= float(acceptance["mean_energy_relative_error_max"])
        and eedf_relative_l1 <= float(acceptance["eedf_relative_l1_error_max"])
    )
    result = {
        "condition_id": condition_id,
        "reduced_field_Td": float(condition["reduced_field_Td"]),
        "gas_mixture": dict(_mapping(condition["gas_mixture"], "gas_mixture")),
        "source_normalization": source.normalization,
        "imported_normalization": imported.normalization,
        "source_mean_energy_eV": source.mean_energy_eV,
        "imported_mean_energy_eV": imported.mean_energy_eV,
        "mean_energy_relative_error": mean_error,
        "eedf_relative_l1_error": eedf_relative_l1,
        "passed": passed,
    }
    return result, imported_pdf


def _evaluate_rates(
    condition_id: str,
    imported_pdf: np.ndarray,
    grid: np.ndarray,
    library: CrossSectionLibrary,
    process_inputs: list[tuple[str, str]],
    external_rates: Mapping[tuple[str, str], float],
    acceptance: Mapping[str, Any],
) -> list[dict[str, Any]]:
    calculator = RateCalculator(grid, library)
    rows: list[dict[str, Any]] = []
    near_zero = float(acceptance["near_zero_rate_floor_m3_s"])
    for process_id, cs_path in process_inputs:
        external_rate = external_rates[(condition_id, process_id)]
        calculated_rate = calculator.rate_from_cross_section_file(cs_path, imported_pdf)
        absolute_error = abs(calculated_rate - external_rate)
        relative_error = (
            None
            if abs(external_rate) <= near_zero
            else _relative_error(calculated_rate, external_rate)
        )
        passed = _rate_passed(relative_error, absolute_error, acceptance)
        coverage = calculator.cross_section_coverage(cs_path, imported_pdf)
        rows.append(
            {
                "condition_id": condition_id,
                "process_id": process_id,
                "external_rate_coefficient_m3_s": external_rate,
                "oescr_rate_coefficient_m3_s": calculated_rate,
                "absolute_error_m3_s": absolute_error,
                "relative_error": relative_error,
                "covered_probability": coverage.covered_probability,
                "probability_below_cross_section_range": coverage.probability_below_data,
                "probability_above_cross_section_range": coverage.probability_above_data,
                "passed": passed,
            }
        )
    return rows


def _rate_passed(
    relative_error: float | None,
    absolute_error: float,
    acceptance: Mapping[str, Any],
) -> bool:
    if relative_error is None:
        return absolute_error <= float(acceptance["near_zero_absolute_error_max_m3_s"])
    return relative_error <= float(acceptance["rate_relative_error_max"])


def evaluate_external_eedf_reference(
    manifest_path: str | Path,
    *,
    include_curves: bool = False,
) -> dict[str, Any]:
    """Evaluate one external EEDF/rate manifest and return a serializable report."""

    config = load_yaml(manifest_path)
    if config.get("format") != REFERENCE_FORMAT:
        raise ValueError(f"format must be '{REFERENCE_FORMAT}'.")

    producer, reference_provenance, eedf_path, rates_path = _reference_inputs(config)

    conditions = _conditions(config)
    condition_ids = [str(item["id"]) for item in conditions]
    grid = _evaluation_grid(config)
    acceptance = _mapping(config.get("acceptance"), "acceptance")
    external_eedfs = _load_eedf_rows(eedf_path)
    external_rates = _load_rate_rows(rates_path)
    if set(external_eedfs) != set(condition_ids):
        raise ValueError("External EEDF condition IDs do not exactly match the manifest.")

    library = CrossSectionLibrary()
    process_inputs, process_provenance = _process_inputs(config, library)
    _require_complete_rate_matrix(external_rates, condition_ids, process_inputs)

    condition_results: list[dict[str, Any]] = []
    rate_results: list[dict[str, Any]] = []
    curve_results: list[dict[str, Any]] = []
    for condition in conditions:
        condition_id = str(condition["id"])
        source_energy, source_pdf = external_eedfs[condition_id]
        eedf_result, imported_pdf = _evaluate_eedf(condition, (source_energy, source_pdf), grid, acceptance)
        condition_results.append(eedf_result)
        if include_curves:
            curve_results.append(
                {
                    "condition_id": condition_id,
                    "external_energy_eV": source_energy.tolist(),
                    "external_energy_pdf_eV_inv": (
                        source_pdf / float(eedf_result["source_normalization"])
                    ).tolist(),
                    "oescr_energy_eV": grid.tolist(),
                    "oescr_energy_pdf_eV_inv": imported_pdf.tolist(),
                }
            )
        rate_results.extend(
            _evaluate_rates(
                condition_id,
                imported_pdf,
                grid,
                library,
                process_inputs,
                external_rates,
                acceptance,
            )
        )

    report = {
        "format": "oescr_external_eedf_rate_result/v1",
        "benchmark_id": str(config["benchmark_id"]),
        "reference_producer": dict(producer),
        "reference_provenance": dict(reference_provenance),
        "process_provenance": process_provenance,
        "input_sha256": {
            "eedf": file_sha256(eedf_path),
            "rates": file_sha256(rates_path),
            "cross_sections": {
                process_id: record["cross_section_sha256"]
                for process_id, record in process_provenance.items()
            },
        },
        "acceptance": dict(acceptance),
        "evaluation_grid": {
            "min_eV": float(grid[0]),
            "max_eV": float(grid[-1]),
            "n_points": len(grid),
        },
        "conditions": condition_results,
        "rates": rate_results,
        "passed": all(row["passed"] for row in condition_results + rate_results),
    }
    if include_curves:
        report["eedf_curves"] = curve_results
    return report
