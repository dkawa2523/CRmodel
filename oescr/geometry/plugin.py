from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import Any, Dict, Mapping

import numpy as np

from ..io.yaml_loader import resolve_path
from ..plugins import PluginBase, PluginRegistry
from .axisym_shell import build_W_axisym_shell
from .asym_lowrank import apply_lowrank_asymmetry


GEOMETRY_PLUGINS: PluginRegistry["GeometryPlugin"] = PluginRegistry("geometry")


class GeometryPlugin(PluginBase):
    @abstractmethod
    def build_matrix(self, cfg: Mapping[str, Any]) -> np.ndarray:
        raise NotImplementedError

    def postprocess_chord_spectra(self, cfg: Mapping[str, Any], chord_spectra: np.ndarray) -> np.ndarray:
        return chord_spectra


class _ChordAverageGeometry(GeometryPlugin):
    kind = "chordavg"
    description = "Single chord that sums over one or more zones without spatial resolution." 
    config_schema = {
        "type": "object",
        "required": ["mode"],
        "properties": {
            "mode": {"const": "chordavg"},
            "n_shells": {"type": "integer", "minimum": 1},
        },
        "additionalProperties": True,
    }

    def build_matrix(self, cfg: Mapping[str, Any]) -> np.ndarray:
        geom = cfg.get("geometry", cfg)
        n_shells = int(geom.get("n_shells", 1))
        return np.ones((1, n_shells), dtype=float)


class _AxisymmetricShellGeometry(GeometryPlugin):
    kind = "axisym_shell"
    description = "Axisymmetric shell forward projector for same-height radial chords."
    config_schema = {
        "type": "object",
        "required": ["mode", "chord_r_m", "chamber_radius_m", "n_shells"],
        "properties": {
            "mode": {"const": "axisym_shell"},
            "chord_r_m": {"type": "array", "items": {"type": "number", "minimum": 0}, "minItems": 1},
            "chamber_radius_m": {"type": "number", "exclusiveMinimum": 0},
            "n_shells": {"type": "integer", "minimum": 1},
        },
        "additionalProperties": True,
    }

    def build_matrix(self, cfg: Mapping[str, Any]) -> np.ndarray:
        geom = cfg.get("geometry", cfg)
        return build_W_axisym_shell(
            chord_r_m=list(geom["chord_r_m"]),
            radius_m=float(geom["chamber_radius_m"]),
            n_shells=int(geom["n_shells"]),
        )


class _AsymLowRankGeometry(_AxisymmetricShellGeometry):
    kind = "asym_lowrank"
    description = "Axisymmetric shell projector with optional first azimuthal correction mode."
    config_schema = {
        "type": "object",
        "required": ["mode", "chord_r_m", "chamber_radius_m", "n_shells"],
        "properties": {
            "mode": {"const": "asym_lowrank"},
            "chord_r_m": {"type": "array", "items": {"type": "number", "minimum": 0}, "minItems": 1},
            "chamber_radius_m": {"type": "number", "exclusiveMinimum": 0},
            "n_shells": {"type": "integer", "minimum": 1},
            "chord_angles_rad": {"type": "array", "items": {"type": "number"}},
            "mode1_amplitude": {"type": "array", "items": {"type": "number"}},
        },
        "additionalProperties": True,
    }

    def postprocess_chord_spectra(self, cfg: Mapping[str, Any], chord_spectra: np.ndarray) -> np.ndarray:
        geom = cfg.get("geometry", cfg)
        chord_angles = np.asarray(geom.get("chord_angles_rad", []), dtype=float)
        mode1 = np.asarray(geom.get("mode1_amplitude", [0.0] * chord_spectra.shape[1]), dtype=float)
        return apply_lowrank_asymmetry(chord_spectra, chord_angles, mode1)


class _UserFieldGeometry(GeometryPlugin):
    kind = "user_field"
    description = "User-supplied forward matrix via inline weights_matrix or CSV weights_file."
    config_schema = {
        "type": "object",
        "required": ["mode"],
        "properties": {
            "mode": {"const": "user_field"},
            "weights_file": {"type": "string"},
            "weights_matrix": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "number"}},
                "minItems": 1,
            },
        },
        "additionalProperties": True,
    }

    def _validate_semantics(self, cfg: Mapping[str, Any]) -> None:
        if "weights_file" not in cfg and "weights_matrix" not in cfg:
            raise ValueError("Geometry mode 'user_field' requires weights_file or weights_matrix.")

    def build_matrix(self, cfg: Mapping[str, Any]) -> np.ndarray:
        geom = cfg.get("geometry", cfg)
        if "weights_matrix" in geom:
            arr = np.asarray(geom["weights_matrix"], dtype=float)
        else:
            path = resolve_path(cfg, str(geom["weights_file"]))
            arr = np.loadtxt(Path(path), delimiter=",")
        if arr.ndim != 2:
            raise ValueError("User-field geometry weights must be a 2D matrix.")
        return np.asarray(arr, dtype=float)


GEOMETRY_PLUGINS.register(_ChordAverageGeometry())
GEOMETRY_PLUGINS.register(_AxisymmetricShellGeometry())
GEOMETRY_PLUGINS.register(_AsymLowRankGeometry())
GEOMETRY_PLUGINS.register(_UserFieldGeometry())


def get_geometry_plugin(cfg: Mapping[str, Any]) -> GeometryPlugin:
    geom = cfg.get("geometry", cfg)
    kind = str(geom.get("mode", "axisym_shell"))
    plugin = GEOMETRY_PLUGINS.get(kind)
    plugin.validate_config(geom)
    return plugin
