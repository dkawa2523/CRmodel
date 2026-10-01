import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oescr.forward.model import OESCRModel
from oescr.inverse.optimize import InverseSolver
from oescr.io.project import load_project
from oescr.io.yaml_loader import load_yaml

EXAMPLES = Path('examples')
BENCH = EXAMPLES / 'benchmarks'


def test_yaml_include_for_case_init():
    case = load_yaml(EXAMPLES / 'case_init_cf4_o2_ar.yaml')
    assert len(case['species_packs']) == 2
    assert case['bands']
    assert case['plasma_state']['te_shells_eV'][0] == 2.1


def test_root_import_does_not_eagerly_load_optimizer():
    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import sys, oescr; print('scipy.optimize' in sys.modules)",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
    )
    assert output.strip() == "False"


def test_parameter_groups_expand_for_inverse():
    solver = InverseSolver.from_yaml(EXAMPLES / 'case_init_cf4_o2_ar.yaml', EXAMPLES / 'inverse_cf4_o2_ar.yaml')
    assert len(solver.params.params) == 6
    assert solver.params.params[0].name.startswith('ne')


def test_project_manifest_loads():
    project = load_project(BENCH / 'nf3_ar_ccp_clean_2023' / 'project.yaml')
    assert project.case_yaml.name == 'case_init.yaml'
    assert project.inverse_yaml is not None


def test_project_case_runs():
    project = load_project(BENCH / 'nf3_ar_ccp_clean_2023' / 'project.yaml')
    model = OESCRModel.from_yaml(project.case_yaml)
    result = model.predict()
    assert 'nf3_benchmark_uvvis' in result.spectra


def test_runtime_parameter_override_reuses_compiled_structure():
    model = OESCRModel.from_yaml(EXAMPLES / 'case_init_cf4_o2_ar.yaml')
    runtime_cfg = deepcopy(model.cfg)
    runtime_cfg['plasma_state']['te_shells_eV'][0] *= 1.1

    _, plan = model._execution_plan(runtime_cfg)

    assert plan is model.compiled


def test_model_uses_compiled_case_without_legacy_object_aliases():
    model = OESCRModel.from_yaml(EXAMPLES / 'case_init_cf4_o2_ar.yaml')

    for name in ('state_registry', 'energy_eV', 'cs_library', 'rate_calc', 'atomic_solver', 'instrument_cfgs'):
        assert not hasattr(model, name)
    assert model.instrument_configs_for()


def test_structural_reaction_override_is_recompiled_and_changes_prediction():
    model = OESCRModel.from_yaml(EXAMPLES / 'case_init_cf4_o2_ar.yaml')
    baseline = model.predict()
    changed_cfg = deepcopy(model.cfg)
    changed_cfg['reactions'][0].pop('cross_section_file')
    changed_cfg['reactions'][0]['coefficient_m3_s'] = 0.0

    _, plan = model._execution_plan(changed_cfg)
    changed = model.predict(changed_cfg)

    assert plan is not model.compiled
    assert not np.array_equal(changed.zone_emissivity, baseline.zone_emissivity)
    assert '_fine_wavelength_nm' not in model.cfg
    assert '_instrument_cfgs' not in model.cfg


def test_mutating_public_model_config_cannot_bypass_recompilation():
    model = OESCRModel.from_yaml(EXAMPLES / 'case_init_cf4_o2_ar.yaml')
    baseline = model.predict()
    model.cfg['reactions'][0].pop('cross_section_file')
    model.cfg['reactions'][0]['coefficient_m3_s'] = 0.0

    changed = model.predict()

    assert not np.array_equal(changed.zone_emissivity, baseline.zone_emissivity)


def test_forward_result_exposes_component_and_solver_diagnostics():
    model = OESCRModel.from_yaml(EXAMPLES / 'case_init_cf4_o2_ar.yaml')
    result = model.predict()

    assert np.allclose(
        result.zone_emissivity,
        result.zone_atomic_emissivity + result.zone_band_emissivity,
    )
    for zone_index, components in enumerate(result.zone_band_components):
        component_sum = np.sum(list(components.values()), axis=0)
        assert np.allclose(result.zone_band_emissivity[zone_index], component_sum)

    for diagnostics in result.zone_diagnostics:
        assert np.isclose(diagnostics.eedf.normalization, 1.0)
        assert diagnostics.eedf.mean_energy_eV > 0.0
        assert diagnostics.cr.matrix_rank > 0
        assert diagnostics.cr.relative_residual >= 0.0
        cross_sections = [
            reaction['cross_section']
            for reaction in diagnostics.reactions
            if 'cross_section' in reaction
        ]
        assert cross_sections
        assert all(len(item['sha256']) == 64 for item in cross_sections)
        assert all(0.0 <= item['covered_probability'] <= 1.0 + 1.0e-12 for item in cross_sections)

    assert result.emission_basis.startswith('mixed')
    assert result.emission_component_bases['atomic_lines'].startswith('spectral_radiant_power')
