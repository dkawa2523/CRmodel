
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from ..data.atomic_db import StateRegistry
from ..forward.emissivity import atomic_line_spectrum_zone
from ..instrument.capability import all_instruments_low_res
from ..io.yaml_loader import load_yaml
from ..physics.bands import evaluate_band_components_zone
from ..physics.cr_atomic import CRDiagnostics
from ..physics.cr_processes import StateBalance
from ..physics.eedf import EEDFDiagnostics, build_eedf_for_zone, eedf_model_kind, summarize_eedf
from ..physics.quality import (
    DiagnosticReport,
    convergence_config,
    convergence_event,
    enforce_quality_policy,
    evaluate_zone_quality,
    quality_config,
)
from ..physics.residuals import build_external_densities
from .compiled import CompiledCase, compile_case


@dataclass
class ZoneDiagnostics:
    eedf: EEDFDiagnostics
    cr: CRDiagnostics
    reactions: List[Dict[str, Any]]
    processes: List[Dict[str, Any]]
    state_balances: Dict[str, StateBalance]
    bands: List[Dict[str, Any]]


@dataclass
class ForwardResult:
    spectra: Dict[str, Dict[str, Dict[str, Any]]]
    zone_populations: List[Dict[str, float]]
    fine_wavelength_nm: np.ndarray
    zone_emissivity: np.ndarray
    state_registry: StateRegistry
    zone_atomic_emissivity: np.ndarray
    zone_band_emissivity: np.ndarray
    zone_band_components: List[Dict[str, np.ndarray]]
    atomic_line_details: List[List[Dict[str, float]]]
    zone_diagnostics: List[ZoneDiagnostics]
    emission_basis: str
    emission_component_bases: Dict[str, str]
    provenance: Dict[str, Any]
    quality_report: DiagnosticReport


class OESCRModel:
    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.compiled = compile_case(cfg)
        self.cfg = self.compiled.cfg

    @classmethod
    def from_yaml(cls, case_path: str | Path) -> "OESCRModel":
        cfg = load_yaml(case_path)
        return cls(cfg)

    def capabilities(self) -> Dict[str, Any]:
        return {"all_low_res": all_instruments_low_res(self.compiled.instrument_cfgs)}

    def instrument_configs_for(self, cfg: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        """Return validated instrument configurations for a runtime case."""

        _, compiled = self._execution_plan(cfg)
        return compiled.instrument_cfgs

    def _execution_plan(self, cfg: Dict[str, Any] | None) -> tuple[Dict[str, Any], CompiledCase]:
        runtime_cfg = self.cfg if cfg is None else cfg
        if self.compiled.is_compatible(runtime_cfg):
            return runtime_cfg, self.compiled
        rebuilt = compile_case(runtime_cfg)
        return rebuilt.cfg, rebuilt

    @staticmethod
    def _maximum_spectrum_relative_l2(reference: ForwardResult, refined: ForwardResult) -> float:
        differences: List[float] = []
        for instrument_id, chord_map in reference.spectra.items():
            for chord_key, spectrum in chord_map.items():
                baseline = np.asarray(spectrum["intensity"], dtype=float)
                comparison = np.asarray(refined.spectra[instrument_id][chord_key]["intensity"], dtype=float)
                scale = max(float(np.linalg.norm(comparison)), float(np.linalg.norm(baseline)), 1.0e-30)
                differences.append(float(np.linalg.norm(comparison - baseline)) / scale)
        return max(differences, default=0.0)

    @staticmethod
    def _refined_config(
        cfg: Dict[str, Any],
        *,
        energy_factor: int = 1,
        wavelength_factor: int = 1,
    ) -> Dict[str, Any]:
        refined = deepcopy(cfg)
        diagnostics = refined.setdefault("diagnostics", {})
        diagnostics.setdefault("quality", {})["on_error"] = "report"
        diagnostics.setdefault("convergence", {})["enabled"] = False
        if energy_factor > 1:
            base_points = int(refined.get("energy_grid", {}).get("n_points", 800))
            refined.setdefault("energy_grid", {})["n_points"] = energy_factor * (base_points - 1) + 1
        if wavelength_factor > 1:
            numerics = refined.setdefault("numerics", {})
            base_factor = float(numerics.get("wavelength_refinement_factor", 1.0))
            numerics["wavelength_refinement_factor"] = base_factor * wavelength_factor
        return refined

    def _build_quality_report(
        self,
        cfg: Dict[str, Any],
        result: ForwardResult,
    ) -> DiagnosticReport:
        quality = quality_config(cfg)
        convergence = convergence_config(cfg)
        report = DiagnosticReport(enabled=bool(quality["enabled"] or convergence["enabled"]))
        if quality["enabled"]:
            for zone_index, diagnostics in enumerate(result.zone_diagnostics):
                report.events.extend(
                    evaluate_zone_quality(
                        zone_index=zone_index,
                        cr=diagnostics.cr,
                        eedf=diagnostics.eedf,
                        reaction_diagnostics=diagnostics.reactions,
                        band_diagnostics=diagnostics.bands,
                        thresholds=quality["thresholds"],
                    )
                )
        enforce_quality_policy(cfg, report)
        if not convergence["enabled"]:
            return report

        energy_factor = int(convergence["energy_grid_factor"])
        wavelength_factor = int(convergence["wavelength_grid_factor"])
        energy_result = OESCRModel(self._refined_config(cfg, energy_factor=energy_factor)).predict()
        wavelength_result = OESCRModel(
            self._refined_config(cfg, wavelength_factor=wavelength_factor)
        ).predict()
        energy_difference = self._maximum_spectrum_relative_l2(result, energy_result)
        wavelength_difference = self._maximum_spectrum_relative_l2(result, wavelength_result)
        report.convergence = {
            "energy_grid": {
                "refinement_factor": energy_factor,
                "maximum_relative_l2_difference": energy_difference,
            },
            "wavelength_grid": {
                "refinement_factor": wavelength_factor,
                "maximum_relative_l2_difference": wavelength_difference,
            },
        }
        for category, value in (
            ("convergence.energy_grid", energy_difference),
            ("convergence.wavelength_grid", wavelength_difference),
        ):
            event = convergence_event(category, value, convergence)
            if event is not None:
                report.events.append(event)
        enforce_quality_policy(cfg, report)
        return report

    def predict(self, cfg_override: Dict[str, Any] | None = None) -> ForwardResult:
        cfg, compiled = self._execution_plan(cfg_override)
        fine_wl = compiled.fine_wavelength_nm

        geom = cfg.get("geometry", {})
        n_shells = int(geom.get("n_shells", 1))
        zone_spectra = []
        zone_atomic_spectra = []
        zone_band_spectra = []
        zone_band_components: List[Dict[str, np.ndarray]] = []
        atomic_line_details: List[List[Dict[str, float]]] = []
        zone_diagnostics: List[ZoneDiagnostics] = []
        component_bases = {"atomic_lines": "spectral_radiant_power_W_m-3_sr-1_nm-1"}
        zone_pops = []

        for z in range(n_shells):
            external = build_external_densities(cfg, z)
            eedf_pdf = build_eedf_for_zone(cfg, z, compiled.energy_eV)
            cr = compiled.atomic_solver.solve_zone(z, external, eedf_pdf)
            atomic = atomic_line_spectrum_zone(
                cfg,
                compiled.state_registry,
                cr.populations_m3,
                fine_wl,
                zone_context=external,
                validate_plugins=False,
            )
            band_results = evaluate_band_components_zone(
                cfg,
                z,
                fine_wl,
                external,
                eedf_pdf,
                compiled.rate_calculator,
                validate_plugins=False,
            )
            band_components = {name: result.spectrum for name, result in band_results.items()}
            bands = np.sum(list(band_components.values()), axis=0) if band_components else np.zeros_like(fine_wl)
            for name, result in band_results.items():
                component_bases[name] = result.output_basis

            zone_spectra.append(atomic["spectrum"] + bands)
            zone_atomic_spectra.append(atomic["spectrum"])
            zone_band_spectra.append(bands)
            zone_band_components.append(band_components)
            atomic_line_details.append(atomic["lines"])
            zone_diagnostics.append(
                ZoneDiagnostics(
                    eedf=summarize_eedf(compiled.energy_eV, eedf_pdf),
                    cr=cr.diagnostics,
                    reactions=cr.reaction_diagnostics,
                    processes=cr.process_diagnostics,
                    state_balances=cr.state_balances,
                    bands=[result.diagnostics for result in band_results.values()],
                )
            )
            zone_pops.append(cr.populations_m3)

        zone_spectra_arr = np.asarray(zone_spectra)
        zone_atomic_arr = np.asarray(zone_atomic_spectra)
        zone_band_arr = np.asarray(zone_band_spectra)
        spectra = compiled.observation_plan.observe(cfg, zone_spectra_arr, fine_wl)
        unique_bases = set(component_bases.values())
        emission_basis = next(iter(unique_bases)) if len(unique_bases) == 1 else "mixed; inspect emission_component_bases"
        result = ForwardResult(
            spectra=spectra,
            zone_populations=zone_pops,
            fine_wavelength_nm=fine_wl,
            zone_emissivity=zone_spectra_arr,
            state_registry=compiled.state_registry,
            zone_atomic_emissivity=zone_atomic_arr,
            zone_band_emissivity=zone_band_arr,
            zone_band_components=zone_band_components,
            atomic_line_details=atomic_line_details,
            zone_diagnostics=zone_diagnostics,
            emission_basis=emission_basis,
            emission_component_bases=component_bases,
            provenance={
                "species_packs": compiled.species_pack_provenance,
                "eedf_kind": eedf_model_kind(cfg),
            },
            quality_report=DiagnosticReport(enabled=False),
        )
        result.quality_report = self._build_quality_report(cfg, result)
        return result
