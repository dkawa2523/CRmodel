# Benchmark Analysis: Cl2/Ar ICP actinometry benchmark (literature-anchored, measurement-like)

- Benchmark ID: cl2_ar_icp_fuller2001
- Source: Fuller, N.C.M.; Herman, I.P.; Donnelly, V.M., Optical actinometry of Cl2, Cl, Cl+, and Ar+ densities in inductively coupled Cl2-Ar plasmas, J. Appl. Phys. 90, 3182-3191 (2001).

## Scenario Summary

| Scenario | Cost | Mean Corr. | Mean NRMSE/std | Mean NRMSE/range | Mean Gain |
| --- | --- | --- | --- | --- | --- |
| init | 507.4403 | 0.9840 | 0.2195 | 0.0071 | 1.1358 |
| opt | 496.2075 | 0.9840 | 0.2196 | 0.0071 | 1.1346 |
| truth | 509.8125 | 0.9840 | 0.2202 | 0.0071 | 0.9375 |

## Instrument View

| Instrument | Min nm | Max nm | Bin nm | Windows | Gain Mean | Gain Min | Gain Max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cl2_benchmark_scan | 270.0000 | 885.0000 | 0.2000 | 6 | 1.1346 | 1.1346 | 1.1346 |

## Parameter Recovery

| Group | Radial Trend | Init Mean Abs Rel Err | Opt Mean Abs Rel Err | Improvement | Mean Rel. Uncertainty |
| --- | --- | --- | --- | --- | --- |
| ne | non-monotonic radial structure | 0.1670 | 0.5005 | -1.9970 | 0.9780 |
| te | monotonic decrease from core to edge | 0.0891 | 0.5265 | -4.9093 | 0.0145 |
| Cl | monotonic decrease from core to edge | 0.1899 | 0.4807 | -1.5307 | 0.0050 |
| Cl2e | non-monotonic radial structure | 0.1349 | 0.5863 | -3.3452 | 0.0064 |

## Window Fidelity

| Window | Kind | Mean Area Ratio | Mean Peak Ratio | Mean Abs Peak Shift nm |
| --- | --- | --- | --- | --- |
| ClII_481_986 | ionic_line | 1.0548 | 1.0544 | 0.0000 |
| ArII_480_602 | ionic_line | 0.9618 | 1.0240 | 0.0000 |
| ClI_822_200_interference | atomic_line_with_interference | 1.0586 | 1.1032 | 0.0000 |
| XeI_828_012 | actinometer_line | 1.1807 | 1.2122 | 0.0000 |
| Cl2_band_306 | molecular_band | 1.0026 | 0.3486 | 2.5200 |
| ArI_750_387 | atomic_line | 1.186e-14 | 9.104e-15 | 0.4400 |

## Plasma OES Interpretation

- Dominant measured features are ClII_481_986 (ionic_line, area ratio 1.05), ArII_480_602 (ionic_line, area ratio 0.96), ClI_822_200_interference (atomic_line_with_interference, area ratio 1.06).
- The inverse solution reduces the objective cost by 2.2% relative to the initial state.
- The truth case remains within the same cost basin as the fitted case, so the fit is consistent with the benchmark physics under noise.
- Parameter recovery against the benchmark truth is weak for ne, te, Cl, Cl2e; spectral agreement is being achieved mainly through shape matching rather than absolute emissivity recovery.
- Recovered radial trends are ne: non-monotonic radial structure, te: monotonic decrease from core to edge, Cl: monotonic decrease from core to edge, Cl2e: non-monotonic radial structure.

## Measurement Engineering Interpretation

- cl2_benchmark_scan covers 270.0-885.0 nm with 0.200 nm sampling and uses 6 analysis windows.
- Fitted gain spans 1.135-1.135 with negligible offsets (max abs offset 4.690e-16).
- Mean absolute peak shift across narrow features is 0.088 nm, which is the practical wavelength-alignment indicator for the current inverse workflow.
- The least constrained fitted quantities are ne2 (136.3% rel.), ne1 (135.3% rel.), ne0 (21.8% rel.), te2 (2.0% rel.).
