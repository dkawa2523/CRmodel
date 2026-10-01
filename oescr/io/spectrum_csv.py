"""CSV serialization for spectra with explicit quantity metadata."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable, Mapping


def write_spectrum_csv(
    path: str | Path,
    wavelength_nm: Iterable[float],
    intensity: Iterable[float],
    *,
    metadata: Mapping[str, Any] | None = None,
    wavelength_digits: int = 8,
) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as stream:
        for key, value in (metadata or {}).items():
            stream.write(f"# {key}: {value}\n")
        writer = csv.writer(stream)
        writer.writerow(["wavelength_nm", "intensity"])
        for wavelength, value in zip(wavelength_nm, intensity, strict=True):
            writer.writerow([f"{float(wavelength):.{wavelength_digits}f}", f"{float(value):.12e}"])
