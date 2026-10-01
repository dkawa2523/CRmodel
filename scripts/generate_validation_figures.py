"""Generate paper-style figures from OESCR benchmark artifacts.

The figures emphasize observable agreement and parameter recovery. They do
not promote generated self-consistency fixtures to external validation.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oescr.forward.model import OESCRModel  # noqa: E402
from oescr.inverse.optimize import InverseSolver  # noqa: E402
from oescr.inverse.window_metrics import fit_local_baseline  # noqa: E402
from oescr.io.yaml_loader import load_yaml  # noqa: E402

OUTPUT_DIR = ROOT / "docs" / "validation-figures"

BLUE = "#2563eb"
ORANGE = "#d97706"
BLACK = "#111827"
GREY = "#667085"
LIGHT_GREY = "#d7dce3"
PALE_BLUE = "#dbeafe"


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.5,
            "axes.titlesize": 11,
            "axes.labelsize": 9.5,
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


def _cumulative_integral(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    increments = 0.5 * (y[:-1] + y[1:]) * np.diff(x)
    return np.concatenate(([0.0], np.cumsum(increments)))


def _read_numeric_csv(path: Path) -> dict[str, np.ndarray]:
    with path.open("r", encoding="utf-8") as stream:
        rows = list(csv.DictReader(line for line in stream if not line.startswith("#")))
    if not rows:
        raise ValueError(f"No data rows found in {path}")
    return {key: np.asarray([float(row[key]) for row in rows], dtype=float) for key in rows[0]}


def _instrument_spectrum(
    result: Any,
    instrument_id: str,
    chord_key: str = "chord_0",
) -> tuple[np.ndarray, np.ndarray]:
    spectrum = result.spectra[instrument_id][chord_key]
    return (
        np.asarray(spectrum["wavelength_nm"], dtype=float),
        np.asarray(spectrum["intensity"], dtype=float),
    )


def _plot_observation_and_predictions(
    ax: plt.Axes,
    wavelength: np.ndarray,
    measurement: np.ndarray,
    initial: np.ndarray,
    optimized: np.ndarray,
    *,
    marker_every: int = 1,
) -> None:
    ax.plot(wavelength, initial, color=ORANGE, linestyle="--", linewidth=1.8, label="Initial")
    ax.plot(wavelength, optimized, color=BLUE, linewidth=2.0, label="Optimized")
    ax.plot(
        wavelength[::marker_every],
        measurement[::marker_every],
        color=BLACK,
        linestyle="none",
        marker="o",
        markerfacecolor="white",
        markeredgewidth=0.8,
        markersize=3.4,
        label="Measurement",
        zorder=3,
    )


def render_analytic_forward() -> Path:
    band_case = ROOT / "examples" / "benchmarks" / "physical_band_analytic" / "case.yaml"
    combined_case = band_case.with_name("combined_case.yaml")
    band_expected = 2.7478614247328814e2
    combined_expected = 3.1295088448346706e2

    band_result = OESCRModel.from_yaml(band_case).predict()
    combined_result = OESCRModel.from_yaml(combined_case).predict()
    band_x, band_y = _instrument_spectrum(band_result, "analytic_radiance")
    combined_x, combined_y = _instrument_spectrum(combined_result, "combined_radiance")
    band_cumulative = _cumulative_integral(band_x, band_y)
    combined_cumulative = _cumulative_integral(combined_x, combined_y)

    fig, axes = plt.subplots(2, 2, figsize=(12.2, 7.2), constrained_layout=True)
    fig.suptitle(
        "Analytic forward benchmarks: spectrum and conserved radiance",
        fontsize=15,
        fontweight="bold",
    )

    ax = axes[0, 0]
    ax.plot(band_x, band_y, color=BLUE, linewidth=2.2)
    ax.fill_between(band_x, band_y, color=PALE_BLUE, alpha=0.7)
    ax.set(
        xlabel="Wavelength (nm)",
        ylabel="Spectral radiance\n(W m$^{-2}$ sr$^{-1}$ nm$^{-1}$)",
    )
    ax.set_title("Single electron-impact photon band", loc="left", fontweight="bold")
    ax.grid(axis="y")
    _panel_label(ax, "A")

    ax = axes[0, 1]
    ax.plot(band_x, band_cumulative, color=BLUE, linewidth=2.2, label="OESCR integral")
    ax.axhline(
        band_expected,
        color=BLACK,
        linestyle="--",
        linewidth=1.4,
        label="Analytic target",
    )
    band_error = abs(band_cumulative[-1] / band_expected - 1.0)
    ax.annotate(
        f"calculated {band_cumulative[-1]:.6f}\ntarget {band_expected:.6f}\nrelative error {band_error:.2e}",
        xy=(band_x[-1], band_cumulative[-1]),
        xytext=(0.53, 0.42),
        textcoords="axes fraction",
        arrowprops={"arrowstyle": "->", "color": GREY},
        fontsize=9,
    )
    ax.set(
        xlabel="Upper integration wavelength (nm)",
        ylabel="Integrated radiance\n(W m$^{-2}$ sr$^{-1}$)",
    )
    ax.set_title("Band integral reaches the analytic target", loc="left", fontweight="bold")
    ax.grid(True)
    ax.legend(loc="lower right")
    _panel_label(ax, "B")

    ax = axes[1, 0]
    ax.plot(combined_x, combined_y, color=BLUE, linewidth=2.0)
    ax.fill_between(combined_x, combined_y, color=PALE_BLUE, alpha=0.55)
    ax.set(
        xlabel="Wavelength (nm)",
        ylabel="Spectral radiance\n(W m$^{-2}$ sr$^{-1}$ nm$^{-1}$)",
    )
    ax.set_title(
        "Independent 500 nm band + 600 nm atomic line",
        loc="left",
        fontweight="bold",
    )
    ax.grid(axis="y")
    _panel_label(ax, "C")

    ax = axes[1, 1]
    ax.plot(
        combined_x,
        combined_cumulative,
        color=BLUE,
        linewidth=2.2,
        label="OESCR integral",
    )
    ax.axhline(
        combined_expected,
        color=BLACK,
        linestyle="--",
        linewidth=1.4,
        label="Analytic target",
    )
    combined_error = abs(combined_cumulative[-1] / combined_expected - 1.0)
    ax.annotate(
        f"calculated {combined_cumulative[-1]:.6f}\n"
        f"target {combined_expected:.6f}\n"
        f"relative error {combined_error:.2e}",
        xy=(combined_x[-1], combined_cumulative[-1]),
        xytext=(0.46, 0.42),
        textcoords="axes fraction",
        arrowprops={"arrowstyle": "->", "color": GREY},
        fontsize=9,
    )
    ax.set(
        xlabel="Upper integration wavelength (nm)",
        ylabel="Integrated radiance\n(W m$^{-2}$ sr$^{-1}$)",
    )
    ax.set_title(
        "Combined integral reaches the sum target",
        loc="left",
        fontweight="bold",
    )
    ax.grid(True)
    ax.legend(loc="lower right")
    _panel_label(ax, "D")

    path = OUTPUT_DIR / "01_analytic_forward_reproduction.png"
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def _fit_two_band(case_name: str, inverse_name: str) -> tuple[InverseSolver, Any]:
    base = ROOT / "examples" / "use_cases" / "two_band"
    solver = InverseSolver.from_yaml(base / case_name, base / inverse_name)
    fit = solver.fit()
    if not fit.success:
        raise RuntimeError(f"Two-band fit failed for {inverse_name}: {fit.message}")
    return solver, fit


def render_two_band_inverse() -> Path:
    base = ROOT / "examples" / "use_cases" / "two_band"
    measurement = _read_numeric_csv(base / "measurement.csv")
    wavelength = measurement["wavelength_nm"]
    measured = measurement["intensity"]
    sigma = measurement["sigma"]

    ratio_solver, ratio_fit = _fit_two_band("case_ratio_init.yaml", "inverse_ratio.yaml")
    _, actinometry_fit = _fit_two_band("case_ratio_init.yaml", "inverse_actinometry.yaml")
    absolute_solver, absolute_fit = _fit_two_band("case_absolute_init.yaml", "inverse_absolute.yaml")
    if not np.allclose(
        ratio_fit.x_opt,
        actinometry_fit.x_opt,
        rtol=1.0e-12,
        atol=0.0,
    ):
        raise RuntimeError("Ratio and actinometry paths no longer produce the same numerical result")

    ratio_init = _instrument_spectrum(ratio_solver.model.predict(), "two_band_radiance")[1]
    ratio_opt = _instrument_spectrum(ratio_solver.model.predict(ratio_fit.case_opt), "two_band_radiance")[1]
    absolute_init = _instrument_spectrum(absolute_solver.model.predict(), "two_band_radiance")[1]
    absolute_opt = _instrument_spectrum(absolute_solver.model.predict(absolute_fit.case_opt), "two_band_radiance")[1]

    truth_case = load_yaml(base / "case_truth.yaml")
    target_initial = float(ratio_solver.case_cfg["plasma_state"]["radicals"]["Target"][0])
    target_optimized = float(ratio_fit.case_opt["plasma_state"]["radicals"]["Target"][0])
    target_truth = float(truth_case["plasma_state"]["radicals"]["Target"][0])
    ne_initial = float(absolute_solver.case_cfg["plasma_state"]["ne_shells_m3"][0])
    ne_optimized = float(absolute_fit.case_opt["plasma_state"]["ne_shells_m3"][0])
    ne_truth = float(truth_case["plasma_state"]["ne_shells_m3"][0])

    fig, axes = plt.subplots(2, 2, figsize=(12.2, 7.4), constrained_layout=True)
    fig.suptitle(
        "Two-band inverse benchmark: spectra and recovered physical quantities",
        fontsize=15,
        fontweight="bold",
    )

    for panel, ax, initial, optimized, title in (
        (
            "A",
            axes[0, 0],
            ratio_init,
            ratio_opt,
            "Ratio / actinometry: target-to-reference band ratio",
        ),
        (
            "B",
            axes[0, 1],
            absolute_init,
            absolute_opt,
            "Absolute mode: calibrated spectral radiance",
        ),
    ):
        ax.errorbar(
            wavelength,
            measured,
            yerr=sigma,
            color=BLACK,
            linestyle="none",
            marker="o",
            markerfacecolor="white",
            markersize=3.5,
            capsize=2,
            linewidth=0.8,
            label="Measurement ± 1σ",
            zorder=3,
        )
        ax.plot(
            wavelength,
            initial,
            color=ORANGE,
            linestyle="--",
            linewidth=1.9,
            label="Initial prediction",
        )
        ax.plot(
            wavelength,
            optimized,
            color=BLUE,
            linewidth=2.2,
            label="Optimized prediction",
        )
        ax.set(
            xlabel="Wavelength (nm)",
            ylabel="Spectral radiance\n(W m$^{-2}$ sr$^{-1}$ nm$^{-1}$)",
        )
        ax.set_title(title, loc="left", fontweight="bold")
        ax.grid(axis="y")
        ax.legend(loc="upper right", fontsize=8.5)
        _panel_label(ax, panel)

    def plot_recovery(
        ax: plt.Axes,
        initial: float,
        optimized: float,
        truth: float,
        scale: float,
        title: str,
        ylabel: str,
        panel: str,
    ) -> None:
        values = np.asarray([initial, optimized], dtype=float) / scale
        target = truth / scale
        ax.plot([0, 1], values, color=GREY, linewidth=1.4, zorder=1)
        ax.scatter([0], [values[0]], color=ORANGE, s=70, marker="s", label="Initial", zorder=2)
        ax.scatter([1], [values[1]], color=BLUE, s=70, marker="o", label="Optimized", zorder=2)
        ax.axhline(
            target,
            color=BLACK,
            linestyle="--",
            linewidth=1.5,
            label="Known target",
        )
        ax.set_xticks([0, 1], ["Initial", "Optimized"])
        ax.set_xlim(-0.35, 1.35)
        spread = max(
            abs(values[0] - target),
            abs(values[1] - target),
            0.05 * target,
        )
        ax.set_ylim(
            min(values.min(), target) - 0.25 * spread,
            max(values.max(), target) + 0.35 * spread,
        )
        ax.set_ylabel(ylabel)
        ax.set_title(title, loc="left", fontweight="bold")
        ax.grid(axis="y")
        for x_value, value in zip([0, 1], values, strict=True):
            ax.text(
                x_value,
                value + 0.07 * spread,
                f"{value:.6g}",
                ha="center",
                va="bottom",
                fontsize=9,
            )
        ax.legend(loc="lower right", fontsize=8.5)
        _panel_label(ax, panel)

    plot_recovery(
        axes[1, 0],
        target_initial,
        target_optimized,
        target_truth,
        1.0e18,
        "Target density recovered from the band ratio",
        "Target density (10$^{18}$ m$^{-3}$)",
        "C",
    )
    plot_recovery(
        axes[1, 1],
        ne_initial,
        ne_optimized,
        ne_truth,
        1.0e16,
        "Electron density recovered from absolute radiance",
        "Electron density (10$^{16}$ m$^{-3}$)",
        "D",
    )

    path = OUTPUT_DIR / "02_two_band_inverse_recovery.png"
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_spectral_window(
    spectrum_ax: plt.Axes,
    residual_ax: plt.Axes,
    data: dict[str, np.ndarray],
    limits: tuple[float, float],
    title: str,
    panel: str,
    *,
    baseline_correct: bool = True,
) -> None:
    wavelength = data["wavelength_nm"]
    mask = (wavelength >= limits[0]) & (wavelength <= limits[1])
    x = wavelength[mask]
    measurement = data["measurement"][mask]
    initial = data["init_fit"][mask]
    optimized = data["opt_fit"][mask]
    if baseline_correct:
        measurement = measurement - fit_local_baseline(x, measurement)
        initial = initial - fit_local_baseline(x, initial)
        optimized = optimized - fit_local_baseline(x, optimized)
    peak = max(float(np.max(np.abs(measurement))), 1.0e-30)
    normalized_measurement = measurement / peak
    normalized_initial = initial / peak
    normalized_optimized = optimized / peak
    marker_every = max(len(x) // 45, 1)

    _plot_observation_and_predictions(
        spectrum_ax,
        x,
        normalized_measurement,
        normalized_initial,
        normalized_optimized,
        marker_every=marker_every,
    )
    spectrum_ax.set_xlim(*limits)
    spectrum_ax.set_ylim(bottom=min(-0.08, 1.1 * float(np.min(normalized_measurement))))
    spectrum_ax.set_title(title, loc="left", fontweight="bold")
    spectrum_ax.grid(axis="y")
    spectrum_ax.tick_params(labelbottom=False)
    _panel_label(spectrum_ax, panel)

    residual_ax.plot(
        x,
        100.0 * (initial - measurement) / peak,
        color=ORANGE,
        linestyle="--",
        linewidth=1.25,
    )
    residual_ax.plot(
        x,
        100.0 * (optimized - measurement) / peak,
        color=BLUE,
        linewidth=1.35,
    )
    residual_ax.axhline(0.0, color=BLACK, linewidth=0.8)
    residual_ax.set_xlim(*limits)
    residual_ax.set_xlabel("Wavelength (nm)")
    residual_ax.grid(axis="y")


def _shell_centers(case: dict[str, Any]) -> np.ndarray:
    n_shells = int(case["geometry"]["n_shells"])
    return (np.arange(n_shells, dtype=float) + 0.5) / n_shells


def _plot_profile(
    ax: plt.Axes,
    radius: np.ndarray,
    initial: np.ndarray,
    optimized: np.ndarray,
    truth: np.ndarray,
    *,
    scale: float,
    title: str,
    ylabel: str,
    panel: str,
) -> None:
    ax.plot(
        radius,
        initial / scale,
        color=ORANGE,
        linestyle="--",
        marker="s",
        linewidth=1.7,
        label="Initial",
    )
    ax.plot(
        radius,
        optimized / scale,
        color=BLUE,
        marker="o",
        linewidth=2.0,
        label="Optimized",
    )
    ax.plot(
        radius,
        truth / scale,
        color=BLACK,
        linestyle=":",
        marker="D",
        linewidth=1.6,
        label="Known truth",
    )
    ax.set(xlabel="Shell-center radius, r/R", ylabel=ylabel)
    ax.set_xlim(0.0, 1.0)
    ax.set_title(title, loc="left", fontweight="bold")
    ax.grid(True)
    _panel_label(ax, panel)


def _case_array(case: dict[str, Any], *path: str) -> np.ndarray:
    value: Any = case
    for key in path:
        value = value[key]
    return np.asarray(value, dtype=float)


def _benchmark_paths(
    benchmark_id: str,
    instrument_id: str,
) -> tuple[Path, Path, Path, Path]:
    base = ROOT / "examples" / "benchmarks" / benchmark_id
    run = base / "runs" / "inverse_observable_20260929"
    comparison = run / "analysis_observable" / "comparisons" / f"{instrument_id}_chord_2_comparison.csv"
    return (
        base / "case_init.yaml",
        base / "case_truth.yaml",
        run / "case_opt.yaml",
        comparison,
    )


def render_nf3_benchmark() -> Path:
    init_path, truth_path, opt_path, comparison_path = _benchmark_paths("nf3_ar_ccp_clean_2023", "nf3_benchmark_uvvis")
    init_case = load_yaml(init_path)
    truth_case = load_yaml(truth_path)
    opt_case = load_yaml(opt_path)
    chord_indices = [0, 2, 4]
    chord_data = [
        _read_numeric_csv(comparison_path.with_name(f"nf3_benchmark_uvvis_chord_{chord_index}_comparison.csv"))
        for chord_index in chord_indices
    ]

    fig = plt.figure(figsize=(13.2, 8.3), constrained_layout=True)
    grid = fig.add_gridspec(3, 3, height_ratios=[2.1, 0.72, 1.55])
    fig.suptitle(
        "NF₃/Ar generated benchmark: F I spectral fit across chords and inferred profiles",
        fontsize=15,
        fontweight="bold",
    )

    chamber_radius = float(truth_case["geometry"]["chamber_radius_m"])
    chord_radii = np.asarray(truth_case["geometry"]["chord_r_m"], dtype=float)
    spectrum_axes: list[plt.Axes] = []
    residual_axes: list[plt.Axes] = []
    for index, (chord_index, data) in enumerate(zip(chord_indices, chord_data, strict=True)):
        spectrum_ax = fig.add_subplot(grid[0, index])
        residual_ax = fig.add_subplot(grid[1, index])
        normalized_radius = chord_radii[chord_index] / chamber_radius
        _plot_spectral_window(
            spectrum_ax,
            residual_ax,
            data,
            (680.0, 718.0),
            f"Chord {chord_index}: b/R = {normalized_radius:.2f}",
            chr(ord("A") + index),
            baseline_correct=False,
        )
        spectrum_axes.append(spectrum_ax)
        residual_axes.append(residual_ax)
    spectrum_axes[0].set_ylabel("Intensity / measured window peak")
    residual_axes[0].set_ylabel("Prediction − measurement\n(% of window peak)")
    spectrum_axes[0].legend(loc="upper right", fontsize=8.0)

    radius = _shell_centers(truth_case)
    profile_specs = [
        (
            ("plasma_state", "te_shells_eV"),
            1.0,
            "Electron temperature",
            "$T_e$ (eV)",
        ),
        (
            ("plasma_state", "radicals", "F"),
            1.0e18,
            "F density",
            "$n_F$ (10$^{18}$ m$^{-3}$)",
        ),
        (
            ("plasma_state", "radicals", "N2_emit"),
            1.0e18,
            "N₂ emitter proxy",
            "$n_{N2,emit}$ (10$^{18}$ m$^{-3}$)",
        ),
    ]
    profile_axes: list[plt.Axes] = []
    for index, (parameter_path, scale, title, ylabel) in enumerate(profile_specs):
        ax = fig.add_subplot(grid[2, index])
        _plot_profile(
            ax,
            radius,
            _case_array(init_case, *parameter_path),
            _case_array(opt_case, *parameter_path),
            _case_array(truth_case, *parameter_path),
            scale=scale,
            title=title,
            ylabel=ylabel,
            panel=chr(ord("D") + index),
        )
        profile_axes.append(ax)
    handles, labels = profile_axes[0].get_legend_handles_labels()
    profile_axes[-1].legend(handles, labels, loc="best", fontsize=8.5)

    path = OUTPUT_DIR / "03_nf3_spectral_fit_and_recovery.png"
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def render_cl2_benchmark() -> Path:
    init_path, truth_path, opt_path, comparison_path = _benchmark_paths("cl2_ar_icp_fuller2001", "cl2_benchmark_scan")
    init_case = load_yaml(init_path)
    truth_case = load_yaml(truth_path)
    opt_case = load_yaml(opt_path)
    data = _read_numeric_csv(comparison_path)

    fig = plt.figure(figsize=(13.2, 8.3), constrained_layout=True)
    grid = fig.add_gridspec(3, 3, height_ratios=[2.1, 0.72, 1.55])
    fig.suptitle(
        "Cl₂/Ar generated benchmark: spectral fit and inferred radial profiles",
        fontsize=15,
        fontweight="bold",
    )

    windows = [
        ((300.0, 312.0), "Cl₂ molecular band"),
        ((478.0, 484.5), "Ar II / Cl II doublet"),
        ((818.0, 832.0), "Cl I / Xe I region"),
    ]
    spectrum_axes: list[plt.Axes] = []
    residual_axes: list[plt.Axes] = []
    for index, (limits, title) in enumerate(windows):
        spectrum_ax = fig.add_subplot(grid[0, index])
        residual_ax = fig.add_subplot(grid[1, index])
        _plot_spectral_window(
            spectrum_ax,
            residual_ax,
            data,
            limits,
            title,
            chr(ord("A") + index),
        )
        spectrum_axes.append(spectrum_ax)
        residual_axes.append(residual_ax)
    spectrum_axes[0].set_ylabel("Baseline-corrected intensity\n/ measured window peak")
    residual_axes[0].set_ylabel("Prediction − measurement\n(% of window peak)")
    spectrum_axes[0].legend(loc="upper right", fontsize=8.0)

    bottom = grid[2, :].subgridspec(1, 2, wspace=0.18)
    radius = _shell_centers(truth_case)
    profile_specs = [
        (
            ("plasma_state", "radicals", "Cl"),
            "Cl density",
            "$n_{Cl}$ (10$^{18}$ m$^{-3}$)",
        ),
        (
            ("plasma_state", "radicals", "Cl2_emit"),
            "Cl₂ emitter proxy",
            "$n_{Cl2,emit}$ (10$^{18}$ m$^{-3}$)",
        ),
    ]
    profile_axes: list[plt.Axes] = []
    for index, (parameter_path, title, ylabel) in enumerate(profile_specs):
        ax = fig.add_subplot(bottom[0, index])
        _plot_profile(
            ax,
            radius,
            _case_array(init_case, *parameter_path),
            _case_array(opt_case, *parameter_path),
            _case_array(truth_case, *parameter_path),
            scale=1.0e18,
            title=title,
            ylabel=ylabel,
            panel=chr(ord("D") + index),
        )
        profile_axes.append(ax)
    handles, labels = profile_axes[0].get_legend_handles_labels()
    profile_axes[-1].legend(handles, labels, loc="best", fontsize=8.5)

    path = OUTPUT_DIR / "04_cl2_spectral_fit_and_recovery.png"
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _style()
    paths = [
        render_analytic_forward(),
        render_two_band_inverse(),
        render_nf3_benchmark(),
        render_cl2_benchmark(),
    ]
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
