from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest
import yaml
from scipy import constants as const

from oescr.analysis.external_eedf_reference import evaluate_external_eedf_reference
from oescr.analysis.external_eedf_renderers import write_external_eedf_figures
from oescr.data.provenance import file_sha256


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _reference_case(tmp_path: Path) -> Path:
    energy = np.linspace(0.0, 20.0, 401)
    pdf = np.sqrt(energy) * np.exp(-energy / 2.0)
    pdf /= np.trapezoid(pdf, energy)
    sigma = np.full_like(energy, 1.0e-20)
    velocity = np.sqrt(2.0 * energy * const.e / const.m_e)
    external_rate = float(np.trapezoid(sigma * velocity * pdf, energy))

    eedf_path = tmp_path / "external_eedf.csv"
    _write_csv(
        eedf_path,
        ["condition_id", "energy_eV", "energy_pdf_eV_inv"],
        [
            {
                "condition_id": "ar_100Td",
                "energy_eV": f"{value:.17g}",
                "energy_pdf_eV_inv": f"{density:.17g}",
            }
            for value, density in zip(energy, pdf, strict=True)
        ],
    )
    rates_path = tmp_path / "external_rates.csv"
    _write_csv(
        rates_path,
        ["condition_id", "process_id", "rate_coefficient_m3_s"],
        [
            {
                "condition_id": "ar_100Td",
                "process_id": "constant_sigma",
                "rate_coefficient_m3_s": f"{external_rate:.17g}",
            }
        ],
    )
    cross_section_path = tmp_path / "constant_sigma.csv"
    _write_csv(
        cross_section_path,
        ["energy_eV", "sigma_m2"],
        [
            {"energy_eV": f"{value:.17g}", "sigma_m2": f"{value_sigma:.17g}"}
            for value, value_sigma in zip(energy, sigma, strict=True)
        ],
    )

    manifest = {
        "format": "oescr_external_eedf_rate_reference/v1",
        "benchmark_id": "analytic_unit_fixture",
        "reference": {
            "producer": {
                "name": "independent analytic unit fixture",
                "version": "1",
                "command": "pytest fixture generator",
                "imports_oescr": False,
            },
            "eedf_file": {
                "path": eedf_path.name,
                "sha256": file_sha256(eedf_path),
                "distribution": "energy_pdf_eV-1",
            },
            "rates_file": {
                "path": rates_path.name,
                "sha256": file_sha256(rates_path),
            },
            "provenance": {
                "cross_section_database": "analytic",
                "dataset_name": "constant cross section unit fixture",
                "retrieved_on": "2026-10-01",
                "native_file_sha256": file_sha256(cross_section_path),
                "conversion_command": "none; written directly by test",
            },
        },
        "conditions": [
            {
                "id": "ar_100Td",
                "reduced_field_Td": 100.0,
                "gas_mixture": {"Ar": 1.0},
            }
        ],
        "processes": [
            {
                "id": "constant_sigma",
                "external_process_id": "analytic_constant_sigma",
                "native_row_count": len(energy),
                "cross_section_file": cross_section_path.name,
                "cross_section_sha256": file_sha256(cross_section_path),
            }
        ],
        "evaluation_grid": {"min_eV": 0.0, "max_eV": 20.0, "n_points": 401},
        "acceptance": {
            "eedf_normalization_abs_error_max": 1.0e-12,
            "mean_energy_relative_error_max": 1.0e-12,
            "eedf_relative_l1_error_max": 1.0e-12,
            "rate_relative_error_max": 1.0e-12,
            "near_zero_rate_floor_m3_s": 1.0e-30,
            "near_zero_absolute_error_max_m3_s": 1.0e-30,
        },
    }
    manifest_path = tmp_path / "reference.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return manifest_path


def test_external_eedf_reference_evaluates_public_rate_path(tmp_path: Path) -> None:
    result = evaluate_external_eedf_reference(_reference_case(tmp_path))

    assert result["passed"] is True
    assert result["reference_producer"]["imports_oescr"] is False
    assert result["conditions"][0]["eedf_relative_l1_error"] < 1.0e-14
    assert result["rates"][0]["relative_error"] < 1.0e-14
    assert result["rates"][0]["covered_probability"] == pytest.approx(1.0)


def test_external_eedf_reference_rejects_mutated_evidence(tmp_path: Path) -> None:
    manifest_path = _reference_case(tmp_path)
    with (tmp_path / "external_eedf.csv").open("a", encoding="utf-8") as stream:
        stream.write("ar_100Td,21,0\n")

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        evaluate_external_eedf_reference(manifest_path)


def test_external_eedf_reference_requires_converted_energy_pdf(tmp_path: Path) -> None:
    manifest_path = _reference_case(tmp_path)
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["reference"]["eedf_file"]["distribution"] = "eepf_eV-3/2"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="convert EEPF"):
        evaluate_external_eedf_reference(manifest_path)


def test_external_eedf_reference_writes_physical_figures(tmp_path: Path) -> None:
    report = evaluate_external_eedf_reference(_reference_case(tmp_path), include_curves=True)

    outputs = write_external_eedf_figures(report, tmp_path / "figures")

    assert [path.name for path in outputs] == [
        "analytic_unit_fixture_ar_100pct_eedf.png",
        "analytic_unit_fixture_ar_100pct_summary.png",
    ]
    assert all(path.stat().st_size > 10_000 for path in outputs)
