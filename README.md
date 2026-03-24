# OESCR Research Scaffold for Low-Pressure Semiconductor Plasma OES

This repository is a **research-oriented scaffold** for an optical-emission-spectroscopy collisional-radiative (OESCR) model aimed at low-pressure semiconductor processing plasmas.

## What this revision improves

This revision focused on two additional requirements:

- **complete YAML schemaization** for user-facing configuration files
- **strict plugin interfaces** for physical and instrument submodels

The codebase now has:

- single-file project execution with `project.yaml`
- recursive YAML `include:` support to reduce duplication
- relative-path rebasing for included YAML fragments
- compact inverse configuration with `parameter_groups`
- compact measurement loading with `files_glob`
- explicit configuration normalization before validation and execution
- **JSON Schema validation** for `case`, `inverse`, `project`, `instrument`, and `windows`
- **plugin registries** for EEDF, reaction-rate, band, trapping, wall-loss, geometry, throughput, LSF, and baseline models
- public decoupled API through `oescr.api`
- expanded markdown documentation covering architecture, physics, numerics, I/O, schema, and plugin extension rules

## What the package implements

- user-defined excited states, reactions, transitions, and effective molecular-band emitters
- forward spectral synthesis from `n_e`, `T_e` or EEDF, species densities, geometry, and instrument response
- axisymmetric radial-shell line-of-sight integration for 5-chord measurements
- multi-instrument support with external YAML instrument files
- inverse solving for `T_e` / `n_e` and, in low-resolution mode, **bi-Maxwell EEDF** only
- spectrum, window-fit, line-area, and peak-based objectives
- broad wall-loss priors and optional residual gas densities
- identifiability and Laplace-approximate uncertainty summaries

## Important scope note

This code is intentionally designed as a **flexible framework**. It does **not** bundle large public atomic/molecular databases. The included curated cross sections are meant as a literature-anchored starting point, not as a claim of exhaustive validated database coverage. Replace or refine them with your own NIST/LXCat/PGOPHER-derived files before research use.

## Installation

```bash
pip install -e .
```

## Recommended way to run

Use a project manifest:

```bash
python scripts/validate_project.py examples/project_cf4_o2_ar.yaml
python scripts/run_project.py examples/project_cf4_o2_ar.yaml --task inverse
```

The older entry points are still available:

```bash
python scripts/run_forward.py examples/case_init_cf4_o2_ar.yaml --out examples/forward_output
python scripts/run_inverse.py examples/case_init_cf4_o2_ar.yaml examples/inverse_cf4_o2_ar.yaml --out examples/inverse_output
```

To inspect fully resolved and normalized YAML after `include:` expansion:

```bash
python scripts/dump_resolved_config.py examples/case_init_cf4_o2_ar.yaml examples/inverse_cf4_o2_ar.yaml --out resolved_config
```

## Schema validation

```bash
python scripts/validate_yaml.py case examples/case_init_cf4_o2_ar.yaml
python scripts/validate_yaml.py inverse examples/inverse_cf4_o2_ar.yaml
python scripts/validate_yaml.py project examples/project_cf4_o2_ar.yaml
```

Validation is now two-stage.

1. JSON Schema checks the user-facing YAML structure.
2. Semantic validation checks array lengths, cross references, and plugin-local constraints.

## Plugin catalog

```bash
python scripts/list_plugins.py
python scripts/list_plugins.py eedf
```

The built-in extension surface now includes registries for:

- EEDF models
- reaction-rate models
- band profiles and band emitters
- radiation trapping
- wall-loss models
- geometry projectors
- instrument throughput / LSF / baseline models

## Design overview

The repository is organized around four layers.

### Configuration and orchestration

- `oescr.io.yaml_loader`
- `oescr.io.schema`
- `oescr.io.normalize`
- `oescr.io.validators`
- `oescr.io.project`
- `scripts/run_project.py`
- `scripts/validate_project.py`
- `scripts/validate_yaml.py`

### Domain modules

- `oescr.data`
- `oescr.physics`
- `oescr.geometry`
- `oescr.instrument`

### Workflow modules

- `oescr.forward`
- `oescr.inverse`

### Extension surface

- `oescr.plugins`
- plugin registries exposed through `oescr.api`

## Documentation map

Detailed markdown documents live under `docs/`:

- `docs/architecture.md`
- `docs/configuration_guide.md`
- `docs/physics_models.md`
- `docs/numerics_and_inverse.md`
- `docs/io_spec.md`
- `docs/developer_guide.md`
- `docs/design_review_architect_sim_phys.md`
- `docs/schema_reference.md`
- `docs/plugin_interfaces.md`

## Decoupled use of submodels

A public convenience API is provided:

```python
from oescr.api import (
    EEDF_PLUGINS,
    REACTION_RATE_PLUGINS,
    InstrumentSpec,
    RateCalculator,
    validate_document,
)
```

This makes it easier to reuse individual physical or numerical modules without the full forward/inverse workflow.

## Benchmarks

Literature-anchored measurement-like benchmark packages are included for:

- `examples/benchmarks/nf3_ar_ccp_clean_2023`
- `examples/benchmarks/cl2_ar_icp_fuller2001`

Each benchmark includes a `project.yaml` entry point in addition to `case_truth.yaml`, `case_init.yaml`, and `inverse.yaml`.

## Limitations

- escape-factor trapping is simplified
- band emitters are effective models, not full rovibronic CR
- no 0D chemistry / composition solver is included
- low-resolution EEDF inverse is restricted to bi-Maxwell
- uncertainty quantification is lightweight

Those limitations are deliberate. The code is meant to stay inspectable, modifiable, and suitable for continued research development.
