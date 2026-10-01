# External validation datasets

This directory holds independently sourced datasets being prepared for OESCR
scientific validation. A dataset directory is not a validation claim by itself.
Only a package with a completed `validation.yaml`, immutable artifacts, a
versioned evaluator, and passing declared tolerances is counted by the evidence
audit.

Prepared candidates may deliberately omit `validation.yaml` while their model
scope or comparator is unresolved. This keeps data acquisition separate from
model acceptance and prevents an available dataset from being reported as a
successful validation.

Current candidates:

- `schuecke_2025_no_uv`: absolute N2/O2 UV-production data; input closure is
  open because the dominant N2(A) source density is not independently known.
- `arellano_2023_ar_ccp`: response-corrected Ar 763.5/750.4 nm ratios; the
  low-pressure subset now has untuned, licensed-input BSR and NGFSRDW
  corona-limit calculations over matched-mean-energy EEDF families and
  threshold bases. Their 3.68-5.09-fold line-ratio discrepancy is explicit,
  neutral-Ar quenching is bounded as negligible, and a 40 eV/1 mTorr cascade
  anchor is recorded but not transferred across conditions. There is no
  validation verdict because the model spread is not an uncertainty
  distribution and independent EEDF closure, pressure-applicable cascade, and
  high-pressure metastable/trapping inputs remain unresolved.

The 2026-09-30 v1 selection gate rejected both candidates for a quantitative
accuracy claim. OESCR v1 therefore deliberately ships with no external
quantitative qualification; these packages remain prepared research evidence,
not hidden acceptance tests.
