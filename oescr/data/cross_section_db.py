
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import numpy as np


@dataclass
class CrossSection:
    energy_eV: np.ndarray
    sigma_m2: np.ndarray
    path: str
    sha256: str
    metadata: Dict[str, str]

    @property
    def energy_range_eV(self) -> tuple[float, float]:
        return float(self.energy_eV[0]), float(self.energy_eV[-1])


def _parse_metadata(lines: list[str]) -> Dict[str, str]:
    metadata: Dict[str, str] = {}
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#") and ":" in stripped:
            key, value = stripped[1:].split(":", 1)
            metadata[key.strip()] = value.strip()
    return metadata


def _parse_table(lines: list[str], path: str) -> tuple[np.ndarray, np.ndarray]:
    reader = csv.DictReader(line for line in lines if not line.lstrip().startswith("#"))
    if reader.fieldnames is None or not {"energy_eV", "sigma_m2"}.issubset(reader.fieldnames):
        raise ValueError(f"Cross section '{path}' must contain energy_eV and sigma_m2 columns.")
    energy = []
    sigma = []
    for row in reader:
        energy.append(float(row["energy_eV"]))
        sigma.append(float(row["sigma_m2"]))
    return np.asarray(energy, dtype=float), np.asarray(sigma, dtype=float)


def _validate_table(energy_eV: np.ndarray, sigma_m2: np.ndarray, path: str) -> None:
    if len(energy_eV) < 2:
        raise ValueError(f"Cross section '{path}' must contain at least two data rows.")
    if not np.all(np.isfinite(energy_eV)) or not np.all(np.isfinite(sigma_m2)):
        raise ValueError(f"Cross section '{path}' contains non-finite values.")
    if np.any(energy_eV < 0.0):
        raise ValueError(f"Cross section '{path}' contains negative energy.")
    if np.any(np.diff(energy_eV) <= 0.0):
        raise ValueError(f"Cross section '{path}' energy_eV must be strictly increasing without duplicates.")
    if np.any(sigma_m2 < 0.0):
        raise ValueError(f"Cross section '{path}' contains negative sigma_m2.")


class CrossSectionLibrary:
    def __init__(self) -> None:
        self._cache: Dict[str, CrossSection] = {}

    def load(self, path: str | Path) -> CrossSection:
        path = str(Path(path).resolve())
        if path in self._cache:
            return self._cache[path]

        raw = Path(path).read_bytes()
        lines = raw.decode("utf-8").splitlines()
        metadata = _parse_metadata(lines)
        energy_array, sigma_array = _parse_table(lines, path)
        _validate_table(energy_array, sigma_array, path)

        cs = CrossSection(
            energy_eV=energy_array,
            sigma_m2=sigma_array,
            path=path,
            sha256=hashlib.sha256(raw).hexdigest(),
            metadata=metadata,
        )
        self._cache[path] = cs
        return cs
