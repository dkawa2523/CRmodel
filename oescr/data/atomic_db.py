
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class StateMeta:
    id: str
    species: str
    energy_eV: float
    solve: bool = True
    mass_amu: float | None = None
    degeneracy: float | None = None


class StateRegistry:
    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.states: Dict[str, StateMeta] = {}
        for st in cfg.get("states", []):
            state_id = str(st["id"])
            if state_id in self.states:
                raise ValueError(f"Duplicate state id: {state_id}")
            meta = StateMeta(
                id=state_id,
                species=st.get("species", st["id"].split("_")[0]),
                energy_eV=float(st.get("energy_eV", 0.0)),
                solve=bool(st.get("solve", True)),
                mass_amu=st.get("mass_amu"),
                degeneracy=st.get("degeneracy"),
            )
            self.states[state_id] = meta
        self.solved_states: List[str] = [
            sid for sid, meta in self.states.items() if meta.solve
        ]
        self.index: Dict[str, int] = {sid: i for i, sid in enumerate(self.solved_states)}

    def is_solved(self, state_id: str | None) -> bool:
        return state_id is not None and state_id in self.index

    def state(self, state_id: str) -> StateMeta:
        return self.states[state_id]
