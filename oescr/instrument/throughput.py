from __future__ import annotations

from abc import abstractmethod
from typing import Any, Dict, Mapping

import numpy as np

from ..plugins import PluginBase, PluginRegistry


THROUGHPUT_PLUGINS: PluginRegistry["ThroughputPlugin"] = PluginRegistry("throughput")


class ThroughputPlugin(PluginBase):
    @abstractmethod
    def evaluate(self, cfg: Mapping[str, Any], wavelength_nm: np.ndarray) -> np.ndarray:
        raise NotImplementedError


class _ConstantThroughput(ThroughputPlugin):
    kind = "constant"
    description = "Scalar throughput applied across the full wavelength range."
    config_schema = {
        "type": "object",
        "required": ["kind", "value"],
        "properties": {
            "kind": {"const": "constant"},
            "value": {"type": "number", "minimum": 0},
        },
        "additionalProperties": False,
    }

    def evaluate(self, cfg: Mapping[str, Any], wavelength_nm: np.ndarray) -> np.ndarray:
        return np.full_like(wavelength_nm, float(cfg["value"]), dtype=float)


class _TabulatedThroughput(ThroughputPlugin):
    kind = "tabulated"
    description = "Interpolated wavelength-dependent throughput curve."
    config_schema = {
        "type": "object",
        "required": ["kind", "wavelength_nm", "values"],
        "properties": {
            "kind": {"const": "tabulated"},
            "wavelength_nm": {"type": "array", "items": {"type": "number"}, "minItems": 2},
            "values": {"type": "array", "items": {"type": "number", "minimum": 0}, "minItems": 2},
        },
        "additionalProperties": False,
    }

    def _validate_semantics(self, cfg: Mapping[str, Any]) -> None:
        wl = np.asarray(cfg["wavelength_nm"], dtype=float)
        val = np.asarray(cfg["values"], dtype=float)
        if len(wl) != len(val):
            raise ValueError("Tabulated throughput requires wavelength_nm and values arrays of equal length.")
        if np.any(np.diff(wl) <= 0.0):
            raise ValueError("Tabulated throughput wavelength_nm must be strictly increasing.")

    def evaluate(self, cfg: Mapping[str, Any], wavelength_nm: np.ndarray) -> np.ndarray:
        wl = np.asarray(cfg["wavelength_nm"], dtype=float)
        val = np.asarray(cfg["values"], dtype=float)
        return np.interp(wavelength_nm, wl, val, left=val[0], right=val[-1])


THROUGHPUT_PLUGINS.register(_ConstantThroughput())
THROUGHPUT_PLUGINS.register(_TabulatedThroughput())


def normalize_throughput_config(inst_cfg: Mapping[str, Any]) -> Dict[str, Any]:
    thr = inst_cfg.get("throughput", 1.0)
    if isinstance(thr, (int, float)):
        return {"kind": "constant", "value": float(thr)}
    if isinstance(thr, dict):
        if "kind" in thr:
            out = dict(thr)
            if out["kind"] == "tabulated" and "values" not in out and "value" in out:
                out["values"] = list(out["value"])
                out.pop("value", None)
            return out
        if "wavelength_nm" in thr and "value" in thr:
            return {"kind": "tabulated", "wavelength_nm": list(thr["wavelength_nm"]), "values": list(thr["value"])}
    raise ValueError("Unsupported throughput format. Use a scalar or a mapping with kind/wavelength_nm/values.")


def evaluate_throughput(inst_cfg: Dict[str, Any], wavelength_nm: np.ndarray) -> np.ndarray:
    spec = normalize_throughput_config(inst_cfg)
    plugin = THROUGHPUT_PLUGINS.get(str(spec["kind"]))
    plugin.validate_config(spec)
    return plugin.evaluate(spec, wavelength_nm)
