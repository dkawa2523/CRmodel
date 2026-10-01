
#!/usr/bin/env python
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse

import yaml

from oescr.inverse.identifiability import identifiability_summary
from oescr.inverse.optimize import InverseSolver
from oescr.io.yaml_loader import save_yaml


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_yaml")
    ap.add_argument("inverse_yaml")
    ap.add_argument("--out", help="Optional YAML output path.")
    args = ap.parse_args()

    solver = InverseSolver.from_yaml(args.case_yaml, args.inverse_yaml)
    summary = identifiability_summary(
        solver.model,
        solver.case_cfg,
        solver.inv_cfg,
        solver.measurements,
        solver.windows,
        solver.params,
    )
    if args.out:
        save_yaml(summary, args.out)
        print(f"Identifiability summary written to: {args.out}")
    else:
        print(yaml.safe_dump(summary, sort_keys=False))


if __name__ == "__main__":
    main()
