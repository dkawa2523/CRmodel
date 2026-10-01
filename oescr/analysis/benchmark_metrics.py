"""Pure benchmark metrics with no report-rendering dependencies."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

import numpy as np


def safe_mean(values: Iterable[float]) -> float:
    seq = [float(value) for value in values]
    return float(sum(seq) / len(seq)) if seq else 0.0


def safe_corr(first: np.ndarray, second: np.ndarray) -> float:
    if len(first) < 2 or len(second) < 2:
        return 1.0
    if np.allclose(first, first[0]) or np.allclose(second, second[0]):
        return 1.0
    return float(np.corrcoef(first, second)[0, 1])


def aggregate_window_rows(
    window_entries: List[Dict[str, Any]],
    group_keys: Tuple[str, ...],
    scenario_filter: Iterable[str] | None = None,
) -> List[Dict[str, Any]]:
    scenario_set = set(scenario_filter) if scenario_filter is not None else None
    grouped: Dict[Tuple[str, ...], List[Dict[str, Any]]] = {}
    for item in window_entries:
        if scenario_set is not None and str(item.get("scenario", "")) not in scenario_set:
            continue
        key = tuple(str(item.get(name, "")) for name in group_keys)
        grouped.setdefault(key, []).append(item)

    rows: List[Dict[str, Any]] = []
    for key, items in grouped.items():
        sample = items[0]
        row: Dict[str, Any] = {group_keys[index]: key[index] for index in range(len(group_keys))}
        row.update(
            {
                "kind": str(sample.get("kind", "")),
                "family": str(sample.get("family", "")),
                "mean_area_ratio": safe_mean(float(item["area_ratio"]) for item in items),
                "mean_peak_ratio": safe_mean(float(item["peak_ratio"]) for item in items),
                "mean_abs_peak_shift_nm": safe_mean(abs(float(item["peak_shift_nm"])) for item in items),
                "mean_abs_measurement_area": safe_mean(
                    abs(float(item["measurement_area"])) for item in items
                ),
            }
        )
        rows.append(row)
    return rows


def dominant_window_rows(
    window_entries: List[Dict[str, Any]], top_n: int = 3
) -> List[Dict[str, Any]]:
    rows = aggregate_window_rows(window_entries, ("window_name",))
    rows.sort(key=lambda item: item["mean_abs_measurement_area"], reverse=True)
    return rows[:top_n]


def trend_label(values: List[float]) -> str:
    if len(values) < 2:
        return "single-zone"
    differences = np.diff(np.asarray(values, dtype=float))
    if np.all(differences <= 0.0):
        return "monotonic decrease from core to edge"
    if np.all(differences >= 0.0):
        return "monotonic increase from core to edge"
    return "non-monotonic radial structure"


def group_indices(group: Dict[str, Any], values: List[Any]) -> List[int]:
    indices_cfg = group.get("indices", "all")
    if indices_cfg in {None, "all", "*"}:
        return list(range(len(values)))
    return [int(value) for value in indices_cfg]


def mean_abs_relative_error(first: np.ndarray, second: np.ndarray) -> float:
    denominator = np.maximum(np.abs(second), 1.0e-30)
    return float(np.mean(np.abs(first - second) / denominator))


def physical_uncertainty_fraction(
    scale: str,
    physical_value: float,
    opt_space_std: float | None,
) -> float | None:
    if opt_space_std is None:
        return None
    if scale == "log":
        return float(10.0 ** float(opt_space_std) - 1.0)
    denominator = max(abs(float(physical_value)), 1.0e-30)
    return float(abs(float(opt_space_std)) / denominator)
