"""Guard this round's already-authorized physical evaluations across SSH disconnects."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path.cwd()
STATE = HERE / "results/raw_large/b0/recovery_tmux_20261123"
MODULES = ("scripts.b0.eval_contact_segments", "scripts.b0.endpoint_targeted_rollout")


def timestamp():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")


def write_json(path, obj):
    tmp = path.with_suffix(".writing")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False)+"\n")
    tmp.replace(path)


def processes():
    found = []
    for path in Path("/proc").glob("[0-9]*"):
        try:
            if (path/"cwd").resolve() != HERE:
                continue
            argv = (path/"cmdline").read_bytes().decode().split("\0")[:-1]
            if "-m" not in argv:
                continue
            args = argv[argv.index("-m")+1:]
            if args[0] not in MODULES or "--run" not in args:
                continue
            name = args[args.index("--run")+1]
            if not name.startswith("recovery_") or Path(name).name != name:
                continue
            found.append((int(path.name), args, os.readlink(path/"fd/1")))
        except (OSError, IndexError, UnicodeError):
            continue
    return found


def make_job(args, log, pid=None, interpreter="warp"):
    def arg(key):
        return args[args.index(key)+1]
    run = arg("--run")
    base = Path("results/b0") / run
    target = args[0] == MODULES[1]
    group = ""
    if target:
        case = int(arg("--case"))
        group = f'{arg("--side")}/full/' + ("nominal" if case == 1 else f"C{case:02d}")
    goal = base/group/"policy_source.json" if target else base/"evaluation.json"
    key = run + ("/"+group if group else "")
    return dict(key=key, argv=args, log=log, original_pid=pid,
                session=os.getsid(pid) if pid else None, interpreter=interpreter,
                run=run, group=group, done=str(goal), attempts=0)


def live_members(sid):
    if sid is None:
        return False
    for entry in Path("/proc").glob("[0-9]*"):
        try:
            pid = int(entry.name)
            if os.getsid(pid) == sid:
                cmd = (entry/"cmdline").read_bytes()
                if b"multiprocessing.spawn" in cmd or b"scripts.b0.eval_contact_segments" in cmd and b"python\x00-u\x00-m\x00" in cmd:
                    return True
        except OSError:
            pass
    return False


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--native-planar",action="store_true")
    args=parser.parse_args()
    STATE.mkdir(parents=True,exist_ok=True)
    manifest=STATE/"jobs.json"
    if args.register:
        if manifest.exists():
            raise FileExistsError(manifest)
        jobs=[make_job(a,log,pid) for pid,a,log in processes()]
        if args.native_planar:
            a=[MODULES[0],"--backend","native","--device","cpu","--side","pull","push","--full-task","--video",
               "--references","results/raw_large/b0/full_warp_hold_park_r1","--run","recovery_planar_arm_native_tmux_r1",
               "--checkpoint","results/b0/recovery_planar_arm_s0_r1/checkpoint_000000.pt"]
            jobs.append(make_job(a,str(STATE/"planar_native.log"),interpreter="native"))
        write_json(manifest,dict(created=timestamp(),host=os.uname().nodename,jobs=jobs))
        print("registered",len(jobs),flush=True)
        return
    jobs=json.loads(manifest.read_text())["jobs"]
    children={}
    missing={}
    while True:
        active=processes()
        snapshot=[]
        finished=True
        for job in jobs:
            key=job["key"]
            done=Path(job["done"])
            matches=[pid for pid,a,_ in active if [v for v in a if v!="--resume"]==[v for v in job["argv"] if v!="--resume"]]
            proc=children.get(key)
            if proc is not None and proc.poll() is not None:
                children.pop(key)
            base=Path("results/b0")/job["run"]
            counts={s:len(list((base/s/"full").glob("*/result.json"))) for s in ("pull","push")}
            if done.is_file():
                try:
                    json.loads(done.read_text())
                    status="completed"
                except (ValueError,OSError):
                    status="writing"
                    finished=False
            elif matches or key in children or live_members(job["session"]):
                missing[key]=0
                status="running"
                finished=False
            elif job["attempts"] >= 2:
                status="needs_attention"
            else:
                finished=False
                missing[key]=missing.get(key,0)+1
                status="checking"
                if not job["original_pid"] or missing[key]>=2:
                    argv=list(job["argv"])
                    if job["group"]:
                        # A partial case must be preserved before the original fresh-only CLI.
                        for root in (Path("results/b0"),Path("results/raw_large/b0")):
                            case=root/job["run"]/job["group"]
                            if case.exists():
                                saved=root/job["run"]/"interrupted"/str(time.time_ns())/job["group"]
                                saved.parent.mkdir(parents=True,exist_ok=True)
                                case.rename(saved)
                    elif (base/"run_spec.json").is_file() and "--resume" not in argv:
                        argv.append("--resume")
                    prefix=([".venv/bin/python"] if job["interpreter"]=="native" else ["bash","scripts/b0/env.sh","python"])
                    logfile=STATE/(key.replace("/","_")+".log")
                    with logfile.open("a") as stream:
                        child=subprocess.Popen(prefix+["-u","-m"]+argv, stdout=stream,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
                    children[key]=child
                    job["attempts"]+=1
                    job["log"]=str(logfile)
                    status="launched"
                    missing[key]=0
                    print(timestamp(),key,status,child.pid,flush=True)
            snapshot.append(dict(job=key,status=status,pids=matches,completed_cases=counts,log=job["log"],attempts=job["attempts"]))
        state=dict(time_beijing=timestamp(),finished=finished,jobs=snapshot)
        write_json(STATE/"status.json",state)
        print(state["time_beijing"]," | ".join(f"{r['job']} {r['status']} {sum(r['completed_cases'].values())}" for r in snapshot),flush=True)
        if finished:
            write_json(STATE/"outcome.json",state)
            break
        time.sleep(30)


if __name__=="__main__":
    main()
