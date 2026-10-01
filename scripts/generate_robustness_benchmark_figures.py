"""Evaluate and plot the multi-seed distant-initialization benchmarks."""

from __future__ import annotations

import csv
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import NullFormatter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oescr.inverse.gain_model import apply_gain_offset_tilt  # noqa: E402
from oescr.inverse.measurements import load_measurement_csv  # noqa: E402
from oescr.inverse.objectives import residual_vector  # noqa: E402
from oescr.inverse.optimize import InverseSolver  # noqa: E402
from oescr.inverse.window_metrics import fit_local_baseline  # noqa: E402
from oescr.io.pathmap import get_path  # noqa: E402
from oescr.io.yaml_loader import load_yaml, save_yaml  # noqa: E402

OUTPUT_DIR = ROOT / "docs" / "robustness-figures"
RUN_DIR = ROOT / ".local_outputs" / "robustness_benchmarks"
BENCHMARK_IDS = (
    "nf3_ar_ccp_clean_2023",
    "cl2_ar_icp_fuller2001",
)

BLACK = "#111827"
GREY = "#667085"
LIGHT_GREY = "#d7dce3"
ORANGE = "#d97706"
BLUE = "#2563eb"
SEED_COLORS = ("#93c5fd", "#2563eb", "#1e3a8a")


@dataclass
class RunEvaluation:
    seed: int
    cost: float
    success: bool
    held_out_truth_nrmse: float
    held_out_window_truth_nrmse: dict[str, float]
    parameter_median_error: float
    parameter_max_error: float
    seed_pass: bool
    case_opt: dict[str, Any]
    summary: dict[str, Any]
    parameter_rows: list[dict[str, Any]]


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
        1.07,
        label,
        transform=ax.transAxes,
        fontsize=11.5,
        fontweight="bold",
        va="bottom",
    )


def _parameter_label(name: str) -> str:
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


def _gain_for_case(solver: InverseSolver, case_cfg: dict[str, Any], instrument_id: str) -> dict[str, float]:
    _, aux = residual_vector(
        solver.model,
        case_cfg,
        solver.inv_cfg,
        solver.measurements,
        solver.windows,
    )
    gain_map = aux.get("gain_offset", {})
    for chord_index in range(len(solver.measurements[instrument_id])):
        key = (instrument_id, f"chord_{chord_index}")
        if key in gain_map:
            return gain_map[key]
    return {"gain": 1.0, "offset": 0.0, "tilt": 0.0}


def _held_out_prediction(
    solver: InverseSolver,
    case_cfg: dict[str, Any],
    metadata: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    instrument_id = str(metadata["instrument_id"])
    held_out_index = int(metadata["held_out_chord"])
    measurement_path = ROOT / "examples" / "benchmarks" / metadata["benchmark_id"] / metadata["held_out_measurement"]
    measurement = load_measurement_csv(measurement_path)
    spectrum = solver.model.predict(case_cfg).spectra[instrument_id][f"chord_{held_out_index}"]
    prediction = np.interp(
        measurement.wavelength_nm,
        spectrum["wavelength_nm"],
        spectrum["intensity"],
        left=0.0,
        right=0.0,
    )
    gain = _gain_for_case(solver, case_cfg, instrument_id)
    fitted = apply_gain_offset_tilt(
        measurement.wavelength_nm,
        prediction,
        float(gain.get("gain", 1.0)),
        float(gain.get("tilt", 0.0)),
        float(gain.get("offset", 0.0)),
    )
    return measurement.wavelength_nm, measurement.intensity, fitted


def _held_out_truth_prediction(
    solver: InverseSolver,
    case_cfg: dict[str, Any],
    metadata: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    instrument_id = str(metadata["instrument_id"])
    held_out_index = int(metadata["held_out_chord"])
    benchmark_dir = ROOT / "examples" / "benchmarks" / metadata["benchmark_id"]
    truth_path = benchmark_dir / "forward_truth" / f"{instrument_id}_chord_{held_out_index}.csv"
    truth_spectrum = load_measurement_csv(truth_path)
    candidate = solver.model.predict(case_cfg).spectra[instrument_id][f"chord_{held_out_index}"]
    prediction = np.interp(
        truth_spectrum.wavelength_nm,
        candidate["wavelength_nm"],
        candidate["intensity"],
        left=0.0,
        right=0.0,
    )
    return truth_spectrum.wavelength_nm, truth_spectrum.intensity, prediction


def _window_values(
    wavelength: np.ndarray,
    measurement: np.ndarray,
    prediction: np.ndarray,
    window: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    mask = (wavelength >= float(window["min_nm"])) & (wavelength <= float(window["max_nm"]))
    x = np.asarray(wavelength[mask], dtype=float)
    measured = np.asarray(measurement[mask], dtype=float).copy()
    predicted = np.asarray(prediction[mask], dtype=float).copy()
    if bool(window.get("baseline_correct", False)):
        measured -= fit_local_baseline(x, measured)
        predicted -= fit_local_baseline(x, predicted)
    scale = max(float(np.max(np.abs(measured))), 1.0e-30)
    nrmse = float(np.sqrt(np.mean(((predicted - measured) / scale) ** 2)))
    return x, measured / scale, predicted / scale, nrmse


def _held_out_truth_nrmse(
    wavelength: np.ndarray,
    measurement: np.ndarray,
    prediction: np.ndarray,
    windows: list[dict[str, Any]],
) -> float:
    return float(np.mean(list(_held_out_window_truth_nrmse(wavelength, measurement, prediction, windows).values())))


def _held_out_window_truth_nrmse(
    wavelength: np.ndarray,
    measurement: np.ndarray,
    prediction: np.ndarray,
    windows: list[dict[str, Any]],
) -> dict[str, float]:
    return {str(window["label"]): _window_values(wavelength, measurement, prediction, window)[3] for window in windows}


def _parameter_rows(
    solver: InverseSolver,
    truth: dict[str, Any],
    optimized: dict[str, Any],
    seed: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for parameter in solver.params.params:
        initial = float(get_path(solver.case_cfg, parameter.path))
        target = float(get_path(truth, parameter.path))
        optimum = float(get_path(optimized, parameter.path))
        rows.append(
            {
                "seed": seed,
                "parameter": parameter.name,
                "path": parameter.path,
                "initial": initial,
                "truth": target,
                "optimized": optimum,
                "initial_relative_error": initial / target - 1.0,
                "optimized_relative_error": optimum / target - 1.0,
            }
        )
    return rows


def _load_case_evaluations(
    benchmark_id: str,
) -> tuple[
    dict[str, Any],
    InverseSolver,
    dict[str, Any],
    list[RunEvaluation],
    dict[str, Any],
]:
    base = ROOT / "examples" / "benchmarks" / benchmark_id
    metadata = load_yaml(base / "robustness.yaml")
    metadata["benchmark_id"] = benchmark_id
    solver = InverseSolver.from_yaml(base / metadata["case"], base / metadata["inverse"])
    truth = load_yaml(base / metadata["truth"])
    acceptance = metadata["acceptance"]

    initial_wavelength, initial_measurement, initial_prediction = _held_out_truth_prediction(
        solver,
        solver.case_cfg,
        metadata,
    )
    initial_nrmse = _held_out_truth_nrmse(
        initial_wavelength,
        initial_measurement,
        initial_prediction,
        metadata["plot_windows"],
    )
    initial_window_nrmse = _held_out_window_truth_nrmse(
        initial_wavelength,
        initial_measurement,
        initial_prediction,
        metadata["plot_windows"],
    )
    initial_errors = np.asarray(
        [
            abs(float(get_path(solver.case_cfg, parameter.path)) / float(get_path(truth, parameter.path)) - 1.0)
            for parameter in solver.params.params
        ],
        dtype=float,
    )
    initial_metrics = {
        "held_out_truth_nrmse": initial_nrmse,
        "held_out_window_truth_nrmse": initial_window_nrmse,
        "parameter_median_error": float(np.median(initial_errors)),
        "parameter_max_error": float(np.max(initial_errors)),
    }

    evaluations: list[RunEvaluation] = []
    for seed_value in metadata["seeds"]:
        seed = int(seed_value)
        run_dir = RUN_DIR / benchmark_id / f"seed_{seed}"
        summary_path = run_dir / "fit_summary.yaml"
        if not summary_path.exists():
            raise FileNotFoundError(
                f"Missing robustness output for {benchmark_id} seed {seed}; "
                "run scripts/run_optimization_robustness_benchmarks.py first."
            )
        summary = load_yaml(summary_path)
        case_opt = deepcopy(solver.case_cfg)
        solver.params.apply_to_case(case_opt, np.asarray(summary["x_opt"], dtype=float))
        wavelength, measurement, prediction = _held_out_truth_prediction(solver, case_opt, metadata)
        held_out_nrmse = _held_out_truth_nrmse(
            wavelength,
            measurement,
            prediction,
            metadata["plot_windows"],
        )
        held_out_window_nrmse = _held_out_window_truth_nrmse(
            wavelength,
            measurement,
            prediction,
            metadata["plot_windows"],
        )
        rows = _parameter_rows(solver, truth, case_opt, seed)
        parameter_errors = np.asarray(
            [abs(float(row["optimized_relative_error"])) for row in rows],
            dtype=float,
        )
        median_error = float(np.median(parameter_errors))
        max_error = float(np.max(parameter_errors))
        seed_pass = bool(
            summary["success"]
            and held_out_nrmse <= float(acceptance["max_optimized_held_out_truth_nrmse"])
            and median_error <= float(acceptance["max_optimized_parameter_median_abs_relative_error"])
            and max_error <= float(acceptance["max_optimized_parameter_max_abs_relative_error"])
        )
        evaluations.append(
            RunEvaluation(
                seed=seed,
                cost=float(summary["cost"]),
                success=bool(summary["success"]),
                held_out_truth_nrmse=held_out_nrmse,
                held_out_window_truth_nrmse=held_out_window_nrmse,
                parameter_median_error=median_error,
                parameter_max_error=max_error,
                seed_pass=seed_pass,
                case_opt=case_opt,
                summary=summary,
                parameter_rows=rows,
            )
        )
    return metadata, solver, truth, evaluations, initial_metrics


def _plot_held_out_spectra(
    parent: Any,
    solver: InverseSolver,
    metadata: dict[str, Any],
    truth: dict[str, Any],
    best: RunEvaluation,
) -> list[plt.Axes]:
    initial = _held_out_prediction(solver, solver.case_cfg, metadata)
    optimized = _held_out_prediction(solver, best.case_opt, metadata)
    truth_prediction = _held_out_prediction(solver, truth, metadata)
    windows = metadata["plot_windows"]
    subgrid = parent.subgridspec(1, len(windows), wspace=0.12)
    axes: list[plt.Axes] = []
    for index, window in enumerate(windows):
        ax = cast(plt.Axes, plt.subplot(subgrid[0, index]))
        x, measured, init_values, _ = _window_values(*initial, window)
        _, _, opt_values, _ = _window_values(*optimized, window)
        _, _, truth_values, _ = _window_values(*truth_prediction, window)
        every = max(len(x) // 40, 1)
        ax.plot(x, init_values, color=ORANGE, linestyle="--", linewidth=1.5, label="Distant initial")
        ax.plot(x, opt_values, color=BLUE, linewidth=1.8, label=f"Selected seed {best.seed}")
        ax.plot(x, truth_values, color=BLACK, linewidth=1.2, label="Known noise-free truth")
        ax.plot(
            x[::every],
            measured[::every],
            color=BLACK,
            linestyle="none",
            marker="o",
            markerfacecolor="white",
            markersize=2.8,
            label="Held-out noisy measurement",
        )
        ax.set_title(str(window["label"]), loc="left", fontweight="bold")
        ax.set_xlabel("Wavelength (nm)")
        if index == 0:
            ax.set_ylabel("Baseline-corrected intensity / held-out peak")
            ax.legend(loc="best", fontsize=7.5)
        ax.grid(axis="y")
        axes.append(ax)
    _panel_label(axes[0], "A")
    return axes


def _plot_parameter_recovery(
    ax: plt.Axes,
    solver: InverseSolver,
    truth: dict[str, Any],
    evaluations: list[RunEvaluation],
) -> None:
    target = np.asarray(
        [float(get_path(truth, parameter.path)) for parameter in solver.params.params],
        dtype=float,
    )
    initial = np.asarray(
        [float(get_path(solver.case_cfg, parameter.path)) for parameter in solver.params.params],
        dtype=float,
    )
    y = np.arange(len(target), dtype=float)
    ax.axvspan(0.6, 1.4, color=LIGHT_GREY, alpha=0.35, label="±40% maximum band")
    ax.axvspan(0.8, 1.2, color="#dbeafe", alpha=0.8, label="±20% reference band")
    ax.axvline(1.0, color=BLACK, linestyle=":", linewidth=1.5, label="Known truth")
    ax.scatter(initial / target, y, color=ORANGE, marker="s", s=32, label="Distant initial", zorder=3)
    for evaluation, color in zip(evaluations, SEED_COLORS, strict=True):
        optimum = np.asarray(
            [float(get_path(evaluation.case_opt, parameter.path)) for parameter in solver.params.params],
            dtype=float,
        )
        ax.scatter(
            optimum / target,
            y,
            color=color,
            s=27,
            label=f"seed {evaluation.seed}",
            zorder=4,
        )
    ax.set_yticks(y, [_parameter_label(parameter.name) for parameter in solver.params.params])
    ax.invert_yaxis()
    ax.set_xscale("log")
    ratios = np.concatenate(
        [
            initial / target,
            *[
                np.asarray([float(get_path(item.case_opt, parameter.path)) for parameter in solver.params.params])
                / target
                for item in evaluations
            ],
        ]
    )
    ax.set_xlim(max(0.08, float(np.min(ratios)) * 0.75), min(8.0, float(np.max(ratios)) * 1.25))
    lower, upper = ax.get_xlim()
    readable_ticks = [value for value in (0.1, 0.2, 0.5, 1.0, 2.0, 5.0) if lower <= value <= upper]
    ax.set_xticks(readable_ticks, [f"{value:g}" for value in readable_ticks])
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.tick_params(axis="x", which="minor", labelbottom=False)
    ax.set_xlabel("Value / known truth (log scale)")
    ax.set_title("All inferred parameters across three seeds", loc="left", fontweight="bold")
    ax.grid(axis="x", which="both")
    ax.legend(loc="best", fontsize=7.0, ncol=2)
    _panel_label(ax, "B")


def _plot_loss_history(
    ax: plt.Axes,
    evaluations: list[RunEvaluation],
    initial_loss: float,
) -> None:
    ax.axhline(initial_loss, color=ORANGE, linestyle="--", linewidth=1.5, label="Distant initial Loss")
    for evaluation, color in zip(evaluations, SEED_COLORS, strict=True):
        trace = evaluation.summary["optimization_trace"]
        x = np.asarray([row["evaluation"] for row in trace], dtype=int)
        losses = np.asarray([row["loss"] for row in trace], dtype=float)
        ax.plot(x, np.minimum.accumulate(losses), color=color, linewidth=1.8, label=f"seed {evaluation.seed}")
    all_losses = [initial_loss]
    for evaluation in evaluations:
        all_losses.extend(float(row["loss"]) for row in evaluation.summary["optimization_trace"])
    positive_losses = [value for value in all_losses if value > 0.0]
    if max(positive_losses) / min(positive_losses) > 3.0:
        ax.set_yscale("log")
    ax.set_xlabel("Objective evaluation")
    ax.set_ylabel("Best training Loss so far")
    ax.set_title("Actual multi-seed optimization histories", loc="left", fontweight="bold")
    ax.grid(axis="y", which="both")
    ax.legend(loc="best", fontsize=7.5)
    _panel_label(ax, "C")


def _plot_acceptance_metrics(
    parent: Any,
    metadata: dict[str, Any],
    evaluations: list[RunEvaluation],
    initial_metrics: dict[str, Any],
) -> list[plt.Axes]:
    subgrid = parent.subgridspec(1, 2, wspace=0.28)
    labels = ["initial", *[f"seed {item.seed}" for item in evaluations]]
    colors = [ORANGE, *SEED_COLORS]
    x = np.arange(len(labels))
    axes: list[plt.Axes] = []
    specifications = (
        (
            "held_out_truth_nrmse",
            "Held-out truth-spectrum NRMSE",
            float(metadata["acceptance"]["max_optimized_held_out_truth_nrmse"]),
        ),
        (
            "parameter_median_error",
            "Median parameter |relative error|",
            float(metadata["acceptance"]["max_optimized_parameter_median_abs_relative_error"]),
        ),
    )
    for index, (field, title, threshold) in enumerate(specifications):
        ax = cast(plt.Axes, plt.subplot(subgrid[0, index]))
        values = [float(initial_metrics[field]), *[float(getattr(item, field)) for item in evaluations]]
        ax.bar(x, values, color=colors, edgecolor=BLACK, linewidth=0.6, width=0.68)
        ax.axhline(threshold, color=BLACK, linestyle=":", linewidth=1.4, label=f"Optimized limit {threshold:.2f}")
        for position, value in zip(x, values, strict=True):
            ax.text(float(position), value, f"{value:.3f}", ha="center", va="bottom", fontsize=7.5)
        ax.set_xticks(x, labels, rotation=30, ha="right")
        ax.set_ylim(0.0, max(max(values) * 1.22, threshold * 1.5))
        ax.set_ylabel("Fraction")
        ax.set_title(title, loc="left", fontweight="bold")
        ax.grid(axis="y")
        ax.legend(loc="best", fontsize=7.2)
        axes.append(ax)
    _panel_label(axes[0], "D")
    return axes


def _render_case(
    benchmark_id: str,
    metadata: dict[str, Any],
    solver: InverseSolver,
    truth: dict[str, Any],
    evaluations: list[RunEvaluation],
    initial_metrics: dict[str, Any],
    overall_pass: bool,
) -> Path:
    best = min(evaluations, key=lambda item: item.cost)
    title_name = "NF₃/Ar" if benchmark_id.startswith("nf3") else "Cl₂/Ar"
    status = "PASS" if overall_pass else "FAIL"
    fig = plt.figure(figsize=(15.5, 10.5), constrained_layout=True)
    grid = fig.add_gridspec(2, 2, height_ratios=[1.0, 0.95], width_ratios=[1.12, 0.88])
    fig.suptitle(
        f"{title_name} distant-initialization robustness benchmark — {status}",
        fontsize=15.5,
        fontweight="bold",
    )
    _plot_held_out_spectra(grid[0, 0], solver, metadata, truth, best)
    parameter_ax = fig.add_subplot(grid[0, 1])
    _plot_parameter_recovery(parameter_ax, solver, truth, evaluations)
    loss_ax = fig.add_subplot(grid[1, 0])
    _plot_loss_history(loss_ax, evaluations, float(evaluations[0].summary["initial_loss"]))
    _plot_acceptance_metrics(grid[1, 1], metadata, evaluations, initial_metrics)
    filename = (
        "01_nf3_distant_initialization.png" if benchmark_id.startswith("nf3") else "02_cl2_distant_initialization.png"
    )
    output_path = OUTPUT_DIR / filename
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return output_path


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    _style()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict[str, Any]] = []
    parameter_rows: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    yaml_cases: list[dict[str, Any]] = []
    generated: list[Path] = []

    for benchmark_id in BENCHMARK_IDS:
        metadata, solver, truth, evaluations, initial_metrics = _load_case_evaluations(benchmark_id)
        acceptance = metadata["acceptance"]
        initial_challenge_pass = bool(
            initial_metrics["held_out_truth_nrmse"] >= float(acceptance["min_initial_held_out_truth_nrmse"])
            and initial_metrics["parameter_median_error"]
            >= float(acceptance["min_initial_parameter_median_abs_relative_error"])
        )
        pass_fraction = float(np.mean([item.seed_pass for item in evaluations]))
        overall_pass = bool(initial_challenge_pass and pass_fraction >= float(acceptance["min_seed_pass_fraction"]))
        best = min(evaluations, key=lambda item: item.cost)

        summary_rows.append(
            {
                "benchmark": benchmark_id,
                "role": "initial",
                "seed": "",
                "selected": False,
                "training_loss": float(evaluations[0].summary["initial_loss"]),
                "held_out_truth_nrmse": initial_metrics["held_out_truth_nrmse"],
                "parameter_median_abs_relative_error": initial_metrics["parameter_median_error"],
                "parameter_max_abs_relative_error": initial_metrics["parameter_max_error"],
                "pass": initial_challenge_pass,
            }
        )
        for window, nrmse in initial_metrics["held_out_window_truth_nrmse"].items():
            window_rows.append(
                {
                    "benchmark": benchmark_id,
                    "role": "initial",
                    "seed": "",
                    "selected": False,
                    "window": window,
                    "held_out_truth_nrmse": nrmse,
                }
            )
        for evaluation in evaluations:
            summary_rows.append(
                {
                    "benchmark": benchmark_id,
                    "role": "optimized",
                    "seed": evaluation.seed,
                    "selected": evaluation.seed == best.seed,
                    "training_loss": evaluation.cost,
                    "held_out_truth_nrmse": evaluation.held_out_truth_nrmse,
                    "parameter_median_abs_relative_error": evaluation.parameter_median_error,
                    "parameter_max_abs_relative_error": evaluation.parameter_max_error,
                    "pass": evaluation.seed_pass,
                }
            )
            for row in evaluation.parameter_rows:
                parameter_rows.append({"benchmark": benchmark_id, **row})
            for window, nrmse in evaluation.held_out_window_truth_nrmse.items():
                window_rows.append(
                    {
                        "benchmark": benchmark_id,
                        "role": "optimized",
                        "seed": evaluation.seed,
                        "selected": evaluation.seed == best.seed,
                        "window": window,
                        "held_out_truth_nrmse": nrmse,
                    }
                )

        yaml_cases.append(
            {
                "benchmark": benchmark_id,
                "overall_pass": overall_pass,
                "initial_challenge_pass": initial_challenge_pass,
                "seed_pass_fraction": pass_fraction,
                "selected_seed": best.seed,
                "selection_rule": metadata["best_run_selection"],
                "initial": initial_metrics,
                "runs": [
                    {
                        "seed": item.seed,
                        "training_loss": item.cost,
                        "held_out_truth_nrmse": item.held_out_truth_nrmse,
                        "held_out_window_truth_nrmse": item.held_out_window_truth_nrmse,
                        "parameter_median_abs_relative_error": item.parameter_median_error,
                        "parameter_max_abs_relative_error": item.parameter_max_error,
                        "pass": item.seed_pass,
                    }
                    for item in evaluations
                ],
                "acceptance": acceptance,
            }
        )
        generated.append(
            _render_case(
                benchmark_id,
                metadata,
                solver,
                truth,
                evaluations,
                initial_metrics,
                overall_pass,
            )
        )
        print(
            f"{benchmark_id}: overall={'PASS' if overall_pass else 'FAIL'}, "
            f"selected_seed={best.seed}, seed_pass_fraction={pass_fraction:.3f}"
        )

    _write_csv(OUTPUT_DIR / "robustness_summary.csv", summary_rows)
    _write_csv(OUTPUT_DIR / "parameter_recovery.csv", parameter_rows)
    _write_csv(OUTPUT_DIR / "held_out_window_metrics.csv", window_rows)
    save_yaml(
        {
            "kind": "oescr_optimizer_robustness_results",
            "version": 2,
            "selection_policy": "minimum training objective; held-out data and truth excluded",
            "cases": yaml_cases,
        },
        OUTPUT_DIR / "robustness_summary.yaml",
    )
    for path in generated:
        print(path)


if __name__ == "__main__":
    main()
