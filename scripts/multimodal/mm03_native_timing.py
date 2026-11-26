"""Time registered native CF windows and compare the scoring logic on shared physical states."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
import json
import multiprocessing
from pathlib import Path
import pickle
import statistics
import subprocess
import sys
import time
import types

import mujoco as mj
import numpy as np

from learning.b0.physics import ActionMap, build
from scripts.b0.eval_contact_segments import continuous_initial
from scripts.multimodal.collect_feasibility import teacher_config
from scripts.multimodal.mm02_physics import JUDGE_DYNAMIC
from scripts.multimodal.mm03_adapter import CommandTeacher
from scripts.multimodal.mm03_launch import REPO, now, read, write


def module(name, source):
    mod=types.ModuleType(name)
    mod.__file__=str(REPO/"scripts/multimodal"/(name+".py"))
    sys.modules[name]=mod
    exec(compile(source,mod.__file__,"exec"),mod.__dict__)
    return mod


def implementations(directory, revision):
    if directory is not None and (directory/"mm03_plant.py").is_file():
        module("scripts.multimodal.mm03_plant",(directory/"mm03_plant.py").read_text())
    if directory is not None and (directory/"mm03_wheel_contacts.py").is_file():
        module("scripts.multimodal.mm03_wheel_contacts",(directory/"mm03_wheel_contacts.py").read_text())
    paths=("scripts/p6_contacts.py","learning/multimodal/judge.py","scripts/multimodal/mm03_c_native.py")
    impl=[]
    for which in ("old","new"):
        src=[subprocess.check_output(["git","show",f"{revision}:{p}"],cwd=REPO,text=True) if which=="old"
             else ((directory/Path(p).name) if directory else (REPO/p)).read_text() for p in paths]
        c,j,n=[module("mm03_timed_"+tag+which,txt) for tag,txt in zip(("contacts","judge","native"),src,strict=True)]
        j.ContactMeter=c.ContactMeter
        impl.append((j.DoorTaskJudge,n.StudentBranch))
    return impl


def compare_result(old,new):
    if old.i!=new.i or old.steps!=new.steps or old.last!=new.last or old.failure!=new.failure:
        raise AssertionError((old.last,new.last,old.failure,new.failure))
    if (old.ready,old.unloaded,old.lost,old.sliding)!=(new.ready,new.unloaded,new.lost,new.sliding):
        raise AssertionError("Changed a sustained force, support or timing counter")
    if not np.array_equal(old.saturated,new.saturated):
        raise AssertionError("Changed the saturation counter")


def full_case(args):
    root,directory,revision,side,goal,mode=args
    (old,_),(new,new_branch)=implementations(directory,revision)
    scene=dict(id="tr_nominal",perturbation={})
    cfg=teacher_config(side,goal,scene)
    model=build(cfg)
    d,_,_=continuous_initial(model,cfg,None)
    teacher=CommandTeacher(model,d,cfg) if mode=="teacher" else None
    action_source=root/f"B/warm/development/warm_development_{mode}_1701_tr_nominal_{side}{goal}_pure/episode/action_clipped.npy"
    source=None if teacher else np.load(action_source,mmap_mode="r")
    judges=[old(model,cfg,side,goal),new(model,cfg,side,goal),new(model,cfg,side,goal)]
    ref,full,short=judges
    if hasattr(new_branch,"cf_meter"):
        short.meter=new_branch.cf_meter(short.meter)
    m=ActionMap(model)
    for k in range(len(d.warning.number)):
        d.warning.number[k]=1
        if any(w.number for w in d.warning)!=bool(d.warning.number.any()):
            raise AssertionError("Warning flag views differ")
        d.warning.number[k]=0
    tick=0
    while not ref.passed and not ref.failure:
        if source is not None and tick>=len(source):
            raise AssertionError("Archived actions ended before the recorded failure")
        raw=teacher.before(d).raw if teacher else source[tick].astype(np.float64)
        servo=(m.offset+m.scale*np.clip(raw,-1.,1.))*m.finger_factor
        for sub in range(10):
            if teacher and sub:teacher.before(d)
            q,v=d.qpos.copy(),d.qvel.copy()
            d.ctrl[m.actuator_ids]=servo+d.qfrc_bias[m.dof]*m.bias_gain
            mj.mj_step(model,d)
            ca=ref.observe(d,q,v)
            cb=full.observe(d,q,v)
            cc=short.observe(d,q,v,return_wheel_slip=False)
            compare_result(ref,full)
            compare_result(ref,short)
            if not (np.array_equal(ca.normal,cb.normal) and np.array_equal(ca.normal,cc.normal)
                    and np.array_equal(ca.finger_normal,cc.finger_normal) and ca.unexpected==cc.unexpected
                    and np.array_equal(ca.slip_long,cb.slip_long,equal_nan=True)
                    and np.array_equal(ca.slip_lat,cb.slip_lat,equal_nan=True)):
                raise AssertionError("Changed a returned contact diagnostic")
            if teacher:teacher.after(d,ca)
            if ref.failure or ref.passed:break
        tick+=1
    if not (ref.result()==full.result()==short.result()):
        raise AssertionError("Final judge results differ")
    return dict(side=side,goal=goal,mode=mode,physics_steps=ref.steps,events=ref.events,first_failure=ref.failure,
                success=ref.passed,judges_compared_on_each_substep=3,warning_flags_tested=len(d.warning.number),
                native_wheel_only_hits=getattr(short.meter,"hits",0),original_meter_calls=getattr(short.meter,"fallbacks",0))


def cf_windows(root,directory,revision):
    pairs=implementations(directory,revision)
    source=next((root/"C/CF32/seed1701/shared_replay").glob("applied0001*.npz"))
    anchors={}
    for f in Path("/root/autodl-tmp/mm02-20261125/round6/recovery_train").glob("*/episode/metadata.json"):
        m=read(f)
        if m["horizon_complete"]:
            anchors[m["anchor_key"]]=Path(m["parent_path"]).parent/"snapshots"/f"{m['anchor_tick']:06d}.pkl"
    with np.load(source) as z:
        keys,slots,ticks,actions,expected=[z[k] for k in ("keys","slot","tick","action","p")]
    chosen=[i for i in range(32) if (slots==i).sum()==32][:6]
    inputs=[(anchors[str(keys[i])],np.flatnonzero(slots==i)) for i in chosen]
    # Both implementations share the same warmed immutable model/sensor caches.
    # Each timing interval starts by restoring a fresh solver and judge state for this anchor.
    records=[]
    reference={}
    cached=set()
    total=0
    for trial in (0,1,1,0):
        judge,branch_impl=pairs[trial]
        wall=0.
        step_count=0
        for idx,(anchor,indices) in enumerate(inputs):
            br=branch_impl(anchor)
            if trial and hasattr(br.sensors,"mm03_compiled_file"):
                cached.add(br.sensors.mm03_compiled_file)
            with anchor.open("rb") as f:
                job=pickle.load(f)["parent"]
            new_judge=judge(br.model,br.judge.cfg,job["side"],job["goal"])
            if hasattr(branch_impl,"cf_meter"):
                new_judge.meter=branch_impl.cf_meter(new_judge.meter)
            new_judge.__dict__.update(deepcopy({k:getattr(br.judge,k) for k in JUDGE_DYNAMIC}))
            br.judge=new_judge
            br.sensors.image(br.data.qpos,br.data.qvel)
            wall_start=time.perf_counter()
            actual=[branch_impl.advance(br,actions[j]) for j in indices[np.argsort(ticks[indices])]]
            wall+=time.perf_counter()-wall_start
            for j,result in zip(indices[np.argsort(ticks[indices])],actual,strict=True):
                step_count+=result["substeps"]
                if not np.array_equal(expected[j],result["p"]):
                    raise AssertionError("Archived on-policy physical proprioception differs")
                compare={k:v for k,v in result.items() if k!="image"}
                image=result["image"]
                if j not in reference:
                    reference[j]=(compare,image)
                else:
                    previous,previous_image=reference[j]
                    if any(not np.array_equal(previous[k],v,equal_nan=True) if isinstance(v,np.ndarray)
                           else previous[k]!=v for k,v in compare.items()):
                        raise AssertionError("Native branch observable or terminal state changed")
                    if (image is None)!=(previous_image is None) or (image is not None and
                                not all(np.array_equal(a,b) for a,b in zip(image,previous_image,strict=True))):
                        raise AssertionError("Native camera exposure changed")
        total+=step_count
        records.append(dict(reference_or_optimized=("original","optimized")[trial],
                            physics_steps=step_count,wall_s=wall,steps_per_s=step_count/wall))
    return dict(source=str(source),anchors=[str(a) for a,_ in inputs],runs=records,native_substeps=total,
                measured_compiled_files=sorted(cached),
                speedup=statistics.mean(z["wall_s"] for z in records if z["reference_or_optimized"]=="original")/
                        statistics.mean(z["wall_s"] for z in records if z["reference_or_optimized"]=="optimized"))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--candidate-dir",type=Path)
    p.add_argument("--cached-windows-only",action="store_true")
    p.add_argument("--baseline",default="e823c6fe1a9ef714b01b7c8b1945e77af9274ccd")
    a=p.parse_args()
    cf=cf_windows(a.root,a.candidate_dir,a.baseline)
    if a.cached_windows_only:
        if not cf["measured_compiled_files"]:
            raise ValueError("No verified compiled model was exercised")
        write(a.output,dict(checked_beijing=now(),reference=a.baseline,cf=cf,
                            diagnostic_native_substeps=cf["native_substeps"],optimizer_updates=0))
        print("Cached native replay verified",cf["native_substeps"],len(cf["measured_compiled_files"]),flush=True)
        raise SystemExit
    cases=[("pull",15,"teacher"),("push",25,"teacher"),("pull",15,"D23"),("pull",15,"H9")]
    with ProcessPoolExecutor(2,mp_context=multiprocessing.get_context("spawn")) as pool:
        scores=list(pool.map(full_case,((a.root,a.candidate_dir,a.baseline,*case) for case in cases)))
    write(a.output,dict(checked_beijing=now(),reference=a.baseline,cf=cf,full_cases=scores,
                       diagnostic_native_substeps=cf["native_substeps"]+sum(r["physics_steps"] for r in scores),
                       optimizer_updates=0,hardware_motion_commands=0))
    print("equal scores",[(r["mode"],r["physics_steps"],len(r["events"])) for r in scores],
          "CF warm speedup",cf["speedup"],flush=True)

