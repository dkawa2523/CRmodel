from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

import numpy as np
from scipy import constants as const

from ..data.cross_section_db import CrossSectionLibrary
from ..plugins import PluginBase, PluginRegistry


REACTION_RATE_PLUGINS: PluginRegistry["ReactionRatePlugin"] = PluginRegistry("reaction_rate")


class ReactionRatePlugin(PluginBase):
    @abstractmethod
    def rate(self, rate_calc: "RateCalculator", spec: Mapping[str, Any], eedf_pdf: np.ndarray) -> float:
        raise NotImplementedError


class _CrossSectionFileRatePlugin(ReactionRatePlugin):
    kind = "cross_section_file"
    description = "Rate coefficient from an external CSV cross section table."
    config_schema = {
        "type": "object",
        "required": ["kind", "cross_section_file"],
        "properties": {
            "kind": {"const": "cross_section_file"},
            "cross_section_file": {"type": "string", "minLength": 1},
        },
        "additionalProperties": True,
    }

    def rate(self, rate_calc: "RateCalculator", spec: Mapping[str, Any], eedf_pdf: np.ndarray) -> float:
        return rate_calc.rate_from_cross_section_file(str(spec["cross_section_file"]), eedf_pdf)


class _ThresholdModelRatePlugin(ReactionRatePlugin):
    kind = "threshold_model"
    description = "Analytic threshold surrogate for excitation or ionization rates."
    config_schema = {
        "type": "object",
        "required": ["kind", "threshold_eV", "sigma_peak_m2", "epeak_eV"],
        "properties": {
            "kind": {"const": "threshold_model"},
            "threshold_eV": {"type": "number", "minimum": 0},
            "sigma_peak_m2": {"type": "number", "minimum": 0},
            "epeak_eV": {"type": "number", "minimum": 0},
        },
        "additionalProperties": False,
    }

    def _validate_semantics(self, cfg: Mapping[str, Any]) -> None:
        if float(cfg["epeak_eV"]) < float(cfg["threshold_eV"]):
            raise ValueError("Threshold surrogate requires epeak_eV >= threshold_eV.")

    def rate(self, rate_calc: "RateCalculator", spec: Mapping[str, Any], eedf_pdf: np.ndarray) -> float:
        return rate_calc.rate_from_threshold_model(
            eedf_pdf,
            float(spec["threshold_eV"]),
            float(spec["sigma_peak_m2"]),
            float(spec["epeak_eV"]),
        )


class _ConstantRatePlugin(ReactionRatePlugin):
    kind = "constant"
    description = "User-specified constant rate coefficient."
    config_schema = {
        "type": "object",
        "required": ["kind", "coefficient_m3_s"],
        "properties": {
            "kind": {"const": "constant"},
            "coefficient_m3_s": {"type": "number", "minimum": 0},
        },
        "additionalProperties": False,
    }

    def rate(self, rate_calc: "RateCalculator", spec: Mapping[str, Any], eedf_pdf: np.ndarray) -> float:
        return float(spec["coefficient_m3_s"])


REACTION_RATE_PLUGINS.register(_CrossSectionFileRatePlugin())
REACTION_RATE_PLUGINS.register(_ThresholdModelRatePlugin())
REACTION_RATE_PLUGINS.register(_ConstantRatePlugin())


@dataclass
class RateCalculator:
    energy_eV: np.ndarray
    cs_library: CrossSectionLibrary

    def __post_init__(self) -> None:
        self._interp_cache: Dict[Tuple[str, int], np.ndarray] = {}

    @property
    def electron_velocity_m_s(self) -> np.ndarray:
        energy_J = np.maximum(self.energy_eV, 0.0) * const.e
        return np.sqrt(2.0 * energy_J / const.m_e)

    def rate_from_cross_section_file(self, path: str, eedf_pdf: np.ndarray) -> float:
        key = (path, len(self.energy_eV))
        if key not in self._interp_cache:
            cs = self.cs_library.load(path)
            interp = np.interp(self.energy_eV, cs.energy_eV, cs.sigma_m2, left=0.0, right=0.0)
            self._interp_cache[key] = interp
        sigma = self._interp_cache[key]
        integrand = sigma * self.electron_velocity_m_s * eedf_pdf
        return float(np.trapezoid(integrand, self.energy_eV))

    def rate_from_threshold_model(
        self,
        eedf_pdf: np.ndarray,
        threshold_eV: float,
        sigma_peak_m2: float,
        epeak_eV: float,
    ) -> float:
        E = self.energy_eV
        x = np.maximum(E - threshold_eV, 0.0)
        width = max(epeak_eV - threshold_eV, 1.0e-3)
        sigma = np.zeros_like(E)
        mask = x > 0.0
        y = x[mask] / width
        sigma[mask] = sigma_peak_m2 * y * np.exp(1.0 - y)
        integrand = sigma * self.electron_velocity_m_s * eedf_pdf
        return float(np.trapezoid(integrand, self.energy_eV))


def resolve_reaction_rate_spec(rxn: Mapping[str, Any]) -> Dict[str, Any]:
    if "rate_model" in rxn:
        spec = dict(rxn["rate_model"])
        if "kind" not in spec:
            raise ValueError(f"Reaction '{rxn.get('id', '<unknown>')}' rate_model requires a 'kind'.")
        return spec
    if "cross_section_file" in rxn:
        return {"kind": "cross_section_file", "cross_section_file": rxn["cross_section_file"]}
    if "threshold_model" in rxn:
        tm = dict(rxn["threshold_model"])
        tm["kind"] = "threshold_model"
        return tm
    return {"kind": "constant", "coefficient_m3_s": float(rxn.get("coefficient_m3_s", 0.0))}


def reaction_rate_coefficient(
    rate_calc: RateCalculator,
    rxn: Mapping[str, Any],
    eedf_pdf: np.ndarray,
) -> float:
    spec = resolve_reaction_rate_spec(rxn)
    plugin = REACTION_RATE_PLUGINS.get(str(spec["kind"]))
    plugin.validate_config(spec)
    return plugin.rate(rate_calc, spec, eedf_pdf)
