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
- compiled electron-impact/first-/two-/three-body CR processes with explicit units and state budgets
- forward spectral synthesis from `n_e`, `T_e` or EEDF, species densities, geometry, and instrument response
- axisymmetric radial-shell line-of-sight integration for 5-chord measurements
- multi-instrument support with external YAML instrument files
- conditional inverse fitting of configured `T_e`, `n_e`, or bi-Maxwell
  parameters, with measurement-only local identifiability reported separately
- spectrum, window-fit, line-area, and peak-based objectives
- broad wall-loss priors and optional residual gas densities
- measurement-only identifiability with named singular directions, separated
  from full-objective Laplace conditional-curvature summaries
- explicit physical/empirical emission modes and dimensioned instrument calibration
- pointwise/correlated spectrum uncertainty, named feature covariance, and
  correlated absolute-calibration uncertainty
- categorized CR/EEDF/cross-section quality gates, optional grid convergence,
  and CLI diagnostics/provenance output

## Important scope note

This code is intentionally designed as a **flexible framework**. It does **not** bundle large public atomic/molecular databases. The included curated cross sections are meant as a literature-anchored starting point, not as a claim of exhaustive validated database coverage. Replace or refine them with your own NIST/LXCat/PGOPHER-derived files before research use.

Read `docs/capability_matrix.md` before interpreting an inverse result. It
defines the independent inputs, units, identifiability requirements, and
unsupported claims for every public workflow. In particular, a successful
optimization is not evidence that `n_e`, `T_e`, or an EEDF was experimentally
identified.

## Installation

```bash
pip install -e .
```

For development and architecture checks, install the optional tool set:

```bash
pip install -e ".[dev]"
```

Run the quality checks from the repository root:

```bash
ruff check oescr tests scripts
pyrefly check
lint-imports
radon cc oescr
radon mi oescr
pytest -q
```

Ruff, Pyrefly, and Import Linter are executable gates. Radon is currently a
review report: it intentionally exposes the existing complexity hotspots
without blocking all work while those functions are being split.

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

Minimal end-to-end examples for `ratio_diagnostic`, `actinometry`, and
`calibrated_absolute` share one inspectable physical two-band case under
`examples/use_cases/two_band/`. Its README gives exact commands, expected
fitted values, and the interpretation boundary for each mode.

Generated run artifacts are intentionally not versioned. Keep outputs in a
user-local directory (for example `--out .local_outputs/...`) and regenerate
them as needed.

To inspect fully resolved and normalized YAML after `include:` expansion:

```bash
python scripts/dump_resolved_config.py examples/case_init_cf4_o2_ar.yaml examples/inverse_cf4_o2_ar.yaml --out resolved_config
```

## Schema validation

```bash
python scripts/validate_yaml.py case examples/case_init_cf4_o2_ar.yaml
python scripts/validate_yaml.py inverse examples/inverse_cf4_o2_ar.yaml
python scripts/validate_yaml.py project examples/project_cf4_o2_ar.yaml
python scripts/validate_yaml.py validation examples/benchmarks/nf3_ar_ccp_clean_2023/validation.yaml
```

Validation is now two-stage.

1. JSON Schema checks the user-facing YAML structure.
2. Semantic validation checks array lengths, cross references, and plugin-local constraints.

## Generated self-consistency and validation evidence

After generating a benchmark analysis, evaluate `init` against `opt` under the
same versioned analysis contract with:

```bash
python scripts/evaluate_strict_gate.py \
  --benchmarks nf3_ar_ccp_clean_2023 cl2_ar_icp_fuller2001 \
  --within-run \
  --improved-run inverse_observable_20260929 \
  --improved-out-name analysis_contract_v1 \
  --cl2-pair-threshold 0.80
```

The command exits with non-zero status when any generated-data gate fails. It
does not claim agreement with an independent experiment. A between-run
comparison additionally requires explicit baseline arguments and identical
`analysis_contract` fields; legacy or incompatible summaries are rejected.

Audit the declared evidence level, data hashes, evaluator hash/version,
calibration status, model-input closure, and evaluation-data use separately:

```bash
python scripts/audit_validation_evidence.py
```

The current NF3/Ar and Cl2/Ar packages pass their declared
`generated_self_consistency` checks and intentionally report
`external_quantitative=NOT READY`. Use
`--require-external-quantitative` in release qualification when a held-out,
calibrated package has been added.

The v1 external-dataset selection gate found no physically closed candidate,
so this release makes no external quantitative accuracy claim. That boundary
does not reduce the analytic, numerical, or generated end-to-end evidence
listed in `docs/scientific_validation.md`.

Two held-out candidates are prepared under `examples/validation/` and are
intentionally not included in the evidence audit yet. The Schuecke N2/O2 data
have an open input set because the dominant N2(A) density was not measured.
The Arellano Ar-CCP 763.5/750.4 nm ratio is response-corrected and directly
matches existing OESCR pathways. Candidate-specific BSR state-resolved curves
now support an untuned corona-limit sensitivity check, but the comparison
remains conditional on cross-section/model-discrepancy uncertainty and
independently closed EEDF, cascade, and metastable inputs.

Inspect whether the configured spectra actually constrain each fitted
parameter before interpreting an inverse result:

```bash
python scripts/summarize_identifiability.py case.yaml inverse.yaml --out observability.yaml
```

This report excludes priors and regularization. They may stabilize an estimate,
but they do not make a parameter experimentally observed.

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
- `docs/compatibility_policy.md`
- `docs/capability_matrix.md`
- `docs/configuration_guide.md`
- `docs/physics_models.md`
- `docs/numerics_and_inverse.md`
- `docs/model_methods_and_validation.md`
- `docs/io_spec.md`
- `docs/developer_guide.md`
- `docs/extension_workflow.md`
- `docs/development_plan.md`
- `docs/schema_reference.md`
- `docs/plugin_interfaces.md`
- `docs/scientific_validation.md`
- `docs/v1_readiness_review.md`

## Decoupled use of submodels

A public convenience API is provided:

```python
from oescr.api import (
    EEDF_PLUGINS,
    EEDFPlugin,
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

`examples/benchmarks/physical_band_analytic` is a separate analytic
conservation benchmark for the physical electron-impact photon-band path. It
does not replace or relabel the empirical literature-anchor packages.

Each benchmark includes a `project.yaml` entry point in addition to `case_truth.yaml`, `case_init.yaml`, and `inverse.yaml`.

## Limitations

- escape-factor trapping is simplified
- band emitters are effective models, not full rovibronic CR
- no 0D chemistry / composition solver is included
- low-resolution EEDF inverse is restricted to bi-Maxwell
- uncertainty quantification is lightweight

Those limitations are deliberate. The code is meant to stay inspectable, modifiable, and suitable for continued research development.
