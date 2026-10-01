#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oescr.analysis.benchmark_contract import (
    AnalysisContractError,
    assert_compatible_analysis_contracts,
    require_analysis_contract,
)
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
    baseline_scenario: str = "opt",
    improved_scenario: str = "opt",
) -> Dict[str, Any]:
    scen_base = _scenario_map(baseline).get(baseline_scenario, {})
    scen_imp = _scenario_map(improved).get(improved_scenario, {})
    corr_base = float(scen_base.get("mean_correlation", 0.0))
    corr_imp = float(scen_imp.get("mean_correlation", 0.0))
    nrmse_base = float(scen_base.get("mean_nrmse_std", 0.0))
    nrmse_imp = float(scen_imp.get("mean_nrmse_std", 0.0))

    pair_base = _accuracy(baseline, "pair_pattern_accuracy_vs_truth", baseline_scenario)
    pair_imp = _accuracy(improved, "pair_pattern_accuracy_vs_truth", improved_scenario)
    win_base = _accuracy(baseline, "window_class_accuracy_vs_truth", baseline_scenario)
    win_imp = _accuracy(improved, "window_class_accuracy_vs_truth", improved_scenario)

    line_base = _line_pass_map(baseline, baseline_scenario)
    line_imp = _line_pass_map(improved, improved_scenario)
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


def _argument_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Evaluate the generated self-consistency acceptance gate from analysis summaries."
    )
    ap.add_argument("--benchmarks", nargs="+", default=["nf3_ar_ccp_clean_2023", "cl2_ar_icp_fuller2001"])
    ap.add_argument("--baseline-run", help="Baseline run directory for a between-run comparison.")
    ap.add_argument("--baseline-out-name", help="Baseline analysis directory for a between-run comparison.")
    ap.add_argument("--improved-run", required=True, help="Candidate run directory.")
    ap.add_argument("--improved-out-name", required=True, help="Candidate analysis directory.")
    ap.add_argument(
        "--within-run",
        action="store_true",
        help="Compare init to opt in each improved summary instead of comparing two run directories.",
    )
    ap.add_argument("--cl2-pair-threshold", type=float, default=0.80)
    return ap


def _comparison_results(args: argparse.Namespace, ap: argparse.ArgumentParser) -> List[Dict[str, Any]]:
    if not args.within_run and (not args.baseline_run or not args.baseline_out_name):
        ap.error("Between-run comparison requires --baseline-run and --baseline-out-name.")

    results: List[Dict[str, Any]] = []
    for benchmark in args.benchmarks:
        imp_summary = _load_summary(benchmark, args.improved_run, args.improved_out_name)
        try:
            if args.within_run:
                require_analysis_contract(imp_summary)
                results.append(
                    _bench_result(
                        benchmark,
                        imp_summary,
                        imp_summary,
                        baseline_scenario="init",
                        improved_scenario="opt",
                    )
                )
            else:
                base_summary = _load_summary(benchmark, args.baseline_run, args.baseline_out_name)
                assert_compatible_analysis_contracts(base_summary, imp_summary)
                results.append(_bench_result(benchmark, base_summary, imp_summary))
        except AnalysisContractError as exc:
            ap.error(str(exc))
    return results


def _gate_flags(results: List[Dict[str, Any]], cl2_pair_threshold: float) -> Dict[str, bool]:
    pair_non_degrade = all(item["pair_acc_delta"] >= -1.0e-12 for item in results)
    window_non_degrade = all(item["window_acc_delta"] >= -1.0e-12 for item in results)
    line_non_degrade = all(
        all(delta >= -1.0e-12 for delta in item["line_pass_delta"].values()) for item in results
    )
    corr_guard = all((-item["mean_correlation_delta"]) <= 0.002 + 1.0e-12 for item in results)
    nrmse_guard = all(item["mean_nrmse_std_rel_delta"] <= 0.05 + 1.0e-12 for item in results)
    any_class_improve = any(
        max(
            item["pair_acc_delta"],
            item["window_acc_delta"],
            max(item["line_pass_delta"].values(), default=0.0),
        )
        >= 0.05 - 1.0e-12
        for item in results
    )
    cl2_items = [item for item in results if item["benchmark_id"] == "cl2_ar_icp_fuller2001"]
    cl2_pair_guard = bool(cl2_items) and cl2_items[0]["pair_acc_improved"] >= cl2_pair_threshold - 1.0e-12

    return {
        "pair_non_degrade": pair_non_degrade,
        "window_non_degrade": window_non_degrade,
        "line_non_degrade": line_non_degrade,
        "correlation_guard": corr_guard,
        "nrmse_guard": nrmse_guard,
        "classification_improvement_ge_5pt": any_class_improve,
        "cl2_pair_accuracy_guard": cl2_pair_guard,
    }


def _print_summary(results: List[Dict[str, Any]], gate: Dict[str, bool], within_run: bool) -> None:
    comparison = "init->opt within current run" if within_run else "baseline->improved runs"
    print(f"Generated Self-Consistency Gate Summary ({comparison})")
    for item in results:
        print(
            f"- {item['benchmark_id']}: pair {item['pair_acc_base']:.3f}->{item['pair_acc_improved']:.3f}, "
            f"window {item['window_acc_base']:.3f}->{item['window_acc_improved']:.3f}, "
            f"corr_delta {item['mean_correlation_delta']:+.6f}, "
            f"nrmse_rel_delta {item['mean_nrmse_std_rel_delta']:+.3%}"
        )
    print("Gate Flags:", gate)
    print("Result:", "PASS" if all(gate.values()) else "FAIL")


def main() -> None:
    ap = _argument_parser()
    args = ap.parse_args()
    results = _comparison_results(args, ap)
    gate = _gate_flags(results, float(args.cl2_pair_threshold))
    _print_summary(results, gate, bool(args.within_run))
    passed = all(gate.values())
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
