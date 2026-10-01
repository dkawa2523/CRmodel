import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oescr.forward.model import OESCRModel
from oescr.inverse.optimize import InverseSolver

BENCH_ROOT = Path('examples/benchmarks')


def test_nf3_benchmark_forward_and_inverse_load():
    case = BENCH_ROOT / 'nf3_ar_ccp_clean_2023' / 'case_init.yaml'
    inv = BENCH_ROOT / 'nf3_ar_ccp_clean_2023' / 'inverse.yaml'
    model = OESCRModel.from_yaml(case)
    result = model.predict()
    assert 'nf3_benchmark_uvvis' in result.spectra
    assert len(result.spectra['nf3_benchmark_uvvis']) == 5
    solver = InverseSolver.from_yaml(case, inv)
    assert solver.measurements['nf3_benchmark_uvvis']


def test_cl2_benchmark_forward_and_inverse_load():
    case = BENCH_ROOT / 'cl2_ar_icp_fuller2001' / 'case_init.yaml'
    inv = BENCH_ROOT / 'cl2_ar_icp_fuller2001' / 'inverse.yaml'
    model = OESCRModel.from_yaml(case)
    result = model.predict()
    assert 'cl2_benchmark_scan' in result.spectra
    assert len(result.spectra['cl2_benchmark_scan']) == 5
    solver = InverseSolver.from_yaml(case, inv)
    assert solver.measurements['cl2_benchmark_scan']
