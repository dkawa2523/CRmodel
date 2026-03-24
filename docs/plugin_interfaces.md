# Plugin interfaces and extension surface

This revision formalizes the extension points of the code base.

## Design goal

A third party should be able to answer three questions quickly.

1. **Which submodel am I replacing?**
2. **What configuration contract does it accept?**
3. **What method must I implement?**

To support that, the code now exposes explicit plugin registries and plugin contracts.

## Built-in registries

- `EEDF_PLUGINS`
- `REACTION_RATE_PLUGINS`
- `BAND_PROFILE_PLUGINS`
- `BAND_EMISSION_PLUGINS`
- `TRAPPING_PLUGINS`
- `WALL_LOSS_PLUGINS`
- `GEOMETRY_PLUGINS`
- `THROUGHPUT_PLUGINS`
- `LSF_PLUGINS`
- `BASELINE_PLUGINS`

These are available from `oescr.api`.

## Core contract

All plugins derive from `oescr.plugins.base.PluginBase`.

A plugin provides:

- `kind` — stable selection key used in configuration or internal resolution
- `description` — human-readable catalog entry
- `config_schema` — JSON Schema fragment for plugin-local validation
- a model-specific execution method

Registries use `PluginRegistry` to:

- register built-ins and third-party extensions
- validate plugin-local config before runtime use
- expose a machine-readable catalog

## Built-in plugin groups

### EEDF plugins

Located in `oescr.physics.eedf`.

Execution method:

```python
build_pdf(spec, energy_eV) -> np.ndarray
```

Built-ins:

- `te_maxwell`
- `te_druyvesteyn`
- `te_bimaxwell`
- `eedf_bimaxwell`
- `eedf_tabulated`

### Reaction-rate plugins

Located in `oescr.physics.rates`.

Execution method:

```python
rate(rate_calc, spec, eedf_pdf) -> float
```

Built-ins:

- `cross_section_file`
- `threshold_model`
- `constant`

### Band plugins

Located in `oescr.physics.bands`.

Profile method:

```python
profile(cfg, band, wavelength_nm) -> np.ndarray
```

Emitter method:

```python
emissivity(cfg, band, wavelength_nm, external_densities, eedf_pdf, rate_calc) -> np.ndarray
```

### Trapping plugins

Located in `oescr.physics.trapping`.

Execution method:

```python
effective_A(A_s1, trapping_cfg, zone_context) -> float
```

### Wall-loss plugins

Located in `oescr.physics.wall`.

Execution method:

```python
loss_rate(wall_cfg, geometry_cfg, gas_temperature_K, state_id, species, mass_amu) -> float
```

### Geometry plugins

Located in `oescr.geometry.plugin`.

Execution methods:

```python
build_matrix(cfg) -> np.ndarray
postprocess_chord_spectra(cfg, chord_spectra) -> np.ndarray
```

### Instrument-model plugins

Located in `oescr.instrument.*`.

- throughput
- LSF
- baseline

## Example: register a custom wall-loss model

```python
from oescr.physics.wall import WALL_LOSS_PLUGINS, WallLossPlugin

class MyWallModel(WallLossPlugin):
    kind = "my_wall_model"
    description = "Example extension"
    config_schema = {
        "type": "object",
        "required": ["model", "alpha"],
        "properties": {
            "model": {"const": "my_wall_model"},
            "alpha": {"type": "number", "minimum": 0.0},
        },
        "additionalProperties": False,
    }

    def loss_rate(self, wall_cfg, geometry_cfg, gas_temperature_K, state_id, species, mass_amu):
        return float(wall_cfg["alpha"])

WALL_LOSS_PLUGINS.register(MyWallModel())
```

## CLI catalog

```bash
python scripts/list_plugins.py
python scripts/list_plugins.py eedf
```

## Architectural consequence

This does **not** make the code magically complete. It does make the extension surface explicit, testable, and stable enough for long-term collaborative development.
