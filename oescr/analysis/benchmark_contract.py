"""Versioned fingerprints for reproducible benchmark comparisons.

The comparison contract contains inputs that must be identical when two
analysis summaries are compared.  The run fingerprint records inputs that are
expected to change between candidate implementations.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

ANALYSIS_CONTRACT_NAME = "oescr.benchmark.analysis"
ANALYSIS_CONTRACT_VERSION = 1
GENERATED_GATE_VERSION = "gate-v1"

_ANALYSIS_OBJECTIVE_KEYS = (
    "auto_gain_fit",
    "auto_gain_tilt_fit",
    "auto_offset_fit",
    "gain_scope",
    "window_min_relative_signal",
    "window_ratio_metric",
    "window_ratio_min_relative_signal",
    "window_ratio_pairs",
)


class AnalysisContractError(ValueError):
    """Raised when summaries do not share a comparable analysis contract."""


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _plain(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if not str(key).startswith("__")
        }
    if isinstance(value, np.ndarray):
        return _plain(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_plain(item) for item in value]
    return value


def semantic_sha256(value: Any) -> str:
    """Hash semantic content without loader-only ``__*`` metadata."""

    payload = json.dumps(
        _plain(value),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def measurement_sha256(measurements: Mapping[str, Sequence[Any]]) -> str:
    payload: dict[str, list[dict[str, Any]]] = {}
    for instrument_id, items in sorted(measurements.items()):
        rows: list[dict[str, Any]] = []
        for measurement in items:
            feature = measurement.feature_covariance
            rows.append(
                {
                    "wavelength_nm": measurement.wavelength_nm,
                    "intensity": measurement.intensity,
                    "sigma": measurement.sigma,
                    "covariance": measurement.covariance,
                    "metadata": measurement.metadata or {},
                    "feature_covariance": None
                    if feature is None
                    else {"names": feature.names, "covariance": feature.covariance},
                    "calibration_relative_standard_uncertainty": (
                        measurement.calibration_relative_standard_uncertainty
                    ),
                }
            )
        payload[str(instrument_id)] = rows
    return semantic_sha256(payload)


def analysis_policy(objective: Mapping[str, Any]) -> dict[str, Any]:
    """Return only objective fields that change benchmark metric semantics."""

    return {key: objective[key] for key in _ANALYSIS_OBJECTIVE_KEYS if key in objective}


def build_analysis_contract(
    *,
    benchmark_id: str,
    benchmark_meta: Mapping[str, Any],
    truth_config: Mapping[str, Any],
    measurements: Mapping[str, Sequence[Any]],
    windows: Sequence[Mapping[str, Any]],
    objective: Mapping[str, Any],
    metric_definition: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the immutable basis required for between-run comparison."""

    evaluation_spec = {
        "windows": windows,
        "objective_policy": analysis_policy(objective),
        "metric_definition": metric_definition,
    }
    return {
        "name": ANALYSIS_CONTRACT_NAME,
        "version": ANALYSIS_CONTRACT_VERSION,
        "benchmark_id": benchmark_id,
        "benchmark_meta_sha256": semantic_sha256(benchmark_meta),
        "truth_config_sha256": semantic_sha256(truth_config),
        "measurement_sha256": measurement_sha256(measurements),
        "evaluation_spec_sha256": semantic_sha256(evaluation_spec),
    }


def build_run_fingerprint(
    *,
    package_version: str,
    case_config: Mapping[str, Any],
    inverse_config: Mapping[str, Any],
    fit_summary_sha256: str,
    parameter_names: Sequence[str],
) -> dict[str, Any]:
    """Record candidate-specific inputs without making them comparison keys."""

    return {
        "oescr_version": package_version,
        "case_config_sha256": semantic_sha256(case_config),
        "inverse_config_sha256": semantic_sha256(inverse_config),
        "fit_summary_sha256": fit_summary_sha256,
        "parameter_names": list(parameter_names),
        "inference_mode": str(inverse_config.get("inference_mode", "relative_shape")),
    }


def require_analysis_contract(summary: Mapping[str, Any]) -> Mapping[str, Any]:
    contract = summary.get("analysis_contract")
    if not isinstance(contract, Mapping):
        raise AnalysisContractError(
            "Analysis summary has no versioned analysis_contract; regenerate it with the current analyzer."
        )
    if contract.get("name") != ANALYSIS_CONTRACT_NAME:
        raise AnalysisContractError(f"Unsupported analysis contract name: {contract.get('name')!r}.")
    if contract.get("version") != ANALYSIS_CONTRACT_VERSION:
        raise AnalysisContractError(
            "Unsupported analysis contract version: "
            f"{contract.get('version')!r}; expected {ANALYSIS_CONTRACT_VERSION}."
        )
    return contract


def assert_compatible_analysis_contracts(
    baseline: Mapping[str, Any],
    improved: Mapping[str, Any],
) -> None:
    """Reject comparisons whose data or metric semantics differ."""

    baseline_contract = dict(require_analysis_contract(baseline))
    improved_contract = dict(require_analysis_contract(improved))
    mismatches = [
        key
        for key in sorted(set(baseline_contract) | set(improved_contract))
        if baseline_contract.get(key) != improved_contract.get(key)
    ]
    if mismatches:
        raise AnalysisContractError(
            "Analysis summaries are not comparable; contract fields differ: "
            + ", ".join(mismatches)
            + ". Regenerate both summaries from the same evidence and analysis contract."
        )
