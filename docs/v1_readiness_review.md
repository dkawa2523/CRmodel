# OESCR v1 readiness review

Reviewed: 2026-09-30

Verification refreshed: 2026-10-01

## Decision

The v1 platform implementation has passed its acceptance gates for the declared
reduced-CR/OES scope. Calculation units, workflow contracts, extension points,
diagnostics, and runnable use cases are in place without adding a global
chemistry model. It is not externally qualified for quantitative plasma
parameter accuracy, and it makes no such claim.

The pinned native Pyrefly 1.3.1 check reports 0 errors and 20 warnings after
adding the distant-initialization benchmark runner and figure generator.

## Architecture outcome

- `CompiledCase` owns static states, grids, reaction processes, solvers,
  instruments, and the observation plan; `OESCRModel` does not duplicate them.
- Physics, geometry, instrument, forward, inverse, and analysis dependencies
  follow the three enforced Import Linter contracts.
- Physical emission bases remain dimensioned. Empirical emitters require an
  explicit mode and cannot enter calibrated-absolute inversion.
- Measurement uncertainty, identifiability, conditional curvature, and
  evidence eligibility are separate responsibilities.
- Ar and namespaced O species packs demonstrate append-only multi-gas
  composition. The exact data and plugin edit points are documented.
- Compatibility is limited to the adapters inventoried in
  [compatibility_policy.md](compatibility_policy.md); no duplicate numerical
  implementation is retained.

## Supported-use boundary

The authoritative workflow table is
[capability_matrix.md](capability_matrix.md). Physical and empirical forward
calculation, relative-shape, ratio, actinometry, calibrated-absolute, and
low-dimensional parametric-EEDF workflows have explicit contracts. The three
previously uncovered inverse modes have runnable examples under
`examples/use_cases/two_band/`.

Arbitrary tabulated-EEDF inversion, self-consistent composition/transport, and
full rovibronic molecular CR are not v1 capabilities. They are not represented
by permissive fallbacks.

## Scientific evidence boundary

- Analytic CR and emission-conservation fixtures qualify the current kernels.
- Generated NF3/Ar and Cl2/Ar packages qualify reproducible workflow
  self-consistency, not experimental accuracy.
- Their separate distant-initialization test currently fails the versioned
  parameter-recovery and held-out-chord criteria; this is retained as an
  identifiability result, not tuned into a pass.
- The Schuecke and Arellano held-out candidates fail the v1 dataset-selection
  gate because required model inputs or claim-level uncertainty remain open.
- No candidate-specific chemistry or tolerance was invented to force a pass.

See [scientific_validation.md](scientific_validation.md) for the exact blockers
and the 2026-09-30 selection table.

## Verification snapshot

| Check | Result |
|---|---|
| pytest | 114 passed |
| Ruff | passed |
| Import Linter | 3 contracts kept, 0 broken |
| Radon CC | 480 blocks, average A (3.525), no D/E blocks |
| Markdown local links | 22 files checked, 0 broken targets |
| benchmark evidence audit | generated declarations and hashes pass; external quantitative status correctly remains NOT READY |
| NF3/Ar and Cl2/Ar project validation | passed |
| Pyrefly 1.3.1 | 0 errors / 20 warnings |
| wheel build and isolated import smoke test | passed; public workflow imports and packaged case schema available from `oescr-0.1.0-py3-none-any.whl` |

## Release operation

No further core implementation is required for the v1 platform boundary.
Before publishing a tag, the release owner should:

1. Repeat the documented quality commands from a clean checkout or CI job.
2. Select the public package version and tag only if that clean run matches this capability and
   evidence boundary.

Further external model qualification is a separate research track. It resumes
only when a candidate independently closes calibration, required physical
inputs, uncertainty, reproducible data access, and a claim already supported
by OESCR.
