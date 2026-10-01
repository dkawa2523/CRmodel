"""Command-line orchestration for benchmark report generation."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from .benchmark_results import analyze_one, resolve_benchmark_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze benchmark spectra, fit quality, and interpretation."
    )
    parser.add_argument(
        "benchmarks",
        nargs="+",
        help="Benchmark directory names under examples/benchmarks or absolute paths",
    )
    parser.add_argument(
        "--result-dir-name",
        default="inverse_test",
        help="Directory under runs/ that holds fit_summary.yaml",
    )
    parser.add_argument(
        "--out-name",
        default="analysis",
        help="Subdirectory to write analysis outputs into",
    )
    args = parser.parse_args()

    output_directories: List[Path] = []
    for benchmark in args.benchmarks:
        output_directory = analyze_one(
            resolve_benchmark_dir(benchmark),
            args.result_dir_name,
            args.out_name,
        )
        output_directories.append(output_directory)
        print(f"Analysis written to: {output_directory}")

    if len(output_directories) > 1:
        print("Generated analysis directories:")
        for output_directory in output_directories:
            print(output_directory)


if __name__ == "__main__":
    main()
