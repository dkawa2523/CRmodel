# Input / Output Specification

## Core input files

### Case YAML

Describes the forward model state and all physics/input resources.

Required sections:

- `states`
- `reactions`
- `instruments`

Common sections:

- `plasma_mode`
- `gas_mixture`
- `energy_grid`
- `geometry`
- `plasma_state`
- `transitions`
- `bands`
- `quenching`
- `losses`
- `wall`
- `residuals`
- `diagnostics`

### Inverse YAML

Describes measurements, objective, optimization, and fitted parameters.

Supports:

- `measurements` with `file`, `files`, or `files_glob`
- `parameters`
- `parameter_groups`
- `priors`
- `fit.objective`
- `fit.global`
- `fit.local`
- `fit.uncertainty`
- `fit.regularization`

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
