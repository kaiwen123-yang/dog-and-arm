"""Run or resume independent native MM03 lanes and their shared inference and video services."""
import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid


REPO = Path(__file__).resolve().parents[2]
NATIVE = REPO/".venv/bin/python"
TORCH = REPO/".conda/envs/arm-and-dog/bin/python"
DEFAULT = Path("/root/autodl-tmp/mm03-20261126")
LANES = ("A", "B", "C", "video")
UNITS = ("inference", *LANES)
CST = timezone(timedelta(hours=8))


def now():
    return datetime.now(CST).isoformat(timespec="seconds")


def read(path):
    return json.loads(path.read_text()) if path.is_file() else {}


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.part")
    with tmp.open("w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def pid_stamp(pid):
    try:
        fields = Path(f"/proc/{int(pid)}/stat").read_text().rsplit(")", 1)[1].split()
        return fields[19] if fields[0] != "Z" else None
    except (FileNotFoundError, ProcessLookupError, TypeError):
        return None


def alive(record, key="pid"):
    return bool(record.get(key) and record.get(key+"_stamp")
                and pid_stamp(record[key]) == record[key+"_stamp"])


def acquire(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    lock = path.open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return None
    return lock


def state_file(root, name):
    return root/"status"/f"{name}.json"


def runtime_environment(root):
    env = dict(os.environ)
    env.pop("PYTHONHOME", None)
    env.update(PYTHONPATH=f"{REPO}:{REPO/'scripts'}", PYTHONUNBUFFERED="1",
               MUJOCO_GL="egl", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", OMP_NUM_THREADS="1",
               NUMEXPR_NUM_THREADS="1", MM03_INFERENCE_SOCKET=str(root/"service/policy.sock"))
    return env


def unit_command(name, root, config):
    mod = "scripts.multimodal."
    if name == "inference":
        return [str(TORCH), "-u", "-m", mod+"mm03_inference", "--root", str(root)]
    if name == "video":
        return [str(NATIVE), "-u", "-m", mod+"mm03_videos", "--root", str(root)]
    return [str(NATIVE), "-u", "-m", mod+"mm03_"+name.lower(), "--root", str(root),
            "--workers", str(config["workers"][name])]


def worker(root, name):
    lock = acquire(root/"locks"/(name+".lock"))
    if lock is None:
        return 0
    dest = state_file(root, name)
    previous = read(dest)
    # On a lost wrapper, an optimizer or native collector may still own its working files.
    # Its inherited lock is released by the kernel when the last owner exits.
    config = read(root/"launch_config.json")
    argv = unit_command(name, root, config)
    attempt = previous.get("attempt", 0)+1
    logpath = root/"logs"/f"{name}.attempt{attempt:03d}.log"
    record = dict(unit=name, attempt=attempt, started_beijing=now(), log=str(logpath),
                  wrapper=os.getpid(), wrapper_stamp=pid_stamp(os.getpid()), argv=argv,
                  git_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip())
    hist = root/"attempts"/name/f"{attempt:03d}.json"
    proc = None
    try:
        with logpath.open("ab",buffering=0) as log:
            proc = subprocess.Popen(argv,cwd=REPO,env=runtime_environment(root),stdout=log,stderr=subprocess.STDOUT,
                                    pass_fds=(lock.fileno(),))
            record.update(state="running",pid=proc.pid,pid_stamp=pid_stamp(proc.pid))
            write(hist,record)
            write(dest,record)
            print(now(), name, "started", proc.pid, logpath, flush=True)
            rc = proc.wait()
    except Exception as error:
        record["error"] = repr(error)
        rc = 1
    record.update(state="complete" if rc==0 else "failed", exit_code=rc, ended_beijing=now())
    write(hist,record)
    write(dest,record)
    print(now(), name, record["state"], "exit", rc, flush=True)
    return rc


def registered_parent():
    manifest = read(REPO/"results/multimodal/mm02_20261125/manifest.json")
    packages = manifest["terminal_packages"]
    for key, item in packages.items():
        if not Path(item["source"]).is_file():
            raise FileNotFoundError(f"Missing {key}: {item['source']}")
    return {key:value["source"] for key,value in packages.items()}


def enqueue(root, name):
    write(root/"requests"/f"{uuid.uuid4().hex}.json",dict(unit=name,requested_beijing=now()))


def submit(root,name):
    return subprocess.Popen([str(NATIVE),"-u","-m","scripts.multimodal.mm03_launch","unit",
                             "--root",str(root),"--unit",name],cwd=REPO,env=runtime_environment(root),
                            start_new_session=True)


def resource_sample(root):
    def cgroup(name):
        p = Path("/sys/fs/cgroup")/name
        return p.read_text().strip() if p.is_file() else None
    stats = dict(beijing=now(), time=time.time(), cpu_stat=cgroup("cpu.stat"),
                 cpu_quota=cgroup("cpu.max"), ram_bytes=cgroup("memory.current"),
                 ram_limit_bytes=cgroup("memory.max"), disk_free_bytes=os.statvfs(root).f_bavail*os.statvfs(root).f_frsize)
    try:
        stats["gpu_name_usedMiB_totalMiB_utilPC"] = subprocess.check_output(
            ["nvidia-smi","--query-gpu=name,memory.used,memory.total,utilization.gpu",
             "--format=csv,noheader,nounits"], text=True).strip()
    except (OSError, subprocess.CalledProcessError) as err:
        stats["gpu_read_error"] = str(err)
    stats["inference"] = read(root/"service/inference_stats.json")
    memo = Path("/sys/fs/cgroup/memory.stat")
    if memo.is_file():
        parts = (s.split() for s in memo.read_text().splitlines())
        stats["memory_components_bytes"] = {k:int(v) for k,v in parts if k in ("anon","file","shmem")}
    stats["lane_pids"] = {name:read(state_file(root,name)).get("pid") for name in UNITS}
    with (root/"resources.jsonl").open("a") as f:
        f.write(json.dumps(stats,separators=(",",":"))+"\n")
    return stats


def service_ready(root):
    import socket
    with socket.socket(socket.AF_UNIX) as client:
        try:
            client.connect(str(root/"service/policy.sock"))
        except OSError:
            return False
    return True


def supervise(args):
    root = args.root.resolve()
    for folder in ("locks","status","attempts","logs","requests","service"):
        (root/folder).mkdir(mode=0o700, parents=True,exist_ok=True)
    lock = acquire(root/"locks/supervisor.lock")
    if lock is None:
        for name in UNITS:
            record = read(state_file(root,name))
            if record.get("state")=="failed" or (record.get("state")=="running" and not alive(record)):
                enqueue(root,name)
        print("Active supervisor owns the queue. Failed/dead units were queued for resume.",flush=True)
        return 0
    cfg = root/"launch_config.json"
    if not cfg.exists():
        write(cfg,dict(created_beijing=now(),root=str(root),repo=str(REPO),workers=dict(A=args.a_workers,
                       B=args.b_workers,C=args.c_workers),parent=registered_parent(),
                       physical_backend="native MuJoCo 3.3.0",policy_dt_s=.02,physics_dt_s=.002,
                       camera_dt_s=.1,hardware_motion_commands=0))
    cfg_data = read(cfg)
    if cfg_data["root"] != str(root) or cfg_data["repo"]!=str(REPO):
        raise ValueError("Existing run configuration refers to another root or code checkout")
    start = dict(pid=os.getpid(),pid_stamp=pid_stamp(os.getpid()),started_beijing=now(),state="running")
    write(state_file(root,"supervisor"),start)
    children, requested = {}, set(UNITS)
    last_resource = 0.
    print(now(),"MM03 supervisor", os.getpid(),cfg_data["workers"],flush=True)
    while True:
        for name,p in list(children.items()):
            if p.poll() is not None:
                del children[name]
        for path in sorted((root/"requests").glob("*.json")):
            request = read(path)["unit"]
            if request not in UNITS:
                raise ValueError(f"Unknown unit in retry request {path}")
            requested.add(request)
            path.rename(path.with_suffix(".accepted"))
        records = {n:read(state_file(root,n)) for n in UNITS}
        ready = alive(records["inference"]) and (not requested.intersection(LANES) or service_ready(root))
        for name in UNITS:
            if name not in requested:
                continue
            rec = records[name]
            if alive(rec) or name in children or (name!="inference" and rec.get("state")=="complete"):
                requested.discard(name)
                continue
            if name not in ("inference", "video") and not ready:
                continue
            children[name]=submit(root,name)
            requested.discard(name)
        if time.monotonic()-last_resource >= 20:
            write(root/"resources/latest.json",resource_sample(root))
            last_resource=time.monotonic()
        terminal = all(records[name].get("state") in ("complete","failed") or
                       (records[name].get("state")=="running" and not alive(records[name]))
                       for name in LANES)
        service_down = (not alive(records["inference"]) and "inference" not in children
                        and records["inference"].get("state") in ("failed","complete"))
        if terminal and not children.keys() & set(LANES) and not requested.intersection(LANES):
            break
        if service_down and not any(alive(records[n]) or n in children for n in LANES):
            break
        time.sleep(2)
    # The CUDA service has no training state; release it only after all clients have left.
    service=read(state_file(root,"inference"))
    if alive(service):
        os.kill(service["pid"],signal.SIGTERM)
    if "inference" in children:
        children["inference"].wait()
    final = {name:read(state_file(root,name)).get("state","not_started") for name in LANES}
    code = int(any(v!="complete" for v in final.values()))
    write(state_file(root,"supervisor"),{**start,"state":"failed" if code else "complete",
                                         "ended_beijing":now(),"units":final,"exit_code":code})
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run","status","retry","unit"))
    parser.add_argument("--root",type=Path,default=DEFAULT)
    parser.add_argument("--unit",choices=UNITS)
    for name,value in (("a",7),("b",7),("c",4)):
        parser.add_argument(f"--{name}-workers",type=int,default=value)
    args=parser.parse_args()
    if args.action=="run":
        return supervise(args)
    if args.action=="status":
        for n in ("supervisor", *UNITS):
            data = read(state_file(args.root,n))
            print(json.dumps(dict(name=n,alive=alive(data),**data),ensure_ascii=False))
        return 0
    if not args.unit:
        parser.error("--unit is required")
    if args.action=="unit":
        return worker(args.root,args.unit)
    enqueue(args.root,args.unit)
    print("Queued",args.unit,"for the active/next supervisor")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
