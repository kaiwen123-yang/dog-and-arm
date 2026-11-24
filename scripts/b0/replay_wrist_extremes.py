"""Replay registered nonterminal wrist-speed extremes on native CPU MuJoCo."""
import argparse
import json
import sys
from pathlib import Path

import mujoco as mj
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from learning.b0.physics import ActionMap, make_model
from p6_contacts import ContactMeter


OUT = ROOT/"results/b0/standard_temporal_20261124"
RAW = ROOT/"results/raw_large/b0/temporal_entries_v1"


def select(reg, mapping):
    """Largest absolute nonterminal endpoint speed by split, side and joint."""
    choices = {}
    for r in reg:
        folder = RAW/r["id"]
        with np.load(folder/"dynamics.npz") as data:
            labels = json.loads((folder/"receipt.json").read_text())["labels"]
            mask = data["valid"] & (data["fail"] == 0) & np.array([k[1]!="repeat" for k in labels])[None,:]
            assert np.any(mask)
            for channel in (19,21):
                # full_state root33 angular conversion does not change these hinge components.
                v = data["state"][1:,:,31+mapping.dof[channel]]
                t,b = np.unravel_index(np.argmax(np.where(mask,abs(v),-np.inf)),v.shape)
                key = (r["split"],r["side"],mapping.names[channel])
                if key not in choices or abs(v[t,b])>abs(choices[key]["peak_rad_s"]):
                    choices[key]=dict(start=r["id"],split=r["split"],side=r["side"],joint=mapping.names[channel],
                        peak_rad_s=float(v[t,b]),transition=int(t),lane=int(b),branch=labels[b])
    return choices


def full_m(m,d):
    mass = np.empty((m.nv,m.nv))
    if mj.__version__.startswith("3.3."):
        mj.mj_fullM(m,mass,d.qM)
    else:
        mj.mj_fullM(m,d,mass)
    return mass


def model_fields(m, a):
    result = {}
    for channel in (19,21):
        n = a.names[channel]; j=m.joint(n)
        act=int(a.actuator_ids[channel]); dof=int(a.dof[channel]); body=int(j.bodyid.item())
        result[n]=dict(channel=channel,actuator_index=act,actuator=m.actuator(act).name,joint_id=j.id,
            trn_joint=m.joint(int(m.actuator_trnid[act,0])).name, qpos_index=int(a.q[channel]),raw_qvel_index=dof,
            state_qvel_index=31+dof,represented_qvel_index=34+dof-6,scale_rad=float(a.scale[channel]),
            offset_rad=float(a.offset[channel]),gear=m.actuator_gear[act].tolist(),force_nm=m.actuator_forcerange[act].tolist(),
            ctrl_limited=int(m.actuator_ctrllimited[act]),kp_nm_per_rad=float(m.actuator_gainprm[act,0]),
            kv_nm_s_per_rad=float(-m.actuator_biasprm[act,2]),joint_damping=float(m.dof_damping[dof]),
            armature=float(m.dof_armature[dof]),frictionloss=float(m.dof_frictionloss[dof]),
            child_body=m.body(body).name,body_mass_kg=float(m.body_mass[body]),subtree_mass_kg=float(m.body_subtreemass[body]),
            body_principal_inertia_kg_m2=m.body_inertia[body].tolist())
    return result


def solve(m, a, q, v, warm, cached_bias, controls, fixed, use_archived_ctrl, from_prefix, inspect_at, side):
    d = mj.MjData(m);d.qpos[:]=q;d.qvel[:]=v
    mj.mj_forward(m,d)
    if warm is not None:
        d.qacc_warmstart[:]=warm
    else:
        d.qacc_warmstart[:]=0
    meter=ContactMeter(m,"preview_floor","back" if side=="push" else "front")
    ds=d if hasattr(d,"D_diag") else m
    ids=a.actuator_ids;vv=a.dof[[19,21]];aa=ids[[19,21]]
    series={k:[] for k in ("qpos_rad","qvel_rad_s","actuator_force_nm","ctrl_rad","contacts","nefc","qDeriv_diagonal","opening_mm","door_force_n","finger_load_n")}
    first_mass={}
    for k,target in enumerate(fixed):
        if k==inspect_at:
            # A separate buffer avoids refreshing the actual live d caches.
            pose=mj.MjData(m);pose.qpos[:]=d.qpos;pose.qvel[:]=d.qvel;mj.mj_forward(m,pose)
            mass=full_m(m,pose)
            first_mass=dict(mass_diagonal_kg_m2=np.diag(mass)[vv].tolist(),
                            effective_unconstrained_inertia_kg_m2=(1/np.diag(np.linalg.inv(mass))[vv]).tolist(),
                            v_at_start=d.qvel[vv].tolist(),q_at_start=d.qpos[a.q[[19,21]]].tolist())
        if use_archived_ctrl or (not from_prefix and k==0):
            d.ctrl[:]=controls[k]
        else:
            bias=cached_bias if k==0 and cached_bias is not None else d.qfrc_bias
            d.ctrl[ids]=target+np.asarray(bias)[a.dof]*a.bias_gain
        before_v=d.qvel.copy()
        mj.mj_step(m,d)
        if k==inspect_at:
            M=full_m(m,d)
            D=np.zeros_like(M)
            for j in range(m.nv):
                i0=ds.D_rowadr[j]
                i1=i0+ds.D_rownnz[j]
                D[j,ds.D_colind[i0:i1]]=d.qDeriv[i0:i1]
            force=d.qfrc_smooth+d.qfrc_constraint
            change=np.zeros_like(M)
            saturated=[]
            for uid in ids:
                cut=m.actuator_forcerange[uid]
                if m.actuator_forcelimited[uid] and (d.actuator_force[uid]<=cut[0] or d.actuator_force[uid]>=cut[1]):
                    joint=int(m.actuator_trnid[uid,0])
                    dof=int(m.jnt_dofadr[joint])
                    assert m.actuator_gear[uid,0]==1
                    change[dof,dof]=m.actuator_biasprm[uid,2]
                    saturated.append(m.joint(joint).name)
            other=D+change if mj.__version__.startswith("3.16.") else D-change
            after=before_v+m.opt.timestep*np.linalg.solve(M-m.opt.timestep*D, force)
            swapped=before_v+m.opt.timestep*np.linalg.solve(M-m.opt.timestep*other, force)
            first_mass["frozen_smooth_derivative_check"]=dict(saturated=saturated,native_D_diagonal=D[vv,vv].tolist(),
                swapped_D_diagonal=other[vv,vv].tolist(),v_after_archived_D=after[vv].tolist(),
                v_after_exchanging_only_saturated_servo_derivatives=swapped[vv].tolist(),
                reference_integration_max_abs_error=float(abs(after-d.qvel).max()))
        if k>=inspect_at:
            contact=meter.measure(d)
            for key,val in (("opening_mm",1000*(d.qpos[29]-d.qpos[30])),("door_force_n",np.linalg.norm(contact.door_force)),
                            ("finger_load_n",contact.finger_normal),("qpos_rad",d.qpos[a.q[[19,21]]]),("qvel_rad_s",d.qvel[vv]),("ctrl_rad",d.ctrl[aa]),
                            ("actuator_force_nm",d.actuator_force[aa]),("contacts",d.ncon),("nefc",d.nefc),
                            ("qDeriv_diagonal",d.qDeriv[ds.D_rowadr[vv]+ds.D_diag[vv]])):
                series[key].append(np.asarray(val).tolist())
    return dict(start_mass=first_mass,trace=series)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-version",required=True)
    args=parser.parse_args()
    if args.expected_version!=mj.__version__:
        raise ValueError(f"Expected {args.expected_version}, got {mj.__version__}")
    reg=json.loads((OUT/"registration.json").read_text())["starts"]
    m=make_model(); a=ActionMap(m); jj=[19,21]; dof=a.dof[jj]; qid=a.q[jj];aid=a.actuator_ids[jj]
    choices=select(reg,a)
    holds=[]
    for row in reg:
        if row["phase"]=="hold" and row["split"]=="validation":
            labels=json.loads((RAW/row["id"]/"receipt.json").read_text())["labels"]
            for tag,role in (("u0","actor"),("reference","reference")):
                b=next(i for i,lab in enumerate(labels) if lab[:2]==[tag,role])
                holds.append(dict(start=row["id"],split="validation",side=row["side"],transition=0,lane=b,
                                  branch=labels[b],diagnostic="registered first hold command"))
    cache={}
    for r in [*choices.values(),*holds]:
        name,t,b=r["start"],r["transition"],r["lane"]
        ident=f"{name}/t{t}/b{b}"
        r["trace_id"]=ident
        if ident in cache:continue
        d=RAW/name
        with np.load(d/"substeps.npz") as sub,np.load(d/"dynamics.npz") as dyn,np.load(d/"start.npz") as s:
            n=(t+1)*10
            q=np.concatenate((s["qpos"][None],sub["qpos_post"][:t+1,b].reshape(n,-1))).astype(float)
            v=np.concatenate((s["qvel"][None],sub["qvel_post"][:t+1,b].reshape(n,-1))).astype(float)
            u=sub["ctrl"][:t+1,b].reshape(n,-1).astype(float)
            f=sub["actuator_force"][:t+1,b].reshape(n,-1)
            target=(dyn["action"][:t+1,b]*a.scale+a.offset)*a.finger_factor
            fine=np.repeat(target,10,axis=0)
            if r.get("diagnostic") is None:
                assert np.all(dyn["valid"][:t+1,b]) and not np.any(dyn["fail"][:t+1,b])
            event=json.loads((d/"receipt.json").read_text())["judges"][b]["failure"] or {}
            assert np.allclose(v[-1,dof],dyn["state"][t+1,b,31+dof],rtol=0,atol=0)
            kk=t*10
            servo=m.actuator_gainprm[aid,0]*(u[kk:,aid]-q[kk:-1,qid])+m.actuator_biasprm[aid,2]*v[kk:-1,dof]
            expected=np.clip(servo,m.actuator_forcerange[aid,0],m.actuator_forcerange[aid,1])
            data=dict(held_policy_command=dyn["action"][t,b].tolist(), mapped_physical_target=target[t].tolist(),
                warmstart_and_registration=sorted(s.files),warp=dict(qvel_start_rad_s=v[kk,dof].tolist(),
                    training_failure_in_interval=int(dyn["fail"][t,b]),event_first_failure_tick=event.get("first_failure_substep"),
                    first_solve_after_event_stop=bool(event.get("first_failure_substep",10**8)<=t*10),
                    opening_mm=(1000*(q[kk+1:,29]-q[kk+1:,30])).tolist(),door_force_n=np.linalg.norm(sub["door_robot_force_N"][t,b],axis=-1).tolist(),
                    finger_load_n=sub["finger_load_N"][t,b].tolist(),
                    v_10=v[kk+1:,dof].tolist(),q_10=q[kk+1:,qid].tolist(),force_nm=f[kk:,aid].tolist(),
                    ctrl_rad=u[kk:,aid].tolist(),max_abs_servo_formula_mismatch_nm=abs(f[kk:,aid]-expected).max(0).tolist()))
            modes={}
            for mode,from_prefix,clamped_ctrl in (("qv_restart_archived_ctrl_10",False,True),
                                                  ("qv_restart_original_servo",False,False),
                                                  ("registered_branch_prefix_original_servo",True,False)):
                first=0 if from_prefix else kk
                modes[mode]=solve(m,a,q[first],v[first],s["qacc_warmstart"] if from_prefix else None,
                    s["qfrc_bias"] if from_prefix else None,u[first:],fine[first:],clamped_ctrl,from_prefix,kk-first,r["side"])
                series=np.asarray(modes[mode]["trace"]["qvel_rad_s"])
                modes[mode]["endpoint_minus_warp_rad_s"]=(series[-1]-v[-1,dof]).tolist()
                modes[mode]["path_rmse_vs_warp_rad_s"]=np.sqrt(np.mean((series-v[kk+1:,dof])**2,axis=0)).tolist()
            data["replay"]=modes;cache[ident]=data
    result=dict(version=mj.__version__,source=str(RAW.relative_to(ROOT)),selection=list(choices.values()),validation_hold=holds,
        columns=["piper_joint4","piper_joint6"],model_fields=model_fields(m,a),
        physics=dict(h=float(m.opt.timestep),integrator=int(m.opt.integrator),solver=int(m.opt.solver),
                     iterations=int(m.opt.iterations),cone=int(m.opt.cone),disableflags=int(m.opt.disableflags),
                     enableflags=int(m.opt.enableflags),gravity=m.opt.gravity.tolist(),ls_iterations=int(m.opt.ls_iterations),
                     tolerance=float(m.opt.tolerance),ls_tolerance=float(m.opt.ls_tolerance)),
        clocks="Select largest measured absolute endpoint velocity across non-repeat, valid, nonterminal windows per joint, split and side. Ten 2ms steps per actual 20ms control. Selection and non-termination use recorded training clock, not formal events.",
        replays="q/v restart uses exact measured Warp interval start and first actual ctrl; initial warmstart at arbitrary coarse boundary unknown, zeroed. One branch holds all ten archived precompensated ctrl vectors, one recomputes original bias servo from the second tick. Prefix branch starts at measured post-prefix registration with saved warmstart and qfrc_bias, replays all original 23-channel actions with its own CPU bias. Full backend contact/internal solver memory cannot be transferred. No future q/v used as control.",
        frozen_matrix_test="At the first solve, reconstruct real implicitfast integration v+h*(M-hD)^-1*(qfrc_smooth+constraint), using that CPU solve. Exchange only the saturated servo derivative diagonals of named unit-gear transmission actuators and solve again without feeding this counterfactual state back. Report reproduction error for the unmodified update.",
        derivation_sources=dict(native33="https://github.com/google-deepmind/mujoco/blob/3.3.0/src/engine/engine_derivative.c#L812",
            cpu316="https://github.com/google-deepmind/mujoco/blob/3.16.0/src/engine/engine_derivative.c#L2313",
            warp316="installed mujoco_warp/_src/derivative.py:157-162"),traces=cache)
    inertia=list(cache.values())[0]["replay"]["qv_restart_archived_ctrl_10"]["start_mass"]["effective_unconstrained_inertia_kg_m2"]
    scalar=[]
    for channel,I in zip((19,21),inertia,strict=True):
        prop=result["model_fields"][a.names[channel]]
        kp=prop["kp_nm_per_rad"]
        kv=prop["kv_nm_s_per_rad"]
        fmax=prop["force_nm"][1]
        xml=(f'<mujoco><option timestep="0.002" integrator="implicitfast" gravity="0 0 0"/>'
             f'<worldbody><body><joint name="hinge"/><inertial pos="0 0 0" mass="1" diaginertia="{I} {I} {I}"/></body></worldbody>'
             f'<actuator><position joint="hinge" kp="{kp}" kv="{kv}" forcerange="-{fmax} {fmax}"/></actuator></mujoco>')
        toy=mj.MjModel.from_xml_string(xml)
        for v0 in (0.5,70.0,-70.0):
            toy_d=mj.MjData(toy)
            toy_d.qvel[0]=v0
            mj.mj_step(toy,toy_d)
            D=float(toy_d.qDeriv[0])
            force=float(toy_d.actuator_force[0])
            expected=v0+toy.opt.timestep*force/(I-toy.opt.timestep*D)
            scalar.append(dict(joint=a.names[channel],v0=v0,inertia=I,kv=kv,dt=float(toy.opt.timestep),
                force=force,clamped=bool(abs(force)>=fmax),qDeriv=D,v1=float(toy_d.qvel[0]),
                v1_from_M_minus_hD=expected,error=float(toy_d.qvel[0]-expected)))
    result["single_hinge_test"]=scalar
    result["single_hinge_definition"]="One DOF, no contact, same 2ms implicitfast, same J4/J6 kp/kv/force limits with inertia taken from the first selected measured configuration's effective free inertia. One step at q=target=0, zero warmstart. Isolates documented saturation derivative branch; not a surrogate full robot."
    (OUT/f"nonterminal_wrist_replay_{mj.__version__}.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(mj.__version__,len(cache),"distinct cases",[(r["side"],r["joint"],r["peak_rad_s"]) for r in choices.values()])


if __name__=="__main__":
    main()
