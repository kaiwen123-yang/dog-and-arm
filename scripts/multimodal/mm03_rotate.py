"""Replace one MM03 policy server at completed-client boundaries during a checkpoint schema upgrade."""
import argparse
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import time
from uuid import uuid4

from scripts.multimodal.mm03_launch import DEFAULT, REPO, TORCH, alive, enqueue, now, pid_stamp, read, runtime_environment, write


def clients(pid, root):
    inodes=set()
    for f in Path(f"/proc/{pid}/fd").iterdir():
        try:
            endpoint=os.readlink(f)
        except FileNotFoundError:
            continue
        if endpoint.startswith("socket:["):
            inodes.add(endpoint[8:-1])
    selected=[]
    for row in Path("/proc/net/unix").read_text().splitlines()[1:]:
        f=row.split()
        if len(f)==8 and f[5]=="03" and f[6] in inodes and f[7].startswith(str(root/"service/policy")):
            selected.append(f[6])
    return selected


def wait_idle(record, root):
    while alive(record) and clients(record["pid"],root):
        time.sleep(.25)
    if alive(record):
        argv=Path(f"/proc/{record['pid']}/cmdline").read_bytes()
        if b"scripts.multimodal.mm03_inference" not in argv:
            raise RuntimeError("The recorded process is no longer an MM03 policy service")
        os.kill(record["pid"],signal.SIGTERM)


def rotate(root, reason):
    marker=root/"service/rotation.json"
    service=root/"service/serving.json"
    status=root/"status/inference.json"
    with (root/"locks/inference-rotation.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=read(marker)
        if state.get("stage")=="complete" and state.get("reason")==reason:
            return
        if not state or state.get("stage")=="complete":
            original=read(status)
            if not alive(original):
                raise RuntimeError("The primary inference process is not live")
            state=dict(id=uuid4().hex,reason=reason,stage="starting_interim",began_beijing=now(),
                       original=original,observed_original_clients=len(clients(original["pid"],root)))
            write(marker,state)
        interim=state.get("interim",{})
        if state["stage"]=="starting_interim":
            if not alive(interim):
                with (root/"logs"/f"inference-rotation-{state['id']}.log").open("ab",buffering=0) as log:
                    child=subprocess.Popen([str(TORCH),"-u","-m","scripts.multimodal.mm03_inference",
                        "--root",str(root)],cwd=REPO,env=runtime_environment(root),stdout=log,
                        stderr=subprocess.STDOUT,start_new_session=True)
                interim=dict(pid=child.pid,pid_stamp=pid_stamp(child.pid))
                state["interim"]=interim
                write(marker,state)
            while read(service).get("pid")!=interim["pid"]:
                if not alive(interim):
                    raise RuntimeError("Interim GPU server failed before it took the socket")
                time.sleep(.1)
            state.update(stage="draining_original",first_cutover_beijing=now())
            write(marker,state)
        if state["stage"]=="draining_original":
            wait_idle(state["original"],root)
            while read(status).get("state")=="running" and read(status).get("pid")==state["original"]["pid"]:
                time.sleep(.15)
            enqueue(root,"inference")
            state.update(stage="waiting_primary",original_clients_at_retirement=0)
            write(marker,state)
        if state["stage"]=="waiting_primary":
            while True:
                primary=read(status)
                if primary.get("attempt",0)>state["original"]["attempt"]:
                    if primary.get("state")=="failed":
                        raise RuntimeError("Replacement primary failed; interim continues serving new connections")
                    if alive(primary) and read(service).get("pid")==primary["pid"]:
                        break
                time.sleep(.15)
            state.update(stage="draining_interim",primary=primary,second_cutover_beijing=now())
            write(marker,state)
        wait_idle(interim,root)
        state.update(stage="complete",finished_beijing=now(),interim_clients_at_retirement=0)
        write(marker,state)
        write(root/"service/upgrades"/(state["id"]+".json"),state)
        print(now(),"MM03 policy server rotated; all clients kept their original connections",flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=DEFAULT)
    p.add_argument("--reason",required=True)
    a=p.parse_args()
    rotate(a.root,a.reason)

