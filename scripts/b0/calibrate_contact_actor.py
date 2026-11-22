"""Supervised initialization of the original proprio actor on six real held door teachers."""
from argparse import ArgumentParser
import json
from pathlib import Path

import numpy as np
import torch
from supermimic.tasks.task_spec import build_actor_obs_td

from learning.b0.contact_policy import DoorMotions, REFERENCE_RESIDUAL, build_actor, sensor
from learning.b0.model import RobotRepresentation, full_state, tensor
from learning.b0.physics import ActionMap, make_model


REFS = tuple(f"{side}_{goal}_train" + ("_grip" if goal == 0 else "")
             for side in ("pull", "push") for goal in (0, 5, 15))


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


@torch.no_grad()
def observations(root, references, bank, rep, device, validation):
    goals, histories, targets, labels = [],[],[],[]
    keys = []
    for ref in references:
        name = ref.name.replace("_train", "_validation") if validation else ref.name
        path = root/name
        meta = json.loads((path/"metadata.json").read_text())
        if meta["wm_split"] != ("validation" if validation else "train") or not meta["success"]:
            raise ValueError(path)
        valid = np.load(path/"valid_full_interval.npy")
        # Both the validation trajectory and the given training reference must
        # have a real frame at this absolute time. No re-timing by physical events.
        n = min(int(valid.sum()), int(bank.motion_ends[bank.ids[ref.name]])-bank.starts[ref.name]-1)
        q, v, prev = [tensor(np.load(path/(f+".npy"))[:n],device) for f in ("qpos","qvel","last_action")]
        s = sensor(rep,full_state(q,v),prev)
        start = 0 if meta.get('full_task') else 9
        k = torch.arange(start,n,device=device)
        # Full tasks repeat the actual initial observation only until ten real frames exist.
        indices = (k[:,None]+torch.arange(-9,1,device=device)).clamp_min(0)
        histories.append(s[indices])
        _, g = bank.goals(rep, k+bank.starts[ref.name],q[k,:7])
        goals.append(g)
        targets.append(tensor(np.load(path/"action_clipped.npy")[start:n],device))
        phase = np.array(meta["phases"])[np.load(path/"phase.npy")[start:n]]
        labels.extend(phase.tolist())
        keys.extend([name]*len(phase))
    return torch.cat(goals),torch.cat(histories),torch.cat(targets),np.array(keys),np.array(labels)


@torch.no_grad()
def scores(actor, data, mapping):
    goals,hist,actions,keys,phases=data
    pred = torch.cat([actor(build_actor_obs_td({"motion":goals[i:i+512]},hist[i:i+512]))
                      for i in range(0,len(hist),512)])
    residual = ((pred-actions)*tensor(mapping.scale,pred.device)).cpu().numpy()
    def group(mask):
        result = dict(frames=int(mask.sum()))
        for name,sl in (("leg_rad",slice(0,12)),("wheel_rad_s",slice(12,16)),
                        ("arm_rad",slice(16,22)),("jaw_m",slice(22,23))):
            err = residual[mask,sl]
            result[name] = dict(rmse=float(np.sqrt(np.mean(err**2))), max_abs=float(np.abs(err).max()),
                                p95_abs=float(np.quantile(np.abs(err),.95)))
        return result
    out = {"all": group(np.ones(len(hist),bool))}
    for name in np.unique(keys):
        out[name] = {"all":group(keys==name)}
        for phase in np.unique(phases[keys==name]):
            out[name][str(phase)]=group((keys==name)&(phases==phase))
    return out


def calibrate(args):
    out=Path("results/b0")/args.run
    out.mkdir(parents=True,exist_ok=False)
    source=torch.load(args.source,weights_only=False,map_location="cpu")
    if (source["seed"],source["updates"],source["collected"])!=(0,1000,1088000):
        raise ValueError("Expected the frozen B0-03 seed0 source")
    torch.manual_seed(0)
    torch.set_float32_matmul_precision("high")
    dev="cuda:0"
    model=make_model()
    mapping=ActionMap(model)
    rep=RobotRepresentation(model,dev)
    names = tuple(args.references or REFS)
    if len(names) != len(set(names)):
        raise ValueError('Duplicate training reference')
    references=[args.reference_directory/n for n in names]
    bank=DoorMotions(references,rep,dev)
    cfg = dict(source["cfg"])
    initial = dict(source["actor"])
    if args.reference_residual:
        cfg["actor_parameterization"] = REFERENCE_RESIDUAL
    actor,_=build_actor(rep,cfg,model,dev)
    if args.reference_residual:
        initial.update(reference_offset=actor.reference_offset,reference_scale=actor.reference_scale)
    if args.warm_actor:
        warm = torch.load(args.warm_actor, map_location='cpu', weights_only=False)
        if (not args.reference_residual or warm.get('actor_parameterization') != REFERENCE_RESIDUAL or
                warm['seed'] != source['seed'] or warm['cfg'] != source['cfg'] or warm['source'] != str(args.source)):
            raise ValueError('Expected a compatible supervised seed0 reference-residual initializer')
        initial = warm['actor']
    actor.load_state_dict(initial,strict=True)
    actor.eval()  # normalizers stay frozen on original B0-03 statistics
    teacher=observations(args.reference_directory,references,bank,rep,dev,False)
    val=observations(args.reference_directory,references,bank,rep,dev,True)
    g,h,targets,_,_ = teacher
    with torch.no_grad():
        anchor=build_actor_obs_td({"motion":g[::128]},h[::128])
        before=actor.raw(anchor)
        # Reparameterize only the final linear rows. All 23 initial physical outputs
        # are preserved. The buffers and the compensating weights travel together.
        if args.warm_actor:
            diff = 0.0
        else:
            actor.standard_action[16:] *= 32
            actor.decoder[-1].weight[16:] /= 32
            actor.decoder[-1].bias[16:] /= 32
            diff=float((actor.raw(anchor)-before).abs().max())
            if diff>1e-5:
                raise ValueError(f"Initial 23-channel actor changed by {diff}")
            if args.reference_residual:
                actor.decoder[-1].weight[16:].zero_()
                actor.decoder[-1].bias[16:].zero_()
                baseline = actor.raw(anchor)
                arm_jaw = torch.cat([g[::128,16:22],g[::128,22:23]-g[::128,23:24]],dim=-1)
                torch.testing.assert_close(baseline[:,:16],before[:,:16],atol=1e-6,rtol=0)
                torch.testing.assert_close(baseline[:,16:] * actor.reference_scale + actor.reference_offset,
                                           arm_jaw,atol=1e-6,rtol=0)
    resolved=dict(run=args.run, variant=("effort32_arm_jaw_history_swap" if args.swap_arm_history else "effort32_arm_jaw_supervised"), seed=0, source=str(args.source),
        references=names, reference_directory=str(args.reference_directory), validation_reference="same-side, same-goal nominal training reference; unchanged absolute frame number",
        validation_feedback="measured validation proprio and previously executed teacher actions at the matching absolute frame, fixed training reference as sole goal; action-regression metric, not a closed loop",
        training_frames=len(h), validation_frames=len(val[1]), input="77 x history10, official motion reference, no object state or teacher target at inference",
        normalizers="B0-03 observation and goal buffers loaded and kept frozen", standard_action=actor.standard_action.tolist(),
        scale_equivalence_max_abs=diff, output_units="units from B0-03 except six arm rows and jaw multiplied by 32; decoder rows divided by 32 before optimization",
        optimizer="AdamW lr=2e-4 wd=0, cosine decay to 2e-6; mean of four dimensionless physical-channel losses",
        block_units=dict(leg_rad=.005,wheel_rad_s=.10,arm_rad=.005,jaw_m=.0005),
        teacher_history_noise="uniform independent perturbation of last-action entries, half-width 1% of declared logical-action range; measured qpos/qvel history unchanged",
        optimizer_steps=args.updates,batch_size=256,selection="final numbered update; validation not used to choose a snapshot",
        checkpoint="actor-only warm start; no WM/Critic/optimizer/online experience in this supervised diagnostic")
    if args.reference_residual:
        resolved.update(variant=REFERENCE_RESIDUAL,actor_parameterization=REFERENCE_RESIDUAL,
                        output_units="same 32x arm/jaw output units as the ordinary BC comparison",
                        initialization="frozen B0-03 network; keep first 16 rows, set 7 residual rows to zero after unit conversion",
                        residual_base="first frame in given goal_motion: six arm joint positions and measured two-finger separation; mapped to the logical servo units before adding trainable residual, then clipped",
                        lineage="cfg in this supervised checkpoint is the frozen source configuration; actor_parameterization selects its new named head")
    if args.warm_actor:
        resolved.update(initial_actor=str(args.warm_actor), warm_start='strict load of the frozen previous policy including its full output units; fresh optimizer',
                        initialization='retain reference residual weights and normalizers; no additional unit rescaling')
    if args.swap_arm_history:
        resolved["training_history_intervention"] = (
            "For half each shuffled batch, replace arm/finger q and v and previous arm/jaw "
            "actions in the complete ten-frame history with one other measured training history. "
            "The goal and labels still come from the original training reference. This auxiliary "
            "corruption trains sensitivity to the given motion; swapped observations are not "
            "physical replay. All evaluation uses the full unmodified measured history.")
    save(out/"actual_config.json",resolved)
    save(out/"u0_validation.json",scores(actor,val,mapping))
    opt=torch.optim.AdamW(actor.parameters(),lr=2e-4,weight_decay=0.,fused=True)
    lr=torch.optim.lr_scheduler.CosineAnnealingLR(opt,T_max=args.updates,eta_min=2e-6)
    # Balance physically different quantities. Scalar multiplier sets only loss scale.
    weights=tensor(mapping.scale/np.r_[np.full(12,.005),np.full(4,.10),np.full(6,.005),.0005],dev)/100
    sizes=(12,4,6,1)
    with (out/"updates.jsonl").open("x",buffering=1) as log:
        for k in range(1,args.updates+1):
            ix=torch.randint(len(h),(256,),device=dev)
            hist=h[ix].clone()
            if args.swap_arm_history:
                donor=h[torch.randint(len(h),(len(ix)//2,),device=dev)]
                # Sensor block order: gravity/omega 6, joint q 24, joint v 24,
                # previous command 23. Actuated arm + both real fingers follow M1.
                for columns in (slice(22,30),slice(46,54),slice(70,77)):
                    hist[:len(donor),:,columns] = donor[:,:,columns]
            hist[:,:,-23:] += torch.empty_like(hist[:,:,-23:]).uniform_(-.01,.01)
            raw=actor.raw(build_actor_obs_td({"motion":g[ix]},hist))
            errors=((raw-targets[ix])*weights).square()
            loss=sum(e.mean() for e in errors.split(sizes,dim=-1))/len(sizes)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(actor.parameters(),1.)
            opt.step()
            lr.step()
            if k<=3 or k%100==0 or k==args.updates:
                row=dict(update=k,loss=loss.item(),lr=lr.get_last_lr()[0])
                log.write(json.dumps(row,allow_nan=False)+"\n")
                print(json.dumps(row),flush=True)
    save(out/"final_train.json",scores(actor,teacher,mapping))
    save(out/"final_validation.json",scores(actor,val,mapping))
    checkpoint=dict(actor=actor.state_dict(),cfg=source['cfg'],seed=0,
                    supervised_updates=args.updates,source=str(args.source),variant=resolved['variant'])
    if args.warm_actor:
        checkpoint['warm_actor'] = str(args.warm_actor)
    if args.reference_residual:
        checkpoint["actor_parameterization"] = REFERENCE_RESIDUAL
    torch.save(checkpoint,out/f"actor_{args.updates:06}.pt")


def main():
    p=ArgumentParser(description=__doc__)
    p.add_argument("--run",required=True)
    p.add_argument("--updates",type=int,default=3000)
    variants=p.add_mutually_exclusive_group()
    variants.add_argument("--swap-arm-history",action="store_true",
                   help="diagnostic: corrupt arm/finger history in half of each training batch")
    variants.add_argument("--reference-residual",action="store_true",
                          help="use the given motion's current arm positions and jaw width as the baseline for seven residuals")
    p.add_argument("--references", nargs="+", help="successful measured training episode names in the given root")
    p.add_argument("--warm-actor", type=Path, help="a previous supervised reference-residual policy")
    p.add_argument("--reference-directory",type=Path,default=Path("results/raw_large/b0/contact_held_r1"))
    p.add_argument("--source",type=Path,default=Path("results/b0/free_s0_cloud_servo_r2/checkpoint_001000.pt"))
    args=p.parse_args()
    if Path(args.run).name!=args.run or args.updates<=0:
        p.error("provide a fresh run name and positive update count")
    calibrate(args)


if __name__=="__main__":
    main()
