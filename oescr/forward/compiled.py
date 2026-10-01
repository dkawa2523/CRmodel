"""Compilation boundary between user configuration and numerical execution.

The compiled case owns objects whose structure is fixed for a forward solve.
Plasma-state values may change between evaluations without rebuilding those
objects; changes to reactions, states, geometry, instruments, or other static
sections produce a new compiled case.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from ..data.atomic_db import StateRegistry
from ..data.cross_section_db import CrossSectionLibrary
from ..instrument.spec import normalize_instrument_config
from ..io.normalize import normalize_case_config
from ..io.species_packs import compose_species_packs
from ..io.validators import validate_case_config, validate_case_structural, validate_instrument_config
from ..io.yaml_loader import load_yaml, resolve_path
from ..physics.cr_atomic import AtomicCRSolver
from ..physics.cr_processes import CompiledReactionProcess, compile_reaction_processes
from ..physics.eedf import build_energy_grid
from ..physics.rates import RateCalculator
from .observe import ObservationPlan

# These sections contain values evaluated for every zone or are reporting-only.
# All other public case sections are structural and trigger recompilation when
# changed. Keeping this list short makes the safe behavior the default.
_RUNTIME_SECTIONS = {"plasma_state", "eedf", "residuals", "diagnostics", "benchmark_anchor", "metadata"}
_TRANSPORT_KEYS = {"_instrument_cfgs", "_fine_wavelength_nm", "__path__"}


def static_case_view(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Return the part of a normalized case that defines compiled structure."""

    return {
        key: deepcopy(value)
        for key, value in cfg.items()
        if key not in _RUNTIME_SECTIONS and key not in _TRANSPORT_KEYS
    }


def load_instrument_configs(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Load, validate, and normalize all instruments referenced by a case."""

    out: List[Dict[str, Any]] = []
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


def build_fine_wavelength_grid(
    cfg: Dict[str, Any],
    instrument_cfgs: List[Dict[str, Any]],
) -> np.ndarray:
    """Build a shared grid that resolves detector bins, LSFs, and atomic lines."""

    minima: List[float] = []
    maxima: List[float] = []
    step_candidates: List[float] = []

    for inst_cfg in instrument_cfgs:
        if "wavelength_grid_nm" in inst_cfg:
            grid = np.asarray(inst_cfg["wavelength_grid_nm"], dtype=float)
            minima.append(float(grid.min()))
            maxima.append(float(grid.max()))
            step_candidates.append(float(np.min(np.diff(grid))) / 8.0)
        else:
            minima.append(float(inst_cfg["wavelength_min_nm"]))
            maxima.append(float(inst_cfg["wavelength_max_nm"]))
            step_candidates.append(float(inst_cfg["bin_nm"]) / 8.0)

        lsf = inst_cfg.get("lsf", {})
        for name in ("fwhm_nm", "fwhm_g_nm", "fwhm_l_nm"):
            if name in lsf:
                step_candidates.append(float(lsf[name]) / 8.0)

    for transition in cfg.get("transitions", []):
        fwhm = float(transition.get("profile", {}).get("fwhm_nm", 0.02))
        step_candidates.append(fwhm / 6.0)

    if not minima or not step_candidates:
        raise ValueError("At least one valid instrument is required to build the wavelength grid.")
    refinement = float(cfg.get("numerics", {}).get("wavelength_refinement_factor", 1.0))
    dx = min(value for value in step_candidates if value > 0.0) / refinement
    return np.arange(min(minima) - 5.0, max(maxima) + 5.0 + 0.5 * dx, dx)


@dataclass
class CompiledCase:
    """Validated static numerical objects for one canonical case structure."""

    cfg: Dict[str, Any]
    static_view: Dict[str, Any]
    state_registry: StateRegistry
    energy_eV: np.ndarray
    cross_sections: CrossSectionLibrary
    rate_calculator: RateCalculator
    reaction_processes: tuple[CompiledReactionProcess, ...]
    atomic_solver: AtomicCRSolver
    instrument_cfgs: List[Dict[str, Any]]
    fine_wavelength_nm: np.ndarray
    species_pack_provenance: List[Dict[str, Any]]
    observation_plan: ObservationPlan

    def is_compatible(self, runtime_cfg: Dict[str, Any]) -> bool:
        return static_case_view(runtime_cfg) == self.static_view


def compile_case(cfg: Dict[str, Any]) -> CompiledCase:
    """Normalize and validate a case, then construct its static numerical plan."""

    composed, species_pack_provenance = compose_species_packs(cfg)
    validate_case_structural(composed)
    canonical = normalize_case_config(composed)
    validate_case_config(canonical)
    canonical = deepcopy(canonical)

    registry = StateRegistry(canonical)
    energy_eV = build_energy_grid(canonical)
    cross_sections = CrossSectionLibrary()
    rate_calculator = RateCalculator(energy_eV, cross_sections)
    reaction_processes = compile_reaction_processes(canonical, validate_plugins=False)
    atomic_solver = AtomicCRSolver(
        canonical,
        registry,
        rate_calculator,
        reaction_processes,
        validate_plugins=False,
    )
    instrument_cfgs = load_instrument_configs(canonical)
    fine_wavelength_nm = build_fine_wavelength_grid(canonical, instrument_cfgs)
    observation_plan = ObservationPlan.compile(canonical, instrument_cfgs, validated=True)

    return CompiledCase(
        cfg=canonical,
        static_view=static_case_view(canonical),
        state_registry=registry,
        energy_eV=energy_eV,
        cross_sections=cross_sections,
        rate_calculator=rate_calculator,
        reaction_processes=reaction_processes,
        atomic_solver=atomic_solver,
        instrument_cfgs=instrument_cfgs,
        fine_wavelength_nm=fine_wavelength_nm,
        species_pack_provenance=species_pack_provenance,
        observation_plan=observation_plan,
    )
