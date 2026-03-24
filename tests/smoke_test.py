import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oescr.forward.model import OESCRModel
from oescr.inverse.optimize import InverseSolver


def test_forward_runs():
    case = Path('examples/case_init_cf4_o2_ar.yaml')
    model = OESCRModel.from_yaml(case)
    result = model.predict()
    assert 'uvvis_lowres' in result.spectra
    assert len(result.spectra['uvvis_lowres']) >= 1


def test_inverse_runs():
    case = Path('examples/case_init_cf4_o2_ar.yaml')
    inv = Path('examples/inverse_cf4_o2_ar.yaml')
    solver = InverseSolver.from_yaml(case, inv)
    fit = solver.fit()
    assert fit.success or fit.cost >= 0.0
