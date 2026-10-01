# Scientific validation status

This document separates numerical correctness, model self-consistency, and
external scientific validation. Passing a generated benchmark does not by
itself validate an OESCR inference against a real plasma.

## Evidence levels

| Level | Meaning | Current evidence |
|---|---|---|
| Analytic kernel | A closed-form solution or conservation identity is reproduced | two-level CR, three-level cascade, radiative branching, physical band power |
| Numerical qualification | The configured discretization is stable under refinement | opt-in energy- and wavelength-grid convergence |
| Generated end-to-end | Forward and inverse workflows recover internally generated observations | NF3/Ar and Cl2/Ar workflow benchmarks |
| External comparison | Predictions are compared with held-out literature or calibrated measurements | two independent datasets are prepared; neither comparator is physically closed yet |

## Evidence declaration and audit

Each qualification dataset uses `validation.yaml` to declare its evidence
level, source, data origin, hold-out status, measurement basis, calibration,
preprocessing, file hashes, model-input closure, evaluation-data use, evaluator
hash/version, result contract, acceptance metrics, and limitations.
`scripts/audit_validation_evidence.py` verifies the declaration and artifacts.
It reports reproducibility and external-quantitative eligibility separately.
Generated analysis summaries also contain an `analysis_contract` that hashes
the truth configuration, measurements, benchmark metadata, windows, metric
definitions, and analysis policy. Candidate case, inverse, fitted parameters,
fit result, and package version are recorded separately in `run_fingerprint`.
Between-run comparison is allowed only when the contracts match.

The current NF3/Ar and Cl2/Ar packages pass as immutable generated
self-consistency evidence. They correctly fail external-quantitative
eligibility because their spectra are generated, not held out, use synthetic
detector counts, and have no experimental response calibration in the packaged
data.

External quantitative eligibility additionally requires `closed` model inputs
and `held_out_only` evaluation data. `held_out: true` alone is insufficient:
an unknown source density, EEDF, or discrepancy term must not be fitted on the
same observations that are then scored as validation.

## Prepared external candidates

The v1 dataset-selection gate was applied on 2026-09-30 before adding another
comparator:

| Candidate | Calibrated observable | Independent required inputs | Quantified uncertainty for the claim | Reproducible source data | Claim already supported by OESCR | v1 decision |
|---|---|---|---|---|---|---|
| Schuecke N2/O2 | yes, absolute photon production | no; dominant N2(A) density is not measured | partial; probe `n_e`/`T_e` uncertainty is missing | figure-derived artifact is reproducible; public archive retrieval remains incomplete | conditional physical-band path | not eligible (`open`) |
| Arellano Ar | yes, relative response | no; EEDF and pressure-applicable cascade input are not independently closed | no; plotted ratio and theoretical curves lack a usable uncertainty model | extracted ratio and licensed-input identities are reproducible | yes, a two-line relative atomic-pathway check | not eligible (`conditional`) |

Consequently OESCR v1 makes **no external quantitative accuracy claim**. This
is the completed outcome of the selection phase, not a failed platform test.
The candidates remain mechanism and sensitivity evidence at the boundaries
below; no missing chemistry is added merely to force a comparator to pass.

### Schuecke et al. 2025 N2/O2 ICP

`examples/validation/schuecke_2025_no_uv` contains a held-out 10 Pa N2/O2
power scan from Schuecke et al. (2025). The vector figures provide absolute UV
photon production rate, LIF NO density, OES gas temperature, and independently
probe-derived electron density and temperature. Raw PDF coordinates, affine
axis conversions, source and artifact hashes, reported measurement uncertainty,
and a separate digitization tolerance are retained.

This candidate deliberately has no `validation.yaml`: data preparation is
complete, but a quantitative OESCR comparison is not. The integrated UV value
is a volumetric photon rate rather than spectral radiance, so
`volumetric_photon_rate` is now an explicit evidence basis. More importantly,
the source attributes NO(A) excitation mainly to N2(A) metastables, whose
density was not independently measured. Treating the signal as a single direct
electron-impact band, or adding an undeclared global chemistry solver, would
make the comparison physically misleading. The candidate is therefore held at
`dataset_prepared_comparator_pending` until the narrow-band data and reduced
mechanism boundary are fixed.

The public repository metadata identifies a 235.97 MB archive, but repeated
resumable downloads timed out or were reset. The vector-derived artifact is
therefore retained rather than replaced by a partial archive. Its model-input
closure is now explicitly `open`.

### Arellano et al. 2023 Ar CCP

`examples/validation/arellano_2023_ar_ccp` contains the response-corrected
experimental `I(763.5 nm) / I(750.4 nm)` pressure series from figure 10. The
source used the same optical path for a certified wavelength-response
calibration, but did not perform absolute intensity calibration. Raw vector
coordinates, affine/log-axis conversions, source and artifact hashes, and a
separate digitization tolerance are retained.

This observable maps directly to the Ar 763.5 and 750.4 nm pathways already in
OESCR. Candidate preparation exposed a pre-existing atomic-label error:
763.5106 nm is Ar `2p6 -> 1s5`, not `2p2 -> 1s5`. The example state, energy,
transition probability, seed filenames, and regression test now follow NIST
ASD. A shared atomic-data pack now contains all five NIST-listed branches from
2p1 and 2p6. The observed-line branch fractions are 0.9948 for 750.4 nm and
0.7135 for 763.5 nm, so the latter is not interchangeable with the total 2p6
decay rate. At 10 Pa and below the published ratio is approximately 0.58-0.70 and is
reported to depend mainly on atomic data, so it is an atomic-data and relative
response check rather than an electron-temperature or density diagnostic.
Above about 20 Pa it becomes strongly sensitive to Ar 1s5 metastables. The
candidate has no `validation.yaml` because the packaged excitation curves are
effective seeds rather than validation-grade state-resolved data. Against the
Chilton et al. direct-excitation anchors at 20/40/100 eV, their ratios are
3.66/8.83/0.84 for 2p1 and 7.70/16.21/1.69 for 2p6. This is a failed atomic
input check, not a tolerance to absorb.

Production LXCat BSR-500 and NGFSRDW state-resolved theoretical curves are used
separately from the general example seeds. BSR processes 62286/62281 retain
their verified 196/218 points; NGFSRDW processes 2560/2567 add independent
17-point relativistic-distorted-wave curves for the same direct ground-state
2p1/2p6 excitations. Because LXCat forbids third-party redistribution, raw
curves are not packaged. The evaluator accepts separate native downloads and
verifies process labels, row counts, and numeric digests before calculation.
BSR divided by the Chilton anchors is 0.37/0.57/0.62 for 2p1 and
0.42/0.72/0.82 for 2p6; NGFSRDW gives 11.28/6.03/2.76 and
1.78/0.83/0.83, respectively. The discrepancy is state- and energy-dependent,
not a shared amplitude factor.

The direct-ground-state corona assessment compares Maxwellian and Druyvesteyn
EEDFs at equal mean energies and evaluates native-model and NIST-aligned
thresholds. The BSR envelope is 0.585-1.202 and overlaps the 2-10 Pa
observations at 0.584-0.697. The NGFSRDW envelope is 0.115-0.321 and does not.
At otherwise identical conditions the two models differ in predicted ratio by
factors of 3.68-5.09. The combined 0.115-1.202 span is a diagnostic bound, not
a probability interval or a tolerance. It demonstrates that cross-section
model choice dominates threshold alignment and is comparable to or larger
than the declared EEDF-shape effect. This is useful mechanism evidence, but
not a pass: neither curve family has supplied uncertainty, the experimental
EEDF is not independently closed, and a pressure-applicable cascade source is
not available.

The Arellano table-3 neutral-Ar quenching coefficients are now evaluated
against the measured pressure points and 304-350 K gas-temperature range. The
state-dependent loss changes the selected line ratio by at most `6.29e-5` at
10 Pa and below, and by `6.24e-4` over 2-100 Pa, in the isolated optically thin
corona balance. This term is negligible at the present precision. In contrast,
the Chilton table-III 40 eV, 1 mTorr cascade/direct anchors imply a nominal
line-ratio multiplier of 1.587 and an arithmetic reported-error corner envelope
of 1.167-2.353. Because the cascade is pressure dependent and monoenergetic,
that result is retained as materiality evidence and is not transferred into
the broad-EEDF 2-100 Pa predictions.
Model input closure therefore remains `conditional`; tuning those inputs on
the same line ratios would be rejected by the evidence contract.

## Closed-form CR fixtures

The two-level fixture supplies an external ground-state density `n_G`, a pump
frequency `S`, radiative loss `A`, and quenching loss `Q`. The expected excited
population is

\[
n_U = \frac{S n_G}{A + Q}.
\]

The test checks the assembled matrix and RHS, population, solver residual, and
state-by-state source/loss balance independently.

The three-level fixture adds an upper-to-middle branch `A_UM`, an
upper-to-ground branch `A_UG`, and a middle-to-ground decay `A_MG`:

\[
n_U = \frac{S n_G}{A_{UM}+A_{UG}}, \qquad
n_M = \frac{A_{UM}n_U}{A_{MG}}.
\]

It also converts integrated line emissivity back to photon production rate and
checks

\[
\frac{R_{UM}}{R_{UG}} = \frac{A_{UM}}{A_{UG}}, \quad
R_{UM}+R_{UG}=S n_G, \quad R_{MG}=R_{UM}.
\]

These fixtures validate the reduced linear CR assembly and emission conversion;
they do not validate any particular cross-section dataset or plasma composition.

## Grid qualification

Case diagnostics can independently refine the EEDF energy grid and internal
wavelength grid. Spectra are compared on the same instrument output bins using
the maximum relative L2 difference. This is opt-in because it requires two
additional complete forward solves. A reported result should retain the grid
sizes, refinement factors, differences, and warn/error thresholds.

## Line-set observability

Observability is evaluated from a finite-difference Jacobian of measurement
residuals only. Priors, profile smoothing, and gain-tilt penalties are excluded
because they add assumptions rather than experimental information. The report
contains parameter column norms plus named right-singular vectors, so an
unobservable or weak combination can be identified instead of being hidden
behind a single rank value. The Laplace calculation separately uses the full
objective Jacobian and remains a conditional-curvature statement.

The current generated benchmark audit found:

| Benchmark | Removed from fit | Optimized data-only rank | Condition number | Interpretation |
|---|---|---:|---:|---|
| Cl2/Ar | `ne_shells_m3`, `te_shells_eV`, fixed Ar-metastable prior | 6/6 | 59.5 | fitted Cl and Cl2-emitter profiles are locally resolved by the packaged observations |
| NF3/Ar | `ne_shells_m3`, fixed Ar-metastable prior | 9/9 | 3.15e6 | full numerical rank, but the weakest Te/F combinations are fragile and require stronger experimental evidence |

These numbers qualify the generated configurations and their chosen parameter
scales; they are not transferable accuracy claims for a real plasma. Within
each newly generated run, optimization changes Cl2/Ar pair classification from
0.667 to 0.867 and NF3/Ar from 0.900 to 1.000. Window classification remains
0.955 for both; mean normalized spectral error changes from 0.2030 to 0.2025
for Cl2/Ar and from 0.1561 to 0.1425 for NF3/Ar. Unversioned historical
summaries are no longer accepted by the gate; they must be regenerated under
the same analysis contract before a between-run comparison.

## Current scientific limits

- Literature-anchored NF3/Ar and Cl2/Ar packages remain generated,
  measurement-like workflow benchmarks rather than held-out calibrated data.
- Absolute electron density is interpretable only with dimensional instrument
  calibration, constrained source densities, and demonstrated local rank.
- Tabulated EEDF inversion still requires an explicit resolution and
  regularization statement plus a demonstrated kernel rank.
- Cross-section provenance and grid coverage are recorded. The Ar candidate
  now demonstrates a source-separated theoretical/experimental comparison,
  licensed-source handling, a two-model cross-section discrepancy sweep, and
  source-bounded cascade/quenching materiality checks. None is yet a
  probabilistic uncertainty model propagated through inference.
- The prepared Ar ratio can test atomic pathways, but cannot validate `n_e`,
  `T_e`, or an EEDF inversion from one ratio.
- OESCR v1 is numerically and architecturally qualified for the declared
  platform scope, but is not externally qualified for quantitative plasma
  parameter accuracy.

## Deferred model-qualification work

These items apply only if a candidate first passes the dataset-selection gate
in `docs/development_plan.md`. They are not the current OESCR v1 platform
priority and must not trigger broader chemistry or solver work on their own.

1. Obtain or calculate a pressure-applicable, candidate-local cascade source
   from state-resolved higher-level excitation and branching data. Neutral-Ar
   quenching is now bounded and negligible; the monoenergetic cascade anchor
   is material but cannot be transferred to the discharge EEDF or pressure.
2. Obtain an uncertainty-bearing near-threshold experimental Ar 2p1/2p6
   excitation function to resolve or weight the BSR/NGFSRDW discrepancy, and
   use an independent EEDF measurement or declare a justified EEDF-family
   discrepancy bound. The two-model min/max span alone is not a probability
   distribution.
3. Fix an immutable low-pressure ratio tolerance that combines reported or
   defensibly bounded experimental uncertainty, digitization tolerance,
   cross-section uncertainty, and model discrepancy. Only then add the Ar
   candidate's `validation.yaml` and evaluator.
4. Replace the NO figure-derived values with the public archive values if the
   source server becomes reachable, preserving both artifact hashes.
5. Isolate the published 230-237.15 nm NO(A-X) band and decide whether N2(A)
   can be supplied independently. If it cannot, classify this dataset as a
   qualitative mechanism/identifiability challenge rather than an absolute
   predictive pass.
6. Implement the resulting declared evaluator and immutable pass/fail
   tolerances; retain calibration, units, preprocessing, and line selection in
   `validation.yaml` only after the comparator is physically closed.
7. Re-evaluate data-only rank and singular directions whenever an external
   dataset changes the selected line set or fitted parameter set.
8. Add cross-section/model-discrepancy uncertainty without relabeling it as
   measurement noise.
