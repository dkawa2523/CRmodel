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
profiles/
measurements/
```

Use `project.yaml` as the entry point for day-to-day work.

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

### 4. Compact parameter groups

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

### 5. Compact measurement loading with glob

```yaml
measurements:
  - instrument_id: nf3_benchmark_uvvis
    files_glob: measurements/chord_*.csv
```

This avoids repetitive measurement file lists.

## Canonical case schema

At runtime the case config is normalized to a canonical schema containing at least:

- `plasma_mode`
- `gas_mixture`
- `energy_grid`
- `geometry`
- `plasma_state`
- `states`
- `reactions`
- `transitions`
- `bands`
- `quenching`
- `losses`
- `residuals`
- `wall`
- `diagnostics`
- `instruments`

## Canonical inverse schema

The inverse config is normalized to:

- `measurements`
- `fit`
- `parameters`
- `priors`

`parameter_groups` and compact regularization entries are expanded before validation.

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
