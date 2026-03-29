#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oescr.io.yaml_loader import load_yaml


BENCH_ROOT = Path(__file__).resolve().parents[1] / "examples" / "benchmarks"


def _scenario_map(summary: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(row.get("scenario", "")): row for row in summary.get("scenario_summary", [])}


def _line_pass_map(summary: Dict[str, Any], scenario: str = "opt") -> Dict[str, float]:
    rows = (
        summary.get("classification_summary", {})
        .get("window_pass_rate_by_kind", {})
        .get(scenario, [])
    )
    out: Dict[str, float] = {}
    for row in rows:
        kind = str(row.get("kind", ""))
        if "line" in kind:
            out[kind] = float(row.get("pass_rate", 0.0))
    return out


def _accuracy(summary: Dict[str, Any], key: str, scenario: str = "opt") -> float:
    return float(
        summary.get("classification_summary", {})
        .get(key, {})
        .get(scenario, {})
        .get("accuracy", 0.0)
    )


def _bench_result(
    benchmark_id: str,
    baseline: Dict[str, Any],
    improved: Dict[str, Any],
) -> Dict[str, Any]:
    scen_base = _scenario_map(baseline).get("opt", {})
    scen_imp = _scenario_map(improved).get("opt", {})
    corr_base = float(scen_base.get("mean_correlation", 0.0))
    corr_imp = float(scen_imp.get("mean_correlation", 0.0))
    nrmse_base = float(scen_base.get("mean_nrmse_std", 0.0))
    nrmse_imp = float(scen_imp.get("mean_nrmse_std", 0.0))

    pair_base = _accuracy(baseline, "pair_pattern_accuracy_vs_truth")
    pair_imp = _accuracy(improved, "pair_pattern_accuracy_vs_truth")
    win_base = _accuracy(baseline, "window_class_accuracy_vs_truth")
    win_imp = _accuracy(improved, "window_class_accuracy_vs_truth")

    line_base = _line_pass_map(baseline)
    line_imp = _line_pass_map(improved)
    line_deltas = {
        kind: float(line_imp.get(kind, line_base[kind]) - line_base[kind])
        for kind in line_base
    }

    return {
        "benchmark_id": benchmark_id,
        "pair_acc_base": pair_base,
        "pair_acc_improved": pair_imp,
        "pair_acc_delta": pair_imp - pair_base,
        "window_acc_base": win_base,
        "window_acc_improved": win_imp,
        "window_acc_delta": win_imp - win_base,
        "line_pass_delta": line_deltas,
        "mean_correlation_base": corr_base,
        "mean_correlation_improved": corr_imp,
        "mean_correlation_delta": corr_imp - corr_base,
        "mean_nrmse_std_base": nrmse_base,
        "mean_nrmse_std_improved": nrmse_imp,
        "mean_nrmse_std_rel_delta": (nrmse_imp - nrmse_base) / max(nrmse_base, 1.0e-30),
    }


def _load_summary(benchmark: str, run_name: str, out_name: str) -> Dict[str, Any]:
    path = BENCH_ROOT / benchmark / "runs" / run_name / out_name / "analysis_summary.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Missing analysis summary: {path}")
    return load_yaml(path)


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate strict benchmark acceptance gate from analysis summaries.")
    ap.add_argument("--benchmarks", nargs="+", default=["nf3_ar_ccp_clean_2023", "cl2_ar_icp_fuller2001"])
    ap.add_argument("--baseline-run", default="inverse_plan_baseline_20260329")
    ap.add_argument("--baseline-out-name", default="analysis_plan_baseline")
    ap.add_argument("--improved-run", default="inverse_plan_improved_20260329")
    ap.add_argument("--improved-out-name", default="analysis_plan_improved")
    ap.add_argument("--cl2-pair-threshold", type=float, default=0.80)
    args = ap.parse_args()

    results: List[Dict[str, Any]] = []
    for benchmark in args.benchmarks:
        base_summary = _load_summary(benchmark, args.baseline_run, args.baseline_out_name)
        imp_summary = _load_summary(benchmark, args.improved_run, args.improved_out_name)
        results.append(_bench_result(benchmark, base_summary, imp_summary))

    pair_non_degrade = all(item["pair_acc_delta"] >= -1.0e-12 for item in results)
    line_non_degrade = all(all(delta >= -1.0e-12 for delta in item["line_pass_delta"].values()) for item in results)
    corr_guard = all((-item["mean_correlation_delta"]) <= 0.002 + 1.0e-12 for item in results)
    nrmse_guard = all(item["mean_nrmse_std_rel_delta"] <= 0.05 + 1.0e-12 for item in results)

    any_class_improve = False
    for item in results:
        max_line_delta = max(item["line_pass_delta"].values(), default=0.0)
        if max(item["pair_acc_delta"], item["window_acc_delta"], max_line_delta) >= 0.05 - 1.0e-12:
            any_class_improve = True
            break

    cl2_items = [item for item in results if item["benchmark_id"] == "cl2_ar_icp_fuller2001"]
    cl2_pair_guard = bool(cl2_items) and cl2_items[0]["pair_acc_improved"] >= float(args.cl2_pair_threshold) - 1.0e-12

    gate = {
        "pair_non_degrade": pair_non_degrade,
        "line_non_degrade": line_non_degrade,
        "correlation_guard": corr_guard,
        "nrmse_guard": nrmse_guard,
        "classification_improvement_ge_5pt": any_class_improve,
        "cl2_pair_accuracy_guard": cl2_pair_guard,
    }
    passed = all(gate.values())

    print("Strict Gate Summary")
    for item in results:
        print(
            f"- {item['benchmark_id']}: pair {item['pair_acc_base']:.3f}->{item['pair_acc_improved']:.3f}, "
            f"window {item['window_acc_base']:.3f}->{item['window_acc_improved']:.3f}, "
            f"corr_delta {item['mean_correlation_delta']:+.6f}, "
            f"nrmse_rel_delta {item['mean_nrmse_std_rel_delta']:+.3%}"
        )
    print("Gate Flags:", gate)
    print("Result:", "PASS" if passed else "FAIL")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
