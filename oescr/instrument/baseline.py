from __future__ import annotations

from abc import abstractmethod
from typing import Any, Dict, Mapping

import numpy as np

from ..plugins import PluginBase, PluginRegistry


BASELINE_PLUGINS: PluginRegistry["BaselinePlugin"] = PluginRegistry("baseline")


class BaselinePlugin(PluginBase):
    @abstractmethod
    def evaluate(self, cfg: Mapping[str, Any], wavelength_nm: np.ndarray) -> np.ndarray:
        raise NotImplementedError


class _ConstantBaseline(BaselinePlugin):
    kind = "constant"
    description = "Constant baseline offset."
    config_schema = {
        "type": "object",
        "required": ["kind", "offset"],
        "properties": {
            "kind": {"const": "constant"},
            "offset": {"type": "number"},
        },
        "additionalProperties": False,
    }

    def evaluate(self, cfg: Mapping[str, Any], wavelength_nm: np.ndarray) -> np.ndarray:
        return np.full_like(wavelength_nm, float(cfg["offset"]))


class _PolynomialBaseline(BaselinePlugin):
    kind = "polynomial"
    description = "Polynomial baseline referenced to the mean wavelength of the grid."
    config_schema = {
        "type": "object",
        "required": ["kind", "coefficients"],
        "properties": {
            "kind": {"const": "polynomial"},
            "coefficients": {"type": "array", "items": {"type": "number"}, "minItems": 1},
        },
        "additionalProperties": False,
    }

    def evaluate(self, cfg: Mapping[str, Any], wavelength_nm: np.ndarray) -> np.ndarray:
        coeffs = list(cfg["coefficients"])
        x = wavelength_nm - wavelength_nm.mean()
        y = np.zeros_like(wavelength_nm)
        for p, c in enumerate(coeffs):
            y += float(c) * (x ** p)
        return y


BASELINE_PLUGINS.register(_ConstantBaseline())
BASELINE_PLUGINS.register(_PolynomialBaseline())


def normalize_baseline_config(inst_cfg: Mapping[str, Any]) -> Dict[str, Any]:
    base = dict(inst_cfg.get("baseline", {"kind": "constant", "offset": 0.0}))
    if "kind" not in base:
        if "coefficients" in base:
            base["kind"] = "polynomial"
        else:
            base["kind"] = "constant"
            base.setdefault("offset", 0.0)
    if base["kind"] == "constant":
        base.setdefault("offset", 0.0)
    return base


def evaluate_baseline(inst_cfg: Dict[str, Any], wavelength_nm: np.ndarray) -> np.ndarray:
    spec = normalize_baseline_config(inst_cfg)
    plugin = BASELINE_PLUGINS.get(str(spec["kind"]))
    plugin.validate_config(spec)
    return plugin.evaluate(spec, wavelength_nm)
