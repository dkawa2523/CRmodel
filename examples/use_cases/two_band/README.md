# Minimal inverse-mode vertical slices

This directory exercises the three retained inverse modes that need more than
a relative full-spectrum fit. All three workflows share one physical two-band
case, one window registry, and one generated measurement. The differences are
limited to the initial state and inverse interpretation.

The bands use constant, dimensioned excitation coefficients so that the
example tests OESCR's data flow rather than a particular gas database. `Target`
and `Actinometer` are placeholders, not qualified chemical species. The
checked-in spectrum is generated from `case_truth.yaml` and has a fixed 1%
full-scale pointwise uncertainty. It is self-consistency evidence only and is
not external model validation.

Run from the repository root:

```text
python scripts/run_inverse.py examples/use_cases/two_band/case_ratio_init.yaml examples/use_cases/two_band/inverse_ratio.yaml --out inverse_ratio_output
python scripts/run_inverse.py examples/use_cases/two_band/case_ratio_init.yaml examples/use_cases/two_band/inverse_actinometry.yaml --out inverse_actinometry_output
python scripts/run_inverse.py examples/use_cases/two_band/case_absolute_init.yaml examples/use_cases/two_band/inverse_absolute.yaml --out inverse_absolute_output
```

Each command writes `fit_summary.yaml` and `case_opt.yaml`. Expected results:

| Mode | Fitted quantity | Expected value | Required result checks |
|---|---|---:|---|
| `ratio_diagnostic` | `plasma_state.radicals.Target[0]` | `2.0e18 m-3` | one ratio observation, rank 1, both windows selected |
| `actinometry` | `plasma_state.radicals.Target[0]` | `2.0e18 m-3` | same numerical ratio path, actinometry assumptions reported |
| `calibrated_absolute` | `plasma_state.ne_shells_m3[0]` | `3.0e16 m-3` | prerequisites true, local absolute-scale rank true, calibration uncertainty `0.01` |

The first two modes deliberately use only the configured area ratio. The
absolute mode fixes automatic gain and uses the full spectrum with matching
basis, unit, calibration-reference metadata, and measurement uncertainty.

To replace the placeholders with a real gas pair, edit the band source keys,
rate source (`cross_section_file` or `coefficient_m3_s`), photon yield,
branching ratio, diagnostic windows, and independently supplied source
densities. Do not interpret an actinometric density until excitation,
quenching, branching, relative response, and composition assumptions are
justified for that experiment.
