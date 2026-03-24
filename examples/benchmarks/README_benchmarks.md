# Benchmark cases

These benchmark directories package literature-anchored, measurement-like spectra for the OESCR examples. They are not redistributed raw experimental spectra. Each benchmark uses a published process window, expected dominant features, and a reproducible synthetic spatialization/noise model to produce five same-height chords for forward/inverse testing.

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

Recommended commands:

```bash
python scripts/validate_project.py examples/benchmarks/nf3_ar_ccp_clean_2023/project.yaml
python scripts/run_project.py examples/benchmarks/nf3_ar_ccp_clean_2023/project.yaml --task inverse
```

You can still use the lower-level entry points directly:

```bash
python scripts/build_benchmark_measurements.py
python scripts/run_forward.py examples/benchmarks/nf3_ar_ccp_clean_2023/case_truth.yaml --out tmp_forward
python scripts/run_inverse.py examples/benchmarks/nf3_ar_ccp_clean_2023/case_init.yaml examples/benchmarks/nf3_ar_ccp_clean_2023/inverse.yaml --out tmp_inverse
```
