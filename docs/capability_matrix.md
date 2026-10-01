# OESCR capability contract

This document is the decision boundary for public OESCR use. It states what a
workflow computes, which inputs must be supplied independently, and which
interpretations are not supported. Configuration syntax is documented in
`configuration_guide.md`; scientific evidence status is documented separately
in `scientific_validation.md`.

## Common model boundary

OESCR is a reduced, steady-state collisional-radiative and optical-observation
platform. It does not solve plasma composition, power balance, transport, or
self-consistent electron kinetics. Ground-state gas composition, selected
radical/metastable densities, electron density, and an EEDF description are
inputs unless a specifically declared inverse workflow fits them.

Every forward or inverse result is conditional on the supplied state set,
reaction set, cross sections, radiative branches, trapping/loss approximations,
geometry, and instrument response. Passing numerical diagnostics establishes
that the configured calculation behaved consistently; it does not establish
experimental accuracy.

## Capability matrix

| Workflow | Required independent inputs | Returned quantity and basis | Interpretation allowed | Not established |
|---|---|---|---|---|
| Physical forward spectrum | Electron density; Te or EEDF; gas/source densities; dimensioned reactions and complete radiative branches; geometry; instrument | `ForwardResult`: zone populations, atomic/band emissivity, instrument spectra, quality diagnostics, and provenance. Physical components use spectral radiant-power/radiance bases; the instrument reports its declared basis and unit | Conditional spectrum for the exact supplied reduced model | Self-consistent composition, plasma power balance, universal accuracy, or parameter identification |
| Empirical forward spectrum | Same operating inputs plus explicitly selected `emission_mode: empirical` effective emitters | Relative or mixed-basis spectrum with component bases reported separately | Workflow prototyping and comparison on the declared empirical basis | Absolute radiance, electron density, or transferable photon production |
| `relative_shape` inverse | Measurement spectrum; instrument wavelength response; fitted parameter bounds; declared source densities or priors | Configured fitted parameters, cost, measurement-only local Jacobian summary, and conditional Laplace curvature | Relative spectral/spatial profile information when the relevant Jacobian directions are resolved | Absolute electron-density/source scale when gain or source density is free; experimental observability from priors alone |
| `ratio_diagnostic` inverse | Registered diagnostic windows and at least one active area/peak ratio objective; relative response between the selected wavelengths; required source densities | Fitted configured parameters and dimensionless ratio residuals, with measurement-only identifiability | Sensitivity of declared line/window ratios to the fitted reduced-model parameters | A ratio being intrinsically a Te, ne, or EEDF diagnostic; absolute intensity scale |
| `actinometry` inverse | An active ratio objective; independently justified actinometer/target excitation, quenching, branching, and composition assumptions | Fitted configured target parameters using the shared ratio objective and diagnostics | Actinometric inference only within the declared kinetic assumptions | A separate built-in actinometry chemistry solver, automatic cancellation of all plasma dependencies, or an absolute density without qualified assumptions |
| `calibrated_absolute` inverse | Absolute instrument calibration and matching measurement metadata; fixed automatic gain; physical emitters only; measurement uncertainty; externally constrained source densities and losses | Fitted configured parameters in the measurement's declared radiance, collected-power, or photoelectron basis; prerequisite and local-rank flags | Absolute-scale inference only when prerequisites pass and the measurement-only Jacobian has the required rank | Absolute ne merely because a spectrum is calibrated; model-discrepancy or cross-section uncertainty marginalization |
| Parametric Te/EEDF sensitivity or inverse | `te`/Maxwellian, Druyvesteyn, or explicit bi-Maxwell parameters; adequate energy grid and cross-section coverage | Fitted or swept low-dimensional parameters plus EEDF/grid diagnostics and local singular directions | Conditional discrimination among the configured low-dimensional families when resolved by the selected observations | Unique recovery of the true EEDF outside the declared family |
| Tabulated EEDF forward | One normalized tabulated EEDF per zone and adequate energy support | Conditional forward rates and spectra with normalization/edge/coverage diagnostics | Forward evaluation of an externally supplied distribution | Inference of that distribution from OES |
| Arbitrary tabulated-EEDF inverse | Not supported in v1 | No public result | None | A resolved EEDF without an explicit basis, regularization, kernel-rank, and resolution analysis |

## Instrument output contract

The instrument layer produces exactly one declared output basis per instrument:

| Calibration kind | Output basis | Unit | Required dimensional inputs |
|---|---|---|---|
| no absolute calibration | `relative_instrument_signal` | `arb` | none; absolute interpretation is prohibited |
| `spectral_radiance` | `spectral_radiance_W_m-2_sr-1_nm-1` | `W_m-2_sr-1_nm-1` | absolute calibration reference |
| `collected_spectral_power` | `spectral_power_W_nm-1` | `W_nm-1` | collection area, solid angle, viewing factor, calibration reference |
| `photoelectron_spectrum` | `photoelectrons_nm-1` | `photoelectron_nm-1` | collection terms, integration time, quantum efficiency, calibration reference |

An absolute inverse measurement must repeat `output_basis`, `output_unit`, and
`calibration_reference` in its CSV metadata. A mismatch is rejected before
optimization.

## Result-reading rules

1. `success: true` means the numerical optimizer terminated successfully; it
   is not a scientific validation verdict.
2. Measurement-only identifiability determines whether the selected spectra
   locally constrain fitted parameter combinations. Priors and smoothing do
   not increase this rank.
3. Laplace covariance is local conditional curvature using configured
   measurement/calibration covariance. It does not marginalize atomic-data,
   cross-section, missing-mechanism, or covariance-hyperparameter uncertainty.
4. `calibrated_absolute` prerequisites and local rank are separate checks; both
   must pass before an absolute fitted scale is interpreted.
5. Generated benchmarks qualify code paths and self-consistency. Only a
   held-out package with closed inputs and fixed tolerances can support an
   external quantitative claim.

## Current executable coverage

| Workflow | Semantic/unit tests | Minimal runnable repository example |
|---|---:|---:|
| Physical forward | yes | yes |
| Empirical forward | yes | yes |
| `relative_shape` | yes | yes |
| `ratio_diagnostic` | yes | yes: `examples/use_cases/two_band/` |
| `actinometry` | yes | yes: `examples/use_cases/two_band/` |
| `calibrated_absolute` | yes | yes: `examples/use_cases/two_band/` |
| Parametric Te/EEDF | yes | partial through generated cases |
| Tabulated EEDF forward | yes | plugin/YAML test only |
| Arbitrary tabulated-EEDF inverse | rejection test | intentionally none |

The two-band examples recover one ratio-constrained source density and one
absolute-scale electron density from a generated physical spectrum. They prove
the YAML-to-result contracts and local-rank reporting; as generated fixtures,
they do not qualify a gas model against experiment.
