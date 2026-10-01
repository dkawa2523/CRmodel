# External EEDF/rate reference package

This directory defines the file boundary between an independent electron
Boltzmann solver and OESCR. It is a template, not scientific evidence and not a
passing benchmark.

The independent workflow must create two long-form CSV files without importing
OESCR:

- `external_eedf.csv`: `condition_id,energy_eV,energy_pdf_eV_inv`
- `external_rates.csv`:
  `condition_id,process_id,rate_coefficient_m3_s`

Convert a solver-specific EEPF $g(E)$ in eV$^{-3/2}$ to the energy probability
density $p(E)=\sqrt{E}\,g(E)$ in eV$^{-1}$ and normalize it in the independent
workflow; do not let OESCR infer the convention. Confirm this formula against
the exact external solver's output definition. Convert each
LXCat process to the OESCR cross-section CSV columns `energy_eV,sigma_m2`
without smoothing or fitting. Record the native LXCat database name, process
ID, retrieval date, row count, native-file hash, conversion command, and
converted-file hash in the completed package.

Copy `reference.template.yaml`, replace every placeholder, and run:

```powershell
python scripts/compare_external_eedf_rates.py `
  path\to\reference.yaml `
  --output-dir .local_outputs\external_eedf_rate
```

The evaluator verifies all declared hashes and the complete condition/process
matrix before calculating anything. It then imports each tabulated EEDF,
checks normalization/interpolation/mean energy, recomputes every declared rate
coefficient with the public OESCR calculation units, and records cross-section
energy coverage. Near-zero external rates use an absolute-error gate. The same
command writes two publication-oriented figures for each gas mixture:

- `*_eedf.png` overlays the frozen external EEDF and the EEDF actually imported
  by OESCR at every reduced field. Shape disagreement, interpolation artifacts,
  or an energy-range truncation should be visible directly.
- `*_summary.png` compares mean electron energy and plots every non-negligible
  process rate as `OESCR / external`. The green band is the declared relative
  acceptance interval and the black line is exact agreement.

The JSON and CSV remain the auditable numerical result; the figures are a
compact physical interpretation of the same values. Use `--no-plots` only in
minimal/headless checks where Matplotlib output is intentionally unnecessary.

The template deliberately does not launch BOLSIG+ or COMSOL. Reference
production is an external process; the evaluator only consumes frozen files.
The analytic pytest fixture for this evaluator proves software behavior only
and must never be reported as external physical validation.

The planned baseline uses the official BOLSIG+ 07/2024 console application
(`bolsigminus`). Obtain it directly from the official site and record its
binary hash. Its terms do not permit third-party redistribution, so the
executable must never be copied into this repository or a generated package.

Prepare the fixed pure-Ar run before executing it:

```powershell
python scripts/prepare_bolsig_reference_run.py `
  "C:\path\Ar_Biagi.txt" `
  --output-dir .local_outputs\bolsig_ar_reference `
  --expected-collision-sha256 43cefbee063bb43df5a1a593c40e6370dc745bf9460300ad3ade5886a71363b1
```

This writes a six-condition `bolsigminus` instruction file for 10, 30, 50,
100, 200, and 300 Td plus a manifest containing the collision and instruction
hashes. It imports no OESCR module. After obtaining the official executable,
repeat the command with `--execute --executable "C:\path\bolsigminus.exe"`.

The prepared state is explicitly `not_executed`; only a successful run records
the executable and result hashes. Converting the native run-by-run result into
`external_eedf.csv` and `external_rates.csv` remains an external-format step;
the OESCR comparator must never be used to generate its own reference values.

## Preparing native LXCat inputs

Keep the native download outside version control. Inventory every process and
optionally export only the rate processes needed by OESCR:

```powershell
python scripts/prepare_lxcat_cross_sections.py "C:\path\Cross section.txt" `
  --inventory .local_outputs\lxcat\inventory.json `
  --export-dir .local_outputs\lxcat\cross_sections `
  --select "Ar -> Ar(2P6)" `
  --select "Ar -> Ar(2P1)" `
  --select "Ar -> Ar^+"
```

The inventory fixes the native file hash, database, process labels, row counts,
energy ranges, and numeric curve hashes. Exported CSVs preserve those values in
comment metadata and are accepted directly by `CrossSectionLibrary`. BOLSIG+
must still read the native complete collision set independently; exporting a
few OESCR rate processes is not a substitute for the solver input.
