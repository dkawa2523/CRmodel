# Physics Models and Approximations

For an equation-level account of every model, its implementation boundary,
evaluation-critical functions, validation results, and literature sources, see
[`model_methods_and_validation.md`](model_methods_and_validation.md).

## Scope

The code is a reduced OES collisional-radiative scaffold for low-pressure semiconductor processing plasmas. It is deliberately **not** a 0D chemistry/composition solver.

Inputs are assumed to provide, or make inferable:

- electron density
- electron temperature or reduced EEDF description
- parent gas fractions
- selected radical and metastable densities
- chamber geometry
- observation geometry
- instrument response

## EEDF models

Supported modes:

- public `eedf.kind` plugins with one validated parameter mapping per zone
- `te` with `maxwell`, `druyvesteyn`, or `bi_maxwell`
- `eedf_bimaxwell`
- `eedf_tabulated`

The three `plasma_mode` forms are retained as compatibility syntax and resolve
to the same EEDF plugin registry. New model families use the public `eedf`
envelope, so adding one does not require editing the central mode enum or
forward solver.

Bi-Maxwell inputs are explicit. The code no longer invents hot temperature or
hot fraction defaults when te_eedf_kind is bi_maxwell.

Rate coefficients are computed from

\[
  k_r = \int_0^\infty \sigma_r(E) v(E) f_E(E)\, dE
\]

The implementation assumes the EEDF is represented as a normalized energy-space PDF.

Analytic CR, branching, emission-conservation, and grid-qualification evidence
is tracked separately from external validation in
`docs/scientific_validation.md`.

## Reduced CR model

For each solved excited state, the code assembles a steady linear balance equation

\[
  M(\theta) n^* = b(\theta)
\]

Included mechanisms in the current scaffold:

- electron-impact, first-order, two-body, and three-body state transfers/losses
- radiative decay with effective A values
- wall loss

Reaction records are compiled before zone evaluation. Their effective
frequencies are explicit:

\[
  \nu_e = n_e k_e(f_E),\quad
  \nu_1 = k_1,\quad
  \nu_2 = k_2 n_M,\quad
  \nu_3 = k_3 n_M n_N.
\]

The corresponding coefficient units are m3/s, 1/s, m3/s, and m6/s. A solved
source contributes a matrix loss and, when tracked, a target-state gain. An
externally supplied source contributes to the right-hand side. Two-/three-body
colliders must be external densities: solved-state colliders would make the
system nonlinear and are rejected instead of being silently approximated.

Every reaction, radiative transfer, and wall loss produces an auditable matrix
contribution. Forward zone diagnostics expose per-state volumetric source and
loss budgets assembled from those same contributions.

The current CR kernel is intentionally small and transparent. It is not yet a full state-complete atomic or molecular CRM.

Atomic level and radiative data are independent of the selected collisional
closure. Reusable species packs therefore own stable states and complete decay
branch sets, while cases select the electron-impact and quenching processes
they can support. `examples/data/species_packs/ar_2p1_2p6_nist.yaml` applies
this rule to the Ar 2p1 and 2p6 levels. Omitting unobserved branches would
overestimate observed-line photon production, so the pack includes the
667.7/750.4 nm branches from 2p1 and the 763.5/800.6/922.4 nm branches from
2p6.

`examples/data/species_packs/o_777_reduced.yaml` demonstrates a second pack
that includes a state, electron-impact excitation, explicit O2 quenching, and
one radiative branch. Its seed cross section is labeled illustrative rather
than externally qualified. `examples/case_truth_cf4_o2_ar.yaml` composes it
with the Ar pack under the `oxygen` namespace; this proves configuration
composition, not a self-consistent O/O2 chemistry model.

## Radiation trapping

The present code uses a simplified effective-A approach through the trapping
module. Only the implemented slab escape-factor geometry is accepted; other
geometries require a dedicated plugin. A beta override is constrained to the
physical interval from zero to one.

## Wall loss

Wall loss is represented as an effective first-order loss rate. A state with a
non-zero wall gamma must define mass_amu. thermal_flux_factor is explicit and
defaults to 1.0 for compatibility; set it to 0.25 when gamma and the selected
mean thermal speed use the conventional isotropic flux-to-wall definition.
This remains an effective OESCR boundary loss, not wall-coupled chemistry.

## Molecular band emitters

Three band types are implemented:

1. `effective_excitation_band`
2. `effective_density_band`
3. `electron_impact_photon_band`

The first two are empirical/effective outputs and do not claim the atomic-line
radiant-power basis. electron_impact_photon_band requires an explicit photon
yield and applies photon energy, branching ratio, and the 1 / 4 pi factor, so it
can be combined with atomic radiant-power spectra. ForwardResult exposes the
total and component bases so mixed legacy outputs are visible. Physical mode is
the default; legacy effective emitters require an explicit empirical mode.

Cross-section tables are checked for finite, non-negative values and strictly
increasing energy. Their comment metadata, SHA-256 hash, energy range, and EEDF
coverage are carried in zone diagnostics.

The forward quality policy turns CR rank/conditioning/residual, pre-clip
negative populations, EEDF upper-grid mass, EEDF edge amplitude, and
cross-section/EEDF overlap into categorized pass/warning/error events. The
policy diagnoses numerical/model-domain adequacy; it does not turn an
internally consistent case into independent scientific validation.

## Geometry

The default geometry is `axisym_shell`.

Zone emissivities are projected into chord signals through a shell path-length matrix

\[
  I_{m,\lambda} = \sum_k W_{mk} j_{k,\lambda}
\]

This is the intended default for the current 5-chord same-height use case.

## Instrument model

The instrument layer applies:

- wavelength shift
- LSF convolution
- throughput
- an optional dimensional calibration transform
- baseline
- bin integration onto the coarse measurement grid

Calibration can retain spectral radiance, convert it to collected spectral
power using area and solid angle, or convert it to a photoelectron spectrum
using integration time and quantum efficiency. Baseline is applied in the
resulting output unit. The coarse detector response is modeled as
**bin-averaged** intensity, not a point sample at the channel center. Detector
bin edges are inserted explicitly during quadrature so integrated power is not
lost when fine-grid samples do not land on an edge.

For calibrated-absolute inverse use, an instrument may also declare a relative
standard calibration uncertainty. It is treated as a common multiplicative
error across that instrument's spectrum and combined with measurement noise;
it does not change the forward mean transform.

## Inverse objective

The inverse solver can combine:

- full-spectrum residuals
- window-fit residuals
- baseline-corrected line-area residuals
- baseline-corrected peak residuals
- named window/ratio feature covariance residuals
- priors
- smoothness regularization on shell arrays

Inverse configurations also declare an inference_mode: relative_shape,
calibrated_absolute, ratio_diagnostic, or actinometry. Calibrated-absolute mode
rejects fitted automatic gain. The fit result reports measurement-only Jacobian
singular values, named parameter directions, inactive columns, rank, condition
number, and interpretation warnings. Priors and smoothing contribute to the
separate full-objective Laplace calculation, which is a local
conditional-curvature estimate rather than a complete posterior uncertainty.
Ratio-diagnostic and actinometry modes require an active ratio residual.
Actinometry reuses the ratio objective and adds interpretation assumptions; it
does not invoke an additional chemistry model. The complete input/output and
claim boundary is maintained in `docs/capability_matrix.md`.

## What is approximated

The most important approximations are:

- no self-consistent chemistry solver
- effective rather than full molecular band CR
- simplified trapping treatment
- simplified wall model
- low-resolution EEDF inverse restricted to bi-Maxwell
- Laplace rather than full Bayesian uncertainty quantification

These approximations are deliberate. They keep the code inspectable and modifiable while still enabling realistic workflow prototyping.
