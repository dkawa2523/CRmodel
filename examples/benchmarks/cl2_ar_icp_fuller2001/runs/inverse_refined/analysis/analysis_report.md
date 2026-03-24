# Benchmark Analysis: Cl2/Ar ICP actinometry benchmark (literature-anchored, measurement-like)

- Benchmark ID: cl2_ar_icp_fuller2001
- Source: Fuller, N.C.M.; Herman, I.P.; Donnelly, V.M., Optical actinometry of Cl2, Cl, Cl+, and Ar+ densities in inductively coupled Cl2-Ar plasmas, J. Appl. Phys. 90, 3182-3191 (2001).

## Scenario Summary

| Scenario | Cost | Mean Corr. | Mean NRMSE/std | Mean NRMSE/range | Mean Gain |
| --- | --- | --- | --- | --- | --- |
| init | 507.4403 | 0.9840 | 0.2195 | 0.0071 | 1.1358 |
| opt | 507.3607 | 0.9840 | 0.2195 | 0.0071 | 1.1358 |
| truth | 509.8125 | 0.9840 | 0.2202 | 0.0071 | 0.9375 |

## Instrument View

| Instrument | Min nm | Max nm | Bin nm | Windows | Gain Mean | Gain Min | Gain Max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cl2_benchmark_scan | 270.0000 | 885.0000 | 0.2000 | 6 | 1.1358 | 1.1358 | 1.1358 |

## Parameter Recovery

| Group | Radial Trend | Init Mean Abs Rel Err | Opt Mean Abs Rel Err | Improvement | Mean Rel. Uncertainty |
| --- | --- | --- | --- | --- | --- |
| ne | monotonic decrease from core to edge | 0.1670 | 0.1588 | 0.0489 | 0.9496 |
| te | monotonic decrease from core to edge | 0.0891 | 0.0897 | -0.0072 | 0.0673 |
| Cl | monotonic decrease from core to edge | 0.1899 | 0.1899 | 1.771e-05 | 0.2198 |
| Cl2e | monotonic decrease from core to edge | 0.1349 | 0.1349 | -1.703e-04 | 0.1736 |

## Window Fidelity

| Window | Kind | Mean Area Ratio | Mean Peak Ratio | Mean Abs Peak Shift nm |
| --- | --- | --- | --- | --- |
| ClII_481_986 | ionic_line | 1.0559 | 1.0555 | 0.0000 |
| ArII_480_602 | ionic_line | 0.9628 | 1.0251 | 0.0000 |
| ClI_822_200_interference | atomic_line_with_interference | 0.9590 | 0.9920 | 0.0000 |
| XeI_828_012 | actinometer_line | 1.1819 | 1.2135 | 0.0000 |
| Cl2_band_306 | molecular_band | 1.1631 | 0.3991 | 2.5200 |
| ArI_750_387 | atomic_line | 4.773e-13 | 5.447e-13 | 0.4400 |

## Plasma OES Interpretation

- Dominant measured features are ClII_481_986 (ionic_line, area ratio 1.06), ArII_480_602 (ionic_line, area ratio 0.96), ClI_822_200_interference (atomic_line_with_interference, area ratio 0.96).
- The inverse solution reduces the objective cost by 0.0% relative to the initial state.
- The truth case remains within the same cost basin as the fitted case, so the fit is consistent with the benchmark physics under noise.
- Parameter recovery against the benchmark truth is weak for ne, te, Cl, Cl2e; spectral agreement is being achieved mainly through shape matching rather than absolute emissivity recovery.
- Recovered radial trends are ne: monotonic decrease from core to edge, te: monotonic decrease from core to edge, Cl: monotonic decrease from core to edge, Cl2e: monotonic decrease from core to edge.

## Measurement Engineering Interpretation

- cl2_benchmark_scan covers 270.0-885.0 nm with 0.200 nm sampling and uses 6 analysis windows.
- Fitted gain spans 1.136-1.136 with negligible offsets (max abs offset 4.698e-16).
- Mean absolute peak shift across narrow features is 0.088 nm, which is the practical wavelength-alignment indicator for the current inverse workflow.
- The least constrained fitted quantities are ne2 (155.8% rel.), ne0 (84.0% rel.), ne1 (45.0% rel.), Cl0 (31.8% rel.).
