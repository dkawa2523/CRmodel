"""Audit scientific-validation evidence without running a physical model.

This module answers two deliberately separate questions:

1. Is the declared evidence package complete and immutable enough to rerun?
2. Is it eligible to support an external quantitative-validation claim?

A generated benchmark can pass the first question while correctly failing the
second.  Keeping those outcomes separate prevents workflow self-consistency
from being reported as experimental validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from oescr.analysis.benchmark_contract import (
    ANALYSIS_CONTRACT_NAME,
    ANALYSIS_CONTRACT_VERSION,
    GENERATED_GATE_VERSION,
)
from oescr.data.provenance import file_sha256
from oescr.io.schema import validate_document
from oescr.io.yaml_loader import resolve_path


@dataclass(frozen=True)
class EvidenceCheck:
    """One reproducibility check performed on an evidence declaration."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class EvidenceAssessment:
    """Result of auditing one scientific-validation evidence declaration."""

    validation_id: str
    evidence_level: str
    declared_evidence_ready: bool
    external_quantitative_ready: bool
    checks: tuple[EvidenceCheck, ...]
    external_quantitative_blockers: tuple[str, ...]


def _resolved_file(config: Mapping[str, Any], file_name: str) -> Path:
    path = resolve_path(config, file_name)
    if path is None:  # pragma: no cover - schema prevents this branch
        raise ValueError("Validation evidence file path cannot be null.")
    return path


def _artifact_checks(config: Mapping[str, Any]) -> list[EvidenceCheck]:
    checks: list[EvidenceCheck] = []
    for artifact in config["dataset"]["files"]:
        path = _resolved_file(config, str(artifact["file"]))
        if not path.is_file():
            checks.append(EvidenceCheck(f"artifact:{artifact['file']}", False, "file is missing"))
            continue
        actual = file_sha256(path)
        expected = str(artifact["sha256"])
        checks.append(
            EvidenceCheck(
                f"artifact:{artifact['file']}",
                actual == expected,
                "SHA-256 matches" if actual == expected else f"SHA-256 mismatch: {actual}",
            )
        )
    return checks


def _evaluator_check(config: Mapping[str, Any]) -> EvidenceCheck:
    acceptance = config["acceptance"]
    evaluator = _resolved_file(config, str(acceptance["evaluator"]))
    if not evaluator.is_file():
        return EvidenceCheck("acceptance_evaluator", False, f"missing: {evaluator}")
    actual = file_sha256(evaluator)
    expected = str(acceptance["evaluator_sha256"])
    return EvidenceCheck(
        "acceptance_evaluator",
        actual == expected,
        (
            f"SHA-256 matches; version={acceptance['evaluator_version']}; "
            f"result_contract={acceptance['result_contract']}"
            if actual == expected
            else f"SHA-256 mismatch: {actual}"
        ),
    )


def _generated_contract_check(config: Mapping[str, Any]) -> EvidenceCheck:
    acceptance = config["acceptance"]
    expected_contract = f"{ANALYSIS_CONTRACT_NAME}/v{ANALYSIS_CONTRACT_VERSION}"
    actual = (str(acceptance["evaluator_version"]), str(acceptance["result_contract"]))
    expected = (GENERATED_GATE_VERSION, expected_contract)
    return EvidenceCheck(
        "generated_evaluator_contract",
        actual == expected,
        f"version={actual[0]}; result_contract={actual[1]}",
    )


def _classification_checks(config: Mapping[str, Any]) -> list[EvidenceCheck]:
    level = str(config["evidence_level"])
    dataset = config["dataset"]
    if level == "generated_self_consistency":
        return [
            EvidenceCheck(
                "generated_origin",
                dataset["origin"] == "generated",
                f"origin={dataset['origin']}",
            ),
            EvidenceCheck(
                "not_held_out",
                dataset["held_out"] is False,
                f"held_out={dataset['held_out']}",
            ),
            _generated_contract_check(config),
        ]
    if level.startswith("external_"):
        return [
            EvidenceCheck(
                "external_origin",
                dataset["origin"] != "generated",
                f"origin={dataset['origin']}",
            ),
            EvidenceCheck(
                "held_out",
                dataset["held_out"] is True,
                f"held_out={dataset['held_out']}",
            ),
        ]
    return []


def _external_quantitative_blockers(config: Mapping[str, Any]) -> list[str]:
    dataset = config["dataset"]
    comparison = config["comparison"]
    blockers: list[str] = []
    if config["evidence_level"] != "external_quantitative":
        blockers.append(f"evidence_level is {config['evidence_level']}, not external_quantitative")
    if dataset["origin"] == "generated":
        blockers.append("dataset origin is generated")
    if dataset["held_out"] is not True:
        blockers.append("dataset is not held out")
    if dataset["measurement_basis"] == "synthetic_detector_counts":
        blockers.append("measurement basis is synthetic detector counts")
    if dataset["calibration"] in {"none", "not_applicable"}:
        blockers.append("instrument response is not calibrated")
    if comparison["model_input_closure"] != "closed":
        blockers.append(
            f"model input closure is {comparison['model_input_closure']}, not closed"
        )
    if comparison["evaluation_data_use"] != "held_out_only":
        blockers.append(
            "evaluation data are not reserved for held-out evaluation only"
        )
    return blockers


def assess_validation_evidence(config: Mapping[str, Any]) -> EvidenceAssessment:
    """Validate and audit one loaded ``oescr_validation_evidence`` mapping."""

    validate_document(dict(config), "validation")
    checks = [*_artifact_checks(config), _evaluator_check(config), *_classification_checks(config)]
    blockers = _external_quantitative_blockers(config)
    classification_ready = config["evidence_level"] != "external_quantitative" or not blockers
    declared_ready = all(check.passed for check in checks) and classification_ready
    external_ready = declared_ready and not blockers
    return EvidenceAssessment(
        validation_id=str(config["validation_id"]),
        evidence_level=str(config["evidence_level"]),
        declared_evidence_ready=declared_ready,
        external_quantitative_ready=external_ready,
        checks=tuple(checks),
        external_quantitative_blockers=tuple(blockers),
    )
