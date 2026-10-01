from __future__ import annotations

from pathlib import Path

from oescr.analysis.benchmark_results import analyze_one
from oescr.inverse.optimize import InverseSolver
from oescr.io.yaml_loader import load_yaml, save_yaml

ROOT = Path(__file__).resolve().parents[1]
NF3_BENCHMARK = ROOT / "examples" / "benchmarks" / "nf3_ar_ccp_clean_2023"


def test_benchmark_report_generation_writes_expected_artifacts(tmp_path: Path) -> None:
    result_directory = tmp_path / "inverse_result"
    result_directory.mkdir()
    solver = InverseSolver.from_yaml(
        NF3_BENCHMARK / "case_init.yaml",
        NF3_BENCHMARK / "inverse.yaml",
    )
    save_yaml(
        {"x_opt": solver.params.initial_vector(solver.case_cfg).tolist()},
        result_directory / "fit_summary.yaml",
    )

    output_directory = analyze_one(
        NF3_BENCHMARK,
        str(result_directory),
        "analysis",
    )

    for relative_path in (
        "analysis_summary.yaml",
        "analysis_report.md",
        "analysis_dashboard.html",
        "forward_dashboard.html",
        "plots/fit_quality.svg",
        "plots/forward_window_fidelity.svg",
    ):
        output = output_directory / relative_path
        assert output.is_file()
        assert output.stat().st_size > 0

    summary = load_yaml(output_directory / "analysis_summary.yaml")
    assert summary["analysis_contract"]["name"] == "oescr.benchmark.analysis"
    assert summary["analysis_contract"]["version"] == 1
    assert len(summary["analysis_contract"]["measurement_sha256"]) == 64
    assert summary["run_fingerprint"]["parameter_names"] == solver.params.names()
    assert len(summary["run_fingerprint"]["fit_summary_sha256"]) == 64
