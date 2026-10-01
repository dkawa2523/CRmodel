# Schuecke et al. 2025 NO/UV external-data candidate

Status: **dataset prepared; physical comparator pending**.

This is independent experimental evidence, not an OESCR validation result yet.
It intentionally has no `validation.yaml`, so the evidence audit cannot count it
as a passed comparison before a physically defensible comparator and tolerance
are fixed.

## Source and scope

The source is L. Schuecke et al., "NO densities and UV emission over the E-H
mode transition in a low-pressure inductively coupled plasma device", *Plasma
Sources Science and Technology* 34 (2025) 045015,
doi:10.1088/1361-6595/adcbd3. The article and dataset are CC BY 4.0.

The selected series is the dark-square 10 Pa power scan in figures 2 and 3:

- 16 sccm N2 and 4 sccm O2;
- rf power from 10 W to 800 W;
- absolutely calibrated UV photon production rate from OES;
- NO(X) density from LIF;
- gas temperature from OES;
- electron density and temperature from a multipole resonance probe.

The methods define the integrated UV range as 200-380 nm, while the figure 2
caption says 200-400 nm. The CSV therefore uses the neutral name
`uv_photon_rate_m3_s` and records this source inconsistency instead of silently
choosing a different spectral basis.

## Reproducible vector extraction

The public data archive was temporarily unreachable, so the plotted marker
centres were extracted from the vector objects in the open-access PDF. The PDF
SHA-256 and URLs are recorded in `source.yaml`. Raw PDF coordinates are retained
beside the converted values in `figure_2_3_10pa.csv`.

For article page 8 (PDF page 9), the conversions are:

```text
P_W   = (x - 344.5409) * 200 / 48.8691
q_UV  = (154.98455 - y) * 0.4e20 / (143.71345 - 132.44225)
n_NO  = (224.636995 - y) * 0.4e19 / (211.359495 - 198.0785)
T_g   = 200 + (304.970515 - y) * 200 / (288.692505 - 272.414495)
```

For article page 9 (PDF page 10), the conversions are:

```text
P_W                = (x - 83.40285) * 200 / 49.667
log10(n_e / 1e16)  = -3 + (157.9035 - y) / (139.508 - 121.114)
T_e                = (231.188 - y) / (212.830 - 194.472)
```

Values are rounded to the precision supported by the plot. A conservative
half-PDF-point coordinate tolerance corresponds to about 2.1 W,
1.8e18 m-3 s-1 in UV rate, 1.6e17 m-3 in NO density, 6.2 K, 0.028 decade in
electron density, and 0.028 eV. These digitization tolerances are separate from
the paper's reported experimental uncertainties of 8.9% for UV rate, 20% for
NO density, and 3% for gas temperature. The paper does not assign a quantitative
uncertainty to the probe-derived electron density or temperature.

`regime_partition` follows the paper's statement that the 10 Pa E-H transition
occurs around 200 W: points through 180 W are E-mode, 200 W is excluded as the
transition point, and points from 220 W are H-mode. It is a comparison partition,
not a new plasma-mode inference.

## Why this is not yet a quantitative pass

The integrated UV rate contains more than the NO(A-X) 236 nm band, and the paper
finds that excitation of NO(A) by N2(A) metastables dominates over direct
electron-impact excitation. N2(A) was not independently measured. Therefore:

- the total UV rate must not be compared directly with one
  `electron_impact_photon_band` component;
- N2(A) must remain an explicit input or identifiable fitted quantity in OESCR;
- a self-consistent global N2/O2 chemistry model is not introduced to fill the
  missing input;
- `n_e` or `T_e` must not be claimed as recovered from this one integrated
  observable.

The next comparator must use the original 230-237.15 nm spectral data if the
archive becomes available, or declare an external qualitative mechanism test
that is explicitly ineligible for an absolute-accuracy claim.
