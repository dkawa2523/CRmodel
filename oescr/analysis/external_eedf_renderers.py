"""Paper-oriented figures for external EEDF and rate comparisons."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402


def _mixture_key(mixture: Mapping[str, Any]) -> tuple[tuple[str, float], ...]:
    return tuple(sorted((str(species), float(fraction)) for species, fraction in mixture.items()))


def _mixture_label(key: tuple[tuple[str, float], ...]) -> str:
    return " / ".join(f"{species} {100.0 * fraction:g}%" for species, fraction in key)


def _mixture_slug(key: tuple[tuple[str, float], ...]) -> str:
    raw = "_".join(f"{species}_{100.0 * fraction:g}pct" for species, fraction in key)
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("_").lower()


def _condition_groups(report: Mapping[str, Any]) -> dict[tuple[tuple[str, float], ...], list[dict[str, Any]]]:
    groups: dict[tuple[tuple[str, float], ...], list[dict[str, Any]]] = defaultdict(list)
    for condition in report["conditions"]:
        groups[_mixture_key(condition["gas_mixture"])].append(condition)
    for conditions in groups.values():
        conditions.sort(key=lambda item: float(item["reduced_field_Td"]))
    return dict(groups)


def _positive(values: np.ndarray) -> np.ndarray:
    return np.where(values > 0.0, values, np.nan)


def _write_eedf_figure(
    report: Mapping[str, Any],
    conditions: list[dict[str, Any]],
    mixture: tuple[tuple[str, float], ...],
    output: Path,
) -> None:
    curves = {curve["condition_id"]: curve for curve in report["eedf_curves"]}
    columns = min(3, len(conditions))
    rows = math.ceil(len(conditions) / columns)
    figure, axes = plt.subplots(
        rows,
        columns,
        figsize=(4.2 * columns, 3.2 * rows),
        squeeze=False,
        layout="constrained",
    )
    for axis, condition in zip(axes.flat, conditions, strict=False):
        curve = curves[condition["condition_id"]]
        external_energy = np.asarray(curve["external_energy_eV"], dtype=float)
        external_pdf = np.asarray(curve["external_energy_pdf_eV_inv"], dtype=float)
        oescr_energy = np.asarray(curve["oescr_energy_eV"], dtype=float)
        oescr_pdf = np.asarray(curve["oescr_energy_pdf_eV_inv"], dtype=float)
        axis.semilogy(external_energy, _positive(external_pdf), color="black", lw=1.8, label="External")
        axis.semilogy(oescr_energy, _positive(oescr_pdf), color="#c43c35", lw=1.4, ls="--", label="OESCR import")
        axis.set_title(f"E/N = {condition['reduced_field_Td']:g} Td")
        axis.set_xlabel("Electron energy (eV)")
        axis.set_ylabel(r"Energy PDF (eV$^{-1}$)")
        axis.grid(alpha=0.2)
    for axis in axes.flat[len(conditions) :]:
        axis.set_visible(False)
    axes.flat[0].legend(frameon=False)
    figure.suptitle(f"Tabulated EEDF import — {_mixture_label(mixture)}")
    figure.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(figure)


def _write_summary_figure(
    report: Mapping[str, Any],
    conditions: list[dict[str, Any]],
    mixture: tuple[tuple[str, float], ...],
    output: Path,
) -> None:
    condition_ids = {condition["condition_id"] for condition in conditions}
    rates = [row for row in report["rates"] if row["condition_id"] in condition_ids]
    fields = np.asarray([condition["reduced_field_Td"] for condition in conditions], dtype=float)

    figure, (mean_axis, rate_axis) = plt.subplots(1, 2, figsize=(11.5, 4.2), layout="constrained")
    _plot_mean_energy(mean_axis, fields, conditions)
    _plot_rate_ratios(rate_axis, fields, conditions, rates, report["acceptance"])
    figure.suptitle(f"Mean energy and rate agreement — {_mixture_label(mixture)}")
    figure.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(figure)


def _plot_mean_energy(axis: Any, fields: np.ndarray, conditions: list[dict[str, Any]]) -> None:
    axis.plot(
        fields,
        [condition["source_mean_energy_eV"] for condition in conditions],
        "o-",
        color="black",
        label="External",
    )
    axis.plot(
        fields,
        [condition["imported_mean_energy_eV"] for condition in conditions],
        "s--",
        color="#c43c35",
        label="OESCR import",
    )
    axis.set_xlabel("E/N (Td)")
    axis.set_ylabel("Mean electron energy (eV)")
    axis.grid(alpha=0.2)
    axis.legend(frameon=False)


def _plot_rate_ratios(
    axis: Any,
    fields: np.ndarray,
    conditions: list[dict[str, Any]],
    rates: list[dict[str, Any]],
    acceptance: Mapping[str, Any],
) -> None:
    tolerance = float(acceptance["rate_relative_error_max"])
    axis.axhspan(1.0 - tolerance, 1.0 + tolerance, color="#d9ead3", alpha=0.8, label="Acceptance")
    axis.axhline(1.0, color="black", lw=1.0)
    process_ids = sorted({row["process_id"] for row in rates})
    finite_ratios: list[float] = []
    for process_id in process_ids:
        process_rows = {row["condition_id"]: row for row in rates if row["process_id"] == process_id}
        ratios = []
        for condition in conditions:
            row = process_rows[condition["condition_id"]]
            external = float(row["external_rate_coefficient_m3_s"])
            ratios.append(np.nan if row["relative_error"] is None else float(row["oescr_rate_coefficient_m3_s"]) / external)
        finite_ratios.extend(value for value in ratios if np.isfinite(value))
        axis.plot(fields, ratios, "o-", label=process_id)
    largest_deviation = max((abs(value - 1.0) for value in finite_ratios), default=0.0)
    half_range = max(0.02, 1.1 * tolerance, 1.1 * largest_deviation)
    axis.set_ylim(1.0 - half_range, 1.0 + half_range)
    axis.ticklabel_format(axis="y", style="plain", useOffset=False)
    axis.set_xlabel("E/N (Td)")
    axis.set_ylabel("OESCR / external rate coefficient")
    axis.grid(alpha=0.2)
    axis.legend(frameon=False, fontsize=8)


def write_external_eedf_figures(report: Mapping[str, Any], output_dir: str | Path) -> list[Path]:
    """Write EEDF overlays and physical summary figures, grouped by gas mixture."""

    if "eedf_curves" not in report:
        raise ValueError("Report must be evaluated with include_curves=True.")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for mixture, conditions in _condition_groups(report).items():
        slug = _mixture_slug(mixture)
        eedf_path = destination / f"{report['benchmark_id']}_{slug}_eedf.png"
        summary_path = destination / f"{report['benchmark_id']}_{slug}_summary.png"
        _write_eedf_figure(report, conditions, mixture, eedf_path)
        _write_summary_figure(report, conditions, mixture, summary_path)
        outputs.extend((eedf_path, summary_path))
    return outputs
