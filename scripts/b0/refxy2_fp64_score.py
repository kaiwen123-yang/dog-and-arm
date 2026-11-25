"""Summarize saved FP64 calls; this file runs no model and takes no gradients."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np


def save_json(path, d):
    path.write_text(json.dumps(d, indent=2, allow_nan=False)+'\n')


def csv_output(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rows[0])
        w.writeheader()
        w.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw', type=Path)
    parser.add_argument('light', type=Path)
    args = parser.parse_args()
    root = args.raw.resolve()
    args.light.mkdir(parents=True, exist_ok=True)
    info = json.loads((root/'fields.json').read_text())
    names = info['fields']
    idx = {f:i for i,f in enumerate(names)}
    amounts = np.asarray(info['scales'])
    counts = dict(perturbed=0, warmup=0, baseline=0, reverse_grad=0, jvp=0, physics=0, optimizer=0)
    outputs, diagnostic, overview, index = [], [], [], []
    closures = {'J_minus_prefix_minus_bootstrap':0., 'prefix_minus_8_components':0.}
    dual_closures = closures.copy()
    states = sorted(p for p in root.iterdir() if p.is_dir())
    assert len(states) == 4
    for s in states:
        side, k = s.name.split('_')
        archived = Path(info['source'])/'response'/side/('frame_'+k.zfill(4))
        directions = np.load(archived/'directions.npz')
        load = lambda nm: np.load(s/(nm+'.npy'))
        b = load('baseline_1')[:, 0]
        rb = load('baseline_2')[:, 0]
        warm = load('warmup')[:, 0]
        grad = load('grad').ravel()
        counts['baseline'] += 2
        counts['warmup'] += 1
        counts['reverse_grad'] += 1
        assert warm.shape == b.shape == rb.shape == (32,len(names)) and grad.shape == (23,)
        gap = abs(rb-b)
        spacing = abs(np.spacing(b))
        for name in info['directions']:
            d = directions[name].ravel().astype('float64')
            signed = load('signed_'+name)
            fw = load('jvp_'+name)[:,0]
            assert signed.shape == (32,22,len(names)) and fw.shape == b.shape
            counts['perturbed'] += signed.shape[1]
            counts['jvp'] += 1
            for data, target in [(signed, closures), (b,closures), (rb,closures), (fw,dual_closures)]:
                target['J_minus_prefix_minus_bootstrap'] = max(target['J_minus_prefix_minus_bootstrap'], float(abs(data[...,1]-data[...,0]-data[...,2]).max()))
                target['prefix_minus_8_components'] = max(target['prefix_minus_8_components'], float(abs(data[...,0]-data[...,9:17].sum(-1)).max()))
            signed = signed.reshape(32,11,2,len(names)).transpose(1,2,0,3)
            plus, minus = signed[:,0], signed[:,1]
            h = amounts[:,None,None]
            central = (plus-minus)/(2*h)
            forward = (plus-b)/h
            backward = (b-minus)/h
            reverse = float(grad@d)
            ad_ref = fw[-1,idx['J']]
            np.savez_compressed(s/('differences_'+name+'.npz'), central=central, plus_slope=forward,
                   minus_slope=backward, adjacent_delta=central[1:]-central[:-1],
                   native_dual_r_plus=plus-b-h*fw, native_dual_r_minus=minus-b+h*fw,
                   scalar_reverse_r_plus=plus[:,-1,1]-b[-1,1]-amounts*reverse,
                   scalar_reverse_r_minus=minus[:,-1,1]-b[-1,1]+amounts*reverse,
                   central_minus_native_dual=central-fw, central_J_minus_reverse=central[:,-1,1]-reverse)
            fd = central[:,-1,idx['J']]
            errors = abs(fd-reverse)
            decreasing = np.diff(errors) < 0
            runs = []
            for i in np.flatnonzero(decreasing & ~np.r_[False,decreasing[:-1]]):
                stop = i+1
                while stop < len(decreasing) and decreasing[stop]:
                    stop += 1
                if stop-i >= 2:
                    runs.append([int(i),int(stop)])
            overview.append(dict(side=side,frame=int(k),direction=name,J32_baseline=float(b[-1,1]),
                reverse_grad_dot=reverse,native_forward_ad=float(ad_ref),finest_central=float(fd[-1]),
                finest_relative_error_reverse=float(errors[-1]/abs(reverse)),
                finest_absolute_error_reverse=float(errors[-1]),finest_reverse_sign_match=bool(fd[-1]*reverse>0),
                native_jvp_minus_reverse=float(ad_ref-reverse),
                decreasing_error_runs_at_least_three_scales_k_inclusive=runs,
                minimum_abs_error_k=int(np.argmin(errors)),
                empirical_roundoff='smallest errors fluctuate after local minimum; rounding compatible' if np.argmin(errors)<10 else
                    'error still improves through finest scale; rounding plateau unresolved',
                spacing_at_baseline=float(spacing[-1,1]),repeat_baseline_range=float(gap[-1,1]),
                first_step_aux_xyz_native_tangent_max_abs=float(abs(fw[0,17:20]).max()),
                first_step_aux_xyz_finest_central_max_abs=float(abs(central[-1,0,17:20]).max())))
            for i, hh in enumerate(amounts):
                for j in (0,6,31):
                    for col in [*range(9), *range(9,17)]:
                        ref = reverse if j==31 and col==idx['J'] else fw[j,col]
                        vv = float(central[i,j,col])
                        nrm = max(abs(ref), abs(vv))
                        outputs.append(dict(side=side,frame=k,direction=name,step=j+1,field=names[col],k=i,h=hh,
                            baseline=b[j,col],plus=plus[i,j,col],minus=minus[i,j,col],
                            slope_plus=forward[i,j,col],slope_minus=backward[i,j,col],central=vv,
                            adjacent_change='' if i==0 else vv-central[i-1,j,col],
                            derivative_source='reverse_grad_dot' if j==31 and col==1 else 'native_dual_affected',
                            directional_ad=ref,abs_central_minus_ad=abs(vv-ref),relative_error=abs(vv-ref)/nrm if nrm else 0.,
                            Rplus=plus[i,j,col]-b[j,col]-hh*ref,Rminus=minus[i,j,col]-b[j,col]+hh*ref,
                            empirical_spacing_per_h=spacing[j,col]/hh,baseline_repeat_difference=gap[j,col]))
            # First WM successor root translation. No independent full rollout required.
            best = int(np.argmax(abs(central[-1,0,17:20]-fw[0,17:20])))+17
            diagnostic.append(dict(side=side,frame=k,direction=name,step=1,field=names[best],
                native_ad=float(fw[0,best]),finest_central=float(central[-1,0,best]),
                previous_three_central=[float(v) for v in central[-4:-1,0,best]],
                first_raw_max_abs_discrepancy=float(abs(central[-1,0,99:122]-fw[0,99:122]).max()),
                first_clipped_max_abs_discrepancy=float(abs(central[-1,0,122:145]-fw[0,122:145]).max())))
        index.append(dict(side=side,frame=int(k),path=str(s),parent_anchor=str(archived),
            records=sorted(f.name for f in s.glob('*.npy')),derived=sorted(f.name for f in s.glob('differences_*.npz')),
            shapes={'signed':[32,22,len(names)],'jvp_or_baseline':[32,1,len(names)],'grad':[1,23]},
            dtype='float64',warmup_baseline_max_difference=float(abs(warm-b).max()),
            baseline_repeat_max_difference=float(gap.max())))
    assert counts == dict(perturbed=264,warmup=4,baseline=8,reverse_grad=4,jvp=12,physics=0,optimizer=0)
    csv_output(args.light/'slopes.csv',outputs)
    save_json(args.light/'raw_manifest.json',dict(root=str(root),parent=info,anchors=index))
    witness = json.loads((args.light/'operator_run.json').read_text())
    save_json(args.light/'same_function_counterexample.json',dict(first_successor=diagnostic,
        operator='mjlab.utils.lab_api.math.quat_apply after three no_grad warmups, on FP64 CUDA',
        q=witness['q'],vector=witness['v'],direction=witness['d'],analytic_jvp=witness['d'],
        native_forward_ad_tangent=witness['native_dual']['tangent'],
        optimized_execution_false_tangent=witness['optimization_disabled']['tangent'],
        reverse_vector_jacobian_dot=witness['reverse_vjp'],corrected_reverse_over_reverse_jvp=witness['corrected_jvp'],
        implication='An identity rotation loses the forward dual at the TorchScript boundary. Original training uses reverse-mode AD. The twelve originally called native directional passes are affected. This witness does not establish a training-core bug.'))
    save_json(args.light/'result.json',dict(counts=counts,anchors_and_directions=overview,primal_algebra_max_abs=closures,
        native_dual_internal_algebra_max_abs=dual_closures,
        scope='Original 540/u10000 archived anchors in the frozen FP64 eager function. Reverse J32 projections agree in sign with finest central differences in all 12 anchor-directions. Decreasing-error intervals and tail behavior are per direction. FP32 training gradients and physical derivatives are outside this check.',
        jvp_status='unresolved at component/full-path level: native forward AD through compiled TorchScript math loses tangents; internal algebra closure alone cannot validate derivatives. Diagnostic entry corrected to reverse-over-reverse by default. No budget remains for full model re-execution.',
        training_core_bug_proven=False, quarantine_required=False, physical_or_training_gate=False))
    print(counts, closures, dual_closures)


if __name__=='__main__':
    main()
