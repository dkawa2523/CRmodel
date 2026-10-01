# Arellano et al. 2023 Ar-CCP line-ratio candidate

Status: **dataset prepared; model-input closure pending**.

This directory contains a held-out experimental line-ratio series, not an
OESCR validation result. It intentionally has no `validation.yaml`; therefore
the evidence audit cannot count it as an external quantitative pass.

## Source and measurement contract

The source is F. J. Arellano et al., "First-principles simulation of optical
emission spectra for low-pressure argon plasmas and its experimental
validation", *Plasma Sources Science and Technology* 32 (2023) 125007,
doi:10.1088/1361-6595/ad0ede.

The selected observable is the experimental figure-10 ratio
`I(763.5 nm) / I(750.4 nm)` from a geometrically symmetric Ar CCP:

- 2-100 Pa Ar at 1 sccm;
- 13.56 MHz, 300 V peak-to-peak excitation;
- light collected from the central approximately 1 cm diameter region;
- wavelength-response correction from a certified total-flux calibration
  source, but no absolute intensity calibration.

The ratio is therefore classified as `relative_intensity` with
`relative_response_corrected` calibration. It must not be treated as spectral
radiance or as an absolute electron-density observable.

## Reproducible vector extraction

The article states that supporting data are available from the authors on
reasonable request rather than from a public repository. Marker centres were
therefore extracted from vector objects in figure 10 (article/PDF page 13).
The source PDF SHA-256 and raw PDF coordinates are retained in `source.yaml`
and `figure_10_oes_ratio.csv`.

For the plot bounds and ticks, the coordinate conversion is:

```text
pressure_Pa = 10 ** (2 * (x - 330.051) / (543.733 - 330.051))
ratio       = (239.691 - y) / 28.467
```

Pressure values are rounded to the experimental set points identified by the
logarithmic marker positions. A conservative half-PDF-point digitization
tolerance is 0.0047 decade in pressure and 0.0176 in the line ratio. This is
only digitization uncertainty; the paper does not report an experimental
uncertainty for the plotted ratios.

## Intended OESCR use and current blocker

The paper shows that the ratio is nearly insensitive to discharge conditions
at 10 Pa and below. That subset is useful as an atomic-data and relative
spectral-response check, not as a `T_e`, `n_e`, or EEDF diagnostic. Above
about 20 Pa, the 763.5 nm path becomes strongly sensitive to the Ar 1s5
metastable population, so the full pressure trend is a metastable-pathway
challenge.

OESCR already contains the 750.4 and 763.5 nm pathways and accepts Ar 1s5 as
an explicit source density. Preparing this candidate exposed and corrected a
pre-existing level-label error: NIST ASD assigns 763.5106 nm to `2p6 -> 1s5`,
not `2p2 -> 1s5`. The example state ID, level energy, transition probability,
and associated seed filenames now use `2p6` consistently.

The NIST level and transition data now live in the reusable
`examples/data/species_packs/ar_2p1_2p6_nist.yaml` pack. It contains every
listed radiative branch from the selected upper levels, rather than only the
two observed lines. With the current NIST values, the 750.4 nm branch fraction
is 0.9948 and the 763.5 nm branch fraction is 0.7135. The latter correction is
material to the ratio and is now exercised by a regression test.

`chilton_1998_ground_2p1_2p6_table4.csv` records the independent direct
ground-state excitation anchors used by the Arellano CRM at 20, 40, and
100 eV. It is deliberately not interpolated into a replacement excitation
curve: three high-energy points do not close the near-threshold rate integral.
The existing effective seeds differ from these anchors by factors of
3.66/8.83/0.84 for 2p1 and 7.70/16.21/1.69 for 2p6 at 20/40/100 eV. This large,
energy-dependent mismatch is a failed input-qualification check, not a reason
to tune the seeds to the held-out line ratios.

## Independent cross-section model check

The production LXCat BSR catalog identifies the required 2014 Ar processes as
62286 for 2p1 (`Ar -> Ar(4p'[1/2]0)`) and 62281 for 2p6
(`Ar -> Ar(4p[3/2]2)`). The production download was compared point-for-point
with the earlier API snapshot: all 196 and 218 rows agree exactly. Stable
numeric digests, row counts, native thresholds, update date, and process IDs
are fixed in `source.yaml`.

The independent LXCat NGFSRDW model supplies the same direct ground-state
quantities through processes 2560 for 2p1 and 2567 for 2p6. These 17-point
curves are the relativistic-distorted-wave results associated with Kaur et al.
(1998), not optical-emission cross sections with cascade folded in. Their
process labels, thresholds, row counts, and numeric digests are also fixed in
`source.yaml`.

Published optical-emission cross sections were not substituted as a third
curve because they can include cascade feeding and pressure-dependent
radiation trapping. Those effects belong in the next population-model
sensitivity step; mixing them into a direct-excitation ensemble would obscure
which responsibility produced the difference.

LXCat does not authorize third-party redistribution of its database contents,
so none of the raw curves are packaged here. Download the two selected BSR
processes and the two selected NGFSRDW processes separately as
`Cross section.txt`; the evaluator parses both native files and rejects a
changed process label, row count, or numeric digest. No smoothing, amplitude
rescaling, or fit to figure 10 is applied.

These are theoretical reference curves, not uncertainty-bearing experimental
replacements. At 20/40/100 eV, BSR divided by the Chilton direct-excitation
anchor is 0.37/0.57/0.62 for 2p1 and 0.42/0.72/0.82 for 2p6. The disagreement
is smaller than for the old effective seeds but remains energy dependent and
cannot be represented by one scale factor. NGFSRDW divided by the same anchors
is 11.28/6.03/2.76 for 2p1 and 1.78/0.83/0.83 for 2p6. The two theoretical
families therefore disagree mainly in the relative excitation of 2p1, not by
a common normalization.

`scripts/assess_arellano_atomic_model.py` evaluates a deliberately narrow
direct-ground-state corona limit using both model families and all NIST
radiative branches. Maxwellian and Druyvesteyn families are compared at the
same mean energies (3, 4.5, 6, 7.5, 9, and 12 eV), and every curve is evaluated
on both its native threshold and the NIST upper-level threshold. Cross sections
are linearly interpolated only over their tabulated support and are forced to
zero below the declared threshold.

For native-threshold Maxwellian cases, the untuned BSR ratio is 0.719, 0.649,
0.619, 0.604, 0.596, and 0.585. Its full EEDF/threshold envelope remains
0.585-1.202. The corresponding NGFSRDW envelope is 0.115-0.321 and never
overlaps the four low-pressure measurements at 0.584-0.697. At identical
EEDF/threshold conditions the predicted ratios differ by factors of
3.68-5.09. Threshold alignment is small compared with both EEDF shape and the
cross-section-model choice.

The combined 0.115-1.202 span is a source-qualified sensitivity bound, not a
probability interval and not permission to select the model that matches the
held-out observations. BSR overlap shows that the atomic pathway is plausible;
NGFSRDW disagreement shows that this conclusion is not robust to the selected
direct-excitation model. Cross-section model discrepancy is now explicit
rather than hidden behind one theoretical dataset.

## Cascade and neutral-quenching sensitivity

Two omitted population terms are now assessed without fitting figure 10.
Arellano table 3 gives the state-specific neutral-Ar quenching coefficients
`1.6e-17 m3/s` for 2p1 and `1.3e-17 m3/s` for 2p6. Combining them with the
measured 2-100 Pa pressure points, the reported 304-350 K gas-temperature
range, and the complete NIST radiative rates gives a maximum change in the
763.5/750.4 ratio of `6.29e-5` at 10 Pa and below, and `6.24e-4` over the full
2-100 Pa range. Neutral-Ar quenching is therefore negligible for this ratio
under the isolated optically thin corona balance. This calculation does not
claim to include feedback through the coupled 1s/2p system.

Chilton table III supplies a different kind of evidence: at 40 eV and 1 mTorr,
the measured cascade/direct source ratios are 6.3/31 for 2p1 and 20/22 for
2p6. Their nominal effect would multiply the line ratio by 1.587. Taking every
quoted error bar to its independent adverse endpoint gives an arithmetic
1.167-2.353 multiplier envelope; it is not a probability interval. Because
Chilton also observes pressure-dependent cascade through radiation trapping,
this monoenergetic 1 mTorr result is retained as a materiality check and is not
applied to the broad-EEDF predictions at 2-100 Pa. The immutable SI values are
stored in `chilton_1998_cascade_2p1_2p6_table3.csv`.

Reproduce the checked-in diagnostic artifact with:

```bash
python scripts/assess_arellano_atomic_model.py \
  --bsr-download "/path/to/bsr/Cross section.txt" \
  --ngfsrdw-download "/path/to/ngfsrdw/Cross section.txt" \
  --output examples/validation/arellano_2023_ar_ccp/atomic_model_assessment.json
```

Consequently, the general example excitation curves remain
literature-anchored effective seeds, and user-supplied BSR/NGFSRDW curves
remain uncertainty-free theoretical references. This experiment also does not
provide an independently closed EEDF plus metastable-density input for every pressure.
Fitting those inputs to figure 10 and then scoring the same points would not be
held-out validation. The candidate therefore remains `conditional` until:

1. a candidate-local, pressure-applicable cascade source is obtained or
   calculated from state-resolved higher-level excitation and branching data;
2. an uncertainty-bearing near-threshold experimental excitation reference
   resolves or quantitatively weights the BSR/NGFSRDW discrepancy, and an
   independently measured EEDF or declared EEDF-family bound closes the
   low-energy shape ambiguity;
3. any high-pressure comparison receives an independent Ar 1s5 density and a
   declared radiation-trapping treatment.

No global plasma-chemistry model is added to manufacture the missing inputs.
