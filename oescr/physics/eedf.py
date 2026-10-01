from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Mapping

import numpy as np

from ..plugins import PluginBase, PluginRegistry

EEDF_PLUGINS: PluginRegistry["EEDFPlugin"] = PluginRegistry("eedf")


@dataclass(frozen=True)
class EEDFDiagnostics:
    normalization: float
    mean_energy_eV: float
    upper_decile_probability: float
    upper_edge_relative_pdf: float


def summarize_eedf(energy_eV: np.ndarray, pdf: np.ndarray) -> EEDFDiagnostics:
    """Return grid-dependent EEDF checks without claiming an unobserved tail."""

    normalization = float(np.trapezoid(pdf, energy_eV))
    mean_energy = float(np.trapezoid(energy_eV * pdf, energy_eV))
    cutoff = float(energy_eV[0] + 0.9 * (energy_eV[-1] - energy_eV[0]))
    mask = energy_eV >= cutoff
    upper_decile = float(np.trapezoid(pdf[mask], energy_eV[mask])) if np.count_nonzero(mask) >= 2 else 0.0
    peak = max(float(np.max(pdf)), 1.0e-300)
    return EEDFDiagnostics(
        normalization=normalization,
        mean_energy_eV=mean_energy,
        upper_decile_probability=upper_decile,
        upper_edge_relative_pdf=float(pdf[-1]) / peak,
    )


class EEDFPlugin(PluginBase):
    @abstractmethod
    def build_pdf(self, spec: Mapping[str, Any], energy_eV: np.ndarray) -> np.ndarray:
        raise NotImplementedError


def _normalize_pdf(energy_eV: np.ndarray, pdf: np.ndarray) -> np.ndarray:
    pdf = np.maximum(pdf, 0.0)
    area = np.trapezoid(pdf, energy_eV)
    if area <= 0.0:
        raise ValueError("EEDF normalization failed: non-positive area.")
    return pdf / area


def maxwell_energy_pdf(energy_eV: np.ndarray, te_eV: float) -> np.ndarray:
    te = max(te_eV, 1.0e-6)
    pdf = (2.0 / np.sqrt(np.pi)) * np.sqrt(np.maximum(energy_eV, 0.0)) / (te ** 1.5)
    pdf *= np.exp(-energy_eV / te)
    return _normalize_pdf(energy_eV, pdf)


def druyvesteyn_energy_pdf(energy_eV: np.ndarray, te_eV: float) -> np.ndarray:
    te = max(te_eV, 1.0e-6)
    pdf = np.sqrt(np.maximum(energy_eV, 0.0)) * np.exp(-((energy_eV / te) ** 2))
    return _normalize_pdf(energy_eV, pdf)


def bi_maxwell_energy_pdf(
    energy_eV: np.ndarray,
    tc_eV: float,
    th_eV: float,
    hot_fraction: float,
) -> np.ndarray:
    alpha = float(np.clip(hot_fraction, 0.0, 1.0))
    pdf = (1.0 - alpha) * maxwell_energy_pdf(energy_eV, tc_eV) + alpha * maxwell_energy_pdf(
        energy_eV, th_eV
    )
    return _normalize_pdf(energy_eV, pdf)


def tabulated_energy_pdf(energy_eV: np.ndarray, input_energy_eV: np.ndarray, fE: np.ndarray) -> np.ndarray:
    interp = np.interp(energy_eV, input_energy_eV, fE, left=0.0, right=0.0)
    return _normalize_pdf(energy_eV, interp)


class _TeMaxwellPlugin(EEDFPlugin):
    kind = "te_maxwell"
    description = "Thermal Maxwellian derived from te_shells_eV."
    config_schema = {
        "type": "object",
        "required": ["kind", "te_eV"],
        "properties": {
            "kind": {"const": "te_maxwell"},
            "te_eV": {"type": "number", "exclusiveMinimum": 0},
        },
        "additionalProperties": False,
    }

    def build_pdf(self, spec: Mapping[str, Any], energy_eV: np.ndarray) -> np.ndarray:
        return maxwell_energy_pdf(energy_eV, float(spec["te_eV"]))


class _TeDruyvesteynPlugin(EEDFPlugin):
    kind = "te_druyvesteyn"
    description = "Druyvesteyn-like thermal EEDF derived from te_shells_eV."
    config_schema = {
        "type": "object",
        "required": ["kind", "te_eV"],
        "properties": {
            "kind": {"const": "te_druyvesteyn"},
            "te_eV": {"type": "number", "exclusiveMinimum": 0},
        },
        "additionalProperties": False,
    }

    def build_pdf(self, spec: Mapping[str, Any], energy_eV: np.ndarray) -> np.ndarray:
        return druyvesteyn_energy_pdf(energy_eV, float(spec["te_eV"]))


class _BiMaxwellPlugin(EEDFPlugin):
    description = "Two-temperature Maxwellian mixture."
    config_schema = {
        "type": "object",
        "required": ["kind", "Tc_eV", "Th_eV", "hot_fraction"],
        "properties": {
            "kind": {"type": "string"},
            "Tc_eV": {"type": "number", "exclusiveMinimum": 0},
            "Th_eV": {"type": "number", "exclusiveMinimum": 0},
            "hot_fraction": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "additionalProperties": False,
    }

    def _validate_semantics(self, cfg: Mapping[str, Any]) -> None:
        if float(cfg["Th_eV"]) < float(cfg["Tc_eV"]):
            raise ValueError(f"Bi-Maxwell plugin '{self.kind}' requires Th_eV >= Tc_eV.")

    def build_pdf(self, spec: Mapping[str, Any], energy_eV: np.ndarray) -> np.ndarray:
        return bi_maxwell_energy_pdf(
            energy_eV,
            float(spec["Tc_eV"]),
            float(spec["Th_eV"]),
            float(spec["hot_fraction"]),
        )


class _TeBiMaxwellPlugin(_BiMaxwellPlugin):
    kind = "te_bimaxwell"


class _ExplicitBiMaxwellPlugin(_BiMaxwellPlugin):
    kind = "eedf_bimaxwell"


class _TabulatedPlugin(EEDFPlugin):
    kind = "eedf_tabulated"
    description = "Tabulated EEDF interpolated onto the internal energy grid."
    config_schema = {
        "type": "object",
        "required": ["kind", "energy_eV", "fE"],
        "properties": {
            "kind": {"const": "eedf_tabulated"},
            "energy_eV": {"type": "array", "items": {"type": "number", "minimum": 0}, "minItems": 2},
            "fE": {"type": "array", "items": {"type": "number", "minimum": 0}, "minItems": 2},
        },
        "additionalProperties": False,
    }

    def _validate_semantics(self, cfg: Mapping[str, Any]) -> None:
        energy = np.asarray(cfg["energy_eV"], dtype=float)
        fE = np.asarray(cfg["fE"], dtype=float)
        if len(energy) != len(fE):
            raise ValueError("Tabulated EEDF requires energy_eV and fE arrays of identical length.")
        if np.any(np.diff(energy) <= 0.0):
            raise ValueError("Tabulated EEDF energy_eV must be strictly increasing.")

    def build_pdf(self, spec: Mapping[str, Any], energy_eV: np.ndarray) -> np.ndarray:
        return tabulated_energy_pdf(
            energy_eV,
            np.asarray(spec["energy_eV"], dtype=float),
            np.asarray(spec["fE"], dtype=float),
        )


EEDF_PLUGINS.register(_TeMaxwellPlugin())
EEDF_PLUGINS.register(_TeDruyvesteynPlugin())
EEDF_PLUGINS.register(_TeBiMaxwellPlugin())
EEDF_PLUGINS.register(_ExplicitBiMaxwellPlugin())
EEDF_PLUGINS.register(_TabulatedPlugin())


def build_energy_grid(cfg: Dict[str, Any]) -> np.ndarray:
    eg = cfg.get("energy_grid", {})
    emin = float(eg.get("min_eV", 0.0))
    emax = float(eg.get("max_eV", 50.0))
    npts = int(eg.get("n_points", 800))
    return np.linspace(emin, emax, npts)


def eedf_model_kind(cfg: Mapping[str, Any]) -> str:
    """Return the selected EEDF plugin kind for capability checks and reports."""

    envelope = cfg.get("eedf")
    if isinstance(envelope, Mapping):
        return str(envelope["kind"])

    mode = str(cfg.get("plasma_mode", "te"))
    if mode == "te":
        te_kind = str(cfg.get("plasma_state", {}).get("te_eedf_kind", "maxwell"))
        return {
            "maxwell": "te_maxwell",
            "druyvesteyn": "te_druyvesteyn",
            "bi_maxwell": "te_bimaxwell",
        }.get(te_kind, te_kind)
    return mode


def resolve_eedf_plugin_spec(cfg: Mapping[str, Any], zone_idx: int) -> Dict[str, Any]:
    envelope = cfg.get("eedf")
    if isinstance(envelope, Mapping):
        zones = envelope.get("zones", [])
        zone = zones[zone_idx]
        if not isinstance(zone, Mapping):
            raise ValueError(f"eedf.zones[{zone_idx}] must be a mapping.")
        return {"kind": str(envelope["kind"]), **dict(zone)}

    mode = cfg.get("plasma_mode", "te")
    plasma_state = cfg.get("plasma_state", {})

    if mode == "te":
        te_kind = plasma_state.get("te_eedf_kind", "maxwell")
        te = float(plasma_state["te_shells_eV"][zone_idx])
        if te_kind == "maxwell":
            return {"kind": "te_maxwell", "te_eV": te}
        if te_kind == "druyvesteyn":
            return {"kind": "te_druyvesteyn", "te_eV": te}
        if te_kind == "bi_maxwell":
            bm = plasma_state["te_bimaxwell_shells"]
            z = bm[zone_idx]
            return {
                "kind": "te_bimaxwell",
                "Tc_eV": float(z["Tc_eV"]),
                "Th_eV": float(z["Th_eV"]),
                "hot_fraction": float(z["hot_fraction"]),
            }
        raise ValueError(f"Unsupported te_eedf_kind: {te_kind}")

    if mode == "eedf_bimaxwell":
        z = plasma_state["eedf_bimaxwell_shells"][zone_idx]
        return {
            "kind": "eedf_bimaxwell",
            "Tc_eV": float(z["Tc_eV"]),
            "Th_eV": float(z["Th_eV"]),
            "hot_fraction": float(z["hot_fraction"]),
        }

    if mode == "eedf_tabulated":
        z = plasma_state["eedf_tabulated_shells"][zone_idx]
        return {
            "kind": "eedf_tabulated",
            "energy_eV": list(z["energy_eV"]),
            "fE": list(z["fE"]),
        }

    raise ValueError(f"Unsupported plasma_mode: {mode}")


def build_eedf_for_zone(cfg: Mapping[str, Any], zone_idx: int, energy_eV: np.ndarray) -> np.ndarray:
    spec = resolve_eedf_plugin_spec(cfg, zone_idx)
    plugin = EEDF_PLUGINS.get(str(spec["kind"]))
    plugin.validate_config(spec)
    return plugin.build_pdf(spec, energy_eV)
