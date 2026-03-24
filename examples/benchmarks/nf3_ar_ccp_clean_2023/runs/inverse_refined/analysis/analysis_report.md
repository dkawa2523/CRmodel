# Benchmark Analysis: NF3/Ar CCP chamber-clean benchmark (literature-anchored, measurement-like)

- Benchmark ID: nf3_ar_ccp_clean_2023
- Source: An, S.; Hong, S.J., Spectroscopic Analysis of NF3 Plasmas with Oxygen Additive for PECVD Chamber Cleaning, Coatings 13(1), 91 (2023).

## Scenario Summary

| Scenario | Cost | Mean Corr. | Mean NRMSE/std | Mean NRMSE/range | Mean Gain |
| --- | --- | --- | --- | --- | --- |
| init | 435.5756 | 0.9906 | 0.1679 | 0.0117 | 4.0939 |
| opt | 435.1080 | 0.9906 | 0.1679 | 0.0117 | 4.0939 |
| truth | 375.4522 | 0.9911 | 0.1564 | 0.0109 | 1.0405 |

## Instrument View

| Instrument | Min nm | Max nm | Bin nm | Windows | Gain Mean | Gain Min | Gain Max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| nf3_benchmark_uvvis | 300.0000 | 820.0000 | 0.5000 | 7 | 4.0939 | 4.0939 | 4.0939 |

## Parameter Recovery

| Group | Radial Trend | Init Mean Abs Rel Err | Opt Mean Abs Rel Err | Improvement | Mean Rel. Uncertainty |
| --- | --- | --- | --- | --- | --- |
| ne | monotonic decrease from core to edge | 0.1831 | 0.1831 | 3.184e-15 | 0.1196 |
| te | monotonic decrease from core to edge | 0.1160 | 0.1160 | 0.0000 | 0.0045 |
| F | monotonic decrease from core to edge | 0.1498 | 0.1498 | 0.0000 | 0.1928 |
| N2e | monotonic decrease from core to edge | 0.1628 | 0.1628 | 2.216e-15 | 0.1342 |

## Window Fidelity

| Window | Kind | Mean Area Ratio | Mean Peak Ratio | Mean Abs Peak Shift nm |
| --- | --- | --- | --- | --- |
| N2_FP_550_700 | broadband_window | -1.0086 | 1.0703 | 0.0000 |
| FI_685_603 | atomic_line | 1.1076 | 1.1132 | 0.0000 |
| FI_703_747 | atomic_line | 1.1155 | 1.0752 | 0.3000 |
| FI_712_789 | atomic_line | 1.1208 | 1.1195 | 0.3000 |
| N2_SPS_300_400 | broadband_window | 2.2077 | 0.8777 | 17.9000 |
| ArI_811_531 | atomic_line | 4.1651 | 2.3199 | 0.4000 |
| ArI_750_387 | atomic_line | 1.246e-13 | 1.787e-14 | 0.6000 |

## Plasma OES Interpretation

- Dominant measured features are N2_FP_550_700 (broadband_window, area ratio -1.01), FI_685_603 (atomic_line, area ratio 1.11), FI_703_747 (atomic_line, area ratio 1.12).
- The inverse solution reduces the objective cost by 0.1% relative to the initial state.
- The truth case remains within the same cost basin as the fitted case, so the fit is consistent with the benchmark physics under noise.
- Parameter recovery against the benchmark truth is weak for ne, te, F, N2e; spectral agreement is being achieved mainly through shape matching rather than absolute emissivity recovery.
- Recovered radial trends are ne: monotonic decrease from core to edge, te: monotonic decrease from core to edge, F: monotonic decrease from core to edge, N2e: monotonic decrease from core to edge.

## Measurement Engineering Interpretation

- nf3_benchmark_uvvis covers 300.0-820.0 nm with 0.500 nm sampling and uses 7 analysis windows.
- Fitted gain spans 4.094-4.094 with negligible offsets (max abs offset 3.143e-16).
- Mean absolute peak shift across narrow features is 0.320 nm, which is the practical wavelength-alignment indicator for the current inverse workflow.
- Signed window-area ratios can become negative for broad bands when local baseline subtraction dominates the integrated residual; treat those entries as a baseline-sensitivity flag rather than a literal negative emissivity.
- The least constrained fitted quantities are F2 (32.0% rel.), ne0 (19.3% rel.), F0 (15.5% rel.), N2e1 (14.9% rel.).
