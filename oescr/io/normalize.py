from __future__ import annotations

"""Configuration normalization.

These helpers convert compact, user-friendly YAML into the canonical internal
format consumed by the forward and inverse solvers. The normalization layer is
where we reduce input duplication and preserve backward compatibility.
"""

from copy import deepcopy
from typing import Any, Dict, Iterable, List

from .pathmap import get_path


_CASE_DEFAULTS: Dict[str, Any] = {
    "plasma_mode": "te",
    "energy_grid": {"min_eV": 0.0, "max_eV": 50.0, "n_points": 800},
    "geometry": {"mode": "axisym_shell", "n_shells": 1},
    "plasma_state": {"te_eedf_kind": "maxwell", "metastables": {}, "radicals": {}},
    "residuals": {"mode": "off", "species_density_m3": {}},
    "wall": {"gamma": {}, "priors": {}},
    "diagnostics": {"window_registry": None, "window_names": [], "window_families": []},
}

_INVERSE_DEFAULTS: Dict[str, Any] = {
    "fit": {
        "objective": {
            "spectrum_weight": 1.0,
            "window_fit_weight": 0.0,
            "window_fit_normalization": "area",
            "window_baseline_mode": "local_linear",
            "area_weight": 0.3,
            "peak_weight": 0.05,
            "auto_gain_fit": True,
            "auto_offset_fit": True,
            "auto_gain_scope": "chord",
            "gain_prior_weight": 0.0,
            "gain_prior_sigma_log10": 1.0,
            "window_ratio_weight": 0.0,
            "window_ratio_metric": "peak",
            "window_ratio_min_relative_signal": 0.02,
            "window_ratio_pairs": [],
        },
        "global": {"enabled": True, "maxiter": 20, "popsize": 8, "seed": 0, "tol": 1.0e-3},
        "local": {"enabled": True, "max_nfev": 200},
        "uncertainty": {"laplace": True},
        "regularization": {"smooth_arrays": []},
    },
    "measurements": [],
    "parameters": [],
    "parameter_groups": [],
    "priors": [],
}


def _deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        out = deepcopy(base)
        for key, value in override.items():
            if key in out:
                out[key] = _deep_merge(out[key], value)
            else:
                out[key] = deepcopy(value)
        return out
    return deepcopy(override)


def normalize_case_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    out = _deep_merge(_CASE_DEFAULTS, cfg)
    out.setdefault("states", [])
    out.setdefault("reactions", [])
    out.setdefault("transitions", [])
    out.setdefault("quenching", [])
    out.setdefault("losses", [])
    out.setdefault("bands", [])
    out.setdefault("instruments", [])
    out.setdefault("gas_mixture", {})
    out["plasma_state"].setdefault("metastables", {})
    out["plasma_state"].setdefault("radicals", {})
    out["residuals"].setdefault("species_density_m3", {})
    return out


# ---- inverse normalization helpers -----------------------------------------------------------


def _iter_indices(indices_cfg: Any, arr: Iterable[Any]) -> List[int]:
    arr_list = list(arr)
    if indices_cfg in {None, "all", "*"}:
        return list(range(len(arr_list)))
    return [int(i) for i in indices_cfg]


_GROUP_TEMPLATES = {"shell_array", "array", "radial_array"}


def expand_parameter_groups(case_cfg: Dict[str, Any], inv_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    explicit = list(inv_cfg.get("parameters", []))
    groups = inv_cfg.get("parameter_groups", [])
    if not groups:
        return explicit

    out = list(explicit)
    for group in groups:
        template = str(group.get("template", "shell_array"))
        if template not in _GROUP_TEMPLATES:
            raise ValueError(f"Unsupported parameter group template: {template}")
        path = str(group["path"])
        arr = get_path(case_cfg, path)
        indices = _iter_indices(group.get("indices", "all"), arr)
        name_prefix = str(group.get("name_prefix", path.split(".")[-1]))
        scale = str(group.get("scale", "linear"))
        bounds = [float(group["bounds"][0]), float(group["bounds"][1])]
        suffix_fmt = str(group.get("suffix_format", "{index}"))
        for idx in indices:
            out.append(
                {
                    "name": f"{name_prefix}{suffix_fmt.format(index=idx)}",
                    "path": f"{path}[{idx}]",
                    "scale": scale,
                    "bounds": bounds,
                }
            )
    return out


def _expand_measurement_groups(inv_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    measurements = list(inv_cfg.get("measurements", []))
    out: List[Dict[str, Any]] = []
    for item in measurements:
        if "files_glob" in item:
            out.append(
                {
                    "instrument_id": item["instrument_id"],
                    "files_glob": item["files_glob"],
                }
            )
        else:
            out.append(item)
    return out


def _normalize_regularization(inv_cfg: Dict[str, Any]) -> None:
    regs = inv_cfg.setdefault("fit", {}).setdefault("regularization", {}).setdefault("smooth_arrays", [])
    for reg in regs:
        if "path" not in reg and "name" in reg:
            reg["path"] = f"plasma_state.{reg['name']}"


def normalize_inverse_config(case_cfg: Dict[str, Any], inv_cfg: Dict[str, Any]) -> Dict[str, Any]:
    out = _deep_merge(_INVERSE_DEFAULTS, inv_cfg)
    out["measurements"] = _expand_measurement_groups(out)
    out["parameters"] = expand_parameter_groups(case_cfg, out)
    _normalize_regularization(out)
    return out
