from __future__ import annotations

"""Structural and semantic validation for OESCR configurations.

The validation stack is intentionally layered:

- JSON Schema checks for user-facing YAML structure.
- semantic checks for cross-field consistency and plugin contracts.
"""

from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

import numpy as np

from ..geometry.plugin import GEOMETRY_PLUGINS
from ..instrument.baseline import BASELINE_PLUGINS
from ..instrument.lsf import LSF_PLUGINS
from ..instrument.spec import normalize_instrument_config
from ..instrument.throughput import THROUGHPUT_PLUGINS
from ..physics.bands import BAND_EMISSION_PLUGINS, BAND_PROFILE_PLUGINS, resolve_band_profile_spec
from ..physics.eedf import EEDF_PLUGINS, resolve_eedf_plugin_spec
from ..physics.rates import REACTION_RATE_PLUGINS, resolve_reaction_rate_spec
from ..physics.trapping import TRAPPING_PLUGINS, resolve_trapping_spec
from ..physics.wall import WALL_LOSS_PLUGINS, resolve_wall_model_kind
from .pathmap import get_path
from .schema import validate_document

VALID_PLASMA_MODES = {"te", "eedf_bimaxwell", "eedf_tabulated"}
VALID_GEOMETRY_MODES = {"chordavg", "axisym_shell", "asym_lowrank", "user_field"}


class ConfigSemanticError(ValueError):
    pass


def validate_case_structural(cfg: Dict[str, Any]) -> None:
    validate_document(cfg, "case")


def validate_inverse_structural(cfg: Dict[str, Any]) -> None:
    validate_document(cfg, "inverse")


def validate_project_structural(cfg: Dict[str, Any]) -> None:
    validate_document(cfg, "project")


def validate_instrument_config(inst_cfg: Dict[str, Any]) -> None:
    validate_document(inst_cfg, "instrument")
    spec = normalize_instrument_config(inst_cfg)
    THROUGHPUT_PLUGINS.validate(str(spec["throughput"]["kind"]), spec["throughput"])
    LSF_PLUGINS.validate(str(spec["lsf"]["kind"]), spec["lsf"])
    BASELINE_PLUGINS.validate(str(spec["baseline"]["kind"]), spec["baseline"])


def validate_window_registry(cfg: Dict[str, Any]) -> None:
    validate_document(cfg, "windows")


def _check_shell_length(name: str, values: Iterable[Any], expected: int) -> None:
    n = len(list(values))
    if n != expected:
        raise ConfigSemanticError(f"{name} length {n} does not match geometry.n_shells={expected}.")


def _validate_zone_arrays(case_cfg: Mapping[str, Any]) -> None:
    geom = case_cfg.get("geometry", {})
    n_shells = int(geom.get("n_shells", 1))
    ps = case_cfg.get("plasma_state", {})
    if "ne_shells_m3" in ps:
        _check_shell_length("plasma_state.ne_shells_m3", ps["ne_shells_m3"], n_shells)
    if case_cfg.get("plasma_mode", "te") == "te" and "te_shells_eV" in ps:
        _check_shell_length("plasma_state.te_shells_eV", ps["te_shells_eV"], n_shells)
    for group_name in ("metastables", "radicals"):
        for species, arr in ps.get(group_name, {}).items():
            _check_shell_length(f"plasma_state.{group_name}.{species}", arr, n_shells)
    for species, arr in case_cfg.get("residuals", {}).get("species_density_m3", {}).items():
        if isinstance(arr, list):
            _check_shell_length(f"residuals.species_density_m3.{species}", arr, n_shells)


def _validate_eedf_plugins(case_cfg: Mapping[str, Any]) -> None:
    n_shells = int(case_cfg.get("geometry", {}).get("n_shells", 1))
    for zone_idx in range(n_shells):
        spec = resolve_eedf_plugin_spec(dict(case_cfg), zone_idx)
        EEDF_PLUGINS.validate(str(spec["kind"]), spec)


def _validate_reaction_plugins(case_cfg: Mapping[str, Any]) -> None:
    known_states = {st["id"] for st in case_cfg.get("states", [])}
    external_like = set(case_cfg.get("gas_mixture", {}).get("fractions", {}).keys())
    external_like |= set(case_cfg.get("plasma_state", {}).get("metastables", {}).keys())
    external_like |= set(case_cfg.get("plasma_state", {}).get("radicals", {}).keys())
    external_like |= set(case_cfg.get("residuals", {}).get("species_density_m3", {}).keys())
    external_like.add("e")
    for rxn in case_cfg.get("reactions", []):
        spec = resolve_reaction_rate_spec(rxn)
        REACTION_RATE_PLUGINS.validate(str(spec["kind"]), spec)
        for label in ("source_state", "target_state"):
            sid = rxn.get(label)
            if sid is None:
                continue
            if sid not in known_states and sid not in external_like:
                raise ConfigSemanticError(f"Reaction '{rxn.get('id')}' references unknown {label}: {sid}")
        for collider in rxn.get("colliders", []):
            if collider not in known_states and collider not in external_like:
                raise ConfigSemanticError(f"Reaction '{rxn.get('id')}' references unknown collider: {collider}")


def _validate_transition_plugins(case_cfg: Mapping[str, Any]) -> None:
    known_states = {st["id"] for st in case_cfg.get("states", [])}
    for tr in case_cfg.get("transitions", []):
        if tr["upper"] not in known_states:
            raise ConfigSemanticError(f"Transition '{tr.get('id', tr['upper'])}' upper state unknown: {tr['upper']}")
        spec = resolve_trapping_spec(tr)
        TRAPPING_PLUGINS.validate(str(spec["kind"]), spec)
        prof = tr.get("profile")
        if prof is not None:
            if str(prof.get("kind", "gaussian")) != "gaussian":
                raise ConfigSemanticError(
                    f"Transition '{tr.get('id', tr['upper'])}' profile kind must be 'gaussian' in the current implementation."
                )


def _validate_band_plugins(case_cfg: Mapping[str, Any]) -> None:
    n_shells = int(case_cfg.get("geometry", {}).get("n_shells", 1))
    ps = case_cfg.get("plasma_state", {})
    available_sources = {"e"}
    available_sources |= set(ps.get("metastables", {}).keys())
    available_sources |= set(ps.get("radicals", {}).keys())
    available_sources |= set(case_cfg.get("gas_mixture", {}).get("fractions", {}).keys())
    for band in case_cfg.get("bands", []):
        BAND_EMISSION_PLUGINS.validate(str(band["kind"]), band)
        BAND_PROFILE_PLUGINS.validate(str(resolve_band_profile_spec(band)["kind"]), resolve_band_profile_spec(band))
        src_key = band.get("source_density_key")
        if src_key not in available_sources:
            # allow arbitrary external source keys but force explicit user acknowledgement via radicals/metastables later
            raise ConfigSemanticError(
                f"Band '{band.get('id')}' source_density_key '{src_key}' is not present in gas fractions, radicals, or metastables."
            )


def validate_case_config(cfg: Dict[str, Any]) -> None:
    mode = cfg.get("plasma_mode", "te")
    if mode not in VALID_PLASMA_MODES:
        raise ConfigSemanticError(f"Unsupported plasma_mode: {mode}")

    geom = cfg.get("geometry", {})
    geom_mode = geom.get("mode", "axisym_shell")
    if geom_mode not in VALID_GEOMETRY_MODES:
        raise ConfigSemanticError(f"Unsupported geometry mode: {geom_mode}")
    GEOMETRY_PLUGINS.validate(str(geom_mode), geom)

    states = cfg.get("states", [])
    if not states:
        raise ConfigSemanticError("No states defined.")
    if "reactions" not in cfg:
        raise ConfigSemanticError("No reactions section defined.")

    instruments = cfg.get("instruments", [])
    if not instruments:
        raise ConfigSemanticError("No instruments defined in case config.")

    if geom_mode in {"axisym_shell", "asym_lowrank"}:
        if "chord_r_m" not in geom:
            raise ConfigSemanticError("geometry.chord_r_m is required for shell-based geometries.")
        if "chamber_radius_m" not in geom:
            raise ConfigSemanticError("geometry.chamber_radius_m is required for shell-based geometries.")
        if int(geom.get("n_shells", 1)) < 1:
            raise ConfigSemanticError("geometry.n_shells must be >= 1.")

    _validate_zone_arrays(cfg)
    _validate_eedf_plugins(cfg)
    _validate_reaction_plugins(cfg)
    _validate_transition_plugins(cfg)
    _validate_band_plugins(cfg)

    wall_cfg = cfg.get("wall", {})
    WALL_LOSS_PLUGINS.validate(resolve_wall_model_kind(wall_cfg), wall_cfg)


def validate_inverse_config(case_cfg: Dict[str, Any], inv_cfg: Dict[str, Any]) -> None:
    if not inv_cfg.get("parameters"):
        raise ConfigSemanticError("Inverse config must define at least one parameter or parameter_group.")
    if not inv_cfg.get("measurements"):
        raise ConfigSemanticError("Inverse config must define measurements.")

    case_inst_ids = {str(item["id"]) for item in case_cfg.get("instruments", [])}
    for m in inv_cfg.get("measurements", []):
        if str(m["instrument_id"]) not in case_inst_ids:
            raise ConfigSemanticError(
                f"Measurement references instrument_id='{m['instrument_id']}', which is absent from case.instruments."
            )

    for p in inv_cfg.get("parameters", []):
        if "path" not in p:
            raise ConfigSemanticError(f"Inverse parameter is missing 'path': {p}")
        get_path(case_cfg, p["path"])  # raises cleanly if missing
        lo, hi = p["bounds"]
        if float(lo) >= float(hi):
            raise ConfigSemanticError(f"Parameter bounds must be ordered: {p['name']}")

    for reg in inv_cfg.get("fit", {}).get("regularization", {}).get("smooth_arrays", []):
        if "path" in reg:
            arr = np.asarray(get_path(case_cfg, str(reg["path"])), dtype=float)
            if arr.ndim != 1:
                raise ConfigSemanticError(f"Regularization target must be 1D: {reg['path']}")


def validate_paths_exist(paths: Iterable[Path]) -> None:
    missing = [p for p in paths if not p.exists()]
    if missing:
        items = "\n  - ".join(str(p) for p in missing)
        raise ConfigSemanticError(f"Referenced file(s) do not exist:\n  - {items}")
