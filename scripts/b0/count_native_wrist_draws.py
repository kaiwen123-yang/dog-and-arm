"""Index J4/J6 force-limit exposure of the actual paired native supervision."""
import argparse
import json
import sys
from pathlib import Path

import mujoco as mj
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from learning.b0.physics import ActionMap
from p6_scene import build

OUT=ROOT/"results/b0/standard_temporal_20261124"


def replay_one(folder,t):
    cfg=json.loads((folder/"config.json").read_text())
    m=build(cfg)
    mapping=ActionMap(m)
    aa=mapping.actuator_ids[[19,21]]
    vv=mapping.dof[[19,21]]
    q=np.load(folder/"qpos.npy",mmap_mode="r")
    v=np.load(folder/"qvel.npy",mmap_mode="r")
    bounds=np.load(folder/"physics_step.npy")
    lo,hi=bounds[t:t+2]; assert hi-lo==10
    u=np.load(folder/"substeps/ctrl.npy",mmap_mode="r")[lo:hi]
    w=np.load(folder/"substeps/qvel.npy",mmap_mode="r")[lo+1:hi+1, vv]
    f=np.load(folder/"substeps/actuator_force.npy",mmap_mode="r")[lo:hi,aa]
    assert np.array_equal(w[-1],v[t+1,vv])
    d=mj.MjData(m)
    d.qpos[:]=q[t];d.qvel[:]=v[t];mj.mj_forward(m,d)
    d.qacc_warmstart[:]=0.
    obs=[];forces=[]
    for actual in u:
        d.ctrl[:]=actual
        mj.mj_step(m,d)
        obs.append(d.qvel[vv].copy()); forces.append(d.actuator_force[aa].copy())
    delta=np.array(obs)-w
    return dict(start_qvel_rad_s=v[t,vv].tolist(),native33_measured_qvel_rad_s=w.tolist(),replay_qvel_rad_s=np.array(obs).tolist(),
                measured_force_nm=f.tolist(),replay_force_nm=np.array(forces).tolist(),
                qvel_path_rmse_rad_s=np.sqrt(np.mean(delta**2,axis=0)).tolist(),qvel_path_max_abs_error_rad_s=abs(delta).max(0).tolist(),
                endpoint_error_rad_s=delta[-1].tolist())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--expected-version",required=True)
    args=p.parse_args()
    assert mj.__version__==args.expected_version
    meta=json.loads((OUT/"paired_sources.json").read_text())
    eps=meta["inventory"]["native"]
    with np.load(OUT/"paired_indices.npz") as indices:
        src,starts=indices["source"],indices["start"]
    ends=np.cumsum([r["n"] for r in eps])
    offsets=np.r_[0,ends[:-1]]
    nstates=ends[-1]
    sides=np.empty(nstates,dtype=bool)
    peak=np.zeros((nstates,2))
    sat_ticks=np.zeros((nstates,2),int)
    live=np.zeros(nstates,dtype=bool)
    epi=[]
    bound=None
    for i,r in enumerate(eps):
        d=ROOT/r["path"]
        mdata=json.loads((d/"metadata.json").read_text())
        assert mdata["mujoco_version"]=="3.3.0" and mdata["wm_split"]=="train"
        assert mdata["actuator_names_xml"][19]=="piper_joint4_motor" and mdata["actuator_names_xml"][21]=="piper_joint6_motor"
        cfg=json.loads((d/"config.json").read_text())
        m=build(cfg); a=ActionMap(m); ids=a.actuator_ids[[19,21]]
        ranges=m.actuator_forcerange[ids]; assert np.array_equal(ranges, np.array([[-12,12],[-8,8]]))
        bound=ranges[:,1]
        f=np.abs(np.load(d/"substeps/actuator_force.npy",mmap_mode="r")[:,ids])
        e=np.load(d/"physics_step.npy"); ok=np.load(d/"valid_full_interval.npy")
        assert np.array_equal(np.diff(e)==10,ok) and len(e)==r["n"] and e[-1]==len(f)
        windows=np.where(ok)[0]; ticks=e[windows,None]+np.arange(10)
        peak[offsets[i]+windows]=f[ticks].max(1)
        sat_ticks[offsets[i]+windows]=(f[ticks]>=bound).sum(1)
        live[offsets[i]+windows]=True
        sides[offsets[i]:ends[i]]=r["side"]=="push"
        epi.append(dict(episode=r["group"],side=r["side"],complete_intervals=len(windows),all_complete_peak_nm=f[ticks].max((0,1)).tolist()))
    per_side={}
    selected={}
    for side in ("all","pull","push"):
        per_side[side]={}
        for horizon_name in ("H1","H7","both"):
            samples=[];wmwindows=[]
            for h in (1,7):
                if horizon_name not in (f"H{h}","both"):
                    continue
                schedule=(np.arange(len(src))%10<2)==(h==1)
                subset=src[schedule]==meta["names"].index("native")
                entry=starts[schedule][subset]
                if side!="all":
                    entry=entry[sides[entry]==(side=="push")]
                idx=entry[:,None]+np.arange(h)
                assert live[idx].all() and np.all(np.searchsorted(ends,entry,side="right")[:,None]==np.searchsorted(ends,idx,side="right"))
                samples.append(idx.ravel())
                wmwindows.append(dict(h=h,start=entry,has_saturation=(peak[idx]>=bound).any(1)))
            ix=np.concatenate(samples)
            unique=np.unique(ix)
            nw=sum(len(w["start"]) for w in wmwindows)
            saturated_windows=sum(w["has_saturation"].sum(0) for w in wmwindows)
            saturated_targets=(peak[ix]>=bound).sum(0)
            ids=np.searchsorted(ends,unique,side="right")
            per_side[side][horizon_name]=dict(draws=nw,distinct_windows=sum(len(np.unique(w["start"])) for w in wmwindows),
                weighted_successors=len(ix),distinct_successors=len(unique),distinct_episodes=int(len(np.unique(ids))),
                weighted_substeps=10*len(ix),actual_peak_abs_nm=peak[ix].max(0).tolist(),
                weighted_windows_with_hard_clamp_J4_J6=saturated_windows.tolist(),
                percent_draws_with_hard_clamp_J4_J6=(100*saturated_windows/nw).tolist(),
                weighted_targets_with_hard_clamp_J4_J6=saturated_targets.tolist(),
                percent_targets_with_hard_clamp_J4_J6=(100*saturated_targets/len(ix)).tolist(),
                weighted_saturated_ticks_J4_J6=sat_ticks[ix].sum(0).tolist(),
                nonzero_saturation_dedup_targets_J4_J6=(peak[unique]>=bound).sum(0).tolist(),
                weighted_targets_reaching_98pct_J4_J6=(peak[ix]>=.98*bound).sum(0).tolist())
            if side!="all" and horizon_name=="both":
                at,which=np.unravel_index(np.argmax(peak[unique]/bound),peak[unique].shape)
                choice=unique[at]; ep=eps[ids[at]]; t=int(choice-offsets[ids[at]])
                selected[side]=dict(group=ep["group"],start=t,path=ep["path"],max_force_fraction=float(peak[choice,which]/bound[which]),
                    weighted_occurrences=int((ix==choice).sum()),chosen_joint=["J4","J6"][which],trace=replay_one(ROOT/ep["path"],t))
    result=dict(replay_version=mj.__version__,force_limits_nm=bound.tolist(),order=["J4","J6"],
        source="paired_indices.npz/paired_sources.json; same index schedule for both arms; native Teacher recorded MuJoCo 3.3.0",
        qualification="Each drawn H1/H7 window verified within same episode, all actual bounds differ by ten ticks. Count force at all ten interval solves from substeps/actuator_force.npy; hard clamp is >= actual absolute ±force limit. The .98 physical monitoring band is counted separately.",
        counting="Window is (source episode, start, h); successor identity is (source episode, 20 ms interval). Draws sample with replacement. Both horizon totals use union of unique physical intervals. Duplicate exposures across arms are not independent.",
        replay_definition="Within actually drawn native successor intervals on each side, choose the greatest actual fraction of either hard wrist force limit (first global interval on ties). Replay only these two intervals on this CPU, exact source q/v and actual ten full bias-compensated 23-motor ctrl vectors; no stored arbitrary-boundary warmstart, so forward then zero warmstart. Geometry built from exact per-episode config.",
        side_horizon_counts=per_side,source_episodes=epi,actually_drawn_replays=selected)
    (OUT/f"native_wrist_draws_{mj.__version__}.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(mj.__version__,per_side["all"]["both"],[(k,v["trace"]["qvel_path_max_abs_error_rad_s"]) for k,v in selected.items()])


if __name__=="__main__":
    main()
