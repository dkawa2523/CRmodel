# Benchmark cases

These benchmark directories package literature-anchored, measurement-like spectra for the OESCR examples. They are not redistributed raw experimental spectra. Each benchmark uses a published process window, expected dominant features, and a reproducible synthetic spatialization/noise model to produce five same-height chords for forward/inverse testing.

`common_state_ar_o2/` and `common_state_ar_cl2/` are a separate focused family:
each narrow wavelength window is one observed spectrum from the same single
zone, and all windows share one fitted `Te` and `ne`. They intentionally do not
use five chords. Run both with:

```bash
python scripts/run_common_state_benchmarks.py
```

The command also runs a fixed-seed CMA-ES cross-check and writes the report to
[`docs/common_state_benchmark.md`](../../docs/common_state_benchmark.md).
Ar/O2 contains five observed spectra but three independent excitation
channels; Ar/Cl2 contains seven and five respectively. This distinction avoids
counting multiple radiative branches from one upper state as independent
physics.

Each benchmark directory now includes:

- `case_truth.yaml`
- `case_init.yaml`
- `inverse.yaml`
- `project.yaml`
- `instrument.yaml`
- `windows.yaml`
- `measurements/`
- `forward_truth/`
- `benchmark_meta.yaml`
- `validation.yaml`

NF3/Ar と Cl2/Ar には、通常の workflow 回帰ケースとは別に次の
optimizer robustness 設定も含まれる。

- `case_robust_init.yaml` — 真値から遠い非単調初期分布
- `inverse_robust.yaml` — chord 0–3 のみを fitting し、truth-near parameter prior を除外
- `robustness.yaml` — seed、held-out chord、作図 window、versioned 合格条件

`measurements/` and `forward_truth/` are fixed, versioned fixtures because
their hashes participate in the evidence contract. Optimizer results, report
directories, and regenerated forward runs are local artifacts and are ignored;
write them under `.local_outputs/` or another disposable output directory.

Recommended commands:

```bash
python scripts/validate_project.py examples/benchmarks/nf3_ar_ccp_clean_2023/project.yaml
python scripts/run_project.py examples/benchmarks/nf3_ar_ccp_clean_2023/project.yaml --task inverse
python scripts/audit_validation_evidence.py
python scripts/run_optimization_robustness_benchmarks.py
python scripts/generate_robustness_benchmark_figures.py
python scripts/summarize_identifiability.py \
  examples/benchmarks/nf3_ar_ccp_clean_2023/case_init.yaml \
  examples/benchmarks/nf3_ar_ccp_clean_2023/inverse.yaml
python scripts/evaluate_strict_gate.py \
  --within-run \
  --improved-run inverse_observable_20260929 \
  --improved-out-name analysis_contract_v1
```

`validation.yaml` fixes the generated measurement files and evaluator by
SHA-256 and records their evidence level, preprocessing, evaluator version,
result contract, generated-truth data use, and limitations.
These literature-anchored spectra are generated self-consistency fixtures, not
redistributed or held-out experimental spectra.

The distant-initialization benchmark deliberately remains an internal
same-model test. Its current NF3/Ar and Cl2/Ar runs fail the versioned
parameter-recovery and held-out-chord criteria; see
[`docs/optimization_robustness_benchmark.md`](../../docs/optimization_robustness_benchmark.md).
Do not replace this result with the best truth-aware seed or interpret it as an
external physics qualification.

Every new analysis summary separates `analysis_contract` from
`run_fingerprint`. Between-run comparison rejects missing or different
contracts; rerun the analyzer instead of comparing legacy summary values.

The benchmark inverse files fit only variables supported by their current
measurement-only Jacobians. Electron density is fixed in both relative-shape
benchmarks because automatic gain and source-density scale make its absolute
value unobservable here. NF3/Ar remains strongly ill-conditioned even after
that reduction, so its weakest Te/F combinations are diagnostic rather than a
claim of robust experimental retrieval.

You can still use the lower-level entry points directly:

```bash
python scripts/build_benchmark_measurements.py
python scripts/run_forward.py examples/benchmarks/nf3_ar_ccp_clean_2023/case_truth.yaml --out tmp_forward
python scripts/run_inverse.py examples/benchmarks/nf3_ar_ccp_clean_2023/case_init.yaml examples/benchmarks/nf3_ar_ccp_clean_2023/inverse.yaml --out tmp_inverse
```
