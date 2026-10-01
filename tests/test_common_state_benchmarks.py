from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from oescr.forward.model import OESCRModel
from oescr.inverse.optimize import InverseSolver
from oescr.io.normalize import normalize_case_config
from oescr.io.validators import validate_case_config, validate_case_structural
from oescr.io.yaml_loader import load_yaml

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = ROOT / "examples" / "benchmarks"


@pytest.mark.parametrize(
    ("directory_name", "spectrum_count", "state_count"),
    [
        ("common_state_ar_o2", 5, 3),
        ("common_state_ar_cl2", 7, 5),
    ],
)
def test_common_state_cases_are_valid_and_share_two_parameters(
    directory_name: str,
    spectrum_count: int,
    state_count: int,
) -> None:
    directory = BENCHMARK_ROOT / directory_name
    for filename in ("case_truth.yaml", "case_init.yaml"):
        raw = load_yaml(directory / filename)
        validate_case_structural(raw)
        normalized = normalize_case_config(raw)
        validate_case_config(normalized)
        assert normalized["geometry"]["n_shells"] == 1
        assert len(normalized["states"]) == state_count
        assert len(normalized["instruments"]) == spectrum_count

    solver = InverseSolver.from_yaml(directory / "case_init.yaml", directory / "inverse.yaml")
    assert solver.params.names() == ["electron_temperature_eV", "electron_density_m3"]
    assert set(solver.measurements) == {item["id"] for item in solver.model.instrument_configs_for()}
    assert all(len(items) == 1 for items in solver.measurements.values())


@pytest.mark.parametrize("directory_name", ["common_state_ar_o2", "common_state_ar_cl2"])
def test_initial_spectra_are_visibly_separated_from_truth(directory_name: str) -> None:
    directory = BENCHMARK_ROOT / directory_name
    truth = OESCRModel.from_yaml(directory / "case_truth.yaml").predict()
    initial = OESCRModel.from_yaml(directory / "case_init.yaml").predict()
    error = 0.0
    reference = 0.0
    for instrument_id, chord_map in truth.spectra.items():
        truth_intensity = np.asarray(chord_map["chord_0"]["intensity"], dtype=float)
        initial_intensity = np.asarray(initial.spectra[instrument_id]["chord_0"]["intensity"], dtype=float)
        error += float(np.sum((initial_intensity - truth_intensity) ** 2))
        reference += float(np.sum(truth_intensity**2))
    nrmse = np.sqrt(error / reference)
    assert 0.25 < nrmse < 0.60


def test_cl_pack_declares_effective_emitter_limit() -> None:
    pack = load_yaml(ROOT / "examples" / "data" / "species_packs" / "cl_effective_lines.yaml")
    assert "not state-resolved external validation" in pack["metadata"]["evidence"]
    assert len(pack["states"]) == 3
    assert len(pack["reactions"]) == 3
    assert len(pack["transitions"]) == 3
