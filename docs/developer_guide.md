# Developer Guide

## How to add a new physics block

### New atomic process

1. Add any new metadata needs to the case YAML.
2. Extend `oescr.physics.cr_atomic` to assemble the new source or sink term.
3. Keep the change local to CR assembly.
4. Add a small test case that exercises only the new term.

### New molecular band model

1. Add a new `kind` to `oescr.physics.bands.evaluate_bands_zone`.
2. Keep the new model self-contained.
3. If the model needs new external files, describe them in `docs/io_spec.md` and add an example.

### New instrument feature

1. Put the new feature in `oescr.instrument.*`.
2. Keep `InstrumentSpec.observe` as the single assembly point for instrument processing.
3. Avoid leaking instrument-specific logic into the forward solver.

## How to keep the code understandable

- Prefer explicit dataclasses or small dictionaries over opaque meta-programming.
- Put convenience syntax in config normalization, not in physics code.
- Keep model assembly in `forward.model` and inverse orchestration in `inverse.optimize`.
- Keep each YAML example small by using `include:`.

## Using submodels independently

The package now exposes a small public component API:

```python
from oescr.api import maxwell_energy_pdf, RateCalculator, InstrumentSpec
```

This is the intended way to reuse parts of the code outside the full forward/inverse workflow.

## Test strategy

The repository currently focuses on:

- smoke tests
- curated dataset load tests
- benchmark load tests
- new architecture tests for include, project loading, and parameter groups

For larger future development, add one regression test per new physics feature and one YAML example showing how the feature is configured.


## New in this revision

- Structural YAML validation now lives in `oescr.io.schema` and `oescr/schemas/*.yaml`.
- Semantic validation now lives in `oescr.io.validators`.
- New physical and instrument extension points are formalized through plugin registries.
- Prefer adding new model families through a plugin + plugin-local schema instead of adding `if/elif` branches in workflow code.

See also `docs/schema_reference.md` and `docs/plugin_interfaces.md`.
