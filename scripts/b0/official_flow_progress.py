"""Paired physical tracking at common full-task times on the same nominal reference."""
import argparse
from pathlib import Path
import numpy as np
from scripts.b0.official_flow import OUT, io


def compare(a,b,backend):
    rows=[]
    for side in ('pull','push'):
        paths=[OUT/'physics'/f'u{k:06}_{backend}_full'/side/'full'/'nominal'/'result.json' for k in (a,b)]
        cases=[io.read(p) for p in paths]
        records=[Path(r['raw_directory']) for r in cases]
        steps=[np.load(p/'physics_step.npy') for p in records]
        shared,i,j=np.intersect1d(*steps,return_indices=True)
        assert shared[0]==0 and len(shared)>1 and cases[0]['episode']==cases[1]['episode']
        ref_dir=Path('results/raw_large/b0/full_warp_hold_park_r1')/cases[0]['episode']
        ref=np.load(ref_dir/'substeps/qpos.npy',mmap_mode='r')[shared[1:]]
        row=dict(side=side,common_end_s=float(shared[-1]*.002),common_measured_endpoints=len(shared)-1)
        for node,r,p,idx in zip((a,b),cases,records,(i,j)):
            q=np.load(p/'qpos.npy',mmap_mode='r')[idx[1:]]
            arm_rmse=float(np.sqrt(np.mean((q[:,23:29]-ref[:,23:29])**2)))
            data=np.load(p/'physical_events_2ms.npy',mmap_mode='r')
            settle=next((e['end_step'] for e in r['events'] if e['phase']=='settle'),None)
            row[f'u{node}']=dict(completed_phases=[e['phase'] for e in r['events']],failure=r['first_failure'],
                tcp_handle_at_failure_m=r['last_physical_observation']['tcp_handle_error_m'],
                common_arm_tracking_rmse_rad=arm_rmse,common_base_tracking_rmse_m=float(np.sqrt(np.mean(np.sum((q[:,:3]-ref[:,:3])**2,axis=1)))),
                common_terminal_tcp_handle_m=float(data[int(shared[-1])-1,6]),
                time_after_settle_s=(r['physics_steps']-settle)*.002 if settle else None)
        rows.append(row)
    io.write(OUT/f'paired_full_{backend}_u{a}_u{b}.json',dict(backend=backend,rows=rows,
        scope='Same physical reference time to the shorter trace, excluding frame zero for RMSE; endpoint metrics use their recorded actual phase and time.'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('start',type=int);p.add_argument('end',type=int);p.add_argument('backend')
    args=p.parse_args()
    compare(args.start,args.end,args.backend)
