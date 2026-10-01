#!/usr/bin/env python
"""Compare immutable external EEDF/rate tables with OESCR integration."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oescr.analysis.external_eedf_reference import evaluate_external_eedf_reference


def _write_rate_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify external-reference identity and compare OESCR EEDF rate integrals."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path(".local_outputs/external_eedf_rate"))
    parser.add_argument("--no-plots", action="store_true", help="Skip PNG figure generation.")
    args = parser.parse_args()

    result = evaluate_external_eedf_reference(args.manifest, include_curves=not args.no_plots)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / f"{result['benchmark_id']}_report.json"
    rates_path = args.output_dir / f"{result['benchmark_id']}_rates.csv"
    if args.no_plots:
        figure_paths = []
    else:
        from oescr.analysis.external_eedf_renderers import write_external_eedf_figures

        figure_paths = write_external_eedf_figures(result, args.output_dir)
    stored_result = {key: value for key, value in result.items() if key != "eedf_curves"}
    report_path.write_text(json.dumps(stored_result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    _write_rate_csv(rates_path, result["rates"])

    status = "PASS" if result["passed"] else "FAIL"
    print(f"{result['benchmark_id']}: {status}")
    print(f"report: {report_path.resolve()}")
    print(f"rates:  {rates_path.resolve()}")
    for figure_path in figure_paths:
        print(f"figure: {figure_path.resolve()}")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
