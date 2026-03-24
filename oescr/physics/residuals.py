
from __future__ import annotations

from typing import Any, Dict

from scipy import constants as const


def neutral_density_from_pressure(pressure_Pa: float, gas_temperature_K: float) -> float:
    return float(pressure_Pa / (const.k * gas_temperature_K))


def _zone_value(x: Any, zone_idx: int, default: float = 0.0) -> float:
    if x is None:
        return default
    if isinstance(x, (list, tuple)):
        return float(x[zone_idx])
    return float(x)


def build_external_densities(cfg: Dict[str, Any], zone_idx: int) -> Dict[str, float]:
    gas = cfg.get("gas_mixture", {})
    pressure_Pa = float(gas.get("total_pressure_Pa", 1.0))
    Tg = float(gas.get("gas_temperature_K", 300.0))
    total_neutral = neutral_density_from_pressure(pressure_Pa, Tg)

    dens: Dict[str, float] = {}
    for name, frac in gas.get("fractions", {}).items():
        dens[name] = float(frac) * total_neutral

    plasma = cfg.get("plasma_state", {})
    dens["e"] = _zone_value(plasma.get("ne_shells_m3", [0.0]), zone_idx)

    for key, arr in plasma.get("radicals", {}).items():
        dens[key] = _zone_value(arr, zone_idx)

    for key, arr in plasma.get("metastables", {}).items():
        dens[key] = _zone_value(arr, zone_idx)

    for key, arr in plasma.get("state_densities", {}).items():
        dens[key] = _zone_value(arr, zone_idx)

    res = cfg.get("residuals", {})
    if res.get("mode", "off") != "off":
        for key, arr in res.get("species_density_m3", {}).items():
            dens[key] = _zone_value(arr, zone_idx)

    return dens
