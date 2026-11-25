"""Execute the registered simulation round from durable phase receipts."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import subprocess
import time

from scripts.multimodal.mm02_physics import ROOT, TORCH, digest, emit
from scripts.multimodal.mm02_suite import BRANCHES, DEV, FORMAL, TRAIN, jobs, recover, run_suite

PILOTS = ("fixed","adaptive_slope_only")
PARENT = Path("/root/autodl-tmp/mm01-20261125")


def read(path):
    return json.loads(path.read_text())


def pilot_choice(rows):
    score = {}
    for branch in PILOTS:
        cases = [r for r in rows if r["branch"]==branch]
        if len(cases)!=8:
            raise ValueError("Pilot needs eight independently scored cases per variant")
        collision_or_limit = sum(bool(r["first_failure"]) and
                                 ("arm_joint_limit" in r["first_failure"]["reason"] or
                                  "robot_self" in r["first_failure"]["reason"] or
                                  "self_collision" in r["first_failure"]["reason"] or
                                  "self_contact" in r["first_failure"]["reason"]) for r in cases)
        score[branch] = dict(success=sum(r["success"] for r in cases),
                             events=sum(len(r["events"]) for r in cases), limit_self=collision_or_limit)
    fixed, adaptive = [score[b] for b in PILOTS]
    wins = (adaptive["success"]>fixed["success"] or (adaptive["success"]==fixed["success"]
            and adaptive["events"]>fixed["events"] and adaptive["limit_self"]<=fixed["limit_self"]))
    return dict(chosen=PILOTS[int(wins)], scores=score, cases=[r["id"] for r in rows])


def extension(development):
    groups = {}
    for stage,rows in development.items():
        if stage>4:
            continue
        if len(rows)!=16:
            raise ValueError("Expected the sixteen registered development cases per round")
        for r in rows:
            if r["mode"]!="pure" or r["scene"] not in DEV or r["partition"]!=f"round{stage}/development":
                raise ValueError("Invalid evidence for the development-only extension decision")
            key = (r["branch"],r["scene"],r["side"],r["goal"])
            groups.setdefault(key, {})[stage] = r
    improved, new_success, sides_at_four = [],[],{b:set() for b in BRANCHES}
    for key,c in groups.items():
        if set(c)!={1,2,3,4}:
            raise ValueError(f"Incomplete matched cases for {key}")
        first = max(len(c[i]["events"]) for i in (1,2))
        last = max(len(c[i]["events"]) for i in (3,4))
        if last>first:
            improved.append(dict(branch=key[0],scene=key[1],side=key[2],goal=key[3],early=first,
                                 late=last,case_ids=[c[i]["id"] for i in range(1,5)]))
        if not any(c[i]["success"] for i in (1,2)) and any(c[i]["success"] for i in (3,4)):
            new_success.append(list(key))
        if c[4]["success"]:
            sides_at_four[key[0]].add(key[2])
    bilateral = [b for b,s in sides_at_four.items() if len(s)==2]
    combinations = sorted(set((row["side"],row["goal"]) for row in improved))
    return dict(extend=bool(not bilateral and (new_success or len(combinations)>=2)),
                round4_bilateral=bilateral,new_complete_success=new_success,
                new_ordered_event_cases=improved,new_side_goal_combinations=combinations,
                decided_at_utc=datetime.now(timezone.utc).isoformat(),student_blind_cases_used=0)


class Experiment:
    def __init__(self,run,workers):
        self.run,self.workers = run.resolve(),workers
        self.logs = self.run/"logs"
        self.logs.mkdir(exist_ok=True,parents=True)

    def state(self,phase):
        emit(self.run/"current.json", dict(phase=phase,utc=datetime.now(timezone.utc).isoformat()))
        print(phase,flush=True)

    def physics(self, name, cases):
        path = self.run/name/"cases.json"
        if path.exists():
            evaluated = read(path)
            if [r["id"] for r in evaluated]!=[j["id"] for j in cases]:
                raise ValueError(f"Existing case list differs for {name}")
            return evaluated
        self.state(name)
        outputs = run_suite(self.run,cases,self.workers)
        emit(path,outputs)
        return outputs

    def branches(self, name, n, parents, max_count):
        path = self.run/name/"cases.json"
        if path.exists():
            return read(path)
        self.state(name)
        return recover(self.run,name,n,parents,max_count,self.workers)

    def command(self, module, args, receipt, label):
        if receipt.exists():
            return
        log = self.logs/(label.replace("/","_")+".log")
        with log.open("a",buffering=1) as f:
            cmd = [str(TORCH),"-u","-m",f"scripts.multimodal.{module}",*map(str,args)]
            print(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),command=cmd)),file=f,flush=True)
            subprocess.run(cmd,check=True,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
        if not receipt.exists():
            raise ValueError(f"Missing completion receipt {receipt}")

    def train_actor(self, n, branch, stage, parent, bundle=None):
        root = self.run/f"round{n}"
        out = root/branch/stage
        args = ["--stage",stage,"--round",n,"--branch",branch,"--members",root/"actor_members.json",
                "--schedule",root/"schedule.npy","--parent",parent,"--output",out]
        if bundle:
            args += ["--h32-bundle",bundle]
        self.command("mm02_train_actor",args,out/"receipt.json",f"r{n}_{branch}_{stage}")

    def dynamics(self,n,stage,parent,actor=None):
        root = self.run/f"round{n}"
        out = root/"dynamics"
        args = [stage,"--membership",root/"wm_membership.json","--round",n,"--parent",parent,"--out",out]
        if actor:
            args += ["--actor",actor]
        receipt = {"wm":"wm_training.json","bridge":"bridge_training.json","validate":"wm_validation.json"}[stage]
        self.command("mm02_dynamics",args,out/receipt,f"r{n}_dynamics_{stage}")

    def run_all(self):
        base = self.run
        initial = read(base/"initial/cases.json")
        if len(initial)!=12:
            raise ValueError("Incomplete original on-policy collection")
        pilots = {b:base/"pilot"/b/"deploy.pt" for b in PILOTS}
        for b in PILOTS:
            receipt=read(base/"pilot"/b/"receipt.json")
            if receipt["retained_actor"]!=512:
                raise ValueError("Incomplete affine pilot")
        pilot = self.physics("pilot_development",jobs(base,"pilot_development",pilots,DEV,0,snapshots=True))
        chosen = pilot_choice(pilot)
        emit(base/"pilot/selection.json",chosen)
        parent = base/"pilot"/chosen["chosen"]/"final.pt"
        actors = {b:parent for b in BRANCHES}
        deploy = {b:pilots[chosen["chosen"]] for b in BRANCHES}
        val_parents = [r for r in pilot if r["branch"]==chosen["chosen"] and r["scene"]=="va_pose"]
        new_train = [r["raw_episode"] for r in initial]
        cum_recovery, dev_results = [],{}
        source_ids = read(PARENT/"actor-common/configuration.json")["membership"]
        wm_parent = PARENT/"wm_final/wm.pt"
        last_round = 4
        for n in range(1,7):
            name = f"round{n}"
            curr = base/name
            collection = self.physics(name+"/collection", jobs(base,name+"/collection",deploy,
                                      TRAIN,n,("pure","mixed"),snapshots=True))
            self.repeat_successes(collection)
            train = self.branches(name+"/recovery_train",n,collection,256)
            val = self.branches(name+"/recovery_validation",n,val_parents,32)
            new_train.extend(r["raw_episode"] for r in collection)
            cum_recovery.extend(r["raw_episode"] for r in train)
            emit(curr/"actor_members.json",sorted(new_train+cum_recovery))
            membership = dict(old_train=[str(PARENT/"data"/i) for i in source_ids["train"]],
                new_train=new_train, cumulative_train_recovery=cum_recovery,
                train_recovery=[r["raw_episode"] for r in train],
                validation_recovery=[r["raw_episode"] for r in val],
                validation_onpolicy=[r["raw_episode"] for r in val_parents],
                validation_demo=[str(PARENT/"data"/i) for i in source_ids["validation"]])
            emit(curr/"wm_membership.json",membership)
            self.state(name+"/bc_and_wm")
            with ThreadPoolExecutor(3) as pool:
                wm = pool.submit(self.dynamics,n,"wm",wm_parent)
                models = {b:pool.submit(self.train_actor,n,b,"bc",actors[b]) for b in BRANCHES}
                for future in models.values():
                    future.result()
                wm.result()
            wm_parent = curr/"dynamics/wm.pt"
            self.state(name+"/paired")
            bundle = curr/"dynamics/trajectory_bundle.pt"
            with ThreadPoolExecutor(2) as pool:
                sup = pool.submit(self.train_actor,n,BRANCHES[0],"paired",curr/BRANCHES[0]/"bc/final.pt")
                self.dynamics(n,"bridge",wm_parent,curr/BRANCHES[1]/"bc/final.pt")
                self.train_actor(n,BRANCHES[1],"paired",curr/BRANCHES[1]/"bc/final.pt",bundle)
                sup.result()
            for stage in ("bc","paired"):
                pair = [read(curr/b/stage/"receipt.json") for b in BRANCHES]
                for field in ("sequence_sha256","membership_signature","retained_actor"):
                    if pair[0][field]!=pair[1][field]:
                        raise ValueError(f"Branches disagree on {stage} {field}")
                if n==1 and stage=="bc" and pair[0]["parent_sha256"]!=pair[1]["parent_sha256"]:
                    raise ValueError("Two main branches did not start at identical common weights")
            actors = {b:curr/b/"paired/final.pt" for b in BRANCHES}
            deploy = {b:curr/b/"paired/deploy.pt" for b in BRANCHES}
            # Avoid forking physics processes from a multithreaded Python parent.
            dev = self.physics(name+"/development",jobs(base,name+"/development",deploy,DEV,n,snapshots=True))
            self.repeat_successes(dev)
            self.dynamics(n,"validate",bundle,actors[BRANCHES[1]])
            dev_results[n] = dev
            val_parents = [r for r in dev if r["scene"]=="va_pose"]
            if n==4:
                decision_file = base/"extension_decision.json"
                decision = extension(dev_results)
                if decision_file.exists():
                    old = read(decision_file)
                    if old["extend"] != decision["extend"]:
                        raise ValueError("Existing extension decision differs")
                else:
                    emit(decision_file,decision)
                last_round = 6 if decision["extend"] else 4
            if n==last_round:
                break
        freeze = base/"terminal_freeze.json"
        identities = {b:dict(training=str(actors[b]), training_sha256=digest(actors[b].read_bytes()),
                             deployment=str(deploy[b]),deployment_sha256=digest(deploy[b].read_bytes()))
                      for b in BRANCHES}
        if freeze.exists():
            if read(freeze)["branches"] != identities:
                raise ValueError("A frozen terminal checkpoint changed")
        else:
            emit(freeze,dict(round=n,branches=identities,decision=read(base/"extension_decision.json"),
                             utc=datetime.now(timezone.utc).isoformat()))
        formal = self.physics("formal",jobs(base,"formal",deploy,FORMAL,n))
        self.repeat_successes(formal)
        # Instantiate each full training package in a fresh process; score one matched development reset.
        reloads = [j for j in jobs(base,"reload",actors,("tr_nominal",),n)
                   if j["side"]=="pull" and j["goal"]==15]
        self.physics("reload",reloads)
        self.state("physics_and_training_complete")

    def repeat_successes(self,rows):
        for r in sorted(rows, key=lambda item: item["recorded_utc"]):
            if not r["success"] or r["mode"]!="pure" or r["branch"] not in BRANCHES:
                continue
            key = f'{r["branch"]}_{r["side"]}_{r["goal"]}'
            folder = self.run/"repeats"/key
            receipt = folder/"first.json"
            if not receipt.exists():
                emit(receipt,dict(source=r["id"],sha=r["sha"],checkpoint=r["checkpoint"]))
            if read(receipt)["source"]!=r["id"]:
                continue
            original = {k:r[k] for k in ("branch","scene","side","goal","mode","round","checkpoint",
                                         "sha","seed","probability")}
            cases = [dict(original,id=f"{key}_repeat_{i}",partition="repeats/"+key,snapshot_count=0)
                     for i in (1,2)]
            self.physics("repeats/"+key,cases)


if __name__=="__main__":
    p = argparse.ArgumentParser()
    p.add_argument("run",type=Path)
    p.add_argument("--workers",type=int,default=10)
    a = p.parse_args()
    with (a.run/"experiment.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        Experiment(a.run,a.workers).run_all()
