from __future__ import annotations

from pathlib import Path

from oescr.analysis.validation_evidence import assess_validation_evidence
from oescr.data.provenance import file_sha256
from oescr.io.schema import validate_document
from oescr.io.yaml_loader import load_yaml

ROOT = Path(__file__).resolve().parents[1]


def test_generated_benchmark_evidence_is_reproducible_but_not_external() -> None:
    for benchmark in ("nf3_ar_ccp_clean_2023", "cl2_ar_icp_fuller2001"):
        config = load_yaml(ROOT / "examples" / "benchmarks" / benchmark / "validation.yaml")
        validate_document(config, "validation")
        result = assess_validation_evidence(config)

        assert result.declared_evidence_ready
        assert not result.external_quantitative_ready
        assert "dataset origin is generated" in result.external_quantitative_blockers
        assert "dataset is not held out" in result.external_quantitative_blockers


def _external_config(tmp_path: Path, sha256: str) -> dict:
    return {
        "kind": "oescr_validation_evidence",
        "validation_id": "calibrated_holdout",
        "evidence_level": "external_quantitative",
        "sources": [{"citation": "Independent calibrated experiment"}],
        "dataset": {
            "origin": "calibrated_measurement",
            "held_out": True,
            "measurement_basis": "spectral_radiance",
            "calibration": "absolute",
            "files": [{"file": "spectrum.csv", "sha256": sha256}],
            "preprocessing": ["Dark subtraction and response correction."],
        },
        "comparison": {
            "model_input_closure": "closed",
            "evaluation_data_use": "held_out_only",
        },
        "acceptance": {
            "evaluator": "evaluate.py",
            "evaluator_sha256": file_sha256(tmp_path / "evaluate.py"),
            "evaluator_version": "external-example-1",
            "result_contract": "example.calibrated-spectrum/v1",
            "metrics": [
                {
                    "name": "spectral error",
                    "criterion": "relative L2 error does not exceed threshold",
                    "threshold": 0.1,
                    "unit": "fraction",
                }
            ],
        },
        "limitations": ["One operating condition."],
        "__base_dir__": str(tmp_path),
        "__path__": str(tmp_path / "validation.yaml"),
    }


def test_calibrated_held_out_package_is_external_quantitative_ready(tmp_path: Path) -> None:
    spectrum = tmp_path / "spectrum.csv"
    spectrum.write_text("wavelength_nm,radiance\n750.4,1.0\n", encoding="utf-8")
    (tmp_path / "evaluate.py").write_text("# evaluator\n", encoding="utf-8")

    result = assess_validation_evidence(_external_config(tmp_path, file_sha256(spectrum)))

    assert result.declared_evidence_ready
    assert result.external_quantitative_ready
    assert not result.external_quantitative_blockers


def test_absolute_volumetric_photon_rate_is_a_supported_external_basis(tmp_path: Path) -> None:
    spectrum = tmp_path / "spectrum.csv"
    spectrum.write_text("power_W,photon_rate_m3_s\n100,1.0e19\n", encoding="utf-8")
    (tmp_path / "evaluate.py").write_text("# evaluator\n", encoding="utf-8")
    config = _external_config(tmp_path, file_sha256(spectrum))
    config["dataset"]["measurement_basis"] = "volumetric_photon_rate"

    validate_document(config, "validation")
    result = assess_validation_evidence(config)

    assert result.declared_evidence_ready
    assert result.external_quantitative_ready


def test_hash_mismatch_makes_declared_evidence_not_ready(tmp_path: Path) -> None:
    (tmp_path / "spectrum.csv").write_text("changed\n", encoding="utf-8")
    (tmp_path / "evaluate.py").write_text("# evaluator\n", encoding="utf-8")

    result = assess_validation_evidence(_external_config(tmp_path, "0" * 64))

    assert not result.declared_evidence_ready
    assert not result.external_quantitative_ready
    assert any(check.name == "artifact:spectrum.csv" and not check.passed for check in result.checks)


def test_evaluator_hash_mismatch_makes_declared_evidence_not_ready(tmp_path: Path) -> None:
    spectrum = tmp_path / "spectrum.csv"
    spectrum.write_text("wavelength_nm,radiance\n750.4,1.0\n", encoding="utf-8")
    evaluator = tmp_path / "evaluate.py"
    evaluator.write_text("# evaluator\n", encoding="utf-8")
    config = _external_config(tmp_path, file_sha256(spectrum))
    config["acceptance"]["evaluator_sha256"] = "0" * 64

    result = assess_validation_evidence(config)

    assert not result.declared_evidence_ready
    assert not result.external_quantitative_ready
    assert any(check.name == "acceptance_evaluator" and not check.passed for check in result.checks)


def test_external_label_cannot_be_used_for_generated_data(tmp_path: Path) -> None:
    spectrum = tmp_path / "spectrum.csv"
    spectrum.write_text("generated\n", encoding="utf-8")
    (tmp_path / "evaluate.py").write_text("# evaluator\n", encoding="utf-8")
    config = _external_config(tmp_path, file_sha256(spectrum))
    config["dataset"].update(
        origin="generated",
        held_out=False,
        measurement_basis="synthetic_detector_counts",
        calibration="not_applicable",
    )

    result = assess_validation_evidence(config)

    assert not result.declared_evidence_ready
    assert not result.external_quantitative_ready


def test_external_quantitative_requires_closed_model_inputs(tmp_path: Path) -> None:
    spectrum = tmp_path / "spectrum.csv"
    spectrum.write_text("wavelength_nm,radiance\n750.4,1.0\n", encoding="utf-8")
    (tmp_path / "evaluate.py").write_text("# evaluator\n", encoding="utf-8")
    config = _external_config(tmp_path, file_sha256(spectrum))
    config["comparison"]["model_input_closure"] = "conditional"

    result = assess_validation_evidence(config)

    assert not result.declared_evidence_ready
    assert not result.external_quantitative_ready
    assert "model input closure is conditional, not closed" in result.external_quantitative_blockers


def test_external_quantitative_rejects_evaluation_data_used_for_tuning(tmp_path: Path) -> None:
    spectrum = tmp_path / "spectrum.csv"
    spectrum.write_text("wavelength_nm,radiance\n750.4,1.0\n", encoding="utf-8")
    (tmp_path / "evaluate.py").write_text("# evaluator\n", encoding="utf-8")
    config = _external_config(tmp_path, file_sha256(spectrum))
    config["comparison"]["evaluation_data_use"] = "tuning_and_evaluation"

    result = assess_validation_evidence(config)

    assert not result.declared_evidence_ready
    assert not result.external_quantitative_ready
    assert (
        "evaluation data are not reserved for held-out evaluation only"
        in result.external_quantitative_blockers
    )
