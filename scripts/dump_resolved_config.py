#!/usr/bin/env python
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse

from oescr.io.normalize import normalize_case_config, normalize_inverse_config
from oescr.io.yaml_loader import load_yaml, save_yaml


def main() -> None:
    ap = argparse.ArgumentParser(description="Dump normalized YAML after include expansion.")
    ap.add_argument("case_yaml")
    ap.add_argument("inverse_yaml", nargs='?')
    ap.add_argument("--out", default="resolved_config")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    case_cfg = normalize_case_config(load_yaml(args.case_yaml))
    save_yaml(case_cfg, out_dir / 'case_resolved.yaml')

    if args.inverse_yaml:
        inv_cfg = normalize_inverse_config(case_cfg, load_yaml(args.inverse_yaml))
        save_yaml(inv_cfg, out_dir / 'inverse_resolved.yaml')

    print(f"Resolved configuration written to: {out_dir}")


if __name__ == '__main__':
    main()
