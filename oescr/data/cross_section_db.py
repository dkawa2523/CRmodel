
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import numpy as np


@dataclass
class CrossSection:
    energy_eV: np.ndarray
    sigma_m2: np.ndarray
    path: str


class CrossSectionLibrary:
    def __init__(self) -> None:
        self._cache: Dict[str, CrossSection] = {}

    def load(self, path: str | Path) -> CrossSection:
        path = str(Path(path).resolve())
        if path in self._cache:
            return self._cache[path]

        energy = []
        sigma = []
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(
                row for row in f if not row.lstrip().startswith("#")
            )
            for row in reader:
                energy.append(float(row["energy_eV"]))
                sigma.append(float(row["sigma_m2"]))
        cs = CrossSection(
            energy_eV=np.asarray(energy, dtype=float),
            sigma_m2=np.asarray(sigma, dtype=float),
            path=path,
        )
        self._cache[path] = cs
        return cs
