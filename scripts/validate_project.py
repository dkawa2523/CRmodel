#!/usr/bin/env python
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from pprint import pformat

from oescr.forward.model import OESCRModel
from oescr.inverse.optimize import InverseSolver
from oescr.io.project import load_project


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate a project YAML and print a concise summary.")
    ap.add_argument("project_yaml")
    args = ap.parse_args()

    project = load_project(args.project_yaml)
    model = OESCRModel.from_yaml(project.case_yaml)
    print(f"Project: {project.name}")
    print(f"Case YAML: {project.case_yaml}")
    print(f"Default output: {project.default_output_dir}")
    print(f"Capabilities: {pformat(model.capabilities())}")
    print(f"Instruments: {[cfg['id'] for cfg in model.instrument_configs_for()]}")
    if project.inverse_yaml is not None:
        solver = InverseSolver.from_yaml(project.case_yaml, project.inverse_yaml)
        print(f"Inverse YAML: {project.inverse_yaml}")
        print(f"Parameter count: {len(solver.params.params)}")
        print(f"Measurement groups: {list(solver.measurements.keys())}")
        print(f"Selected windows: {solver.windows and len(solver.windows) or 0}")


if __name__ == "__main__":
    main()
