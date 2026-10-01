"""Structural and semantic validation for OESCR configurations.

The validation stack is intentionally layered:

- JSON Schema checks for user-facing YAML structure.
- semantic checks for cross-field consistency and plugin contracts.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping

import numpy as np

from ..geometry.plugin import GEOMETRY_PLUGINS
from ..instrument.baseline import BASELINE_PLUGINS
from ..instrument.calibration import CalibrationTransform
from ..instrument.lsf import LSF_PLUGINS
from ..instrument.spec import normalize_instrument_config
from ..instrument.throughput import THROUGHPUT_PLUGINS
from ..physics.bands import BAND_EMISSION_PLUGINS, BAND_PROFILE_PLUGINS, resolve_band_profile_spec
from ..physics.cr_processes import compile_reaction_processes
from ..physics.eedf import EEDF_PLUGINS, resolve_eedf_plugin_spec
from ..physics.quality import validate_diagnostic_config
from ..physics.rates import REACTION_RATE_PLUGINS, resolve_reaction_rate_spec
from ..physics.trapping import TRAPPING_PLUGINS, resolve_trapping_spec
from ..physics.wall import WALL_LOSS_PLUGINS, resolve_gamma, resolve_wall_model_kind
from .pathmap import get_path
from .schema import validate_document
from .species_packs import compose_species_packs

VALID_PLASMA_MODES = {"te", "eedf_bimaxwell", "eedf_tabulated"}


class ConfigSemanticError(ValueError):
    pass


def _validate_unique_ids(items: Iterable[Mapping[str, Any]], section: str, *, required: bool = True) -> None:
    seen: set[str] = set()
    for index, item in enumerate(items):
        raw_id = item.get("id")
        if raw_id is None:
            if required:
                raise ConfigSemanticError(f"{section}[{index}] requires an id.")
            continue
        item_id = str(raw_id)
        if item_id in seen:
            raise ConfigSemanticError(f"Duplicate {section} id: {item_id}")
        seen.add(item_id)


def validate_case_structural(cfg: Dict[str, Any]) -> None:
    composed, _ = compose_species_packs(cfg)
    validate_document(composed, "case")


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
    CalibrationTransform.from_instrument_config(spec)


def validate_window_registry(cfg: Dict[str, Any]) -> None:
    validate_document(cfg, "windows")


def _check_shell_length(name: str, values: Iterable[Any], expected: int) -> None:
    n = len(list(values))
    if n != expected:
        raise ConfigSemanticError(f"{name} length {n} does not match geometry.n_shells={expected}.")


def _validate_legacy_eedf_zone_arrays(
    case_cfg: Mapping[str, Any],
    plasma_state: Mapping[str, Any],
    n_shells: int,
) -> None:
    mode = case_cfg.get("plasma_mode", "te")
    if mode == "te" and "te_shells_eV" in plasma_state:
        _check_shell_length("plasma_state.te_shells_eV", plasma_state["te_shells_eV"], n_shells)
    if mode == "te" and plasma_state.get("te_eedf_kind") == "bi_maxwell":
        if "te_bimaxwell_shells" not in plasma_state:
            raise ConfigSemanticError(
                "plasma_state.te_bimaxwell_shells is required when te_eedf_kind=bi_maxwell."
            )
        _check_shell_length(
            "plasma_state.te_bimaxwell_shells", plasma_state["te_bimaxwell_shells"], n_shells
        )
    if mode == "eedf_bimaxwell":
        if "eedf_bimaxwell_shells" not in plasma_state:
            raise ConfigSemanticError("plasma_state.eedf_bimaxwell_shells is required for eedf_bimaxwell mode.")
        _check_shell_length(
            "plasma_state.eedf_bimaxwell_shells", plasma_state["eedf_bimaxwell_shells"], n_shells
        )
    if mode == "eedf_tabulated":
        if "eedf_tabulated_shells" not in plasma_state:
            raise ConfigSemanticError("plasma_state.eedf_tabulated_shells is required for eedf_tabulated mode.")
        _check_shell_length(
            "plasma_state.eedf_tabulated_shells", plasma_state["eedf_tabulated_shells"], n_shells
        )


def _validate_external_density_arrays(
    case_cfg: Mapping[str, Any],
    plasma_state: Mapping[str, Any],
    n_shells: int,
) -> None:
    for group_name in ("metastables", "radicals"):
        for species, arr in plasma_state.get(group_name, {}).items():
            _check_shell_length(f"plasma_state.{group_name}.{species}", arr, n_shells)
    residuals = case_cfg.get("residuals", {})
    if residuals.get("mode", "off") != "off":
        for species, arr in residuals.get("species_density_m3", {}).items():
            if isinstance(arr, list):
                _check_shell_length(f"residuals.species_density_m3.{species}", arr, n_shells)


def _validate_zone_arrays(case_cfg: Mapping[str, Any]) -> None:
    n_shells = int(case_cfg.get("geometry", {}).get("n_shells", 1))
    plasma_state = case_cfg.get("plasma_state", {})
    if "ne_shells_m3" in plasma_state:
        _check_shell_length("plasma_state.ne_shells_m3", plasma_state["ne_shells_m3"], n_shells)
    if "eedf" in case_cfg:
        _check_shell_length("eedf.zones", case_cfg["eedf"].get("zones", []), n_shells)
    else:
        _validate_legacy_eedf_zone_arrays(case_cfg, plasma_state, n_shells)
    _validate_external_density_arrays(case_cfg, plasma_state, n_shells)


def _validate_eedf_plugins(case_cfg: Mapping[str, Any]) -> None:
    n_shells = int(case_cfg.get("geometry", {}).get("n_shells", 1))
    for zone_idx in range(n_shells):
        spec = resolve_eedf_plugin_spec(dict(case_cfg), zone_idx)
        EEDF_PLUGINS.validate(str(spec["kind"]), spec)


def _validate_reaction_processes(case_cfg: Mapping[str, Any]) -> None:
    states = {str(item["id"]): bool(item.get("solve", True)) for item in case_cfg.get("states", [])}
    solved_states = {state_id for state_id, solved in states.items() if solved}
    external_like = set(case_cfg.get("gas_mixture", {}).get("fractions", {}).keys())
    external_like |= set(case_cfg.get("plasma_state", {}).get("metastables", {}).keys())
    external_like |= set(case_cfg.get("plasma_state", {}).get("radicals", {}).keys())
    residuals = case_cfg.get("residuals", {})
    if residuals.get("mode", "off") != "off":
        external_like |= set(residuals.get("species_density_m3", {}).keys())
    external_like.add("e")
    try:
        compile_reaction_processes(case_cfg, validate_plugins=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigSemanticError(str(exc)) from exc

    for rxn in case_cfg.get("reactions", []):
        reaction_id = str(rxn.get("id", "<unknown>"))
        source = str(rxn["source_state"])
        target_value = rxn.get("target_state")
        target = str(target_value) if target_value is not None else None
        if source not in solved_states and source not in external_like:
            if source in states:
                detail = "is declared solve=false but has no external density"
            else:
                detail = "is not a solved state or external density"
            raise ConfigSemanticError(
                f"Reaction '{reaction_id}' source_state '{source}' {detail}."
            )
        if target is not None and target not in states and target not in external_like:
            raise ConfigSemanticError(
                f"Reaction '{reaction_id}' target_state '{target}' is not a known state or external density; "
                "omit target_state for an untracked sink."
            )
        if source not in solved_states and target not in solved_states:
            raise ConfigSemanticError(
                f"Reaction '{reaction_id}' must connect to at least one solved state."
            )
        for collider in rxn.get("colliders", []):
            if collider not in external_like:
                raise ConfigSemanticError(
                    f"Reaction '{reaction_id}' collider '{collider}' must be an externally supplied density; "
                    "coupling solved-state colliders would make the current CR system nonlinear."
                )


def _validate_transition_plugins(case_cfg: Mapping[str, Any]) -> None:
    known_states = {st["id"] for st in case_cfg.get("states", [])}
    for tr in case_cfg.get("transitions", []):
        if tr["upper"] not in known_states:
            raise ConfigSemanticError(f"Transition '{tr.get('id', tr['upper'])}' upper state unknown: {tr['upper']}")
        if tr["upper"] == tr["lower"]:
            raise ConfigSemanticError(
                f"Transition '{tr.get('id', tr['upper'])}' upper and lower states must differ."
            )
        spec = resolve_trapping_spec(tr)
        TRAPPING_PLUGINS.validate(str(spec["kind"]), spec)
        prof = tr.get("profile")
        if prof is not None:
            if str(prof.get("kind", "gaussian")) != "gaussian":
                raise ConfigSemanticError(
                    f"Transition '{tr.get('id', tr['upper'])}' profile kind must be 'gaussian' in the current implementation."
                )


def _validate_band_plugins(case_cfg: Mapping[str, Any]) -> None:
    emission_mode = str(case_cfg.get("emission_mode", "physical"))
    empirical_kinds = {"effective_excitation_band", "effective_density_band"}
    empirical_ids = [
        str(band.get("id", "<unknown>"))
        for band in case_cfg.get("bands", [])
        if str(band.get("kind")) in empirical_kinds
    ]
    if empirical_ids and emission_mode != "empirical":
        raise ConfigSemanticError(
            "Legacy effective bands require emission_mode='empirical'; "
            f"affected bands: {', '.join(empirical_ids)}."
        )

    ps = case_cfg.get("plasma_state", {})
    available_sources = {"e"}
    available_sources |= set(ps.get("metastables", {}).keys())
    available_sources |= set(ps.get("radicals", {}).keys())
    available_sources |= set(case_cfg.get("gas_mixture", {}).get("fractions", {}).keys())
    for band in case_cfg.get("bands", []):
        BAND_EMISSION_PLUGINS.validate(str(band["kind"]), band)
        if str(band["kind"]) in {"effective_excitation_band", "electron_impact_photon_band"}:
            rate_spec = resolve_reaction_rate_spec(band)
            REACTION_RATE_PLUGINS.validate(str(rate_spec["kind"]), rate_spec)
        BAND_PROFILE_PLUGINS.validate(str(resolve_band_profile_spec(band)["kind"]), resolve_band_profile_spec(band))
        src_key = band.get("source_density_key")
        if src_key not in available_sources:
            # allow arbitrary external source keys but force explicit user acknowledgement via radicals/metastables later
            raise ConfigSemanticError(
                f"Band '{band.get('id')}' source_density_key '{src_key}' is not present in gas fractions, radicals, or metastables."
            )


def _validate_eedf_selection(cfg: Mapping[str, Any]) -> None:
    if "eedf" in cfg and "plasma_mode" in cfg:
        raise ConfigSemanticError("Use either the public eedf envelope or legacy plasma_mode, not both.")
    if "eedf" not in cfg:
        mode = cfg.get("plasma_mode", "te")
        if mode not in VALID_PLASMA_MODES:
            raise ConfigSemanticError(f"Unsupported plasma_mode: {mode}")


def _validate_geometry_config(cfg: Mapping[str, Any]) -> None:
    geom = cfg.get("geometry", {})
    geom_mode = geom.get("mode", "axisym_shell")
    GEOMETRY_PLUGINS.validate(str(geom_mode), geom)
    if geom_mode not in {"axisym_shell", "asym_lowrank"}:
        return
    if "chord_r_m" not in geom:
        raise ConfigSemanticError("geometry.chord_r_m is required for shell-based geometries.")
    if "chamber_radius_m" not in geom:
        raise ConfigSemanticError("geometry.chamber_radius_m is required for shell-based geometries.")
    if int(geom.get("n_shells", 1)) < 1:
        raise ConfigSemanticError("geometry.n_shells must be >= 1.")


def _validate_case_inventory(cfg: Mapping[str, Any]) -> None:
    states = cfg.get("states", [])
    if "reactions" not in cfg:
        raise ConfigSemanticError("No reactions section defined.")
    if not states and not cfg.get("bands", []):
        raise ConfigSemanticError("A case must define at least one atomic state or molecular band.")

    _validate_unique_ids(states, "states")
    _validate_unique_ids(cfg.get("reactions", []), "reactions")
    _validate_unique_ids(cfg.get("transitions", []), "transitions", required=False)
    _validate_unique_ids(cfg.get("bands", []), "bands")
    _validate_unique_ids(cfg.get("instruments", []), "instruments")

    if not cfg.get("instruments", []):
        raise ConfigSemanticError("No instruments defined in case config.")


def _validate_gas_fractions(cfg: Mapping[str, Any]) -> None:
    fractions = cfg.get("gas_mixture", {}).get("fractions", {})
    fraction_sum = float(sum(float(value) for value in fractions.values()))
    if not np.isclose(fraction_sum, 1.0, rtol=0.0, atol=1.0e-6):
        raise ConfigSemanticError(f"gas_mixture.fractions must sum to 1.0; got {fraction_sum:.12g}.")


def _validate_wall_config(cfg: Mapping[str, Any]) -> None:
    wall_cfg = cfg.get("wall", {})
    WALL_LOSS_PLUGINS.validate(resolve_wall_model_kind(wall_cfg), wall_cfg)
    if resolve_wall_model_kind(wall_cfg) != "none":
        for state in cfg.get("states", []):
            if not bool(state.get("solve", True)):
                continue
            gamma = resolve_gamma(
                wall_cfg,
                str(state["id"]),
                str(state.get("species", str(state["id"]).split("_")[0])),
            )
            if gamma > 0.0 and state.get("mass_amu") is None:
                raise ConfigSemanticError(
                    f"State '{state['id']}' needs mass_amu because its wall-loss gamma is non-zero."
                )


def validate_case_config(cfg: Dict[str, Any]) -> None:
    """Validate case semantics after structural validation and normalization."""

    _validate_eedf_selection(cfg)
    _validate_geometry_config(cfg)
    _validate_case_inventory(cfg)
    _validate_gas_fractions(cfg)
    _validate_zone_arrays(cfg)
    _validate_eedf_plugins(cfg)
    _validate_reaction_processes(cfg)
    _validate_transition_plugins(cfg)
    _validate_band_plugins(cfg)
    try:
        validate_diagnostic_config(cfg)
    except ValueError as exc:
        raise ConfigSemanticError(str(exc)) from exc
    _validate_wall_config(cfg)


def _validate_inverse_required_sections(inv_cfg: Mapping[str, Any]) -> None:
    if not inv_cfg.get("parameters"):
        raise ConfigSemanticError("Inverse config must define at least one parameter or parameter_group.")
    if not inv_cfg.get("measurements"):
        raise ConfigSemanticError("Inverse config must define measurements.")


def _validate_inverse_use_case(inv_cfg: Mapping[str, Any]) -> None:
    mode = str(inv_cfg.get("inference_mode", "relative_shape"))
    objective = inv_cfg.get("fit", {}).get("objective", {})
    auto_gain = bool(objective.get("auto_gain_fit", True))
    if mode == "calibrated_absolute" and auto_gain:
        raise ConfigSemanticError(
            "calibrated_absolute inference requires fit.objective.auto_gain_fit=false."
        )
    if mode in {"ratio_diagnostic", "actinometry"} and not _has_active_ratio_objective(inv_cfg):
        raise ConfigSemanticError(
            f"{mode} inference requires an active ratio objective: set window_ratio_weight > 0, "
            "a positive window_ratio_pairs[].weight, or ratio feature covariance."
        )


def _has_active_ratio_objective(inv_cfg: Mapping[str, Any]) -> bool:
    objective = inv_cfg.get("fit", {}).get("objective", {})
    default_weight = float(objective.get("window_ratio_weight", 0.0))
    if default_weight > 0.0:
        return True

    ratio_pairs = objective.get("window_ratio_pairs", [])
    if any(float(pair.get("weight", default_weight)) > 0.0 for pair in ratio_pairs):
        return True

    covariance_names = {
        str(name)
        for measurement in inv_cfg.get("measurements", [])
        for name in measurement.get("feature_covariance", {}).get("names", [])
    }
    named_ratio_features = {f"ratio:{pair['name']}" for pair in ratio_pairs if str(pair.get("name", "")).strip()}
    return bool(covariance_names & named_ratio_features)


def _validate_feature_covariance_name(feature_name: Any, named_ratio_pairs: set[str]) -> None:
    parts = str(feature_name).split(":")
    valid_window = len(parts) == 3 and parts[0] == "window" and parts[2] in {"area", "peak"}
    valid_ratio = len(parts) == 2 and parts[0] == "ratio" and parts[1] in named_ratio_pairs
    if not valid_window and not valid_ratio:
        raise ConfigSemanticError(
            "Feature covariance names must be window:<name>:area, window:<name>:peak, "
            "or ratio:<explicit_pair_name>; "
            f"got '{feature_name}'."
        )


def _validate_inverse_measurements(case_cfg: Mapping[str, Any], inv_cfg: Mapping[str, Any]) -> None:
    case_inst_ids = {str(item["id"]) for item in case_cfg.get("instruments", [])}
    ratio_pairs = inv_cfg.get("fit", {}).get("objective", {}).get("window_ratio_pairs", [])
    named_ratio_pairs = {str(pair["name"]) for pair in ratio_pairs if pair.get("name")}
    for measurement in inv_cfg.get("measurements", []):
        if str(measurement["instrument_id"]) not in case_inst_ids:
            raise ConfigSemanticError(
                "Measurement references "
                f"instrument_id='{measurement['instrument_id']}', which is absent from case.instruments."
            )
        if "covariance_file" in measurement and "covariance_files" in measurement:
            raise ConfigSemanticError("Measurement may declare covariance_file or covariance_files, not both.")
        if "covariance_file" in measurement and "file" not in measurement:
            raise ConfigSemanticError("covariance_file requires a single measurement file entry.")
        feature_names = list(measurement.get("feature_covariance", {}).get("names", []))
        for feature_name in feature_names:
            _validate_feature_covariance_name(feature_name, named_ratio_pairs)


def _validate_inverse_parameters(case_cfg: Mapping[str, Any], inv_cfg: Mapping[str, Any]) -> None:
    for parameter in inv_cfg.get("parameters", []):
        if "path" not in parameter:
            raise ConfigSemanticError(f"Inverse parameter is missing 'path': {parameter}")
        get_path(case_cfg, parameter["path"])  # raises cleanly if missing
        lo, hi = parameter["bounds"]
        if float(lo) >= float(hi):
            raise ConfigSemanticError(f"Parameter bounds must be ordered: {parameter['name']}")


def _constraint_targets_fitted_parameter(target_path: str, parameter_paths: set[str]) -> bool:
    return any(
        parameter_path == target_path
        or parameter_path.startswith(f"{target_path}[")
        or parameter_path.startswith(f"{target_path}.")
        for parameter_path in parameter_paths
    )


def _validate_inverse_constraints(case_cfg: Mapping[str, Any], inv_cfg: Mapping[str, Any]) -> None:
    parameter_paths = {str(parameter["path"]) for parameter in inv_cfg.get("parameters", [])}
    for prior in inv_cfg.get("priors", []):
        path = str(prior["path"])
        get_path(case_cfg, path)
        if not _constraint_targets_fitted_parameter(path, parameter_paths):
            raise ConfigSemanticError(
                f"Prior target '{path}' does not contain a fitted parameter; the residual would be constant."
            )
    for reg in inv_cfg.get("fit", {}).get("regularization", {}).get("smooth_arrays", []):
        if "path" in reg:
            path = str(reg["path"])
            arr = np.asarray(get_path(case_cfg, path), dtype=float)
            if arr.ndim != 1:
                raise ConfigSemanticError(f"Regularization target must be 1D: {path}")
            if not _constraint_targets_fitted_parameter(path, parameter_paths):
                raise ConfigSemanticError(
                    f"Regularization target '{path}' does not contain a fitted parameter; "
                    "the residual would be constant."
                )


def validate_inverse_config(case_cfg: Dict[str, Any], inv_cfg: Dict[str, Any]) -> None:
    """Validate cross-field inverse semantics behind one stable public entry point."""

    _validate_inverse_required_sections(inv_cfg)
    _validate_inverse_use_case(inv_cfg)
    _validate_inverse_measurements(case_cfg, inv_cfg)
    _validate_inverse_parameters(case_cfg, inv_cfg)
    _validate_inverse_constraints(case_cfg, inv_cfg)
