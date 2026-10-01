"""Compiled linear process records and auditable CR matrix contributions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Mapping, Sequence

import numpy as np

from ..data.atomic_db import StateRegistry
from ..io.yaml_loader import resolve_path
from .rates import (
    REACTION_RATE_PLUGINS,
    RateCalculator,
    reaction_rate_from_spec,
    resolve_reaction_rate_spec,
)


@dataclass(frozen=True)
class ReactionFamily:
    kind: str
    family: str
    collider_count: int
    coefficient_field: str | None
    coefficient_unit: str
    electron_driven: bool = False


REACTION_FAMILIES: Dict[str, ReactionFamily] = {
    "electron_excitation": ReactionFamily(
        kind="electron_excitation",
        family="electron_impact",
        collider_count=0,
        coefficient_field=None,
        coefficient_unit="m^3 s^-1",
        electron_driven=True,
    ),
    "first_order": ReactionFamily(
        kind="first_order",
        family="first_order",
        collider_count=0,
        coefficient_field="coefficient_s-1",
        coefficient_unit="s^-1",
    ),
    "two_body": ReactionFamily(
        kind="two_body",
        family="two_body",
        collider_count=1,
        coefficient_field="coefficient_m3_s",
        coefficient_unit="m^3 s^-1",
    ),
    "three_body": ReactionFamily(
        kind="three_body",
        family="three_body",
        collider_count=2,
        coefficient_field="coefficient_m6_s",
        coefficient_unit="m^6 s^-1",
    ),
}

_RATE_SOURCE_FIELDS = {
    "rate_model",
    "cross_section_file",
    "threshold_model",
    "coefficient_m3_s",
}
_CONSTANT_COEFFICIENT_FIELDS = {"coefficient_s-1", "coefficient_m3_s", "coefficient_m6_s"}


@dataclass(frozen=True)
class CompiledReactionProcess:
    id: str
    kind: str
    family: str
    source_state: str
    target_state: str | None
    colliders: tuple[str, ...]
    coefficient_unit: str
    coefficient: float | None = None
    rate_spec: Mapping[str, Any] | None = None


@dataclass
class CRProcessContribution:
    key: str
    id: str
    kind: str
    family: str
    source_state: str
    target_state: str | None
    coefficient_value: float
    coefficient_unit: str
    effective_frequency_s_1: float
    colliders: tuple[str, ...]
    collider_densities_m3: Dict[str, float]
    matrix: np.ndarray
    rhs: np.ndarray
    cross_section: Dict[str, Any] | None = None

    def diagnostic(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "family": self.family,
            "source_state": self.source_state,
            "target_state": self.target_state,
            "coefficient_value": self.coefficient_value,
            "coefficient_unit": self.coefficient_unit,
            "effective_frequency_s-1": self.effective_frequency_s_1,
            "colliders": list(self.colliders),
            "collider_densities_m3": dict(self.collider_densities_m3),
        }
        if self.cross_section is not None:
            result["cross_section"] = dict(self.cross_section)
        return result


@dataclass(frozen=True)
class StateBalance:
    sources_m3_s: Dict[str, float]
    losses_m3_s: Dict[str, float]
    total_source_m3_s: float
    total_loss_m3_s: float
    net_m3_s: float

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _resolve_rate_paths(case_cfg: Mapping[str, Any], spec: Mapping[str, Any]) -> Dict[str, Any]:
    resolved = dict(spec)
    if "cross_section_file" in resolved:
        resolved["cross_section_file"] = str(resolve_path(case_cfg, str(resolved["cross_section_file"])))
    return resolved


def _compile_reaction_process(
    case_cfg: Mapping[str, Any],
    reaction: Mapping[str, Any],
    *,
    validate_plugins: bool,
) -> CompiledReactionProcess:
    reaction_id = str(reaction.get("id", "<unknown>"))
    kind = str(reaction.get("kind", ""))
    if kind not in REACTION_FAMILIES:
        raise ValueError(
            f"Reaction '{reaction_id}' kind '{kind}' is unsupported; "
            f"expected one of {sorted(REACTION_FAMILIES)}."
        )
    family = REACTION_FAMILIES[kind]
    colliders = tuple(str(item) for item in reaction.get("colliders", []))
    if len(colliders) != family.collider_count:
        raise ValueError(
            f"Reaction '{reaction_id}' kind '{kind}' requires exactly "
            f"{family.collider_count} collider(s); got {len(colliders)}."
        )

    source_state = str(reaction["source_state"])
    target_value = reaction.get("target_state")
    target_state = str(target_value) if target_value is not None else None
    if target_state == source_state:
        raise ValueError(f"Reaction '{reaction_id}' source_state and target_state must differ.")

    if family.electron_driven:
        invalid_fields = set(reaction) & {"coefficient_s-1", "coefficient_m6_s"}
        if invalid_fields:
            raise ValueError(
                f"Reaction '{reaction_id}' kind '{kind}' cannot use {sorted(invalid_fields)}; "
                "electron-impact rates have units m^3 s^-1."
            )
        if target_state is None:
            raise ValueError(f"Reaction '{reaction_id}' kind '{kind}' requires target_state.")
        rate_spec = _resolve_rate_paths(case_cfg, resolve_reaction_rate_spec(reaction))
        if validate_plugins:
            REACTION_RATE_PLUGINS.validate(str(rate_spec["kind"]), rate_spec)
        return CompiledReactionProcess(
            id=reaction_id,
            kind=kind,
            family=family.family,
            source_state=source_state,
            target_state=target_state,
            colliders=colliders,
            coefficient_unit=family.coefficient_unit,
            rate_spec=rate_spec,
        )

    assert family.coefficient_field is not None
    present = (set(reaction) & _RATE_SOURCE_FIELDS) | (set(reaction) & _CONSTANT_COEFFICIENT_FIELDS)
    if present != {family.coefficient_field}:
        raise ValueError(
            f"Reaction '{reaction_id}' kind '{kind}' requires only "
            f"'{family.coefficient_field}' as its coefficient; got {sorted(present)}."
        )
    coefficient = float(reaction[family.coefficient_field])
    if not np.isfinite(coefficient) or coefficient < 0.0:
        raise ValueError(f"Reaction '{reaction_id}' coefficient must be finite and non-negative.")
    return CompiledReactionProcess(
        id=reaction_id,
        kind=kind,
        family=family.family,
        source_state=source_state,
        target_state=target_state,
        colliders=colliders,
        coefficient_unit=family.coefficient_unit,
        coefficient=coefficient,
    )


def compile_reaction_processes(
    case_cfg: Mapping[str, Any],
    *,
    validate_plugins: bool = True,
) -> tuple[CompiledReactionProcess, ...]:
    """Compile reaction dictionaries into fixed-order, dimensioned records."""

    return tuple(
        _compile_reaction_process(case_cfg, reaction, validate_plugins=validate_plugins)
        for reaction in case_cfg.get("reactions", [])
    )


def linear_transfer_contribution(
    *,
    key: str,
    process_id: str,
    kind: str,
    family: str,
    source_state: str,
    target_state: str | None,
    coefficient_value: float,
    coefficient_unit: str,
    effective_frequency_s_1: float,
    colliders: Sequence[str],
    collider_densities_m3: Mapping[str, float],
    registry: StateRegistry,
    external_source_density_m3: float | None = None,
    cross_section: Mapping[str, Any] | None = None,
) -> CRProcessContribution:
    """Build one linear transfer/loss contribution in ``M n = b`` form."""

    state_count = len(registry.solved_states)
    matrix = np.zeros((state_count, state_count), dtype=float)
    rhs = np.zeros(state_count, dtype=float)
    source_solved = registry.is_solved(source_state)
    target_solved = registry.is_solved(target_state)
    if source_solved:
        source_index = registry.index[source_state]
        matrix[source_index, source_index] += effective_frequency_s_1
        if target_solved:
            assert target_state is not None
            matrix[registry.index[target_state], source_index] -= effective_frequency_s_1
    elif target_solved:
        if external_source_density_m3 is None:
            raise ValueError(f"Process '{process_id}' requires external density for '{source_state}'.")
        assert target_state is not None
        rhs[registry.index[target_state]] += effective_frequency_s_1 * external_source_density_m3
    else:
        raise ValueError(f"Process '{process_id}' must connect to at least one solved state.")
    return CRProcessContribution(
        key=key,
        id=process_id,
        kind=kind,
        family=family,
        source_state=source_state,
        target_state=target_state,
        coefficient_value=coefficient_value,
        coefficient_unit=coefficient_unit,
        effective_frequency_s_1=effective_frequency_s_1,
        colliders=tuple(colliders),
        collider_densities_m3=dict(collider_densities_m3),
        matrix=matrix,
        rhs=rhs,
        cross_section=dict(cross_section) if cross_section is not None else None,
    )


def _external_density(external_densities: Mapping[str, float], name: str, process_id: str) -> float:
    if name not in external_densities:
        raise ValueError(f"Process '{process_id}' requires missing external density '{name}'.")
    value = float(external_densities[name])
    if not np.isfinite(value) or value < 0.0:
        raise ValueError(f"Process '{process_id}' external density '{name}' must be finite and non-negative.")
    return value


def assemble_reaction_process(
    process: CompiledReactionProcess,
    registry: StateRegistry,
    rate_calculator: RateCalculator,
    external_densities: Mapping[str, float],
    eedf_pdf: np.ndarray,
) -> CRProcessContribution:
    """Evaluate one compiled reaction and return its exact matrix/RHS contribution."""

    collider_names = ("e",) if process.family == "electron_impact" else process.colliders
    collider_values = [
        _external_density(external_densities, name, process.id) for name in collider_names
    ]
    collider_densities = dict(zip(collider_names, collider_values, strict=True))
    if process.rate_spec is not None:
        coefficient = reaction_rate_from_spec(
            rate_calculator,
            process.rate_spec,
            eedf_pdf,
            validate=False,
        )
    else:
        assert process.coefficient is not None
        coefficient = process.coefficient
    if not np.isfinite(coefficient) or coefficient < 0.0:
        raise ValueError(f"Process '{process.id}' evaluated coefficient must be finite and non-negative.")
    effective_frequency = coefficient * float(np.prod(collider_values, dtype=float))
    if not np.isfinite(effective_frequency):
        raise ValueError(f"Process '{process.id}' effective frequency is not finite.")

    source_density = None
    if not registry.is_solved(process.source_state):
        source_density = _external_density(external_densities, process.source_state, process.id)

    cross_section = None
    if process.rate_spec is not None and process.rate_spec.get("kind") == "cross_section_file":
        cross_section = rate_calculator.cross_section_coverage(
            str(process.rate_spec["cross_section_file"]),
            eedf_pdf,
        ).as_dict()
    return linear_transfer_contribution(
        key=f"reaction:{process.id}",
        process_id=process.id,
        kind=process.kind,
        family=process.family,
        source_state=process.source_state,
        target_state=process.target_state,
        coefficient_value=coefficient,
        coefficient_unit=process.coefficient_unit,
        effective_frequency_s_1=effective_frequency,
        colliders=collider_names,
        collider_densities_m3=collider_densities,
        registry=registry,
        external_source_density_m3=source_density,
        cross_section=cross_section,
    )


def sum_process_contributions(
    contributions: Iterable[CRProcessContribution],
    state_count: int,
) -> tuple[np.ndarray, np.ndarray]:
    matrix = np.zeros((state_count, state_count), dtype=float)
    rhs = np.zeros(state_count, dtype=float)
    for contribution in contributions:
        matrix += contribution.matrix
        rhs += contribution.rhs
    return matrix, rhs


def build_state_balances(
    contributions: Sequence[CRProcessContribution],
    populations_m3: np.ndarray,
    registry: StateRegistry,
) -> Dict[str, StateBalance]:
    """Convert matrix contributions into per-state volumetric source/loss rates."""

    balances: Dict[str, StateBalance] = {}
    for state_id, state_index in registry.index.items():
        sources: Dict[str, float] = {}
        losses: Dict[str, float] = {}
        for contribution in contributions:
            source_rate = float(contribution.rhs[state_index])
            for source_index, population in enumerate(populations_m3):
                if source_index == state_index:
                    continue
                source_rate += max(-float(contribution.matrix[state_index, source_index]), 0.0) * float(population)
            loss_rate = max(float(contribution.matrix[state_index, state_index]), 0.0) * float(
                populations_m3[state_index]
            )
            if source_rate > 0.0:
                sources[contribution.key] = source_rate
            if loss_rate > 0.0:
                losses[contribution.key] = loss_rate
        total_source = float(sum(sources.values()))
        total_loss = float(sum(losses.values()))
        balances[state_id] = StateBalance(
            sources_m3_s=sources,
            losses_m3_s=losses,
            total_source_m3_s=total_source,
            total_loss_m3_s=total_loss,
            net_m3_s=total_source - total_loss,
        )
    return balances
