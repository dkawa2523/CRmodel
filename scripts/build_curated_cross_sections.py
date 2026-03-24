#!/usr/bin/env python
from __future__ import annotations

from pathlib import Path
import numpy as np


def energy_grid(max_e=200.0):
    g1 = np.linspace(0.0, 1.0, 101)
    g2 = np.linspace(1.0, 20.0, 191)
    g3 = np.linspace(20.0, max_e, 181)
    return np.unique(np.concatenate([g1, g2, g3]))


def peaked_sigma(E, threshold, peak_e, peak_sigma, shape=1.0):
    E = np.asarray(E, float)
    out = np.zeros_like(E)
    delta = max(peak_e - threshold, 1.0e-6)
    x = (E - threshold) / delta
    m = x > 0
    xm = x[m]
    out[m] = peak_sigma * np.power(np.maximum(xm, 1.0e-12), shape) * np.exp(shape * (1.0 - xm))
    return out


def multi_peak(E, peaks):
    total = np.zeros_like(np.asarray(E, float))
    for p in peaks:
        total += peaked_sigma(E, p['threshold_eV'], p['peak_eV'], p['peak_sigma_m2'], p.get('shape', 1.0))
    return total


def write_csv(path: Path, energy_eV, sigma_m2, comments):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for c in comments:
            f.write(f"# {c}
")
        f.write('energy_eV,sigma_m2
')
        for e, s in zip(energy_eV, sigma_m2):
            f.write(f"{e:.6f},{s:.8e}
")


def main() -> None:
    out_root = Path(__file__).resolve().parents[1] / 'examples' / 'data' / 'cross_sections_curated'
    E200 = energy_grid(200.0)
    E100 = energy_grid(100.0)

    # Only a compact subset is rebuilt here; extend as needed.
    jobs = [
        (
            out_root / 'nf3' / 'NF3_total_ionization_curated.csv',
            E200,
            peaked_sigma(E200, 13.0, 140.0, 2.4e-20, 0.35),
            ['curve_class: literature_anchored_recommended_fit', 'process: e + NF3 -> total ionization'],
        ),
        (
            out_root / 'cl2' / 'Cl2_dissociation_curated.csv',
            E200,
            peaked_sigma(E200, 3.25, 10.0, 2.2e-20, 0.9),
            ['curve_class: literature_anchored_recommended_fit', 'process: e + Cl2 -> Cl + Cl + e'],
        ),
        (
            out_root / 'nf3' / 'NF3_attachment_Fminus_curated.csv',
            E100,
            multi_peak(E100, [
                dict(threshold_eV=0.01, peak_eV=0.05, peak_sigma_m2=3.0e-21, shape=0.35),
                dict(threshold_eV=0.10, peak_eV=2.0, peak_sigma_m2=1.6e-20, shape=1.0),
            ]),
            ['curve_class: literature_anchored_recommended_fit', 'process: e + NF3 -> F- + fragments'],
        ),
    ]
    for path, E, sigma, comments in jobs:
        write_csv(path, E, sigma, comments)
        print(f'wrote {path}')


if __name__ == '__main__':
    main()
