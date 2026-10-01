from __future__ import annotations

from importlib.metadata import version

import pytest

from oescr import __version__
from oescr.analysis.benchmark_contract import (
    ANALYSIS_CONTRACT_NAME,
    ANALYSIS_CONTRACT_VERSION,
    AnalysisContractError,
    assert_compatible_analysis_contracts,
    semantic_sha256,
)


def _summary(measurement_hash: str = "a" * 64) -> dict:
    return {
        "analysis_contract": {
            "name": ANALYSIS_CONTRACT_NAME,
            "version": ANALYSIS_CONTRACT_VERSION,
            "benchmark_id": "example",
            "benchmark_meta_sha256": "b" * 64,
            "truth_config_sha256": "c" * 64,
            "measurement_sha256": measurement_hash,
            "evaluation_spec_sha256": "d" * 64,
        }
    }


def test_semantic_hash_ignores_loader_metadata_and_mapping_order() -> None:
    left = {"value": [1.0, 2.0], "nested": {"x": 3}, "__path__": "machine-a"}
    right = {"nested": {"x": 3}, "__base_dir__": "machine-b", "value": [1.0, 2.0]}

    assert semantic_sha256(left) == semantic_sha256(right)


def test_analysis_contract_rejects_missing_or_changed_evidence() -> None:
    with pytest.raises(AnalysisContractError, match="no versioned analysis_contract"):
        assert_compatible_analysis_contracts({}, _summary())

    with pytest.raises(AnalysisContractError, match="measurement_sha256"):
        assert_compatible_analysis_contracts(_summary(), _summary("e" * 64))


def test_package_version_has_one_installed_source_of_truth() -> None:
    assert __version__ == version("oescr")
