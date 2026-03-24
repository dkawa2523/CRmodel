import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oescr.forward.model import OESCRModel
from oescr.inverse.optimize import InverseSolver
from oescr.io.project import load_project
from oescr.io.yaml_loader import load_yaml


EXAMPLES = Path('examples')
BENCH = EXAMPLES / 'benchmarks'


def test_yaml_include_for_case_init():
    case = load_yaml(EXAMPLES / 'case_init_cf4_o2_ar.yaml')
    assert case['states']
    assert case['transitions']
    assert case['plasma_state']['te_shells_eV'][0] == 2.1


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
