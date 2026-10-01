# YAML schema reference

This revision adds **machine-checkable JSON Schema validation** for all user-facing YAML entry points.

## Supported schema types

- `case` — plasma, geometry, instrument references, reactions, transitions, bands
- `inverse` — measurements, fit strategy, parameters, priors, regularization
- `project` — single-file orchestration manifest
- `instrument` — wavelength grid/range, throughput, LSF, baseline, nuisance parameters
- `windows` — diagnostics window registry for line/window fitting
- `validation` — scientific-evidence level, immutable data artifacts,
  preprocessing, acceptance metrics, and known limitations

The schema files live in `oescr/schemas/` and are loaded through `oescr.io.schema`.

Window registries may carry optional `notes` and `reference` strings. They are
descriptive provenance for readers and reports; they do not alter the objective.

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
   - unique state/reaction/band/instrument IDs and normalized gas fractions
   - exactly one rate source for electron-impact reactions
   - reaction-family collider count and coefficient dimension
   - reaction endpoints connected to a solved state and external-only colliders
   - plugin-local configuration after envelope validation
   - explicit empirical mode for legacy effective emitters
   - calibration-kind unit and required-parameter consistency
   - inverse measurement/covariance cardinality and named feature forms
   - nonnegative instrument calibration uncertainty
   - quality/convergence diagnostic field types and threshold ordering
   - validation-evidence SHA-256 form, source metadata, measurement basis,
     calibration label, and acceptance declaration

## Why both layers exist

JSON Schema is very good at answering questions like:

- Does geometry provide a plugin selection key and structurally valid common fields?
- Does an instrument define either `wavelength_grid_nm` or `wavelength_min_nm / wavelength_max_nm / bin_nm`?
- Does a window define `center_nm` and `half_width_nm`?

But JSON Schema alone is not a good place to express:

- whether `plasma_state.ne_shells_m3` has the same length as `geometry.n_shells`
- whether a reaction references known states or valid external density keys
- whether a plugin kind exists and whether its config is physically coherent

The inverse objective also supports a small signal-gating threshold,
`fit.objective.window_min_relative_signal`, which is used to skip low-signal
windows from window-fit, area, and peak residual terms while keeping the
rest of the objective unchanged (default `0.02`).

An inverse measurement may declare feature_covariance with ordered names and a
square matrix. Supported names are window:<window-name>:area,
window:<window-name>:peak, and ratio:<explicit-pair-name>. Matrix dimension,
symmetry, finiteness, and positive definiteness are checked when measurements
are loaded. A calibration block may declare
relative_standard_uncertainty >= 0; in calibrated_absolute mode a positive
value requires measurement sigma or covariance data.

An optional gain-tilt model is also available for ratio-sensitive inversions:
`fit.objective.auto_gain_tilt_fit` plus optional regularization
`fit.objective.gain_tilt_prior_weight` and
`fit.objective.gain_tilt_prior_sigma`
(defaults: `false`, `0.0`, `1.0` respectively).

Those checks therefore stay in Python semantic validation.

The inverse semantic layer also rejects `ratio_diagnostic` or `actinometry`
when no ratio residual is active. The mode name is an interpretation contract,
not a substitute for an objective term. See `capability_matrix.md` for the
corresponding input, output, and scientific-claim boundary.

Inverse semantic validation also requires every prior and smooth-array
regularization target to contain a fitted parameter. A valid case path alone is
not sufficient: a constraint on a fixed value would be constant throughout the
optimization and is rejected.

Case diagnostics may contain quality and convergence policies. JSON Schema
checks individual values; semantic validation checks that warning thresholds
are no stricter than the corresponding error thresholds and that refinement
factors are at least two.

A case selects its electron distribution through either the public `eedf`
plugin envelope or the frozen compatibility `plasma_mode` field. The public envelope
requires `kind` and `zones`; semantic validation checks the zone count and then
validates every merged zone specification with the registered plugin schema.
New models use only the public envelope. The retained adapter, its owner, and
its removal condition are listed in `compatibility_policy.md`.

Validation evidence has a small additional semantic audit in
`oescr.analysis.validation_evidence`. It verifies declared dataset files and
the acceptance evaluator by SHA-256, records the evaluator version and result
contract, and keeps
`declared_evidence_ready` separate from `external_quantitative_ready`.
External quantitative eligibility requires non-generated held-out data, a
non-synthetic measurement basis, and relative-response or absolute
calibration. It also requires `comparison.model_input_closure: closed` and
`comparison.evaluation_data_use: held_out_only`; this prevents a comparison
from passing when an unmeasured source density is adjusted against the same
evaluation data. `conditional` means the result still depends on an unclosed
input or unqualified model component, while `open` means a required physical
input is unavailable. The audit verifies the declaration but does not run the
physical comparison itself.
Supported physical measurement bases include spectral radiance, collected
power, photoelectrons, and volumetric photon rate. The last is kept distinct
because it is a source-volume production rate in m-3 s-1, not detector radiance
or power.

Benchmark `analysis_summary.yaml` has a separate runtime contract. Its
`analysis_contract` fixes the evidence and metric semantics required for
comparison; `run_fingerprint` records the candidate configuration and fit that
are allowed to differ. The strict gate rejects missing, unsupported, or
mismatched contracts.

## CLI

```bash
python scripts/validate_yaml.py case examples/case_init_cf4_o2_ar.yaml
python scripts/validate_yaml.py inverse examples/inverse_cf4_o2_ar.yaml
python scripts/validate_yaml.py project examples/project_cf4_o2_ar.yaml
python scripts/validate_yaml.py validation examples/benchmarks/nf3_ar_ccp_clean_2023/validation.yaml
python scripts/audit_validation_evidence.py
```

## Schema authoring policy

The repository follows these rules when adding new YAML fields.

- User-facing YAML fields should be added to a JSON Schema file.
- Cross-field logic should be added to `oescr.io.validators`.
- Plugin-specific settings should be validated by the plugin itself.
- Outer schemas must not duplicate a closed enum of registered plugin kinds.
- Backward-compatible shorthands may be accepted in raw YAML, but the normalized internal form should be explicit.

## Backward compatibility

The loader now coerces numeric-like YAML strings such as `1.0e16` into floating-point values before schema validation. This keeps older case files valid while still allowing strict numeric schema checks.

`compatibility_policy.md` is the authoritative inventory. Compatibility input
must normalize or resolve to a canonical representation; it may not introduce
a second physics or inverse execution path.

Validation evidence created before analysis contract v1 must be migrated by
adding `acceptance.evaluator_sha256`, `evaluator_version`, and
`result_contract`, then regenerating its analysis summaries. This is an
intentional incompatibility: accepting an unversioned evaluator would defeat
the evidence-integrity guarantee.
