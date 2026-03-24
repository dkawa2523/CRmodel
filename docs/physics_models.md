# Physics Models and Approximations

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

- `te` with `maxwell`, `druyvesteyn`, or `bi_maxwell`
- `eedf_bimaxwell`
- `eedf_tabulated`

Rate coefficients are computed from

\[
  k_r = \int_0^\infty \sigma_r(E) v(E) f_E(E)\, dE
\]

The implementation assumes the EEDF is represented as a normalized energy-space PDF.

## Reduced CR model

For each solved excited state, the code assembles a steady linear balance equation

\[
  M(\theta) n^* = b(\theta)
\]

Included mechanisms in the current scaffold:

- electron-driven excitation and stepwise excitation
- radiative decay with effective A values
- gas quenching
- user-defined loss terms
- wall loss

The current CR kernel is intentionally small and transparent. It is not yet a full state-complete atomic or molecular CRM.

## Radiation trapping

The present code uses a simplified effective-A approach through the trapping module. This is intended as an extensible placeholder, not a final self-absorption treatment.

## Wall loss

Wall loss is currently represented as an effective first-order loss rate. This is the right abstraction for the current scope because the package is not solving full wall-coupled surface chemistry.

## Molecular band emitters

Two effective band types are implemented:

1. `effective_excitation_band`
2. `effective_density_band`

These are deliberately separated from the atomic CR solver because the public data quality and modeling needs differ significantly between atomic lines and molecular bands.

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
- baseline
- bin integration onto the coarse measurement grid

The coarse detector response is modeled as **bin-averaged** intensity, not a point sample at the channel center.

## Inverse objective

The inverse solver can combine:

- full-spectrum residuals
- window-fit residuals
- baseline-corrected line-area residuals
- baseline-corrected peak residuals
- priors
- smoothness regularization on shell arrays

## What is approximated

The most important approximations are:

- no self-consistent chemistry solver
- effective rather than full molecular band CR
- simplified trapping treatment
- simplified wall model
- low-resolution EEDF inverse restricted to bi-Maxwell
- Laplace rather than full Bayesian uncertainty quantification

These approximations are deliberate. They keep the code inspectable and modifiable while still enabling realistic workflow prototyping.
