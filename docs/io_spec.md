# Input / Output Specification

## Core input files

### Case YAML

Describes the forward model state and all physics/input resources.

Required sections:

- `states`
- `reactions`
- `instruments`

Common sections:

- `eedf` (public plugin selector) or `plasma_mode` (compatibility input)
- `gas_mixture`
- `energy_grid`
- `geometry`
- `plasma_state`
- `transitions`
- `bands`
- `wall`
- `residuals`
- `diagnostics`

`reactions` is the canonical home for electron-impact, first-order, two-body,
and three-body linear CR processes. Legacy `quenching` and `losses` input is
accepted only as normalization syntax and is not retained in the compiled case.

### Inverse YAML

Describes measurements, objective, optimization, and fitted parameters.

Supports:

- `inference_mode`: `relative_shape`, `ratio_diagnostic`, `actinometry`, or
  `calibrated_absolute`
- `measurements` with `file`, `files`, or `files_glob`
- `parameters`
- `parameter_groups`
- `priors`
- `fit.objective`
- `fit.global`
- `fit.local`
- `fit.uncertainty`
- `fit.regularization`

`ratio_diagnostic` and `actinometry` require an active ratio objective. The
meaning, dimensional basis, and unsupported interpretation of every mode are
defined in `capability_matrix.md`.

### Project YAML

Single-file orchestration wrapper.

Fields:

- `kind: oescr_project`
- `project.name`
- `case`
- `inverse` optional for forward-only projects
- `outputs.default_dir`

## Measurement CSV

```csv
wavelength_nm,intensity
200.0,1.23e-4
200.5,1.40e-4
```

## Forward outputs

One CSV per instrument and chord:

- `{instrument_id}_chord_0.csv`
- `{instrument_id}_chord_1.csv`
- ...

Forward CLI workflows also write `diagnostics.yaml` containing:

- overall pass/warning/error status and categorized events
- optional energy/wavelength convergence results
- per-zone EEDF and CR diagnostics
- reaction/process records and state source/loss budgets
- cross-section and species-pack provenance

## Inverse outputs

- `fit_summary.yaml`
- `case_opt.yaml`

## Example compact inverse pattern

```yaml
measurements:
  - instrument_id: uvvis_lowres
    files_glob: measurements/uvvis_lowres_chord_*.csv

parameter_groups:
  - template: shell_array
    name_prefix: ne
    path: plasma_state.ne_shells_m3
    scale: log
    bounds: [5.0e15, 4.0e16]
```


## Schema files

The authoritative structural contracts are now stored in `oescr/schemas/`. The runtime loader does not depend on hand-written ad hoc checks alone anymore; it first validates the merged YAML document against JSON Schema, then applies semantic checks in `oescr.io.validators`.
