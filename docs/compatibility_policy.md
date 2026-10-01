# Compatibility policy

OESCR keeps compatibility only where an older input can be converted to the
same canonical model without creating a second numerical implementation. New
cases should use the canonical form. Compatibility code must have one owner,
one target representation, and an explicit removal condition.

| Retained input or API | Single owner | Canonical target | Why it remains | Removal condition |
|---|---|---|---|---|
| `plasma_mode` and its legacy `plasma_state` EEDF arrays | `oescr.physics.eedf.resolve_eedf_plugin_spec` | one registered EEDF plugin specification per zone | existing pre-v1 cases still use this spelling; both forms execute the same plugin kernels | a major input-format revision after maintained examples and downstream cases have migrated to `eedf.kind` plus `eedf.zones` |
| top-level `quenching` and `losses` sections | `oescr.io.normalize._migrate_legacy_cr_sections` | dimensioned entries in `reactions` | old cases can be loaded without retaining the former CR assembly path | a major input-format revision after a documented migration period |
| numeric-looking YAML strings | `oescr.io.yaml_loader` | Python numeric values before schema validation | scientific YAML commonly contains exponential notation parsed as text by YAML 1.1 readers | when the supported YAML reader guarantees the same numeric interpretation |
| `from oescr import OESCRModel, InverseSolver` | lazy package exports in `oescr.__init__` | workflow classes in their owning modules | preserves the small public import surface without eagerly importing optimization/reporting dependencies | only in a major public-API revision |

The legacy EEDF adapter is a selection adapter, not a separate EEDF model: it
returns the same plugin specifications used by the canonical `eedf` envelope.
New EEDF kinds must be added only through the plugin registry and must not add
new `plasma_mode` branches.

The empirical band emitters are not an implicit compatibility fallback. They
are an explicit, retained `emission_mode: empirical` capability for
literature-anchored relative-shape fixtures. Their mixed basis is reported,
and they are rejected for calibrated-absolute inversion.

## Removed in the v1 cleanup

- duplicated `OESCRModel` aliases for compiled state, grids, solvers, and
  instruments;
- the accidental `window_features` re-export from inverse objectives;
- unreferenced helper functions with no public callers;
- duplicate root-level inverse/measurement copies of benchmark packages;
- generated benchmark run and optimizer output files from version control.

Generated outputs belong in ignored local output directories. Fixed benchmark
`measurements/` and `forward_truth/` remain versioned because their hashes are
part of the scientific-evidence contract.
