"""Index continuous-lane training from completed checkpoints, collector blocks and frozen scores."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np


def read(p):
    return json.loads(p.read_text())


def lines(p):
    return [json.loads(x) for x in p.read_text().splitlines()]


def block_counts(raw):
    files=sorted(raw.glob('lanes_*.npz'))
    group={}
    total=dict(intervals=0,prefix=0,policy_valid=0,policy_invalid=0,post_failure_substeps=0)
    for file in files:
        with np.load(file) as arr:
            valid=arr['valid']
            prefix=arr['prefix']
            total['intervals']+=valid.size
            total['prefix']+=int(prefix.sum())
            total['policy_valid']+=int(valid.sum())
            total['policy_invalid']+=int((~valid & ~prefix).sum())
            total['post_failure_substeps']+=int(np.where(~prefix & (arr['fail']>0),10-arr['fail'],0).sum())
            for side in (0,1):
                for phase in np.unique(arr['phase']):
                    mask=valid & (arr['side']==side) & (arr['phase']==phase)
                    if not mask.any(): continue
                    key=(int(side),int(phase))
                    d=group.setdefault(key,dict(valid=0,entire_interval_dual=0,starts=set(),terminal=0,peak_n=0.))
                    d['valid']+=int(mask.sum())
                    d['entire_interval_dual']+=int(((arr['finger_min']>.01).all(-1) & mask).sum())
                    d['terminal']+=int((mask & (arr['fail']>0)).sum())
                    d['starts'].update(arr['episode'][mask].tolist())
                    d['peak_n']=max(d['peak_n'],float(arr['peak_force'][mask].max()))
    from learning.b0.contact_warp import PHASES
    total['by_side_phase']=[dict(side=('pull','push')[side],phase=PHASES[phase],episodes=len(d.pop('starts')),**d)
                             for (side,phase),d in sorted(group.items())]
    total['recording_blocks']=len(files)
    return total


def main(a):
    root=Path('results/b0')
    raw=Path('results/raw_large/b0')
    warm='lanes_wm_v1'
    data='lanes_modes_v1'
    matched=read(root/'lanes_matched_v1/comparison.json')
    costs=[]
    cfgs=[]
    history=[]
    for name in a.runs:
        p=root/name
        cfg=read(p/'actual_config.json')
        cs=lines(p/'cohorts.jsonl')
        us=lines(p/'updates.jsonl')
        measured=block_counts(raw/name)
        assert measured['policy_valid']==sum(r['valid_transitions'] for r in cs)
        assert measured['intervals']==sum(r['simulated_lane_intervals'] for r in cs)
        assert not cfgs or cfgs[-1]==cfg['cfg']
        cfgs.append(cfg['cfg'])
        history.extend(r['update'] for r in us)
        cfg_path=p/'resume_boundary.json'
        costs.append(dict(run=name,parent=cfg['initialization']['resume'],resume_boundary=read(cfg_path) if cfg_path.exists() else None,
                actual_config=str(p/'actual_config.json'),recovery=str(p/'cohort_state.pt'),raw=str(raw/name),
                checkpoints=[f.name for f in sorted(p.glob('checkpoint_*.pt'))],first_new_update=us[0]['update'],
                last_update=us[-1]['update'],added_h32=len(us),added_wm=10*len(us),added_critic=20*len(us),
                imagined=sum(r['imagined_policy_steps'] for r in us),elapsed_s=read(p/'outcome.json')['elapsed_process_s'],
                starts=sum(sum(r['starts_per_motion']) for r in cs),rejected_prefixes=sum(r['prefix_invalid'] for r in cs),
                collection=measured))
    assert history==list(range(1,1+len(history)))
    cohort_rows=read(root/data/'cohorts.json')
    wmcfg=read(root/warm/'config.json')
    wm_scores=[]
    for p in sorted([*root.glob('lanes_val_*'),*root.glob('lanes_joint*')]):
        if not (p/'errors.csv').is_file(): continue
        with (p/'errors.csv').open() as f:
            for r in csv.DictReader(f):
                if r['h']=='32' and r['stratum']=='contact_mode' and r['label'] in ('two_finger','free') and r['predictor'] in ('wm','constant_velocity','hold') and r['metric']=='tcp_mm' and r['p95']:
                    wm_scores.append(dict(score=p.name,side=r['side'],mode=r['label'],predictor=r['predictor'],scored=int(r['scored']),
                                          independent_lanes=int(r['scored_lanes']),p95_mm=float(r['p95'])))
    formal=read(a.out/'nominal_summary.json')['records']
    assert all(r['segments_only']['cases']==10 for r in formal)
    if any(r['segments_only']['physical_passes']==10 for r in formal):
        raise ValueError('A nominal candidate qualified; index its subsequent gates before reporting')

    manifest=dict(method='SuperMimic-M1Piper-standard-v1',status='B0-04',seed=0,final_candidate=None,final_frozen=False,
           code_parent='ee41ee39170e5695f34cf62aa150328c000fb09c',implementation='54e8aa94833d2478619719cf8a1c83480d9141d3',
           previous='results/b0/standard_baseline_20261124/baseline_manifest.json',upstream=read(root/'standard_baseline_20261124/baseline_manifest.json')['upstream'],
           field_root=str(Path.cwd()),selected_recipe='config/b0/standard_lanes_v1.yaml',resolved=cfgs[0],
           inherited=read(root/'standard_baseline_20261124/baseline_manifest.json')['inheritance'],
           data=dict(supplemental=wmcfg['supplemental_train'],new_split={k:dict(lanes=64*len(rs),prefix_2ms_steps=64*100*len(rs),
                    physical_intervals=64*40*len(rs),valid=sum(r['valid'] for r in rs),hard_terminals=sum(r['hard_terminal'] for r in rs))
                    for k in ('train','validation') for rs in [[r for r in cohort_rows if r['split']==k]]},coverage='coverage.json',
                    behavior='historical feedback for WM only; no validation/H in optimizers, statistics or replay'),
           pretraining=dict(run=warm,selected='wm_001000.pt',outcome=read(root/warm/'outcome.json'),fresh_optimizers=True,fixed_statistics=True),
           independent_wm=wm_scores, frozen_collection_comparison=matched,contact_training=costs,
           new_joint_totals=dict(h32=len(history),wm_minibatches=10*len(history),critic_minibatches=20*len(history),
                valid=sum(c['collection']['policy_valid'] for c in costs),physics_intervals=sum(c['collection']['intervals'] for c in costs),
                prefix_intervals=sum(c['collection']['prefix'] for c in costs),imagined=sum(c['imagined'] for c in costs),
                process_hours=sum(c['elapsed_s'] for c in costs)/3600,exclusive_gpu_hours=None),
           formal_nominal=formal, full_from_start_return=None, subsequent_gates=dict(D='unopened',full_warp_C='unopened',
                full_native='unopened',seed1_2='unopened',H='sealed'),restart_receipts='restart_receipts.json', protocols=read(root/'standard_baseline_20261124/baseline_manifest.json')['protocols'],
           diagnostics=['entry_response_matched_u50.json','held_action_support.json','grip_commands.csv'],
           continuation_decision='Same recipe stopped at u200. Six force failures on the first 2ms at both u100/u200. No registered phase events or complete dual-finger 20ms policy intervals. The prolonged push approach at u200 ended without contact.')
    (a.out/'baseline_manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('runs',nargs='+')
    p.add_argument('--out',type=Path,required=True)
    main(p.parse_args())
