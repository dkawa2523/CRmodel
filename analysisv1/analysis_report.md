# Benchmark Analysis: NF3/Ar CCP chamber-clean benchmark (literature-anchored, measurement-like)

- Benchmark ID: nf3_ar_ccp_clean_2023
- Source: An, S.; Hong, S.J., Spectroscopic Analysis of NF3 Plasmas with Oxygen Additive for PECVD Chamber Cleaning, Coatings 13(1), 91 (2023).

## Scenario Summary

| Scenario | Cost | Mean Corr. | Mean NRMSE/std | Mean NRMSE/range | Mean Gain |
| --- | --- | --- | --- | --- | --- |
| init | 417.6906 | 0.9906 | 0.1544 | 0.0108 | 3.9523 |
| opt | 416.9854 | 0.9906 | 0.1544 | 0.0108 | 3.9523 |
| truth | 374.4378 | 0.9911 | 0.1554 | 0.0108 | 1.0421 |

## Instrument View

| Instrument | Min nm | Max nm | Bin nm | Windows | Gain Mean | Gain Min | Gain Max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| nf3_benchmark_uvvis | 300.0000 | 820.0000 | 0.5000 | 7 | 3.9523 | 3.6764 | 4.2299 |

## Parameter Recovery

| Group | Radial Trend | Init Mean Abs Rel Err | Opt Mean Abs Rel Err | Improvement | Mean Rel. Uncertainty |
| --- | --- | --- | --- | --- | --- |
| ne | monotonic decrease from core to edge | 0.1831 | 0.1831 | -1.288e-05 | 0.1441 |
| te | monotonic decrease from core to edge | 0.1160 | 0.1160 | -4.268e-07 | 0.0089 |
| F | monotonic decrease from core to edge | 0.1498 | 0.1498 | 3.048e-05 | 0.2880 |
| N2e | monotonic decrease from core to edge | 0.1628 | 0.1628 | -1.822e-05 | 0.1343 |

## Window Fidelity

| Window | Kind | Mean Area Ratio | Mean Peak Ratio | Mean Abs Peak Shift nm |
| --- | --- | --- | --- | --- |
| N2_FP_550_700 | broadband_window | -0.9721 | 1.0310 | 0.0000 |
| FI_685_603 | atomic_line | 1.0675 | 1.0733 | 0.0000 |
| FI_703_747 | atomic_line | 1.0737 | 1.0331 | 0.3000 |
| FI_712_789 | atomic_line | 1.0804 | 1.0796 | 0.3000 |
| N2_SPS_300_400 | broadband_window | 2.0922 | 0.8337 | 17.9000 |
| ArI_811_531 | atomic_line | 3.9406 | 2.1674 | 0.4000 |
| ArI_750_387 | atomic_line | 8.643e-14 | 1.253e-14 | 0.6000 |

## Plasma OES Interpretation

- Dominant measured features are N2_FP_550_700 (broadband_window, area ratio -0.97), FI_685_603 (atomic_line, area ratio 1.07), FI_703_747 (atomic_line, area ratio 1.07).
- The inverse solution reduces the objective cost by 0.2% relative to the initial state.
- The truth case remains within the same cost basin as the fitted case, so the fit is consistent with the benchmark physics under noise.
- Parameter recovery against the benchmark truth is weak for ne, te, F, N2e; spectral agreement is being achieved mainly through shape matching rather than absolute emissivity recovery.
- Recovered radial trends are ne: monotonic decrease from core to edge, te: monotonic decrease from core to edge, F: monotonic decrease from core to edge, N2e: monotonic decrease from core to edge.

## Measurement Engineering Interpretation

- nf3_benchmark_uvvis covers 300.0-820.0 nm with 0.500 nm sampling and uses 7 analysis windows.
- Fitted gain spans 3.676-4.230 with negligible offsets (max abs offset 8.173e-16).
- Mean absolute peak shift across narrow features is 0.320 nm, which is the practical wavelength-alignment indicator for the current inverse workflow.
- Signed window-area ratios can become negative for broad bands when local baseline subtraction dominates the integrated residual; treat those entries as a baseline-sensitivity flag rather than a literal negative emissivity.
- The least constrained fitted quantities are F2 (46.6% rel.), F1 (23.9% rel.), N2e1 (17.0% rel.), ne2 (16.1% rel.).
