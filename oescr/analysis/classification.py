from __future__ import annotations

from typing import Any, Dict, List, Tuple

WINDOW_CLASS_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "line": {"area_lo": 0.75, "area_hi": 1.35, "peak_lo": 0.80, "peak_hi": 1.25, "shift_nm": 0.5},
    "broad": {"area_lo": 0.50, "area_hi": 1.80, "peak_lo": 0.60, "peak_hi": 1.50, "shift_nm": 3.0},
}
PAIR_CLASS_LOG_TOL = 0.15


def is_broad_kind(kind: str) -> bool:
    lowered = kind.lower()
    return ("band" in lowered) or ("broad" in lowered)


def window_thresholds(kind: str) -> Dict[str, float]:
    return WINDOW_CLASS_THRESHOLDS["broad"] if is_broad_kind(kind) else WINDOW_CLASS_THRESHOLDS["line"]


def window_class_label(
    kind: str,
    use_area: bool,
    use_peak: bool,
    area_ratio: float,
    peak_ratio: float,
    abs_peak_shift_nm: float,
    skipped_low_signal: bool,
) -> str:
    if skipped_low_signal:
        return "ignored_low_signal"
    th = window_thresholds(kind)
    if abs_peak_shift_nm > th["shift_nm"]:
        return "misaligned"
    over = False
    under = False
    if use_area:
        over = over or area_ratio > th["area_hi"]
        under = under or area_ratio < th["area_lo"]
    if use_peak:
        over = over or peak_ratio > th["peak_hi"]
        under = under or peak_ratio < th["peak_lo"]
    if over:
        return "over"
    if under:
        return "under"
    return "good"


def classify_window(
    kind: str,
    use_area: bool,
    use_peak: bool,
    area_ratio: float,
    peak_ratio: float,
    abs_peak_shift_nm: float,
    skipped_low_signal: bool,
) -> str:
    return window_class_label(
        kind=kind,
        use_area=use_area,
        use_peak=use_peak,
        area_ratio=area_ratio,
        peak_ratio=peak_ratio,
        abs_peak_shift_nm=abs_peak_shift_nm,
        skipped_low_signal=skipped_low_signal,
    )


def window_quality_score(row: Dict[str, Any]) -> float:
    th = window_thresholds(str(row.get("kind", "")))
    use_area = bool(row.get("use_area", True))
    use_peak = bool(row.get("use_peak", True))
    area_ok = (not use_area) or (th["area_lo"] <= float(row.get("area_ratio", 0.0)) <= th["area_hi"])
    peak_ok = (not use_peak) or (th["peak_lo"] <= float(row.get("peak_ratio", 0.0)) <= th["peak_hi"])
    shift_ok = abs(float(row.get("peak_shift_nm", 0.0))) <= th["shift_nm"]
    return (float(area_ok) + float(peak_ok) + float(shift_ok)) / 3.0


def pair_pattern_label(log_ratio_error: float, log_tol: float = PAIR_CLASS_LOG_TOL) -> str:
    if log_ratio_error > log_tol:
        return "numerator_dominant"
    if log_ratio_error < -log_tol:
        return "denominator_dominant"
    return "balanced"


def classify_pair_log_error(log_ratio_error: float, log_tol: float = PAIR_CLASS_LOG_TOL) -> str:
    return pair_pattern_label(log_ratio_error, log_tol=log_tol)


def scenario_accuracy_vs_truth(
    rows: List[Dict[str, Any]],
    scenario_field: str,
    key_fields: Tuple[str, ...],
    label_field: str,
) -> Dict[str, Dict[str, float]]:
    truth_map: Dict[Tuple[str, ...], str] = {}
    for row in rows:
        if str(row.get(scenario_field, "")) != "truth":
            continue
        key = tuple(str(row.get(field, "")) for field in key_fields)
        truth_map[key] = str(row.get(label_field, ""))

    out: Dict[str, Dict[str, float]] = {}
    for scenario in ("init", "opt", "truth"):
        support = 0
        hits = 0
        for row in rows:
            if str(row.get(scenario_field, "")) != scenario:
                continue
            key = tuple(str(row.get(field, "")) for field in key_fields)
            truth_label = truth_map.get(key)
            if truth_label is None or truth_label == "ignored_low_signal":
                continue
            pred_label = str(row.get(label_field, ""))
            if pred_label == "ignored_low_signal":
                continue
            support += 1
            if pred_label == truth_label:
                hits += 1
            row["truth_label"] = truth_label
            row["class_match_truth"] = bool(pred_label == truth_label)
        out[scenario] = {"accuracy": float(hits / support) if support > 0 else 0.0, "support": int(support)}
    return out


def window_pass_rate_by_kind(window_class_rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for scenario in ("init", "opt", "truth"):
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in window_class_rows:
            if str(row.get("scenario", "")) != scenario:
                continue
            if str(row.get("window_class", "")) == "ignored_low_signal":
                continue
            grouped.setdefault(str(row.get("kind", "")), []).append(row)

        rows: List[Dict[str, Any]] = []
        for kind, items in grouped.items():
            support = len(items)
            pass_count = sum(1 for item in items if bool(item.get("quality_pass", False)))
            rows.append(
                {
                    "kind": kind,
                    "pass_rate": float(pass_count / support) if support > 0 else 0.0,
                    "support": int(support),
                }
            )
        rows.sort(key=lambda x: (-x["support"], x["kind"]))
        out[scenario] = rows
    return out
