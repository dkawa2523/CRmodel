# Architecture

## Why the architecture was revised

The earlier scaffold already had good physics separation, but several things still made long-term use harder than necessary:

- case YAML and inverse YAML could become repetitive
- there was no single project manifest for a whole run
- there was little guidance on how to use submodels independently
- input validation was intentionally light
- the theory and approximations were only briefly described in the top-level README

This revision keeps only the bounded compatibility listed in
`compatibility_policy.md` while organizing the implementation around three
layers.

## Layer 1: configuration and orchestration

Modules:

- `oescr.io.yaml_loader`
- `oescr.io.normalize`
- `oescr.io.validators`
- `oescr.io.project`
- `scripts/run_project.py`
- `scripts/validate_project.py`

Responsibilities:

- load YAML with recursive `include:` support
- rebase relative file paths safely when YAML fragments are included from other folders
- normalize compact user YAML into canonical internal configuration
- validate the normalized structure before running physics
- provide one-file project execution through `project.yaml`

### Design intent

The configuration layer is the only place where general convenience syntax is
allowed. The rest of the code consumes canonical, explicit dictionaries. The
one retained EEDF selection adapter maps pre-v1 `plasma_mode` input directly to
the same registered EEDF specifications used by the canonical envelope; it
does not own a numerical kernel or accept new model kinds.

That means:

- user convenience stays at the edges
- physics modules do not need to know about `include`, `files_glob`, or `parameter_groups`
- third-party developers can reason about one normalized schema

## Layer 2: domain modules

Modules:

- `oescr.data.*`
- `oescr.physics.*`
- `oescr.geometry.*`
- `oescr.instrument.*`

Responsibilities:

- `data`: cross-section and line/band metadata access
- `physics`: EEDF, rates, reduced CR, band emitters, wall loss, residual handling
- `geometry`: shell geometry and line-of-sight projection weights
- `instrument`: LSF, throughput, dimensional calibration, baseline, coarse-bin observation

### Design intent

These modules are meant to remain independently usable. For example:

- `RateCalculator` can be used without the inverse solver
- `AtomicCRSolver` can be driven by external EEDF data
- `InstrumentSpec` can post-process arbitrary synthetic spectra
- the shell geometry matrix can be reused for other plasma emission models

A convenience re-export module, `oescr.api`, now makes this explicit.

## Layer 3: workflows

Modules:

- `oescr.forward.*`
- `oescr.inverse.*`
- `oescr.inverse.measurements` for measurement units, pixel/feature covariance,
  calibration-error propagation, and whitening
- `oescr.analysis.benchmark_metrics` for renderer-independent calculations
- `oescr.analysis.benchmark_model` for shared report records
- `oescr.analysis.benchmark_contract` for comparison contracts and run
  fingerprints independent of rendering
- `oescr.analysis.benchmark_renderers` for concrete CSV/SVG/HTML/Markdown writers
- `oescr.analysis.benchmark_cli` for command-line dispatch
- `oescr.analysis.validation_evidence` for immutable evidence and
  external-validation eligibility auditing
- `scripts/run_forward.py`
- `scripts/run_inverse.py`

Responsibilities:

- assemble the domain modules into forward spectral synthesis
- perform inverse fitting, local/global optimization, and simple uncertainty summaries
- keep benchmark metrics independently importable from report rendering and CLI
- keep generated self-consistency distinct from external quantitative evidence
- require independently closed model inputs and evaluation-only hold-out data
  before an external quantitative claim
- reject comparisons whose evidence or metric semantics differ
- keep workflow logic out of the low-level physics code

## Data flow

```text
YAML fragments / project manifest
        ↓
load_yaml(include, path rebase, variable expansion)
        ↓
normalize_case_config / normalize_inverse_config
        ↓
validate_case_config / validate_inverse_config
        ↓
compile_case -> CompiledCase
  - state registry
  - energy grid
  - rate calculator
  - dimensioned CompiledReactionProcess records
  - reduced CR solver
  - fine wavelength grid
  - ObservationPlan (LOS projection + instruments)
        ↓
Runtime plasma state
  - ne / public EEDF plugin zone parameters
  - supplied radicals / metastables / residuals
        ↓
ForwardResult
  - predicted spectra and component spectra
  - populations
  - per-process and per-state source/loss budgets
  - EEDF / CR / cross-section diagnostics
  - categorized quality report and optional grid-convergence results
  - units and provenance
        ↓
Inverse objective
  - full spectrum residual (pixel + calibration covariance)
  - window-fit residual
  - named line-area / peak / ratio feature residuals
  - priors
  - smoothness regularization
        ↓
Optimization
  ├─ measurement residual Jacobian -> observability / singular directions
  └─ full objective Jacobian -> local conditional Laplace curvature
```

`CompiledCase` is the sole owner of compiled states, grids, rate/CR objects,
instruments, and observation plan. `OESCRModel` orchestrates execution through
that object and does not duplicate those fields as compatibility aliases.

## Maintainability rules

1. New convenience syntax belongs in `oescr.io.normalize`, not in physics
   modules. The frozen pre-v1 EEDF selector is the documented exception; no
   new modes may be added to it.
2. New physical mechanisms should be added as small modules, then wired into `forward.model`.
3. File-path handling should always pass through `load_yaml` and `resolve_path`.
4. Example projects should prefer `include:` plus small overrides instead of copy-paste duplication.
5. New diagnostics should first be added as YAML windows and plugins, not hard-coded into inverse logic.
6. Static structure changes must pass through compile_case; runtime state changes
   may reuse the existing CompiledCase.
7. Species packs compose spectroscopic OESCR inputs only. They must not become an
   implicit global chemistry solver. Stable level/radiative data may be shared
   in a pack while case-specific reactions remain in the case; the Ar 2p1/2p6
   pack is the reference example of this boundary.
8. Physical emission is the default. Legacy effective emitters require an
   explicit empirical mode and may not enter calibrated-absolute inversion.
9. Instrument dimensional conversion belongs to instrument.calibration; the
   forward and inverse workflows consume its declared output basis and unit.
10. Measurement and derived-feature uncertainty belongs to
    inverse.measurements. Objective assembly only produces named residuals and
    must not duplicate covariance-weighted terms with scalar weights.
11. Reaction order and units belong to physics.cr_processes. cr_atomic sums
    compiled matrix/RHS contributions and must not grow a second process-kind
    dispatch path.
12. Threshold evaluation belongs to physics.quality; CLI serialization belongs
    to forward.reporting. Physics kernels report measurements and do not decide
    output-file formats.
13. Benchmark metrics and shared records may not import report orchestration;
    the dependency direction is enforced by Import Linter.
14. Evidence auditing verifies provenance and eligibility only. Physical
    comparison remains an explicit evaluator so evidence metadata cannot grow
    into a second forward or inverse workflow.
15. Observability uses measurement residuals only. Priors and regularization
    belong to optimization and conditional uncertainty, not to claims about
    information contained in the selected spectra.
16. Benchmark comparison contracts contain only evidence and metric semantics;
    candidate configuration belongs in a separate run fingerprint so legitimate
    model changes remain comparable without permitting data drift.
17. Compatibility is limited to `compatibility_policy.md`; every retained
    adapter has one owner and must resolve to an existing canonical model.

## What remains intentionally simple

This is still a research scaffold, not a full production simulator. The architecture is designed to stay understandable first. The following are still intentionally lightweight:

- case validation combines JSON Schema with focused semantic checks; validation
  evidence has its own small JSON Schema and immutable-artifact audit
- plugin registration is explicit YAML-driven logic, not a dynamic plugin framework
- uncertainty quantification uses a simple Laplace approximation, not a general Bayesian engine
- molecular support includes a physical photon-rate path and explicitly marked
  empirical emitters, but not a full rovibronic CR solver
