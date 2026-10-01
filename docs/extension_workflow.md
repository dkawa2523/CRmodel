# OESCR extension workflow

This is the shortest supported path for adding spectroscopic content without
editing unrelated forward or inverse orchestration. Prefer data and YAML
composition when the governing equation already exists. Add a plugin only when
the calculation itself changes.

## Data and configuration edit points

| Addition | Owning file or section | Required public fields | Core-code change |
|---|---|---|---|
| Species/emitter pack | a YAML file such as `examples/data/species_packs/o_777_reduced.yaml` | `kind: oescr_species_pack`; provenance `metadata`; one or more of `states`, `reactions`, `transitions`, `bands` | none |
| Pack selection | case `species_packs` | `yaml_file`; optional `namespace` | none |
| Electron-impact cross section | CSV beside the owning data pack | columns `energy_eV,sigma_m2`; comment metadata should identify source, process, and evidence status | none |
| Cross-section use | one `reactions` or physical `bands` entry | `cross_section_file` as the exclusive rate source; reaction/band identifiers and physical fields | none |
| Atomic state | pack or case `states` | `id`, `species`, `energy_eV`, `solve`; `mass_amu` when wall loss requires it | none |
| Radiative branch | pack or case `transitions` | `id`, `upper`, `lower`, `wavelength_nm`, `A_s-1`; optional `profile` and trapping data | none |
| Physical photon band | pack or case `bands` | `id`, `kind: electron_impact_photon_band`, `source_density_key`, exactly one rate source, `photon_yield`, profile fields; optional `branching_ratio` | none |
| Empirical band | pack or case `bands` with `emission_mode: empirical` | an effective band `kind`, its source density, coefficient/rate source, and profile | none; never use for absolute inference |
| Built-in EEDF selection | case `eedf` | registered `kind` and one zone-local mapping in `zones` per shell | none |
| Instrument selection | case `instruments` | inline instrument fields or `yaml_file`; a stable `id` | none |

Cross-section and profile paths inside a pack are resolved relative to the pack
file, not the case. Each rate-bearing reaction or band must have exactly one
rate source. A state pack should include every radiative branch needed for its
population balance; omitting unobserved branches changes predicted photon
yields.

The checked-in multi-gas example composes two independent packs:

```yaml
species_packs:
  - yaml_file: data/species_packs/ar_2p1_2p6_nist.yaml
  - yaml_file: data/species_packs/o_777_reduced.yaml
    namespace: oxygen
```

The O pack owns its reduced state, excitation, quenching, and transition. The
case still owns plasma composition and source densities. This remains a
reduced OESCR model and does not introduce global chemistry.

## ID and override policy

Pack composition is append-only in v1. A namespace prefixes pack-local IDs and
rewrites their internal state references; external collider and source-density
keys remain unchanged. Duplicate IDs after namespacing are errors and are
never silently overwritten.

There is no implicit merge, delete, or override operation. To replace a pack,
remove its case entry and select a replacement pack. To retain two variants in
one process, give them distinct namespaces. This policy keeps the compiled
model unambiguous and avoids order-dependent configuration behavior.

## When a plugin is actually required

Use the registries exposed by `oescr.api`. Every plugin supplies a stable
`kind`, description, plugin-local JSON Schema, and the group-specific execution
method.

| Changed equation | Implementation owner | Registry / base contract | Configuration selector |
|---|---|---|---|
| EEDF shape | `oescr/physics/eedf.py` | `EEDF_PLUGINS` / `EEDFPlugin.build_pdf` | `eedf.kind` plus `eedf.zones` |
| Reaction-rate law | `oescr/physics/rates.py` | `REACTION_RATE_PLUGINS` / rate plugin | reaction or band rate specification |
| Band photon production or contour | `oescr/physics/bands.py` | `BAND_EMISSION_PLUGINS` or `BAND_PROFILE_PLUGINS` | `bands[].kind` or `profile_kind` |
| Geometry projection | `oescr/geometry/plugin.py` | `GEOMETRY_PLUGINS` / geometry plugin | `geometry.mode` |
| Throughput | `oescr/instrument/throughput.py` | `THROUGHPUT_PLUGINS` | `instruments[].throughput.kind` |
| Line-spread function | `oescr/instrument/lsf.py` | `LSF_PLUGINS` | `instruments[].lsf.kind` |
| Baseline | `oescr/instrument/baseline.py` | `BASELINE_PLUGINS` | `instruments[].baseline.kind` |

Do not add a new workflow branch for a plugin. Registration, local validation,
and one public-YAML test should be enough. A new physical quantity also needs
an analytic or conservation test and an explicit output basis/unit.

## Verification

For the composed Ar/O example, run:

```text
python scripts/validate_yaml.py case examples/case_truth_cf4_o2_ar.yaml
python scripts/run_forward.py examples/case_truth_cf4_o2_ar.yaml --out multigas_output
pytest tests/test_model_contracts.py -q
```

The regression test checks namespace isolation, two-pack provenance, internal
reference rewriting, pack-relative cross-section rebasing, and duplicate-ID
rejection. Forward diagnostics provide the final cross-section hash and EEDF
coverage used by the calculation.
