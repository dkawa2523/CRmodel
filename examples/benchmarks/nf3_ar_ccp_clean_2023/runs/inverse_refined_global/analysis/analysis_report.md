# Benchmark Analysis: NF3/Ar CCP chamber-clean benchmark (literature-anchored, measurement-like)

- Benchmark ID: nf3_ar_ccp_clean_2023
- Source: An, S.; Hong, S.J., Spectroscopic Analysis of NF3 Plasmas with Oxygen Additive for PECVD Chamber Cleaning, Coatings 13(1), 91 (2023).

## Scenario Summary

| Scenario | Cost | Mean Corr. | Mean NRMSE/std | Mean NRMSE/range | Mean Gain |
| --- | --- | --- | --- | --- | --- |
| init | 435.5756 | 0.9906 | 0.1679 | 0.0117 | 4.0939 |
| opt | 372.3069 | 0.9911 | 0.1569 | 0.0109 | 0.5755 |
| truth | 375.4522 | 0.9911 | 0.1564 | 0.0109 | 1.0405 |

## Instrument View

| Instrument | Min nm | Max nm | Bin nm | Windows | Gain Mean | Gain Min | Gain Max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| nf3_benchmark_uvvis | 300.0000 | 820.0000 | 0.5000 | 7 | 0.5755 | 0.5755 | 0.5755 |

## Parameter Recovery

| Group | Radial Trend | Init Mean Abs Rel Err | Opt Mean Abs Rel Err | Improvement | Mean Rel. Uncertainty |
| --- | --- | --- | --- | --- | --- |
| ne | monotonic decrease from core to edge | 0.1831 | 0.4879 | -1.6651 | 0.6044 |
| te | non-monotonic radial structure | 0.1160 | 0.1919 | -0.6538 | 0.0245 |
| F | non-monotonic radial structure | 0.1498 | 0.4590 | -2.0644 | 0.8504 |
| N2e | non-monotonic radial structure | 0.1628 | 0.5461 | -2.3534 | 0.6950 |

## Window Fidelity

| Window | Kind | Mean Area Ratio | Mean Peak Ratio | Mean Abs Peak Shift nm |
| --- | --- | --- | --- | --- |
| N2_FP_550_700 | broadband_window | -1.0244 | 1.0359 | 0.0000 |
| FI_685_603 | atomic_line | 1.0713 | 1.0769 | 0.0000 |
| FI_703_747 | atomic_line | 1.0793 | 1.0390 | 0.3000 |
| FI_712_789 | atomic_line | 1.0850 | 1.0843 | 0.3000 |
| N2_SPS_300_400 | broadband_window | 0.3244 | 0.1322 | 17.9000 |
| ArI_811_531 | atomic_line | 0.5855 | 0.3261 | 0.4000 |
| ArI_750_387 | atomic_line | 1.340e-13 | 2.357e-14 | 0.6000 |

## Plasma OES Interpretation

- Dominant measured features are N2_FP_550_700 (broadband_window, area ratio -1.02), FI_685_603 (atomic_line, area ratio 1.07), FI_703_747 (atomic_line, area ratio 1.08).
- The inverse solution reduces the objective cost by 14.5% relative to the initial state.
- The truth case remains within the same cost basin as the fitted case, so the fit is consistent with the benchmark physics under noise.
- Parameter recovery against the benchmark truth is weak for ne, te, F, N2e; spectral agreement is being achieved mainly through shape matching rather than absolute emissivity recovery.
- Recovered radial trends are ne: monotonic decrease from core to edge, te: non-monotonic radial structure, F: non-monotonic radial structure, N2e: non-monotonic radial structure.

## Measurement Engineering Interpretation

- nf3_benchmark_uvvis covers 300.0-820.0 nm with 0.500 nm sampling and uses 7 analysis windows.
- Fitted gain spans 0.575-0.575 with negligible offsets (max abs offset 5.767e-18).
- Mean absolute peak shift across narrow features is 0.320 nm, which is the practical wavelength-alignment indicator for the current inverse workflow.
- Signed window-area ratios can become negative for broad bands when local baseline subtraction dominates the integrated residual; treat those entries as a baseline-sensitivity flag rather than a literal negative emissivity.
- The least constrained fitted quantities are F0 (177.7% rel.), N2e0 (111.5% rel.), ne2 (97.5% rel.), N2e1 (66.7% rel.).
