#!/usr/bin/env python
"""Prepare or execute the independent Daly et al. multi-gas surrogate pilot.

The released TensorFlow models are treated as an external empirical reference:
this producer deliberately imports no OESCR modules.  Its output is useful for
multi-gas spectral preflight, but is not a substitute for held-out measured
spectra or an independent electron-state reference.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

REFERENCE_FORMAT = "oescr_daly_surrogate_pilot/v1"
SOURCE_URL = "https://github.com/gregdaly/generative_modelling_for_optical_plasma_diagnostics"
INPUT_COLUMNS = (
    "icp_power_W",
    "table_power_W",
    "ar_flow_sccm",
    "o2_flow_sccm",
    "cf4_flow_sccm",
    "sf6_flow_sccm",
    "pressure_mTorr",
)
CONVERSION_ARRAY = np.asarray([3000.0, 600.0, 140.0, 100.0, 168.0, 104.0, 100.0])
GAS_RANGES: Mapping[str, Mapping[str, tuple[float, float]]] = {
    "Ar": {
        "icp_power_W": (480.0, 3000.0),
        "table_power_W": (0.0, 600.0),
        "ar_flow_sccm": (3.5, 70.0),
        "pressure_mTorr": (5.0, 90.0),
    },
    "O2": {
        "icp_power_W": (600.0, 3000.0),
        "table_power_W": (30.0, 600.0),
        "o2_flow_sccm": (2.5, 50.0),
        "pressure_mTorr": (5.0, 90.0),
    },
    "Ar_O2": {
        "icp_power_W": (750.0, 3000.0),
        "table_power_W": (30.0, 540.0),
        "ar_flow_sccm": (2.5, 50.0),
        "o2_flow_sccm": (2.5, 50.0),
        "pressure_mTorr": (5.0, 80.0),
    },
    "CF4_O2": {
        "icp_power_W": (600.0, 3000.0),
        "table_power_W": (30.0, 600.0),
        "o2_flow_sccm": (2.5, 50.0),
        "cf4_flow_sccm": (4.2, 84.0),
        "pressure_mTorr": (4.0, 90.0),
    },
    "SF6_O2": {
        "icp_power_W": (750.0, 3000.0),
        "table_power_W": (30.0, 600.0),
        "o2_flow_sccm": (2.5, 50.0),
        "sf6_flow_sccm": (2.6, 52.0),
        "pressure_mTorr": (5.0, 80.0),
    },
}
_PERMUTATIONS = {
    "icp_power_W": (1, 0),
    "table_power_W": (7, 3),
    "ar_flow_sccm": (11, 5),
    "o2_flow_sccm": (13, 7),
    "cf4_flow_sccm": (17, 11),
    "sf6_flow_sccm": (19, 13),
    "pressure_mTorr": (23, 17),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_identity(root: Path) -> dict[str, Any]:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256(path).encode("ascii"))
        digest.update(b"\n")
    return {"path": str(root.resolve()), "file_count": len(files), "tree_sha256": digest.hexdigest()}


def _wavelengths_nm() -> np.ndarray:
    calibration = np.asarray(
        [
            [2016, 2137, 2254, 2690, 1967, 1879, 1452],
            [777.194, 811.5311, 844.636, 965.7786, 763.5106, 738.3980, 615.818],
        ],
        dtype=float,
    )
    polynomial = np.polynomial.Polynomial.fit(
        calibration[0], calibration[1], 3, domain=[0, 4095], window=[0, 4095]
    )
    wavelengths = polynomial.linspace(4096, domain=[0, 4095])[1][44:-980]
    if wavelengths.shape != (3072,) or np.any(np.diff(wavelengths) <= 0.0):
        raise RuntimeError("The published Daly wavelength calibration did not produce 3072 increasing bins.")
    return wavelengths


def _axis_fraction(index: int, column: str, count: int) -> float:
    multiplier, shift = _PERMUTATIONS[column]
    while math.gcd(multiplier, count) != 1:
        multiplier += 2
    rank = (multiplier * index + shift) % count
    return rank / (count - 1)


def _build_conditions(per_gas: int) -> list[dict[str, str | float | int]]:
    if per_gas < 3:
        raise ValueError("At least three setpoints per gas are required to cover low, middle, and high values.")
    conditions: list[dict[str, str | float | int]] = []
    for gas_system, ranges in GAS_RANGES.items():
        for index in range(per_gas):
            condition: dict[str, str | float | int] = {
                "condition_id": f"{gas_system.lower()}_{index:03d}",
                "gas_system": gas_system,
                "condition_index": index,
            }
            for column in INPUT_COLUMNS:
                value = 0.0
                if column in ranges:
                    low, high = ranges[column]
                    fraction = _axis_fraction(index, column, per_gas)
                    value = low + fraction * (high - low)
                condition[column] = value
            conditions.append(condition)
    return conditions


def _write_conditions(path: Path, conditions: Sequence[Mapping[str, str | float | int]]) -> None:
    fieldnames = ["condition_id", "gas_system", "condition_index", *INPUT_COLUMNS]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(conditions)


def _write_wavelengths(path: Path, wavelengths: np.ndarray) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["pixel_index", "wavelength_nm"])
        writer.writerows((index, f"{wavelength:.9f}") for index, wavelength in enumerate(wavelengths))


def _condition_array(conditions: Sequence[Mapping[str, str | float | int]]) -> np.ndarray:
    return np.asarray([[float(condition[column]) for column in INPUT_COLUMNS] for condition in conditions])


def _write_spectra(
    spectra_dir: Path,
    conditions: Sequence[Mapping[str, str | float | int]],
    wavelengths: np.ndarray,
    spectra: np.ndarray,
) -> None:
    spectra_dir.mkdir(parents=True, exist_ok=True)
    for condition, intensity in zip(conditions, spectra, strict=True):
        path = spectra_dir / f"{condition['condition_id']}.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["wavelength_nm", "intensity"])
            writer.writerows(
                (f"{wavelength:.9f}", f"{value:.9e}")
                for wavelength, value in zip(wavelengths, intensity, strict=True)
            )


def _render_overview(
    path: Path,
    conditions: Sequence[Mapping[str, str | float | int]],
    wavelengths: np.ndarray,
    spectra: np.ndarray,
    per_gas: int,
) -> None:
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(len(GAS_RANGES), 1, figsize=(10.0, 11.0), sharex=True)
    for gas_index, (gas_system, axis) in enumerate(zip(GAS_RANGES, axes, strict=True)):
        start = gas_index * per_gas
        ranges = GAS_RANGES[gas_system]
        distances = []
        for offset in range(per_gas):
            condition = conditions[start + offset]
            distance = sum(
                ((float(condition[column]) - low) / (high - low) - 0.5) ** 2
                for column, (low, high) in ranges.items()
            )
            distances.append(distance)
        row = start + int(np.argmin(distances))
        condition = conditions[row]
        axis.plot(wavelengths, spectra[row], color="#2457A7", linewidth=0.9)
        axis.set_ylabel(f"{gas_system}\nnormalized\nintensity")
        axis.text(
            0.99,
            0.9,
            f"ICP {float(condition['icp_power_W']):.0f} W; "
            f"{float(condition['pressure_mTorr']):.1f} mTorr",
            transform=axis.transAxes,
            ha="right",
            va="top",
            fontsize=8,
        )
        axis.grid(alpha=0.18)
    axes[-1].set_xlabel("Wavelength (nm)")
    figure.suptitle("Daly released surrogate (not measured data): representative multi-gas spectra")
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _execute(
    tool_encoder_dir: Path,
    spectra_decoder_dir: Path,
    conditions: Sequence[Mapping[str, str | float | int]],
) -> tuple[np.ndarray, str]:
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
    # TensorFlow is an optional dependency of this external producer and is
    # intentionally absent from the OESCR runtime environment.
    tf = importlib.import_module("tensorflow")

    tool_encoder = tf.keras.models.load_model(tool_encoder_dir, compile=False)
    spectra_decoder = tf.keras.models.load_model(spectra_decoder_dir, compile=False)
    scaled = _condition_array(conditions) / CONVERSION_ARRAY
    latent = tool_encoder(scaled, training=False)
    predicted = np.asarray(spectra_decoder(latent, training=False), dtype=float)
    if predicted.shape != (len(conditions), 3072, 1):
        raise RuntimeError(f"Unexpected Daly spectrum shape: {predicted.shape}")
    spectra = predicted[:, :, 0]
    if not np.all(np.isfinite(spectra)):
        raise RuntimeError("Daly surrogate returned non-finite intensities.")
    if np.min(spectra) < 0.0 or np.max(spectra) > 1.0:
        raise RuntimeError("Daly surrogate violated its published sigmoid output range [0, 1].")
    return spectra, str(tf.__version__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--setpoints-per-gas", type=int, default=30)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--tool-encoder-dir", type=Path)
    parser.add_argument("--spectra-decoder-dir", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.execute and (args.tool_encoder_dir is None or args.spectra_decoder_dir is None):
        parser.error("--tool-encoder-dir and --spectra-decoder-dir are required with --execute")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    conditions = _build_conditions(args.setpoints_per_gas)
    wavelengths = _wavelengths_nm()
    conditions_file = output_dir / "conditions.csv"
    wavelengths_file = output_dir / "wavelengths.csv"
    _write_conditions(conditions_file, conditions)
    _write_wavelengths(wavelengths_file, wavelengths)

    manifest: dict[str, Any] = {
        "format": REFERENCE_FORMAT,
        "reference_model": {
            "name": "Daly et al. released tool encoder and spectrum decoder",
            "source_url": SOURCE_URL,
            "source_revision": args.source_revision,
        },
        "producer": {"script": Path(__file__).name, "imports_oescr": False},
        "design": {
            "method": "deterministic_stratified_permutation",
            "gas_systems": list(GAS_RANGES),
            "setpoints_per_gas": args.setpoints_per_gas,
            "condition_count": len(conditions),
            "input_order": list(INPUT_COLUMNS),
            "published_ranges": GAS_RANGES,
        },
        "inputs": {
            "conditions": {"path": conditions_file.name, "sha256": _sha256(conditions_file)},
            "wavelengths": {"path": wavelengths_file.name, "sha256": _sha256(wavelengths_file)},
        },
        "result": {"status": "not_executed"},
        "evidence_boundary": {
            "supports": ["multi-gas spectral preflight", "OESCR emitter and wavelength coverage assessment"],
            "does_not_support": [
                "held-out measured-spectrum validation",
                "electron temperature accuracy",
                "electron density accuracy",
                "EEDF accuracy",
            ],
        },
    }

    if args.execute:
        tool_encoder_dir = args.tool_encoder_dir.resolve()
        spectra_decoder_dir = args.spectra_decoder_dir.resolve()
        if not tool_encoder_dir.is_dir() or not spectra_decoder_dir.is_dir():
            parser.error("Both released model directories must exist.")
        spectra, tensorflow_version = _execute(tool_encoder_dir, spectra_decoder_dir, conditions)
        spectra_dir = output_dir / "spectra"
        _write_spectra(spectra_dir, conditions, wavelengths, spectra)
        overview_file = output_dir / "representative_spectra.png"
        _render_overview(overview_file, conditions, wavelengths, spectra, args.setpoints_per_gas)
        manifest["model_inputs"] = {
            "tool_encoder": _tree_identity(tool_encoder_dir),
            "spectra_decoder": _tree_identity(spectra_decoder_dir),
        }
        manifest["result"] = {
            "status": "completed",
            "tensorflow_version": tensorflow_version,
            "spectra": _tree_identity(spectra_dir),
            "intensity_min": float(np.min(spectra)),
            "intensity_max": float(np.max(spectra)),
            "overview": {"path": overview_file.name, "sha256": _sha256(overview_file)},
        }

    manifest_file = output_dir / "run_manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"conditions: {conditions_file}")
    print(f"manifest:   {manifest_file}")
    print(f"status:     {manifest['result']['status']}")


if __name__ == "__main__":
    main()
