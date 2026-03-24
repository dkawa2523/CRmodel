# Architecture

## Why the architecture was revised

The earlier scaffold already had good physics separation, but several things still made long-term use harder than necessary:

- case YAML and inverse YAML could become repetitive
- there was no single project manifest for a whole run
- there was little guidance on how to use submodels independently
- input validation was intentionally light
- the theory and approximations were only briefly described in the top-level README

This revision keeps backward compatibility while adding a clearer architecture around three layers.

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

The configuration layer is the only place where convenience syntax is allowed. The rest of the code should consume canonical, explicit dictionaries.

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
- `instrument`: LSF, throughput, baseline, coarse-bin observation

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
- `scripts/run_forward.py`
- `scripts/run_inverse.py`

Responsibilities:

- assemble the domain modules into forward spectral synthesis
- perform inverse fitting, local/global optimization, and simple uncertainty summaries
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
Forward model assembly
  - state registry
  - energy grid
  - rate calculator
  - reduced CR solver
  - band emitters
  - LOS projection
  - instrument observation
        ↓
Predicted spectra
        ↓
Inverse objective
  - full spectrum residual
  - window-fit residual
  - line area residual
  - peak residual
  - priors
  - smoothness regularization
        ↓
Optimization / Laplace approximation
```

## Maintainability rules

1. New convenience syntax belongs in `oescr.io.normalize`, not in physics modules.
2. New physical mechanisms should be added as small modules, then wired into `forward.model`.
3. File-path handling should always pass through `load_yaml` and `resolve_path`.
4. Example projects should prefer `include:` plus small overrides instead of copy-paste duplication.
5. New diagnostics should first be added as YAML windows and plugins, not hard-coded into inverse logic.

## What remains intentionally simple

This is still a research scaffold, not a full production simulator. The architecture is designed to stay understandable first. The following are still intentionally lightweight:

- validation is semantic but not full JSON-schema level
- plugin registration is explicit YAML-driven logic, not a dynamic plugin framework
- uncertainty quantification uses a simple Laplace approximation, not a general Bayesian engine
- molecular bands remain effective emitters rather than full rovibronic CR solvers
