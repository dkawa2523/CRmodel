"""Explicit interpretation rules for supported inverse-analysis use cases."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable

from ..instrument.calibration import CalibrationTransform
from ..physics.eedf import eedf_model_kind


@dataclass
class InferenceAssessment:
    mode: str
    absolute_scale_prerequisites_met: bool
    absolute_scale_locally_identifiable: bool | None
    warnings: list[str]
    assumptions: list[str]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _validate_calibrated_absolute(
    case_cfg: Dict[str, Any],
    instrument_cfgs: Iterable[Dict[str, Any]] | None,
    auto_gain: bool,
) -> list[str]:
    if auto_gain:
        raise ValueError(
            "calibrated_absolute inference requires fit.objective.auto_gain_fit=false; "
            "otherwise instrument gain absorbs the absolute emission scale."
        )

    instruments = list(instrument_cfgs or [])
    transforms = [CalibrationTransform.from_instrument_config(item) for item in instruments]
    uncalibrated = [
        str(item.get("id", "<unknown>"))
        for item, transform in zip(instruments, transforms, strict=True)
        if not transform.absolute
    ]
    if not instruments or uncalibrated:
        missing = ", ".join(uncalibrated) if uncalibrated else "<all>"
        raise ValueError(
            "calibrated_absolute inference requires calibration.absolute=true for every instrument; "
            f"missing for: {missing}."
        )

    empirical_bands = [
        str(item.get("id", "<unknown>"))
        for item in case_cfg.get("bands", [])
        if item.get("kind") != "electron_impact_photon_band"
    ]
    if empirical_bands:
        raise ValueError(
            "calibrated_absolute inference cannot combine empirical effective bands; "
            f"replace or remove: {', '.join(empirical_bands)}."
        )
    return [
        "Instrument throughput/gain and viewing geometry are supplied on an absolute scale.",
        "Emitter source densities and relevant quenching processes are externally constrained.",
    ]


def _relative_shape_assessment(
    fits_electron_density: bool,
    auto_gain: bool,
) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    if fits_electron_density and auto_gain:
        warnings.append(
            "Electron-density absolute scale is confounded with source density and fitted gain; "
            "interpret only constrained relative-profile information."
        )
    return warnings, ["Only relative spectral or spatial information is interpreted."]


def _ratio_assessment(objective: Dict[str, Any]) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    if float(objective.get("spectrum_weight", 0.0)) > 0.0:
        warnings.append("ratio_diagnostic also has spectrum_weight > 0; the result is not ratio-only.")
    return warnings, ["Only configured line/window ratios are interpreted as diagnostics."]


def _actinometry_assessment(auto_gain: bool) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    if auto_gain:
        warnings.append("Fitted gain is acceptable only when the actinometric ratio, not absolute intensity, is used.")
    return warnings, ["Actinometer and target excitation/quenching assumptions are externally validated."]


def assess_inference_use_case(
    case_cfg: Dict[str, Any],
    inv_cfg: Dict[str, Any],
    parameter_paths: Iterable[str],
    instrument_cfgs: Iterable[Dict[str, Any]] | None = None,
) -> InferenceAssessment:
    mode = str(inv_cfg.get("inference_mode", "relative_shape"))
    objective = inv_cfg.get("fit", {}).get("objective", {})
    auto_gain = bool(objective.get("auto_gain_fit", True))
    paths = list(parameter_paths)
    fits_electron_density = any(path.startswith("plasma_state.ne_shells_m3") for path in paths)

    absolute_scale_prerequisites_met = mode == "calibrated_absolute" and not auto_gain

    if mode == "calibrated_absolute":
        warnings: list[str] = []
        assumptions = _validate_calibrated_absolute(case_cfg, instrument_cfgs, auto_gain)
    elif mode == "relative_shape":
        warnings, assumptions = _relative_shape_assessment(fits_electron_density, auto_gain)
    elif mode == "ratio_diagnostic":
        warnings, assumptions = _ratio_assessment(objective)
    elif mode == "actinometry":
        warnings, assumptions = _actinometry_assessment(auto_gain)
    else:
        raise ValueError(f"Unsupported inference_mode: {mode}")

    if eedf_model_kind(case_cfg) == "eedf_tabulated":
        warnings.append(
            "Tabulated EEDF inversion requires an independently demonstrated kernel rank and explicit regularization."
        )

    return InferenceAssessment(
        mode=mode,
        absolute_scale_prerequisites_met=absolute_scale_prerequisites_met,
        absolute_scale_locally_identifiable=None,
        warnings=warnings,
        assumptions=assumptions,
    )
