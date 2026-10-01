from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Mapping

import numpy as np
from scipy import constants as const

from ..data.band_db import load_profile_csv
from ..io.yaml_loader import resolve_path
from ..plugins import PluginBase, PluginRegistry
from .rates import RateCalculator, reaction_rate_coefficient

BAND_PROFILE_PLUGINS: PluginRegistry["BandProfilePlugin"] = PluginRegistry("band_profile")
BAND_EMISSION_PLUGINS: PluginRegistry["BandEmissionPlugin"] = PluginRegistry("band_emission")


@dataclass
class BandSpectrum:
    spectrum: np.ndarray
    output_basis: str
    diagnostics: Dict[str, Any]


class BandProfilePlugin(PluginBase):
    @abstractmethod
    def profile(self, cfg: Dict[str, Any], band: Mapping[str, Any], wavelength_nm: np.ndarray) -> np.ndarray:
        raise NotImplementedError


class BandEmissionPlugin(PluginBase):
    output_basis = "unspecified"

    @abstractmethod
    def emissivity(
        self,
        cfg: Dict[str, Any],
        band: Mapping[str, Any],
        wavelength_nm: np.ndarray,
        external_densities: Dict[str, float],
        eedf_pdf: np.ndarray,
        rate_calc: RateCalculator,
    ) -> np.ndarray:
        raise NotImplementedError


class _GaussianBandProfile(BandProfilePlugin):
    kind = "gaussian"
    description = "Normalized Gaussian molecular band contour."
    config_schema = {
        "type": "object",
        "required": ["kind", "center_nm", "fwhm_nm"],
        "properties": {
            "kind": {"const": "gaussian"},
            "center_nm": {"type": "number"},
            "fwhm_nm": {"type": "number", "exclusiveMinimum": 0},
        },
        "additionalProperties": False,
    }

    def profile(self, cfg: Dict[str, Any], band: Mapping[str, Any], wavelength_nm: np.ndarray) -> np.ndarray:
        sigma = max(float(band["fwhm_nm"]) / 2.35482004503, 1.0e-6)
        p = np.exp(-0.5 * ((wavelength_nm - float(band["center_nm"])) / sigma) ** 2)
        area = np.trapezoid(p, wavelength_nm)
        return p / max(area, 1.0e-30)


class _TabulatedBandProfile(BandProfilePlugin):
    kind = "tabulated"
    description = "Band contour read from a tabulated profile CSV file."
    config_schema = {
        "type": "object",
        "required": ["kind", "profile_file"],
        "properties": {
            "kind": {"const": "tabulated"},
            "profile_file": {"type": "string", "minLength": 1},
        },
        "additionalProperties": True,
    }

    def profile(self, cfg: Dict[str, Any], band: Mapping[str, Any], wavelength_nm: np.ndarray) -> np.ndarray:
        prof_path = resolve_path(cfg, str(band["profile_file"]))
        prof = load_profile_csv(prof_path)
        interp = np.interp(
            wavelength_nm,
            prof["wavelength_nm"],
            prof["relative_intensity"],
            left=0.0,
            right=0.0,
        )
        area = np.trapezoid(interp, wavelength_nm)
        return interp / max(area, 1.0e-30)


class _EffectiveExcitationBand(BandEmissionPlugin):
    kind = "effective_excitation_band"
    description = "Band emissivity proportional to ne * n_source * k_exc(EEDF)."
    output_basis = "effective_event_rate_density_m-3_s-1_nm-1"
    config_schema = {
        "type": "object",
        "required": ["kind", "source_density_key"],
        "properties": {
            "kind": {"const": "effective_excitation_band"},
            "source_density_key": {"type": "string"},
            "cross_section_file": {"type": "string"},
            "coefficient_m3_s": {"type": "number", "minimum": 0},
            "amplitude_scale": {"type": "number", "minimum": 0},
            "profile_kind": {"type": "string"},
            "center_nm": {"type": "number"},
            "fwhm_nm": {"type": "number", "exclusiveMinimum": 0},
            "profile_file": {"type": "string"},
        },
        "additionalProperties": True,
    }

    def emissivity(
        self,
        cfg: Dict[str, Any],
        band: Mapping[str, Any],
        wavelength_nm: np.ndarray,
        external_densities: Dict[str, float],
        eedf_pdf: np.ndarray,
        rate_calc: RateCalculator,
    ) -> np.ndarray:
        ne = float(external_densities.get("e", 0.0))
        nsrc = float(external_densities.get(str(band["source_density_key"]), 0.0))
        band_work = dict(band)
        if "cross_section_file" in band_work:
            band_work["cross_section_file"] = str(resolve_path(cfg, band_work["cross_section_file"]))
        k = reaction_rate_coefficient(rate_calc, band_work, eedf_pdf)
        profile = band_profile(cfg, band, wavelength_nm)
        amplitude = float(band.get("amplitude_scale", 1.0)) * ne * nsrc * k
        return amplitude * profile


class _EffectiveDensityBand(BandEmissionPlugin):
    kind = "effective_density_band"
    description = "Band emissivity proportional to source density only."
    output_basis = "empirical_density_scaled_nm-1"
    config_schema = {
        "type": "object",
        "required": ["kind", "source_density_key", "coefficient"],
        "properties": {
            "kind": {"const": "effective_density_band"},
            "source_density_key": {"type": "string"},
            "coefficient": {"type": "number", "minimum": 0},
            "profile_kind": {"type": "string"},
            "center_nm": {"type": "number"},
            "fwhm_nm": {"type": "number", "exclusiveMinimum": 0},
            "profile_file": {"type": "string"},
        },
        "additionalProperties": True,
    }

    def emissivity(
        self,
        cfg: Dict[str, Any],
        band: Mapping[str, Any],
        wavelength_nm: np.ndarray,
        external_densities: Dict[str, float],
        eedf_pdf: np.ndarray,
        rate_calc: RateCalculator,
    ) -> np.ndarray:
        nsrc = float(external_densities.get(str(band["source_density_key"]), 0.0))
        profile = band_profile(cfg, band, wavelength_nm)
        amplitude = float(band.get("coefficient", 0.0)) * nsrc
        return amplitude * profile


class _ElectronImpactPhotonBand(BandEmissionPlugin):
    kind = "electron_impact_photon_band"
    description = (
        "Physical electron-impact band in spectral radiant-power units using an explicit photon yield."
    )
    output_basis = "spectral_radiant_power_W_m-3_sr-1_nm-1"
    config_schema = {
        "type": "object",
        "required": ["kind", "source_density_key", "photon_yield"],
        "properties": {
            "kind": {"const": "electron_impact_photon_band"},
            "id": {"type": "string"},
            "source_density_key": {"type": "string"},
            "cross_section_file": {"type": "string"},
            "coefficient_m3_s": {"type": "number", "minimum": 0},
            "threshold_model": {"type": "object"},
            "rate_model": {"type": "object"},
            "photon_yield": {"type": "number", "minimum": 0},
            "branching_ratio": {"type": "number", "minimum": 0, "maximum": 1},
            "profile_kind": {"type": "string"},
            "center_nm": {"type": "number", "exclusiveMinimum": 0},
            "fwhm_nm": {"type": "number", "exclusiveMinimum": 0},
            "profile_file": {"type": "string"},
        },
        "additionalProperties": False,
    }

    def emissivity(
        self,
        cfg: Dict[str, Any],
        band: Mapping[str, Any],
        wavelength_nm: np.ndarray,
        external_densities: Dict[str, float],
        eedf_pdf: np.ndarray,
        rate_calc: RateCalculator,
    ) -> np.ndarray:
        ne = float(external_densities.get("e", 0.0))
        nsrc = float(external_densities.get(str(band["source_density_key"]), 0.0))
        band_work = dict(band)
        if "cross_section_file" in band_work:
            band_work["cross_section_file"] = str(resolve_path(cfg, band_work["cross_section_file"]))
        k = reaction_rate_coefficient(rate_calc, band_work, eedf_pdf)
        photon_profile = band_profile(cfg, band, wavelength_nm)
        photon_energy_J = const.h * const.c / np.maximum(wavelength_nm * 1.0e-9, 1.0e-30)
        photon_rate = (
            ne
            * nsrc
            * k
            * float(band["photon_yield"])
            * float(band.get("branching_ratio", 1.0))
        )
        return photon_rate * photon_profile * photon_energy_J / (4.0 * np.pi)


BAND_PROFILE_PLUGINS.register(_GaussianBandProfile())
BAND_PROFILE_PLUGINS.register(_TabulatedBandProfile())
BAND_EMISSION_PLUGINS.register(_EffectiveExcitationBand())
BAND_EMISSION_PLUGINS.register(_EffectiveDensityBand())
BAND_EMISSION_PLUGINS.register(_ElectronImpactPhotonBand())


def resolve_band_profile_spec(band: Mapping[str, Any]) -> Dict[str, Any]:
    kind = str(band.get("profile_kind", "gaussian"))
    spec: Dict[str, Any] = {"kind": kind}
    if kind == "gaussian":
        spec["center_nm"] = float(band["center_nm"])
        spec["fwhm_nm"] = float(band.get("fwhm_nm", 5.0))
    elif kind == "tabulated":
        spec["profile_file"] = str(band["profile_file"])
    else:
        spec.update(dict(band))
    return spec


def band_profile(
    cfg: Dict[str, Any],
    band: Mapping[str, Any],
    wavelength_nm: np.ndarray,
    *,
    validate: bool = True,
) -> np.ndarray:
    spec = resolve_band_profile_spec(band)
    plugin = BAND_PROFILE_PLUGINS.get(str(spec["kind"]))
    if validate:
        plugin.validate_config(spec)
    return plugin.profile(cfg, band, wavelength_nm)


def evaluate_band_components_zone(
    cfg: Dict[str, Any],
    zone_idx: int,
    wavelength_nm: np.ndarray,
    external_densities: Dict[str, float],
    eedf_pdf: np.ndarray,
    rate_calc: RateCalculator,
    *,
    validate_plugins: bool = True,
) -> Dict[str, BandSpectrum]:
    _ = zone_idx
    components: Dict[str, BandSpectrum] = {}
    for band in cfg.get("bands", []):
        plugin = BAND_EMISSION_PLUGINS.get(str(band["kind"]))
        if validate_plugins:
            plugin.validate_config(band)
        band_id = str(band["id"])
        diagnostics: Dict[str, Any] = {"id": band_id, "kind": str(band["kind"])}
        if "cross_section_file" in band:
            resolved = str(resolve_path(cfg, str(band["cross_section_file"])))
            diagnostics["cross_section"] = rate_calc.cross_section_coverage(resolved, eedf_pdf).as_dict()
        elif isinstance(band.get("rate_model"), dict):
            rate_model = band["rate_model"]
            if rate_model.get("kind") == "cross_section_file":
                resolved = str(resolve_path(cfg, str(rate_model["cross_section_file"])))
                diagnostics["cross_section"] = rate_calc.cross_section_coverage(resolved, eedf_pdf).as_dict()
        components[band_id] = BandSpectrum(
            spectrum=plugin.emissivity(
                cfg,
                band,
                wavelength_nm,
                external_densities,
                eedf_pdf,
                rate_calc,
            ),
            output_basis=plugin.output_basis,
            diagnostics=diagnostics,
        )
    return components
