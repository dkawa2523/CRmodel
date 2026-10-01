from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

import numpy as np

from ..data.atomic_db import StateRegistry
from .cr_processes import (
    CompiledReactionProcess,
    CRProcessContribution,
    StateBalance,
    assemble_reaction_process,
    build_state_balances,
    compile_reaction_processes,
    linear_transfer_contribution,
    sum_process_contributions,
)
from .rates import RateCalculator
from .trapping import effective_A
from .wall import effective_wall_loss_rate_s


@dataclass
class CRDiagnostics:
    solve_method: str
    system_size: int
    matrix_rank: int
    condition_number: float
    relative_residual: float
    negative_population_count: int
    negative_population_l1_m3: float
    negative_population_fraction: float


@dataclass
class AtomicCRResult:
    populations_m3: Dict[str, float]
    matrix: np.ndarray
    rhs: np.ndarray
    diagnostics: CRDiagnostics
    reaction_diagnostics: List[Dict[str, Any]]
    process_diagnostics: List[Dict[str, Any]]
    process_contributions: List[CRProcessContribution]
    state_balances: Dict[str, StateBalance]


class AtomicCRSolver:
    def __init__(
        self,
        cfg: Dict[str, Any],
        registry: StateRegistry,
        rate_calc: RateCalculator,
        reaction_processes: Sequence[CompiledReactionProcess] | None = None,
        *,
        validate_plugins: bool = True,
    ) -> None:
        self.cfg = cfg
        self.registry = registry
        self.rate_calc = rate_calc
        self.reaction_processes = tuple(
            reaction_processes
            if reaction_processes is not None
            else compile_reaction_processes(cfg, validate_plugins=validate_plugins)
        )
        self.validate_plugins = validate_plugins

    def _reaction_contributions(
        self,
        external_densities: Dict[str, float],
        eedf_pdf: np.ndarray,
    ) -> List[CRProcessContribution]:
        return [
            assemble_reaction_process(
                process,
                self.registry,
                self.rate_calc,
                external_densities,
                eedf_pdf,
            )
            for process in self.reaction_processes
        ]

    def _radiative_contributions(
        self,
        external_densities: Dict[str, float],
    ) -> List[CRProcessContribution]:
        contributions: List[CRProcessContribution] = []
        for index, transition in enumerate(self.cfg.get("transitions", [])):
            upper = str(transition["upper"])
            lower = str(transition["lower"])
            if not self.registry.is_solved(upper):
                continue
            process_id = str(transition.get("id", f"transition_{index}"))
            if upper == lower:
                raise ValueError(f"Radiative process '{process_id}' upper and lower states must differ.")
            rate = effective_A(
                transition,
                zone_context=external_densities,
                validate=self.validate_plugins,
            )
            contributions.append(
                linear_transfer_contribution(
                    key=f"radiative:{process_id}",
                    process_id=process_id,
                    kind="radiative_transition",
                    family="radiative",
                    source_state=upper,
                    target_state=lower,
                    coefficient_value=rate,
                    coefficient_unit="s^-1",
                    effective_frequency_s_1=rate,
                    colliders=(),
                    collider_densities_m3={},
                    registry=self.registry,
                )
            )
        return contributions

    def _wall_contributions(self) -> List[CRProcessContribution]:
        contributions: List[CRProcessContribution] = []
        wall_cfg = self.cfg.get("wall", {})
        geometry_cfg = self.cfg.get("geometry", {})
        gas_temperature = float(self.cfg.get("gas_mixture", {}).get("gas_temperature_K", 300.0))
        for state_id in self.registry.solved_states:
            meta = self.registry.state(state_id)
            rate = effective_wall_loss_rate_s(
                wall_cfg=wall_cfg,
                geometry_cfg=geometry_cfg,
                gas_temperature_K=gas_temperature,
                state_id=state_id,
                species=meta.species,
                mass_amu=meta.mass_amu,
                validate=self.validate_plugins,
            )
            if rate <= 0.0:
                continue
            contributions.append(
                linear_transfer_contribution(
                    key=f"wall:{state_id}",
                    process_id=f"wall_{state_id}",
                    kind="wall_loss",
                    family="wall_loss",
                    source_state=state_id,
                    target_state=None,
                    coefficient_value=rate,
                    coefficient_unit="s^-1",
                    effective_frequency_s_1=rate,
                    colliders=(),
                    collider_densities_m3={},
                    registry=self.registry,
                )
            )
        return contributions

    @staticmethod
    def _solve_population_system(matrix: np.ndarray, rhs: np.ndarray) -> tuple[np.ndarray, CRDiagnostics]:
        if matrix.shape == (0, 0):
            return np.zeros(0, dtype=float), CRDiagnostics(
                solve_method="empty",
                system_size=0,
                matrix_rank=0,
                condition_number=1.0,
                relative_residual=0.0,
                negative_population_count=0,
                negative_population_l1_m3=0.0,
                negative_population_fraction=0.0,
            )
        try:
            raw_population = np.linalg.solve(matrix, rhs)
            solve_method = "solve"
        except np.linalg.LinAlgError:
            raw_population = np.linalg.lstsq(matrix, rhs, rcond=None)[0]
            solve_method = "lstsq"
        residual_norm = float(np.linalg.norm(matrix @ raw_population - rhs))
        negative = raw_population[raw_population < 0.0]
        population_l1 = float(np.sum(np.abs(raw_population)))
        diagnostics = CRDiagnostics(
            solve_method=solve_method,
            system_size=len(rhs),
            matrix_rank=int(np.linalg.matrix_rank(matrix)),
            condition_number=float(np.linalg.cond(matrix)),
            relative_residual=residual_norm / max(float(np.linalg.norm(rhs)), 1.0e-30),
            negative_population_count=len(negative),
            negative_population_l1_m3=float(np.sum(np.abs(negative))),
            negative_population_fraction=float(np.sum(np.abs(negative))) / max(population_l1, 1.0e-300),
        )
        return np.clip(raw_population, 0.0, None), diagnostics

    def solve_zone(
        self,
        zone_idx: int,
        external_densities: Dict[str, float],
        eedf_pdf: np.ndarray,
    ) -> AtomicCRResult:
        _ = zone_idx
        reaction_contributions = self._reaction_contributions(external_densities, eedf_pdf)
        contributions = [
            *reaction_contributions,
            *self._radiative_contributions(external_densities),
            *self._wall_contributions(),
        ]
        matrix, rhs = sum_process_contributions(contributions, len(self.registry.solved_states))
        population, diagnostics = self._solve_population_system(matrix, rhs)
        populations = {
            state_id: float(population[index])
            for state_id, index in self.registry.index.items()
        }
        return AtomicCRResult(
            populations_m3=populations,
            matrix=matrix,
            rhs=rhs,
            diagnostics=diagnostics,
            reaction_diagnostics=[item.diagnostic() for item in reaction_contributions],
            process_diagnostics=[item.diagnostic() for item in contributions],
            process_contributions=contributions,
            state_balances=build_state_balances(contributions, population, self.registry),
        )
