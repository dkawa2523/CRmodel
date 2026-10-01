#!/usr/bin/env python
"""Run the Ar/O2 and Ar/Cl2 shared-electron-state validation cases.

The benchmark deliberately fits only one Maxwellian electron temperature and
one electron density shared by all line-resolved spectra in a gas case.  The
ordinary OESCR DE + least-squares result is cross-checked with CMA-ES without a
seed sweep.  These are synthetic same-model recovery tests, not a substitute
for external cross-section or plasma-diagnostic validation.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cma
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oescr.forward.model import OESCRModel
from oescr.inverse.objectives import residual_vector
from oescr.inverse.optimize import FitResult, InverseSolver
from oescr.io.pathmap import get_path
from oescr.io.yaml_loader import save_yaml
from oescr.physics.eedf import build_eedf_for_zone

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / ".local_outputs" / "common_state_benchmarks"
DEFAULT_FIGURES = REPO_ROOT / "docs" / "common-state-figures"
DEFAULT_REPORT = REPO_ROOT / "docs" / "common_state_benchmark.md"
MEASUREMENT_SEED = 20261002
CMA_SEED = 20261002


@dataclass(frozen=True)
class BenchmarkCase:
    key: str
    title: str
    directory: Path
    feature_labels: dict[str, str]
    independent_channels: int
    limitation: str

    @property
    def truth_path(self) -> Path:
        return self.directory / "case_truth.yaml"

    @property
    def init_path(self) -> Path:
        return self.directory / "case_init.yaml"

    @property
    def inverse_path(self) -> Path:
        return self.directory / "inverse.yaml"


CASES = (
    BenchmarkCase(
        key="ar_o2",
        title="Ar/O$_2$ common-state recovery",
        directory=REPO_ROOT / "examples" / "benchmarks" / "common_state_ar_o2",
        feature_labels={
            "ar750": "Ar I 750.4 nm",
            "ar763": "Ar I 763.5 nm",
            "o777": "O I 777.4 nm",
            "ar800": "Ar I 800.6 nm",
            "ar922": "Ar I 922.4 nm",
        },
        independent_channels=3,
        limitation="Ar branches share two upper states; O I 844.6 nm is not yet covered.",
    ),
    BenchmarkCase(
        key="ar_cl2",
        title="Ar/Cl$_2$ common-state recovery",
        directory=REPO_ROOT / "examples" / "benchmarks" / "common_state_ar_cl2",
        feature_labels={
            "cl725": "Cl I 725.7 nm",
            "ar750": "Ar I 750.4 nm",
            "cl755": "Cl I 754.7 nm",
            "ar763": "Ar I 763.5 nm",
            "ar800": "Ar I 800.6 nm",
            "cl822": "Cl I 822.2 nm",
            "ar922": "Ar I 922.4 nm",
        },
        independent_channels=5,
        limitation="The three Cl channels use literature-anchored effective-emitter curves, not state-resolved data.",
    ),
)


def _write_measurement(
    path: Path,
    wavelength_nm: np.ndarray,
    intensity: np.ndarray,
    sigma: np.ndarray,
    metadata: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        for key, value in metadata.items():
            stream.write(f"# {key}: {value}\n")
        writer = csv.writer(stream)
        writer.writerow(["wavelength_nm", "intensity", "sigma"])
        for wavelength, value, uncertainty in zip(wavelength_nm, intensity, sigma, strict=True):
            writer.writerow(
                [
                    f"{float(wavelength):.8f}",
                    f"{float(value):.12e}",
                    f"{float(uncertainty):.12e}",
                ]
            )


def generate_measurements(case: BenchmarkCase, rng: np.random.Generator) -> None:
    result = OESCRModel.from_yaml(case.truth_path).predict()
    for instrument_id, chord_map in result.spectra.items():
        spectrum = chord_map["chord_0"]
        wavelength = np.asarray(spectrum["wavelength_nm"], dtype=float)
        truth = np.asarray(spectrum["intensity"], dtype=float)
        peak = max(float(np.max(truth)), 1.0e-30)
        sigma = np.sqrt((0.015 * truth) ** 2 + (0.0015 * peak) ** 2)
        measured = truth + rng.normal(0.0, sigma)
        _write_measurement(
            case.directory / "measurements" / f"{instrument_id}.csv",
            wavelength,
            measured,
            sigma,
            {
                "output_basis": spectrum["output_basis"],
                "output_unit": spectrum["output_unit"],
                "calibration_reference": spectrum["calibration_reference"],
                "generator": "OESCR truth case with 1.5% point noise and 0.15% peak floor",
                "measurement_seed": MEASUREMENT_SEED,
            },
        )


def _case_from_vector(solver: InverseSolver, vector: np.ndarray) -> dict[str, Any]:
    cfg = deepcopy(solver.case_cfg)
    solver.params.apply_to_case(cfg, vector)
    return cfg


def _physical_parameters(solver: InverseSolver, vector: np.ndarray) -> dict[str, float]:
    return {
        parameter.name: parameter.from_opt(float(value))
        for parameter, value in zip(solver.params.params, vector, strict=True)
    }


def _objective(solver: InverseSolver, vector: np.ndarray) -> float:
    cfg = _case_from_vector(solver, vector)
    residual, _ = residual_vector(
        solver.model,
        cfg,
        solver.inv_cfg,
        solver.measurements,
        solver.windows,
    )
    return 0.5 * float(np.dot(residual, residual))


def run_cma_es(solver: InverseSolver) -> tuple[np.ndarray, list[dict[str, float]], str]:
    lower, upper = solver.params.bounds()
    scale = upper - lower
    initial = solver.params.initial_vector(solver.case_cfg)
    normalized_initial = np.clip((initial - lower) / scale, 0.0, 1.0)

    def decode(normalized: np.ndarray) -> np.ndarray:
        return lower + np.clip(np.asarray(normalized, dtype=float), 0.0, 1.0) * scale

    strategy = cma.CMAEvolutionStrategy(
        normalized_initial,
        0.22,
        {
            "bounds": [0.0, 1.0],
            "popsize": 12,
            "maxiter": 90,
            "seed": CMA_SEED,
            "tolfun": 1.0e-12,
            "tolx": 1.0e-10,
            "verbose": -9,
            "verb_disp": 0,
        },
    )
    trace: list[dict[str, float]] = []
    best_loss = float("inf")
    while not strategy.stop():
        candidates = strategy.ask()
        losses = [_objective(solver, decode(candidate)) for candidate in candidates]
        strategy.tell(candidates, losses)
        best_loss = min(best_loss, min(losses))
        trace.append(
            {
                "evaluation": float(strategy.countevals),
                "best_loss": best_loss,
            }
        )
    return decode(np.asarray(strategy.result.xbest, dtype=float)), trace, str(strategy.stop())


def _predictions(model: OESCRModel, cfg: dict[str, Any]) -> dict[str, dict[str, np.ndarray]]:
    result = model.predict(cfg)
    return {
        instrument_id: {
            "wavelength_nm": np.asarray(chords["chord_0"]["wavelength_nm"], dtype=float),
            "intensity": np.asarray(chords["chord_0"]["intensity"], dtype=float),
        }
        for instrument_id, chords in result.spectra.items()
    }


def _overview_spectrum(
    cfg: dict[str, Any],
    wavelength_min_nm: float,
    wavelength_max_nm: float,
) -> dict[str, np.ndarray]:
    overview_cfg = deepcopy(cfg)
    instrument = deepcopy(overview_cfg["instruments"][0])
    instrument.pop("wavelength_grid_nm", None)
    instrument.update(
        {
            "id": "conference_overview",
            "wavelength_min_nm": wavelength_min_nm,
            "wavelength_max_nm": wavelength_max_nm,
            "bin_nm": 0.1,
        }
    )
    overview_cfg["instruments"] = [instrument]
    spectrum = OESCRModel(overview_cfg).predict().spectra["conference_overview"]["chord_0"]
    return {
        "wavelength_nm": np.asarray(spectrum["wavelength_nm"], dtype=float),
        "intensity": np.asarray(spectrum["intensity"], dtype=float),
    }


def _measurement_arrays(solver: InverseSolver) -> dict[str, dict[str, np.ndarray]]:
    return {
        instrument_id: {
            "wavelength_nm": np.asarray(items[0].wavelength_nm, dtype=float),
            "intensity": np.asarray(items[0].intensity, dtype=float),
            "sigma": np.asarray(items[0].sigma, dtype=float),
        }
        for instrument_id, items in solver.measurements.items()
    }


def _aggregate_nrmse(
    prediction: dict[str, dict[str, np.ndarray]],
    reference: dict[str, dict[str, np.ndarray]],
) -> float:
    squared_error = 0.0
    squared_reference = 0.0
    for instrument_id, values in reference.items():
        predicted = np.interp(
            values["wavelength_nm"],
            prediction[instrument_id]["wavelength_nm"],
            prediction[instrument_id]["intensity"],
        )
        squared_error += float(np.sum((predicted - values["intensity"]) ** 2))
        squared_reference += float(np.sum(values["intensity"] ** 2))
    return float(np.sqrt(squared_error / max(squared_reference, 1.0e-300)))


def _max_spectrum_relative_l2(
    coarse: dict[str, dict[str, np.ndarray]],
    refined: dict[str, dict[str, np.ndarray]],
) -> float:
    values = []
    for instrument_id, spectrum in coarse.items():
        ref = refined[instrument_id]["intensity"]
        base = spectrum["intensity"]
        values.append(float(np.linalg.norm(ref - base) / max(np.linalg.norm(ref), 1.0e-300)))
    return max(values)


def _eedf_metrics(
    truth_cfg: dict[str, Any],
    configs: dict[str, dict[str, Any]],
) -> tuple[np.ndarray, dict[str, np.ndarray], dict[str, float]]:
    grid = np.linspace(0.0, 30.0, 601)
    curves = {"truth": build_eedf_for_zone(truth_cfg, 0, grid)}
    errors: dict[str, float] = {}
    for name, cfg in configs.items():
        curve = build_eedf_for_zone(cfg, 0, grid)
        curves[name] = curve
        errors[name] = float(np.trapezoid(np.abs(curve - curves["truth"]), grid))
    return grid, curves, errors


def _best_so_far(trace: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    evaluations = np.asarray([float(item["evaluation"]) for item in trace], dtype=float)
    loss_key = "best_loss" if "best_loss" in trace[0] else "loss"
    losses = np.asarray([float(item[loss_key]) for item in trace], dtype=float)
    return evaluations, np.minimum.accumulate(losses)


def _concatenate_measurements(
    measurements: dict[str, dict[str, np.ndarray]],
    instrument_ids: list[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    wavelength = np.concatenate([measurements[item]["wavelength_nm"] for item in instrument_ids])
    intensity = np.concatenate([measurements[item]["intensity"] for item in instrument_ids])
    sigma = np.concatenate([measurements[item]["sigma"] for item in instrument_ids])
    order = np.argsort(wavelength)
    return wavelength[order], intensity[order], sigma[order]


def _annotate_spectral_features(
    axis: Any,
    case: BenchmarkCase,
    predictions: dict[str, dict[str, dict[str, np.ndarray]]],
) -> None:
    for instrument_id, label in case.feature_labels.items():
        line = predictions["truth"][instrument_id]
        peak_index = int(np.argmax(line["intensity"]))
        axis.annotate(
            label.replace(" nm", ""),
            xy=(float(line["wavelength_nm"][peak_index]), float(line["intensity"][peak_index])),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center",
            va="bottom",
            rotation=90,
            fontsize=8,
            color="#333333",
            clip_on=False,
        )


def _save_conference_figure(figure: Any, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=300, bbox_inches="tight")
    svg_path = output_path.with_suffix(".svg")
    figure.savefig(svg_path, bbox_inches="tight")
    svg_text = svg_path.read_text(encoding="utf-8")
    svg_path.write_text(
        "\n".join(line.rstrip() for line in svg_text.splitlines()) + "\n",
        encoding="utf-8",
    )


def render_spectra(
    case: BenchmarkCase,
    measurements: dict[str, dict[str, np.ndarray]],
    predictions: dict[str, dict[str, dict[str, np.ndarray]]],
    configs: dict[str, dict[str, Any]],
    output_path: Path,
) -> None:
    instrument_ids = list(case.feature_labels)
    wavelength_min = min(float(np.min(measurements[item]["wavelength_nm"])) for item in instrument_ids)
    wavelength_max = max(float(np.max(measurements[item]["wavelength_nm"])) for item in instrument_ids)
    overview = {
        name: _overview_spectrum(cfg, wavelength_min, wavelength_max)
        for name, cfg in configs.items()
    }
    colors = {"truth": "black", "initial": "#d95f02", "oescr": "#0072b2", "cma": "#009e73"}
    styles = {"truth": ":", "initial": "--", "oescr": "-", "cma": "-."}
    labels = {"truth": "Truth", "initial": "Initial", "oescr": "DE + LSQ", "cma": "CMA-ES"}

    with plt.rc_context(
        {
            "font.size": 10,
            "axes.labelsize": 11,
            "axes.titlesize": 12,
            "legend.fontsize": 9,
            "xtick.direction": "in",
            "ytick.direction": "in",
            "xtick.top": True,
            "ytick.right": True,
            "axes.linewidth": 1.1,
            "xtick.major.width": 1.0,
            "ytick.major.width": 1.0,
        }
    ):
        figure, (spectrum_axis, residual_axis) = plt.subplots(
            2,
            1,
            figsize=(11.5, 5.8),
            sharex=True,
            constrained_layout=True,
            gridspec_kw={"height_ratios": [3.5, 1.0], "hspace": 0.08},
        )
        for name in ("truth", "initial", "oescr", "cma"):
            spectrum_axis.plot(
                overview[name]["wavelength_nm"],
                overview[name]["intensity"],
                styles[name],
                color=colors[name],
                linewidth=2.8 if name in {"oescr", "cma"} else 2.3,
                label=labels[name],
                zorder=3 if name in {"oescr", "cma"} else 2,
            )

        measurement_wavelength, measurement_intensity, measurement_sigma = _concatenate_measurements(
            measurements,
            instrument_ids,
        )
        spectrum_axis.errorbar(
            measurement_wavelength,
            measurement_intensity,
            yerr=measurement_sigma,
            fmt="o",
            markersize=4.0,
            markerfacecolor="#666666",
            markeredgewidth=0.0,
            ecolor="#9a9a9a",
            elinewidth=0.9,
            alpha=0.82,
            label="Synthetic measurement",
            zorder=4,
        )

        case_peak = max(float(np.max(overview["truth"]["intensity"])), 1.0e-30)
        _annotate_spectral_features(spectrum_axis, case, predictions)

        fitted_at_measurement = np.interp(
            measurement_wavelength,
            overview["oescr"]["wavelength_nm"],
            overview["oescr"]["intensity"],
        )
        standardized_residual = (measurement_intensity - fitted_at_measurement) / measurement_sigma
        residual_axis.axhspan(-2.0, 2.0, color="#0072b2", alpha=0.08, linewidth=0.0)
        residual_axis.axhline(0.0, color="black", linewidth=1.1)
        residual_axis.scatter(
            measurement_wavelength,
            standardized_residual,
            s=18,
            color="#555555",
            alpha=0.82,
            edgecolors="none",
        )
        residual_axis.set_ylim(-4.0, 4.0)
        residual_axis.set_yticks([-4, -2, 0, 2, 4])
        residual_axis.set_ylabel(r"Residual / $\sigma$")
        residual_axis.set_xlabel("Wavelength (nm)")

        spectrum_axis.set_xlim(wavelength_min, wavelength_max)
        spectrum_axis.set_ylim(-0.025 * case_peak, 1.23 * case_peak)
        spectrum_axis.set_ylabel("Spectral radiance (W m$^{-2}$ sr$^{-1}$ nm$^{-1}$)")
        spectrum_axis.set_title(
            f"{case.title} — {len(instrument_ids)} spectra, "
            f"{case.independent_channels} independent excitation channels"
        )
        spectrum_axis.legend(
            loc="upper right",
            bbox_to_anchor=(0.995, 0.985),
            ncol=1,
            frameon=False,
        )
        spectrum_axis.grid(axis="y", alpha=0.16, linewidth=0.6)
        residual_axis.grid(axis="y", alpha=0.16, linewidth=0.6)
        figure.align_ylabels((spectrum_axis, residual_axis))
    _save_conference_figure(figure, output_path)
    plt.close(figure)


def render_recovery(
    case: BenchmarkCase,
    parameters: dict[str, dict[str, float]],
    energy: np.ndarray,
    eedf_curves: dict[str, np.ndarray],
    oescr_trace: list[dict[str, Any]],
    cma_trace: list[dict[str, Any]],
    output_path: Path,
) -> None:
    labels = ["Truth", "Initial", "DE + LSQ", "CMA-ES"]
    keys = ["truth", "initial", "oescr", "cma"]
    colors = ["black", "#d95f02", "#0072b2", "#009e73"]
    styles = [":", "--", "-", "-."]

    with plt.rc_context(
        {
            "font.size": 10,
            "axes.labelsize": 11,
            "axes.titlesize": 12,
            "legend.fontsize": 9,
            "xtick.direction": "in",
            "ytick.direction": "in",
            "xtick.top": True,
            "ytick.right": True,
            "axes.linewidth": 1.1,
            "xtick.major.width": 1.0,
            "ytick.major.width": 1.0,
        }
    ):
        figure, axes = plt.subplots(2, 2, figsize=(10.8, 7.2), constrained_layout=True)
        te_values = [parameters[key]["electron_temperature_eV"] for key in keys]
        ne_values = [parameters[key]["electron_density_m3"] / 1.0e16 for key in keys]
        te_bars = axes[0, 0].bar(labels, te_values, color=colors, width=0.72)
        axes[0, 0].bar_label(te_bars, labels=[f"{value:.2f}" for value in te_values], padding=3, fontsize=9)
        axes[0, 0].set_ylim(0.0, 1.16 * max(te_values))
        axes[0, 0].set_ylabel("Electron temperature $T_e$ (eV)")
        axes[0, 0].set_title("Common electron temperature")
        axes[0, 0].grid(axis="y", alpha=0.16, linewidth=0.6)

        ne_bars = axes[0, 1].bar(labels, ne_values, color=colors, width=0.72)
        axes[0, 1].bar_label(ne_bars, labels=[f"{value:.2f}" for value in ne_values], padding=3, fontsize=9)
        axes[0, 1].set_ylim(0.0, 1.16 * max(ne_values))
        axes[0, 1].set_ylabel("Electron density $n_e$ ($10^{16}$ m$^{-3}$)")
        axes[0, 1].set_title("Common electron density")
        axes[0, 1].grid(axis="y", alpha=0.16, linewidth=0.6)

        for key, label, color, style in zip(keys, labels, colors, styles, strict=True):
            axes[1, 0].semilogy(
                energy,
                np.maximum(eedf_curves[key], 1.0e-12),
                style,
                color=color,
                linewidth=2.6,
                label=label,
            )
        axes[1, 0].set_xlim(0.0, 30.0)
        axes[1, 0].set_ylim(1.0e-8, 4.0e-1)
        axes[1, 0].set_xlabel("Electron energy (eV)")
        axes[1, 0].set_ylabel("Normalized Maxwellian EEDF (eV$^{-1}$)")
        axes[1, 0].set_title("Parametric EEDF recovery")
        axes[1, 0].grid(alpha=0.16, linewidth=0.6)
        axes[1, 0].legend(frameon=False)

        de_x, de_y = _best_so_far(oescr_trace)
        cma_x, cma_y = _best_so_far(cma_trace)
        axes[1, 1].semilogy(
            de_x + 1.0,
            np.maximum(de_y, 1.0e-16),
            color="#0072b2",
            linewidth=2.6,
            label="DE + LSQ",
        )
        axes[1, 1].semilogy(
            cma_x,
            np.maximum(cma_y, 1.0e-16),
            color="#009e73",
            linewidth=2.6,
            label="CMA-ES",
        )
        axes[1, 1].set_xlabel("Objective evaluations")
        axes[1, 1].set_ylabel("Best loss so far")
        axes[1, 1].set_title("Optimizer convergence")
        axes[1, 1].grid(alpha=0.16, linewidth=0.6)
        axes[1, 1].legend(frameon=False)

        for axis, panel in zip(axes.flat, ("(a)", "(b)", "(c)", "(d)"), strict=True):
            axis.text(-0.11, 1.04, panel, transform=axis.transAxes, fontweight="bold", va="bottom")
        figure.suptitle(case.title, fontsize=14)
    _save_conference_figure(figure, output_path)
    plt.close(figure)


def _relative_parameter_errors(
    parameters: dict[str, dict[str, float]],
    eedf_errors: dict[str, float],
) -> dict[str, dict[str, float]]:
    truth = parameters["truth"]
    errors: dict[str, dict[str, float]] = {}
    for name in ("initial", "oescr", "cma"):
        values = parameters[name]
        errors[name] = {
            "te_relative": abs(values["electron_temperature_eV"] - truth["electron_temperature_eV"])
            / truth["electron_temperature_eV"],
            "ne_relative": abs(values["electron_density_m3"] - truth["electron_density_m3"])
            / truth["electron_density_m3"],
            "eedf_l1": eedf_errors[name],
        }
    return errors


def _passes_acceptance_gate(
    *,
    fit_success: bool,
    full_rank: bool,
    errors: dict[str, dict[str, float]],
    numerical_difference: float,
) -> bool:
    return all(
        (
            fit_success,
            full_rank,
            errors["oescr"]["te_relative"] < 0.05,
            errors["oescr"]["ne_relative"] < 0.05,
            errors["cma"]["te_relative"] < 0.05,
            errors["cma"]["ne_relative"] < 0.05,
            numerical_difference < 0.01,
        )
    )


def _write_case_outputs(
    case_output: Path,
    result: dict[str, Any],
    fit: FitResult,
    cma_vector: np.ndarray,
    cma_trace: list[dict[str, float]],
    cma_stop: str,
    cma_case: dict[str, Any],
) -> None:
    case_output.mkdir(parents=True, exist_ok=True)
    (case_output / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    save_yaml(fit.case_opt, case_output / "case_opt_oescr.yaml")
    save_yaml(cma_case, case_output / "case_opt_cma.yaml")
    save_yaml(
        {
            "success": fit.success,
            "message": fit.message,
            "cost": fit.cost,
            "x_opt": fit.x_opt.tolist(),
            "identifiability": fit.identifiability,
            "uncertainty": fit.uncertainty,
            "assessment": fit.assessment,
            "optimization_trace": fit.optimization_trace,
        },
        case_output / "fit_oescr.yaml",
    )
    save_yaml({"x_opt": cma_vector.tolist(), "trace": cma_trace, "stop": cma_stop}, case_output / "fit_cma.yaml")


def run_case(case: BenchmarkCase, output_dir: Path, figure_dir: Path) -> dict[str, Any]:
    solver = InverseSolver.from_yaml(case.init_path, case.inverse_path)
    truth_cfg = OESCRModel.from_yaml(case.truth_path).cfg
    initial_vector = solver.params.initial_vector(solver.case_cfg)
    fit = solver.fit(record_trace=True)
    cma_vector, cma_trace, cma_stop = run_cma_es(solver)

    configs = {
        "truth": truth_cfg,
        "initial": solver.case_cfg,
        "oescr": fit.case_opt,
        "cma": _case_from_vector(solver, cma_vector),
    }
    predictions = {name: _predictions(solver.model, cfg) for name, cfg in configs.items()}
    measurements = _measurement_arrays(solver)
    parameter_vectors = {
        "truth": {
            "electron_temperature_eV": float(get_path(truth_cfg, "plasma_state.te_shells_eV[0]")),
            "electron_density_m3": float(get_path(truth_cfg, "plasma_state.ne_shells_m3[0]")),
        },
        "initial": _physical_parameters(solver, initial_vector),
        "oescr": _physical_parameters(solver, fit.x_opt),
        "cma": _physical_parameters(solver, cma_vector),
    }
    energy, eedf_curves, eedf_errors = _eedf_metrics(
        truth_cfg,
        {name: configs[name] for name in ("initial", "oescr", "cma")},
    )

    energy_refined_cfg = deepcopy(truth_cfg)
    energy_refined_cfg["energy_grid"]["n_points"] = 1201
    energy_refined = _predictions(OESCRModel(energy_refined_cfg), energy_refined_cfg)
    energy_difference = _max_spectrum_relative_l2(predictions["truth"], energy_refined)

    wavelength_refined_cfg = deepcopy(truth_cfg)
    wavelength_refined_cfg.setdefault("numerics", {})["wavelength_refinement_factor"] = 2.0
    wavelength_refined = _predictions(OESCRModel(wavelength_refined_cfg), wavelength_refined_cfg)
    wavelength_difference = _max_spectrum_relative_l2(predictions["truth"], wavelength_refined)
    numerical_difference = max(energy_difference, wavelength_difference)

    errors = _relative_parameter_errors(parameter_vectors, eedf_errors)
    spectral_nrmse = {
        name: _aggregate_nrmse(predictions[name], measurements)
        for name in ("initial", "oescr", "cma")
    }
    full_rank = bool(
        fit.identifiability
        and fit.identifiability["rank_estimate"] == fit.identifiability["n_parameters"]
    )
    passed = _passes_acceptance_gate(
        fit_success=fit.success,
        full_rank=full_rank,
        errors=errors,
        numerical_difference=numerical_difference,
    )
    result = {
        "case": case.key,
        "status": "pass" if passed else "fail",
        "interpretation": "synthetic_same_model_recovery",
        "observed_spectra": len(case.feature_labels),
        "independent_excitation_channels": case.independent_channels,
        "measurement_seed": MEASUREMENT_SEED,
        "cma_seed": CMA_SEED,
        "parameters": parameter_vectors,
        "relative_errors": errors,
        "spectral_nrmse_vs_noisy_measurement": spectral_nrmse,
        "objective": {"oescr": fit.cost, "cma": _objective(solver, cma_vector)},
        "identifiability": fit.identifiability,
        "numerical_refinement_max_relative_l2": numerical_difference,
        "numerical_refinement": {
            "energy_grid_max_relative_l2": energy_difference,
            "wavelength_grid_max_relative_l2": wavelength_difference,
        },
        "forward_quality": OESCRModel(truth_cfg).predict().quality_report.as_dict(),
        "cma_stop": cma_stop,
        "limitation": case.limitation,
    }

    _write_case_outputs(
        output_dir / case.key,
        result,
        fit,
        cma_vector,
        cma_trace,
        cma_stop,
        configs["cma"],
    )

    render_spectra(case, measurements, predictions, configs, figure_dir / f"{case.key}_spectral_fit.png")
    render_recovery(
        case,
        parameter_vectors,
        energy,
        eedf_curves,
        fit.optimization_trace or [],
        cma_trace,
        figure_dir / f"{case.key}_recovery.png",
    )
    return result


def _percent(value: float) -> str:
    return f"{100.0 * value:.2f}%"


def write_report(results: list[dict[str, Any]], path: Path, figure_dir: Path) -> None:
    lines = [
        "# Ar/O2・Ar/Cl2 共通電子状態ベンチマーク",
        "",
        "## 結論",
        "",
        "本検証では、同一プラズマ条件で得た複数の線分解スペクトルを同時に用い、全スペクトルに共通する電子温度 `Te` と電子密度 `ne` を推定した。既存の differential evolution + least-squares（DE + LSQ）と、独立実装の CMA-ES を同じ目的関数に適用した。判定はパラメータ誤差 5% 未満、測定データだけの局所ヤコビアンがフルランク、数値格子精密化差 1% 未満である。",
        "",
        "これは**同じ前進モデルで生成・逆解析する自己整合性検証**であり、断面積や実プラズマに対する外部物理検証ではない。EEDF は自由関数として復元せず、推定 `Te` から定まる Maxwell EEDF の回収を評価する。",
        "",
        "## 問題設定",
        "",
        "| ケース | 観測スペクトル | 独立励起チャネル | 真値 `(Te, ne)` | 初期値 `(Te, ne)` |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in results:
        truth = item["parameters"]["truth"]
        initial = item["parameters"]["initial"]
        lines.append(
            f"| {item['case']} | {item['observed_spectra']} | {item['independent_excitation_channels']} | "
            f"({truth['electron_temperature_eV']:.2f} eV, {truth['electron_density_m3']:.3e} m^-3) | "
            f"({initial['electron_temperature_eV']:.2f} eV, {initial['electron_density_m3']:.3e} m^-3) |"
        )
    lines.extend(
        [
            "",
            "初期値は `Te` を真値より 20% 低く、`ne` を 50% 高く設定した。したがって初期スペクトルは真値と明確に異なるが、探索範囲端の非現実的な遠方点ではない。乱数 seed の変更比較は行わず、測定ノイズと CMA-ES にそれぞれ固定 seed を一つだけ用いた。",
            "",
            "Ar/O2 は Ar I 750.4, 763.5, 800.6, 922.4 nm と O I 777.4 nm の5スペクトルを使う。ただし Ar の4線は2上準位からの分岐なので、独立励起情報は Ar 2 + O 1 = 3チャネルである。",
            "",
            "Ar/Cl2 は上記 Ar 4線と Cl I 725.7, 754.7, 822.2 nm の7スペクトルを使い、独立励起情報は Ar 2 + Cl 3 = 5チャネルである。Cl 822.2 nm は Cl2 解離励起干渉チャネルとして分離した。",
            "",
            "## 結果",
            "",
            "| ケース | 手法 | Te 誤差 | ne 誤差 | EEDF L1 誤差 | スペクトル NRMSE | loss | 識別ランク | 格子精密化差 | 判定 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for item in results:
        rank = item["identifiability"]
        for method, label in (("oescr", "DE + LSQ"), ("cma", "CMA-ES")):
            error = item["relative_errors"][method]
            lines.append(
                f"| {item['case']} | {label} | {_percent(error['te_relative'])} | "
                f"{_percent(error['ne_relative'])} | {_percent(error['eedf_l1'])} | "
                f"{_percent(item['spectral_nrmse_vs_noisy_measurement'][method])} | "
                f"{item['objective'][method]:.4g} | {rank['rank_estimate']}/{rank['n_parameters']} | "
                f"{_percent(item['numerical_refinement_max_relative_l2'])} | {item['status']} |"
            )
    lines.extend(
        [
            "",
            "スペクトル NRMSE はノイズを含む測定値との差であり、ゼロを目標にしていない。EEDF L1 誤差は 0–30 eV で正規化 EEDF の絶対差を積分した値である。格子精密化差はエネルギー点数を 601→1201、波長内部格子を2倍にしたときの最大スペクトル相対 L2 差である。",
            "",
            "## 図",
            "",
            "スペクトル比較は個別線パネルではなく、全診断波長域を同一の物理波長軸・絶対放射輝度軸で重ねた。下段は各測定点の標準化残差で、淡青帯は ±2 sigma を示す。PNG に加えて学会原稿・ポスター編集用のベクター SVG も同じディレクトリへ出力する。",
            "",
            f"![Ar/O2 spectral fit](common-state-figures/{figure_dir.joinpath('ar_o2_spectral_fit.png').name})",
            "",
            "[Ar/O2 spectral fit (SVG)](common-state-figures/ar_o2_spectral_fit.svg)",
            "",
            f"![Ar/O2 recovery](common-state-figures/{figure_dir.joinpath('ar_o2_recovery.png').name})",
            "",
            "[Ar/O2 recovery (SVG)](common-state-figures/ar_o2_recovery.svg)",
            "",
            f"![Ar/Cl2 spectral fit](common-state-figures/{figure_dir.joinpath('ar_cl2_spectral_fit.png').name})",
            "",
            "[Ar/Cl2 spectral fit (SVG)](common-state-figures/ar_cl2_spectral_fit.svg)",
            "",
            f"![Ar/Cl2 recovery](common-state-figures/{figure_dir.joinpath('ar_cl2_recovery.png').name})",
            "",
            "[Ar/Cl2 recovery (SVG)](common-state-figures/ar_cl2_recovery.svg)",
            "",
            "## 妥当性の解釈と限界",
            "",
            "- 複数スペクトルを一つの `Te・ne` で同時説明でき、異なる最適化法が同じ解へ到達すれば、共通状態の連携計算と局所最適解依存の回避は確認できる。",
            "- Ar の複数分岐線は観測点を増やすが、励起断面積の独立情報数を増やさない。本表では観測線数と独立チャネル数を分けた。",
            "- Ar/O2 の O I 844.6 nm は現行モデルに断面積・上準位がないため追加していない。存在しない物理データを補間して線数を増やすことは避けた。",
            "- Ar/Cl2 の3曲線は literature-anchored effective-emitter fit である。このケースは逆問題の有用性を検証するが、Cl 原子素過程の絶対精度を保証しない。外部測定または状態分解断面積による置換が次の物理検証である。",
            "- `ne` の回収には絶対校正、視線長、Ar/O/Cl 密度が既知という前提がある。相対スペクトルだけの場合、`ne` と発光種密度・装置 gain は分離できない。",
            "",
            "## 再実行",
            "",
            "```powershell",
            ".\\.venv\\Scripts\\python.exe scripts\\run_common_state_benchmarks.py",
            "```",
            "",
            f"固定 seed: measurement={MEASUREMENT_SEED}, CMA-ES={CMA_SEED}。seed sweep は実施しない。",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--figures", type=Path, default=DEFAULT_FIGURES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    rng = np.random.default_rng(MEASUREMENT_SEED)
    for case in CASES:
        generate_measurements(case, rng)
    results = [run_case(case, args.output, args.figures) for case in CASES]
    write_report(results, args.report, args.figures)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
