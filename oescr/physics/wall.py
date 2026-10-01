from __future__ import annotations

from abc import abstractmethod
from typing import Any, Dict, Mapping

import numpy as np
from scipy import constants as const

from ..plugins import PluginBase, PluginRegistry

WALL_LOSS_PLUGINS: PluginRegistry["WallLossPlugin"] = PluginRegistry("wall_loss")


class WallLossPlugin(PluginBase):
    @abstractmethod
    def loss_rate(
        self,
        wall_cfg: Mapping[str, Any],
        geometry_cfg: Mapping[str, Any],
        gas_temperature_K: float,
        state_id: str,
        species: str,
        mass_amu: float | None,
    ) -> float:
        raise NotImplementedError


def cylinder_characteristic_length(radius_m: float, height_m: float) -> float:
    V = np.pi * radius_m * radius_m * height_m
    A = 2.0 * np.pi * radius_m * height_m + 2.0 * np.pi * radius_m * radius_m
    return max(V / max(A, 1.0e-12), 1.0e-6)


def thermal_speed_m_s(mass_amu: float | None, gas_temperature_K: float) -> float:
    if mass_amu is None:
        raise ValueError("Wall-loss thermal speed requires state mass_amu; no fallback speed is assumed.")
    m = mass_amu * const.atomic_mass
    T = max(gas_temperature_K, 1.0)
    return float(np.sqrt(8.0 * const.k * T / (np.pi * m)))


def resolve_gamma(wall_cfg: Mapping[str, Any], state_id: str, species: str) -> float:
    gamma_map = wall_cfg.get("gamma", {})
    if state_id in gamma_map:
        return float(gamma_map[state_id])
    if species in gamma_map:
        return float(gamma_map[species])
    pri = wall_cfg.get("priors", {})
    if f"gamma_{state_id}" in pri:
        item = pri[f"gamma_{state_id}"]
        return float(np.sqrt(float(item["min"]) * float(item["max"])))
    if f"gamma_{species}" in pri:
        item = pri[f"gamma_{species}"]
        return float(np.sqrt(float(item["min"]) * float(item["max"])))
    if f"gamma_{species}_eff" in pri:
        item = pri[f"gamma_{species}_eff"]
        return float(np.sqrt(float(item["min"]) * float(item["max"])))
    return float(wall_cfg.get("gamma_default", 0.0))


class _NoWallLossPlugin(WallLossPlugin):
    kind = "none"
    description = "Disable wall-loss contribution."
    config_schema = {
        "type": "object",
        "properties": {"model": {"enum": ["none"]}},
        "additionalProperties": True,
    }

    def loss_rate(
        self,
        wall_cfg: Mapping[str, Any],
        geometry_cfg: Mapping[str, Any],
        gas_temperature_K: float,
        state_id: str,
        species: str,
        mass_amu: float | None,
    ) -> float:
        return 0.0


class _GammaThermalWallLossPlugin(WallLossPlugin):
    kind = "gamma_thermal"
    description = "Gamma-based thermal flux to walls using an effective characteristic length."
    config_schema = {
        "type": "object",
        "properties": {
            "model": {"enum": ["gamma_thermal"]},
            "characteristic_length_m": {"type": "number", "exclusiveMinimum": 0},
            "gamma_default": {"type": "number", "minimum": 0, "maximum": 1},
            "gamma": {"type": "object"},
            "priors": {"type": "object"},
            "thermal_flux_factor": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
        },
        "additionalProperties": True,
    }

    def _validate_semantics(self, cfg: Mapping[str, Any]) -> None:
        priors = cfg.get("priors", {})
        for name, item in priors.items():
            if float(item["min"]) >= float(item["max"]):
                raise ValueError(f"Wall prior '{name}' requires min < max.")

    def loss_rate(
        self,
        wall_cfg: Mapping[str, Any],
        geometry_cfg: Mapping[str, Any],
        gas_temperature_K: float,
        state_id: str,
        species: str,
        mass_amu: float | None,
    ) -> float:
        gamma = resolve_gamma(wall_cfg, state_id, species)
        if gamma <= 0.0:
            return 0.0
        L = float(wall_cfg.get("characteristic_length_m", 0.0))
        if L <= 0.0:
            L = cylinder_characteristic_length(
                float(geometry_cfg.get("chamber_radius_m", 0.15)),
                float(geometry_cfg.get("chamber_height_m", 0.08)),
            )
        vth = thermal_speed_m_s(mass_amu, gas_temperature_K)
        flux_factor = float(wall_cfg.get("thermal_flux_factor", 1.0))
        return gamma * flux_factor * vth / L


WALL_LOSS_PLUGINS.register(_NoWallLossPlugin())
WALL_LOSS_PLUGINS.register(_GammaThermalWallLossPlugin())


def resolve_wall_model_kind(wall_cfg: Mapping[str, Any]) -> str:
    if not wall_cfg:
        return "none"
    return str(wall_cfg.get("model", "gamma_thermal"))


def effective_wall_loss_rate_s(
    wall_cfg: Dict[str, Any],
    geometry_cfg: Dict[str, Any],
    gas_temperature_K: float,
    state_id: str,
    species: str,
    mass_amu: float | None,
    *,
    validate: bool = True,
) -> float:
    kind = resolve_wall_model_kind(wall_cfg)
    plugin = WALL_LOSS_PLUGINS.get(kind)
    if validate:
        plugin.validate_config(wall_cfg)
    return plugin.loss_rate(wall_cfg, geometry_cfg, gas_temperature_K, state_id, species, mass_amu)
