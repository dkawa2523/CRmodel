
from __future__ import annotations

import numpy as np

from .chords import shell_path_length


def shell_edges(radius_m: float, n_shells: int) -> np.ndarray:
    return np.linspace(0.0, radius_m, n_shells + 1)


def build_W_axisym_shell(chord_r_m: list[float], radius_m: float, n_shells: int) -> np.ndarray:
    edges = shell_edges(radius_m, n_shells)
    W = np.zeros((len(chord_r_m), n_shells), dtype=float)
    for i, b in enumerate(chord_r_m):
        for k in range(n_shells):
            W[i, k] = shell_path_length(edges[k], edges[k + 1], b)
    return W


def shell_centers(radius_m: float, n_shells: int) -> np.ndarray:
    edges = shell_edges(radius_m, n_shells)
    return 0.5 * (edges[:-1] + edges[1:])
