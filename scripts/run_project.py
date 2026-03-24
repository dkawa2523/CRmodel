#!/usr/bin/env python
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import csv

from oescr.forward.model import OESCRModel
from oescr.inverse.optimize import InverseSolver
from oescr.io.project import load_project
from oescr.io.yaml_loader import save_yaml


def _write_forward(case_yaml: Path, out_dir: Path) -> None:
    model = OESCRModel.from_yaml(case_yaml)
    result = model.predict()
    out_dir.mkdir(parents=True, exist_ok=True)
    for inst_id, chord_map in result.spectra.items():
        for chord_key, spec in chord_map.items():
            out_path = out_dir / f"{inst_id}_{chord_key}.csv"
            with out_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["wavelength_nm", "intensity"])
                for wl, it in zip(spec["wavelength_nm"], spec["intensity"]):
                    writer.writerow([f"{wl:.8f}", f"{it:.12e}"])


def _write_inverse(case_yaml: Path, inverse_yaml: Path, out_dir: Path) -> None:
    solver = InverseSolver.from_yaml(case_yaml, inverse_yaml)
    fit = solver.fit()
    out_dir.mkdir(parents=True, exist_ok=True)
    save_yaml(
        {
            "success": fit.success,
            "message": fit.message,
            "cost": fit.cost,
            "x_opt": fit.x_opt.tolist(),
            "uncertainty": fit.uncertainty,
            "gain_offset": {str(k): v for k, v in fit.aux.get("gain_offset", {}).items()},
            "selected_windows": fit.aux.get("selected_windows", {}),
        },
        out_dir / "fit_summary.yaml",
    )
    save_yaml(fit.case_opt, out_dir / "case_opt.yaml")


def main() -> None:
    ap = argparse.ArgumentParser(description="Run OESCR from a single project YAML manifest.")
    ap.add_argument("project_yaml")
    ap.add_argument("--task", choices=["forward", "inverse"], default="inverse")
    ap.add_argument("--out", default=None, help="Override output directory.")
    args = ap.parse_args()

    project = load_project(args.project_yaml)
    out_dir = Path(args.out).resolve() if args.out else project.default_output_dir.resolve()

    if args.task == "forward":
        _write_forward(project.case_yaml, out_dir)
    else:
        if project.inverse_yaml is None:
            raise ValueError("Project manifest has no inverse YAML.")
        _write_inverse(project.case_yaml, project.inverse_yaml, out_dir)
    print(f"Project task '{args.task}' completed: {out_dir}")


if __name__ == "__main__":
    main()
