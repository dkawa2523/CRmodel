# YAML schema reference

This revision adds **machine-checkable JSON Schema validation** for all user-facing YAML entry points.

## Supported schema types

- `case` — plasma, geometry, instrument references, reactions, transitions, bands
- `inverse` — measurements, fit strategy, parameters, priors, regularization
- `project` — single-file orchestration manifest
- `instrument` — wavelength grid/range, throughput, LSF, baseline, nuisance parameters
- `windows` — diagnostics window registry for line/window fitting

The schema files live in `oescr/schemas/` and are loaded through `oescr.io.schema`.

## Validation model

Validation is intentionally two-stage.

1. **Structural validation**
   - JSON Schema validates field names, required sections, scalar/array types, enums, and nested object layout.
   - This is run on the merged YAML after `include:` expansion and numeric-string coercion.

2. **Semantic validation**
   - cross-field consistency checks in `oescr.io.validators`
   - plugin selection and plugin-specific config validation
   - shell-array length checks against `geometry.n_shells`
   - parameter path resolution for inverse problems

## Why both layers exist

JSON Schema is very good at answering questions like:

- Is `geometry.mode` one of the supported modes?
- Does an instrument define either `wavelength_grid_nm` or `wavelength_min_nm / wavelength_max_nm / bin_nm`?
- Does a window define `center_nm` and `half_width_nm`?

But JSON Schema alone is not a good place to express:

- whether `plasma_state.ne_shells_m3` has the same length as `geometry.n_shells`
- whether a reaction references known states or valid external density keys
- whether a plugin kind exists and whether its config is physically coherent

Those checks therefore stay in Python semantic validation.

## CLI

```bash
python scripts/validate_yaml.py case examples/case_init_cf4_o2_ar.yaml
python scripts/validate_yaml.py inverse examples/inverse_cf4_o2_ar.yaml
python scripts/validate_yaml.py project examples/project_cf4_o2_ar.yaml
```

## Schema authoring policy

The repository follows these rules when adding new YAML fields.

- User-facing YAML fields should be added to a JSON Schema file.
- Cross-field logic should be added to `oescr.io.validators`.
- Plugin-specific settings should be validated by the plugin itself.
- Backward-compatible shorthands may be accepted in raw YAML, but the normalized internal form should be explicit.

## Backward compatibility

The loader now coerces numeric-like YAML strings such as `1.0e16` into floating-point values before schema validation. This keeps older case files valid while still allowing strict numeric schema checks.
