#!/usr/bin/env python
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from pathlib import Path

from oescr.inverse.optimize import InverseSolver
from oescr.io.yaml_loader import save_yaml


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_yaml")
    ap.add_argument("inverse_yaml")
    ap.add_argument("--out", default="inverse_output")
    ap.add_argument(
        "--record-trace",
        action="store_true",
        help="Record objective evaluations for convergence diagnostics.",
    )
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    solver = InverseSolver.from_yaml(args.case_yaml, args.inverse_yaml)
    fit = solver.fit(record_trace=args.record_trace)

    save_yaml(
        {
            "success": fit.success,
            "message": fit.message,
            "cost": fit.cost,
            "x_opt": fit.x_opt.tolist(),
            "uncertainty": fit.uncertainty,
            "identifiability": fit.identifiability,
            "assessment": fit.assessment,
            "calibration_uncertainty": fit.calibration_uncertainty,
            "gain_offset": {str(k): v for k, v in fit.aux.get("gain_offset", {}).items()},
            "optimization_trace": fit.optimization_trace,
        },
        out_dir / "fit_summary.yaml",
    )
    save_yaml(fit.case_opt, out_dir / "case_opt.yaml")
    print(f"Inverse results written to: {out_dir}")


if __name__ == "__main__":
    main()
