#!/usr/bin/env python
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from pprint import pprint

from oescr.api import (
    BAND_EMISSION_PLUGINS,
    BAND_PROFILE_PLUGINS,
    BASELINE_PLUGINS,
    EEDF_PLUGINS,
    GEOMETRY_PLUGINS,
    LSF_PLUGINS,
    REACTION_RATE_PLUGINS,
    THROUGHPUT_PLUGINS,
    TRAPPING_PLUGINS,
    WALL_LOSS_PLUGINS,
)

REGISTRIES = {
    "eedf": EEDF_PLUGINS,
    "reaction_rate": REACTION_RATE_PLUGINS,
    "band_profile": BAND_PROFILE_PLUGINS,
    "band_emission": BAND_EMISSION_PLUGINS,
    "trapping": TRAPPING_PLUGINS,
    "wall_loss": WALL_LOSS_PLUGINS,
    "geometry": GEOMETRY_PLUGINS,
    "throughput": THROUGHPUT_PLUGINS,
    "lsf": LSF_PLUGINS,
    "baseline": BASELINE_PLUGINS,
}


def main() -> None:
    ap = argparse.ArgumentParser(description="Print the built-in OESCR plugin catalog.")
    ap.add_argument("registry", nargs="?", choices=sorted(REGISTRIES), help="Optional registry to print.")
    args = ap.parse_args()

    if args.registry:
        pprint(REGISTRIES[args.registry].catalog())
    else:
        pprint({name: reg.catalog() for name, reg in REGISTRIES.items()})


if __name__ == "__main__":
    main()
