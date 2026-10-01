# Configuration Guide

## Recommended file layout

A practical project layout is:

```text
project.yaml
case_truth.yaml
case_init.yaml
inverse.yaml
instrument.yaml
windows.yaml
validation.yaml
profiles/
measurements/
```

Use `project.yaml` as the entry point for day-to-day work.

Use `validation.yaml` only for a qualification dataset. It declares the
evidence level, source, calibration, preprocessing, immutable file hashes,
model-input closure, evaluation-data use, acceptance evaluator hash/version,
result contract, and limitations; it is not part of forward-model input.
Changing an evaluator requires updating its hash and version instead of
silently reusing prior acceptance evidence.

## New convenience features

### 1. YAML include

Any YAML mapping can now include one or more base files:

```yaml
include: case_truth.yaml

plasma_state:
  te_shells_eV: [2.4, 2.1, 1.9]
```

The included file is deep-merged first, then the local file overrides only what changed.

### 2. Path rebasing

If an included YAML fragment contains relative file paths such as:

- `cross_section_file`
- `profile_file`
- `window_registry`
- `yaml_file`
- `file`
- `files`

those paths are automatically rebased relative to the including YAML. This keeps modular YAML safe even when files live in different folders.

### 3. `${THIS_DIR}` expansion

Use `${THIS_DIR}` inside YAML strings when an absolute path rooted at the current YAML location is useful.

### 4. Public EEDF model selection

New EEDF models use a plugin envelope that does not require adding another
`plasma_mode` value:

```yaml
eedf:
  kind: eedf_tabulated
  zones:
    - energy_eV: [0.0, 1.0, 2.0, 5.0, 10.0]
      fE: [0.0, 0.45, 0.32, 0.08, 0.0]
```

Provide one zone mapping per geometry shell. The same form accepts registered
third-party EEDF kinds. Existing `plasma_mode` cases remain valid compatibility
inputs; do not specify `plasma_mode` and `eedf` together.

### 5. Compact parameter groups

Instead of writing one inverse parameter per shell, use `parameter_groups`:

```yaml
parameter_groups:
  - template: shell_array
    name_prefix: ne
    path: plasma_state.ne_shells_m3
    scale: log
    bounds: [4.0e15, 3.0e16]
```

This expands internally to one parameter per shell.

### 6. Compact measurement loading with glob

```yaml
measurements:
  - instrument_id: nf3_benchmark_uvvis
    files_glob: measurements/chord_*.csv
```

This avoids repetitive measurement file lists.

### 7. Reusable species packs

Use a species pack to add OESCR states, reactions, transitions, and bands
without copying lists into every gas-mixture case:

    species_packs:
      - yaml_file: species/ar_reduced.yaml
        namespace: ar

The namespace is applied to local IDs and their internal references. Duplicate
IDs are rejected; they are never silently overwritten. Paths inside a pack are
resolved relative to the pack file. Species packs compose externally supplied
densities and spectroscopy only; they do not solve global chemistry.

Put stable level and radiative data in a pack, but keep the excitation and
quenching processes that define a particular reduced model in the case (or in
a separate, explicitly selected process pack). For example, the packaged Ar
2p1/2p6 atomic data are selected with:

    species_packs:
      - yaml_file: data/species_packs/ar_2p1_2p6_nist.yaml

That pack owns both levels and all NIST-listed decay branches from them. A case
chooses its own ground-state and metastable excitation cross sections. This
boundary lets atomic data be corrected once without silently changing which
collisional mechanisms a case claims to include.

`examples/case_truth_cf4_o2_ar.yaml` composes that Ar pack with the namespaced
O 777 nm reduced pack. The complete edit-point and no-implicit-override policy
is in `docs/extension_workflow.md`.

### 8. Inference modes

Every inverse run has an explicit interpretation. The backward-compatible
default is:

    inference_mode: relative_shape

The authoritative capability and interpretation table is
`docs/capability_matrix.md`. `ratio_diagnostic` and `actinometry` must activate
at least one ratio residual through `window_ratio_weight`, a positive explicit
pair weight, or named ratio feature covariance. Selecting the mode name alone
is rejected because it would not change the information used by the fit.

Use calibrated_absolute only with auto_gain_fit set to false and an externally
validated absolute instrument/source-density model. Every instrument must
declare calibration.kind, absolute, input_basis, output_unit, and a calibration
reference. A one-standard-deviation fractional scale error can be declared as
relative_standard_uncertainty. Three transforms are supported:

- spectral_radiance keeps W_m-2_sr-1_nm-1;
- collected_spectral_power multiplies radiance by collection area, collection
  solid angle, and viewing factor to produce W_nm-1;
- photoelectron_spectrum additionally applies integration time, photon energy,
  and quantum efficiency to produce photoelectron_nm-1.

Baseline values are interpreted in the selected output unit. Passing the
calibration checks means only that the prerequisites are present. Local scale
identifiability is set after the fitted Jacobian has been evaluated. Empirical
effective bands are rejected in calibrated_absolute mode. Other supported
modes are ratio_diagnostic and actinometry. Actinometry uses the shared ratio
objective; it is an interpretation contract requiring externally qualified
actinometer/target kinetics, not a separate chemistry solver.

The minimal runnable configurations in `examples/use_cases/two_band/` show all
three modes with one shared physical case. The directory README lists the
expected fitted values and the result fields that must be checked.

In calibrated_absolute mode, every measurement CSV must also declare comment
metadata for output_basis, output_unit, and calibration_reference. These values
must match the compiled instrument transform; unitless or differently
calibrated data are rejected before optimization.

Measurement CSV files may add a positive sigma column. When present, it weights
the full-spectrum residual point by point. A measurement entry may instead
declare covariance_file, or covariance_files aligned with files/files_glob.
The matrix must be finite, symmetric, positive definite, and match the spectrum
length; residuals are whitened by its Cholesky factor. Pointwise sigma and a
covariance matrix are mutually exclusive.

A measurement entry can whiten correlated window areas, peaks, and explicit
ratio pairs by naming each feature in covariance order:

    measurements:
      - instrument_id: uvvis
        file: measured.csv
        feature_covariance:
          names:
            - window:Ar750:area
            - window:Ar763:peak
            - ratio:Ar750_to_Ar763
          matrix:
            - [0.0100, 0.0010, 0.0000]
            - [0.0010, 0.0225, 0.0020]
            - [0.0000, 0.0020, 0.0400]

Ratio features must use a name declared in
fit.objective.window_ratio_pairs. A feature listed in this covariance is not
also multiplied by its scalar area_weight, peak_weight, or ratio-pair weight;
this prevents double counting. Its matrix describes the covariance of the
normalized feature residuals, not covariance in raw radiance units. If a named
feature is disabled or removed by low-signal gating, the run fails explicitly
instead of silently dropping a covariance row.

For calibrated_absolute runs, relative_standard_uncertainty adds the common
multiplicative term

    C_effective = C_measurement + (u_rel * y) (u_rel * y)^T

to the pixel covariance. Therefore a positive calibration uncertainty requires
either pointwise sigma values or a measurement covariance. The calibration
contribution and its value are fixed from the observed spectrum during a fit;
FitResult also reports the configured value per instrument.

### 9. Physical and empirical emission modes

The default is emission_mode: physical. It accepts atomic radiant-power lines
and electron_impact_photon_band components, which share the same volume
spectral-radiant-power basis. Cases using effective_excitation_band or
effective_density_band must explicitly set emission_mode: empirical. This is a
migration requirement: the explicit marker prevents empirical amplitudes from
being mistaken for dimensioned radiance.

A molecular-band-only case may use empty states and reactions arrays. The CR
result then reports solve_method: empty instead of requiring dummy atomic
states or zero-rate reactions.

### 10. Dimensioned reaction processes

The canonical reactions list supports four linear reduced-CR process families:

    reactions:
      - id: excite_X
        kind: electron_excitation
        source_state: X
        target_state: X_excited
        cross_section_file: data/X_excitation.csv
      - id: spontaneous_nonradiative_loss
        kind: first_order
        source_state: X_excited
        coefficient_s-1: 2.0e3
      - id: quench_by_Ar
        kind: two_body
        source_state: X_excited
        colliders: [Ar]
        coefficient_m3_s: 1.0e-16
      - id: three_body_loss
        kind: three_body
        source_state: X_excited
        colliders: [Ar, Ar]
        coefficient_m6_s: 1.0e-42

target_state is optional for an untracked sink. Electron excitation requires a
target and exactly one rate source. First-, two-, and three-body processes use
only the coefficient field matching their displayed unit. Collider count is
fixed by kind, and collider densities must come from gas fractions, radicals,
metastables, or enabled residual-gas inputs.

Legacy quenching and losses sections are still accepted at the input boundary
and normalized once into two_body and first_order reactions. They are no longer
separate CR execution paths; new cases and species packs should use reactions.

### 11. Actionable quality diagnostics

Forward quality checks are enabled by default. Normal cases need no additional
configuration. Thresholds can be overridden explicitly:

    diagnostics:
      quality:
        enabled: true
        on_error: raise  # or report
        thresholds:
          cr_condition_warn_above: 1.0e10
          cr_condition_error_above: 1.0e14
          cr_residual_warn_above: 1.0e-8
          cr_residual_error_above: 1.0e-5
          negative_population_fraction_warn_above: 1.0e-12
          negative_population_fraction_error_above: 1.0e-6
          eedf_upper_decile_warn_above: 1.0e-2
          eedf_upper_decile_error_above: 5.0e-2
          eedf_edge_relative_warn_above: 2.0e-2
          eedf_edge_relative_error_above: 1.0e-1
          cross_section_coverage_warn_below: 0.99
          cross_section_coverage_error_below: 0.90

raise stops a forward/inverse evaluation on an error event and attaches the
complete report to DiagnosticPolicyError. report returns the result with
quality_report.status: error for deliberate inspection workflows. Singular CR
matrices always produce the category cr.singular_matrix when the system is not
empty.

Grid convergence requires additional forward solves and is therefore opt-in:

    diagnostics:
      convergence:
        enabled: true
        energy_grid_factor: 2
        wavelength_grid_factor: 2
        warn_relative_above: 1.0e-3
        error_relative_above: 1.0e-2

The check refines each grid independently and compares spectra on the same
instrument output bins using the maximum relative L2 difference. The base
internal wavelength resolution can also be increased permanently with
numerics.wavelength_refinement_factor, whose default is 1.

## Canonical case schema

At runtime the case config is normalized to a canonical schema containing at least:

- either public `eedf` or compatibility `plasma_mode`
- `emission_mode`
- `gas_mixture`
- `energy_grid`
- `geometry`
- `plasma_state`
- `states`
- `reactions`
- `transitions`
- `bands`
- `residuals`
- `wall`
- `diagnostics`
- `instruments`
- expanded species packs and their provenance in the compiled result

## Canonical inverse schema

The inverse config is normalized to:

- `measurements`
- `inference_mode`
- `fit`
- `parameters`
- `priors`

`parameter_groups` and compact regularization entries are expanded before validation.

Every `priors[].path` and `fit.regularization.smooth_arrays[].path` must contain
at least one fitted parameter path. Constraints on fixed case values are
rejected because they add a constant residual and cannot inform optimization.
Before adding a parameter group, run:

```bash
python scripts/summarize_identifiability.py case.yaml inverse.yaml --out observability.yaml
```

The summary is measurement-data-only and includes named singular directions,
column norms, inactive parameters, rank, and condition number. It must not be
interpreted as including information supplied by priors or smoothing.

## Single-file project execution

Example `project.yaml`:

```yaml
kind: oescr_project
project:
  name: nf3_ar_ccp_clean_2023
case: case_init.yaml
inverse: inverse.yaml
outputs:
  default_dir: runs/default
```

Run it with:

```bash
python scripts/run_project.py examples/benchmarks/nf3_ar_ccp_clean_2023/project.yaml --task inverse
```

Validate it with:

```bash
python scripts/validate_project.py examples/benchmarks/nf3_ar_ccp_clean_2023/project.yaml
```

## Guidance on keeping YAML manageable

- Put long state, reaction, and transition definitions in truth/base files.
- Put inverse starting guesses in `case_init.yaml` as small overrides.
- Put instrument response in separate `instrument.yaml` files.
- Put diagnostic windows in separate `windows.yaml` files.
- Use `parameter_groups` whenever a shell array is fitted elementwise.
- Prefer `files_glob` for chord measurements.


## Structural validation

Use `scripts/validate_yaml.py` to validate any merged YAML against its machine-checkable schema before running an expensive simulation.

```bash
python scripts/validate_yaml.py case examples/case_init_cf4_o2_ar.yaml
python scripts/validate_yaml.py inverse examples/inverse_cf4_o2_ar.yaml
```
