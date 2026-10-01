# Plugin interfaces and extension surface

This revision formalizes the extension points of the code base.

## Design goal

A third party should be able to answer three questions quickly.

1. **Which submodel am I replacing?**
2. **What configuration contract does it accept?**
3. **What method must I implement?**

To support that, the code now exposes explicit plugin registries and plugin contracts.
For the prior decision between a data-only addition and a plugin, and for the
exact supported edit points, see `docs/extension_workflow.md`.

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

Outer case/instrument schemas validate common envelope fields. Registered
geometry, EEDF, reaction-rate, band, trapping, wall, throughput, LSF, and
baseline plugins then validate their own local configuration. Geometry,
reaction-rate, and EEDF plugins are covered by end-to-end YAML tests.

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

The public case envelope is independent of the legacy `plasma_mode` selector:

```yaml
eedf:
  kind: my_eedf
  zones:
    - scale_eV: 2.4
    - scale_eV: 2.1
    - scale_eV: 1.8
```

`zones` must match `geometry.n_shells`. For each zone, OESCR combines the
envelope `kind` with that zone mapping, validates the resulting object against
the selected plugin schema, and passes it to `build_pdf`. A case must use either
`eedf` or the compatibility `plasma_mode` input, never both.

```python
import numpy as np

from oescr.api import EEDF_PLUGINS, EEDFPlugin


class MyEEDF(EEDFPlugin):
    kind = "my_eedf"
    description = "Example normalized energy-space EEDF."
    config_schema = {
        "type": "object",
        "required": ["kind", "scale_eV"],
        "properties": {
            "kind": {"const": "my_eedf"},
            "scale_eV": {"type": "number", "exclusiveMinimum": 0},
        },
        "additionalProperties": False,
    }

    def build_pdf(self, spec, energy_eV):
        pdf = np.sqrt(energy_eV) * np.exp(-energy_eV / spec["scale_eV"])
        return pdf / np.trapezoid(pdf, energy_eV)


EEDF_PLUGINS.register(MyEEDF())
```

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

Plugin schema validator objects are cached. Static geometry and instrument
preparation occurs during case compilation; runtime EEDF values remain
validated because fitted values change between evaluations.

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
