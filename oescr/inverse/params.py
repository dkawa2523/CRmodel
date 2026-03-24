
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

from ..io.pathmap import get_path, set_path


@dataclass
class Parameter:
    name: str
    path: str
    bounds: Tuple[float, float]
    scale: str = "linear"

    def to_opt(self, physical: float) -> float:
        if self.scale == "log":
            return float(np.log10(physical))
        return float(physical)

    def from_opt(self, opt_value: float) -> float:
        if self.scale == "log":
            return float(10.0 ** opt_value)
        return float(opt_value)

    @property
    def opt_bounds(self) -> Tuple[float, float]:
        if self.scale == "log":
            return float(np.log10(self.bounds[0])), float(np.log10(self.bounds[1]))
        return self.bounds


class ParameterSet:
    def __init__(self, params_cfg: Sequence[Dict[str, Any]]) -> None:
        self.params: List[Parameter] = []
        for p in params_cfg:
            self.params.append(
                Parameter(
                    name=p["name"],
                    path=p["path"],
                    bounds=(float(p["bounds"][0]), float(p["bounds"][1])),
                    scale=p.get("scale", "linear"),
                )
            )

    def initial_vector(self, case_cfg: Dict[str, Any]) -> np.ndarray:
        vals = []
        for p in self.params:
            vals.append(p.to_opt(float(get_path(case_cfg, p.path))))
        return np.asarray(vals, dtype=float)

    def bounds(self) -> Tuple[np.ndarray, np.ndarray]:
        lo = []
        hi = []
        for p in self.params:
            a, b = p.opt_bounds
            lo.append(a)
            hi.append(b)
        return np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)

    def apply_to_case(self, case_cfg: Dict[str, Any], x: np.ndarray) -> Dict[str, Any]:
        out = case_cfg
        for p, xv in zip(self.params, x):
            set_path(out, p.path, p.from_opt(float(xv)))
        return out

    def names(self) -> List[str]:
        return [p.name for p in self.params]
