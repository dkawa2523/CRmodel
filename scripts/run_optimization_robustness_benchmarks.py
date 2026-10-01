#!/usr/bin/env python
"""Run the versioned multi-seed optimizer robustness benchmarks."""

from __future__ import annotations

import argparse
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oescr.inverse.objectives import residual_vector  # noqa: E402
from oescr.inverse.optimize import InverseSolver  # noqa: E402
from oescr.io.yaml_loader import load_yaml, save_yaml  # noqa: E402

BENCHMARK_IDS = (
    "nf3_ar_ccp_clean_2023",
    "cl2_ar_icp_fuller2001",
)


def _objective_loss(solver: InverseSolver, case_cfg: dict[str, Any]) -> float:
    residual, _ = residual_vector(
        solver.model,
        case_cfg,
        solver.inv_cfg,
        solver.measurements,
        solver.windows,
    )
    return 0.5 * float(np.dot(residual, residual))


def _run_one(
    benchmark_id: str,
    seed: int,
    output_root: Path,
) -> Path:
    base = ROOT / "examples" / "benchmarks" / benchmark_id
    metadata = load_yaml(base / "robustness.yaml")
    case_cfg = load_yaml(base / metadata["case"])
    inverse_cfg = load_yaml(base / metadata["inverse"])
    truth_cfg = load_yaml(base / metadata["truth"])
    inverse_cfg = deepcopy(inverse_cfg)
    inverse_cfg["fit"]["global"]["seed"] = int(seed)

    solver = InverseSolver(case_cfg, inverse_cfg)
    initial_loss = _objective_loss(solver, solver.case_cfg)
    truth_loss = _objective_loss(solver, truth_cfg)
    fit = solver.fit(record_trace=True)

    output_dir = output_root / benchmark_id / f"seed_{seed}"
    save_yaml(
        {
            "benchmark_id": benchmark_id,
            "seed": int(seed),
            "success": fit.success,
            "message": fit.message,
            "initial_loss": initial_loss,
            "truth_loss": truth_loss,
            "cost": fit.cost,
            "x_opt": fit.x_opt.tolist(),
            "assessment": fit.assessment,
            "gain_offset": {str(key): value for key, value in fit.aux.get("gain_offset", {}).items()},
            "optimization_trace": fit.optimization_trace,
        },
        output_dir / "fit_summary.yaml",
    )
    save_yaml(fit.case_opt, output_dir / "case_opt.yaml")
    print(f"{benchmark_id} seed={seed}: initial={initial_loss:.6g}, truth={truth_loss:.6g}, optimized={fit.cost:.6g}")
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Run distant-initialization, prior-free OESCR robustness benchmarks.")
    parser.add_argument(
        "--benchmark",
        action="append",
        choices=BENCHMARK_IDS,
        help="Benchmark to run; repeat to select more than one. Defaults to both.",
    )
    parser.add_argument(
        "--seed",
        action="append",
        type=int,
        help="Override the configured seed list; repeat for multiple seeds.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / ".local_outputs" / "robustness_benchmarks",
    )
    args = parser.parse_args()

    benchmark_ids = tuple(args.benchmark or BENCHMARK_IDS)
    for benchmark_id in benchmark_ids:
        base = ROOT / "examples" / "benchmarks" / benchmark_id
        metadata = load_yaml(base / "robustness.yaml")
        seeds = tuple(args.seed or metadata["seeds"])
        for seed in seeds:
            _run_one(benchmark_id, int(seed), args.output)


if __name__ == "__main__":
    main()
