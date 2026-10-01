# OESCR Development Plan

Updated: 2026-09-30

## Purpose

Build a small, inspectable, and extensible reduced OES collisional-radiative
platform that can:

- synthesize spectra from explicitly supplied plasma state and composition;
- evaluate sensitivity and experimental observability;
- support clearly scoped relative, ratio, actinometric, and calibrated-absolute
  inverse workflows;
- add gas species, cross sections, emitters, and instrument models without
  editing unrelated workflow code;
- report enough numerical, unit, and data-provenance information to decide
  whether a result is physically interpretable.

The project does not add a self-consistent global chemistry model. Parent,
radical, and metastable densities remain explicit inputs or fitted quantities
whose identifiability must be demonstrated.

## Completion boundary

Two different outcomes must not be called the same kind of completion:

1. **OESCR v1 platform completion** means that the reduced CR/OES calculation
   units, public inputs and outputs, extension points, diagnostics, examples,
   and maintenance gates form a small and understandable system.
2. **External model qualification** means that one specified gas, transition
   set, operating range, and inference claim has passed a held-out experiment
   with closed inputs and a fixed tolerance. Qualification applies only to that
   declared scope; it is an ongoing evidence track, not permission to keep
   expanding the platform until every dataset can be explained.

The v1 platform is complete when all of the following are true:

- forward physical line/band calculation has one documented runnable path;
- `relative_shape`, `ratio_diagnostic`, `actinometry`, and
  `calibrated_absolute` each have a minimal runnable example or are removed
  from the public contract;
- each mode states required calibration, externally supplied densities,
  identifiable quantities, units, and unsupported claims in one capability
  matrix;
- a second reusable species pack composes with the Ar pack, and a test proves
  that a new pack can be added without editing the forward/inverse core;
- obsolete compatibility paths are either removed with their examples or
  explicitly retained at one documented input-normalization or model-selection
  boundary; no duplicate numerical implementation remains;
- architecture, Ruff, Pyrefly, Import Linter, Radon, unit, analytic, and
  end-to-end gates pass, and the edit points for data/model additions are
  documented;
- scientific evidence is labeled honestly: generated self-consistency,
  conditional external evidence, and externally qualified claims are never
  merged.

The following are not v1 completion requirements:

- a self-consistent global plasma chemistry or PIC/MCC solver;
- unrestricted reconstruction of an arbitrary tabulated EEDF from OES;
- externally validating every gas species, line set, and operating regime;
- changing the core model to compensate for a candidate dataset whose EEDF,
  source density, calibration, or uncertainty is not independently closed.

An unavailable external dataset blocks the corresponding accuracy claim, not
the completion of the reusable platform. Conversely, platform completion does
not turn a conditional candidate into a validated physical model.

**Status:** the OESCR v1 platform completion criteria were met on 2026-09-30.
External quantitative model qualification remains a separate evidence track.

## Design rules

1. Parse and validate user input once, then run numerical kernels on compiled
   objects.
2. Separate static model structure from runtime plasma-state parameters.
3. Never add quantities with different physical bases without making that
   distinction visible in the result.
4. Reject unsupported process types instead of evaluating them with a
   dimensionally wrong fallback.
5. Keep plugin-local configuration in the plugin contract; outer YAML schemas
   only define the envelope and common fields.
6. Prefer ordinary functions and small dataclasses over new framework layers.
7. Every fitted parameter must change an intended observation or be rejected.
8. A plan change must update affected schemas, documentation, examples,
   dependency contracts, and acceptance tests in the same change.

## Current position

| Work item | Status | Evidence / remaining work |
|---|---|---|
| Static/runtime compilation boundary | Complete | CompiledCase and ObservationPlan; reaction override and mutable-config regression tests |
| Hidden wavelength/instrument transport keys | Complete | Explicit arrays and compiled observation plan |
| Reaction-rate exactly-one contract | Complete | compiled electron-impact validation and tests; other families accept only their dimensioned coefficient field |
| Reaction process dimensionality | Complete for linear reduced CR | compiled electron-impact, first-order, two-body, and three-body records have fixed collider counts and coefficient units; solved-state colliders are rejected as nonlinear |
| Cross-section quality and provenance | Partial | finite/nonnegative/monotonic checks, metadata, hash, EEDF coverage; the Ar candidate verifies BSR/NGFSRDW process identities and exposes their direct-excitation model spread without redistributing licensed curves, while an uncertainty-bearing near-threshold reference and probabilistic discrepancy policy remain |
| CR/EEDF diagnostics | Complete for current kernels | categorized warn/error policy covers rank, condition, residual, negative fraction, EEDF edge indicators, and cross-section coverage; optional energy/wavelength convergence and CLI export are implemented |
| Emission-unit separation | Complete for current emitters | physical mode only combines radiant-power components; legacy effective bands require explicit empirical mode and report a mixed basis |
| Inverse use-case contract | Complete for v1 | four modes, dimensional calibration transforms, measurement-unit/reference matching, empirical-band rejection, calibration-scale uncertainty, and separate prerequisite/local-rank results are implemented |
| Measurement uncertainty | Complete for current objectives | pointwise sigma, correlated full-spectrum covariance, and named window-area/peak/ratio feature covariance use Cholesky whitening |
| Identifiability reporting | Complete for current benchmark line sets | measurement-only Jacobian, named singular directions, inactive parameters, and condition number; priors/regularization are excluded from observability and retained only for objective curvature |
| Uncertainty labeling | Complete for current method | Laplace result is explicitly labeled local conditional curvature |
| Plugin YAML extensibility | Complete for current plugin families | geometry, EEDF, rate, band, trapping, wall and instrument envelopes accept registered plugins; EEDF kinds use zone-local public YAML without adding plasma modes |
| Public capability contract | Complete | one matrix now fixes inputs, output bases/units, prerequisites, evidence levels, and unsupported claims; ratio/actinometry labels require an active ratio objective |
| Public use-case examples | Complete | one shared physical two-band fixture exercises ratio, actinometry, and calibrated-absolute YAML-to-result paths; generated evidence is explicitly not external qualification |
| Multi-gas OESCR composition | Complete for v1 | Ar and namespaced O 777 reduced packs compose in one runnable case; tests cover provenance, internal reference rewriting, path rebasing, namespace isolation, and duplicate rejection; v1 has an explicit no-implicit-override policy |
| Responsibility and deletion pass | Complete | generated outputs and duplicate fixtures removed; compiled ownership is singular; retained adapters have one owner and removal condition |
| Inverse objective responsibility | Complete | options, window, ratio, gain-prior, and regularization functions separated; residual_vector is no longer a complexity hotspot |
| Benchmark-report responsibility | Complete | pure metrics, shared records, concrete CSV/SVG/HTML/Markdown writers, report assembly, and CLI are separated with an enforced inward dependency direction |
| Independent scientific validation | v1 qualification decision complete; no external quantitative claim | analytic/grid checks, immutable evidence, versioned contracts, and eligibility audit are complete; the selection gate rejects both held-out candidates because required inputs or uncertainty are open |
| Release readiness | Complete for v1 platform | all four quality tools, 113 tests, project/evidence/link checks, and wheel import/package-data smoke test pass |

## Completed sequence to v1 platform completion

This is the authoritative priority order. The detailed phase history below
records how the current implementation was reached but does not override this
sequence.

### 1. Consolidate the public capability contract — complete

- Add one matrix covering forward, relative shape, ratio, actinometry,
  calibrated absolute, parametric EEDF sensitivity, and unsupported arbitrary
  EEDF reconstruction.
- For every row, state required inputs, returned quantities and units,
  identifiability/calibration prerequisites, and evidence level.
- Remove or correct documentation that implies a broader prediction claim.

Exit condition: a user can decide whether OESCR supports a task before reading
implementation code.

`docs/capability_matrix.md` now supplies this decision boundary. README,
configuration, physics, I/O, and schema documentation point to the same
contract. Semantic validation also rejects ratio and actinometry modes that do
not activate a ratio residual, eliminating a label-only execution path.

### 2. Complete one runnable vertical slice per retained use case — complete

- Keep the existing forward and relative-shape paths.
- Add the smallest valid ratio, actinometry, and calibrated-absolute examples
  using existing kernels; do not add new physics merely to make an example run.
- Record expected outputs, diagnostics, and the exact command for each example.

Exit condition: every public inverse mode is exercised from YAML through its
result contract, or the unexercised mode is removed from the public API.

`examples/use_cases/two_band/` now shares one physical case, diagnostic-window
registry, and generated measurement across the three previously uncovered
modes. End-to-end tests verify the recovered quantity, selected observations,
measurement-only rank, absolute prerequisites, and calibration uncertainty.
The exercise also corrected explicit wavelength-grid resolution gating to use
the spacing local to each diagnostic window. No new physics model was
introduced for this completion step.

### 3. Prove the multi-gas and extension workflow — complete

- Extract one additional reusable species pack from existing curated example
  data and compose it with the Ar pack in one case.
- Document the exact files and fields used to add a species, cross section,
  transition, band, EEDF, and instrument plugin.
- Test namespace isolation, provenance, path rebasing, and duplicate rejection
  without modifying forward/inverse orchestration.

Exit condition: a third party can add a supported spectroscopic species by
data/configuration extension rather than by editing unrelated workflow code.

The CF4/O2/Ar example now composes the Ar atomic-data pack with a namespaced O
777 nm reduced pack extracted from its former inline state, excitation,
quenching, and transition entries. A regression test verifies namespace
isolation, internal reference rewriting, two-pack provenance, pack-relative
cross-section paths, and duplicate rejection. `docs/extension_workflow.md`
lists the exact data/configuration and plugin edit points. The v1 replacement
policy is deliberately simple: composition is append-only, duplicate IDs are
errors, and replacement means selecting a different pack rather than applying
order-dependent overrides.

### 4. Perform the final responsibility and deletion pass — complete

- Inventory compatibility adapters, deprecated examples, duplicate data,
  unused helpers, and documentation that describes superseded behavior.
- Remove only paths whose callers and migration need are resolved; keep any
  required compatibility translation at one documented input or model-selection
  boundary.
- Re-run responsibility, dependency, complexity, and full regression gates.

Exit condition: retained compatibility has one owner and reason; obsolete code
and duplicate instructions are absent.

The pass removed generated benchmark run outputs, duplicate benchmark inverse
and measurement copies at the example root, compiled-object aliases on
`OESCRModel`, an accidental objective-module re-export, and six unreferenced
helpers. Fixed truth/measurement fixtures remain because evidence manifests
hash them. `docs/compatibility_policy.md` now records the single owner,
canonical target, reason, and removal condition for every retained adapter.
The next item is an evidence decision, not an invitation to add new chemistry
or a global model.

### 5. Bound scientific qualification instead of expanding the platform — complete for v1

- Freeze Arellano and Schuecke as conditional evidence at their demonstrated
  boundary; do not implement more chemistry simply to force a pass.
- Before new comparator code, require a dataset-selection gate: calibrated
  observable, independent required inputs, uncertainty, redistributable or
  reproducibly extractable data, and a claim already supported by OESCR.
- If a dataset passes that gate, implement one dataset-local evaluator and
  fixed tolerance. If none passes, release v1 with no external quantitative
  accuracy claim and retain the explicit blockers.

Exit condition: either one narrowly scoped external claim passes, or the
platform clearly states that no external quantitative claim is made. Both are
valid platform outcomes; only the former is a model qualification.

The 2026-09-30 selection gate found no eligible candidate. Schuecke has an
absolute observable but open N2(A) source density and incomplete probe-input
uncertainty. Arellano has a response-corrected ratio and a supported atomic
pathway, but the EEDF/cascade inputs and experimental/model-discrepancy
uncertainty are not closed. Both remain held-out research evidence without a
`validation.yaml`; no comparator or broader chemistry was added. OESCR v1
therefore makes no external quantitative accuracy claim.

### 6. Release-readiness review — complete

- Run all tests and the four architecture/quality tools.
- Verify every example command, result basis/unit, documentation link, and
  evidence label.
- Produce the final architecture review, supported-use-case matrix, known
  limitations, and next research items separately from v1 implementation work.

Exit condition: the implementation, documentation, examples, and declared
scientific evidence describe the same system.

`docs/v1_readiness_review.md` now consolidates the architecture result,
supported-use boundary, known scientific limits, and verification snapshot.
Ruff, pytest, Import Linter, Radon, project validation, evidence audit, and
documentation-link checks pass. Pyrefly 1.3.1 was run through WSL against the
installed Windows type information and reports 0 errors and 17 warnings. A
wheel build plus isolated import/package-data smoke test also passes. Remaining
tag/version selection and clean-checkout repetition are release operations,
not missing platform implementation.

## Completed in the current implementation increment

- Added one authoritative capability matrix covering physical/empirical
  forward use, all four inverse modes, parametric EEDF use, tabulated-EEDF
  forward use, instrument output bases, and unsupported arbitrary-EEDF
  inversion.
- Aligned README, configuration, physics, I/O, and schema documentation with
  that contract and removed the unconditional `T_e`/`n_e` inverse claim.
- Rejected label-only `ratio_diagnostic` and `actinometry` configurations when
  no ratio residual is active.
- Added minimal runnable ratio, actinometry, and calibrated-absolute examples
  backed by one physical two-band case and end-to-end recovery tests.
- Corrected diagnostic-window resolution checks for explicit wavelength grids
  to use the local observed bin spacing instead of an unrelated default.
- Completed the responsibility/deletion pass: generated outputs and duplicate
  inverse fixtures are no longer versioned, runtime aliases/re-exports and six
  dead helpers are removed, and retained compatibility has one documented
  owner and removal condition.
- Applied the external dataset-selection gate and closed the v1 qualification
  decision without expanding the model: neither candidate is eligible, so v1
  explicitly makes no external quantitative accuracy claim.
- Completed release readiness with all four quality tools, 113 tests, project
  and evidence audits, documentation-link checks, and a built-wheel import and
  package-data smoke test.
- Removed the superseded initial design-review document after its resolved
  findings were captured by the current plan, capability matrix, compatibility
  policy, scientific-validation status, and v1 readiness review.
- Added CompiledCase to own states, energy grid, rate calculator, CR solver,
  instruments, wavelength grid, and observation plan.
- Runtime ne/Te/EEDF/density changes reuse the plan; changes to reactions,
  transitions, geometry, wall, gas mixture, or instruments recompile safely.
- Removed the private fine-wavelength and instrument transport keys.
- Reused the same trapping zone context for CR populations and emitted lines.
- Added reaction exactly-one rate-source validation and rejected unsupported
  reaction kinds/collider dimensionality.
- Added cross-section table validation, comment metadata, SHA-256 provenance,
  and EEDF/data-range coverage diagnostics.
- Added CR and EEDF diagnostics to ForwardResult.
- Added separate atomic, band, and per-band spectra and declared each output
  basis.
- Added electron_impact_photon_band for a physically dimensioned molecular
  emission path while retaining legacy empirical emitters explicitly.
- Added relative_shape, calibrated_absolute, ratio_diagnostic, and actinometry
  inverse modes, plus local Jacobian identifiability results.
- Added namespaced species-pack composition without adding chemistry solving.
- Extracted the O 777 nm reduced emitter into a second reusable, namespaced
  pack and composed it with Ar in the CF4/O2/Ar example.
- Documented the exact species, cross-section, transition, band, EEDF, and
  instrument extension points and the v1 no-implicit-override policy.
- Centralized the Ar 2p1/2p6 levels and all five NIST-listed radiative branches
  in one reusable atomic-data pack, removing duplicated partial branch lists
  from two cases while leaving their collisional processes case-specific.
- Added immutable Chilton et al. direct-excitation anchors at 20, 40, and
  100 eV. The effective Ar seeds fail this input check by large,
  energy-dependent factors and remain explicitly non-validation-grade.
- Verified production LXCat BSR-500 Ar 2p1/2p6 processes against the earlier
  snapshot at every one of 196/218 points, fixed their numeric digests, and
  removed the redistributed raw curves in accordance with LXCat policy.
- Extended the diagnostic-only corona calculation to mean-energy-matched
  Maxwellian/Druyvesteyn EEDFs and native/NIST-aligned thresholds. The full
  BSR ratio envelope is 0.585-1.202, exposing low-energy EEDF shape as a
  blocker.
- Added independent LXCat NGFSRDW direct-excitation curves with the same
  licensed-input and numeric-identity checks. Their ratio envelope is
  0.115-0.321, and the BSR/NGFSRDW prediction spread is 3.68-5.09 at matched
  conditions. This closes the deterministic model-comparison task, while
  uncertainty weighting and cascade closure still prevent a pass.
- Evaluated Arellano's state-specific neutral-Ar quenching coefficients over
  the measured pressure and temperature range. The selected line-ratio shift
  is below 0.0063% at 10 Pa and below, so this loss is no longer a low-pressure
  blocker. Added the Chilton 40 eV, 1 mTorr cascade/direct anchor as an
  immutable materiality check; its nominal 1.587 ratio multiplier is not
  transferred to a different pressure or broad EEDF.
- Moved static geometry and instrument preparation into ObservationPlan.
- Split the inverse objective into small calculation functions.
- Added radiance, collected-power, and photoelectron calibration transforms and
  wrote output basis/unit metadata to forward CSV files.
- Added correlated spectrum covariance with Cholesky whitening.
- Isolated measurement parsing, unit metadata, covariance, and whitening from
  inverse objective assembly.
- Made physical emission the default and required explicit empirical mode for
  legacy effective emitters.
- Added a physical-band analytic benchmark; it exposed and fixed detector-bin
  edge integration loss.
- Removed the unnecessary requirement for dummy atomic states and reactions in
  molecular-band-only cases; an empty CR system is now an explicit result.
- Added named window-area, peak, and explicit ratio covariance without
  duplicating their scalar objective weights.
- Added common multiplicative calibration uncertainty to calibrated-absolute
  pixel covariance and exposed the configured value in FitResult.
- Added an analytic combined atomic-line plus physical-band conservation
  fixture through the shared line-of-sight and instrument path.
- Removed the unused case argument from measurement loading and the no-op
  measurement-group normalization pass.
- Compiled electron-impact, first-order, two-body, and three-body reactions into
  fixed, dimensioned process records before zone evaluation.
- Unified reaction, radiative, and wall terms as auditable matrix/RHS
  contributions and exposed per-state volumetric source/loss budgets.
- Removed separate runtime quenching/direct-loss assembly and the unreachable
  plasma_state.state_densities branch. Legacy quenching/loss input is migrated
  once at normalization.
- Removed the hidden 1e-30 CR diagonal repair; singular systems now remain
  visible to the existing least-squares diagnostics.
- Added categorized quality events and configurable warn/error thresholds for
  CR, EEDF, and cross-section coverage, with raise/report policies.
- Added opt-in independent energy- and wavelength-grid refinement checks on the
  final instrument-bin spectra.
- Added diagnostics.yaml output containing quality, convergence, per-zone
  process/state budgets, emission bases, and provenance to forward CLI runs.
- Corrected YAML-schema parsing of the literal string off, which previously
  rejected already-normalized configurations during convergence recompilation.
- Added validation-evidence declarations, immutable measurement hashes, and an
  eligibility audit that separates generated recovery from external
  quantitative validation.
- Separated measurement-data observability from prior/regularization curvature,
  named the parameter combinations in every singular direction, and rejected
  constraints that target no fitted parameter.
- Removed unobservable electron-density/electron-temperature groups and
  constant metastable priors from the generated NF3/Ar and Cl2/Ar inverse
  configurations, then reran their optimizations and strict gate.
- Added a versioned benchmark-analysis contract that fixes truth, measurements,
  metric definitions, windows, and analysis policy while recording candidate
  case/inverse/fit/package fingerprints separately.
- Removed obsolete historical-run defaults from the strict-gate CLI. Legacy or
  incompatible summaries now fail explicitly, and current-run `init` to `opt`
  comparison also guards window-classification non-degradation.
- Added evaluator SHA-256, evaluator version, and result-contract fields to
  scientific-evidence declarations and removed the conflicting hard-coded
  package version.
- Selected and digitized an independently measured 10 Pa N2/O2 ICP power scan
  with absolute UV rate, NO density, gas temperature, electron density, and
  electron temperature. Source/artifact hashes, raw vector coordinates,
  measurement uncertainty, and digitization tolerance are retained.
- Added `volumetric_photon_rate` as an explicit validation measurement basis.
  The candidate is not labeled as validation because its integrated signal is
  not a single band and the dominant N2(A) input was not independently measured.
- Required external quantitative evidence to declare independently closed
  model inputs and evaluation-only hold-out use; generated-truth comparisons
  remain explicitly separate.
- Added a second held-out candidate from an Ar CCP: the response-corrected
  763.5/750.4 nm ratio maps to existing OESCR pathways. Its low-pressure subset
  is reserved as an atomic-data check and is not mislabeled as an `n_e`, `T_e`,
  or EEDF diagnostic.
- Corrected the Ar 763.5106 nm upper-state assignment from `2p2` to NIST's
  `2p6`, including its energy, transition probability, seed filenames, example
  reactions, and a regression test; obsolete `2p2` Ar paths were removed.
- Split strict-gate argument parsing, comparison loading, gate calculation, and
  reporting. Its Radon grade improved from D to C without changing gate
  semantics; both evidence declarations carry the new evaluator hash.

## Implementation history

The numbered phases below explain the architectural work already performed.
For remaining v1 work, follow `Revised remaining sequence to v1 completion`
above.

### 1. Finish remaining uncertainty contracts — complete

- Add window-area, peak, and ratio feature covariance.
- Represent calibration-factor uncertainty and propagate it into the inverse
  uncertainty statement.
- Add a combined atomic-line plus physical-band conservation fixture.

Acceptance:

- feature residuals can be whitened with a declared covariance;
- calibration uncertainty is visible in FitResult;
- combined physical components conserve their analytic integrated power.

All three acceptance conditions have regression tests and enabled item 2.

### 2. Separate reaction process families — complete

- Introduce compiled electron-impact, first-order, two-body, and three-body
  process records with explicit coefficient units and reactant order.
- Evaluate family-specific frequencies, then feed one shared linear-transfer
  matrix/RHS assembler.
- Return state-by-state source/loss budgets.

Acceptance:

- each process has an analytic unit test;
- unsupported dimensions fail at compile time;
- process budgets reproduce the assembled matrix and RHS.

All acceptance conditions have analytic and end-to-end regression tests and
enabled item 3.

### 3. Make diagnostics actionable — complete

- Add warn/error thresholds for CR condition number, residual, negative
  pre-clip population, EEDF edge mass, and cross-section coverage.
- Add wavelength- and energy-grid convergence checks.
- Include diagnostics and provenance in CLI forward output, not only Python
  objects.

Acceptance:

- deliberately under-resolved or singular fixtures fail with a specific
  diagnostic category;
- normal examples pass without hidden repair.

Both deliberately singular and energy-range-under-resolved fixtures fail with
stable categories. Representative normal examples pass the default policy, and
all acceptance conditions have regression tests.

### 4. Complete extension and responsibility cleanup — complete

- Add a public EEDF plugin envelope independent of built-in plasma_mode. — complete
- Split analysis/benchmark_results.py into metrics, report model, renderers,
  and command orchestration. — complete
- Split inverse semantic validation into focused use-case, measurement, and
  optimization-policy checks behind the existing public validator. — complete
- Remove compatibility access to private model helpers from analysis/inverse.
  — complete

Acceptance:

- a third-party EEDF plugin runs from YAML;
- benchmark metrics can be tested without importing renderers;
- no D/E Radon block remains under `oescr`.

All acceptance gates pass. Concrete CSV, SVG, HTML, and Markdown writers now
live in `benchmark_renderers.py`; `benchmark_results.py` owns calculation and
report-data assembly only. Remaining platform work is now governed by the
revised finite sequence above rather than by unbounded candidate research.

### 5. Scientific evidence framework — complete; model qualification ongoing

- Add two-/three-level analytic CR fixtures, branching checks, and grid
  convergence. — complete for current linear CR kernel
- Add hold-out literature or calibrated experimental comparisons. — evidence
  protocol and eligibility gate complete; two independent datasets prepared,
  physically closed comparator pending
- Quantify which Te/EEDF modes are observable from each configured line set.
  — complete for the current generated NF3/Ar and Cl2/Ar line sets; arbitrary
  tabulated-EEDF inversion remains out of scope until a resolution analysis is
  supplied
- Propagate cross-section and model-discrepancy uncertainty beyond the fixed
  measurement/calibration covariance already supported.

Acceptance:

- each supported inference mode declares its prerequisites, evidence level,
  and unsupported claims;
- absolute ne is only reported for calibrated, locally identifiable cases;
- arbitrary tabulated-EEDF reconstruction is not presented as a supported v1
  result without a resolution/regularization analysis;
- an external pass/fail claim is emitted only for a dataset with independently
  closed inputs and a fixed tolerance.

The analytic-kernel and numerical-qualification layer is complete and recorded
in `docs/scientific_validation.md`. The current line-set audit removed six
inactive variables from Cl2/Ar and the three electron-density variables from
NF3/Ar. At the optimized points, Cl2/Ar is rank 6/6 with condition number 59.5;
NF3/Ar is rank 9/9 but weakly conditioned at 3.15e6, so its weakest Te/F
combinations must not be treated as robust experimental determinations.

For the Ar external candidate, radiative closure, production process identity,
licensed-input handling, EEDF-family sensitivity, threshold alignment, and a
deterministic BSR/NGFSRDW model-discrepancy sweep are complete. The two models
differ by 3.68-5.09 in line ratio under matched conditions, so their min/max
span is retained as diagnostic evidence rather than converted into a
probability distribution. State-specific neutral-Ar quenching is now bounded
and negligible in the corona limit. The Chilton cascade anchor is material but
cannot be transferred from 40 eV/1 mTorr to the discharge conditions. These
are recorded blockers for an Arellano-specific accuracy claim, not the next
platform implementation tasks. The candidate remains outside `validation.yaml`
and is frozen as conditional evidence unless it later passes the dataset gate
in the revised sequence.
Generated benchmark success remains labeled as self-consistency rather than
external validation. Comparison-contract versioning and preparation of the
Schuecke et al. 10 Pa dataset are complete, but the public archive could not be
reliably downloaded and N2(A) remains unmeasured. A second Arellano et al. Ar
CCP ratio dataset is now prepared because it directly exercises existing
750.4/763.5 nm OESCR pathways. Radiative branching is now complete for the two
selected upper levels, and independent absolute cross-section anchors show
that the existing excitation seeds cannot be promoted to validation data. A
second direct-excitation model now quantifies the unresolved cross-section
spread. Neutral-Ar quenching and monoenergetic cascade materiality are now
bounded without tuning to the held-out ratios. Further cascade or discrepancy
work belongs to model qualification only after its missing independent inputs
are available; it no longer displaces the remaining v1 usability work.
The NO dataset remains a
mechanism/identifiability challenge unless its narrow-band data and N2(A) input
can be closed. Cross-section/model-discrepancy uncertainty propagation follows
the first physically closed comparator.

## Change-control checklist

When priorities or model assumptions change, update all applicable items:

- this plan and its status table;
- docs/architecture.md and docs/physics_models.md;
- JSON schemas and plugin-local schemas;
- example YAML and migration notes;
- Import Linter contracts if dependency direction changes;
- unit, sensitivity, convergence, and benchmark tests;
- ForwardResult/FitResult diagnostics and provenance.

A change is not complete when code passes alone; documentation and the public
input/output contract must describe the same model.

## Plan decisions

### 2026-09-30: separate negligible quenching from unresolved cascade transfer

Arellano table 3 supplies state-specific neutral-Ar quenching coefficients for
2p1 and 2p6. Evaluating them with the measured pressure points, the reported
304-350 K range, and the complete NIST radiative rates changes the low-pressure
763.5/750.4 ratio by at most `6.29e-5`. This is retained as a candidate-local
corona-loss sensitivity rather than adding another core model or adjustable
parameter.

Chilton table III shows that cascade feeding is not similarly negligible: its
40 eV, 1 mTorr values imply a nominal ratio multiplier of 1.587. The quoted
error endpoints span 1.167-2.353, but this is an arithmetic envelope, not a
probability interval. Because the source demonstrates pressure-dependent
cascade through radiation trapping, applying that multiplier to the Arellano
EEDF/pressure sweep would conflate experimental conditions. The evaluator
therefore records but does not apply it. The plan narrows the next task to a
pressure-applicable higher-level cascade source for this candidate; no global
plasma-chemistry layer is introduced.

### 2026-09-30: retain cross-section model spread as evidence, not a fitted tolerance

The LXCat NGFSRDW database provides the same state-resolved, direct
ground-state Ar 2p1/2p6 excitation quantities as BSR-500. It can therefore be
compared in the corona-limit evaluator without mixing in apparent optical
emission, cascade, or radiation-trapping effects. The evaluator now verifies
NGFSRDW processes 2560/2567 exactly like the BSR inputs and keeps both raw
downloads outside the repository.

NGFSRDW predicts a 0.115-0.321 line-ratio envelope, compared with
0.585-1.202 for BSR. Under the same EEDF and threshold basis the ratio differs
by factors of 3.68-5.09. This completes the planned deterministic
multi-source comparison but does not define source probabilities or an
experimental uncertainty. The plan therefore advances cascade/quenching
sensitivity ahead of tolerance definition. A near-threshold experiment and
independent EEDF evidence are still required before weighting the two models
or adding `validation.yaml`; no global chemistry layer is introduced.

### 2026-09-29: verify licensed BSR inputs without redistributing them

The LXCat 2 production catalog identifies the 2014 Ar curves as processes
62286 (2p1) and 62281 (2p6). Their 196/218 numeric rows match the earlier API
snapshot exactly. LXCat's redistribution policy nevertheless requires users
to obtain data from LXCat directly, so the copied curve files were removed.
The candidate now records production identities, row counts, and hashes of the
numeric float64 pairs; its evaluator accepts a user-downloaded native file and
rejects changed data. This changes data delivery, not the physical model.

The same evaluator now compares Maxwellian and Druyvesteyn EEDFs at equal mean
energy and shifts each curve independently from its native threshold to the
NIST upper-level energy. The large low-energy EEDF-shape spread means the
earlier Maxwellian overlap cannot support a robust pass. Threshold alignment
is secondary. The next plan item is therefore narrowed to cross-section model
discrepancy and cascade/quenching closure; no global chemistry model is added.

### 2026-09-29: make input closure part of external-validation eligibility

A held-out label does not prevent circular validation when an unmeasured EEDF,
source density, metastable density, or discrepancy term is adjusted on the
same observations that are scored. Validation evidence now declares
`model_input_closure` and `evaluation_data_use`; an external quantitative claim
requires `closed` and `held_out_only`. This extends the existing evidence gate
without moving dataset-specific physics into a central framework.

Repeated resumable downloads of the Schuecke public archive timed out or were
reset. Rather than weakening the NO mechanism or waiting indefinitely, the
plan selected the Arellano Ar-CCP 763.5/750.4 nm ratio as a second candidate.
It is closer to the current OESCR state model, but remains conditional because
the packaged excitation curves are effective seeds and the high-pressure
series needs independent EEDF/metastable inputs. The 2-10 Pa subset is first an
atomic-data validation target, not a plasma-parameter retrieval benchmark.

### 2026-09-29: separate Ar atomic structure from collisional closure

The two example cases previously duplicated only the observed 750.4 and
763.5 nm transitions. That made each observed line act as though it carried
the full upper-level decay rate. The selected Ar levels and all their NIST
radiative branches now live in one species pack; case-specific excitation and
quenching reactions remain outside it. This is a data-responsibility cleanup,
not a new model layer or a global chemistry expansion.

Chilton et al. table-IV direct-excitation values are retained as immutable SI
anchors rather than stretched into a full curve. The packaged effective seeds
differ by factors of 3.66/8.83/0.84 for 2p1 and 7.70/16.21/1.69 for 2p6 at
20/40/100 eV. Because the mismatch is energy dependent and the Maxwellian rate
is near-threshold sensitive, rescaling the seeds or fitting them to the
Arellano ratios would not be a defensible fix. The plan therefore advances
only the radiative-closure item; cross-section qualification remains the next
blocking item.

### 2026-09-29: prepare external data without widening OESCR into global chemistry

The Schuecke et al. N2/O2 ICP dataset was selected because it combines absolute
OES photon rates with independent NO, gas-temperature, electron-density, and
electron-temperature measurements. The public archive was unreachable during
this increment, so the 10 Pa series was reproducibly extracted from vector PDF
figures with raw coordinates, source hash, conversions, and a separate
digitization tolerance. Its observation basis required the new explicit
`volumetric_photon_rate` evidence value.

The paper also shows that N2(A)-driven NO(A) excitation is important while
N2(A) was not independently measured. Adding a self-consistent N2/O2 chemistry
model solely to make this comparison pass would change the project scope and
couple validation to a new unvalidated subsystem. The candidate therefore has
no `validation.yaml`. It remains qualitative unless narrow-band data and every
required source density become independently available.

### 2026-09-29: reject unversioned or incompatible benchmark comparisons

Historical analysis summaries were produced under evolving classification and
report logic, so comparing their aggregate values with a new summary could
mix different metric semantics. Analysis output now separates an immutable
comparison contract from a candidate-specific run fingerprint. Between-run
evaluation requires identical comparison contracts; legacy summaries must be
regenerated. The default historical run names were removed rather than kept as
an unsafe compatibility path. The same evaluator is fixed by hash and version
in `validation.yaml`.

### 2026-09-29: move line-set observability ahead of external comparison

The Fuller Cl2/Ar paper provides operating-point densities and electron
temperature, but not a machine-readable raw spectrum with the response and
uncertainty information needed for a defensible held-out tolerance. The NF3/Ar
source likewise does not provide a redistributable calibrated spectrum in the
package. Rather than inventing uncertainty bounds, item 5 advanced the next
independent task: a data-only Jacobian audit of the packaged line sets. This
exposed parameters whose apparent constraint came only from priors and led to
their removal. The later v1 dataset-selection gate retained both candidates as
research evidence but found neither eligible for a quantitative accuracy
claim.

### 2026-09-29: separate evidence eligibility from physical comparison

The literature-anchored NF3/Ar and Cl2/Ar spectra are generated from empirical
emitters and spatialized into five chords, so passing their recovery gate
cannot establish experimental accuracy. A small validation-evidence schema and
audit now verify provenance, file hashes, hold-out status, measurement basis,
and calibration without creating another model framework. Physical pass/fail
calculation remains in a dataset-specific evaluator. This advances item 5's
protocol work while leaving the scientific result honestly incomplete until an
independent dataset is added.

### 2026-09-29: prefer the public EEDF envelope without removing legacy cases

The EEDF registry already owned execution and plugin-local validation, while
`plasma_mode` duplicated model selection in a central branch. New models now
use `eedf.kind` plus one `zones` mapping per geometry shell. Existing
`plasma_mode` inputs remain compatibility syntax and resolve to the same
registry; specifying both is rejected as ambiguous. The selected plugin kind is
recorded in forward provenance. This avoids a mass migration of validated
examples while ensuring future EEDF additions do not edit the central schema
enum or forward solver.

### 2026-09-29: extend responsibility cleanup to inverse validation

The item-3 quality gate found two remaining D-complexity blocks: benchmark
rendering/orchestration and the public inverse semantic validator. Limiting the
item-4 acceptance criterion to forward/inverse calculation modules would leave
both responsibility concentrations outside the gate. Item 4 therefore keeps
the public `validate_inverse_config` entry point but delegates its checks to
focused helpers, and applies the D/E criterion to the whole `oescr` package.
This is a responsibility-boundary change only; accepted YAML and error
semantics must remain compatible.

### 2026-09-29: make convergence qualification opt-in

Energy- and wavelength-grid convergence require two additional complete
forward evaluations. Running them inside every inverse objective call would
triple optimization cost without changing the objective definition. Quality
thresholds therefore remain enabled by default, while convergence is an
explicit case-qualification option. Its results use the same warning/error
event contract and are exported by the CLI. This changes execution policy, not
the planned convergence metrics or acceptance criteria.

### 2026-09-29: share linear transfer assembly across reaction families

Electron-impact, first-order, two-body, and three-body processes differ in how
their effective frequency is calculated, but have the same linear
source-to-target matrix form. Separate matrix assemblers would duplicate sign,
index, and budget logic. The implementation therefore compiles family-specific
units and collider order, evaluates each frequency independently, and sends all
families through one linear_transfer_contribution function. This changes the
original implementation detail, not the supported physics scope or acceptance
criteria. Reaction, radiative, and wall contributions now use the same ledger,
so their diagnostics and state budgets cannot drift from the solved matrix.

### 2026-09-29: preserve empirical literature-anchor benchmarks

The existing NF3/Ar and Cl2/Ar benchmark spectra use effective emitters and are
measurement-like self-consistency fixtures. Relabeling those amplitudes as a
physical photon-rate model would change their scientific meaning. They remain
available under explicit emission_mode: empirical. A separate
physical_band_analytic benchmark now verifies photon-rate, radiant-power,
line-of-sight, calibration-unit, and detector-bin conservation. This decision
changed the benchmark migration task without changing the project scope.

### 2026-09-29: isolate theoretical Ar references from general-purpose seeds

The full Chilton excitation functions could not be recovered reproducibly from
the source, and three table anchors do not determine the threshold-dominated
rate integral. Stretching those points into a curve or scaling a seed to the
held-out line ratio would create an undocumented model. Instead, the official
LXCat BSR-500 2p1/2p6 curves are consumed only by the Arellano evaluator as
user-supplied theoretical references, with stable production process IDs and
numeric digests. The later NGFSRDW comparison follows the same boundary and
does not promote either theoretical family into the general example data.
The general examples and generated benchmarks are not silently changed.

The new corona-limit assessment reuses the existing EEDF and rate kernels and
adds no global chemistry or new core abstraction. Agreement over an EEDF-family
and threshold sweep is recorded as sensitivity evidence only. The two-model
spread is now quantified; the remaining work is to bound omitted
cascade/quenching physics and obtain evidence that can weight model
uncertainty before declaring a pass/fail protocol.
