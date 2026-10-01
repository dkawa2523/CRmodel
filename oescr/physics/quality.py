"""Actionable quality policy for forward-model numerical diagnostics."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

from .cr_atomic import CRDiagnostics
from .eedf import EEDFDiagnostics

DEFAULT_QUALITY_THRESHOLDS = {
    "cr_condition_warn_above": 1.0e10,
    "cr_condition_error_above": 1.0e14,
    "cr_residual_warn_above": 1.0e-8,
    "cr_residual_error_above": 1.0e-5,
    "negative_population_fraction_warn_above": 1.0e-12,
    "negative_population_fraction_error_above": 1.0e-6,
    "eedf_upper_decile_warn_above": 1.0e-2,
    "eedf_upper_decile_error_above": 5.0e-2,
    "eedf_edge_relative_warn_above": 2.0e-2,
    "eedf_edge_relative_error_above": 1.0e-1,
    "cross_section_coverage_warn_below": 0.99,
    "cross_section_coverage_error_below": 0.90,
}

DEFAULT_CONVERGENCE = {
    "enabled": False,
    "energy_grid_factor": 2,
    "wavelength_grid_factor": 2,
    "warn_relative_above": 1.0e-3,
    "error_relative_above": 1.0e-2,
}


@dataclass(frozen=True)
class DiagnosticEvent:
    category: str
    severity: str
    message: str
    zone_index: int | None = None
    metric: str | None = None
    value: float | None = None
    threshold: float | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DiagnosticReport:
    events: list[DiagnosticEvent] = field(default_factory=list)
    convergence: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    @property
    def status(self) -> str:
        if not self.enabled:
            return "disabled"
        if any(event.severity == "error" for event in self.events):
            return "error"
        if any(event.severity == "warning" for event in self.events):
            return "warning"
        return "pass"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "enabled": self.enabled,
            "event_counts": {
                "warning": sum(event.severity == "warning" for event in self.events),
                "error": sum(event.severity == "error" for event in self.events),
            },
            "events": [event.as_dict() for event in self.events],
            "convergence": dict(self.convergence),
        }


class DiagnosticPolicyError(RuntimeError):
    def __init__(self, report: DiagnosticReport) -> None:
        categories = sorted({event.category for event in report.events if event.severity == "error"})
        super().__init__(f"Forward quality policy failed: {', '.join(categories)}")
        self.report = report


def quality_config(case_cfg: Mapping[str, Any]) -> dict[str, Any]:
    configured = dict(case_cfg.get("diagnostics", {}).get("quality", {}))
    thresholds = dict(DEFAULT_QUALITY_THRESHOLDS)
    thresholds.update(configured.get("thresholds", {}))
    return {
        "enabled": bool(configured.get("enabled", True)),
        "on_error": str(configured.get("on_error", "raise")),
        "thresholds": thresholds,
    }


def convergence_config(case_cfg: Mapping[str, Any]) -> dict[str, Any]:
    configured = dict(case_cfg.get("diagnostics", {}).get("convergence", {}))
    result = dict(DEFAULT_CONVERGENCE)
    result.update(configured)
    return result


def validate_diagnostic_config(case_cfg: Mapping[str, Any]) -> None:
    quality = quality_config(case_cfg)
    if quality["on_error"] not in {"raise", "report"}:
        raise ValueError("diagnostics.quality.on_error must be 'raise' or 'report'.")
    thresholds = quality["thresholds"]
    upper_pairs = (
        ("cr_condition_warn_above", "cr_condition_error_above"),
        ("cr_residual_warn_above", "cr_residual_error_above"),
        ("negative_population_fraction_warn_above", "negative_population_fraction_error_above"),
        ("eedf_upper_decile_warn_above", "eedf_upper_decile_error_above"),
        ("eedf_edge_relative_warn_above", "eedf_edge_relative_error_above"),
    )
    for warn_name, error_name in upper_pairs:
        if float(thresholds[warn_name]) > float(thresholds[error_name]):
            raise ValueError(f"Diagnostic threshold {warn_name} must be <= {error_name}.")
    if float(thresholds["cross_section_coverage_error_below"]) > float(
        thresholds["cross_section_coverage_warn_below"]
    ):
        raise ValueError(
            "Diagnostic threshold cross_section_coverage_error_below must be <= "
            "cross_section_coverage_warn_below."
        )
    convergence = convergence_config(case_cfg)
    if int(convergence["energy_grid_factor"]) < 2 or int(convergence["wavelength_grid_factor"]) < 2:
        raise ValueError("Convergence refinement factors must be >= 2.")
    if float(convergence["warn_relative_above"]) > float(convergence["error_relative_above"]):
        raise ValueError("Convergence warn_relative_above must be <= error_relative_above.")


def _upper_event(
    *,
    category: str,
    metric: str,
    value: float,
    warn_threshold: float,
    error_threshold: float,
    zone_index: int | None,
    context: Mapping[str, Any] | None = None,
) -> DiagnosticEvent | None:
    if value > error_threshold:
        severity = "error"
        threshold = error_threshold
    elif value > warn_threshold:
        severity = "warning"
        threshold = warn_threshold
    else:
        return None
    return DiagnosticEvent(
        category=category,
        severity=severity,
        message=f"{metric}={value:.6g} exceeds {severity} threshold {threshold:.6g}.",
        zone_index=zone_index,
        metric=metric,
        value=value,
        threshold=threshold,
        context=dict(context or {}),
    )


def _lower_event(
    *,
    category: str,
    metric: str,
    value: float,
    warn_threshold: float,
    error_threshold: float,
    zone_index: int | None,
    context: Mapping[str, Any] | None = None,
) -> DiagnosticEvent | None:
    if value < error_threshold:
        severity = "error"
        threshold = error_threshold
    elif value < warn_threshold:
        severity = "warning"
        threshold = warn_threshold
    else:
        return None
    return DiagnosticEvent(
        category=category,
        severity=severity,
        message=f"{metric}={value:.6g} is below {severity} threshold {threshold:.6g}.",
        zone_index=zone_index,
        metric=metric,
        value=value,
        threshold=threshold,
        context=dict(context or {}),
    )


def _cross_section_diagnostics(
    reaction_diagnostics: Iterable[Mapping[str, Any]],
    band_diagnostics: Iterable[Mapping[str, Any]],
) -> Iterable[tuple[str, Mapping[str, Any]]]:
    for diagnostic in [*reaction_diagnostics, *band_diagnostics]:
        coverage = diagnostic.get("cross_section")
        if isinstance(coverage, Mapping):
            yield str(diagnostic.get("id", "<unknown>")), coverage


def evaluate_zone_quality(
    *,
    zone_index: int,
    cr: CRDiagnostics,
    eedf: EEDFDiagnostics,
    reaction_diagnostics: Iterable[Mapping[str, Any]],
    band_diagnostics: Iterable[Mapping[str, Any]],
    thresholds: Mapping[str, float],
) -> list[DiagnosticEvent]:
    events: list[DiagnosticEvent] = []
    if cr.system_size > 0 and cr.matrix_rank < cr.system_size:
        events.append(
            DiagnosticEvent(
                category="cr.singular_matrix",
                severity="error",
                message=f"CR matrix rank {cr.matrix_rank} is below system size {cr.system_size}.",
                zone_index=zone_index,
                metric="matrix_rank",
                value=float(cr.matrix_rank),
                threshold=float(cr.system_size),
            )
        )
    upper_metrics = (
        (
            "cr.condition_number",
            "condition_number",
            cr.condition_number,
            "cr_condition_warn_above",
            "cr_condition_error_above",
        ),
        (
            "cr.relative_residual",
            "relative_residual",
            cr.relative_residual,
            "cr_residual_warn_above",
            "cr_residual_error_above",
        ),
        (
            "cr.negative_population",
            "negative_population_fraction",
            cr.negative_population_fraction,
            "negative_population_fraction_warn_above",
            "negative_population_fraction_error_above",
        ),
        (
            "eedf.upper_decile_mass",
            "upper_decile_probability",
            eedf.upper_decile_probability,
            "eedf_upper_decile_warn_above",
            "eedf_upper_decile_error_above",
        ),
        (
            "eedf.upper_edge_pdf",
            "upper_edge_relative_pdf",
            eedf.upper_edge_relative_pdf,
            "eedf_edge_relative_warn_above",
            "eedf_edge_relative_error_above",
        ),
    )
    for category, metric, value, warn_name, error_name in upper_metrics:
        if cr.system_size == 0 and category.startswith("cr."):
            continue
        event = _upper_event(
            category=category,
            metric=metric,
            value=float(value),
            warn_threshold=float(thresholds[warn_name]),
            error_threshold=float(thresholds[error_name]),
            zone_index=zone_index,
        )
        if event is not None:
            events.append(event)
    for process_id, coverage in _cross_section_diagnostics(reaction_diagnostics, band_diagnostics):
        value = float(coverage["covered_probability"])
        event = _lower_event(
            category="cross_section.eedf_coverage",
            metric="covered_probability",
            value=value,
            warn_threshold=float(thresholds["cross_section_coverage_warn_below"]),
            error_threshold=float(thresholds["cross_section_coverage_error_below"]),
            zone_index=zone_index,
            context={"process_id": process_id, "path": coverage.get("path")},
        )
        if event is not None:
            events.append(event)
    return events


def convergence_event(
    category: str,
    value: float,
    config: Mapping[str, Any],
) -> DiagnosticEvent | None:
    return _upper_event(
        category=category,
        metric="maximum_relative_l2_difference",
        value=value,
        warn_threshold=float(config["warn_relative_above"]),
        error_threshold=float(config["error_relative_above"]),
        zone_index=None,
    )


def enforce_quality_policy(case_cfg: Mapping[str, Any], report: DiagnosticReport) -> None:
    config = quality_config(case_cfg)
    convergence_enabled = bool(convergence_config(case_cfg)["enabled"])
    if (
        (config["enabled"] or convergence_enabled)
        and config["on_error"] == "raise"
        and report.status == "error"
    ):
        raise DiagnosticPolicyError(report)
