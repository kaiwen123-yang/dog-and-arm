"""Execute the pre-registered RefXY2 pair, charging actual optimizer components."""
import argparse
from contextlib import nullcontext
import fcntl
import json
import math
from pathlib import Path
import time
import torch
from scripts.b0 import refxy2_state as state
from scripts.b0.refxy2_first_update import first_collection, first_update

io = state.io
MAIN = dict(actor=420, wm=4200, critic=8400)
EXTENDED = dict(actor=2020, wm=20200, critic=40400)
CYCLE = dict(actor=1, wm=10, critic=20)
RESERVE = dict(actor=20, wm=200, critic=400)


def difference(high, low):
    return {k:high[k]-low[k] for k in CYCLE}


def paid_total():
    rows = state.LIGHT/"optimizer_cost.jsonl"
    totals=dict.fromkeys(CYCLE,0)
    if rows.is_file():
        for line in rows.read_text().splitlines():
            for key,value in json.loads(line)["cost"].items():
                assert value >= 0
                totals[key]+=value
    return totals


def train(mode, stop):
    if stop not in (200,500,1000):
        raise ValueError(stop)
    if stop>200 and not io.read(state.LIGHT/"extension_decision.json")["extend"]:
        raise ValueError("Joint extension decision required")
    limit=MAIN if stop==200 else EXTENDED
    light=state.LIGHT/mode
    raw=state.RAW/mode
    nodes=sorted(light.glob("node_*.json"))
    u=int(nodes[-1].stem.split("_")[-1])
    if u>=stop:
        return
    run,info=state.flow.build(state.config(mode))
    run.log_physical_dual=True
    current=state.restore(run,mode,u)
    io.write(light/f"restored_{u:06}.json",dict(node=current,device=info["device"],statistics=state.flow.stats(run),
        steps=io.optimizer_steps(run),clock=run.replay.clock,sampler_fields=list(run.sampler.state_dict()),
        lane_fields=list(run.lanes), replay_pages=len(run.replay.pages), ratio=run.schedule.state_dict()))
    parent=io.read(state.PARENT)
    paid=paid_total()
    spent_retained = sum(max(int(f.stem.split("_")[-1]) for f in (state.LIGHT/m).glob("node_*.json")) for m in state.METHOD)
    rollback={k:paid[k]-spent_retained*CYCLE[k] for k in CYCLE}
    assert all(0<=rollback[k]<=RESERVE[k] for k in CYCLE),rollback
    # Reduce interval after a failed segment, including separately charged partial WM or critic work.
    interval=min(10,*( (RESERVE[k]-rollback[k])//CYCLE[k] for k in CYCLE))
    target_save_spacing=max(1,interval)
    session=time.time_ns()
    pending=state.LIGHT/"inflight.json"
    if pending.exists():
        raise RuntimeError("Unclosed component accounting record: "+str(pending))
    io.append(light/"sessions.jsonl",dict(started_ns=session, from_node=u, stop=stop, charged_before=paid,
        rollback_at_restore=rollback, interval=target_save_spacing))
    first_tick=(u==0)
    while u<stop:
        if not run.schedule.pending:
            with (first_collection(run,light,raw) if first_tick else nullcontext()):
                report=run.collect()
            first_tick=False
            io.append(light/"collection.jsonl",dict(session=session,clock=run.replay.clock,valid=run.total,
                ratio=run.schedule.state_dict(),**report))
            continue
        run.schedule.pending -= 1
        if not len(run.replay.positions(7)[1]):
            io.append(light/"readiness.jsonl",dict(clock=run.replay.clock,skipped=1))
            continue
        if any(paid[k]+CYCLE[k]>limit[k] for k in CYCLE):
            raise RuntimeError("Component budget exhausted")
        before=io.optimizer_steps(run)
        intent=dict(mode=mode,session=session,attempt=u+1,from_node=current["update"],before=before,
                    from_clock=current["clock"],clock=run.replay.clock)
        io.write(pending,intent)
        try:
            with (first_update(run,light,raw) if u==0 else nullcontext()):
                wm=run.learners[7].update(run.replay.windows(7,run.b) for _ in range(10))
                if not torch.stack(list(wm.values())).isfinite().all():
                    raise FloatingPointError("Nonfinite WM update")
                policy=run.policy.update()
            metrics={k:float(v) for k,v in (wm|policy).items()}
            if not all(map(math.isfinite,metrics.values())):
                raise FloatingPointError(str(metrics))
            after=io.optimizer_steps(run)
            assert difference(after,before)==CYCLE, (before,after)
        except BaseException as e:
            after=io.optimizer_steps(run)
            io.append(state.LIGHT/"optimizer_cost.jsonl",intent|dict(cost=difference(after,before),after=after,error=repr(e)))
            pending.unlink()
            raise
        cost=difference(after,before)
        io.append(state.LIGHT/"optimizer_cost.jsonl",intent|dict(cost=cost,after=after))
        pending.unlink()
        paid={k:paid[k]+cost[k] for k in CYCLE}
        u+=1
        assert difference(after,parent["steps"])=={k:CYCLE[k]*u for k in CYCLE}
        io.append(light/"updates.jsonl",dict(update=u,session=session,tick=run.replay.clock,valid=run.total,
            simulated=run.simulated,statistics=state.flow.stats(run),metrics=metrics,steps=after,ratio=run.schedule.state_dict()))
        if u in (1,10,50,100,200,500,1000) or u-current["update"]>=target_save_spacing or u==stop:
            current=state.save(run,mode,u,current)
            print(mode,u,current["valid"],paid,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=state.METHOD)
    parser.add_argument("stop",type=int)
    args=parser.parse_args()
    with (state.LIGHT/"pair.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        train(args.mode,args.stop)
