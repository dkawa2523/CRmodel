# Benchmark Analysis: Cl2/Ar ICP actinometry benchmark (literature-anchored, measurement-like)

- Benchmark ID: cl2_ar_icp_fuller2001
- Source: Fuller, N.C.M.; Herman, I.P.; Donnelly, V.M., Optical actinometry of Cl2, Cl, Cl+, and Ar+ densities in inductively coupled Cl2-Ar plasmas, J. Appl. Phys. 90, 3182-3191 (2001).

## Scenario Summary

| Scenario | Cost | Mean Corr. | Mean NRMSE/std | Mean NRMSE/range | Mean Gain |
| --- | --- | --- | --- | --- | --- |
| init | 507.4590 | 0.9840 | 0.2195 | 0.0071 | 1.1358 |
| opt | 509.5416 | 0.9840 | 0.2192 | 0.0071 | 1.1334 |
| truth | 511.7007 | 0.9840 | 0.2202 | 0.0071 | 0.9375 |

## Instrument View

| Instrument | Min nm | Max nm | Bin nm | Windows | Gain Mean | Gain Min | Gain Max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cl2_benchmark_scan | 270.0000 | 885.0000 | 0.2000 | 6 | 1.1334 | 1.1334 | 1.1334 |

## Parameter Recovery

| Group | Radial Trend | Init Mean Abs Rel Err | Opt Mean Abs Rel Err | Improvement | Mean Rel. Uncertainty |
| --- | --- | --- | --- | --- | --- |
| ne | monotonic decrease from core to edge | 0.1670 | 0.1723 | -0.0316 | 0.3384 |
| te | monotonic decrease from core to edge | 0.0891 | 0.0806 | 0.0955 | 0.0446 |
| Cl | non-monotonic radial structure | 0.1899 | 0.3602 | -0.8964 | 0.1514 |
| Cl2e | monotonic decrease from core to edge | 0.1349 | 0.3133 | -1.3221 | 0.1565 |

## Window Fidelity

| Window | Kind | Mean Area Ratio | Mean Peak Ratio | Mean Abs Peak Shift nm |
| --- | --- | --- | --- | --- |
| ClII_481_986 | ionic_line | 1.0537 | 1.0532 | 0.0000 |
| ArII_480_602 | ionic_line | 0.9607 | 1.0229 | 0.0000 |
| ClI_822_200_interference | atomic_line_with_interference | 1.2456 | 1.3075 | 0.0000 |
| XeI_828_012 | actinometer_line | 1.1794 | 1.2109 | 0.0000 |
| Cl2_band_306 | molecular_band | 0.9489 | 0.3265 | 2.5200 |
| ArI_750_387 | atomic_line | 4.849e-13 | 5.510e-13 | 0.4400 |

## Plasma OES Interpretation

- Dominant measured features are ClII_481_986 (ionic_line, area ratio 1.05), ArII_480_602 (ionic_line, area ratio 0.96), ClI_822_200_interference (atomic_line_with_interference, area ratio 1.25).
- The inverse solution does not materially improve the objective cost relative to the initial state.
- The truth case remains within the same cost basin as the fitted case, so the fit is consistent with the benchmark physics under noise.
- Parameter recovery against the benchmark truth is weak for ne, te, Cl, Cl2e; spectral agreement is being achieved mainly through shape matching rather than absolute emissivity recovery.
- Recovered radial trends are ne: monotonic decrease from core to edge, te: monotonic decrease from core to edge, Cl: non-monotonic radial structure, Cl2e: monotonic decrease from core to edge.

## Measurement Engineering Interpretation

- cl2_benchmark_scan covers 270.0-885.0 nm with 0.200 nm sampling and uses 6 analysis windows.
- Fitted gain spans 1.133-1.133 with negligible offsets (max abs offset 4.715e-16).
- Mean absolute peak shift across narrow features is 0.088 nm, which is the practical wavelength-alignment indicator for the current inverse workflow.
- The least constrained fitted quantities are ne2 (40.4% rel.), ne0 (32.3% rel.), ne1 (28.8% rel.), Cl2e0 (20.1% rel.).
