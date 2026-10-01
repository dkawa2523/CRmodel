from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np

from ..geometry.plugin import GeometryPlugin, get_geometry_plugin
from ..instrument.spec import InstrumentSpec


def build_geometry_matrix(cfg: Dict[str, Any]) -> np.ndarray:
    plugin = get_geometry_plugin(cfg)
    return plugin.build_matrix(cfg)


@dataclass
class ObservationPlan:
    geometry_plugin: GeometryPlugin
    geometry_matrix: np.ndarray
    instruments: List[InstrumentSpec]

    @classmethod
    def compile(
        cls,
        cfg: Dict[str, Any],
        instrument_cfgs: List[Dict[str, Any]],
        *,
        validated: bool = False,
    ) -> "ObservationPlan":
        plugin = get_geometry_plugin(cfg, validate=not validated)
        return cls(
            geometry_plugin=plugin,
            geometry_matrix=plugin.build_matrix(cfg),
            instruments=[InstrumentSpec(item, validated=validated) for item in instrument_cfgs],
        )

    def observe(
        self,
        cfg: Dict[str, Any],
        zone_spectra: np.ndarray,
        source_wavelength_nm: np.ndarray,
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        out: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for inst in self.instruments:
            fine_wl = inst.fine_grid_nm()
            zone_interp = np.asarray(
                [
                    np.interp(
                        fine_wl,
                        source_wavelength_nm,
                        zone_spectra[zone_index],
                        left=0.0,
                        right=0.0,
                    )
                    for zone_index in range(zone_spectra.shape[0])
                ]
            )
            chord_spectra = self.geometry_matrix @ zone_interp
            chord_spectra = self.geometry_plugin.postprocess_chord_spectra(cfg, chord_spectra)

            measurements: Dict[str, Dict[str, Any]] = {}
            for chord_idx in range(chord_spectra.shape[0]):
                measurements[f"chord_{chord_idx}"] = inst.observe(fine_wl, chord_spectra[chord_idx])
            out[inst.instrument_id] = measurements
        return out


def observe_multi_instrument(
    cfg: Dict[str, Any],
    zone_spectra: np.ndarray,
    source_wavelength_nm: np.ndarray,
    instrument_cfgs: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    return ObservationPlan.compile(cfg, instrument_cfgs).observe(cfg, zone_spectra, source_wavelength_nm)
