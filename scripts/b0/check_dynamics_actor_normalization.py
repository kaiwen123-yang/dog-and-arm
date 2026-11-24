"""Recompute the Actor input statistics from the pilot's real online samples and RNG."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from supermimic.tasks.task_spec import build_actor_obs_td
from scripts.b0.dynamics_h32_pilot import ARMS, DEVICE, OUT, RAW, SHARED, build, load_common, read, write
from scripts.b0.dynamics_h32_probe import assert_draws, observed_draws


def diffs(left,right):
    return {k:float((left[k].double()-right[k].double()).abs().max()) for k in left}


def norm_state(module):
    return {k:v.detach().clone() for k,v in module.state_dict().items()}


def merge64(stats,x):
    batch=x.double()
    n=int(stats["count"])
    m=batch.size(0)
    mu=stats["_mean"].double()
    var=stats["_var"].double()
    delta=batch.mean(0,keepdim=True)-mu
    rate=m/(n+m)
    mean=mu+rate*delta
    var=(1.-rate)*var+rate*batch.var(0,unbiased=False,keepdim=True)+rate*(1.-rate)*delta.square()
    return {"count":stats["count"].new_tensor(n+m),"_mean":mean,"_var":var,"_std":var.sqrt()}


def noise_draws(n):
    # reset warm-start 9 historical sensors + current. Each of the 32 simulated
    # successors draws one new noisy sensor. Only reproduce random-number consumption.
    torch.rand(n,9,77,device=DEVICE)
    for _ in range(33):
        torch.rand(n,77,device=DEVICE)
    torch.randperm(32*n,device=DEVICE)


@torch.no_grad()
def main(arm):
    run=build(arm)
    load_common(run)
    out=OUT/"h32"/arm
    raw=RAW/"h32"/arm
    finish=torch.load(raw/"cohort_state.pt",weights_only=False,map_location=DEVICE)
    chunks=finish["replay"]
    initial=torch.load(run.cfg["actor_checkpoint"],weights_only=False,map_location=DEVICE)["actor"]
    actual=finish["actor"]
    weight0=torch.load(raw/"checkpoint_000000.pt",weights_only=False,map_location=DEVICE)["actor"]
    weight1=torch.load(raw/"checkpoint_000001.pt",weights_only=False,map_location=DEVICE)["actor"]
    final_policy=torch.load(raw/"checkpoint_000010.pt",weights_only=False,map_location=DEVICE)["actor"]
    final_saved_exact=(actual.keys()==final_policy.keys() and all(torch.equal(x,final_policy[k]) for k,x in actual.items()))
    if not final_saved_exact:raise ValueError("u10 policy and complete restart Actor/normalizers disagree")
    groups={"history":("obs_normalizer.",run.actor.obs_normalizer),
            "goal":("goal_normalizers.motion.",run.actor.goal_normalizers["motion"])}
    evidence={}
    fp64={}
    for name,(prefix,module) in groups.items():
        state=norm_state(module)
        for k,v in state.items():
            if not (torch.equal(initial[prefix+k],v) and torch.equal(weight0[prefix+k],v) and torch.equal(weight1[prefix+k],v)):
                raise ValueError(f"{name} initialization not retained in u0 and u1")
        fp64[name]=state
        evidence[name]=dict(shape=list(state["_mean"].shape),initial_count=int(state["count"]),
             initial_variance_min=float(state["_var"].min()),initial_std_min=float(state["_std"].min()),
             eps=module.eps,until=module.until)
    run.actor.train()
    first_actual=None
    cohort_replayed=1
    prev_episode=np.load(SHARED/"lanes_000001.npz")["episode"][-1]
    valid_after=0
    replayed_noise=True
    draw_mismatches=[]
    updates=[json.loads(x) for x in (out/"updates.jsonl").read_text().splitlines()]
    moments={k:[] for k in groups}
    for step,entry in enumerate(updates,1):
        needed=entry["ratio"]["cohorts"]
        while cohort_replayed<needed:
            idx=cohort_replayed
            block=idx+1
            td,starts=chunks[idx]
            with np.load(raw/f"lanes_{block:06}.npz") as d:
                valid=d["valid"]
                time_count=len(valid)
                offset=td.batch_size[1]-time_count
                if offset!=6:raise ValueError("Missing retained six-row overlap")
                for tick in range(time_count):
                    nreset=int((d["episode"][tick]!=prev_episode).sum())
                    prev_episode=d["episode"][tick]
                    if nreset:
                        # The categorical input has the identical support/shape; saved physical
                        # trajectories supply the real resulting frames. The output is discarded.
                        run.sampler.sample(nreset)
                    t=tick+offset
                    h=td["history"][:,t].reshape(run.n,10,77).clone()
                    clean=h[:,-1].contiguous()
                    noisy=run.robot.add_proprio_noise(clean)
                    torch.randn(run.n,23,device=DEVICE)    # collection exploration after the sensor noise
                    valid_tick=torch.as_tensor(valid[tick],device=DEVICE)
                    if not valid_tick.any():continue
                    frame=td["motion_time"][:,t].contiguous()
                    state=td["state"][:,t].contiguous()
                    np.testing.assert_array_equal(frame.cpu().numpy(),d["frame"][tick])
                    _,goal=run.bank.goals(run.rep,frame,state[:,:7],state[:,61])
                    h[:,-1]=noisy
                    latest={"history":noisy[valid_tick],"goal":goal[valid_tick]}
                    for name, x in latest.items():
                        fp64[name]=merge64(fp64[name],x)
                        moments[name].append(x.cpu())
                    run.actor.update_normalization(build_actor_obs_td({"motion":goal},h)[valid_tick])
                    if first_actual is None:
                        first_actual={name:dict(samples=int(valid_tick.sum()),max_abs_fp32_vs_independent_fp64=diffs(norm_state(groups[name][1]),fp64[name])) for name in groups}
                    valid_after+=int(valid_tick.sum())
            run.replay.chunks.append((td,starts))
            run.replay.index.clear()
            cohort_replayed=block
        before=len(run.registered_wm.rows)
        with observed_draws(run) as draws:
            for d,h in enumerate([7]*8+[1,1]):
                run.registered_wm.draw(h,(step-1)*10+d,run.b,run.replay)
            run.policy.wm_env.sample_initial_states()
        del run.registered_wm.rows[before:]
        with np.load(out/f"draws_u{step:02}.npz") as z:
            try:
                assert_draws(draws,dict(z))
            except (ValueError,AssertionError):
                replayed_noise=False
                draw_mismatches.append(step)
        noise_draws(run.cfg["actor_batch"])
    target_rng=finish["gpu_rng"].cpu()
    merged={}
    for name,(prefix,module) in groups.items():
        goal={k:actual[prefix+k] for k in module.state_dict()}
        values=norm_state(module)
        x=torch.cat(moments[name])
        source=weight0
        base={k:source[prefix+k] for k in values}
        init=base["_std"].cpu().clamp_min(1e-30)
        pooled=merge64(base,x.to(DEVICE))
        spread=x.std(0,unbiased=False)
        val=actual[prefix+"_std"].cpu()
        merged[name]=dict(**evidence[name],final_count=int(goal["count"]),new_samples=len(x),
            actual_fp32_vs_checkpoint=diffs(values,goal),independent_fp64_vs_checkpoint=diffs(fp64[name],goal),
            pooled_fp64_vs_checkpoint=diffs(pooled,goal), source_observation_range=[float(x.min()),float(x.max())],
            incoming_std_max=float(spread.max()),max_final_std=float(val.max()),
            largest_updated_scale_ratio=float(((val+module.eps)/(init+module.eps)).max()))
    newobs=[];newgoal=[]
    for row in read(run.cfg["wm_data_recipe"]["sources"]["response"]["registration"])["starts"]:
        folder=Path(run.cfg["wm_data_recipe"]["sources"]["response"]["raw"])/row["id"]
        if row["split"]=="validation" and not read(folder/"receipt.json").get("rejected"):
            with np.load(folder/"start.npz") as z:
                newobs.append(torch.as_tensor(z["history"],device=DEVICE))
                newgoal.append(torch.as_tensor(z["goal"],device=DEVICE))
    held={}
    for stage,params in (("u0",weight0),("u10",actual)):
        run.actor.load_state_dict(params)
        run.actor.eval()
        held[stage]={}
        for name,inp in (("history",newobs),("goal",newgoal)):
            module=groups[name][1]
            x=module(torch.cat(inp)).abs().cpu().numpy()
            held[stage][name]=dict(p95=float(np.percentile(x,95)),max=float(x.max()))
    result=dict(arm=arm,initial_count_and_all_buffers_match_free_u0_u1=True,valid_after=valid_after,
        all_final_checkpoint_and_recovery_actor_tensors_exact=final_saved_exact,actual_final_tensor_count=len(actual),
        actual_wm_and_actor_indices_reproduced_at=list(range(1,11)) if replayed_noise else [i for i in range(1,11) if i not in draw_mismatches],
        rng_final_equal=torch.equal(torch.cuda.get_rng_state(),target_rng),first_batch=first_actual,
        history_and_goals=merged,held_validation_abs_z=held,additional_h32_forwards=0,updates=0,
        method="original physical rows, frames and histories in actual per-tick original lane order, prior slot actuation and seeded stochastic sensor; only RNG advancement through intervening training",
        units="77 = gravity direction3, angular velocity3 rad/s, home-relative joint positions24 (radians/finger metres), joint speeds24, last clipped canonical actions23; 540 = ten future 24 position+24 speed reference blocks plus ten relative anchor rotations in 6D",
        normalized_rows="only last observation (each of 10 frame history still normalized in forward); exactly one update per valid 20ms row",
        persisted="empirical count/mean/population variance/std are persistent buffers of both checkpoints and complete recovery; eps=0.01, exact forward (x-mean)/(std+eps)")
    if not replayed_noise or not result["rng_final_equal"] or merged["history"]["actual_fp32_vs_checkpoint"] != {k:0. for k in fp64["history"]}:
        raise ValueError("The exact recorded sensor RNG sequence or observed normalization replay changed")
    if any(abs(v)>1e-8 for v in merged["goal"]["actual_fp32_vs_checkpoint"].values()):
        raise ValueError("Rebuilt physical goal inputs change the saved statistics beyond FP32 roundoff")
    write(out/"normalization_replay.json",result)
    print(arm,valid_after,draw_mismatches,result["rng_final_equal"],merged["history"]["actual_fp32_vs_checkpoint"],merged["goal"]["actual_fp32_vs_checkpoint"],flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("arm",choices=ARMS)
    main(p.parse_args().arm)
