# Curated real-dataized Ar / NF3 / Cl2 update

This revision adds three main upgrades:

1. **Curated cross-section CSVs** under `examples/data/cross_sections_curated/`
   - `Ar/`: effective excitation seeds for the Ar 750.4 nm and 763.5 nm CR branches, including stepwise seeds from Ar(1s5).
   - `NF3/`: literature-anchored smooth fits for total ionization, dominant attachment, two dissociation surrogates, and effective F-line emitters.
   - `Cl2/`: literature-anchored smooth fits for total ionization, attachment, total dissociation, and effective visible Cl-line emitters.

2. **Improved inverse objective**
   - full-spectrum residual
   - per-window shape fitting (`window_fit_weight`)
   - baseline-corrected line area residuals
   - baseline-corrected peak residuals
   - optional per-window normalization (`area`, `peak`, `l2`, or `none`)

3. **Window filtering by gas family**
   - cases can now declare `diagnostics.window_families` so that, for example, an NF3/Ar case only activates `Ar` and `NF3/Ar` windows from a shared registry.

## Important interpretation

These CSVs are **not verbatim LXCat redistribution bundles**. Instead they are **literature-anchored smooth fits** designed to make the code immediately usable for forward modeling, sensitivity analysis, and first-pass inverse studies while keeping provenance explicit.

Use these curves for:
- initializing model structure,
- building synthetic studies,
- checking identifiability,
- bootstrapping inverse problems before a project-specific preferred dataset is imported.

Replace them with project-approved exports or digitized reference curves when you freeze a production workflow.

## New objective keys

```yaml
fit:
  objective:
    spectrum_weight: 1.0
    window_fit_weight: 0.2
    window_fit_normalization: area   # area | peak | l2 | none
    window_baseline_mode: local_linear
    area_weight: 0.35
    peak_weight: 0.05
```

## New curated cases

- `examples/case_skeleton_nf3_ar.yaml`
- `examples/case_skeleton_cl2_ar.yaml`

Both now point at the curated CSVs and activate only their relevant window families.


## Explicit benchmark additions

The curated NF3/Ar and Cl2/Ar examples are now complemented by explicit benchmark directories in `examples/benchmarks/`.
These are not raw redistributed experimental spectra. They are literature-anchored, measurement-like cases intended for repeatable forward/inverse testing.
Use them when you want a named benchmark with documented process conditions instead of only a generic curated example.
