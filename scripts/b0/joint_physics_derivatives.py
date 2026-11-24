"""Compare signed one-sided measured 20 ms secants with a C20 command Jacobian at the same start."""
import numpy as np
import torch
from learning.b0.contact_model import contact_context
from learning.b0.physics import ActionMap
from scripts.b0.dynamics_c20_pair import model_and_rep
from scripts.b0.joint_physics_audit import OLD, OUT, RAW, read, source, write
from scripts.b0.score_temporal_wm import csv_file,load_wm

WM=OLD/"offline_wm/rebase/wm_001000.pt"
DEVICE="cuda:0"
NAMES=["J2_rad","J2_rad_s","TCP_x_m","TCP_y_m","TCP_z_m","jaw_opening_m"]


def outputs(rep,x):
    tcp=rep.tcp_pose(x[:,:7],x[:,7:31])[0]
    return torch.cat([x[:,24:25],x[:,54:55],tcp,(x[:,29]-x[:,30])[:,None]],1)


def collect(model,rep,dyn,start,identity):
    examples={}
    for repeat in (0,1):
        loc=RAW/"boundary"/identity/f"repeat{repeat}"/("joint_boundary__"+start)
        meta=read(loc/"receipt.json")
        with np.load(loc/"dynamics.npz") as z,np.load(loc/"substeps.npz") as sub:
            for i,row in enumerate(meta["results"]):
                examples[row["point"],repeat]=dict(action=z["action"][0,i],state0=z["state"][0,i],state1=z["state"][1,i],
                    mode=(sub["finger_load_N"][0,i]>.01),fail=int(z["fail"][0,i]),cmd=z["physical"][i],
                    judge_fail=row["failure"]["reason"] if row["failure"] else None)
    original=source(identity)/start
    receipt=read(original/"receipt.json")
    with np.load(original/"dynamics.npz") as z,np.load(original/"substeps.npz") as sub:
        for repeat,role in enumerate(["actor","repeat"]):
            i=receipt["labels"].index(["u0",role,0,0.])
            examples["archived_u0",repeat]=dict(action=z["action"][0,i],state0=z["state"][0,i],state1=z["state"][1,i],
                mode=sub["finger_load_N"][0,i]>.01,fail=int(z["fail"][0,i]),cmd=z["physical"][i],
                judge_fail=(receipt["judges"][i]["failure"] or {}).get("reason"))
    physical={k:outputs(rep,torch.as_tensor(x["state1"],device=DEVICE)[None])[0].detach().cpu().numpy() for k,x in examples.items()}
    mapping=ActionMap(model)
    side=receipt["row"]["side"]
    ctx=contact_context(model,side,DEVICE)[None]
    rows=[]
    for ch,tag in ((17,"j2"),(22,"jaw")):
        for a,b,region in (("archived_u0",tag+"_outer","both_first_solve_saturated"),
            (tag+"_edge",tag+"_outer","one_sided_outward"),(tag+"_edge",tag+"_inner","one_sided_inward")):
            xa,xb=examples[a,0],examples[b,0]
            # Converting identical q/v across batch shapes can round body-frame velocities differently.
            state_diff=float(np.abs(xa["state0"]-xb["state0"]).max())
            np.testing.assert_allclose(xa["state0"],xb["state0"],atol=2e-7,rtol=2e-7)
            gap=xb["cmd"][ch]-xa["cmd"][ch]
            xa_rep=torch.as_tensor(xa["state0"],device=DEVICE)[None]
            act=torch.as_tensor(xa["action"],device=DEVICE)[None].requires_grad_(True)
            def forward(cmd):
                aux,rs=dyn(rep.represent(xa_rep),cmd,xa_rep[:,:7],ctx)
                return outputs(rep,rep.reconstruct_full_state(aux,rs))[0]
            if identity=="training":
                p=forward(act)
                grad=[float(torch.autograd.grad(v,act,retain_graph=i<len(p)-1)[0][0,ch]/mapping.scale[ch]) for i,v in enumerate(p)]
                pred=(forward(torch.as_tensor(xb["action"],device=DEVICE)[None])-p).detach().cpu().numpy()/gap
            else:
                grad=pred=[None]*len(NAMES)
            contact_unchanged=np.array_equal(xa["mode"],xb["mode"])
            repeat_unchanged=all(np.array_equal(examples[k,0]["mode"],examples[k,1]["mode"]) and examples[k,0]["fail"]==examples[k,1]["fail"] for k in (a,b))
            y=physical[b,0]-physical[a,0]
            noise=np.abs(physical[a,1]-physical[a,0])+np.abs(physical[b,1]-physical[b,0])
            for i,name in enumerate(NAMES):
                real=float(y[i]/gap)
                interpretable=bool(abs(y[i])>noise[i] and repeat_unchanged and contact_unchanged and xa["fail"]==xb["fail"])
                rows.append(dict(identity=identity,start=start,split=receipt["row"]["split"],channel=ch,
                    direction=region,from_point=a,to_point=b,physical_command_delta=float(gap),max_input_state_difference=state_diff,
                    output=name,measured_delta=float(y[i]),repeat_noise_bound=float(noise[i]),finite_difference=real,
                    wm_local_derivative=grad[i],wm_same_interval_secant=float(pred[i]) if pred[i] is not None else None,
                    force_contact_mode_unchanged=contact_unchanged,original_terminal_unchanged=xa["fail"]==xb["fail"],
                    repeat_mode_and_terminal_stable=repeat_unchanged,sign_interpretable=interpretable,
                    wm_sign_match=(bool(np.sign(grad[i])==np.sign(real)) if interpretable and grad[i] is not None else None)))
    return rows


if __name__=="__main__":
    model,rep=model_and_rep(.00025)
    dyn,_=load_wm(WM,model,rep,DEVICE)
    rows=[]
    for entry in read(OUT/"boundary_registration.json")["points"]:
        rows.extend(collect(model,rep,dyn,entry["id"],entry["identity"]))
    csv_file(OUT/"boundary_derivatives.csv",rows)
    matched=[r for r in rows if r["wm_sign_match"] is not None]
    write(OUT/"derivative_summary.json",dict(original_wm=str(WM),rows=len(rows),local_jacobian="Gradient with respect to actual physical target (J2 rad or full jaw m) at the named first point; reported only for matching fine training physics.",
        output_units=NAMES,interpretable_matching_identity=len(matched),matching_signs=sum(r["wm_sign_match"] for r in matched),
        method="Measured finite differences use separate 20 ms branches at the identical complete input, adjacent points are one-sided at the edge. Raw mode-switch secants provided without sign verdict. Wide saturated-region interval is a secant; its first-point local Jacobian need not match a nonlinear secant.",
        effective_starts=4,post_terminal="Terminal-first complete and numerically valid endpoints describe 20 ms diagnostic response."))
    print("directions",len(rows),len(matched),sum(r["wm_sign_match"] for r in matched))
