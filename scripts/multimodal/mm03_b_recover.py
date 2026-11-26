"""Reconstitute one paid CF32 update from its exact prior Adam state and verified native tape."""
import argparse
from copy import deepcopy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pickle
import time

import numpy as np
import torch

from learning.multimodal.mm03_task import load_task_actor, optimizer_for
from learning.multimodal.mm03_task_data import SharedRows
from learning.multimodal.mm03_model import MM03Objective, gradient_step
from scripts.multimodal.mm03_b import emit, read
from scripts.multimodal.mm03_b_train import restore_rng,global_rng
from scripts.multimodal.mm03_c_train import record_replay
from scripts.multimodal.mm03_cf_timing import Tape
from scripts.multimodal.mm03_launch import now,pid_stamp
from scripts.multimodal.train_actor import atomic_save

DEVICE=torch.device("cuda:0")


def digest_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition,message):
    if not condition:
        raise ValueError(message)


def narrow_batch(spec,vocabulary,step):
    """Gather the same frozen row indices; materialize only episodes used by this one batch."""
    manifest=read(spec["members"])
    schedule=np.load(spec["schedule"],mmap_mode="r")
    schedule_meta=read(Path(spec["schedule"]).with_suffix(".json"))
    directories=list(dict.fromkeys(manifest["teachers"]+manifest["corrections"]))
    require(directories==schedule_meta["paths"],"Original BC order directory mapping changed")
    original=np.asarray(schedule[spec["offset"]+step-1],dtype=np.int64)
    lengths=[]
    for name in directories:
        path=Path(name)
        count=read(path/"metadata.json")["transitions"]+1
        prefix=path/"history_prefix_proprio.npy"
        if prefix.exists():
            count+=len(np.load(prefix,mmap_mode="r"))
        lengths.append(count)
    offsets=np.r_[0,np.cumsum(lengths)]
    owners=np.searchsorted(offsets,original,side="right")-1
    eligible=set(directories[i] for i in owners)
    sub={k:[p for p in manifest[k] if p in eligible] for k in ("teachers","corrections")}
    pool=SharedRows(sub,vocabulary,DEVICE)
    local={str(p):j for j,(p,_) in enumerate(pool.data.episodes)}
    indices=np.array([pool.data.history_starts[local[directories[owner]]]+at-offsets[owner]
                      for owner,at in zip(owners,original,strict=True)])
    return pool.batch(indices),original,schedule_meta


class ExactCapture:
    def __init__(self,native,receipt,source):
        self.native=native
        self.receipt=receipt
        self.source=source
        self.ticks=[]
        self.steps=0
        self.expected={}
        for i,(tick,slot) in enumerate(zip(source["tick"],source["slot"],strict=True)):
            self.expected[int(tick),int(slot)]=source["action"][i]
        self.quaternions=[]
        self.paths=[]
        self.initial={}

    def reset(self,paths):
        self.paths=list(map(str,paths))
        self.initial=self.native.reset(paths)
        return self.initial

    def start_step(self,slots,actions):
        tick=len(self.ticks)
        require(all((tick,s) in self.expected for s in slots),
                "Recovery needs the paid command of every active slot, including terminal slots")
        issued=np.stack([self.expected[tick,s] for s in slots])
        require(np.array_equal(actions,issued),f"Current policy differs from archived action at decision {tick}")
        return self.native.start_step(slots,issued),tuple(slots),issued

    def finish_step(self,ticket):
        command,slots,issued=ticket
        replies=self.native.finish_step(command)
        self.steps+=sum(row["substeps"] for row in replies.values())
        require(self.steps<=self.receipt["native_substeps"],"Recovery exceeded the original native duration")
        self.ticks.append((slots,issued.copy(),replies))
        return replies


def verify_archives(original, rebuilt):
    checks={}
    with np.load(original,allow_pickle=False) as ref, np.load(rebuilt,allow_pickle=False) as new:
        require(set(ref.files)==set(new.files),"Native archive fields differ")
        for key in ref.files:
            a,b=ref[key],new[key]
            checks[key]=bool(a.shape==b.shape and a.dtype==b.dtype and a.tobytes()==b.tobytes())
    require(all(checks.values()),"Paid archive fields differ: "+str([k for k,v in checks.items() if not v]))
    return checks


def execute(root,seed,round_id):
    from scripts.multimodal.mm03_c_native import NativePool
    out=root/"B"/"rounds"/f"r{round_id:02d}"/"H9-WM"/f"seed{seed}"/"paired"
    recovery=out/"recovery_after_sigkill"
    recovery.mkdir(exist_ok=True)
    spec=read(out/"spec.json")
    require(spec["stage"]=="paired" and spec["variant"]=="CF32","Not a CF32 paired stage")
    if (recovery/"reconstruction.json").exists():
        result=read(recovery/"reconstruction.json")
        require(digest_file(result["checkpoint2"])==result["reconstructed_sha256"] and
                digest_file(result["original_checkpoint"])==result["source_sha256"],
                "The two immutable recovery checkpoints must match the retained receipt")
        return result
    guard=read(recovery/"guard.json")
    require(guard.get("pid_stamp") and pid_stamp(guard.get("pid"))==guard["pid_stamp"] and guard.get("state")=="holding",
            "A verified stage-owner recovery lock is required before modifying the checkpoint")
    journal=out/"applied.jsonl"
    journal_bytes=journal.read_bytes()
    records=[json.loads(s) for s in journal_bytes.splitlines()]
    require(len(records)==2 and [x["update"] for x in records]==[1,2],"Expected exactly two original paid applications")
    original=recovery/"step1_original.pt"
    if not original.exists():
        os.link(out/"last.pt",original)
    original_journal=recovery/"original_applied_1_2.jsonl"
    if not original_journal.exists():
        with original_journal.open("xb") as f:f.write(journal_bytes)
    require(original_journal.read_bytes()==journal_bytes,"Paid application ledger changed")
    saved_sha=digest_file(original)
    require(digest_file(out/"last.pt")==saved_sha,"The active checkpoint is no longer the original recovery source")
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision("high")
    torch.cuda.set_device(DEVICE)
    actor,vocab,saved=load_task_actor(original,DEVICE)
    require(saved["update"]==1 and saved["next_schedule_row"]==spec["offset"]+1,"Wrong prior state")
    actor.set_encoder_grad(False)
    actor.low.requires_grad_(False).eval()
    optimizer,names=optimizer_for(actor)
    require(names==saved["optimizer_names"],"Adam parameter names changed")
    optimizer.load_state_dict(saved["optimizer"])
    batch,batch_rows,order=narrow_batch(spec,vocab,2)
    require(saved["row_order"]==order["batch_rows_sha256"],"Frozen BC order changed")
    obj=MM03Objective(spec["bundle"],DEVICE,vocab,seed+937*round_id)
    obj.verify_actor(actor)
    cap=read(out/"fixed_cap.json")["cap"]
    restore_rng(saved["rng"])
    obj.rng.set_state(saved["objective_rng"].cpu())
    indices=obj.sample()
    committed=records[1]; path=Path(committed["shared_native_replay"])
    with np.load(path,allow_pickle=False) as raw:
        fields={k:raw[k] for k in ("tick","slot","action","rows","keys")}
    require(np.array_equal(indices.cpu().numpy(),fields["rows"]),"Recovered model sampler rows differ")
    require(list(fields["keys"])==[obj.keys[i] for i in indices.cpu().tolist()],"Recovered training anchors differ")
    require(committed["native_substeps"]==10*committed["legal"],"Unarchived partial action cannot be silently filled")
    bc=actor.bc_loss(batch)
    require(float(bc.detach())==committed["bc"],"Reconstructed BC minibatch or inherited actor differs before native work")
    groups=[[p for p in g["params"] if p.requires_grad] for g in optimizer.param_groups]
    tape_path=recovery/"original_step2_native_tape.pkl"
    phys_file=recovery/"physical_recovery.json"
    native=None
    capture=None
    cost=0
    began=time.monotonic()
    reused=tape_path.exists()
    if reused:
        with tape_path.open("rb") as f:tape=Tape(pickle.load(f))
    else:
        require(not phys_file.exists(),"An existing incomplete physical audit must be reviewed before another solve")
        # Use exactly one native worker; this repair is accounted separately from the 3x6/7/8 study.
        os.environ["MM03_UNIT"]="recovery"
        native=NativePool(1)
        capture=ExactCapture(native,committed,fields)
        tape=capture
    try:
        traj,stats=obj.loss_for(actor,indices,"CF32",cap,native=tape,collect=True)
    finally:
        if native is not None:
            try:
                native.close()
            finally:
                cost=capture.steps
                complete=(cost==committed["native_substeps"] and len(capture.ticks)==32)
                write_path=tape_path if complete else recovery/"partial_native_tape.pkl"
                temp=write_path.with_suffix(".part")
                with temp.open("wb") as f:pickle.dump(dict(paths=capture.paths,initial=capture.initial,ticks=capture.ticks),f,protocol=5)
                os.replace(temp,write_path)
                emit(phys_file,dict(native_workers=1,native_substeps=cost,decision_boundaries=len(capture.ticks),
                     complete=complete,original_native_substeps=committed["native_substeps"],host_pid=os.getpid(),
                     source=str(path),tape=str(write_path),scope="deterministic paid-step recovery; no new on-policy training data"))
    require(stats["native_substeps"]==committed["native_substeps"] and stats["model_queries"]==committed["model_queries"],
            "Recovered physical cost differs")
    rebuilt=record_replay(recovery/"regenerated_archive",1,2,list(fields["keys"]),indices,stats,obj)
    checked=verify_archives(path,rebuilt)
    require(float(traj.detach())==committed["trajectory"],"Trajectory objective differs")
    measures=gradient_step(bc,traj,"CF32",optimizer,groups,[2.]*len(groups))
    unmatched={k:(v,committed.get(k)) for k,v in measures.items() if v!=committed.get(k)}
    emit(recovery/"gradient_comparison.json",dict(complete=not unmatched,all_metrics=measures,
         different=unmatched,archive_fields=checked,bc_rows_sha256=hashlib.sha256(batch_rows.astype("<i8").tobytes()).hexdigest()))
    require(not unmatched,"A saved gradient/Adam diagnostic differs; retaining checkpoint 1")
    original_totals=dict(saved["totals"])
    additions=dict(model_updates=int(committed["legal"]>0),model_queries=committed["model_queries"],
        native_substeps=committed["native_substeps"],legal_model_slots=committed["legal"],
        command_label_draws=committed["command_draws"],bc_rows=len(batch_rows))
    saved.update(actor=actor.state_dict(),optimizer=optimizer.state_dict(),rng=global_rng(),objective_rng=obj.rng.get_state(),
        update=2,next_schedule_row=spec["offset"]+2,totals={k:v+additions[k] for k,v in original_totals.items()},
        recovery_provenance=dict(original_checkpoint_sha=saved_sha,checked_archive=digest_file(path),
           original_ledger_sha256=hashlib.sha256(journal_bytes).hexdigest(),original_step2_already_paid=True))
    # The already committed ledger is retained byte-for-byte. No new applied row is appended.
    require(journal.read_bytes()==journal_bytes and digest_file(out/"last.pt")==saved_sha,"Recovery ownership changed")
    dst=recovery/"step2_reconstructed.pt"
    atomic_save(dst,saved)
    verification=torch.load(dst,map_location="cpu",weights_only=False)
    require(verification["update"]==2 and verification["next_schedule_row"]==2050,"Serialized recovery checkpoint invalid")
    for name,tensor in actor.state_dict().items():
        require(torch.equal(tensor.detach().cpu(),verification["actor"][name]),"Serialized recovered actor changed")
    for pid,state in optimizer.state_dict()["state"].items():
        for k,value in state.items():
            if torch.is_tensor(value):
                require(torch.equal(value.detach().cpu(),verification["optimizer"]["state"][pid][k]),"Serialized Adam moment changed")
    tmp=out/"last.recovery-link"
    if tmp.exists():
        require(os.path.samefile(tmp,dst),"Unexpected recovery link")
    else:os.link(dst,tmp)
    os.replace(tmp,out/"last.pt")
    elapsed=time.monotonic()-began
    result=dict(at=now(),original_checkpoint=str(original),source_sha256=saved_sha,
        checkpoint2=str(dst),reconstructed_sha256=digest_file(dst),ledger_sha256=hashlib.sha256(journal_bytes).hexdigest(),
        reconstructed_step=2,original_paid_rows=2,retained_distinct_updates=2,unchanged_original_ledger=True,
        missing_original_field="root quaternion at each actual successor",archive_fields=checked,
        exact_original_actions=committed["legal"],exact_logged_metrics=list(measures),native_restore_substeps=read(phys_file)["native_substeps"],
        replay_cached_this_execution=reused,restore_forward_backward_adam=1,additional_distinct_updates=0,
        additional_training_rows=0,wall_s=elapsed,original_step2_wall_clock_not_recovered=True)
    emit(recovery/"reconstruction.json",result)
    emit(out/"progress.json",dict(stage="paired",method="H9-WM",seed=seed,step=2,steps=512,paid=2,loss=committed["bc"],
                                  recovery=str(recovery/"reconstruction.json"),**saved["totals"]))
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--seed",type=int,required=True)
    p.add_argument("--round",type=int,required=True)
    args=p.parse_args()
    dest=args.root/"B"/"rounds"/f"r{args.round:02d}"/"H9-WM"/f"seed{args.seed}"/"paired"/"recovery_after_sigkill"
    with (dest/"reconstruction.lock").open("a") as gate:
        fcntl.flock(gate,fcntl.LOCK_EX|fcntl.LOCK_NB)
        print(json.dumps(execute(args.root,args.seed,args.round)),flush=True)

