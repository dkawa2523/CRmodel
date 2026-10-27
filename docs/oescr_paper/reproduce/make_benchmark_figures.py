from __future__ import annotations

import csv
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import scipy
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from oescr.forward.model import OESCRModel
from oescr.io.yaml_loader import load_yaml
from oescr.inverse.optimize import InverseSolver

RUN = ROOT / '.local_outputs/paper_benchmarks'
FIG = ROOT / 'docs/oescr_paper/figures'
DATA = ROOT / 'docs/oescr_paper/evidence'
FIG.mkdir(parents=True, exist_ok=True)
DATA.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10.3, 'axes.labelsize': 10.3,
    'axes.titlesize': 10.8, 'legend.fontsize': 10.3, 'figure.dpi': 140, 'savefig.dpi': 240,
    'axes.spines.top': False, 'axes.spines.right': False, 'pdf.fonttype': 42,
    'axes.prop_cycle': plt.cycler(color=['#246498','#b76527','#505050'])})
BLUE, ORANGE, DARK, GRAY = '#246498', '#b76527', '#252525', '#929292'

def yload(path):
    return yaml.safe_load(path.read_text(encoding='utf-8'))

def save(fig, name):
    from matplotlib.text import Text
    for label in fig.findobj(Text):
        if label.get_fontsize() < 10.3:
            label.set_fontsize(10.3)
    fig.savefig(FIG / f'{name}.png', bbox_inches=None)
    fig.savefig(FIG / f'{name}.pdf', bbox_inches=None)
    plt.close(fig)

def csvwrite(name, rows):
    rows = list(rows)
    with (DATA/name).open('w', newline='', encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)

def spectrum(path):
    return np.genfromtxt(path, delimiter=',', names=True, comments='#')

def clean_ax(ax):
    ax.grid(axis='y', color='#dddddd', lw=.5)
    ax.set_axisbelow(True)

def analytic():
    base=ROOT/'examples/benchmarks/physical_band_analytic'
    cfg=load_yaml(base/'combined_case.yaml')
    out=OESCRModel(cfg).predict()
    expected=yload(base/'combined_benchmark.yaml')['expected']
    ob=out.spectra['combined_radiance']['chord_0']
    measured = {
        'atomic_line_emissivity_W_m3_sr': np.trapezoid(out.zone_atomic_emissivity[0],out.fine_wavelength_nm),
        'band_emissivity_W_m3_sr':np.trapezoid(out.zone_band_emissivity[0],out.fine_wavelength_nm),
        'combined_emissivity_W_m3_sr':np.trapezoid(out.zone_emissivity[0],out.fine_wavelength_nm),
        'central_chord_combined_radiance_W_m2_sr':np.trapezoid(ob['intensity'],ob['wavelength_nm'])}
    rows=[{'quantity':k,'analytic':float(expected[k]),'computed':v,'relative_error':abs(v/float(expected[k])-1)} for k,v in measured.items()]
    csvwrite('analytic_conservation.csv',rows)
    csvwrite('analytic_spectrum.csv',({'wavelength_nm':w,'spectral_radiance_W_m2_sr_nm':v} for w,v in zip(ob['wavelength_nm'],ob['intensity'])))
    fig,axs=plt.subplots(1,2,figsize=(7.0,3.1),layout='constrained')
    wl=np.asarray(ob['wavelength_nm']);v=np.asarray(ob['intensity'])
    axs[0].plot(wl,v,color=BLUE,lw=1.4)
    axs[0].set(xlabel='Wavelength (nm)',ylabel=r'$I_\lambda$ (W m$^{-2}$ sr$^{-1}$ nm$^{-1}$)',title='(a) Atomic line + photon band')
    axs[0].text(503,0.35*max(v),'500 nm band',fontsize=8)
    axs[0].text(595,0.82*max(v),'600 nm\natomic line',ha='right',fontsize=8)
    xs=np.arange(4)
    axs[1].bar(xs,100*np.array([r['relative_error'] for r in rows]),color=BLUE,width=.6)
    axs[1].axhline(.02,color=DARK,ls='--',lw=.9,label='Tolerance: 0.02%')
    axs[1].set_xticks(xs,['Atomic','Band','Total','Radiance'])
    axs[1].set(ylabel='Absolute relative error (%)',title='(b) Integral conservation',ylim=(0,.022))
    axs[1].legend(loc='upper left',bbox_to_anchor=(0.0,.88),frameon=False)
    for i,r in enumerate(rows): axs[1].text(i,.0006+100*r['relative_error'],f"{100*r['relative_error']:.4f}%",ha='center',fontsize=7)
    for a in axs: clean_ax(a)
    save(fig,'benchmark_analytic')
    return rows

def common():
    summ=yload(RUN/'common_state/summary.yaml')['cases']
    (DATA/'common_state_summary.yaml').write_text(yaml.safe_dump({'cases':summ},sort_keys=False),encoding='utf-8')
    rows=[]
    fig,axs=plt.subplots(3,2,figsize=(7.0,8.2),layout='constrained')
    fig.get_layout_engine().set(rect=(0,.045,1,.955))
    for ir,(info,label) in enumerate(zip(summ,[r'Ar/O$_2$',r'Ar/Cl$_2$'])):
        key=info['case'];dd=RUN/'common_state'/key
        ident=yload(dd/'audit/identifiability.yaml')
        fit=yload(dd/'result.yaml')
        t=info['parameters']['truth'];initial=info['parameters']['initial'];est=info['parameters']['oescr']
        for name in t:
            rows.append({'case':key,'parameter':name,'truth':t[name],'initial':initial[name],'estimated':est[name],
                'relative_error':abs(est[name]/t[name]-1),'condition_number':ident['condition_number'],'rank':ident['rank_estimate'],
                'runner_status':info['status']})
        ax=axs[ir,0]
        xx=np.arange(2)
        ax.scatter(xx-.1,[initial[k]/t[k] for k in t],marker='x',color=ORANGE,s=36,label='Initial',zorder=3)
        ax.scatter(xx+.1,[est[k]/t[k] for k in t],marker='o',facecolor=BLUE,edgecolor=BLUE,s=24,label='Estimated',zorder=3)
        ax.axhline(1,color=DARK,lw=.9,ls='--',label='Truth')
        ax.set_xticks(xx,[r'$T_e$',r'$n_e$'])
        ax.set(ylabel='Parameter / truth',ylim=(.65,1.65),title=f'({chr(97+ir*2)}) {label}: recovery')
        ax.text(.04,.04,f"Fit relative L2: {100*info['spectral_metrics']['oescr']['fit_nrmse_vs_measurement']:.2f}%",transform=ax.transAxes,fontsize=9)
        if ir==0: ax.legend(frameon=False,loc='upper left')
        for j,k in enumerate(t): ax.annotate(f'{100*abs(est[k]/t[k]-1):.2f}%',(j+.1,est[k]/t[k]),xytext=((5 if j==0 else -40),(-15 if ir==1 and j==0 else 6)),textcoords='offset points',fontsize=9)
        clean_ax(ax)
        ax=axs[2,ir]
        win = 'o777' if ir==0 else 'cl755'
        record=next(r for r in fit['spectral_fits'] if r['instrument_id']==win)
        ar=spectrum(dd/record['file']); norm=np.max(ar['measured'])
        ax.errorbar(ar['wavelength_nm'],ar['measured']/norm,yerr=ar['sigma']/norm,fmt='o',ms=2.5,color=DARK,lw=.6,label='Synthetic data')
        ax.plot(ar['wavelength_nm'],ar['predicted']/norm,color=BLUE,lw=1.2,label='Estimated')
        truth_model=OESCRModel.from_yaml(ROOT/f'examples/benchmarks/common_state_{key}/case_truth.yaml')
        truth=truth_model.predict_spectra()[win]['chord_0']
        ax.plot(truth['wavelength_nm'],truth['intensity']/norm,color=GRAY,ls='--',lw=1,label='Truth')
        ax.set(xlabel='Wavelength (nm)',ylabel='Intensity / data peak',title=f'({chr(101+ir)}) '+('O I 777.4 nm (fit)' if ir==0 else 'Cl I 754.7 nm (holdout)'))
        csvwrite(f'{key}_{win}_spectrum.csv',({n:float(row[n]) for n in ar.dtype.names} for row in ar))
        clean_ax(ax)
        ax=axs[ir,1]
        pro=yload(dd/'audit/parameter_profiles.yaml')['profiles']['electron_temperature_eV']
        points=pro['points']
        ax.plot([p['value'] for p in points],[p['delta_measurement_sum_squares'] for p in points],color=BLUE,lw=1.2,marker='.',ms=4)
        ax.axvline(t['electron_temperature_eV'],color=DARK,ls='--',lw=.9,label='Truth')
        ax.set(xlabel=r'Conditional $T_e$ (eV)',ylabel=r'$\Delta\sum r_i^2$',title=f'({chr(98+ir*2)}) Conditional profile',yscale='symlog',ylim=(0,30000))
        clean_ax(ax)
        csvwrite(f'{key}_temperature_profile.csv',({'Te_eV':p['value'],'delta_measurement_sum_squares':p['delta_measurement_sum_squares'],'conditional_ne_m3':p['conditional_parameters']['electron_density_m3']} for p in points))
    handles,labels=axs[2,0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.5,.005),ncol=3,frameon=False)
    save(fig,'benchmark_common_state')
    csvwrite('common_state_parameter_recovery.csv',rows)
    return rows

def six():
    dd=RUN/'ar_six_kernel'
    info=yload(dd/'fit_summary.yaml')
    records=yload(dd/'kernel_sensitivity.yaml')['records']
    csvwrite('ar_kernel_sensitivity.csv',records)
    (DATA/'ar_six_kernel_summary.yaml').write_text(yaml.safe_dump(info,sort_keys=False),encoding='utf-8')
    fig,axs=plt.subplots(2,2,figsize=(7.0,5.9),layout='constrained')
    for i,chan in enumerate(['vis_650_850','nir_840_1050']):
        ar=spectrum(dd/f'audit_spectra/{chan}_rep_0.csv');norm=np.max(ar['measured']);ax=axs[0,i]
        ax.plot(ar['wavelength_nm'],ar['measured']/norm,color=DARK,lw=.7,label='Generated')
        ax.plot(ar['wavelength_nm'],ar['predicted']/norm,color=BLUE,lw=1.0,ls='--',label='Estimated')
        ax.plot(ar['wavelength_nm'],ar['initial_prediction']/norm,color=ORANGE,lw=.7,alpha=.8,label='Initial')
        fits=ar['fit_mask']>0;scores=ar['score_mask']>0
        ax.scatter(ar['wavelength_nm'][fits],np.full(sum(fits),-.06),marker='|',s=8,color=BLUE,label='Fit pixels')
        ax.scatter(ar['wavelength_nm'][scores],np.full(sum(scores),-.10),marker='|',s=8,color=ORANGE,label='Score pixels')
        ax.set(xlabel='Wavelength (nm)',ylabel='Intensity / data peak',title=f'({chr(97+i)}) '+('VIS channel' if i==0 else 'NIR channel'),ylim=(-.14,1.08))
        if i==0: ax.legend(frameon=False,ncol=1,loc='upper left')
        clean_ax(ax)
        csvwrite(f'ar_six_{chan}_spectrum.csv',({n:row[n] for n in ar.dtype.names} for row in ar))
    ax=axs[1,0];p=spectrum(dd/'temperature_profile.csv')
    ax.plot(p['electron_temperature_eV'],p['delta_measurement_sum_squares'],color=BLUE,marker='.',lw=1.2)
    ax.axvline(info['truth_te_eV'],color=DARK,ls='--',lw=.9,label='Truth: 4 eV')
    ax.set(xlabel=r'Conditional $T_e$ (eV)',ylabel=r'$\Delta\sum r_i^2$',title='(c) Measurement-only profile',yscale='symlog',ylim=(0,3e5))
    ax.legend(frameon=False);clean_ax(ax)
    ax=axs[1,1];x=np.arange(6);labels=[r['upper_state'].replace('Ar_','') for r in records]
    ax.scatter(x,[r['d_log_rate_d_log_te'] for r in records],marker='o',s=24,color=BLUE)
    ax.set_xticks(x,labels);ax.set(ylabel=r'$\partial\log k/\partial\log T_e$',title='(d) Kernel sensitivities at 4 eV',ylim=(0,4.5))
    for i,r in enumerate(records): ax.text(i,r['d_log_rate_d_log_te']+.12,f"{r['d_log_rate_d_log_te']:.2f}",ha='center',fontsize=7)
    clean_ax(ax);save(fig,'benchmark_ar_six_kernel')
    return info

def two_band():
    rows=[]
    for mode,truth in [('ratio',2e18),('actinometry',2e18),('absolute',3e16)]:
        r=yload(RUN/f'two_band_{mode}/result.yaml');ident=yload(RUN/f'two_band_{mode}/audit/identifiability.yaml')
        name,val=next(iter(r['parameters'].items()))
        rows.append({'mode':mode,'parameter':name,'truth':truth,'estimated':val,'relative_error':abs(val/truth-1),'cost':r['cost'],'optimizer_success':r['success'],'measurement_rank':ident['rank_estimate'],'measurement_observations':ident['n_observations']})
    csvwrite('two_band_recovery.csv',rows)
    return rows

def ancillary():
    rows=[]
    for case in ['nf3','cl2']:
        dd=RUN/case
        if not (dd/'result.yaml').exists():continue
        results=yload(dd/'result.yaml')
        truth=load_yaml(ROOT/f'examples/benchmarks/{"nf3_ar_ccp_clean_2023" if case=="nf3" else "cl2_ar_icp_fuller2001"}/case_truth.yaml')
        for name,val in results['parameters'].items():
            match=re.fullmatch(r'(Cl2e|N2e|Cl|te|F)_?(\d+)',name)
            if match is None:raise ValueError(f'Unexpected shell parameter: {name}')
            group,idx=match.group(1),int(match.group(2))
            path={'te':('te_shells_eV',None),'F':('radicals','F'),'N2e':('radicals','N2_emit'),'Cl':('radicals','Cl'),'Cl2e':('radicals','Cl2_emit')}[group]
            ref=truth['plasma_state'][path[0]][idx] if path[1] is None else truth['plasma_state'][path[0]][path[1]][idx]
            rows.append({'case':case,'parameter':name,'group':group,'shell_index':idx,'truth':ref,'estimated':val,'relative_error':abs(val/ref-1),'optimizer_success':results['success'],'cost':results['cost']})
    if not rows:return []
    csvwrite('multichord_parameter_recovery.csv',rows)
    fig,axs=plt.subplots(2,2,figsize=(7.0,5.8),layout='constrained')
    for ir,case in enumerate(['nf3','cl2']):
        dd=RUN/case
        if not (dd/'result.yaml').exists(): continue
        r=yload(dd/'result.yaml');record=r['spectral_fits'][0];ar=spectrum(dd/record['file']);norm=np.max(ar['measured'])
        ax=axs[ir,0]
        ax.plot(ar['wavelength_nm'],ar['measured']/norm,color=DARK,lw=.7,label='Synthetic data')
        ax.plot(ar['wavelength_nm'],ar['predicted']/norm,color=BLUE,lw=.8,ls='--',label='Estimated')
        ax.set(xlabel='Wavelength (nm)',ylabel='Intensity / data peak',title=f'({chr(97+ir*2)}) '+('NF3/Ar' if case=='nf3' else 'Cl2/Ar')+': central chord')
        ax.legend(frameon=False,fontsize=7);clean_ax(ax)
        ax=axs[ir,1];items=[v for v in rows if v['case']==case]
        groups=list(dict.fromkeys(v['group'] for v in items))
        for ig,g in enumerate(groups):
            rr=[v for v in items if v['group']==g]
            ax.plot([v['shell_index']+1 for v in rr],[v['estimated']/v['truth'] for v in rr],marker=['o','s','^'][ig],lw=1,label=g)
        ax.axhline(1,color=DARK,ls='--',lw=.8)
        ax.set(xlabel='Radial shell (center to wall)',ylabel='Parameter / truth',xticks=[1,2,3],title=f'({chr(98+ir*2)}) Regularized recovery')
        ax.legend(frameon=False,ncol=3,loc='upper left',bbox_to_anchor=(0,.96));clean_ax(ax)
        csvwrite(f'{case}_central_spectrum.csv',({n:float(row[n]) for n in ar.dtype.names} for row in ar))
    save(fig,'benchmark_multichord')
    return rows

def main():
    metrics={'analytic':analytic(),'two_band':two_band(),'common_state':common(),'ar_six_kernel':six(),'multichord':ancillary()}
    (DATA/'benchmark_metrics.json').write_text(json.dumps(metrics,indent=2,default=float),encoding='utf-8')
    spectrum_rows=[]
    for key in ['common_state/ar_o2','common_state/ar_cl2','ar_six_kernel','two_band_ratio','two_band_actinometry','two_band_absolute','nf3','cl2']:
        source=RUN/key
        if not (source/'result.yaml').exists():continue
        result=yload(source/'result.yaml')
        squared_error=squared_reference=fit_error=fit_reference=0.0
        full_count=fit_count=0
        for record in result['spectral_fits']:
            array=spectrum(source/record['file']);mask=array['used_for_fit']>0
            squared_error+=float(np.sum((array['predicted']-array['measured'])**2))
            squared_reference+=float(np.sum(array['measured']**2))
            fit_error+=float(np.sum((array['predicted'][mask]-array['measured'][mask])**2))
            fit_reference+=float(np.sum(array['measured'][mask]**2))
            full_count+=len(array);fit_count+=sum(mask)
        spectrum_rows.append({'case':key,'spectrum_observations':len(result['spectral_fits']),
            'all_pixel_count':full_count,'selected_spectral_pixel_count':int(fit_count),
            'all_spectra_relative_l2':np.sqrt(squared_error/max(squared_reference,1e-300)),
            'selected_spectral_relative_l2':np.sqrt(fit_error/max(fit_reference,1e-300)) if fit_count else None,
            'interpretation':'unweighted_L2_of_exported_nuisance_adjusted_prediction;_not_optimizer_cost'})
    csvwrite('exported_spectral_metrics.csv',spectrum_rows)
    files=[]
    for top in [ROOT/'oescr',ROOT/'scripts',ROOT/'tests',ROOT/'examples/benchmarks',ROOT/'examples/use_cases/two_band',ROOT/'examples/data']:
        for f in sorted(top.rglob('*')):
            if f.is_file() and f.suffix in ['.py','.yaml','.csv','.json']:
                files.append({'file':str(f.relative_to(ROOT)).replace('\\','/'),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
    files.append({'file':'pyproject.toml','sha256':hashlib.sha256((ROOT/'pyproject.toml').read_bytes()).hexdigest()})
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    status=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)
    run_commands=[
        {'command':'python scripts/run_common_state_benchmarks.py --out .local_outputs/paper_benchmarks/common_state','exit_status':1,'reason':'ar_cl2 recovery gates failed, ar_o2 passed'},
        {'command':'python scripts/run_argon_six_kernel_candidate.py --out .local_outputs/paper_benchmarks/ar_six_kernel','exit_status':0},
        {'command':'python scripts/run_inverse.py examples/use_cases/two_band/case_ratio_init.yaml examples/use_cases/two_band/inverse_ratio.yaml --out .local_outputs/paper_benchmarks/two_band_ratio --audit','exit_status':0},
        {'command':'python scripts/run_inverse.py examples/use_cases/two_band/case_ratio_init.yaml examples/use_cases/two_band/inverse_actinometry.yaml --out .local_outputs/paper_benchmarks/two_band_actinometry --audit','exit_status':0},
        {'command':'python scripts/run_inverse.py examples/use_cases/two_band/case_absolute_init.yaml examples/use_cases/two_band/inverse_absolute.yaml --out .local_outputs/paper_benchmarks/two_band_absolute --audit','exit_status':0},
        {'command':'python -m pytest -q tests/test_cr_analytic.py tests/test_spectral_sampling.py tests/test_model_contracts.py tests/test_argon_six_kernel_candidate.py tests/test_common_state_benchmarks.py tests/test_use_case_examples.py','exit_status':0,'summary':'106 passed; inspect the retained test log for elapsed time'},
    ]
    for case,dirname in [('nf3','nf3_ar_ccp_clean_2023'),('cl2','cl2_ar_icp_fuller2001')]:
        if (RUN/case/'result.yaml').exists():
            fit=yload(RUN/case/'result.yaml')
            run_commands.append({'command':f'python scripts/run_project.py examples/benchmarks/{dirname}/project.yaml --out .local_outputs/paper_benchmarks/{case} --audit','exit_status':0 if fit['success'] else 1,'interpretation':'regularized same-model synthetic recovery'})
    tree_hasher=hashlib.sha256()
    for f in files:tree_hasher.update((f['file']+'\0'+f['sha256']+'\n').encode())
    manifest={'date_local':'2026-10-27','timezone':'Asia/Tokyo','git_head':head,'git_dirty':bool(status.strip()),'git_status_at_export':status,'source_input_tree_sha256':tree_hasher.hexdigest(),'python':platform.python_version(),'platform':platform.platform(),'numpy':np.__version__,'scipy':scipy.__version__,'matplotlib':matplotlib.__version__,'claim':'synthetic_same_model_recovery_or_analytic_conservation_only','working_tree':'uncommitted current source used; hashes define exact inputs','performance_note':'Wall-clock timing was not recorded as a controlled performance benchmark. Concurrent jobs were used.','runs':run_commands,'files':files}
    (DATA/'run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    if (RUN/'run_execution.json').exists():
        shutil.copyfile(RUN/'run_execution.json',DATA/'run_execution.json')
        manifest['runs']=json.loads((RUN/'run_execution.json').read_text(encoding='utf-8'))
        manifest['focused_test_summary']=(RUN/'focused_tests.log').read_text(encoding='utf-8').strip().splitlines()[-1]
        (DATA/'run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    for key in ['common_state/ar_o2','common_state/ar_cl2','ar_six_kernel','two_band_ratio','two_band_actinometry','two_band_absolute','nf3','cl2']:
        source=RUN/key
        destination=DATA/'results'/key
        for filename in ['result.yaml','case_opt.yaml','audit/identifiability.yaml','audit/parameter_profiles.yaml','audit/uncertainty.yaml']:
            if (source/filename).exists():
                (destination/filename).parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source/filename,destination/filename)
    for filename in ['common_state.log','ar_six_kernel.log','nf3.log','cl2.log','focused_tests.log']:
        if (RUN/filename).exists():
            (DATA/'logs').mkdir(exist_ok=True)
            shutil.copyfile(RUN/filename,DATA/'logs'/filename)
    print('Figures and reviewed CSV data written:',FIG)

if __name__=='__main__':main()
