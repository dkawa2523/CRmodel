# Numerics and Inverse Strategy

## Forward numerics

### Rate integration

Cross sections are interpolated onto a shared energy grid. Rate coefficients are then computed by direct numerical quadrature over energy.

### Reduced CR solve

The steady-state CR problem is solved as a dense linear system with a least-squares fallback if the matrix is singular or ill-conditioned.

### Emission synthesis

Atomic lines and effective bands are accumulated onto a fine wavelength grid and then passed through the instrument model.

### Coarse detector output

Each detector channel is computed by integration over the channel width, which is important for low-resolution spectrometers.

## Inverse numerics

### Optimization

The current workflow is:

1. optional differential evolution for coarse global search
2. local refinement with `scipy.optimize.least_squares`
3. optional Laplace approximation around the optimum

### Residual structure

Residuals are intentionally assembled as one long vector. This keeps the objective readable and allows the use of standard least-squares tools.

### Regularization

The current regularization is array smoothing on shell profiles. First- and second-order finite-difference penalties are supported.

### Why low-resolution EEDF inverse stops at bi-Maxwell

At low spectral resolution, line overlap and local-gain ambiguity make arbitrary EEDF retrieval underconstrained. For that reason the code explicitly guards against unrestricted low-resolution tabulated-EEDF inversion.

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
