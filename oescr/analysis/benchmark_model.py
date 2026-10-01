"""Data records shared by benchmark metric and rendering layers."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ChordSeries:
    wavelength_nm: np.ndarray
    measurement: np.ndarray
    prediction_raw: np.ndarray
    prediction_fit: np.ndarray
