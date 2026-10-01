#!/usr/bin/env python
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse

from oescr.io.schema import AVAILABLE_SCHEMAS, validate_document
from oescr.io.species_packs import compose_species_packs
from oescr.io.yaml_loader import load_yaml


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate an OESCR YAML file against a structural schema.")
    ap.add_argument("schema", choices=sorted(AVAILABLE_SCHEMAS))
    ap.add_argument("yaml_path")
    args = ap.parse_args()

    cfg = load_yaml(args.yaml_path)
    if args.schema == "case":
        cfg, _ = compose_species_packs(cfg)
    validate_document(cfg, args.schema)
    print(f"Schema validation OK: {args.yaml_path} [{args.schema}]")


if __name__ == "__main__":
    main()
