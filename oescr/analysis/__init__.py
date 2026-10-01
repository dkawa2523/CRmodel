from pathlib import Path

from .classification import (
    PAIR_CLASS_LOG_TOL,
    WINDOW_CLASS_THRESHOLDS,
    classify_pair_log_error,
    classify_window,
    is_broad_kind,
    pair_pattern_label,
    scenario_accuracy_vs_truth,
    window_class_label,
    window_pass_rate_by_kind,
    window_quality_score,
    window_thresholds,
)


def analyze_one(bench_dir: Path, result_dir_name: str, out_name: str) -> Path:
    """Load benchmark orchestration only when report generation is requested."""

    from .benchmark_results import analyze_one as _analyze_one

    return _analyze_one(bench_dir, result_dir_name, out_name)


def main() -> None:
    """Load the CLI/reporting stack lazily."""

    from .benchmark_cli import main as _main

    _main()

__all__ = [
    "analyze_one",
    "main",
    "PAIR_CLASS_LOG_TOL",
    "WINDOW_CLASS_THRESHOLDS",
    "classify_pair_log_error",
    "classify_window",
    "is_broad_kind",
    "pair_pattern_label",
    "scenario_accuracy_vs_truth",
    "window_class_label",
    "window_pass_rate_by_kind",
    "window_quality_score",
    "window_thresholds",
]
