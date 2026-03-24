
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

import numpy as np

from ..data.atomic_db import StateRegistry
from ..io.yaml_loader import resolve_path
from .rates import RateCalculator, reaction_rate_coefficient
from .trapping import effective_A
from .wall import effective_wall_loss_rate_s


@dataclass
class AtomicCRResult:
    populations_m3: Dict[str, float]
    matrix: np.ndarray
    rhs: np.ndarray


class AtomicCRSolver:
    def __init__(self, cfg: Dict[str, Any], registry: StateRegistry, rate_calc: RateCalculator) -> None:
        self.cfg = cfg
        self.registry = registry
        self.rate_calc = rate_calc

    def _reaction_rate_coeff(self, rxn: Dict[str, Any], eedf_pdf: np.ndarray) -> float:
        rxn_work = dict(rxn)
        if "cross_section_file" in rxn_work:
            rxn_work["cross_section_file"] = str(resolve_path(self.cfg, rxn_work["cross_section_file"]))
        if "rate_model" in rxn_work and isinstance(rxn_work["rate_model"], dict):
            rate_model = dict(rxn_work["rate_model"])
            if "cross_section_file" in rate_model:
                rate_model["cross_section_file"] = str(resolve_path(self.cfg, rate_model["cross_section_file"]))
            rxn_work["rate_model"] = rate_model
        return reaction_rate_coefficient(self.rate_calc, rxn_work, eedf_pdf)

    def solve_zone(
        self,
        zone_idx: int,
        external_densities: Dict[str, float],
        eedf_pdf: np.ndarray,
    ) -> AtomicCRResult:
        N = len(self.registry.solved_states)
        idx = self.registry.index
        M = np.zeros((N, N), dtype=float)
        b = np.zeros(N, dtype=float)

        ne = float(external_densities.get("e", 0.0))

        # Electron-driven or effective user-defined reactions.
        for rxn in self.cfg.get("reactions", []):
            src = rxn.get("source_state")
            tgt = rxn.get("target_state")
            k = self._reaction_rate_coeff(rxn, eedf_pdf)
            extra_factor = 1.0
            for collider in rxn.get("colliders", []):
                extra_factor *= float(external_densities.get(collider, 0.0))
            coeff = ne * k * extra_factor

            src_solved = self.registry.is_solved(src)
            tgt_solved = self.registry.is_solved(tgt)

            if src_solved:
                i = idx[src]
                M[i, i] += coeff
                if tgt_solved:
                    j = idx[tgt]
                    M[j, i] -= coeff
            else:
                nsrc = float(external_densities.get(src, 0.0))
                if tgt_solved:
                    j = idx[tgt]
                    b[j] += coeff * nsrc

        # Radiative cascade / losses.
        for tr in self.cfg.get("transitions", []):
            upper = tr["upper"]
            lower = tr["lower"]
            Aeff = effective_A(tr, zone_context=external_densities)
            if self.registry.is_solved(upper):
                iu = idx[upper]
                M[iu, iu] += Aeff
                if self.registry.is_solved(lower):
                    il = idx[lower]
                    M[il, iu] -= Aeff

        # Gas quenching.
        for q in self.cfg.get("quenching", []):
            st = q["state"]
            if not self.registry.is_solved(st):
                continue
            collider = q["collider"]
            nq = float(external_densities.get(collider, 0.0))
            kq = float(q["rate_coefficient_m3_s"])
            M[idx[st], idx[st]] += nq * kq

        # User-specified direct losses.
        for loss in self.cfg.get("losses", []):
            st = loss["state"]
            if not self.registry.is_solved(st):
                continue
            M[idx[st], idx[st]] += float(loss["rate_coefficient_s-1"])

        # Wall loss.
        wall_cfg = self.cfg.get("wall", {})
        geom_cfg = self.cfg.get("geometry", {})
        Tg = float(self.cfg.get("gas_mixture", {}).get("gas_temperature_K", 300.0))
        for state_id in self.registry.solved_states:
            meta = self.registry.state(state_id)
            kwall = effective_wall_loss_rate_s(
                wall_cfg=wall_cfg,
                geometry_cfg=geom_cfg,
                gas_temperature_K=Tg,
                state_id=state_id,
                species=meta.species,
                mass_amu=meta.mass_amu,
            )
            M[idx[state_id], idx[state_id]] += kwall

        # Stabilization.
        M += np.eye(N) * 1.0e-30

        try:
            n = np.linalg.solve(M, b)
        except np.linalg.LinAlgError:
            n = np.linalg.lstsq(M, b, rcond=None)[0]
        n = np.clip(n, 0.0, None)

        pops = {sid: float(n[i]) for sid, i in idx.items()}
        return AtomicCRResult(populations_m3=pops, matrix=M, rhs=b)
