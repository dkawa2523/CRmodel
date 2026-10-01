# Developer Guide

## How to add a new physics block

First use the data/configuration checklist in `docs/extension_workflow.md`.
States, cross sections, transitions, existing band types, instrument
configurations, and registered EEDF selections do not require a new physics
block. The steps below apply only when the governing calculation changes.

### New EEDF model

Subclass the public `oescr.api.EEDFPlugin`, define its zone-local
`config_schema`, implement `build_pdf(spec, energy_eV)`, and register it in
`EEDF_PLUGINS`. Select it through `case.eedf.kind` with one `zones` entry per
geometry shell. Do not add a new `plasma_mode` branch; that selector exists only
for compatibility with existing cases. Add an end-to-end YAML-path test that
checks normalization and the resulting EEDF diagnostics.

### New atomic process

1. Decide its reactant order, coefficient unit, and whether the current linear
   steady-state CR representation can express it.
2. Add its compiled family contract to `oescr.physics.cr_processes` and the
   case schema; do not add a parallel loop to `cr_atomic`.
3. Reuse `linear_transfer_contribution` so the matrix, RHS, diagnostics, and
   state budget stay consistent.
4. Reject solved-state collider products unless a deliberate nonlinear solver
   is introduced with its own scope and tests.
5. Add an analytic unit test for coefficient units, matrix/RHS contribution,
   and source/loss budget, plus one public-YAML test.

### New molecular band model

1. Implement BandEmissionPlugin or BandProfilePlugin.
2. Declare its output basis and plugin-local schema.
3. Register it in the appropriate band registry.
4. If the model needs new external files, describe them in docs/io_spec.md and add an example.
5. Add a public-YAML test and a unit/conservation test for the emitted quantity.

### New instrument feature

1. Put the new feature in `oescr.instrument.*`.
2. Keep `InstrumentSpec.observe` as the single assembly point for instrument processing.
3. Avoid leaking instrument-specific logic into the forward solver.

## How to keep the code understandable

- Prefer explicit dataclasses or small dictionaries over opaque meta-programming.
- Put convenience syntax in config normalization, not in physics code.
- Keep model assembly in `forward.model` and inverse orchestration in `inverse.optimize`.
- Put static preparation in forward.compiled; keep repeated evaluation in
  runtime kernels.
- Keep each YAML example small by using `include:`.

### New numerical diagnostic

1. Add the raw numerical quantity to the owning physics result dataclass.
2. Add threshold evaluation and a stable category to `oescr.physics.quality`.
3. Keep CLI/YAML rendering in `oescr.forward.reporting`.
4. Add one normal fixture and one deliberately failing fixture; do not repair
   the numerical problem inside the diagnostic evaluator.

### New benchmark output

Add numerical aggregation to `analysis.benchmark_metrics` or report-data
assembly to `analysis.benchmark_results`. Shared array records belong in
`analysis.benchmark_model`; concrete CSV, SVG, HTML, and Markdown serialization
belongs in `analysis.benchmark_renderers`; argument parsing belongs in
`analysis.benchmark_cli`. Metrics and shared records must not import any of the
presentation modules.

### New external validation package

1. Keep measured or digitized data outside `case_truth.yaml`; do not tune a
   truth case from the same data and call it held out.
2. Add a `validation.yaml` that records the source, origin, calibration,
   measurement basis, preprocessing, SHA-256 hashes, model-input closure,
   evaluation-data use, evaluator version/result contract, metrics, and
   limitations. External quantitative evidence requires `closed` inputs and
   `held_out_only` evaluation data.
3. Put the physical comparator in a focused evaluator. The evidence audit only
   checks reproducibility and eligibility. Record the evaluator's own SHA-256
   and update it whenever its implementation changes.
4. Run `scripts/audit_validation_evidence.py --require-external-quantitative`
   and add a regression test for both the tolerance boundary and a known
   failure.

For generated benchmark comparisons, regenerate both summaries after an
analysis-contract change. Do not add a bypass for unversioned summaries; use
`--within-run` when the valid question is whether optimization improves the
current initial case.

### New inverse parameter or line set

1. Add only parameters that are intended to change a named measurement feature.
2. Run `scripts/summarize_identifiability.py` before optimization and inspect
   inactive columns, singular directions, rank, and condition number.
3. Remove parameters that are invisible to the measurement set; do not use a
   prior or smoothing term to relabel them as observed.
4. Add a sensitivity/identifiability regression test and rerun the generated
   benchmark gate after changing the parameter set.

## Using submodels independently

The package now exposes a small public component API:

```python
from oescr.api import maxwell_energy_pdf, RateCalculator, InstrumentSpec
```

This is the intended way to reuse parts of the code outside the full forward/inverse workflow.

## Test strategy

The repository combines analytic/invariant tests, public-YAML tests, generated
end-to-end benchmarks, architecture contracts, and qualification diagnostics.
For each fitted physics feature, add one analytic or conservation test, one
public-YAML test, and one sensitivity/identifiability test. Generated recovery
must remain labeled separately from held-out experimental comparison.

Development priorities and acceptance criteria live in
docs/development_plan.md; update it whenever a design decision changes scope.


## New in this revision

- Structural YAML validation now lives in `oescr.io.schema` and `oescr/schemas/*.yaml`.
- Semantic validation now lives in `oescr.io.validators`.
- New physical and instrument extension points are formalized through plugin registries.
- Prefer adding new model families through a plugin + plugin-local schema instead of adding `if/elif` branches in workflow code.

See also `docs/schema_reference.md` and `docs/plugin_interfaces.md`.
