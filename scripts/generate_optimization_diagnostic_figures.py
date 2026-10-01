"""Render optimization diagnostics from actual OESCR objective evaluations."""

from __future__ import annotations

import csv
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oescr.inverse.gain_model import apply_gain_offset_tilt  # noqa: E402
from oescr.inverse.objectives import residual_vector  # noqa: E402
from oescr.inverse.optimize import InverseSolver  # noqa: E402
from oescr.inverse.window_metrics import fit_local_baseline  # noqa: E402
from oescr.io.pathmap import get_path  # noqa: E402
from oescr.io.yaml_loader import load_yaml  # noqa: E402
from oescr.physics.eedf import (  # noqa: E402
    build_eedf_for_zone,
    build_energy_grid,
    summarize_eedf,
)

OUTPUT_DIR = ROOT / "docs" / "optimization-figures"
TRACE_DIR = ROOT / ".local_outputs" / "optimization_diagnostics"

BLUE = "#2563eb"
ORANGE = "#d97706"
BLACK = "#111827"
GREY = "#667085"
LIGHT_GREY = "#d7dce3"
PURPLE = "#7c3aed"


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.2,
            "axes.titlesize": 10.5,
            "axes.labelsize": 9.2,
            "axes.edgecolor": BLACK,
            "axes.labelcolor": BLACK,
            "xtick.color": BLACK,
            "ytick.color": BLACK,
            "text.color": BLACK,
            "grid.color": LIGHT_GREY,
            "grid.linewidth": 0.65,
            "legend.frameon": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def _panel_label(ax: plt.Axes, label: str) -> None:
    ax.text(
        -0.13,
        1.06,
        label,
        transform=ax.transAxes,
        fontsize=11.5,
        fontweight="bold",
        va="bottom",
    )


def _load_traced_case(
    benchmark_id: str,
    trace_name: str,
) -> tuple[InverseSolver, dict[str, Any], dict[str, Any], dict[str, Any]]:
    base = ROOT / "examples" / "benchmarks" / benchmark_id
    solver = InverseSolver.from_yaml(base / "case_init.yaml", base / "inverse.yaml")
    truth = load_yaml(base / "case_truth.yaml")
    summary_path = TRACE_DIR / trace_name / "fit_summary.yaml"
    if not summary_path.exists():
        raise FileNotFoundError(
            f"Missing optimization trace: {summary_path}. Run scripts/run_inverse.py with --record-trace first."
        )
    summary = load_yaml(summary_path)
    if not summary.get("optimization_trace"):
        raise ValueError(f"Optimization trace is empty: {summary_path}")
    optimized = deepcopy(solver.case_cfg)
    solver.params.apply_to_case(optimized, np.asarray(summary["x_opt"], dtype=float))
    return solver, truth, optimized, summary


def _fit_space_arrays(
    solver: InverseSolver,
    truth: dict[str, Any],
    optimized: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    initial_values: list[float] = []
    optimized_values: list[float] = []
    truth_values: list[float] = []
    for parameter in solver.params.params:
        initial_values.append(float(get_path(solver.case_cfg, parameter.path)))
        optimized_values.append(float(get_path(optimized, parameter.path)))
        truth_values.append(float(get_path(truth, parameter.path)))
    return (
        np.asarray(initial_values, dtype=float),
        np.asarray(optimized_values, dtype=float),
        np.asarray(truth_values, dtype=float),
    )


def _parameter_symbol(name: str) -> str:
    if name.startswith("te"):
        return f"Tₑ[{name[2:]}]"
    if name.startswith("N2e"):
        return f"N₂ emit[{name[3:]}]"
    if name.startswith("Cl2e"):
        return f"Cl₂ emit[{name[4:]}]"
    if name.startswith("Cl"):
        return f"Cl[{name[2:]}]"
    if name.startswith("F"):
        return f"F[{name[1:]}]"
    return name


def _format_truth(name: str, value: float) -> str:
    if name.startswith("te"):
        return f"{value:.3g} eV"
    return f"{value:.2e} m⁻³"


def _plot_parameter_recovery(
    ax: plt.Axes,
    solver: InverseSolver,
    truth: dict[str, Any],
    optimized: dict[str, Any],
) -> list[dict[str, Any]]:
    initial, optimum, target = _fit_space_arrays(solver, truth, optimized)
    y = np.arange(len(target), dtype=float)
    initial_ratio = initial / target
    optimum_ratio = optimum / target
    ax.axvline(1.0, color=BLACK, linestyle=":", linewidth=1.4, label="Known truth")
    ax.hlines(y, initial_ratio, optimum_ratio, color=GREY, linewidth=1.0, alpha=0.7)
    ax.scatter(initial_ratio, y, color=ORANGE, marker="s", s=30, label="Initial / truth", zorder=3)
    ax.scatter(optimum_ratio, y, color=BLUE, marker="o", s=30, label="Optimized / truth", zorder=3)
    labels = [
        f"{_parameter_symbol(parameter.name)}\n{_format_truth(parameter.name, value)}"
        for parameter, value in zip(solver.params.params, target, strict=True)
    ]
    ax.set_yticks(y, labels, fontsize=7.2)
    ax.invert_yaxis()
    ax.set_xlabel("Value / known truth")
    ax.set_title("Unknown parameters and recovery (tick text gives the truth)", loc="left", fontweight="bold")
    ax.grid(axis="x")
    ax.legend(loc="best", fontsize=7.8)

    rows: list[dict[str, Any]] = []
    for parameter, initial_value, optimum_value, target_value in zip(
        solver.params.params,
        initial,
        optimum,
        target,
        strict=True,
    ):
        rows.append(
            {
                "parameter": parameter.name,
                "path": parameter.path,
                "status": "optimized",
                "initial": initial_value,
                "truth": target_value,
                "optimized": optimum_value,
                "relative_error": optimum_value / target_value - 1.0,
            }
        )
    return rows


def _fitted_prediction(
    solver: InverseSolver,
    case: dict[str, Any],
    instrument_id: str,
    chord_index: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    chord_key = f"chord_{chord_index}"
    measurement = solver.measurements[instrument_id][chord_index]
    forward = solver.model.predict(case)
    spectrum = forward.spectra[instrument_id][chord_key]
    prediction = np.interp(
        measurement.wavelength_nm,
        spectrum["wavelength_nm"],
        spectrum["intensity"],
        left=0.0,
        right=0.0,
    )
    _, aux = residual_vector(
        solver.model,
        case,
        solver.inv_cfg,
        solver.measurements,
        solver.windows,
    )
    gain_info = aux.get("gain_offset", {}).get(
        (instrument_id, chord_key),
        {"gain": 1.0, "tilt": 0.0, "offset": 0.0},
    )
    fitted = apply_gain_offset_tilt(
        np.asarray(measurement.wavelength_nm, dtype=float),
        prediction,
        float(gain_info.get("gain", 1.0)),
        float(gain_info.get("tilt", 0.0)),
        float(gain_info.get("offset", 0.0)),
    )
    return (
        np.asarray(measurement.wavelength_nm, dtype=float),
        np.asarray(measurement.intensity, dtype=float),
        fitted,
    )


def _plot_spectrum_window(
    ax: plt.Axes,
    wavelength: np.ndarray,
    measurement: np.ndarray,
    initial: np.ndarray,
    optimized: np.ndarray,
    limits: tuple[float, float],
    title: str,
    *,
    baseline_correct: bool,
    show_legend: bool = False,
) -> None:
    mask = (wavelength >= limits[0]) & (wavelength <= limits[1])
    x = wavelength[mask]
    measured = measurement[mask].copy()
    init = initial[mask].copy()
    opt = optimized[mask].copy()
    if baseline_correct:
        measured -= fit_local_baseline(x, measured)
        init -= fit_local_baseline(x, init)
        opt -= fit_local_baseline(x, opt)
    scale = max(float(np.max(np.abs(measured))), 1.0e-30)
    marker_every = max(len(x) // 40, 1)
    ax.plot(x, init / scale, color=ORANGE, linestyle="--", linewidth=1.5, label="Initial")
    ax.plot(x, opt / scale, color=BLUE, linewidth=1.8, label="Optimized")
    ax.plot(
        x[::marker_every],
        measured[::marker_every] / scale,
        color=BLACK,
        linestyle="none",
        marker="o",
        markerfacecolor="white",
        markersize=3.0,
        label="Measurement",
    )
    ax.set_xlim(*limits)
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Intensity / measured peak")
    ax.set_title(title, loc="left", fontweight="bold")
    ax.grid(axis="y")
    if show_legend:
        ax.legend(loc="best", fontsize=7.8)


def _plot_electron_status(
    ax: plt.Axes,
    initial: dict[str, Any],
    optimized: dict[str, Any],
    truth: dict[str, Any],
    optimized_te: bool,
    optimized_ne: bool,
) -> list[dict[str, Any]]:
    truth_te = np.asarray(truth["plasma_state"]["te_shells_eV"], dtype=float)
    initial_te = np.asarray(initial["plasma_state"]["te_shells_eV"], dtype=float)
    optimized_te_values = np.asarray(optimized["plasma_state"]["te_shells_eV"], dtype=float)
    truth_ne = np.asarray(truth["plasma_state"]["ne_shells_m3"], dtype=float)
    initial_ne = np.asarray(initial["plasma_state"]["ne_shells_m3"], dtype=float)
    optimized_ne_values = np.asarray(optimized["plasma_state"]["ne_shells_m3"], dtype=float)
    shell = np.arange(len(truth_te))

    ax.axhline(1.0, color=BLACK, linestyle=":", linewidth=1.3, label="Known truth")
    if optimized_te:
        ax.plot(shell, initial_te / truth_te, color=ORANGE, linestyle="--", marker="s", label="Tₑ initial")
        ax.plot(shell, optimized_te_values / truth_te, color=BLUE, marker="o", label="Tₑ optimized")
    else:
        ax.plot(shell, initial_te / truth_te, color=ORANGE, linestyle="--", marker="s", label="Tₑ fixed—not inferred")
    if optimized_ne:
        ax.plot(shell, initial_ne / truth_ne, color=GREY, linestyle="--", marker="x", label="nₑ initial")
        ax.plot(shell, optimized_ne_values / truth_ne, color=PURPLE, marker="D", label="nₑ optimized")
    else:
        ax.plot(shell, initial_ne / truth_ne, color=GREY, linestyle="--", marker="x", label="nₑ fixed—not inferred")
    ax.set_xticks(shell, [f"shell {index}" for index in shell])
    ax.set_ylabel("Value / known truth")
    ax.set_title("Electron quantities: inferred versus fixed inputs", loc="left", fontweight="bold")
    ax.grid(axis="y")
    ax.legend(loc="best", fontsize=7.5)

    rows: list[dict[str, Any]] = []
    for index in shell:
        rows.extend(
            [
                {
                    "parameter": f"te{index}",
                    "path": f"plasma_state.te_shells_eV[{index}]",
                    "status": "optimized" if optimized_te else "fixed_not_inferred",
                    "initial": initial_te[index],
                    "truth": truth_te[index],
                    "optimized": optimized_te_values[index],
                    "relative_error": optimized_te_values[index] / truth_te[index] - 1.0,
                },
                {
                    "parameter": f"ne{index}",
                    "path": f"plasma_state.ne_shells_m3[{index}]",
                    "status": "optimized" if optimized_ne else "fixed_not_inferred",
                    "initial": initial_ne[index],
                    "truth": truth_ne[index],
                    "optimized": optimized_ne_values[index],
                    "relative_error": optimized_ne_values[index] / truth_ne[index] - 1.0,
                },
            ]
        )
    return rows


def _plot_eedf(
    ax: plt.Axes,
    initial: dict[str, Any],
    optimized: dict[str, Any],
    truth: dict[str, Any],
    *,
    optimized_te: bool,
) -> dict[str, float]:
    energy = build_energy_grid(truth)
    initial_pdf = build_eedf_for_zone(initial, 0, energy)
    optimized_pdf = build_eedf_for_zone(optimized, 0, energy)
    truth_pdf = build_eedf_for_zone(truth, 0, energy)
    upper = min(20.0, float(energy[-1]))
    mask = energy <= upper
    truth_mean = summarize_eedf(energy, truth_pdf).mean_energy_eV
    initial_mean = summarize_eedf(energy, initial_pdf).mean_energy_eV
    optimized_mean = summarize_eedf(energy, optimized_pdf).mean_energy_eV
    ax.plot(
        energy[mask],
        truth_pdf[mask],
        color=BLACK,
        linestyle=":",
        linewidth=1.8,
        label=f"Known truth, ⟨E⟩={truth_mean:.2f} eV",
    )
    ax.plot(
        energy[mask],
        initial_pdf[mask],
        color=ORANGE,
        linestyle="--",
        linewidth=1.6,
        label=f"Initial, ⟨E⟩={initial_mean:.2f} eV",
    )
    if optimized_te:
        ax.plot(
            energy[mask],
            optimized_pdf[mask],
            color=BLUE,
            linewidth=1.9,
            label=f"Optimized, ⟨E⟩={optimized_mean:.2f} eV",
        )
        title = "Maxwell EEDF implied by inferred Tₑ (central shell)"
    else:
        title = "Maxwell EEDF implied by fixed Tₑ—not independently inferred"
    ax.set(xlabel="Electron energy (eV)", ylabel="Energy probability density (eV$^{-1}$)")
    ax.set_title(title, loc="left", fontweight="bold")
    ax.grid(True)
    ax.legend(loc="best", fontsize=7.5)
    return {
        "initial_l1": float(np.trapezoid(np.abs(initial_pdf - truth_pdf), energy)),
        "optimized_l1": float(np.trapezoid(np.abs(optimized_pdf - truth_pdf), energy)),
        "truth_mean_eV": truth_mean,
        "optimized_mean_eV": optimized_mean,
    }


def _trace_arrays(summary: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    trace = summary["optimization_trace"]
    evaluations = np.asarray([row["evaluation"] for row in trace], dtype=int)
    losses = np.asarray([row["loss"] for row in trace], dtype=float)
    stages = np.asarray([row["stage"] for row in trace], dtype=object)
    points = np.asarray([row["x"] for row in trace], dtype=float)
    return evaluations, losses, stages, points


def _plot_loss_history(ax: plt.Axes, summary: dict[str, Any]) -> None:
    evaluations, losses, stages, _ = _trace_arrays(summary)
    for stage, color, label in (("global", GREY, "Global evaluations"), ("local", ORANGE, "Local evaluations")):
        mask = stages == stage
        if np.any(mask):
            ax.scatter(evaluations[mask], losses[mask], s=7, color=color, alpha=0.22, label=label)
    best_so_far = np.minimum.accumulate(losses)
    ax.plot(evaluations, best_so_far, color=BLUE, linewidth=2.0, label="Best so far")
    final_index = int(np.argmin(losses))
    ax.scatter(
        [evaluations[final_index]],
        [losses[final_index]],
        color=BLACK,
        marker="*",
        s=90,
        label=f"Minimum {losses[final_index]:.4g}",
        zorder=4,
    )
    positive = losses[losses > 0.0]
    if len(positive) and float(np.max(positive) / np.min(positive)) > 3.0:
        ax.set_yscale("log")
    local_indices = evaluations[stages == "local"]
    if len(local_indices):
        ax.axvline(local_indices[0], color=BLACK, linestyle=":", linewidth=1.0)
    ax.set(xlabel="Objective evaluation", ylabel="Configured objective Loss")
    ax.set_title("Actual optimization history", loc="left", fontweight="bold")
    ax.grid(axis="y")
    ax.legend(loc="best", fontsize=7.5)


def _plot_parallel_coordinates(
    ax: plt.Axes,
    solver: InverseSolver,
    truth: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    _, losses, _, points = _trace_arrays(summary)
    lower, upper = solver.params.bounds()
    normalized = (points - lower) / np.maximum(upper - lower, 1.0e-30)
    threshold = float(np.quantile(losses, 0.10))
    low_mask = losses <= threshold
    high_indices = np.flatnonzero(~low_mask)
    if len(high_indices) > 300:
        high_indices = high_indices[np.linspace(0, len(high_indices) - 1, 300, dtype=int)]
    x = np.arange(points.shape[1], dtype=float)
    for index in high_indices:
        ax.plot(x, normalized[index], color=LIGHT_GREY, linewidth=0.55, alpha=0.18)
    for index in np.flatnonzero(low_mask):
        ax.plot(x, normalized[index], color=BLUE, linewidth=0.8, alpha=0.18)

    initial_x = solver.params.initial_vector(solver.case_cfg)
    truth_x = np.asarray(
        [parameter.to_opt(float(get_path(truth, parameter.path))) for parameter in solver.params.params],
        dtype=float,
    )
    initial_norm = (initial_x - lower) / np.maximum(upper - lower, 1.0e-30)
    truth_norm = (truth_x - lower) / np.maximum(upper - lower, 1.0e-30)
    best_index = int(np.argmin(losses))
    ax.plot(x, initial_norm, color=ORANGE, linestyle="--", linewidth=1.8)
    ax.plot(x, truth_norm, color=BLACK, linestyle=":", linewidth=2.0)
    ax.plot(x, normalized[best_index], color=BLACK, linewidth=2.2)
    ax.set_xticks(x, [_parameter_symbol(parameter.name) for parameter in solver.params.params], fontsize=7.5)
    ax.set_ylim(-0.03, 1.03)
    ax.set_ylabel("Position within configured bounds")
    ax.set_title(
        f"Evaluated parameter paths (blue = lowest 10% Loss ≤ {threshold:.4g})",
        loc="left",
        fontweight="bold",
    )
    ax.grid(axis="x")
    ax.legend(
        handles=[
            Line2D([0], [0], color=LIGHT_GREY, lw=1.2, label="Other evaluated candidates"),
            Line2D([0], [0], color=BLUE, lw=1.4, label="Lowest 10% Loss"),
            Line2D([0], [0], color=ORANGE, lw=1.8, ls="--", label="Initial"),
            Line2D([0], [0], color=BLACK, lw=2.0, ls=":", label="Known truth"),
            Line2D([0], [0], color=BLACK, lw=2.2, label="Best evaluated"),
        ],
        loc="best",
        fontsize=7.2,
    )


def _render_benchmark_case(
    *,
    benchmark_id: str,
    trace_name: str,
    instrument_id: str,
    title: str,
    windows: list[tuple[tuple[float, float], str, bool]],
    optimized_te: bool,
    optimized_ne: bool,
    output_name: str,
) -> tuple[Path, list[dict[str, Any]], dict[str, float]]:
    solver, truth, optimized, summary = _load_traced_case(benchmark_id, trace_name)
    wavelength, measurement, initial_prediction = _fitted_prediction(solver, solver.case_cfg, instrument_id, 2)
    _, _, optimized_prediction = _fitted_prediction(solver, optimized, instrument_id, 2)

    fig = plt.figure(figsize=(15.0, 11.0), constrained_layout=True)
    grid = fig.add_gridspec(3, 2, height_ratios=[1.15, 1.0, 1.05])
    fig.suptitle(title, fontsize=16, fontweight="bold")

    spectrum_grid = grid[0, 0].subgridspec(1, len(windows), wspace=0.10)
    spectrum_axes: list[plt.Axes] = []
    for index, (limits, window_title, baseline_correct) in enumerate(windows):
        ax = fig.add_subplot(spectrum_grid[0, index])
        _plot_spectrum_window(
            ax,
            wavelength,
            measurement,
            initial_prediction,
            optimized_prediction,
            limits,
            window_title,
            baseline_correct=baseline_correct,
            show_legend=index == 0,
        )
        if index > 0:
            ax.set_ylabel("")
        spectrum_axes.append(ax)
    _panel_label(spectrum_axes[0], "A")

    parameter_ax = fig.add_subplot(grid[0, 1])
    parameter_rows = _plot_parameter_recovery(parameter_ax, solver, truth, optimized)
    _panel_label(parameter_ax, "B")

    electron_ax = fig.add_subplot(grid[1, 0])
    electron_rows = _plot_electron_status(
        electron_ax,
        solver.case_cfg,
        optimized,
        truth,
        optimized_te,
        optimized_ne,
    )
    _panel_label(electron_ax, "C")

    eedf_ax = fig.add_subplot(grid[1, 1])
    eedf_summary = _plot_eedf(
        eedf_ax,
        solver.case_cfg,
        optimized,
        truth,
        optimized_te=optimized_te,
    )
    _panel_label(eedf_ax, "D")

    loss_ax = fig.add_subplot(grid[2, 0])
    _plot_loss_history(loss_ax, summary)
    _panel_label(loss_ax, "E")

    parallel_ax = fig.add_subplot(grid[2, 1])
    _plot_parallel_coordinates(parallel_ax, solver, truth, summary)
    _panel_label(parallel_ax, "F")

    path = OUTPUT_DIR / output_name
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    optimized_paths = {str(row["path"]) for row in parameter_rows}
    fixed_rows = [row for row in electron_rows if str(row["path"]) not in optimized_paths]
    return path, parameter_rows + fixed_rows, eedf_summary


def _predict_two_band(
    solver: InverseSolver,
    case: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    result = solver.model.predict(case)
    spectrum = result.spectra["two_band_radiance"]["chord_0"]
    return (
        np.asarray(spectrum["wavelength_nm"], dtype=float),
        np.asarray(spectrum["intensity"], dtype=float),
    )


def _plot_two_band_loss(
    ax: plt.Axes,
    ratio_summary: dict[str, Any],
    absolute_summary: dict[str, Any],
) -> None:
    for summary, color, label in (
        (ratio_summary, BLUE, "Ratio / actinometry"),
        (absolute_summary, PURPLE, "Calibrated absolute"),
    ):
        evaluations, losses, _, _ = _trace_arrays(summary)
        scale = max(float(losses[0]), 1.0e-30)
        ax.plot(evaluations, np.minimum.accumulate(losses) / scale, color=color, linewidth=2.0, label=label)
    ax.set_yscale("log")
    ax.set(xlabel="Objective evaluation", ylabel="Best Loss / first evaluated Loss")
    ax.set_title("Actual local-optimization histories", loc="left", fontweight="bold")
    ax.grid(axis="y")
    ax.legend(loc="best", fontsize=7.8)


def _plot_two_band_landscape(
    ax: plt.Axes,
    ratio_solver: InverseSolver,
    ratio_summary: dict[str, Any],
    absolute_solver: InverseSolver,
    absolute_summary: dict[str, Any],
) -> None:
    for solver, summary, color, marker, label in (
        (ratio_solver, ratio_summary, BLUE, "o", "Target density ratio mode"),
        (absolute_solver, absolute_summary, PURPLE, "s", "Electron density absolute mode"),
    ):
        _, losses, _, points = _trace_arrays(summary)
        parameter = solver.params.params[0]
        physical = np.asarray([parameter.from_opt(value) for value in points[:, 0]], dtype=float)
        truth = float(
            get_path(load_yaml(ROOT / "examples" / "use_cases" / "two_band" / "case_truth.yaml"), parameter.path)
        )
        normalized_x = physical / truth
        normalized_loss = losses / max(float(losses[0]), 1.0e-30)
        threshold = float(np.quantile(losses, 0.10))
        low = losses <= threshold
        ax.scatter(normalized_x[~low], normalized_loss[~low], color=LIGHT_GREY, s=14, alpha=0.45)
        ax.scatter(
            normalized_x[low],
            normalized_loss[low],
            color=color,
            marker=marker,
            s=26,
            alpha=0.75,
            label=label,
        )
    ax.axvline(1.0, color=BLACK, linestyle=":", linewidth=1.5, label="Known truth")
    ax.set_yscale("log")
    ax.set(xlabel="Evaluated parameter / known truth", ylabel="Loss / first evaluated Loss")
    ax.set_title("One-dimensional evaluated landscapes (colored = lowest 10%)", loc="left", fontweight="bold")
    ax.grid(True)
    ax.legend(loc="best", fontsize=7.4)


def render_two_band_case() -> tuple[Path, list[dict[str, Any]], dict[str, float]]:
    base = ROOT / "examples" / "use_cases" / "two_band"
    ratio_solver = InverseSolver.from_yaml(base / "case_ratio_init.yaml", base / "inverse_ratio.yaml")
    ratio_fit = ratio_solver.fit(record_trace=True)
    act_solver = InverseSolver.from_yaml(base / "case_ratio_init.yaml", base / "inverse_actinometry.yaml")
    act_fit = act_solver.fit(record_trace=True)
    absolute_solver = InverseSolver.from_yaml(base / "case_absolute_init.yaml", base / "inverse_absolute.yaml")
    absolute_fit = absolute_solver.fit(record_trace=True)
    if not np.allclose(ratio_fit.x_opt, act_fit.x_opt, rtol=1.0e-12, atol=0.0):
        raise RuntimeError("Ratio and actinometry numerical paths diverged")
    ratio_summary = {
        "optimization_trace": ratio_fit.optimization_trace,
        "x_opt": ratio_fit.x_opt.tolist(),
        "cost": ratio_fit.cost,
    }
    absolute_summary = {
        "optimization_trace": absolute_fit.optimization_trace,
        "x_opt": absolute_fit.x_opt.tolist(),
        "cost": absolute_fit.cost,
    }
    truth = load_yaml(base / "case_truth.yaml")
    measurement = ratio_solver.measurements["two_band_radiance"][0]
    wavelength = np.asarray(measurement.wavelength_nm, dtype=float)
    measured = np.asarray(measurement.intensity, dtype=float)
    _, ratio_initial = _predict_two_band(ratio_solver, ratio_solver.case_cfg)
    _, absolute_initial = _predict_two_band(absolute_solver, absolute_solver.case_cfg)
    _, optimized = _predict_two_band(ratio_solver, ratio_fit.case_opt)

    fig = plt.figure(figsize=(15.0, 11.0), constrained_layout=True)
    grid = fig.add_gridspec(3, 2, height_ratios=[1.15, 1.0, 1.05])
    fig.suptitle(
        "Two-band inverse cases: problem definition, recovery, and actual optimization paths",
        fontsize=16,
        fontweight="bold",
    )

    spectrum_ax = fig.add_subplot(grid[0, 0])
    spectrum_ax.plot(wavelength, ratio_initial, color=ORANGE, linestyle="--", label="Ratio initial")
    spectrum_ax.plot(wavelength, absolute_initial, color=PURPLE, linestyle="-.", label="Absolute initial")
    spectrum_ax.plot(wavelength, optimized, color=BLUE, linewidth=2.0, label="Optimized")
    spectrum_ax.plot(
        wavelength,
        measured,
        color=BLACK,
        linestyle="none",
        marker="o",
        markerfacecolor="white",
        markersize=3.2,
        label="Measurement",
    )
    spectrum_ax.set(xlabel="Wavelength (nm)", ylabel="Spectral radiance (W m$^{-2}$ sr$^{-1}$ nm$^{-1}$)")
    spectrum_ax.set_title("Optimization data: target and actinometer bands", loc="left", fontweight="bold")
    spectrum_ax.grid(axis="y")
    spectrum_ax.legend(loc="best", fontsize=7.7)
    _panel_label(spectrum_ax, "A")

    parameter_ax = fig.add_subplot(grid[0, 1])
    target_truth = float(truth["plasma_state"]["radicals"]["Target"][0])
    ne_truth = float(truth["plasma_state"]["ne_shells_m3"][0])
    initial_ratio = np.asarray(
        [
            ratio_solver.case_cfg["plasma_state"]["radicals"]["Target"][0] / target_truth,
            absolute_solver.case_cfg["plasma_state"]["ne_shells_m3"][0] / ne_truth,
        ],
        dtype=float,
    )
    optimized_ratio = np.asarray(
        [
            ratio_fit.case_opt["plasma_state"]["radicals"]["Target"][0] / target_truth,
            absolute_fit.case_opt["plasma_state"]["ne_shells_m3"][0] / ne_truth,
        ],
        dtype=float,
    )
    x = np.arange(2)
    parameter_ax.axhline(1.0, color=BLACK, linestyle=":", label="Known truth")
    parameter_ax.plot(x, initial_ratio, color=ORANGE, linestyle="--", marker="s", label="Initial / truth")
    parameter_ax.plot(x, optimized_ratio, color=BLUE, marker="o", label="Optimized / truth")
    parameter_ax.set_xticks(
        x,
        ["Target density\ntruth 2.0e18 m⁻³", "Electron density\ntruth 3.0e16 m⁻³"],
    )
    parameter_ax.set_ylabel("Value / known truth")
    parameter_ax.set_title("Unknown parameters and exact targets", loc="left", fontweight="bold")
    parameter_ax.grid(axis="y")
    parameter_ax.legend(loc="best", fontsize=7.8)
    _panel_label(parameter_ax, "B")

    electron_ax = fig.add_subplot(grid[1, 0])
    electron_ax.axhline(1.0, color=BLACK, linestyle=":", label="Known truth")
    electron_ax.scatter([0], [1.0], color=GREY, marker="x", s=70, label="Tₑ fixed—not inferred")
    electron_ax.plot([1, 2], [0.5, 1.0], color=PURPLE, marker="D", label="nₑ absolute-mode recovery")
    electron_ax.set_xticks([0, 1, 2], ["Tₑ fixed", "nₑ initial", "nₑ optimized"])
    electron_ax.set_ylabel("Value / known truth")
    electron_ax.set_title("Electron quantities and inference status", loc="left", fontweight="bold")
    electron_ax.grid(axis="y")
    electron_ax.legend(loc="best", fontsize=7.8)
    _panel_label(electron_ax, "C")

    eedf_ax = fig.add_subplot(grid[1, 1])
    energy = build_energy_grid(truth)
    truth_pdf = build_eedf_for_zone(truth, 0, energy)
    mask = energy <= 20.0
    mean_energy = summarize_eedf(energy, truth_pdf).mean_energy_eV
    eedf_ax.plot(energy[mask], truth_pdf[mask], color=BLACK, linewidth=2.0)
    eedf_ax.set(xlabel="Electron energy (eV)", ylabel="Energy probability density (eV$^{-1}$)")
    eedf_ax.set_title(
        f"Fixed Maxwell EEDF, ⟨E⟩={mean_energy:.2f} eV—not inferred",
        loc="left",
        fontweight="bold",
    )
    eedf_ax.grid(True)
    _panel_label(eedf_ax, "D")

    loss_ax = fig.add_subplot(grid[2, 0])
    _plot_two_band_loss(loss_ax, ratio_summary, absolute_summary)
    _panel_label(loss_ax, "E")

    landscape_ax = fig.add_subplot(grid[2, 1])
    _plot_two_band_landscape(
        landscape_ax,
        ratio_solver,
        ratio_summary,
        absolute_solver,
        absolute_summary,
    )
    _panel_label(landscape_ax, "F")

    path = OUTPUT_DIR / "01_two_band_optimization_diagnostics.png"
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    rows = [
        {
            "parameter": "target_density_m3",
            "path": "plasma_state.radicals.Target[0]",
            "status": "optimized_ratio_and_actinometry",
            "initial": target_truth * initial_ratio[0],
            "truth": target_truth,
            "optimized": target_truth * optimized_ratio[0],
            "relative_error": optimized_ratio[0] - 1.0,
        },
        {
            "parameter": "electron_density_m3",
            "path": "plasma_state.ne_shells_m3[0]",
            "status": "optimized_calibrated_absolute",
            "initial": ne_truth * initial_ratio[1],
            "truth": ne_truth,
            "optimized": ne_truth * optimized_ratio[1],
            "relative_error": optimized_ratio[1] - 1.0,
        },
        {
            "parameter": "electron_temperature_eV",
            "path": "plasma_state.te_shells_eV[0]",
            "status": "fixed_not_inferred",
            "initial": truth["plasma_state"]["te_shells_eV"][0],
            "truth": truth["plasma_state"]["te_shells_eV"][0],
            "optimized": truth["plasma_state"]["te_shells_eV"][0],
            "relative_error": 0.0,
        },
    ]
    return (
        path,
        rows,
        {"initial_l1": 0.0, "optimized_l1": 0.0, "truth_mean_eV": mean_energy, "optimized_mean_eV": mean_energy},
    )


def _write_parameter_csv(case_rows: dict[str, list[dict[str, Any]]]) -> Path:
    path = OUTPUT_DIR / "parameter_recovery.csv"
    fieldnames = [
        "case",
        "parameter",
        "path",
        "status",
        "initial",
        "truth",
        "optimized",
        "relative_error",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for case_name, rows in case_rows.items():
            for row in rows:
                writer.writerow({"case": case_name, **row})
    return path


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _style()
    two_band_path, two_band_rows, two_band_eedf = render_two_band_case()
    nf3_path, nf3_rows, nf3_eedf = _render_benchmark_case(
        benchmark_id="nf3_ar_ccp_clean_2023",
        trace_name="nf3",
        instrument_id="nf3_benchmark_uvvis",
        title="NF₃/Ar: optimization problem, inferred Tₑ, implied EEDF, and search path",
        windows=[((680.0, 718.0), "Central chord: F I 685.6 / 703.7 / 712.8 nm", False)],
        optimized_te=True,
        optimized_ne=False,
        output_name="02_nf3_optimization_diagnostics.png",
    )
    cl2_path, cl2_rows, cl2_eedf = _render_benchmark_case(
        benchmark_id="cl2_ar_icp_fuller2001",
        trace_name="cl2",
        instrument_id="cl2_benchmark_scan",
        title="Cl₂/Ar: optimization problem, fixed electron state, and search path",
        windows=[
            ((478.0, 484.5), "Ar II / Cl II", True),
            ((818.0, 832.0), "Cl I / Xe I", True),
        ],
        optimized_te=False,
        optimized_ne=False,
        output_name="03_cl2_optimization_diagnostics.png",
    )
    csv_path = _write_parameter_csv(
        {
            "two_band": two_band_rows,
            "nf3_ar": nf3_rows,
            "cl2_ar": cl2_rows,
        }
    )
    for path in [two_band_path, nf3_path, cl2_path, csv_path]:
        print(path)
    print("EEDF summaries:")
    print({"two_band": two_band_eedf, "nf3_ar": nf3_eedf, "cl2_ar": cl2_eedf})


if __name__ == "__main__":
    main()
