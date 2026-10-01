"""Dimensional transforms from chord spectral radiance to instrument output."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
from scipy import constants as const

_OUTPUT_CONTRACTS = {
    "spectral_radiance": (
        "spectral_radiance_W_m-2_sr-1_nm-1",
        "W_m-2_sr-1_nm-1",
    ),
    "collected_spectral_power": (
        "spectral_power_W_nm-1",
        "W_nm-1",
    ),
    "photoelectron_spectrum": (
        "photoelectrons_nm-1",
        "photoelectron_nm-1",
    ),
}


def _resolve_output_contract(calibration: Mapping[str, Any]) -> tuple[str, str, str]:
    kind = str(calibration.get("kind", ""))
    if kind not in _OUTPUT_CONTRACTS:
        raise ValueError(
            f"Unsupported calibration kind '{kind}'. Expected one of {sorted(_OUTPUT_CONTRACTS)}."
        )
    if calibration.get("input_basis") != "spectral_radiance":
        raise ValueError("Calibration input_basis must be 'spectral_radiance'.")
    output_basis, expected_unit = _OUTPUT_CONTRACTS[kind]
    output_unit = str(calibration.get("output_unit", ""))
    if output_unit != expected_unit:
        raise ValueError(
            f"Calibration kind '{kind}' requires output_unit='{expected_unit}', got '{output_unit}'."
        )
    return kind, output_basis, output_unit


def _collection_terms(calibration: Mapping[str, Any], kind: str) -> tuple[float, float, float]:
    area = float(calibration.get("collection_area_m2", 1.0))
    solid_angle = float(calibration.get("collection_solid_angle_sr", 1.0))
    viewing_factor = float(calibration.get("viewing_factor", 1.0))
    if kind != "spectral_radiance":
        if "collection_area_m2" not in calibration or area <= 0.0:
            raise ValueError(f"Calibration kind '{kind}' requires collection_area_m2 > 0.")
        if "collection_solid_angle_sr" not in calibration or not 0.0 < solid_angle <= 4.0 * np.pi:
            raise ValueError(
                f"Calibration kind '{kind}' requires 0 < collection_solid_angle_sr <= 4*pi."
            )
    if not 0.0 < viewing_factor <= 1.0:
        raise ValueError("Calibration viewing_factor must be in (0, 1].")
    return area, solid_angle, viewing_factor


def _detection_terms(calibration: Mapping[str, Any], kind: str) -> tuple[float, float]:
    integration_time = float(calibration.get("integration_time_s", 1.0))
    quantum_efficiency = float(calibration.get("quantum_efficiency", 1.0))
    if kind != "photoelectron_spectrum":
        return integration_time, quantum_efficiency
    if "integration_time_s" not in calibration or integration_time <= 0.0:
        raise ValueError("photoelectron_spectrum calibration requires integration_time_s > 0.")
    if "quantum_efficiency" not in calibration or not 0.0 <= quantum_efficiency <= 1.0:
        raise ValueError("photoelectron_spectrum calibration requires quantum_efficiency in [0, 1].")
    return integration_time, quantum_efficiency


@dataclass(frozen=True)
class CalibrationTransform:
    """Validated transform applied after LSF and dimensionless throughput."""

    kind: str
    absolute: bool
    output_basis: str
    output_unit: str
    reference: str | None
    collection_area_m2: float = 1.0
    collection_solid_angle_sr: float = 1.0
    viewing_factor: float = 1.0
    integration_time_s: float = 1.0
    quantum_efficiency: float = 1.0
    relative_standard_uncertainty: float = 0.0

    @classmethod
    def relative(cls) -> "CalibrationTransform":
        return cls(
            kind="relative",
            absolute=False,
            output_basis="relative_instrument_signal",
            output_unit="arb",
            reference=None,
        )

    @classmethod
    def from_instrument_config(cls, instrument_cfg: Mapping[str, Any]) -> "CalibrationTransform":
        calibration = instrument_cfg.get("calibration")
        if calibration is None:
            return cls.relative()
        if not isinstance(calibration, Mapping):
            raise ValueError("instrument.calibration must be a mapping.")

        kind, output_basis, output_unit = _resolve_output_contract(calibration)
        absolute = bool(calibration.get("absolute", False))
        reference = str(calibration.get("reference", "")).strip() or None
        if absolute and reference is None:
            raise ValueError("Absolute calibration requires a non-empty reference.")
        area, solid_angle, viewing_factor = _collection_terms(calibration, kind)
        integration_time, quantum_efficiency = _detection_terms(calibration, kind)
        relative_uncertainty = float(calibration.get("relative_standard_uncertainty", 0.0))
        if relative_uncertainty < 0.0:
            raise ValueError("Calibration relative_standard_uncertainty must be >= 0.")

        return cls(
            kind=kind,
            absolute=absolute,
            output_basis=output_basis,
            output_unit=output_unit,
            reference=reference,
            collection_area_m2=area,
            collection_solid_angle_sr=solid_angle,
            viewing_factor=viewing_factor,
            integration_time_s=integration_time,
            quantum_efficiency=quantum_efficiency,
            relative_standard_uncertainty=relative_uncertainty,
        )

    def apply(self, wavelength_nm: np.ndarray, spectral_radiance: np.ndarray) -> np.ndarray:
        values = np.asarray(spectral_radiance, dtype=float)
        if self.kind in {"relative", "spectral_radiance"}:
            return values.copy()

        etendue_m2_sr = self.collection_area_m2 * self.collection_solid_angle_sr * self.viewing_factor
        spectral_power = values * etendue_m2_sr
        if self.kind == "collected_spectral_power":
            return spectral_power

        photon_energy_J = const.h * const.c / (np.asarray(wavelength_nm, dtype=float) * 1.0e-9)
        return spectral_power * self.integration_time_s * self.quantum_efficiency / photon_energy_J
