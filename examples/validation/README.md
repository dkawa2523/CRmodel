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

`benchmark_portfolio.yaml` is the machine-readable post-v1 acquisition and
qualification plan. It adds no validation verdict. It fixes the priority,
independent unit, minimum condition design, split, supported claim, and
explicitly unsupported claim for multi-condition Ar, O2, NF3, Cl2, CF4, SF6,
C4F8, and N2 cases. The rationale and literature review are in
`docs/multi_spectrum_benchmark_plan.md`.

`external_eedf_rate_template` is the executable file-contract template for the
first portfolio case. The independent solver writes frozen EEDF/rate tables;
`scripts/prepare_bolsig_reference_run.py` prepares the fixed official-console
instruction and provenance manifest without importing OESCR, while
`scripts/compare_external_eedf_rates.py` verifies their hashes and compares
them with OESCR's tabulated-EEDF rate path. The template and its analytic unit
test are infrastructure, not external validation evidence.

The Daly five-gas path has a separate external preflight producer:

```bash
python scripts/prepare_daly_surrogate_pilot.py \
  --output-dir .local_outputs/daly_surrogate_pilot \
  --source-revision <official-repository-commit> \
  --tool-encoder-dir path/to/tool_encoder_l4 \
  --spectra-decoder-dir path/to/spectra_decoder_l4 \
  --execute
```

It generates 30 deterministic setpoints per gas system and one 3072-bin CSV
per setpoint from the authors' released model. Run it in an isolated environment
with the model-compatible TensorFlow version; TensorFlow is intentionally not
an OESCR dependency. This output is an external empirical-surrogate preflight,
not a substitute for the 48.8 GB held-out measured archive.
