"""Measurement loading, uncertainty validation, and residual whitening."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from ..instrument.calibration import CalibrationTransform
from ..io.yaml_loader import resolve_path


@dataclass
class Measurement:
    wavelength_nm: np.ndarray
    intensity: np.ndarray
    sigma: np.ndarray | None = None
    covariance: np.ndarray | None = None
    covariance_cholesky: np.ndarray | None = None
    metadata: Dict[str, str] | None = None
    feature_covariance: "FeatureCovariance | None" = None
    calibration_relative_standard_uncertainty: float = 0.0
    effective_covariance_cholesky: np.ndarray | None = None


@dataclass(frozen=True)
class FeatureCovariance:
    names: tuple[str, ...]
    covariance: np.ndarray
    cholesky: np.ndarray


def _factor_covariance(
    covariance: np.ndarray,
    size: int,
    label: str,
) -> tuple[np.ndarray, np.ndarray]:
    matrix = np.atleast_2d(np.asarray(covariance, dtype=float))
    if matrix.shape != (size, size):
        raise ValueError(f"{label} has shape {matrix.shape}; expected {(size, size)}.")
    if np.any(~np.isfinite(matrix)):
        raise ValueError(f"{label} must contain only finite values.")
    scale = max(float(np.max(np.abs(np.diag(matrix)))), 1.0)
    if not np.allclose(matrix, matrix.T, rtol=1.0e-10, atol=1.0e-12 * scale):
        raise ValueError(f"{label} must be symmetric.")
    try:
        cholesky = np.linalg.cholesky(matrix)
    except np.linalg.LinAlgError as exc:
        raise ValueError(f"{label} must be positive definite.") from exc
    return matrix, cholesky


def _load_covariance_csv(path: str | Path, size: int) -> tuple[np.ndarray, np.ndarray]:
    covariance = np.loadtxt(path, delimiter=",", dtype=float)
    return _factor_covariance(covariance, size, f"Measurement covariance '{path}'")


def _feature_covariance_from_config(item: Dict[str, Any]) -> FeatureCovariance | None:
    config = item.get("feature_covariance")
    if config is None:
        return None
    names = tuple(str(name) for name in config["names"])
    if len(set(names)) != len(names):
        raise ValueError("Feature covariance names must be unique.")
    covariance, cholesky = _factor_covariance(
        np.asarray(config["matrix"], dtype=float),
        len(names),
        "Feature covariance",
    )
    return FeatureCovariance(names=names, covariance=covariance, cholesky=cholesky)


def _read_measurement_metadata(path: str | Path) -> Dict[str, str]:
    metadata: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as stream:
        for line in stream:
            stripped = line.strip()
            if not stripped.startswith("#"):
                continue
            key, separator, value = stripped[1:].partition(":")
            if separator:
                metadata[key.strip()] = value.strip()
    return metadata


def _read_measurement_columns(path: str | Path) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    wavelength = []
    intensity = []
    sigma = []
    with open(path, "r", encoding="utf-8") as stream:
        reader = csv.DictReader(row for row in stream if not row.lstrip().startswith("#"))
        for row in reader:
            wavelength.append(float(row["wavelength_nm"]))
            intensity.append(float(row["intensity"]))
            if row.get("sigma") not in {None, ""}:
                sigma.append(float(row["sigma"]))
    sigma_array = np.asarray(sigma, dtype=float) if sigma else None
    return np.asarray(wavelength, dtype=float), np.asarray(intensity, dtype=float), sigma_array


def _validate_pointwise_sigma(path: str | Path, sigma: np.ndarray | None, size: int) -> None:
    if sigma is None:
        return
    if len(sigma) != size or np.any(~np.isfinite(sigma)) or np.any(sigma <= 0.0):
        raise ValueError(f"Measurement '{path}' sigma values must be finite, positive, and complete.")


def load_measurement_csv(
    path: str | Path,
    covariance_path: str | Path | None = None,
) -> Measurement:
    wavelength, intensity, sigma_array = _read_measurement_columns(path)
    metadata = _read_measurement_metadata(path)
    _validate_pointwise_sigma(path, sigma_array, len(wavelength))
    if sigma_array is not None and covariance_path is not None:
        raise ValueError(f"Measurement '{path}' cannot declare both pointwise sigma and covariance.")
    covariance = None
    cholesky = None
    if covariance_path is not None:
        covariance, cholesky = _load_covariance_csv(covariance_path, len(wavelength))
    return Measurement(wavelength, intensity, sigma_array, covariance, cholesky, metadata)


def _measurement_paths(inv_cfg: Dict[str, Any], item: Dict[str, Any]) -> List[Path]:
    if "files_glob" in item:
        pattern = str(item["files_glob"])
        base = Path(inv_cfg.get("__base_dir__", "."))
        return sorted(base.glob(pattern))
    if "files" in item:
        return [resolve_path(inv_cfg, path) for path in item["files"]]
    if "file" in item:
        return [resolve_path(inv_cfg, item["file"])]
    raise ValueError(f"Measurement entry must define file/files/files_glob: {item}")


def _covariance_paths(
    inv_cfg: Dict[str, Any],
    item: Dict[str, Any],
    measurement_count: int,
) -> List[Path | None]:
    if "covariance_file" in item:
        if measurement_count != 1:
            raise ValueError("covariance_file can only be used with one measurement file.")
        return [resolve_path(inv_cfg, item["covariance_file"])]
    if "covariance_files" in item:
        paths = [resolve_path(inv_cfg, path) for path in item["covariance_files"]]
        if len(paths) != measurement_count:
            raise ValueError(
                "covariance_files must have the same number and order as the resolved measurement files."
            )
        return paths
    return [None] * measurement_count


def _validate_absolute_measurement_metadata(
    instrument_id: str,
    measurements: List[Measurement],
    instrument_cfg: Dict[str, Any],
) -> None:
    calibration = CalibrationTransform.from_instrument_config(instrument_cfg)
    expected = {
        "output_basis": calibration.output_basis,
        "output_unit": calibration.output_unit,
        "calibration_reference": str(calibration.reference),
    }
    for index, measurement in enumerate(measurements):
        metadata = measurement.metadata or {}
        mismatches = [key for key, value in expected.items() if metadata.get(key) != value]
        if mismatches:
            raise ValueError(
                f"Absolute measurement {instrument_id}[{index}] metadata does not match the instrument "
                f"calibration for: {', '.join(mismatches)}."
            )
        relative_uncertainty = calibration.relative_standard_uncertainty
        measurement.calibration_relative_standard_uncertainty = relative_uncertainty
        if relative_uncertainty <= 0.0:
            continue
        if measurement.covariance is not None:
            base_covariance = measurement.covariance
        elif measurement.sigma is not None:
            base_covariance = np.diag(measurement.sigma ** 2)
        else:
            raise ValueError(
                f"Absolute measurement {instrument_id}[{index}] has calibration uncertainty but no "
                "pointwise sigma or measurement covariance."
            )
        calibration_error = relative_uncertainty * measurement.intensity
        effective_covariance = base_covariance + np.outer(calibration_error, calibration_error)
        _, measurement.effective_covariance_cholesky = _factor_covariance(
            effective_covariance,
            len(measurement.intensity),
            f"Effective covariance for absolute measurement {instrument_id}[{index}]",
        )


def load_measurements(
    inv_cfg: Dict[str, Any],
    instrument_cfgs: List[Dict[str, Any]] | None = None,
) -> Dict[str, List[Measurement]]:
    out: Dict[str, List[Measurement]] = {}
    instrument_map = {str(item["id"]): item for item in (instrument_cfgs or [])}
    absolute = inv_cfg.get("inference_mode") == "calibrated_absolute"
    for item in inv_cfg.get("measurements", []):
        instrument_id = str(item["instrument_id"])
        paths = _measurement_paths(inv_cfg, item)
        covariance_paths = _covariance_paths(inv_cfg, item, len(paths))
        loaded = [
            load_measurement_csv(path, covariance_path)
            for path, covariance_path in zip(paths, covariance_paths, strict=True)
        ]
        feature_covariance = _feature_covariance_from_config(item)
        for measurement in loaded:
            measurement.feature_covariance = feature_covariance
        if absolute:
            if instrument_id not in instrument_map:
                raise ValueError(
                    f"No compiled instrument configuration found for absolute measurement '{instrument_id}'."
                )
            _validate_absolute_measurement_metadata(instrument_id, loaded, instrument_map[instrument_id])
        out.setdefault(instrument_id, []).extend(loaded)
    return out


def spectrum_residuals(measurement: Measurement, predicted: np.ndarray) -> np.ndarray:
    delta = np.asarray(predicted, dtype=float) - measurement.intensity
    if measurement.effective_covariance_cholesky is not None:
        return np.linalg.solve(measurement.effective_covariance_cholesky, delta)
    if measurement.covariance_cholesky is not None:
        return np.linalg.solve(measurement.covariance_cholesky, delta)
    if measurement.sigma is not None:
        return delta / measurement.sigma
    scale = max(float(np.std(measurement.intensity)), 1.0e-12)
    return delta / scale


def whiten_feature_residuals(
    measurement: Measurement,
    residuals_by_name: Dict[str, float],
) -> np.ndarray:
    feature_covariance = measurement.feature_covariance
    if feature_covariance is None:
        return np.zeros(0, dtype=float)
    missing = [name for name in feature_covariance.names if name not in residuals_by_name]
    if missing:
        raise ValueError(
            "Feature covariance references residuals that were not produced; "
            f"check enabled/low-signal windows and named ratio pairs: {', '.join(missing)}."
        )
    residual = np.asarray([residuals_by_name[name] for name in feature_covariance.names], dtype=float)
    return np.linalg.solve(feature_covariance.cholesky, residual)
