"""Read-only comparison of two archived actor checkpoints and their observed u1 graph."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from supermimic.tasks.task_spec import build_actor_obs_td

from learning.b0.contact_model import ContactRepresentation
from learning.b0.contact_policy import build_actor
from learning.b0.contact_warp import PHASE_ID
from learning.b0.physics import ActionMap, make_model


@torch.no_grad()
def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    base=Path("results/b0/response_s0_v1")
    raw=Path("results/raw_large/b0")
    reg=Path("results/b0/standard_response_20261124/registration.json")
    ck=[torch.load(base/f"checkpoint_{i:06}.pt",map_location="cpu",weights_only=False) for i in (0,1)]
    assert [w["updates"] for w in ck]==[0,1]
    model=make_model()
    rep=ContactRepresentation(model,"cpu")
    mapping=ActionMap(model)
    actor,_=build_actor(rep,ck[0]["cfg"],model,"cpu")
    params=dict(actor.named_parameters())
    states=[x["actor"] for x in ck]
    assert states[0].keys()==states[1].keys()==actor.state_dict().keys()
    layers={}
    for key in states[0]:
        a=states[0][key].double()
        dx=states[1][key].double()-a
        layers[key]=dict(shape=list(a.shape),trainable=key in params,elements=a.numel(),initial_l2=float(a.norm()),
                         delta_l2=float(dx.norm()),max_abs=float(dx.abs().max()),changed=int(dx.count_nonzero()))
    param_rows=[v for v in layers.values() if v["trainable"]]
    rows=json.loads(reg.read_text())["starts"]
    obs=[]
    archived=[]
    for row in rows:
        src=raw/"response_entries_v1"/row["id"]/"start.npz"
        with np.load(src) as s:
            obs.append(build_actor_obs_td({"motion":torch.from_numpy(s["goal"])},torch.from_numpy(s["history"])))
        with np.load(raw/"response_requery_v1"/row["id"]/"commands.npz") as f:
            archived.append(np.stack([f["u0"], f["u1"]]))
    archived=np.stack(archived)
    commands={}
    for th,buf in ((0,0),(0,1),(1,0),(1,1)):
        actor.load_state_dict({k:states[th if k in params else buf][k] for k in states[0]},strict=True)
        actor.eval()
        commands[(th,buf)]=np.stack([actor.raw(o)[0].numpy() for o in obs])
    maxima={f"u{th}":float(abs(commands[(th,th)]-archived[:,th]).max()) for th in (0,1)}
    physical={k:np.clip(x,-1,1).astype(float)*mapping.scale+mapping.offset for k,x in commands.items()}
    changes=[]
    for i,r in enumerate(rows):
        for ch in range(23):
            x0,x1=archived[i,:,ch].astype(float)
            before,after=(np.clip([x0,x1],-1,1)*mapping.scale[ch]+mapping.offset[ch])
            u0,norm_only,param_only,u1=[a[i,ch] for a in physical.values()]
            changes.append(dict(start=r["id"],split=r["split"],side=r["side"],phase=r["phase"],channel=ch,
                 name=mapping.names[ch],u0_raw=x0,u1_raw=x1,u0_physical=before,u1_physical=after,
                 observed_clipped_delta_physical=after-before,cpu_recomputed_delta=u1-u0,
                 updated_stats_only=norm_only-u0,weights_at_updated_stats=u1-norm_only,
                 updated_weights_only_at_old_stats=param_only-u0,
                 interaction=(u1-norm_only)-(param_only-u0)))
    with (args.output/"historical_u1_frozen_commands.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,changes[0],lineterminator="\n");w.writeheader();w.writerows(changes)
    trace=json.loads((base/"gradient_u1.json").read_text())
    receipt=json.loads((base/"updates.jsonl").read_text().splitlines()[0])
    draws=[json.loads(x) for x in (base/"wm_draws.jsonl").read_text().splitlines() if json.loads(x)["update"]==1]
    assert [r["index"] for r in draws]==list(range(10))
    first_macro=list(np.array([r['h'] for r in draws]).astype(int).tolist())
    source=Counter()
    for r in draws:
        for s,meta in r["sources"].items():
            source[f"H{r['h']}/{s}"]+=meta["samples"]
    with np.load(raw/"response_s0_v1/u1_true_actor_batch.npz") as x:
        scopes={"all":np.ones(len(x["episode"]),bool),"open_hold":np.isin(x["draw_phase"],[PHASE_ID["open"],PHASE_ID["hold"]])}
        quantities={k.removeprefix("dreturn_dphysical_"):x[k].astype(float) for k in x if k.startswith("dreturn_dphysical_")}
        whole=quantities.pop("complete")
        residual=whole-sum(quantities.values())
        scopes_result={}
        for k,mask in scopes.items():
            scopes_result[k]=dict(n=int(mask.sum()),episodes=int(len(np.unique(x["episode"][mask]))),
                mode_counts={str(int(m)):int((x["draw_mode"][mask]==m).sum()) for m in np.unique(x["draw_mode"][mask])},
                terminal=int(x["terminated"][mask].sum()),by_channel={})
            for ch in (17,22):
                value=whole[mask,ch]
                scopes_result[k]["by_channel"][ch]=dict(complete_mean=float(value.mean()),complete_positive=int((value>0).sum()),
                    terms_mean={term:float(g[mask,ch].mean()) for term,g in quantities.items()},
                    residual_l2_fraction=float(np.linalg.norm(residual[mask,ch])/np.linalg.norm(value)),
                    residual_abs_max=float(abs(residual[mask,ch]).max()))
    result=dict(chain=str(base),checkpoints=["checkpoint_000000.pt","checkpoint_000001.pt"],
        state_tensors=layers,full_trainable=dict(tensors=len(param_rows),elements=sum(x["elements"] for x in param_rows),
            changed=sum(x["changed"] for x in param_rows),changed_tensors=sum(x["changed"]>0 for x in param_rows),
            delta_l2=sum(x["delta_l2"]**2 for x in param_rows)**.5,initial_l2=sum(x["initial_l2"]**2 for x in param_rows)**.5,
            max_abs=max(x["max_abs"] for x in param_rows)),
        frozen_command_identity=dict(registration=str(reg),starts=len(rows),sources=dict(train=4,validation=2),
            inputs="recorded per-start noisy history and matching goal/previous command; source requery_v1 provided independent archived actual GPU raw outputs; CPU eval and frozen two-factor substitution recomputed separately",
            cpu_minus_archived_gpu_max_abs_canonical=maxima,
            effects="Columns updated_stats_only then weights_at_updated_stats telescope for CPU predictions. Also report weights only at u0 stats and the finite difference interaction. Physical post-clamp targets in native command units (J2 rad, jaw m); no optimizer or physical stepping."),
        actual_u1=dict(optimizer_sequence=["collect 2103 legal online intervals and update actual actor input statistics","train WM on batches in recorded order","freeze WM, sample actual 256 online starts, shared policy H32","original Adam + Muon actor step","20 minibatches of GAE critic fitting"],
            wm_batch_horizons=first_macro,wm_window_counts=dict(source),wm_successor_targets=sum(x["successors"] for x in draws),
            actor_update=receipt,preclip_grad_l2=receipt["Policy/grad_norm"],global_norm_clip=1.,element_clip=.1,
            nominal_lr=2e-4,bootstrap_cap=trace["critic_value_cap"],gamma=.99,gae_lambda=.95,
            surviving_mass_step32_mean=trace["survival_mean_by_step"][-1],derivatives=scopes_result),
        scope="Recorded dJ/da0 is the derivative of the discounted original return minus auxiliary on the noisy graph through future WM states, actions, survival and clipped bootstrap. 35 open/hold starts are from actual online replay. Frozen validation commands use different states. No stored original full parameter gradient, optimizer moment at u1, raw per-sample V or u1 RNG/noisy input tensors for exact graph replay. Per-term parameter gradient, cap fraction and its cause cannot be inferred from dJ/da0, parameter displacements or factor substitutions. Residual retained.")
    (args.output/"historical_u1_actor.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")


if __name__=="__main__":
    main()
