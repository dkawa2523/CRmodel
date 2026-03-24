
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict

import numpy as np


def load_profile_csv(path: str | Path) -> Dict[str, np.ndarray]:
    wl = []
    val = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(row for row in f if not row.lstrip().startswith("#"))
        for row in reader:
            wl.append(float(row["wavelength_nm"]))
            val.append(float(row["relative_intensity"]))
    wl_arr = np.asarray(wl, dtype=float)
    val_arr = np.asarray(val, dtype=float)
    area = np.trapezoid(np.maximum(val_arr, 0.0), wl_arr)
    if area > 0.0:
        val_arr = val_arr / area
    return {"wavelength_nm": wl_arr, "relative_intensity": val_arr}
