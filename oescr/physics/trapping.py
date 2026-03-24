from __future__ import annotations

from abc import abstractmethod
from typing import Any, Dict, Mapping

from ..plugins import PluginBase, PluginRegistry


TRAPPING_PLUGINS: PluginRegistry["TrappingPlugin"] = PluginRegistry("trapping")


class TrappingPlugin(PluginBase):
    @abstractmethod
    def effective_A(self, A_s1: float, trapping_cfg: Mapping[str, Any], zone_context: Mapping[str, Any] | None) -> float:
        raise NotImplementedError


def escape_factor(tau0: float, model: str = "slab") -> float:
    tau = max(float(tau0), 0.0)
    if tau <= 1.0e-12:
        return 1.0
    beta = (1.0 - pow(2.718281828459045, -tau)) / tau
    return float(max(min(beta, 1.0), 1.0e-6))


class _NoTrappingPlugin(TrappingPlugin):
    kind = "none"
    description = "No trapping; A_eff = A."
    config_schema = {
        "type": "object",
        "properties": {"kind": {"const": "none"}},
        "additionalProperties": False,
    }

    def effective_A(self, A_s1: float, trapping_cfg: Mapping[str, Any], zone_context: Mapping[str, Any] | None) -> float:
        return float(A_s1)


class _BetaOverridePlugin(TrappingPlugin):
    kind = "beta_override"
    description = "User-provided escape factor beta_override."
    config_schema = {
        "type": "object",
        "required": ["kind", "beta_override"],
        "properties": {
            "kind": {"const": "beta_override"},
            "beta_override": {"type": "number", "minimum": 0},
        },
        "additionalProperties": False,
    }

    def effective_A(self, A_s1: float, trapping_cfg: Mapping[str, Any], zone_context: Mapping[str, Any] | None) -> float:
        return float(A_s1) * float(trapping_cfg["beta_override"])


class _EscapeFactorPlugin(TrappingPlugin):
    kind = "escape_factor"
    description = "Simple escape-factor trapping model with slab/cylinder shape."
    config_schema = {
        "type": "object",
        "properties": {
            "kind": {"const": "escape_factor"},
            "tau0": {"type": "number", "minimum": 0},
            "shape": {"type": "string", "enum": ["slab", "cylinder"]},
        },
        "additionalProperties": False,
    }

    def effective_A(self, A_s1: float, trapping_cfg: Mapping[str, Any], zone_context: Mapping[str, Any] | None) -> float:
        tau0 = float(trapping_cfg.get("tau0", 0.0))
        shape = str(trapping_cfg.get("shape", "slab"))
        return float(A_s1) * escape_factor(tau0, model=shape)


TRAPPING_PLUGINS.register(_NoTrappingPlugin())
TRAPPING_PLUGINS.register(_BetaOverridePlugin())
TRAPPING_PLUGINS.register(_EscapeFactorPlugin())


def resolve_trapping_spec(transition: Mapping[str, Any]) -> Dict[str, Any]:
    trap = dict(transition.get("trapping", {}) or {})
    if not trap:
        return {"kind": "none"}
    if "kind" in trap:
        return trap
    if "beta_override" in trap:
        return {"kind": "beta_override", "beta_override": trap["beta_override"]}
    shape = trap.get("shape", trap.get("model", "slab"))
    return {"kind": "escape_factor", "tau0": float(trap.get("tau0", 0.0)), "shape": str(shape)}


def effective_A(transition: Dict[str, Any], zone_context: Dict[str, Any] | None = None) -> float:
    A = float(transition["A_s-1"])
    spec = resolve_trapping_spec(transition)
    plugin = TRAPPING_PLUGINS.get(str(spec["kind"]))
    plugin.validate_config(spec)
    return plugin.effective_A(A, spec, zone_context)
