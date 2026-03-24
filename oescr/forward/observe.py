from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ..geometry.plugin import get_geometry_plugin
from ..instrument.spec import InstrumentSpec


def build_geometry_matrix(cfg: Dict[str, Any]) -> np.ndarray:
    plugin = get_geometry_plugin(cfg)
    return plugin.build_matrix(cfg)


def observe_multi_instrument(
    cfg: Dict[str, Any],
    zone_spectra: np.ndarray,
    instrument_cfgs: List[Dict[str, Any]],
) -> Dict[str, Dict[str, np.ndarray]]:
    plugin = get_geometry_plugin(cfg)
    W = plugin.build_matrix(cfg)  # [n_chords, n_shells]
    out: Dict[str, Dict[str, np.ndarray]] = {}

    for inst_cfg in instrument_cfgs:
        inst = InstrumentSpec(inst_cfg)
        fine_wl = inst.fine_grid_nm()
        zone_interp = []
        for k in range(zone_spectra.shape[0]):
            zone_interp.append(
                np.interp(
                    fine_wl,
                    cfg["_fine_wavelength_nm"],
                    zone_spectra[k],
                    left=0.0,
                    right=0.0,
                )
            )
        zone_interp = np.asarray(zone_interp)
        chord_spectra = W @ zone_interp
        chord_spectra = plugin.postprocess_chord_spectra(cfg, chord_spectra)

        measurements = {}
        for chord_idx in range(chord_spectra.shape[0]):
            obs = inst.observe(fine_wl, chord_spectra[chord_idx])
            measurements[f"chord_{chord_idx}"] = obs

        out[inst.instrument_id] = measurements
    return out
