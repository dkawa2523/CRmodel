from __future__ import annotations

from pathlib import Path

import numpy as np

from oescr.inverse.optimize import InverseSolver
from oescr.io.pathmap import get_path
from oescr.io.yaml_loader import load_yaml

ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS = (
    "nf3_ar_ccp_clean_2023",
    "cl2_ar_icp_fuller2001",
)


def test_robustness_cases_are_distant_prior_free_and_hold_out_a_chord() -> None:
    for benchmark_id in BENCHMARKS:
        base = ROOT / "examples" / "benchmarks" / benchmark_id
        metadata = load_yaml(base / "robustness.yaml")
        solver = InverseSolver.from_yaml(base / metadata["case"], base / metadata["inverse"])
        truth = load_yaml(base / metadata["truth"])

        assert metadata["version"] == 2
        assert metadata["held_out_metric"] == "noise_free_forward_truth_window_nrmse"
        assert solver.inv_cfg["priors"] == []
        assert metadata["held_out_chord"] not in metadata["training_chords"]
        measurement_files = solver.inv_cfg["measurements"][0]["files"]
        assert len(measurement_files) == len(metadata["training_chords"])
        assert all("chord_4.csv" not in path for path in measurement_files)
        assert len(metadata["seeds"]) >= 3
        assert len(set(metadata["seeds"])) == len(metadata["seeds"])
        truth_spectrum = base / "forward_truth" / f"{metadata['instrument_id']}_chord_4.csv"
        assert truth_spectrum.exists()

        labels = {window["label"] for window in metadata["plot_windows"]}
        if benchmark_id.startswith("nf3"):
            assert "N2(B-A) molecular band" in labels
        else:
            assert "Ar II / Cl II" not in labels

        initial_errors = []
        for parameter in solver.params.params:
            initial = float(get_path(solver.case_cfg, parameter.path))
            target = float(get_path(truth, parameter.path))
            initial_errors.append(abs(initial / target - 1.0))
            lower, upper = parameter.bounds
            assert lower <= initial <= upper

        threshold = metadata["acceptance"]["min_initial_parameter_median_abs_relative_error"]
        assert float(np.median(initial_errors)) >= float(threshold)
