"""Paired imagination and native-forward objectives on the same causal task histories."""
import json
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

from .mm02_trajectory import ENCODERS, GROUP_WEIGHTS, encoder_id, frozen_dynamics, starting_observations
from .wm_replay import PhysicalReplay
from .world_model import Belief, camera_features

VARIANT_HORIZON = {"C8": 8, "C32": 32, "C32G": 32, "CF32": 32}


def eligible_recoveries(paths, split):
    complete = []
    seen = set()
    for directory in paths:
        path = Path(directory)
        meta = json.loads((path/"metadata.json").read_text())
        if meta["split"] != split or meta["source"] != "recovery":
            raise ValueError(f"{path}: wrong split or target source")
        if split == "train" and meta["scene_id"] not in ("tr_nominal", "tr_offset", "tr_load"):
            raise ValueError(f"{path}: unknown training scene")
        if np.any(np.load(path/"execution_source.npy") != 1):
            raise ValueError(f"{path}: recovery targets include student execution")
        mask = np.load(path/"valid_transition.npy")
        legal = len(mask) == 32 and bool(mask.all())
        if legal != bool(meta["horizon_complete"]):
            raise ValueError(f"{path}: inconsistent intervals")
        if legal:
            key = meta["anchor_key"]
            if key in seen:
                continue
            seen.add(key)
            snapshot = Path(meta["parent_path"]).parent/"snapshots"/f'{meta["anchor_tick"]:06d}.pkl'
            if not snapshot.is_file():
                raise FileNotFoundError(snapshot)
            complete.append((key, path, snapshot))
    return sorted(complete, key=lambda item: item[0])


def multiply_quats(q, r):
    qw, qv = q[:, :1], q[:, 1:]
    rw, rv = r[:, :1], r[:, 1:]
    return torch.cat((qw*rw-(qv*rv).sum(-1, keepdim=True),
                      qw*rv+rw*qv+torch.linalg.cross(qv,rv)), -1)


def native_value(predicted, actual):
    # The subtraction is exactly zero forward. Its gradient is the model Jacobian.
    return actual.detach() + (predicted - predicted.detach())


def project_native(predicted, real_p, obj, contact, vision, real_quat, anchor_frame):
    """Map real successor into the original initial state's gauge without reinitializing."""
    zero = torch.zeros_like(real_p[:, 46:49])
    quat = F.normalize(multiply_quats(anchor_frame, real_quat), dim=-1)
    robot = torch.cat((zero[:, :1], real_p[:, 46:49], zero, real_p[:, 49:52], real_p[:, :46]),-1)
    aux = torch.cat((zero, quat), -1)
    measured = Belief(aux, robot, obj, vision, torch.logit(contact.clamp(1e-4, 1.-1e-4)))
    return Belief(*(native_value(p, r) for p, r in zip(predicted, measured)))


def per_step(model, x, target, tick, visual_weight):
    p = model.sensor(x)
    y = target["p"][:, tick+1]
    def huber(a, b, scale):
        residual = (a-b)/scale
        return F.smooth_l1_loss(residual, torch.zeros_like(residual), reduction="none").mean(-1)
    terms = {
        "position": huber(p[:, :23], y[:, :23], .25*model.p_scale[:23]),
        "velocity": huber(p[:, 23:46], y[:, 23:46], model.p_scale[23:46]),
        "imu": huber(p[:, 46:], y[:, 46:], model.p_scale[46:]),
        "object": huber(x.obj, target["o"][:,tick+1], model.o_scale),
        "contact": F.binary_cross_entropy_with_logits(x.contact_logits, target["contact"][:,tick], reduction="none").mean(-1),
        "vision": huber(x.vision, target["vision"][:,tick+1], model.v_scale)*visual_weight,
    }
    return sum(GROUP_WEIGHTS[key]*value for key,value in terms.items())


class MM03Objective:
    def __init__(self, bundle_path, device, vocab, seed, *, split="train", directories=None, max_anchors=None):
        self.device = torch.device(device)
        config = torch.load(bundle_path, map_location=device, weights_only=False)
        if config["schema"] != "mm03_bound_trajectory_v1" or config["bridge_updates"] != 600:
            raise ValueError("Expected a complete MM03 bridge binding")
        if vocab.tokens != config["vocabulary"]:
            raise ValueError("Task vocabulary changed since the binding")
        self.model, self.bridge = frozen_dynamics(config, self.device)
        self.vocab, self.encoder = vocab, config["encoder_id"]
        members = eligible_recoveries(config["train_recovery"] if directories is None else directories, split)
        if max_anchors is not None:
            members = members[:max_anchors]
        if not members:
            raise ValueError(f"No complete teacher recovery anchors for split {split}")
        self.keys, paths, self.snapshots = zip(*members)
        self.replay = PhysicalReplay(None, split, device, episode_dirs=paths)
        self.starts = torch.tensor([ep["start"] for ep in self.replay.episodes],device=device)
        self.targets = self.replay.window(self.starts, 32)
        self.rng = torch.Generator(device=device).manual_seed(seed)
        self.obs = None

    def verify_actor(self, actor):
        if encoder_id(actor) != self.encoder:
            raise ValueError("Active encoder differs from fitted bridge")
        if any(param.requires_grad for name,param in actor.named_parameters() if name.startswith(ENCODERS)):
            raise ValueError("Frozen-encoder comparison received trainable RGB-D/text encoders")
        if self.obs is None:
            self.obs = starting_observations(actor, self.vocab, self.replay, self.starts, self.targets)

    def sample(self):
        return torch.randint(len(self.keys),(32,),generator=self.rng,device=self.device)

    def loss_for(self, actor, rows, variant, cap, native=None, *, collect=False):
        """Return the unweighted trajectory loss (apply the coefficient once in gradient_step)."""
        if self.obs is None:
            self.verify_actor(actor)
        h = VARIANT_HORIZON[variant]
        real = variant == "CF32"
        if real and native is None:
            raise ValueError("CF32 requires current native physical branches")
        obs = {k:x[rows] for k,x in self.obs.items()}
        target = {k:self.targets[k][rows] for k in ("p","o","vision","contact","fresh")}
        hist, prev, sensor = obs["history"], obs["previous"], obs["sensor"]
        z0, low0 = obs["measured"], obs["low"]
        visual, text = z0, obs["text"]
        zbridge0 = self.bridge(self.model.v_units(low0))
        state = self.model.initial(hist,prev,low0)
        hold = low0
        ids = torch.arange(len(rows),device=self.device)
        keys = rows.detach().cpu().tolist()
        frame = None
        as_float = lambda items: torch.as_tensor(np.asarray(items), dtype=torch.float32, device=self.device)
        if real:
            initial = native.reset([self.snapshots[i] for i in keys])
            meta = [initial[i] for i in range(len(rows))]
            if any(item["key"] != self.keys[row] for item,row in zip(meta, keys)):
                raise ValueError("Native snapshot identity differs from the teacher recovery")
            if (not torch.equal(as_float([m["p"] for m in meta]),hist[:,-1]) or
                not torch.equal(as_float([m["previous"] for m in meta]),prev[:,-1]) or
                not torch.allclose(as_float([m["time"] for m in meta]),sensor[:,2],atol=2e-6,rtol=0) or
                not torch.allclose(as_float([m["time"]-m["image_t"] for m in meta]),sensor[:,0],atol=2e-6,rtol=0)):
                raise ValueError("Snapshot clock, latest exposure, measured proprioception or previous action differs")
            q0 = as_float([m["q0"] for m in meta])
            frame = multiply_quats(state.aux[:,3:7], torch.cat((q0[:,:1],-q0[:,1:]),-1))
        weights = hist.new_tensor([.985**i for i in range(h)])
        fresh = target["fresh"][:,1:h+1].float()
        exposure_mass = (fresh*weights).sum(-1,keepdim=True)
        vision_weights = fresh*weights.sum()/exposure_mass.clamp_min(1e-8)
        costs = hist.new_full((len(rows),h), 0. if cap is None else float(cap))
        mask = torch.zeros_like(costs,dtype=torch.bool)
        capped = 0
        steps = calls = 0
        terminals = []
        sequences = []
        active_slots = list(range(len(rows)))
        full_order = True
        for tick in range(h):
            if not len(ids):
                break
            action = actor.act_features(visual,text,hist,prev,sensor)
            calls += len(ids)
            if real:
                ids_list = active_slots
                action_np = action.detach().cpu().numpy()
                if hasattr(native,"start_step"):
                    ticket = native.start_step(ids_list,action_np)
                    # Both successors depend on the same current action. Drain every
                    # reply even if the independent differentiable CUDA step raises.
                    try:
                        nxt = self.model.step(state,action,prev[:,-1])
                    finally:
                        replies = native.finish_step(ticket)
                else:
                    nxt = self.model.step(state,action,prev[:,-1])
                    replies = native.advance(ids_list,action_np)
                output = [replies[i] for i in ids_list]
                steps += sum(r["substeps"] for r in output)
                for slot, r in zip(ids_list,output):
                    if r["done"]:
                        terminals.append(dict(slot=slot,tick=tick+1,substeps=r["substeps"],dt=r["dt"],
                            partial_dt=r["dt"] if r["substeps"]<10 else None,
                            scored=bool(r["substeps"]==10 and r["failure"]!="nonfinite_or_solver_warning"),
                            failure=r["failure"],success=r["success"],events_advanced=r["events_advanced"],
                            time=r["time"],image_t=r["image_t"],
                            p=[float(x) if np.isfinite(x) else None for x in r["p"]],
                            object=[float(x) if np.isfinite(x) else None for x in r["o"]],
                            contact=[float(x) if np.isfinite(x) else None for x in r["contact"]]))
                valid_local = [j for j,r in enumerate(output) if r["substeps"] == 10 and
                               r["failure"] != "nonfinite_or_solver_warning"]
                if not valid_local:
                    break
                if len(valid_local)!=len(output):
                    full_order=False
                    take = torch.tensor(valid_local,device=self.device)
                    ids = ids[take]
                    nxt = Belief(*(x[take] for x in nxt))
                    hist,prev,sensor,action,hold,frame,visual,text,z0,zbridge0 = (
                        x[take] for x in (hist,prev,sensor,action,hold,frame,visual,text,z0,zbridge0))
                    output = [output[j] for j in valid_local]
                    active_slots = [ids_list[j] for j in valid_local]
                    action_np = action_np[valid_local]
                inserted = [j for j,r in enumerate(output) if r["image"] is not None]
                photos = torch.tensor(inserted,dtype=torch.long,device=self.device)
                current_z = visual.detach().clone()
                if inserted:
                    image_args = [torch.as_tensor(np.stack([output[j]["image"][k] for j in inserted]),device=self.device)
                                  for k in range(3)]
                    with torch.no_grad():
                        hold = hold.index_copy(0,photos,camera_features(*image_args))
                        current_z = current_z.index_copy(0,photos,actor.encode_visual(*image_args))
                p = as_float([r["p"] for r in output])
                nxt = project_native(nxt,p,as_float([r["o"] for r in output]),as_float([r["contact"] for r in output]),
                                     hold,as_float([r["quat"] for r in output]),frame)
                if not torch.equal(self.model.sensor(nxt).detach(),p):
                    raise ValueError("Real successor projection did not reproduce the actual 52 sensors")
                age = as_float([r["time"]-r["image_t"] for r in output])[:,None]
                clock = as_float([r["time"] for r in output])[:,None]
                fresh_mask = age.abs() < 1e-5
                if int(fresh_mask.sum()) != len(inserted):
                    raise ValueError("Native exposure timestamps and frame delivery disagree")
                estimated = z0+self.bridge(self.model.v_units(nxt.vision))-zbridge0
                visual = torch.where(fresh_mask,native_value(estimated,current_z),visual)
                if collect:
                    # Keep each actual new exposure once. Held images are recoverable from
                    # this sequence or the original anchor snapshot on the source disk.
                    fresh_images=[output[j]["image"] for j in inserted]
                    slot_array=np.asarray(active_slots,dtype=np.int64)
                    sequences.append(dict(slot=slot_array,tick=tick,
                        exposure_slots=slot_array[inserted],exposures=fresh_images,
                        exposure_times=np.asarray([output[j]["image_t"] for j in inserted],dtype=np.float64),
                        measured_features=current_z[photos].detach(),
                        action=action_np,p=p.detach(),o=nxt.obj.detach(),
                        vision=hold.detach(),contact=np.stack([r["contact"] for r in output]),
                        fresh=fresh_mask[:,0].detach(),clock=clock[:,0].detach()))
                survivors = [j for j,r in enumerate(output) if not r["done"]]
            else:
                nxt = self.model.step(state,action,prev[:,-1])
                clock = sensor[:,2:3]+.02
                ticks = torch.round(clock/.02).long()
                fresh_mask = ticks.remainder(5) == 0
                age = torch.where(fresh_mask,0.,sensor[:,0:1]+.02)
                estimated = z0+self.bridge(self.model.v_units(nxt.vision))-zbridge0
                visual = torch.where(fresh_mask,estimated,visual)
            available = target if real and full_order else {key: val[ids] for key,val in target.items()}
            cost = per_step(self.model,nxt,available,tick,vision_weights[ids,tick])
            if cap is not None:
                capped = capped+(cost.detach()>cap).sum()
                cost = cost.clamp_max(cap)
            costs[:,tick] = costs[:,tick].index_copy(0,ids,cost)
            mask[ids,tick] = True
            hist = torch.cat((hist[:,1:],self.model.sensor(nxt)[:,None]),1)
            prev = torch.cat((prev[:,1:],action[:,None]),1)
            valid = torch.where(fresh_mask,1.,sensor[:,1:2])
            sensor = torch.cat((age*valid,valid,clock),1)
            state = nxt
            if real and len(survivors)!=len(active_slots):
                full_order=False
                active_slots=[active_slots[j] for j in survivors]
                keep=torch.tensor(survivors,dtype=torch.long,device=self.device)
                ids,hist,prev,sensor,hold,frame,visual,text,z0,zbridge0 = (
                    x[keep] for x in (ids,hist,prev,sensor,hold,frame,visual,text,z0,zbridge0))
                state = Belief(*(x[keep] for x in state))
        loss = (costs*weights).sum(-1).div(weights.sum()).mean()
        if sequences:
            # Replay storage is outside the gradient graph. Consolidate many small
            # GPU-to-host transfers without changing each interval's dtype or shape.
            for key in ("measured_features","p","o","vision","fresh","clock"):
                blocks=[s[key] for s in sequences]
                combined=torch.cat(blocks,dim=0).cpu().numpy()
                offset=0
                for s,block in zip(sequences,blocks,strict=True):
                    end=offset+len(block)
                    s[key]=combined[offset:end]
                    offset=end
        stats = dict(valid=mask, per_step=costs.detach(), native_substeps=steps, model_queries=calls,
                     capped=capped, terminals=terminals, sequences=sequences)
        return loss,stats

    @torch.no_grad()
    def calibrate(self, actor):
        self.verify_actor(actor)
        selected = list(range(min(256,len(self.keys))))
        errors = []
        for start in range(0,len(selected),32):
            rows = torch.tensor(selected[start:start+32],device=self.device)
            _,stats = self.loss_for(actor,rows,"C32",None)
            errors.append(stats["per_step"].flatten())
        values = torch.cat(errors)
        q = float(torch.quantile(values,.999))
        if not np.isfinite(q):
            raise FloatingPointError("Nonfinite parent Cmax calibration")
        return max(1.,2*q),dict(quantile_999=q, steps=values.numel(), anchor_keys=[self.keys[i] for i in selected],
                               source="sorted complete training recoveries, frozen parent imagination H32")


def gradient_step(loss_bc, loss_traj, variant, optimizer, groups, limits):
    """Separate gradients before clipping; preserve the parent's optimizer groups and moments."""
    groups = [[p for p in g if p.requires_grad] for g in groups]
    params = [p for g in groups for p in g]
    before = [p.detach().clone() for p in params]
    grad_bc = torch.autograd.grad(loss_bc,params,allow_unused=True)
    has_graph = loss_traj is not None and loss_traj.requires_grad
    grad_traj = (torch.autograd.grad(loss_traj,params,allow_unused=True) if has_graph else [None]*len(params))
    zero = loss_bc.detach().new_zeros(())
    def norm(grads):
        return sum((g.detach().square().sum() for g in grads if g is not None),zero).sqrt()
    bn,tn = norm(grad_bc),norm(grad_traj)
    dot = sum(((a.detach()*b.detach()).sum() for a,b in zip(grad_bc,grad_traj)
               if a is not None and b is not None),zero)
    weight = zero if not has_graph else zero+.15
    if variant == "C32G":
        weight = torch.minimum(weight, .25*bn/(tn+1e-12)).detach()
    optimizer.zero_grad(set_to_none=True)
    for p,b,t in zip(params,grad_bc,grad_traj):
        if b is not None or t is not None:
            p.grad = ((b.detach() if b is not None else 0.) +
                      (weight*t.detach() if t is not None else 0.))
    pre,post = [],[]
    for group,limit in zip(groups,limits,strict=True):
        if group:
            pre.append(float(torch.nn.utils.clip_grad_norm_(group,limit,error_if_nonfinite=True)))
            post.append(float(norm([p.grad for p in group])))
    optimizer.step()
    with torch.no_grad():
        delta = norm([p-v for p,v in zip(params,before)])
    return dict(bc=float(loss_bc.detach()), trajectory=None if loss_traj is None else float(loss_traj.detach()),
                grad_bc=float(bn),grad_trajectory=float(tn),gradient_cosine=float(dot/(bn*tn).clamp_min(1e-12))
                if float(bn*tn)>0 else None, coefficient=float(weight),preclip_by_group=pre,
                postclip_by_group=post,actual_adam_delta_l2=float(delta))
