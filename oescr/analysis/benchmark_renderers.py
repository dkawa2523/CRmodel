"""Small dependency-free SVG/text primitives for benchmark reports."""

from __future__ import annotations

import csv
import html
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np

PLOT_COLORS = {
    "measurement": "#111827",
    "init": "#9ca3af",
    "opt": "#2563eb",
    "truth": "#d97706",
    "area": "#2563eb",
    "peak": "#d97706",
    "shift": "#059669",
    "grid": "#e5e7eb",
    "axis": "#374151",
    "window": "#f3f4f6",
}


def xml_escape(text: Any) -> str:
    return html.escape(str(text), quote=True)


def format_tick(value: float) -> str:
    if value == 0.0:
        return "0"
    absolute = abs(value)
    if absolute >= 1.0e4 or absolute < 1.0e-2:
        return f"{value:.1e}"
    if absolute >= 100.0:
        return f"{value:.0f}"
    if absolute >= 10.0:
        return f"{value:.1f}"
    return f"{value:.2f}"


def linear_ticks(minimum: float, maximum: float, count: int = 5) -> List[float]:
    if not math.isfinite(minimum) or not math.isfinite(maximum):
        return [0.0, 1.0]
    if math.isclose(minimum, maximum):
        return [minimum - 1.0, minimum, minimum + 1.0]
    return [float(value) for value in np.linspace(minimum, maximum, count)]


def extent(
    values: List[np.ndarray],
    pad_fraction: float = 0.05,
    include_zero: bool = False,
) -> Tuple[float, float]:
    array = np.concatenate([np.asarray(value, dtype=float).ravel() for value in values if len(value) > 0])
    minimum = float(np.min(array))
    maximum = float(np.max(array))
    if include_zero:
        minimum = min(minimum, 0.0)
        maximum = max(maximum, 0.0)
    if math.isclose(minimum, maximum):
        delta = max(abs(minimum) * 0.1, 1.0)
        return minimum - delta, maximum + delta
    padding = (maximum - minimum) * pad_fraction
    return minimum - padding, maximum + padding


def downsample_xy(
    x_values: np.ndarray,
    y_values: np.ndarray,
    max_points: int = 1600,
) -> Tuple[np.ndarray, np.ndarray]:
    if len(x_values) <= max_points:
        return x_values, y_values
    indices = np.linspace(0, len(x_values) - 1, max_points).astype(int)
    return x_values[indices], y_values[indices]


def polyline_points(
    x_values: np.ndarray,
    y_values: np.ndarray,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    left: float,
    top: float,
    width: float,
    height: float,
) -> str:
    x_use, y_use = downsample_xy(
        np.asarray(x_values, dtype=float),
        np.asarray(y_values, dtype=float),
    )
    x_range = max(xmax - xmin, 1.0e-30)
    y_range = max(ymax - ymin, 1.0e-30)
    points = []
    for x_value, y_value in zip(x_use, y_use, strict=True):
        screen_x = left + (float(x_value) - xmin) / x_range * width
        screen_y = top + height - (float(y_value) - ymin) / y_range * height
        points.append(f"{screen_x:.2f},{screen_y:.2f}")
    return " ".join(points)


def draw_axes(
    lines: List[str],
    left: float,
    top: float,
    width: float,
    height: float,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    x_label: str,
    y_label: str,
    show_x_ticks: bool = True,
) -> None:
    lines.append(
        f'<rect x="{left:.1f}" y="{top:.1f}" width="{width:.1f}" height="{height:.1f}" '
        f'fill="white" stroke="{PLOT_COLORS["axis"]}" stroke-width="1"/>'
    )
    for tick in linear_ticks(ymin, ymax, 5):
        screen_y = top + height - (tick - ymin) / max(ymax - ymin, 1.0e-30) * height
        lines.append(
            f'<line x1="{left:.1f}" y1="{screen_y:.1f}" x2="{left + width:.1f}" '
            f'y2="{screen_y:.1f}" stroke="{PLOT_COLORS["grid"]}" stroke-width="1"/>'
        )
        lines.append(
            f'<text x="{left - 8:.1f}" y="{screen_y + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="{PLOT_COLORS["axis"]}">{xml_escape(format_tick(tick))}</text>'
        )
    if show_x_ticks:
        for tick in linear_ticks(xmin, xmax, 6):
            screen_x = left + (tick - xmin) / max(xmax - xmin, 1.0e-30) * width
            lines.append(
                f'<line x1="{screen_x:.1f}" y1="{top:.1f}" x2="{screen_x:.1f}" '
                f'y2="{top + height:.1f}" stroke="{PLOT_COLORS["grid"]}" stroke-width="1"/>'
            )
            lines.append(
                f'<text x="{screen_x:.1f}" y="{top + height + 16:.1f}" text-anchor="middle" '
                f'font-size="11" fill="{PLOT_COLORS["axis"]}">{xml_escape(format_tick(tick))}</text>'
            )
    lines.append(
        f'<text x="{left + width / 2:.1f}" y="{top + height + 34:.1f}" text-anchor="middle" '
        f'font-size="12" fill="{PLOT_COLORS["axis"]}">{xml_escape(x_label)}</text>'
    )
    lines.append(
        f'<text x="{left - 46:.1f}" y="{top - 8:.1f}" text-anchor="start" '
        f'font-size="12" fill="{PLOT_COLORS["axis"]}">{xml_escape(y_label)}</text>'
    )


def svg_document(width: int, height: int, title: str, body: List[str]) -> str:
    head = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        "<style>",
        "text { font-family: Arial, sans-serif; }",
        "</style>",
        f'<rect width="{width}" height="{height}" fill="white"/>',
        f'<text x="24" y="30" font-size="22" font-weight="700" fill="#111827">'
        f"{xml_escape(title)}</text>",
    ]
    return "\n".join(head + body + ["</svg>"])


def write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_chord_comparison_csv(
    out_dir: Path,
    inst_id: str,
    chord_key: str,
    scenarios: Dict[str, Dict[str, Any]],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{inst_id}_{chord_key}_comparison.csv"

    init_series = scenarios["init"]["comparison_series"][(inst_id, chord_key)]
    opt_series = scenarios["opt"]["comparison_series"][(inst_id, chord_key)]
    truth_series = scenarios["truth"]["comparison_series"][(inst_id, chord_key)]

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "wavelength_nm",
                "measurement",
                "init_raw",
                "init_fit",
                "opt_raw",
                "opt_fit",
                "truth_raw",
                "truth_fit",
            ]
        )
        for idx, wl in enumerate(init_series.wavelength_nm):
            writer.writerow(
                [
                    f"{wl:.8f}",
                    f"{init_series.measurement[idx]:.12e}",
                    f"{init_series.prediction_raw[idx]:.12e}",
                    f"{init_series.prediction_fit[idx]:.12e}",
                    f"{opt_series.prediction_raw[idx]:.12e}",
                    f"{opt_series.prediction_fit[idx]:.12e}",
                    f"{truth_series.prediction_raw[idx]:.12e}",
                    f"{truth_series.prediction_fit[idx]:.12e}",
                ]
            )


def write_flat_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def write_spectra_overview_svg(
    path: Path,
    benchmark_title: str,
    inst_id: str,
    scenarios: Dict[str, Dict[str, Any]],
) -> None:
    chord_keys = sorted(
        chord_key
        for plot_inst_id, chord_key in scenarios["opt"]["comparison_series"].keys()
        if plot_inst_id == inst_id
    )
    panel_height = 150
    width = 1300
    height = 110 + len(chord_keys) * (panel_height + 35)
    left = 90.0
    plot_width = 1160.0

    body: List[str] = []
    body.append(f'<text x="24" y="56" font-size="14" fill="#4b5563">{xml_escape(benchmark_title)} / {inst_id}</text>')

    legend_items = [
        ("Measurement", PLOT_COLORS["measurement"], ""),
        ("Init fit", PLOT_COLORS["init"], ' stroke-dasharray="6,4"'),
        ("Opt fit", PLOT_COLORS["opt"], ""),
        ("Truth fit", PLOT_COLORS["truth"], ' stroke-dasharray="2,3"'),
    ]
    lx = 24.0
    ly = 78.0
    for label, color, dash in legend_items:
        body.append(f'<line x1="{lx:.1f}" y1="{ly:.1f}" x2="{lx + 28:.1f}" y2="{ly:.1f}" stroke="{color}" stroke-width="3"{dash}/>')
        body.append(f'<text x="{lx + 36:.1f}" y="{ly + 4:.1f}" font-size="12" fill="#374151">{xml_escape(label)}</text>')
        lx += 160.0

    for idx, chord_key in enumerate(chord_keys):
        top = 100.0 + idx * (panel_height + 35.0)
        init_series = scenarios["init"]["comparison_series"][(inst_id, chord_key)]
        opt_series = scenarios["opt"]["comparison_series"][(inst_id, chord_key)]
        truth_series = scenarios["truth"]["comparison_series"][(inst_id, chord_key)]
        x = init_series.wavelength_nm
        y_arrays = [
            init_series.measurement,
            init_series.prediction_fit,
            opt_series.prediction_fit,
            truth_series.prediction_fit,
        ]
        xmin, xmax = float(np.min(x)), float(np.max(x))
        ymin, ymax = extent(y_arrays, pad_fraction=0.05, include_zero=False)

        draw_axes(body, left, top, plot_width, panel_height, xmin, xmax, ymin, ymax, "Wavelength (nm)", "Intensity", show_x_ticks=True)
        body.append(f'<text x="{left:.1f}" y="{top - 14:.1f}" font-size="13" font-weight="700" fill="#111827">{xml_escape(chord_key)}</text>')

        series_specs = [
            (init_series.measurement, PLOT_COLORS["measurement"], "", 2.0),
            (init_series.prediction_fit, PLOT_COLORS["init"], ' stroke-dasharray="6,4"', 1.8),
            (opt_series.prediction_fit, PLOT_COLORS["opt"], "", 2.1),
            (truth_series.prediction_fit, PLOT_COLORS["truth"], ' stroke-dasharray="2,3"', 1.8),
        ]
        for y, color, dash, stroke_width in series_specs:
            points = polyline_points(x, y, xmin, xmax, ymin, ymax, left, top, plot_width, panel_height)
            body.append(f'<polyline fill="none" stroke="{color}" stroke-width="{stroke_width}"{dash} points="{points}"/>')

    write_text_file(path, svg_document(width, height, f"Spectral Overlays: {inst_id}", body))


def write_fit_quality_svg(
    path: Path,
    benchmark_title: str,
    scenario_rows: List[Dict[str, Any]],
    chord_rows: List[Dict[str, Any]],
) -> None:
    width = 1200
    height = 940
    body: List[str] = []
    body.append(f'<text x="24" y="56" font-size="14" fill="#4b5563">{xml_escape(benchmark_title)}</text>')

    scenarios_order = ["init", "opt", "truth"]
    scenario_map = {row["scenario"]: row for row in scenario_rows}

    # Panel 1: scenario cost
    left = 90.0
    top = 90.0
    plot_width = 420.0
    plot_height = 220.0
    cost_values = [float(scenario_map[name]["cost"]) for name in scenarios_order]
    ymin, ymax = extent([np.asarray(cost_values, dtype=float)], pad_fraction=0.1, include_zero=False)
    draw_axes(body, left, top, plot_width, plot_height, -0.5, 2.5, ymin, ymax, "Scenario", "Cost", show_x_ticks=False)
    bar_width = plot_width / 6.0
    for idx, name in enumerate(scenarios_order):
        sx = left + (idx + 0.5) / 3.0 * plot_width - bar_width / 2.0
        sy = top + plot_height - (cost_values[idx] - ymin) / max(ymax - ymin, 1.0e-30) * plot_height
        body.append(f'<rect x="{sx:.1f}" y="{sy:.1f}" width="{bar_width:.1f}" height="{top + plot_height - sy:.1f}" fill="{PLOT_COLORS.get(name, "#2563eb")}"/>')
        body.append(f'<text x="{sx + bar_width / 2:.1f}" y="{top + plot_height + 18:.1f}" text-anchor="middle" font-size="12" fill="#374151">{xml_escape(name)}</text>')
        body.append(f'<text x="{sx + bar_width / 2:.1f}" y="{sy - 6:.1f}" text-anchor="middle" font-size="11" fill="#111827">{xml_escape(format_tick(cost_values[idx]))}</text>')
    body.append(f'<text x="{left:.1f}" y="{top - 14:.1f}" font-size="13" font-weight="700" fill="#111827">Objective cost by scenario</text>')

    # Panel 2 and 3: per-chord correlation and nrmse
    chord_order = sorted({str(row["chord_key"]) for row in chord_rows})
    for panel_idx, metric_key, title, y_label in [
        (0, "correlation", "Chord-wise correlation", "Correlation"),
        (1, "nrmse_std", "Chord-wise NRMSE/std", "NRMSE/std"),
    ]:
        panel_left = 90.0
        panel_top = 380.0 + panel_idx * 260.0
        panel_width = 1000.0
        panel_height = 180.0
        values = [float(row[metric_key]) for row in chord_rows]
        ymin2, ymax2 = extent([np.asarray(values, dtype=float)], pad_fraction=0.1, include_zero=(metric_key != "correlation"))
        if metric_key == "correlation":
            ymin2 = min(ymin2, 0.95)
            ymax2 = max(ymax2, 1.0)
        draw_axes(body, panel_left, panel_top, panel_width, panel_height, 0.0, float(len(chord_order) - 1), ymin2, ymax2, "Chord index", y_label, show_x_ticks=False)
        body.append(f'<text x="{panel_left:.1f}" y="{panel_top - 14:.1f}" font-size="13" font-weight="700" fill="#111827">{xml_escape(title)}</text>')

        for chord_idx, chord_key in enumerate(chord_order):
            sx = panel_left + chord_idx / max(len(chord_order) - 1, 1) * panel_width
            body.append(f'<line x1="{sx:.1f}" y1="{panel_top:.1f}" x2="{sx:.1f}" y2="{panel_top + panel_height:.1f}" stroke="{PLOT_COLORS["grid"]}" stroke-width="1"/>')
            body.append(f'<text x="{sx:.1f}" y="{panel_top + panel_height + 16:.1f}" text-anchor="middle" font-size="11" fill="#374151">{xml_escape(chord_key.replace("chord_", ""))}</text>')

        for scenario_name in scenarios_order:
            series_rows = [row for row in chord_rows if row["scenario"] == scenario_name]
            series_rows.sort(key=lambda x: x["chord_key"])
            x_vals = np.asarray(list(range(len(series_rows))), dtype=float)
            y_vals = np.asarray([float(row[metric_key]) for row in series_rows], dtype=float)
            points = polyline_points(x_vals, y_vals, 0.0, float(len(chord_order) - 1), ymin2, ymax2, panel_left, panel_top, panel_width, panel_height)
            dash = ' stroke-dasharray="6,4"' if scenario_name == "init" else (' stroke-dasharray="2,3"' if scenario_name == "truth" else "")
            body.append(f'<polyline fill="none" stroke="{PLOT_COLORS.get(scenario_name, "#2563eb")}" stroke-width="2.5"{dash} points="{points}"/>')
            for xv, yv in zip(x_vals, y_vals, strict=True):
                sx = panel_left + xv / max(len(chord_order) - 1, 1) * panel_width
                sy = panel_top + panel_height - (yv - ymin2) / max(ymax2 - ymin2, 1.0e-30) * panel_height
                body.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="3.5" fill="{PLOT_COLORS.get(scenario_name, "#2563eb")}"/>')

    legend_x = 620.0
    legend_y = 112.0
    for idx, scenario_name in enumerate(scenarios_order):
        yy = legend_y + idx * 22.0
        dash = ' stroke-dasharray="6,4"' if scenario_name == "init" else (' stroke-dasharray="2,3"' if scenario_name == "truth" else "")
        body.append(f'<line x1="{legend_x:.1f}" y1="{yy:.1f}" x2="{legend_x + 24:.1f}" y2="{yy:.1f}" stroke="{PLOT_COLORS.get(scenario_name, "#2563eb")}" stroke-width="3"{dash}/>')
        body.append(f'<text x="{legend_x + 32:.1f}" y="{yy + 4:.1f}" font-size="12" fill="#374151">{xml_escape(scenario_name)}</text>')

    write_text_file(path, svg_document(width, height, "Fit Quality Overview", body))


def write_parameter_recovery_svg(path: Path, benchmark_title: str, parameter_rows: List[Dict[str, Any]]) -> None:
    n_panels = len(parameter_rows)
    n_cols = 2
    n_rows = math.ceil(n_panels / n_cols)
    width = 1200
    panel_width = 480.0
    panel_height = 220.0
    height = 100 + n_rows * 280
    body: List[str] = []
    body.append(f'<text x="24" y="56" font-size="14" fill="#4b5563">{xml_escape(benchmark_title)}</text>')

    for idx, row in enumerate(parameter_rows):
        col = idx % n_cols
        grid_row = idx // n_cols
        left = 90.0 + col * 560.0
        top = 100.0 + grid_row * 280.0
        x_vals = np.asarray(list(range(len(row["init_values"]))), dtype=float)
        series_map = {
            "init": np.asarray(row["init_values"], dtype=float),
            "opt": np.asarray(row["opt_values"], dtype=float),
            "truth": np.asarray(row["truth_values"], dtype=float),
        }

        scale = str(row.get("scale", "linear"))
        if scale == "log":
            transformed = [np.log10(np.maximum(vals, 1.0e-30)) for vals in series_map.values()]
            ymin, ymax = extent(transformed, pad_fraction=0.08, include_zero=False)
            y_label = "log10(value)"
        else:
            transformed = list(series_map.values())
            ymin, ymax = extent(transformed, pad_fraction=0.08, include_zero=False)
            y_label = "value"

        draw_axes(body, left, top, panel_width, panel_height, 0.0, float(len(x_vals) - 1), ymin, ymax, "Shell index", y_label, show_x_ticks=False)
        body.append(f'<text x="{left:.1f}" y="{top - 14:.1f}" font-size="13" font-weight="700" fill="#111827">{xml_escape(str(row["group"]))}</text>')
        body.append(
            f'<text x="{left + 160:.1f}" y="{top - 14:.1f}" font-size="11" fill="#4b5563">opt rel err {float(row["opt_mean_abs_rel_error"]):.3f}, uncertainty {float(row["mean_relative_uncertainty"]):.3f}</text>'
        )

        for x_idx in range(len(x_vals)):
            sx = left + x_idx / max(len(x_vals) - 1, 1) * panel_width
            body.append(f'<line x1="{sx:.1f}" y1="{top:.1f}" x2="{sx:.1f}" y2="{top + panel_height:.1f}" stroke="{PLOT_COLORS["grid"]}" stroke-width="1"/>')
            body.append(f'<text x="{sx:.1f}" y="{top + panel_height + 16:.1f}" text-anchor="middle" font-size="11" fill="#374151">{x_idx}</text>')

        for name, vals in series_map.items():
            plot_vals = np.log10(np.maximum(vals, 1.0e-30)) if scale == "log" else vals
            points = polyline_points(x_vals, plot_vals, 0.0, float(len(x_vals) - 1), ymin, ymax, left, top, panel_width, panel_height)
            dash = ' stroke-dasharray="6,4"' if name == "init" else (' stroke-dasharray="2,3"' if name == "truth" else "")
            body.append(f'<polyline fill="none" stroke="{PLOT_COLORS.get(name, "#2563eb")}" stroke-width="2.5"{dash} points="{points}"/>')
            for xv, yv in zip(x_vals, plot_vals, strict=True):
                sx = left + xv / max(len(x_vals) - 1, 1) * panel_width
                sy = top + panel_height - (float(yv) - ymin) / max(ymax - ymin, 1.0e-30) * panel_height
                body.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="3.5" fill="{PLOT_COLORS.get(name, "#2563eb")}"/>')

    legend_x = 820.0
    legend_y = 56.0
    for idx, name in enumerate(["init", "opt", "truth"]):
        yy = legend_y + idx * 18.0
        dash = ' stroke-dasharray="6,4"' if name == "init" else (' stroke-dasharray="2,3"' if name == "truth" else "")
        body.append(f'<line x1="{legend_x:.1f}" y1="{yy:.1f}" x2="{legend_x + 24:.1f}" y2="{yy:.1f}" stroke="{PLOT_COLORS.get(name, "#2563eb")}" stroke-width="3"{dash}/>')
        body.append(f'<text x="{legend_x + 30:.1f}" y="{yy + 4:.1f}" font-size="12" fill="#374151">{xml_escape(name)}</text>')

    write_text_file(path, svg_document(width, height, "Parameter Recovery", body))


def write_window_fidelity_svg(path: Path, benchmark_title: str, window_rows: List[Dict[str, Any]]) -> None:
    rows = window_rows[:8]
    width = 1320
    height = 860
    left = 280.0
    plot_width = 980.0
    body: List[str] = []
    body.append(f'<text x="24" y="56" font-size="14" fill="#4b5563">{xml_escape(benchmark_title)}</text>')

    # Ratios panel
    top = 100.0
    plot_height = 340.0
    all_ratio_values = [float(row["mean_area_ratio"]) for row in rows] + [float(row["mean_peak_ratio"]) for row in rows]
    xmin = min(min(all_ratio_values), 0.0) - 0.15
    xmax = max(max(all_ratio_values), 1.0) + 0.15
    draw_axes(body, left, top, plot_width, plot_height, xmin, xmax, -0.5, float(len(rows) - 0.5), "Ratio to measurement", "Window", show_x_ticks=True)
    body.append(f'<text x="{left:.1f}" y="{top - 14:.1f}" font-size="13" font-weight="700" fill="#111827">Window area and peak ratios</text>')
    x_one = left + (1.0 - xmin) / max(xmax - xmin, 1.0e-30) * plot_width
    x_zero = left + (0.0 - xmin) / max(xmax - xmin, 1.0e-30) * plot_width
    body.append(f'<line x1="{x_one:.1f}" y1="{top:.1f}" x2="{x_one:.1f}" y2="{top + plot_height:.1f}" stroke="#dc2626" stroke-width="2" stroke-dasharray="4,4"/>')
    body.append(f'<line x1="{x_zero:.1f}" y1="{top:.1f}" x2="{x_zero:.1f}" y2="{top + plot_height:.1f}" stroke="#9ca3af" stroke-width="1" stroke-dasharray="2,4"/>')
    for idx, row in enumerate(rows):
        cy = top + (idx + 0.5) / len(rows) * plot_height
        area_val = float(row["mean_area_ratio"])
        peak_val = float(row["mean_peak_ratio"])
        for val, color, yoff in [(area_val, PLOT_COLORS["area"], -8.0), (peak_val, PLOT_COLORS["peak"], 8.0)]:
            x0 = left + (min(1.0, val) - xmin) / max(xmax - xmin, 1.0e-30) * plot_width
            x1 = left + (max(1.0, val) - xmin) / max(xmax - xmin, 1.0e-30) * plot_width
            if val < 1.0:
                x0 = left + (val - xmin) / max(xmax - xmin, 1.0e-30) * plot_width
                x1 = left + (1.0 - xmin) / max(xmax - xmin, 1.0e-30) * plot_width
            body.append(f'<rect x="{min(x0, x1):.1f}" y="{cy + yoff - 5:.1f}" width="{abs(x1 - x0):.1f}" height="10" fill="{color}" opacity="0.85"/>')
        body.append(f'<text x="{left - 10:.1f}" y="{cy + 4:.1f}" text-anchor="end" font-size="12" fill="#374151">{xml_escape(str(row["window_name"]))}</text>')
        body.append(f'<text x="{left + plot_width + 8:.1f}" y="{cy - 4:.1f}" font-size="11" fill="{PLOT_COLORS["area"]}">A {xml_escape(format_tick(area_val))}</text>')
        body.append(f'<text x="{left + plot_width + 8:.1f}" y="{cy + 10:.1f}" font-size="11" fill="{PLOT_COLORS["peak"]}">P {xml_escape(format_tick(peak_val))}</text>')

    # Peak shift panel
    top2 = 520.0
    plot_height2 = 220.0
    shift_values = [float(row["mean_abs_peak_shift_nm"]) for row in rows]
    _, ymax_shift = extent([np.asarray(shift_values, dtype=float)], pad_fraction=0.15, include_zero=True)
    draw_axes(body, left, top2, plot_width, plot_height2, -0.5, float(len(rows) - 0.5), 0.0, ymax_shift, "Window index", "Abs peak shift (nm)", show_x_ticks=False)
    body.append(f'<text x="{left:.1f}" y="{top2 - 14:.1f}" font-size="13" font-weight="700" fill="#111827">Mean absolute peak shift</text>')
    bar_w = plot_width / max(len(rows) * 1.8, 1.0)
    for idx, row in enumerate(rows):
        value = float(row["mean_abs_peak_shift_nm"])
        sx = left + (idx + 0.5) / len(rows) * plot_width - bar_w / 2.0
        sy = top2 + plot_height2 - value / max(ymax_shift, 1.0e-30) * plot_height2
        body.append(f'<rect x="{sx:.1f}" y="{sy:.1f}" width="{bar_w:.1f}" height="{top2 + plot_height2 - sy:.1f}" fill="{PLOT_COLORS["shift"]}"/>')
        body.append(f'<text x="{sx + bar_w / 2:.1f}" y="{top2 + plot_height2 + 16:.1f}" text-anchor="middle" font-size="11" fill="#374151">{idx + 1}</text>')
        body.append(f'<text x="{sx + bar_w / 2:.1f}" y="{sy - 6:.1f}" text-anchor="middle" font-size="11" fill="#111827">{xml_escape(format_tick(value))}</text>')

    write_text_file(path, svg_document(width, height, "Window Fidelity", body))


def _classification_table_rows(classification_summary: Dict[str, Any], scenarios: Iterable[str]) -> str:
    window_acc = dict(classification_summary.get("window_class_accuracy_vs_truth", {}))
    pair_acc = dict(classification_summary.get("pair_pattern_accuracy_vs_truth", {}))
    pair_support = dict(classification_summary.get("pair_support_count", {}))
    rows: List[str] = []
    for scenario in scenarios:
        win_item = window_acc.get(scenario, {})
        pair_item = pair_acc.get(scenario, {})
        rows.append(
            "<tr>"
            f"<td>{xml_escape(scenario)}</td>"
            f"<td>{float(win_item.get('accuracy', 0.0)):.4f}</td>"
            f"<td>{int(win_item.get('support', 0))}</td>"
            f"<td>{float(pair_item.get('accuracy', 0.0)):.4f}</td>"
            f"<td>{int(pair_support.get(scenario, 0))}</td>"
            "</tr>"
        )
    return "".join(rows)


def write_dashboard_html(
    path: Path,
    benchmark_meta: Dict[str, Any],
    scenario_rows: List[Dict[str, Any]],
    plasma_findings: List[str],
    measurement_findings: List[str],
    classification_summary: Dict[str, Any],
) -> None:
    title = str(benchmark_meta.get("title", benchmark_meta.get("benchmark_id", path.parent.name)))
    benchmark_id = str(benchmark_meta.get("benchmark_id", ""))
    source = str(benchmark_meta.get("source", {}).get("citation", ""))
    html_text = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{xml_escape(title)} - Analysis Dashboard</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #111827; background: #f8fafc; }}
    h1, h2 {{ margin-bottom: 8px; }}
    .card {{ background: white; border: 1px solid #e5e7eb; border-radius: 12px; padding: 18px; margin-bottom: 18px; }}
    .meta {{ color: #4b5563; font-size: 14px; }}
    .plots img {{ width: 100%; max-width: 1200px; border: 1px solid #e5e7eb; border-radius: 10px; background: white; }}
    ul {{ margin-top: 6px; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 720px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px 10px; text-align: left; font-size: 14px; }}
    th {{ background: #f3f4f6; }}
    a {{ color: #2563eb; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{xml_escape(title)}</h1>
    <div class="meta">Benchmark ID: {xml_escape(benchmark_id)}</div>
    <div class="meta">Source: {xml_escape(source)}</div>
    <div class="meta"><a href="analysis_report.md">Markdown report</a> | <a href="analysis_summary.yaml">YAML summary</a> | <a href="chord_metrics.csv">Chord metrics</a> | <a href="window_metrics.csv">Window metrics</a> | <a href="classification_window_metrics.csv">Window classes</a> | <a href="mixed_pattern_metrics.csv">Pair classes</a></div>
  </div>
  <div class="card">
    <h2>Scenario Snapshot</h2>
    <table>
      <tr><th>Scenario</th><th>Cost</th><th>Mean Corr.</th><th>Mean NRMSE/std</th><th>Mean Gain</th></tr>
      {''.join(f"<tr><td>{xml_escape(row['scenario'])}</td><td>{float(row['cost']):.4f}</td><td>{float(row['mean_correlation']):.4f}</td><td>{float(row['mean_nrmse_std']):.4f}</td><td>{float(row['mean_gain']):.4f}</td></tr>" for row in scenario_rows)}
    </table>
  </div>
  <div class="card">
    <h2>Classification Metrics</h2>
    <table>
      <tr><th>Scenario</th><th>Window Acc. vs Truth</th><th>Window Support</th><th>Pair Acc. vs Truth</th><th>Pair Support</th></tr>
      {_classification_table_rows(classification_summary, ("init", "opt", "truth"))}
    </table>
  </div>
  <div class="card">
    <h2>Plasma OES Interpretation</h2>
    <ul>{''.join(f"<li>{xml_escape(item)}</li>" for item in plasma_findings)}</ul>
  </div>
  <div class="card">
    <h2>Measurement Engineering Interpretation</h2>
    <ul>{''.join(f"<li>{xml_escape(item)}</li>" for item in measurement_findings)}</ul>
  </div>
  <div class="card plots">
    <h2>Fit Quality</h2>
    <img src="plots/fit_quality.svg" alt="Fit quality plot">
  </div>
  <div class="card plots">
    <h2>Parameter Recovery</h2>
    <img src="plots/parameter_recovery.svg" alt="Parameter recovery plot">
  </div>
  <div class="card plots">
    <h2>Window Fidelity</h2>
    <img src="plots/window_fidelity.svg" alt="Window fidelity plot">
  </div>
  <div class="card plots">
    <h2>Spectral Overlays</h2>
    <img src="plots/spectra_overview.svg" alt="Spectral overlay plot">
  </div>
</body>
</html>
"""
    write_text_file(path, html_text)


def write_forward_spectra_svg(
    path: Path,
    benchmark_title: str,
    inst_id: str,
    scenarios: Dict[str, Dict[str, Any]],
) -> None:
    chord_keys = sorted(
        chord_key
        for plot_inst_id, chord_key in scenarios["init"]["comparison_series"].keys()
        if plot_inst_id == inst_id
    )
    panel_height = 150
    width = 1300
    height = 110 + len(chord_keys) * (panel_height + 35)
    left = 90.0
    plot_width = 1160.0
    body: List[str] = []
    body.append(f'<text x="24" y="56" font-size="14" fill="#4b5563">{xml_escape(benchmark_title)} / {inst_id}</text>')

    legend_items = [
        ("Measurement", PLOT_COLORS["measurement"], ""),
        ("Init forward", PLOT_COLORS["init"], ' stroke-dasharray="6,4"'),
        ("Truth forward", PLOT_COLORS["truth"], ""),
    ]
    lx = 24.0
    ly = 78.0
    for label, color, dash in legend_items:
        body.append(f'<line x1="{lx:.1f}" y1="{ly:.1f}" x2="{lx + 28:.1f}" y2="{ly:.1f}" stroke="{color}" stroke-width="3"{dash}/>')
        body.append(f'<text x="{lx + 36:.1f}" y="{ly + 4:.1f}" font-size="12" fill="#374151">{xml_escape(label)}</text>')
        lx += 180.0

    for idx, chord_key in enumerate(chord_keys):
        top = 100.0 + idx * (panel_height + 35.0)
        init_series = scenarios["init"]["comparison_series"][(inst_id, chord_key)]
        truth_series = scenarios["truth"]["comparison_series"][(inst_id, chord_key)]
        x = init_series.wavelength_nm
        y_arrays = [init_series.measurement, init_series.prediction_fit, truth_series.prediction_fit]
        xmin, xmax = float(np.min(x)), float(np.max(x))
        ymin, ymax = extent(y_arrays, pad_fraction=0.05, include_zero=False)

        draw_axes(body, left, top, plot_width, panel_height, xmin, xmax, ymin, ymax, "Wavelength (nm)", "Intensity", show_x_ticks=True)
        body.append(f'<text x="{left:.1f}" y="{top - 14:.1f}" font-size="13" font-weight="700" fill="#111827">{xml_escape(chord_key)}</text>')

        series_specs = [
            (init_series.measurement, PLOT_COLORS["measurement"], "", 2.0),
            (init_series.prediction_fit, PLOT_COLORS["init"], ' stroke-dasharray="6,4"', 1.8),
            (truth_series.prediction_fit, PLOT_COLORS["truth"], "", 2.0),
        ]
        for y, color, dash, stroke_width in series_specs:
            points = polyline_points(x, y, xmin, xmax, ymin, ymax, left, top, plot_width, panel_height)
            body.append(f'<polyline fill="none" stroke="{color}" stroke-width="{stroke_width}"{dash} points="{points}"/>')

    write_text_file(path, svg_document(width, height, f"Forward Spectral Overlays: {inst_id}", body))


def write_forward_quality_svg(
    path: Path,
    benchmark_title: str,
    scenario_rows: List[Dict[str, Any]],
    chord_rows: List[Dict[str, Any]],
) -> None:
    forward_scenarios = ["init", "truth"]
    scenario_map = {row["scenario"]: row for row in scenario_rows}
    width = 1200
    height = 900
    body: List[str] = []
    body.append(f'<text x="24" y="56" font-size="14" fill="#4b5563">{xml_escape(benchmark_title)}</text>')

    left = 90.0
    top = 90.0
    plot_width = 420.0
    plot_height = 220.0
    cost_values = [float(scenario_map[name]["cost"]) for name in forward_scenarios]
    ymin, ymax = extent([np.asarray(cost_values, dtype=float)], pad_fraction=0.1, include_zero=False)
    draw_axes(body, left, top, plot_width, plot_height, -0.5, 1.5, ymin, ymax, "Scenario", "Cost", show_x_ticks=False)
    bar_width = plot_width / 5.0
    for idx, name in enumerate(forward_scenarios):
        sx = left + (idx + 0.5) / 2.0 * plot_width - bar_width / 2.0
        sy = top + plot_height - (cost_values[idx] - ymin) / max(ymax - ymin, 1.0e-30) * plot_height
        body.append(f'<rect x="{sx:.1f}" y="{sy:.1f}" width="{bar_width:.1f}" height="{top + plot_height - sy:.1f}" fill="{PLOT_COLORS.get(name, "#2563eb")}"/>')
        body.append(f'<text x="{sx + bar_width / 2:.1f}" y="{top + plot_height + 18:.1f}" text-anchor="middle" font-size="12" fill="#374151">{xml_escape(name)}</text>')
        body.append(f'<text x="{sx + bar_width / 2:.1f}" y="{sy - 6:.1f}" text-anchor="middle" font-size="11" fill="#111827">{xml_escape(format_tick(cost_values[idx]))}</text>')
    body.append(f'<text x="{left:.1f}" y="{top - 14:.1f}" font-size="13" font-weight="700" fill="#111827">Forward-only objective by scenario</text>')

    panel_specs = [
        ("correlation", "Chord-wise correlation", "Correlation", 380.0),
        ("nrmse_std", "Chord-wise NRMSE/std", "NRMSE/std", 620.0),
    ]
    chord_order = sorted({str(row["chord_key"]) for row in chord_rows if row["scenario"] in forward_scenarios})
    for metric_key, title, y_label, panel_top in panel_specs:
        panel_left = 90.0
        panel_width = 1000.0
        panel_height = 180.0
        metric_rows = [row for row in chord_rows if row["scenario"] in forward_scenarios]
        values = [float(row[metric_key]) for row in metric_rows]
        ymin2, ymax2 = extent([np.asarray(values, dtype=float)], pad_fraction=0.1, include_zero=(metric_key != "correlation"))
        if metric_key == "correlation":
            ymin2 = min(ymin2, 0.95)
            ymax2 = max(ymax2, 1.0)
        draw_axes(body, panel_left, panel_top, panel_width, panel_height, 0.0, float(len(chord_order) - 1), ymin2, ymax2, "Chord index", y_label, show_x_ticks=False)
        body.append(f'<text x="{panel_left:.1f}" y="{panel_top - 14:.1f}" font-size="13" font-weight="700" fill="#111827">{xml_escape(title)}</text>')
        for chord_idx, chord_key in enumerate(chord_order):
            sx = panel_left + chord_idx / max(len(chord_order) - 1, 1) * panel_width
            body.append(f'<line x1="{sx:.1f}" y1="{panel_top:.1f}" x2="{sx:.1f}" y2="{panel_top + panel_height:.1f}" stroke="{PLOT_COLORS["grid"]}" stroke-width="1"/>')
            body.append(f'<text x="{sx:.1f}" y="{panel_top + panel_height + 16:.1f}" text-anchor="middle" font-size="11" fill="#374151">{xml_escape(chord_key.replace("chord_", ""))}</text>')

        for scenario_name in forward_scenarios:
            series_rows = [row for row in metric_rows if row["scenario"] == scenario_name]
            series_rows.sort(key=lambda x: x["chord_key"])
            x_vals = np.asarray(list(range(len(series_rows))), dtype=float)
            y_vals = np.asarray([float(row[metric_key]) for row in series_rows], dtype=float)
            dash = ' stroke-dasharray="6,4"' if scenario_name == "init" else ""
            points = polyline_points(x_vals, y_vals, 0.0, float(len(chord_order) - 1), ymin2, ymax2, panel_left, panel_top, panel_width, panel_height)
            body.append(f'<polyline fill="none" stroke="{PLOT_COLORS.get(scenario_name, "#2563eb")}" stroke-width="2.5"{dash} points="{points}"/>')
            for xv, yv in zip(x_vals, y_vals, strict=True):
                sx = panel_left + xv / max(len(chord_order) - 1, 1) * panel_width
                sy = panel_top + panel_height - (yv - ymin2) / max(ymax2 - ymin2, 1.0e-30) * panel_height
                body.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="3.5" fill="{PLOT_COLORS.get(scenario_name, "#2563eb")}"/>')

    legend_x = 620.0
    legend_y = 112.0
    for idx, scenario_name in enumerate(forward_scenarios):
        yy = legend_y + idx * 22.0
        dash = ' stroke-dasharray="6,4"' if scenario_name == "init" else ""
        body.append(f'<line x1="{legend_x:.1f}" y1="{yy:.1f}" x2="{legend_x + 24:.1f}" y2="{yy:.1f}" stroke="{PLOT_COLORS.get(scenario_name, "#2563eb")}" stroke-width="3"{dash}/>')
        body.append(f'<text x="{legend_x + 32:.1f}" y="{yy + 4:.1f}" font-size="12" fill="#374151">{xml_escape(scenario_name)}</text>')

    write_text_file(path, svg_document(width, height, "Forward Quality Overview", body))


def _index_forward_window_rows(
    forward_window_rows: List[Dict[str, Any]],
) -> Tuple[List[str], Dict[Tuple[str, str], Dict[str, Any]]]:
    names: List[str] = []
    row_index: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in forward_window_rows:
        name = str(row["window_name"])
        if name not in names:
            names.append(name)
        row_index[(name, str(row["scenario"]))] = row
    return names, row_index


def _append_forward_ratio_bars(
    body: List[str],
    row_index: Dict[Tuple[str, str], Dict[str, Any]],
    name: str,
    center_y: float,
    left: float,
    plot_width: float,
    xmin: float,
    xmax: float,
) -> None:
    for scenario_name, color, y_offset in (
        ("init", PLOT_COLORS["init"], -8.0),
        ("truth", PLOT_COLORS["truth"], 8.0),
    ):
        row = row_index.get((name, scenario_name))
        if row is None:
            continue
        value = float(row["mean_area_ratio"])
        scale = max(xmax - xmin, 1.0e-30)
        x_start = left + (min(1.0, value) - xmin) / scale * plot_width
        x_end = left + (max(1.0, value) - xmin) / scale * plot_width
        body.append(
            f'<rect x="{min(x_start, x_end):.1f}" y="{center_y + y_offset - 5:.1f}" '
            f'width="{abs(x_end - x_start):.1f}" height="10" fill="{color}" opacity="0.85"/>'
        )
        body.append(
            f'<text x="{left + plot_width + 8:.1f}" y="{center_y + y_offset + 4:.1f}" '
            f'font-size="11" fill="{color}">{xml_escape(scenario_name[0].upper())} {format_tick(value)}</text>'
        )


def _append_forward_shift_bars(
    body: List[str],
    row_index: Dict[Tuple[str, str], Dict[str, Any]],
    name: str,
    base_x: float,
    bar_width: float,
    top: float,
    plot_height: float,
    maximum_shift: float,
) -> None:
    for scenario_name, color, shift_index in (
        ("init", PLOT_COLORS["init"], -1),
        ("truth", PLOT_COLORS["truth"], 1),
    ):
        row = row_index.get((name, scenario_name))
        if row is None:
            continue
        value = float(row["mean_abs_peak_shift_nm"])
        x_position = base_x + shift_index * bar_width * 0.7 - bar_width / 2.0
        y_position = top + plot_height - value / max(maximum_shift, 1.0e-30) * plot_height
        body.append(
            f'<rect x="{x_position:.1f}" y="{y_position:.1f}" width="{bar_width:.1f}" '
            f'height="{top + plot_height - y_position:.1f}" fill="{color}"/>'
        )


def write_forward_window_svg(path: Path, benchmark_title: str, forward_window_rows: List[Dict[str, Any]]) -> None:
    names, row_index = _index_forward_window_rows(forward_window_rows)
    rows = list(row_index.values())

    width = 1320
    height = 860
    left = 280.0
    plot_width = 980.0
    body: List[str] = []
    body.append(f'<text x="24" y="56" font-size="14" fill="#4b5563">{xml_escape(benchmark_title)}</text>')

    top = 100.0
    plot_height = 340.0
    all_ratio_values = [float(row["mean_area_ratio"]) for row in rows] + [float(row["mean_peak_ratio"]) for row in rows]
    xmin = min(min(all_ratio_values), 0.0) - 0.2
    xmax = max(max(all_ratio_values), 1.0) + 0.2
    draw_axes(body, left, top, plot_width, plot_height, xmin, xmax, -0.5, float(len(names) - 0.5), "Ratio to measurement", "Window", show_x_ticks=True)
    body.append(f'<text x="{left:.1f}" y="{top - 14:.1f}" font-size="13" font-weight="700" fill="#111827">Forward window area ratios (init vs truth)</text>')
    x_one = left + (1.0 - xmin) / max(xmax - xmin, 1.0e-30) * plot_width
    body.append(f'<line x1="{x_one:.1f}" y1="{top:.1f}" x2="{x_one:.1f}" y2="{top + plot_height:.1f}" stroke="#dc2626" stroke-width="2" stroke-dasharray="4,4"/>')
    for idx, name in enumerate(names):
        cy = top + (idx + 0.5) / len(names) * plot_height
        body.append(f'<text x="{left - 10:.1f}" y="{cy + 4:.1f}" text-anchor="end" font-size="12" fill="#374151">{xml_escape(name)}</text>')
        _append_forward_ratio_bars(body, row_index, name, cy, left, plot_width, xmin, xmax)

    top2 = 520.0
    plot_height2 = 220.0
    shift_values = [float(row["mean_abs_peak_shift_nm"]) for row in rows]
    _, ymax_shift = extent([np.asarray(shift_values, dtype=float)], pad_fraction=0.15, include_zero=True)
    draw_axes(body, left, top2, plot_width, plot_height2, -0.5, float(len(names) - 0.5), 0.0, ymax_shift, "Window index", "Abs peak shift (nm)", show_x_ticks=False)
    body.append(f'<text x="{left:.1f}" y="{top2 - 14:.1f}" font-size="13" font-weight="700" fill="#111827">Forward window peak shift (init vs truth)</text>')
    bar_w = plot_width / max(len(names) * 2.6, 1.0)
    for idx, name in enumerate(names):
        base_x = left + (idx + 0.5) / len(names) * plot_width
        body.append(f'<text x="{base_x:.1f}" y="{top2 + plot_height2 + 16:.1f}" text-anchor="middle" font-size="11" fill="#374151">{idx + 1}</text>')
        _append_forward_shift_bars(
            body,
            row_index,
            name,
            base_x,
            bar_w,
            top2,
            plot_height2,
            ymax_shift,
        )

    write_text_file(path, svg_document(width, height, "Forward Window Fidelity", body))


def write_forward_dashboard_html(
    path: Path,
    benchmark_meta: Dict[str, Any],
    scenario_rows: List[Dict[str, Any]],
    plasma_findings: List[str],
    measurement_findings: List[str],
    classification_summary: Dict[str, Any],
) -> None:
    title = str(benchmark_meta.get("title", benchmark_meta.get("benchmark_id", path.parent.name)))
    benchmark_id = str(benchmark_meta.get("benchmark_id", ""))
    source = str(benchmark_meta.get("source", {}).get("citation", ""))
    html_text = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{xml_escape(title)} - Forward Dashboard</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #111827; background: #f8fafc; }}
    h1, h2 {{ margin-bottom: 8px; }}
    .card {{ background: white; border: 1px solid #e5e7eb; border-radius: 12px; padding: 18px; margin-bottom: 18px; }}
    .meta {{ color: #4b5563; font-size: 14px; }}
    .plots img {{ width: 100%; max-width: 1200px; border: 1px solid #e5e7eb; border-radius: 10px; background: white; }}
    ul {{ margin-top: 6px; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 720px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px 10px; text-align: left; font-size: 14px; }}
    th {{ background: #f3f4f6; }}
    a {{ color: #2563eb; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{xml_escape(title)} Forward Dashboard</h1>
    <div class="meta">Benchmark ID: {xml_escape(benchmark_id)}</div>
    <div class="meta">Source: {xml_escape(source)}</div>
    <div class="meta"><a href="analysis_report.md">Inverse-oriented report</a> | <a href="analysis_summary.yaml">YAML summary</a> | <a href="chord_metrics.csv">Chord metrics</a> | <a href="window_metrics.csv">Window metrics</a> | <a href="classification_window_metrics.csv">Window classes</a> | <a href="mixed_pattern_metrics.csv">Pair classes</a></div>
  </div>
  <div class="card">
    <h2>Forward Scenario Snapshot</h2>
    <table>
      <tr><th>Scenario</th><th>Cost</th><th>Mean Corr.</th><th>Mean NRMSE/std</th><th>Mean Gain</th></tr>
      {''.join(f"<tr><td>{xml_escape(row['scenario'])}</td><td>{float(row['cost']):.4f}</td><td>{float(row['mean_correlation']):.4f}</td><td>{float(row['mean_nrmse_std']):.4f}</td><td>{float(row['mean_gain']):.4f}</td></tr>" for row in scenario_rows if row['scenario'] in ('init','truth'))}
    </table>
  </div>
  <div class="card">
    <h2>Forward Classification Metrics</h2>
    <table>
      <tr><th>Scenario</th><th>Window Acc. vs Truth</th><th>Window Support</th><th>Pair Acc. vs Truth</th><th>Pair Support</th></tr>
      {_classification_table_rows(classification_summary, ("init", "truth"))}
    </table>
  </div>
  <div class="card">
    <h2>Plasma OES View</h2>
    <ul>{''.join(f"<li>{xml_escape(item)}</li>" for item in plasma_findings)}</ul>
  </div>
  <div class="card">
    <h2>Measurement Engineering View</h2>
    <ul>{''.join(f"<li>{xml_escape(item)}</li>" for item in measurement_findings)}</ul>
  </div>
  <div class="card plots">
    <h2>Forward Quality</h2>
    <img src="plots/forward_quality.svg" alt="Forward quality plot">
  </div>
  <div class="card plots">
    <h2>Forward Window Fidelity</h2>
    <img src="plots/forward_window_fidelity.svg" alt="Forward window fidelity plot">
  </div>
  <div class="card plots">
    <h2>Forward Spectral Overlays</h2>
    <img src="plots/forward_spectra_overview.svg" alt="Forward spectral overlays">
  </div>
</body>
</html>
"""
    write_text_file(path, html_text)


def _markdown_table(rows: List[Dict[str, Any]], columns: List[Tuple[str, str]]) -> List[str]:
    header = "| " + " | ".join(label for _, label in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, divider]
    for row in rows:
        cells = []
        for key, _label in columns:
            value = row.get(key, "")
            if isinstance(value, float):
                if math.isnan(value) or math.isinf(value):
                    cells.append(str(value))
                elif abs(value) >= 1.0e4 or (0 < abs(value) < 1.0e-3):
                    cells.append(f"{value:.3e}")
                else:
                    cells.append(f"{value:.4f}")
            elif isinstance(value, list):
                cells.append(", ".join(str(v) for v in value))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def write_markdown_report(
    path: Path,
    benchmark_meta: Dict[str, Any],
    scenario_rows: List[Dict[str, Any]],
    instrument_rows: List[Dict[str, Any]],
    parameter_rows: List[Dict[str, Any]],
    window_rows: List[Dict[str, Any]],
    plasma_findings: List[str],
    measurement_findings: List[str],
    classification_summary: Dict[str, Any],
) -> None:
    title = str(benchmark_meta.get("title", benchmark_meta.get("benchmark_id", path.parent.name)))

    lines: List[str] = []
    lines.append(f"# Benchmark Analysis: {title}")
    lines.append("")
    lines.append(f"- Benchmark ID: {benchmark_meta.get('benchmark_id', '')}")
    lines.append(f"- Source: {benchmark_meta.get('source', {}).get('citation', '')}")
    lines.append("")
    lines.append("## Scenario Summary")
    lines.append("")
    lines.extend(
        _markdown_table(
            scenario_rows,
            [
                ("scenario", "Scenario"),
                ("cost", "Cost"),
                ("mean_correlation", "Mean Corr."),
                ("mean_nrmse_std", "Mean NRMSE/std"),
                ("mean_nrmse_range", "Mean NRMSE/range"),
                ("mean_gain", "Mean Gain"),
            ],
        )
    )
    lines.append("")
    lines.append("## Instrument View")
    lines.append("")
    lines.extend(
        _markdown_table(
            instrument_rows,
            [
                ("instrument_id", "Instrument"),
                ("wavelength_min_nm", "Min nm"),
                ("wavelength_max_nm", "Max nm"),
                ("bin_nm", "Bin nm"),
                ("selected_window_count", "Windows"),
                ("gain_mean", "Gain Mean"),
                ("gain_min", "Gain Min"),
                ("gain_max", "Gain Max"),
            ],
        )
    )
    lines.append("")
    lines.append("## Parameter Recovery")
    lines.append("")
    lines.extend(
        _markdown_table(
            parameter_rows,
            [
                ("group", "Group"),
                ("trend", "Radial Trend"),
                ("init_mean_abs_rel_error", "Init Mean Abs Rel Err"),
                ("opt_mean_abs_rel_error", "Opt Mean Abs Rel Err"),
                ("improvement_fraction", "Improvement"),
                ("mean_relative_uncertainty", "Mean Rel. Uncertainty"),
            ],
        )
    )
    lines.append("")
    lines.append("## Window Fidelity")
    lines.append("")
    lines.extend(
        _markdown_table(
            window_rows[:8],
            [
                ("window_name", "Window"),
                ("kind", "Kind"),
                ("mean_area_ratio", "Mean Area Ratio"),
                ("mean_peak_ratio", "Mean Peak Ratio"),
                ("mean_abs_peak_shift_nm", "Mean Abs Peak Shift nm"),
            ],
        )
    )
    lines.append("")
    lines.append("## Classification Metrics")
    lines.append("")
    class_rows = []
    window_acc = dict(classification_summary.get("window_class_accuracy_vs_truth", {}))
    pair_acc = dict(classification_summary.get("pair_pattern_accuracy_vs_truth", {}))
    pair_support = dict(classification_summary.get("pair_support_count", {}))
    for scenario in ["init", "opt", "truth"]:
        class_rows.append(
            {
                "scenario": scenario,
                "window_accuracy": float(window_acc.get(scenario, {}).get("accuracy", 0.0)),
                "window_support": int(window_acc.get(scenario, {}).get("support", 0)),
                "pair_accuracy": float(pair_acc.get(scenario, {}).get("accuracy", 0.0)),
                "pair_support": int(pair_support.get(scenario, 0)),
            }
        )
    lines.extend(
        _markdown_table(
            class_rows,
            [
                ("scenario", "Scenario"),
                ("window_accuracy", "Window Acc. vs Truth"),
                ("window_support", "Window Support"),
                ("pair_accuracy", "Pair Acc. vs Truth"),
                ("pair_support", "Pair Support"),
            ],
        )
    )
    lines.append("")
    lines.append("## Plasma OES Interpretation")
    lines.append("")
    for item in plasma_findings:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Measurement Engineering Interpretation")
    lines.append("")
    for item in measurement_findings:
        lines.append(f"- {item}")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
