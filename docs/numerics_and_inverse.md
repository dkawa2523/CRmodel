# Numerics and Inverse Strategy

The complete mathematical definition of the residuals, optimizer coordinates,
observability analysis, validation cases, and interpretation limits is given in
[`model_methods_and_validation.md`](model_methods_and_validation.md).

## Forward numerics

### Rate integration

Cross sections are interpolated onto a shared energy grid. Rate coefficients are then computed by direct numerical quadrature over energy.

### Reduced CR solve

The steady-state CR problem is solved as a dense linear system with a least-squares fallback if the matrix is singular or ill-conditioned.

Each zone reports the solve method, rank, condition number, relative linear
residual, and negative population amount before clipping. These values are
evaluated by a configurable warn/error policy. Non-empty rank-deficient systems
produce a cr.singular_matrix error instead of being hidden by diagonal repair.
Negative populations are also reported as a fraction of the pre-clip solution
norm so the threshold is independent of density scale.

### Emission synthesis

Atomic lines and effective bands are accumulated onto a fine wavelength grid and then passed through the instrument model.

### Coarse detector output

Each detector channel is computed by integration over the channel width, which
is important for low-resolution spectrometers. The numerical integrator adds
the exact channel edges by interpolation before trapezoidal integration; this
preserves a constant signal and removes fine-grid phase dependence.

Optional convergence checking rebuilds the forward model twice: once with a
refined energy grid and once with a refined internal wavelength grid. Both are
compared with the base result after projection to identical instrument bins.
It is disabled by default because inverse optimization would otherwise triple
every forward evaluation; enable it for case qualification and release gates.

## Inverse numerics

### Optimization

The current workflow is:

1. optional differential evolution for coarse global search
2. local refinement with `scipy.optimize.least_squares`
3. optional Laplace approximation around the optimum

### Residual structure

Residuals are assembled as one long vector for standard least-squares tools.
The implementation is split into ordinary functions for objective options,
gain priors, window terms, ratio terms, and regularization so one feature does
not enlarge a single branch-heavy function.

Full-spectrum uncertainty may be supplied either as independent positive sigma
values in the measurement CSV or as a correlated covariance matrix referenced
by the inverse YAML. Covariance residuals use a Cholesky solve rather than an
explicit matrix inverse. A positive absolute-calibration scale uncertainty adds
a rank-one correlated term to that covariance using the measured spectrum as
the fixed scale reference.

Window-derived area, peak, and explicitly named ratio residuals can use a
separate feature covariance. These residuals are dimensionless before
whitening. A feature handled by this matrix is excluded from the corresponding
scalar weight, avoiding duplicate use of the same information. Missing named
features, including features removed by low-signal gating, are errors rather
than silently shortened residual vectors.

To reduce the influence of extremely weak windows, the inverse objective can
apply `window_min_relative_signal` and skip window-fit, area, and peak residuals
when a window's measured signal is small relative to the strongest selected
window in the same chord. The skipped window names are stored in the residual
`aux` output for later analysis. Default is `0.02`.

For wavelength-separated ratio diagnostics, the inverse objective can also fit
an optional instrument-level gain tilt (`auto_gain_tilt_fit`) so the scalar
gain model does not absorb broad spectral slope mismatch. The tilt term is
optional and can be regularized by `gain_tilt_prior_weight/sigma`
(defaults: `false`, `0.0`, `1.0`).

### Regularization

The current regularization is array smoothing on shell profiles. First- and
second-order finite-difference penalties are supported. A prior or smoothing
target must contain at least one fitted parameter; otherwise its residual is
constant and configuration validation rejects it.

### Why low-resolution EEDF inverse stops at bi-Maxwell

At low spectral resolution, line overlap and local-gain ambiguity make arbitrary EEDF retrieval underconstrained. For that reason the code explicitly guards against unrestricted low-resolution tabulated-EEDF inversion.

Fit results include a local finite-difference Jacobian summary built only from
measurement residuals. It reports numerical rank, condition number, column
norms, inactive parameters, and named right-singular-vector combinations.
Priors and regularization are deliberately excluded so assumptions cannot make
an experimentally invisible variable appear observable. Rank is local and
scale-dependent; a full-rank but very ill-conditioned result is not a robust
experimental determination. calibrated_absolute mode also refuses automatic
gain and reports configuration prerequisites separately from the post-fit
local-rank decision. relative_shape warns when electron-density scale is
confounded with a fitted gain.

FitResult records the configured relative calibration uncertainty for every
instrument. The Laplace covariance uses the complete objective Jacobian,
including priors and regularization, and remains a local, conditional curvature
estimate: it uses the configured measurement and calibration covariance as
fixed and does not marginalize cross-section, model-discrepancy, or covariance
hyperparameter uncertainty.

## Performance notes

This scaffold prioritizes clarity over speed, but several design choices already support future acceleration:

- shared energy grid
- cached cross-section interpolation
- separated geometry and instrument operators
- decoupled physics blocks that can later be vectorized or JIT-compiled

## Extension targets for future performance work

- sparse CR matrix assembly
- batched multi-zone rate evaluation
- surrogate models for selected band emitters
- JAX/Numba acceleration for repeated inverse runs
