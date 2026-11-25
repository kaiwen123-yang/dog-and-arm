"""Publish the first student video and the frozen MM-02 results using ordinary main pushes."""
import argparse
import base64
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

SLUG="kaiwen123-yang/dog-and-arm"
REMOTE=f"https://github.com/{SLUG}.git"
RESULT=Path("results/multimodal/mm02_20261125")


def shell(cwd,args):
    return subprocess.check_output(args,cwd=cwd,text=True).strip()


def git(repo,*args):
    return shell(repo,["git","-c","credential.helper=","-c","credential.helper=!gh auth git-credential",
                       "-c","user.name=kaiwen123-yang","-c","user.email=kaiwen123-yang@users.noreply.github.com",
                       *map(str,args)])


def api(endpoint):
    return json.loads(shell(None,["gh","api","repos/"+SLUG+"/"+endpoint]))


def sync(repo):
    git(repo,"fetch",REMOTE,"main")
    git(repo,"merge","--ff-only","FETCH_HEAD")


def publish(run,repo,stage):
    from scripts.multimodal.mm02_physics import emit
    receipt=run/f"published_{stage}.json"
    with (run/"publication.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        if receipt.exists():
            return
        sync(repo)
        if stage=="video":
            folder=run/"videos"
            claim=json.loads((folder/"first_success.json").read_text())
            case=json.loads(Path(claim["result"]).read_text())
            if not case["success"] or case["mode"]!="pure" or len(case["events"])!=12 or case["teacher_steps"]:
                raise ValueError("First-success publication requires a pure, complete frame0 episode")
            dest=repo/RESULT/"videos"
            dest.mkdir(parents=True,exist_ok=True)
            for name in ("first_student_success_1080p.mp4","first_student_success_1080p.json","first_success.json"):
                shutil.copy2(folder/name,dest/name)
            emit(dest/"first_physics_case.json",case)
            files=[RESULT/"videos"]
            verify=RESULT/"videos/first_physics_case.json"
            title="Deliver the first MM02 pure-student 1080p full-episode success"
        else:
            subprocess.run([sys.executable,"-m","scripts.multimodal.mm02_closeout",str(run),str(repo)],check=True)
            files=[RESULT,*map(Path,("reports/MULTIMODAL_MM02_RESULTS.md","DAILY_WORK_LOG.md","PROJECT_STATE.md",
                   "README.md","AGENTS.md","docs/GOAL_GAP_20261125.md","docs/MULTIMODAL_ALGORITHM_PLAN_20261125.md",
                   "docs/RESEARCH_ROADMAP.md","prompts/NEXT_RUN.txt","prompts/MULTIMODAL_START.txt",
                   "prompts/B0_START.txt"))]
            verify=Path("reports/MULTIMODAL_MM02_RESULTS.md")
            title="Publish frozen MM02 on-policy whole-body learning and blind physics results"
            prompts=[(repo/"prompts"/f).read_bytes() for f in ("NEXT_RUN.txt","MULTIMODAL_START.txt","B0_START.txt")]
            if len(set(prompts))!=1 or not (repo/verify).is_file():
                raise ValueError("Result report or the common continuation prompt is incomplete")
        git(repo,"add","--",*[str(f) for f in files if (repo/f).exists()])
        if git(repo,"diff","--cached","--name-only"):
            git(repo,"diff","--cached","--check")
            git(repo,"commit","-m",title)
        # If another job published concurrently, keep its commits and apply ours on top.
        for attempt in range(3):
            try:
                git(repo,"push",REMOTE,"HEAD:refs/heads/main")
                break
            except subprocess.CalledProcessError:
                if attempt==2:
                    raise
                git(repo,"fetch",REMOTE,"main")
                git(repo,"rebase","FETCH_HEAD")
        fixed=git(repo,"rev-parse","HEAD")
        commit=api("git/commits/"+fixed)
        if commit["sha"]!=fixed:
            raise ValueError("Fixed-commit GitHub readback disagrees")
        tree=commit["tree"]["sha"]
        for name in verify.parts:
            entries=api("git/trees/"+tree)["tree"]
            tree=next(item["sha"] for item in entries if item["path"]==name)
        blob=api("git/blobs/"+tree)
        data=base64.b64decode(blob["content"])
        stored=subprocess.check_output(["git","cat-file","blob",f"{fixed}:{verify.as_posix()}"],cwd=repo)
        if data!=stored:
            raise ValueError("Published fixed-commit blob and restoration tree disagree")
        emit(receipt,dict(commit=fixed,file=verify.as_posix(),git_blob=tree,
                          verified_at_utc=datetime.now(timezone.utc).isoformat(),
                          link=f"https://github.com/{SLUG}/blob/{fixed}/{verify.as_posix()}"))
        print(receipt.read_text(),flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("run",type=Path)
    p.add_argument("publish_repo",type=Path)
    p.add_argument("stage",choices=("watch-video","video","final"))
    a=p.parse_args()
    if a.stage=="watch-video":
        while not (a.run/"videos/first_student_success_1080p.json").exists():
            if (a.run/"published_final.json").exists():
                return
            time.sleep(4)
        publish(a.run,a.publish_repo,"video")
    else:
        if a.stage=="final" and (a.run/"videos/first_student_success_1080p.json").exists():
            publish(a.run,a.publish_repo,"video")
        publish(a.run,a.publish_repo,a.stage)


if __name__=="__main__":
    main()
