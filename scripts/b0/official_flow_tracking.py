"""Lock full parent-clock windows and compare frozen packages without shortening a window."""
import argparse
from datetime import datetime,timezone,timedelta
from pathlib import Path
import numpy as np
from learning.b0.physics import ActionMap,make_model
from scripts.b0.official_flow import PARENT_OUT,OUT,io

LOCK=OUT/'tracking_windows.json'


def trial(u,backend,side):
    root=PARENT_OUT if u<=1000 else OUT
    case=io.read(root/'physics'/f'u{u:06}_{backend}_full'/side/'full/nominal/result.json')
    raw=Path(case['raw_directory'])
    return case,raw,np.load(raw/'physics_step.npy')


def lock():
    if LOCK.exists():
        raise FileExistsError(LOCK)
    windows=[]
    for backend in ('warp','native'):
        for side in ('pull','push'):
            a,_,t=trial(500,backend,side)
            b,_,s=trial(1000,backend,side)
            assert a['episode']==b['episode']
            ref=Path('results/raw_large/b0/full_warp_hold_park_r1')/a['episode']
            labels=np.asarray(io.read(ref/'metadata.json')['phases'])[np.load(ref/'substeps/phase.npy')]
            shared=np.intersect1d(t,s)
            times=shared[(shared>0)&(shared%10==0)]
            for phase in ('settle','pregrasp'):
                selected=times[labels[times-1]==phase]
                assert len(selected)<2 or np.all(np.diff(selected)==10)
                windows.append(dict(backend=backend,side=side,episode=a['episode'],phase=phase,
                    start=int(selected[0]) if len(selected) else None,end=int(selected[-1]) if len(selected) else None,
                    step=10,count=len(selected)))
    io.write(LOCK,dict(created_beijing=datetime.now(timezone(timedelta(hours=8))).isoformat(),
        timing='Computed solely from u500/u1000 before any new milestone physical score; an initial resumed update had already run.',
        units='indices in the original 2ms reference; every common complete 20ms endpoint, label of just-ended interval',
        denominators='fixed for every evaluation and empty if unavailable; missing endpoints are not replaced',
        current_policy_dev_seeds={'1000':821001,'3000':823001,'5000':825001},windows=windows))


def yaw(q):
    w,x,y,z=q[:,3:7].T
    return np.arctan2(2*(w*z+x*y),1-2*(y*y+z*z))


def compare(u):
    w=io.read(LOCK)
    rows=[]
    for window in w['windows']:
        side,backend=window['side'],window['backend']
        case,raw,t=trial(u,backend,side)
        row=dict(window,update=u,completed_phases=[e['phase'] for e in case['events']],outcome=case['first_failure'])
        accept=False
        if window['count']:
            k=np.arange(window['start'],window['end']+1,10)
            accept=np.isin(k,t).all()
        if accept:
            ref=Path('results/raw_large/b0/full_warp_hold_park_r1')/case['episode']/'substeps'
            i=np.searchsorted(t,k)
            q,v=(np.load(raw/(name+'.npy'),mmap_mode='r')[i] for name in ('qpos','qvel'))
            qr,vr=(np.load(ref/(name+'.npy'),mmap_mode='r')[k] for name in ('qpos','qvel'))
            wheel=ActionMap(make_model('mobile' if side=='pull' else 'push')).dof[12:16]
            rmse=lambda arr:float(np.mean(arr**2)**.5)
            dy=yaw(q)-yaw(qr)
            row.update(xy_rmse_m=rmse(np.linalg.norm(q[:,:2]-qr[:,:2],axis=1)),
                heading_rmse_deg=rmse(np.rad2deg(np.arctan2(np.sin(dy),np.cos(dy)))),
                four_wheel_speed_rmse_rad_s=rmse(v[:,wheel]-vr[:,wheel]),
                six_arm_rmse_rad=rmse(q[:,23:29]-qr[:,23:29]),
                jaw_opening_rmse_m=rmse((q[:,29]-q[:,30])-(qr[:,29]-qr[:,30])))
        rows.append(row|dict(full_window_scored=bool(accept)))
    io.write(OUT/f'tracking_u{u:06}.json',rows)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('nodes',nargs='*',type=int)
    p.add_argument('--lock',action='store_true')
    args=p.parse_args()
    if args.lock: lock()
    for u in args.nodes: compare(u)
