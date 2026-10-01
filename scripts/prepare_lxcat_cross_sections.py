#!/usr/bin/env python
"""Inventory a native LXCat file and optionally export selected process curves."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oescr.data.lxcat import LXCatDataset, LXCatProcess, load_lxcat_dataset, select_lxcat_process
from oescr.data.provenance import file_sha256


def _write_process_csv(path: Path, dataset: LXCatDataset, process: LXCatProcess) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        stream.write(f"# source_database: {dataset.database}\n")
        stream.write(f"# source_file_sha256: {dataset.source_sha256}\n")
        stream.write(f"# collision_type: {process.collision_type}\n")
        stream.write(f"# process_label: {process.target_label}\n")
        stream.write(f"# process_description: {process.process_description}\n")
        stream.write(f"# parameter_line: {process.parameter_line or ''}\n")
        stream.write(f"# curve_data_sha256: {process.curve_data_sha256}\n")
        writer = csv.writer(stream)
        writer.writerow(["energy_eV", "sigma_m2"])
        writer.writerows(zip(process.energy_eV, process.sigma_m2, strict=True))


def _process_record(process: LXCatProcess) -> dict[str, Any]:
    return {
        "index": process.index,
        "collision_type": process.collision_type,
        "target_label": process.target_label,
        "process_description": process.process_description,
        "parameter_line": process.parameter_line,
        "row_count": len(process.energy_eV),
        "energy_min_eV": float(process.energy_eV[0]),
        "energy_max_eV": float(process.energy_eV[-1]),
        "curve_data_sha256": process.curve_data_sha256,
    }


def _inventory(dataset: LXCatDataset) -> dict[str, Any]:
    return {
        "format": "oescr_lxcat_inventory/v1",
        "source_file": dataset.path.name,
        "source_sha256": dataset.source_sha256,
        "database": dataset.database,
        "generated_on": dataset.generated_on,
        "process_count": len(dataset.processes),
        "process_counts": dict(sorted(Counter(p.collision_type for p in dataset.processes).items())),
        "processes": [_process_record(process) for process in dataset.processes],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="User-downloaded native LXCat text file.")
    parser.add_argument("--inventory", type=Path, help="Write the complete JSON inventory.")
    parser.add_argument(
        "--select",
        action="append",
        default=[],
        help="Exact target label or PROCESS description to export; repeat as needed.",
    )
    parser.add_argument("--export-dir", type=Path, help="Directory for selected standard CSV curves.")
    args = parser.parse_args()
    if args.select and args.export_dir is None:
        parser.error("--export-dir is required when --select is used")

    dataset = load_lxcat_dataset(args.source)
    inventory = _inventory(dataset)
    if args.inventory is not None:
        args.inventory.parent.mkdir(parents=True, exist_ok=True)
        args.inventory.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")

    exported: list[Path] = []
    for label in args.select:
        process = select_lxcat_process(dataset, label)
        output = args.export_dir / f"process_{process.index:03d}_{process.collision_type.lower()}.csv"
        _write_process_csv(output, dataset, process)
        exported.append(output)

    print(f"database: {dataset.database}")
    print(f"source SHA-256: {dataset.source_sha256}")
    print(f"process counts: {inventory['process_counts']}")
    for path in exported:
        print(f"exported: {path.resolve()} ({file_sha256(path)})")


if __name__ == "__main__":
    main()
