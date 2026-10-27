"""Reproduce the paper's numerical experiments without changing input fixtures.

Run from the repository root with an environment containing the project and
its ``dev`` dependencies. A nonzero common-state exit code is retained as an
experimental result: the Ar/Cl2 fixture fails its configured recovery gates.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / '.local_outputs' / 'paper_benchmarks'


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--skip-multichord', action='store_true', help='Skip the slower NF3 and Cl2 empirical workflows.')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    commands = [
        ('common_state', ['scripts/run_common_state_benchmarks.py', '--out', str(OUT/'common_state')]),
        ('ar_six_kernel', ['scripts/run_argon_six_kernel_candidate.py', '--out', str(OUT/'ar_six_kernel')]),
    ]
    for mode in ['ratio', 'actinometry', 'absolute']:
        initial = 'case_absolute_init.yaml' if mode == 'absolute' else 'case_ratio_init.yaml'
        commands.append((f'two_band_{mode}', ['scripts/run_inverse.py', f'examples/use_cases/two_band/{initial}',
            f'examples/use_cases/two_band/inverse_{mode}.yaml', '--out', str(OUT/f'two_band_{mode}'), '--audit']))
    if not args.skip_multichord:
        for key, directory in [('nf3', 'nf3_ar_ccp_clean_2023'), ('cl2', 'cl2_ar_icp_fuller2001')]:
            commands.append((key, ['scripts/run_project.py', f'examples/benchmarks/{directory}/project.yaml',
                '--out', str(OUT/key), '--audit']))
    commands.append(('focused_tests', ['-m', 'pytest', '-q', 'tests/test_cr_analytic.py',
        'tests/test_spectral_sampling.py', 'tests/test_model_contracts.py', 'tests/test_argon_six_kernel_candidate.py',
        'tests/test_common_state_benchmarks.py', 'tests/test_use_case_examples.py']))
    records=[]
    for key, argv in commands:
        full=[sys.executable, *argv]
        print(f'Running {key}', flush=True)
        started=datetime.now(timezone.utc).isoformat()
        t0=time.perf_counter()
        with (OUT/f'{key}.log').open('w', encoding='utf-8') as stream:
            result=subprocess.run(full, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=False)
        records.append({'name': key, 'argv': full, 'started_utc': started, 'elapsed_s': time.perf_counter()-t0,
            'exit_status': result.returncode, 'log': str((OUT/f'{key}.log').relative_to(ROOT))})
        (OUT/'run_execution.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
        print(f'  exit={result.returncode}; elapsed={records[-1]["elapsed_s"]:.2f} s', flush=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name('make_benchmark_figures.py'))], cwd=ROOT, check=True)
    failures=[r for r in records if r['exit_status'] and r['name'] != 'common_state']
    if failures:
        raise SystemExit('One or more commands failed; inspect the retained execution records.')


if __name__ == '__main__':
    main()
