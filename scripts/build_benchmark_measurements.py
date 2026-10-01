#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oescr.forward.model import OESCRModel
from oescr.io.spectrum_csv import write_spectrum_csv
from oescr.io.yaml_loader import load_yaml, save_yaml

BENCH_ROOT = Path(__file__).resolve().parents[1] / "examples" / "benchmarks"


def iter_benchmark_dirs(selection: list[str] | None) -> Iterable[Path]:
    if not selection:
        for p in sorted(BENCH_ROOT.iterdir()):
            if p.is_dir() and (p / "benchmark_meta.yaml").exists():
                yield p
        return
    for item in selection:
        p = (BENCH_ROOT / item).resolve() if not Path(item).is_absolute() else Path(item)
        if not (p / "benchmark_meta.yaml").exists():
            raise FileNotFoundError(f"No benchmark_meta.yaml in {p}")
        yield p


def apply_measurement_model(wl: np.ndarray, y: np.ndarray, cfg: dict, rng: np.random.Generator, chord_idx: int) -> np.ndarray:
    shift = float(cfg.get("global_wavelength_shift_nm", 0.0)) + rng.normal(0.0, 0.01)
    gain = float(cfg.get("global_gain", 1.0)) * (1.0 + rng.normal(0.0, 0.015))
    y_shift = np.interp(wl, wl - shift, y, left=0.0, right=0.0)

    x = (wl - wl.mean()) / max((wl.max() - wl.min()) / 2.0, 1.0e-12)
    maxy = max(float(np.max(np.abs(y_shift))), 1.0)
    offset = float(cfg.get("baseline_offset_fraction_of_max", 0.0)) * maxy
    slope = float(cfg.get("baseline_slope_fraction_of_max", 0.0)) * maxy
    curvature = 0.25 * slope * (0.4 + 0.2 * chord_idx)
    baseline = offset + slope * x + curvature * (x ** 2 - np.mean(x ** 2))

    smooth_gain = 1.0 + 0.01 * x + 0.006 * np.sin(2.0 * np.pi * (x + 0.1 * chord_idx))
    y_work = gain * smooth_gain * y_shift + baseline

    sigma = (
        float(cfg.get("relative_noise_sigma", 0.0)) * np.maximum(np.abs(y_work), 0.1 * maxy)
        + float(cfg.get("additive_noise_fraction_of_max", 0.0)) * maxy
    )
    noise = rng.normal(0.0, sigma)
    return y_work + noise



def write_measurement_csv(path: Path, wl: np.ndarray, y: np.ndarray, comments: list[str]) -> None:
    metadata = dict(line.split(": ", 1) for line in comments)
    write_spectrum_csv(path, wl, y, metadata=metadata, wavelength_digits=6)



def build_one(bench_dir: Path) -> None:
    meta = load_yaml(bench_dir / "benchmark_meta.yaml")
    case_truth = bench_dir / "case_truth.yaml"
    model = OESCRModel.from_yaml(case_truth)
    result = model.predict()

    mm = meta.get("measurement_model", {})
    seed = int(mm.get("seed", 0))
    rng = np.random.default_rng(seed)

    meas_dir = bench_dir / "measurements"
    truth_dir = bench_dir / "forward_truth"
    meas_dir.mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)

    summary = {"benchmark_id": meta.get("benchmark_id"), "instrument_summaries": {}}

    for inst_id, chord_map in result.spectra.items():
        inst_summary = {}
        for chord_key, spec in chord_map.items():
            wl = np.asarray(spec["wavelength_nm"], dtype=float)
            y = np.asarray(spec["intensity"], dtype=float)
            chord_idx = int(chord_key.split("_")[-1])
            y_meas = apply_measurement_model(wl, y, mm, rng, chord_idx)

            comments = [
                f"benchmark_id: {meta.get('benchmark_id')}",
                f"title: {meta.get('title')}",
                f"source: {meta.get('source', {}).get('citation', '')}",
                f"kind: {meta.get('benchmark_kind')}",
                f"chord: {chord_key}",
                "note: literature-anchored measurement-like spectrum, not redistributed raw experimental data",
                f"output_basis: {spec['output_basis']}",
                f"output_unit: {spec['output_unit']}",
            ]
            write_measurement_csv(meas_dir / f"{chord_key}.csv", wl, y_meas, comments)
            write_measurement_csv(
                truth_dir / f"{inst_id}_{chord_key}.csv",
                wl,
                y,
                comments[:4]
                + [
                    "kind: noise-free forward truth",
                    f"output_basis: {spec['output_basis']}",
                    f"output_unit: {spec['output_unit']}",
                ],
            )
            inst_summary[chord_key] = {
                "max_truth": float(np.max(y)),
                "max_measurement": float(np.max(y_meas)),
                "mean_measurement": float(np.mean(y_meas)),
            }
        summary["instrument_summaries"][inst_id] = inst_summary

    save_yaml(summary, bench_dir / "measurement_summary.yaml")
    print(f"Built benchmark measurements in {bench_dir}")



def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("benchmarks", nargs="*", help="Benchmark directory names under examples/benchmarks")
    args = ap.parse_args()
    for bench in iter_benchmark_dirs(args.benchmarks):
        build_one(bench)


if __name__ == "__main__":
    main()
