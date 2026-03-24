# Benchmark Analysis: NF3/Ar CCP chamber-clean benchmark (literature-anchored, measurement-like)

- Benchmark ID: nf3_ar_ccp_clean_2023
- Source: An, S.; Hong, S.J., Spectroscopic Analysis of NF3 Plasmas with Oxygen Additive for PECVD Chamber Cleaning, Coatings 13(1), 91 (2023).

## Scenario Summary

| Scenario | Cost | Mean Corr. | Mean NRMSE/std | Mean NRMSE/range | Mean Gain |
| --- | --- | --- | --- | --- | --- |
| init | 435.5537 | 0.9906 | 0.1679 | 0.0117 | 4.0939 |
| opt | 394.0121 | 0.9911 | 0.1582 | 0.0110 | 0.7773 |
| truth | 377.0304 | 0.9911 | 0.1564 | 0.0109 | 1.0405 |

## Instrument View

| Instrument | Min nm | Max nm | Bin nm | Windows | Gain Mean | Gain Min | Gain Max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| nf3_benchmark_uvvis | 300.0000 | 820.0000 | 0.5000 | 7 | 0.7773 | 0.7773 | 0.7773 |

## Parameter Recovery

| Group | Radial Trend | Init Mean Abs Rel Err | Opt Mean Abs Rel Err | Improvement | Mean Rel. Uncertainty |
| --- | --- | --- | --- | --- | --- |
| ne | non-monotonic radial structure | 0.1831 | 0.3193 | -0.7439 | 0.1332 |
| te | monotonic decrease from core to edge | 0.1160 | 0.2715 | -1.3400 | 0.0077 |
| F | non-monotonic radial structure | 0.1498 | 0.6517 | -3.3507 | 0.1190 |
| N2e | non-monotonic radial structure | 0.1628 | 0.3523 | -1.1632 | 0.2535 |

## Window Fidelity

| Window | Kind | Mean Area Ratio | Mean Peak Ratio | Mean Abs Peak Shift nm |
| --- | --- | --- | --- | --- |
| N2_FP_550_700 | broadband_window | -1.0243 | 1.0371 | 0.0000 |
| FI_685_603 | atomic_line | 1.0724 | 1.0778 | 0.0000 |
| FI_703_747 | atomic_line | 1.0800 | 1.0399 | 0.3000 |
| FI_712_789 | atomic_line | 1.0871 | 1.0872 | 0.3000 |
| N2_SPS_300_400 | broadband_window | 0.3881 | 0.1545 | 17.9000 |
| ArI_811_531 | atomic_line | 0.7909 | 0.4405 | 0.4000 |
| ArI_750_387 | atomic_line | 1.775e-13 | 2.483e-14 | 0.6000 |

## Plasma OES Interpretation

- Dominant measured features are N2_FP_550_700 (broadband_window, area ratio -1.02), FI_685_603 (atomic_line, area ratio 1.07), FI_703_747 (atomic_line, area ratio 1.08).
- The inverse solution reduces the objective cost by 9.5% relative to the initial state.
- The truth case remains within the same cost basin as the fitted case, so the fit is consistent with the benchmark physics under noise.
- Parameter recovery against the benchmark truth is weak for ne, te, F, N2e; spectral agreement is being achieved mainly through shape matching rather than absolute emissivity recovery.
- Recovered radial trends are ne: non-monotonic radial structure, te: monotonic decrease from core to edge, F: non-monotonic radial structure, N2e: non-monotonic radial structure.

## Measurement Engineering Interpretation

- nf3_benchmark_uvvis covers 300.0-820.0 nm with 0.500 nm sampling and uses 7 analysis windows.
- Fitted gain spans 0.777-0.777 with negligible offsets (max abs offset 1.055e-17).
- Mean absolute peak shift across narrow features is 0.320 nm, which is the practical wavelength-alignment indicator for the current inverse workflow.
- Signed window-area ratios can become negative for broad bands when local baseline subtraction dominates the integrated residual; treat those entries as a baseline-sensitivity flag rather than a literal negative emissivity.
- The least constrained fitted quantities are N2e0 (49.3% rel.), ne0 (20.8% rel.), N2e2 (17.6% rel.), F1 (13.3% rel.).
