
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from ..data.atomic_db import StateRegistry
from ..data.cross_section_db import CrossSectionLibrary
from ..forward.emissivity import atomic_line_spectrum_zone
from ..forward.observe import observe_multi_instrument
from ..instrument.capability import all_instruments_low_res
from ..instrument.spec import normalize_instrument_config
from ..io.normalize import normalize_case_config
from ..io.validators import validate_case_config, validate_case_structural, validate_instrument_config
from ..io.yaml_loader import load_yaml, resolve_path
from ..physics.bands import evaluate_bands_zone
from ..physics.cr_atomic import AtomicCRSolver
from ..physics.eedf import build_eedf_for_zone, build_energy_grid
from ..physics.rates import RateCalculator
from ..physics.residuals import build_external_densities


@dataclass
class ForwardResult:
    spectra: Dict[str, Dict[str, Dict[str, np.ndarray]]]
    zone_populations: List[Dict[str, float]]
    fine_wavelength_nm: np.ndarray
    zone_emissivity: np.ndarray
    state_registry: StateRegistry


class OESCRModel:
    def __init__(self, cfg: Dict[str, Any]) -> None:
        validate_case_structural(cfg)
        cfg = normalize_case_config(cfg)
        validate_case_config(cfg)
        self.cfg = deepcopy(cfg)
        self.state_registry = StateRegistry(self.cfg)
        self.energy_eV = build_energy_grid(self.cfg)
        self.cs_library = CrossSectionLibrary()
        self.rate_calc = RateCalculator(self.energy_eV, self.cs_library)
        self.atomic_solver = AtomicCRSolver(self.cfg, self.state_registry, self.rate_calc)
        self.instrument_cfgs = self._load_instrument_cfgs(self.cfg)
        self.cfg["_instrument_cfgs"] = self.instrument_cfgs

    @classmethod
    def from_yaml(cls, case_path: str | Path) -> "OESCRModel":
        cfg = load_yaml(case_path)
        return cls(cfg)

    @staticmethod
    def _load_instrument_cfgs(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
        out = []
        for item in cfg.get("instruments", []):
            if "yaml_file" in item:
                inst_cfg = load_yaml(resolve_path(cfg, item["yaml_file"]))
                if "id" not in inst_cfg:
                    inst_cfg["id"] = item.get("id", Path(item["yaml_file"]).stem)
            else:
                inst_cfg = dict(item)
            validate_instrument_config(inst_cfg)
            out.append(normalize_instrument_config(inst_cfg))
        return out

    def capabilities(self) -> Dict[str, Any]:
        return {"all_low_res": all_instruments_low_res(self.instrument_cfgs)}

    def _fine_wavelength_grid(self) -> np.ndarray:
        mins = []
        maxs = []
        bins = []
        for inst_cfg in self.instrument_cfgs:
            if "wavelength_grid_nm" in inst_cfg:
                grid = np.asarray(inst_cfg["wavelength_grid_nm"], dtype=float)
                mins.append(grid.min())
                maxs.append(grid.max())
                bins.append(np.mean(np.diff(grid)))
            else:
                mins.append(float(inst_cfg["wavelength_min_nm"]))
                maxs.append(float(inst_cfg["wavelength_max_nm"]))
                bins.append(float(inst_cfg["bin_nm"]))
        dx = min(bins) / 8.0
        return np.arange(min(mins) - 5.0, max(maxs) + 5.0 + 0.5 * dx, dx)

    def predict(self, cfg_override: Dict[str, Any] | None = None) -> ForwardResult:
        cfg = deepcopy(self.cfg if cfg_override is None else cfg_override)
        instrument_cfgs = self._load_instrument_cfgs(cfg)
        fine_wl = self._fine_wavelength_grid()
        cfg["_fine_wavelength_nm"] = fine_wl

        geom = cfg.get("geometry", {})
        n_shells = int(geom.get("n_shells", 1))
        zone_spectra = []
        zone_pops = []

        for z in range(n_shells):
            external = build_external_densities(cfg, z)
            eedf_pdf = build_eedf_for_zone(cfg, z, self.energy_eV)
            cr = self.atomic_solver.solve_zone(z, external, eedf_pdf)
            atomic = atomic_line_spectrum_zone(cfg, self.state_registry, cr.populations_m3, fine_wl)
            bands = evaluate_bands_zone(cfg, z, fine_wl, external, eedf_pdf, self.rate_calc)
            zone_spectra.append(atomic["spectrum"] + bands)
            zone_pops.append(cr.populations_m3)

        zone_spectra_arr = np.asarray(zone_spectra)
        spectra = observe_multi_instrument(cfg, zone_spectra_arr, instrument_cfgs)
        return ForwardResult(
            spectra=spectra,
            zone_populations=zone_pops,
            fine_wavelength_nm=fine_wl,
            zone_emissivity=zone_spectra_arr,
            state_registry=self.state_registry,
        )
