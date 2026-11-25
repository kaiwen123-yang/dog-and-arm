"""Independently recompute original fixed-window scores and index the input arrays."""
from pathlib import Path
import numpy as np
from learning.b0.physics import ActionMap, build
from scripts.b0.pregrasp_geometry import OUT, OLD, case_at, read, write


def scalar_rmse(delta):
    return float(np.sqrt(np.mean(delta**2)))


def heading(q):
    w,x,y,z=q[:,3:7].T
    return np.arctan2(2*(w*z+x*y),1-2*(y*y+z*z))


def run():
    records=read(OUT/'registered_windows_recheck.json')
    inventory=[]
    for row in records:
        u,backend,side=(row[k] for k in ('update','backend','side'))
        case,raw,obs,ref,path=case_at(u,backend,side)
        if row['kind']=='actual_event':
            official=next(r for r in read(OLD/f'readiness_u{u:06}.json') if r['side']==side and r['backend']==backend)
            assert row['complete']==official['window_complete']
            assert row['matched']==official['window_phase_match_n'] and row['available']==official['actual_n']
            score={}
            if row['complete']:
                mask=(obs['step']>=row['start'])&(obs['step']<=row['end'])
                for k in ('endpoint_m','endpoint_rad','xy_m','heading_deg','speed_m_s','yaw_rate_deg_s'):
                    a=obs[k][mask]
                    score[k+'_median_abs']=float(np.median(abs(a))) if np.isfinite(a).all() else None
                score['best_ready_ratio']=float((obs['current'][mask]/obs['required'][mask]).max())
                score['four_wheel_min_N']=[float(np.min(obs[f'wheel_{i}_N'][mask])) for i in range(4)]
            inventory.append(dict(update=u,side=side,backend=backend,result=str(path),raw=str(raw),
                reference=str(ref),raw_inputs=['readiness.npy','solved_servo_trace.npz','physics_step.npy','qpos.npy','qvel.npy'],
                actor_input_extra=['clipped_action.npy','raw_action.npy'] if (u,backend)==(10000,'warp') else [],
                reference_inputs=['metadata.json','qpos.npy','substeps/qpos.npy','substeps/qvel.npy',
                                  'substeps/phase.npy','substeps/tcp_goal_world_m.npy','substeps/tool_goal_world_R.npy']))
        else:
            official=next(r for r in read(OLD/f'tracking_u{u:06}.json') if r['side']==side and r['backend']==backend and r['phase']==row['phase'])
            assert row['complete']==official['full_window_scored']
            score={}
            if row['complete']:
                parent=Path('results/b0/standard_official_flow_continuation_20261124') if u==4991 else OLD
                formal=read(parent/'physics'/f'u{u:06}_{backend}_full'/side/'full/nominal/result.json')
                d=Path(formal['raw_directory'])
                ticks=np.load(d/'physics_step.npy')
                k=np.arange(row['start'],row['end']+1,10)
                ix=np.searchsorted(ticks,k)
                q,v=(np.load(d/(n+'.npy'),mmap_mode='r')[ix] for n in ('qpos','qvel'))
                qr,vr=(np.load(ref/'substeps'/(n+'.npy'),mmap_mode='r')[k] for n in ('qpos','qvel'))
                dh=heading(q)-heading(qr)
                wheels=ActionMap(build(case['actual_config'])).dof[12:16]
                score=dict(xy_rmse_m=scalar_rmse(np.linalg.norm(q[:,:2]-qr[:,:2],axis=1)),
                           heading_rmse_deg=scalar_rmse(np.rad2deg(np.arctan2(np.sin(dh),np.cos(dh)))),
                           four_wheel_speed_rmse_rad_s=scalar_rmse(v[:,wheels]-vr[:,wheels]),
                           six_arm_rmse_rad=scalar_rmse(q[:,23:29]-qr[:,23:29]),
                           jaw_opening_rmse_m=scalar_rmse((q[:,29]-q[:,30])-(qr[:,29]-qr[:,30])))
        for key,value in score.items():
            if value is None:
                assert official[key] is None
            else:
                np.testing.assert_allclose(value,official[key],rtol=1e-6,atol=1e-10)
        row['score']=score if row['complete'] else None
        row['original_receipt_check']=True
    write('registered_windows_recheck.json',records)
    write('source_array_inventory.json',inventory)


if __name__=='__main__':
    run()
