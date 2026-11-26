"""Cooperative C worker handoff at a fully committed native development-matrix boundary."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid


def read(path):
    return json.loads(path.read_text())


def publish(path, value):
    tmp=path.with_name(path.name+"."+uuid.uuid4().hex+".tmp")
    tmp.write_text(json.dumps(value,indent=2)+"\n")
    tmp.replace(path)


def arm(root, variant, seed, reason):
    lane=root/"C"
    status=read(root/"status/C.json")
    if status["state"]!="running":
        raise ValueError("Only a running lane needs a cooperative handoff")
    folder=lane/variant/f"seed{seed}"
    if (folder/"development/cases.json").exists():
        raise ValueError("This development boundary has already passed; choose a later uncommitted matrix")
    record=dict(request_id=uuid.uuid4().hex,variant=variant,seed=seed,reason=reason,
                requested_utc=datetime.now(timezone.utc).isoformat(),parent_pid=status["pid"],
                parent_pid_stamp=status["pid_stamp"],old_code_commit=status["git_commit"])
    path=lane/"pending_handoff.json"
    if path.exists():
        pending=read(path)
        if all(pending[k]==record[k] for k in ("variant","seed","parent_pid","parent_pid_stamp","reason")):
            return pending
        raise ValueError(f"Different pending handoff at {path}")
    publish(path,record)
    return record


def consume(root, variant, seed):
    """Called after the last case and its cases.json are atomically complete."""
    lane=root/"C"
    path=lane/"pending_handoff.json"
    if not path.is_file():
        return False
    request=read(path)
    if (variant,seed)!=(request["variant"],request["seed"]):
        return False
    status=read(root/"status/C.json")
    if (status.get("pid"),status.get("pid_stamp"))!=(request["parent_pid"],request["parent_pid_stamp"]):
        return False
    folder=lane/variant/f"seed{seed}"
    receipt=read(folder/"receipt.json")
    cases=read(folder/"development/cases.json")
    if receipt["retained"]!=512 or len(cases)!=8 or not Path(receipt["full"]).is_file():
        raise ValueError("C handoff requires its completed optimizer and native development matrix")
    if any(row["teacher_steps"]!=0 or row["parent_tick"]!=0 for row in cases):
        raise ValueError("C handoff found an ineligible frame-zero evaluation")
    receipts=[read(p) for p in lane.glob("C*/seed*/receipt.json")]
    saved=lane/"handoffs"/(request["request_id"]+".json")
    saved.parent.mkdir(exist_ok=True)
    publish(saved,dict(request=request,completed_utc=datetime.now(timezone.utc).isoformat(),
            stage="after_eight_native_development_cases",source_full_parent=read(lane/"parent.json")["actor"],
            bridge_encoder=read(lane/"bridge/bridge.json")["encoder_id"],calibration_cap=read(lane/"calibration.json")["cap"],
            optimizer_checkpoint=receipt["full"],bc_schedule_sha=receipt["configuration"]["bc_schedule"],
            anchor_schedule_sha=receipt["anchor_schedule_sha"],
            completed_optimizer_forks=len(receipts),actor_paid=sum(r["paid"] for r in receipts),
            actor_retained=sum(r["retained"] for r in receipts),
            rollback_before_handoff=sum(r["rollback"] for r in receipts),
            target_matrix=[r["id"] for r in cases],target_physics_steps=sum(r["physics_steps"] for r in cases),
            next_pending="short recovery for this fork (unless separately completed)",
            native_child_exit=75))
    path.replace(saved.with_name(request["request_id"]+"_request.json"))
    print(f"C cooperative handoff committed to {saved}; native eval exiting 75",flush=True)
    return True


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--after",choices=["C0","C8","C32","C32G","CF32"],required=True)
    parser.add_argument("--seed",choices=[1701,1702,1703],type=int,required=True)
    parser.add_argument("--reason",required=True)
    args=parser.parse_args()
    print(json.dumps(arm(args.root,args.after,args.seed,args.reason),indent=2))
