# Benchmark Analysis: Cl2/Ar ICP actinometry benchmark (literature-anchored, measurement-like)

- Benchmark ID: cl2_ar_icp_fuller2001
- Source: Fuller, N.C.M.; Herman, I.P.; Donnelly, V.M., Optical actinometry of Cl2, Cl, Cl+, and Ar+ densities in inductively coupled Cl2-Ar plasmas, J. Appl. Phys. 90, 3182-3191 (2001).

## Scenario Summary

| Scenario | Cost | Mean Corr. | Mean NRMSE/std | Mean NRMSE/range | Mean Gain |
| --- | --- | --- | --- | --- | --- |
| init | 506.2716 | 0.9840 | 0.2192 | 0.0071 | 1.1356 |
| opt | 506.1738 | 0.9840 | 0.2192 | 0.0071 | 1.1356 |
| truth | 507.0948 | 0.9840 | 0.2194 | 0.0071 | 0.9412 |

## Instrument View

| Instrument | Min nm | Max nm | Bin nm | Windows | Gain Mean | Gain Min | Gain Max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cl2_benchmark_scan | 270.0000 | 885.0000 | 0.2000 | 6 | 1.1356 | 1.1154 | 1.1480 |

## Parameter Recovery

| Group | Radial Trend | Init Mean Abs Rel Err | Opt Mean Abs Rel Err | Improvement | Mean Rel. Uncertainty |
| --- | --- | --- | --- | --- | --- |
| ne | monotonic decrease from core to edge | 0.1670 | 0.1588 | 0.0489 | 0.9074 |
| te | monotonic decrease from core to edge | 0.0891 | 0.0897 | -0.0072 | 0.0803 |
| Cl | monotonic decrease from core to edge | 0.1899 | 0.1899 | 2.459e-05 | 0.2227 |
| Cl2e | monotonic decrease from core to edge | 0.1349 | 0.1349 | -9.867e-05 | 0.2168 |

## Window Fidelity

| Window | Kind | Mean Area Ratio | Mean Peak Ratio | Mean Abs Peak Shift nm |
| --- | --- | --- | --- | --- |
| ClII_481_986 | ionic_line | 1.0555 | 1.0550 | 0.0000 |
| ArII_480_602 | ionic_line | 0.9624 | 1.0245 | 0.0000 |
| ClI_822_200_interference | atomic_line_with_interference | 0.9586 | 0.9916 | 0.0000 |
| XeI_828_012 | actinometer_line | 1.1813 | 1.2130 | 0.0000 |
| Cl2_band_306 | molecular_band | 1.1612 | 0.3982 | 2.5200 |
| ArI_750_387 | atomic_line | 4.767e-13 | 5.452e-13 | 0.4400 |

## Plasma OES Interpretation

- Dominant measured features are ClII_481_986 (ionic_line, area ratio 1.06), ArII_480_602 (ionic_line, area ratio 0.96), ClI_822_200_interference (atomic_line_with_interference, area ratio 0.96).
- The inverse solution reduces the objective cost by 0.0% relative to the initial state.
- The truth case remains within the same cost basin as the fitted case, so the fit is consistent with the benchmark physics under noise.
- Parameter recovery against the benchmark truth is weak for ne, te, Cl, Cl2e; spectral agreement is being achieved mainly through shape matching rather than absolute emissivity recovery.
- Recovered radial trends are ne: monotonic decrease from core to edge, te: monotonic decrease from core to edge, Cl: monotonic decrease from core to edge, Cl2e: monotonic decrease from core to edge.

## Measurement Engineering Interpretation

- cl2_benchmark_scan covers 270.0-885.0 nm with 0.200 nm sampling and uses 6 analysis windows.
- Fitted gain spans 1.115-1.148 with negligible offsets (max abs offset 6.097e-16).
- Mean absolute peak shift across narrow features is 0.088 nm, which is the practical wavelength-alignment indicator for the current inverse workflow.
- The least constrained fitted quantities are ne2 (154.9% rel.), ne0 (65.4% rel.), ne1 (52.0% rel.), Cl2e0 (31.9% rel.).
