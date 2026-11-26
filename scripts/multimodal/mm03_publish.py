"""Publish completed MM03 milestones using the dedicated publication worktree."""
import argparse
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import subprocess
import time
import traceback

from scripts.multimodal.mm03_first import deliver
from scripts.multimodal.mm03_launch import DEFAULT, read, write, now
from scripts.multimodal.mm03_report import OUT, REPORT, SLUG, snapshot


def command(*argv, repo, capture=True):
    return subprocess.run(argv,cwd=repo,check=True,text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def git(repo,*args):
    return command("git","-c","http.version=HTTP/1.1","-c","credential.helper=",
                   "-c","credential.helper=!gh auth git-credential","-c","user.name=kaiwen123-yang",
                   "-c","user.email=kaiwen123-yang@users.noreply.github.com",*args,repo=repo).strip()


def reached(root):
    milestones=[]
    complete_episodes=(root/"A/channel_results.json").is_file() and (root/"B/teacher_cases.json").is_file()
    if complete_episodes and (root/"videos/mm02/index.json").is_file():
        milestones.append("44 案干预与 96 条完整教师")
    if len(read(root/"videos/mm03/examples.json").get("videos",[]))>=3:
        milestones.append("完整教师与同条件高层学生录像")
    for block in range(3):
        if all((root/f"A/low/seed{seed}/block{block}/train_result.json").is_file() for seed in (1701,1702,1703)):
            milestones.append(f"L16 第 {block} 个训练块")
    if (root/"A/completion.json").is_file():
        milestones.append("L16 工程评测完成")
    if (root/"B/warm/H9/seed1703/receipt.json").is_file():
        milestones.append("高层预热完成")
    for variant in ("C32G","CF32"):
        if all((root/f"C/{variant}/seed{seed}/short_recovery.json").is_file() for seed in (1701,1702,1703)):
            milestones.append(variant+" 同父对照完成")
    if (root/"C/selection.json").is_file():
        milestones.append("C 候选冻结")
    for block in sorted((root/"B/rounds").glob("r*/block.json")):
        milestones.append(block.parent.name+" 工作块")
    if (root/"videos/mm03/first_student_full_1080p.json").exists():
        milestones.append("首次纯学习完整成功视频")
    if (root/"videos/mm03/independent_reloads.json").exists():
        milestones.append("首次纯学习完整成功及独立重载")
    if (root/"B/candidate_freeze.json").exists():
        milestones.append("主方法候选冻结")
    if (root/"B/completion.json").exists() and (root/"C/selection.json").exists() and (root/"A/completion.json").exists():
        milestones.append("正式评测结案")
    return milestones


def finish_pending(root,repo):
    pending=root/"publication/pending.json"
    record=read(pending)
    if not record:
        return
    # A concurrent normal push is integrated without rewriting that remote history.
    git(repo,"fetch","-q","origin","main")
    ahead=git(repo,"rev-list","--left-right","--count","origin/main...HEAD").split()
    if int(ahead[0]):
        git(repo,"rebase","origin/main")
    git(repo,"push","origin","HEAD:refs/heads/main")
    fixed=git(repo,"rev-parse","HEAD")
    back=command("gh","api",f"repos/{SLUG}/git/commits/{fixed}","--jq",".sha",repo=repo).strip()
    if fixed!=back:
        raise RuntimeError("GitHub fixed-commit readback disagrees")
    prev=read(root/"publication/published.json")
    prev.update({name:fixed for name in record["names"]})
    write(root/"publication/published.json",prev)
    write(root/f"publication/commits/{fixed}.json",dict(commit=fixed,names=record["names"],verified_beijing=now()))
    pending.unlink()
    print(now(),"Published",fixed,record["names"],flush=True)


def publish(root,repo,extra=None):
    (root/"publication").mkdir(exist_ok=True)
    with (root/"publication/publish.lock").open("a") as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        finish_pending(root,repo)
        names=[x for x in reached(root) if x not in read(root/"publication/published.json")]
        if extra and extra not in read(root/"publication/published.json"):
            names.append(extra)
        if not names:
            return
        if git(repo,"status","--porcelain","--",str(OUT),str(REPORT),"PROJECT_STATE.md","DAILY_WORK_LOG.md"):
            raise RuntimeError("Publication worktree has an unfinished edit; inspect before reusing")
        git(repo,"fetch","-q","origin","main")
        git(repo,"merge","--ff-only","origin/main")
        snapshot(root,repo,"、".join(names))
        git(repo,"add","--sparse","--",str(OUT),str(REPORT),"PROJECT_STATE.md","DAILY_WORK_LOG.md")
        git(repo,"diff","--cached","--check")
        git(repo,"commit","-m","Record MM03 physical evidence: "+"; ".join(names))
        write(root/"publication/pending.json",dict(names=names,local_commit=git(repo,"rev-parse","HEAD"),at=now()))
        finish_pending(root,repo)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=("watch","once"))
    p.add_argument("--root",type=Path,default=DEFAULT)
    p.add_argument("--repo",type=Path,default=Path("/root/autodl-tmp/dog-and-arm-mm03-publish"))
    p.add_argument("--milestone")
    a=p.parse_args()
    if a.action=="once":
        deliver(a.root)
        publish(a.root,a.repo,a.milestone)
        return
    (a.root/"publication").mkdir(exist_ok=True)
    with (a.root/"publication/watch.lock").open("a") as lock:
        try:
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            return
        last_attempt=0.
        while True:
            try:
                success = deliver(a.root,video_only=True)
                if time.monotonic()-last_attempt>35:
                    last_attempt=time.monotonic()
                    publish(a.root,a.repo)
                if success:
                    deliver(a.root)
                if "正式评测结案" in read(a.root/"publication/published.json"):
                    return
            except Exception as exc:
                write(a.root/"publication/last_error.json",dict(at=now(),error=repr(exc)))
                traceback.print_exc()
            time.sleep(5)


if __name__=="__main__":
    main()
