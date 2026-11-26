"""Summarize durable MM03 receipts at a publication boundary without touching simulation data."""
from collections import Counter, defaultdict
from pathlib import Path
import json
import os
import shutil

from scripts.multimodal.mm03_launch import UNITS, alive, now, read, state_file, write

OUT = Path("results/multimodal/mm03_20261126")
REPORT = Path("reports/MULTIMODAL_MM03_RESULTS.md")
SLUG = "kaiwen123-yang/dog-and-arm"


def lines(path):
    if not path.exists():
        return
    with path.open() as f:
        for line in f:
            # An open stream may be between the data write and its final newline.
            if line.endswith("\n"):
                yield json.loads(line)


def case_rows(root):
    fields=("id","source","branch","method","variant","stage","partition","mode","use","scene","side","goal",
            "seed","training_seed","round","block","command","arm","success","first_failure","next_phase",
            "student_steps","teacher_steps","teacher_substeps","prefix_reached","prefix_switch_tick","events",
            "physics_steps","robot_door_contact_steps","bilateral_contact_steps","maximum_hinge_deg",
            "executor_source_mask","min_wheel_load_n","unsupported_samples","max_incomplete_support_s",
            "stable_at_end_s","all_supported_fraction","max_stop_drift_m","initial_state_sha256",
            "checkpoint","checkpoint_sha256","sha","raw_episode","case_dir","wall_s","completed_utc","recorded_utc")
    res=[]
    for lane in ("A","B","C"):
        for path in sorted((root/lane).rglob("result.json")):
            if any(part.startswith(".") for part in path.relative_to(root).parts):
                continue
            row=read(path)
            if "physics_steps" not in row or "success" not in row:
                continue
            parts=path.relative_to(root).parts
            if lane=="C":
                group=next((k for k in ("development","independent_reload","first_success_reloads") if k in parts),"native")
            elif lane=="B":
                group=row.get("partition",parts[1])
            else:
                group=row.get("stage") or parts[1]
            selected={k:row[k] for k in fields if k in row}
            if lane=="C" and len(parts)>2 and parts[2].startswith("seed"):
                selected["training_seed"]=int(parts[2][4:])
            selected.update(lane=lane, group=group, result=str(path),ordered_events=len(row.get("events",[])))
            res.append(selected)
    return res


def budgets(root, rows):
    physics=Counter()
    kinds=defaultdict(lambda:dict(cases=0,success=0,ordered_events=0,native_substeps=0))
    for r in rows:
        key=r["lane"]+"/"+r["group"]
        physics[key]+=r["physics_steps"]
        v=kinds[key]
        for k,n in (("cases",1),("success",int(r["success"])),("ordered_events",r["ordered_events"]),
                     ("native_substeps",r["physics_steps"])):
            v[k]+=n
    a=[]
    for f in sorted((root/"A/low").glob("seed*/block*/progress.json")):
        rec=read(f)
        a.append(dict(seed=rec["seed"],block=rec["block"],retained=rec["update"],
                      paid=rec.get("paid",rec["update"]),resume=str(f.parent/"latest.pt"),
                      deploy=str(f.parent/"deploy.pt") if (f.parent/"deploy.pt").exists() else None))
    b=[]
    for f in sorted((root/"B").rglob("spec.json")):
        spec=read(f)
        if "stage" not in spec or "output" not in spec:continue
        folder=f.parent
        rec=read(folder/"receipt.json") or read(folder/"progress.json")
        if not rec:continue
        retained=int(rec.get("retained",rec.get("step",0)))
        b.append(dict(stage=spec["stage"],method=spec.get("method"),seed=spec.get("seed"),
            round=spec.get("round",0),retained=retained,paid=rec.get("paid",retained),path=str(folder),
            native_substeps=rec.get("paid_model_cost",{}).get("native_substeps",rec.get("native_substeps",0)),
            model_queries=rec.get("paid_model_cost",{}).get("model_queries",rec.get("model_queries",0)),
            full=rec.get("full"),deploy=rec.get("deploy")))
    c=[]
    for f in sorted((root/"C").glob("*/seed*/applications.jsonl")):
        recs=list(lines(f))
        stable=read(f.parent/"receipt.json") or read(f.parent/"progress.json")
        c.append(dict(variant=f.parent.parent.name,seed=int(f.parent.name[4:]),paid=len(recs),
            retained=stable.get("retained",stable.get("step",0)),bc_rows_paid=256*len(recs),
            model_queries=sum(s["model_queries"] for s in recs),native_substeps=sum(s["native_substeps"] for s in recs),
            full=str(f.parent/"final.pt") if (f.parent/"final.pt").is_file() else None))
    cs=[]
    for f in sorted((root/"C").glob("*/seed*/short_recovery.json")):
        data=read(f)
        cs.append(dict(variant=f.parent.parent.name,seed=int(f.parent.name[4:]),cases=len(data),
            survived=sum(x["survived_32"] for x in data),native_substeps=sum(x["physical_substeps"] for x in data)))
    bridge=read(root/"C/bridge/bridge.json") or read(root/"C/bridge/progress.json")
    direction=read(root/"C/directional_response.json")
    parity=read(root/"A/cpu_parity/comparison.json")
    additional={"C/true_forward_optimization":sum(x["native_substeps"] for x in c),
                "C/short_recovery_evaluation":sum(x["native_substeps"] for x in cs),
                "C/directional_check":direction.get("native_substeps",0),
                "B/true_forward_optimization":sum(x["native_substeps"] for x in b)}
    high=sum(x["paid"] for x in b if x["stage"] not in ("wm","bridge"))
    return dict(as_of_beijing=now(),low_updates=sum(x["paid"] for x in a),B_high_updates=high,
        C_actor_updates=sum(x["paid"] for x in c),wm_updates=sum(x["paid"] for x in b if x["stage"]=="wm"),
        bridge_updates=sum(x["paid"] for x in b if x["stage"]=="bridge")+bridge.get("paid",0),critic_updates=0,
        completed_episodes=len(rows),episode_substeps=sum(physics.values()),
        extra_substeps=additional,accounted_native_substeps=sum(physics.values())+sum(additional.values()),
        physical_by_group=dict(sorted(kinds.items())),A_stages=a,B_stages=b,C_forks=c,C_short=cs,
        C_comparison_bridge=bridge,parity_receipt=parity,
        accounting="Completed native case receipts and logged optimization/short-window steps. An open episode counts when it commits. Render playback integrates zero steps. Extra diagnostics appear separately.",
        hardware_motion_commands=0)


def active(root):
    rec={}
    for unit in ("supervisor",*UNITS):
        info=read(state_file(root,unit))
        rec[unit]=dict(**info,live=alive(info))
    return rec


def resource_bounds(root):
    data=list(lines(root/"resources.jsonl"))
    gpu=[str(row.get("gpu_name_usedMiB_totalMiB_utilPC","")).split(", ") for row in data]
    gpu=[g for g in gpu if len(g)==4]
    return dict(samples=len(data),initial=read(root/"launch_config.json").get("workers"),
        current=data[-1] if data else {}, peak_sampled_gpu_used_MiB=max((int(x[-3]) for x in gpu),default=None),
        peak_sampled_gpu_util_percent=max((int(x[-1]) for x in gpu),default=None),
        scope="sampled whole allocated GPU incl. unrelated users; service Torch peak and queue waits are separate")


def slimcopy(src,dest):
    if src.is_file():
        dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.is_file() or dest.stat().st_size!=src.stat().st_size or src.stat().st_mtime_ns!=dest.stat().st_mtime_ns:
            shutil.copy2(src,dest)


def mirror_records(root,out):
    small=("A/design.json","A/channel_results.json","A/command_reference.json","A/low/compatibility.json",
           "A/completion.json","A/complete.json","B/teacher_registration.json","B/candidate_freeze.json",
           "B/completion.json","C/parent.json","C/calibration.json","C/directional_response.json",
           "C/directional_local_fp64.json","C/development_anchors.json","C/selection.json","C/bridge/bridge.json",
           "service/upgrade1.json","A/low/summary.json","A/low/development_results.json",
           "A/cpu_parity/comparison.json","resources/worker_targets.json","B/prefix_p6_parity_pull.json",
           "B/prefix_p6_parity_push.json","C/native_pool_changes.jsonl")
    for name in small:
        slimcopy(root/name, out/"receipts"/name)
    for lane,globs in (("A",("low/seed*/block*/train_result.json","parity/*.json")),
                       ("B",("models/*/seed*/*.json","rounds/r*/block.json","rounds/r*/collection_complete.json")),
                       ("C",("*/seed*/receipt.json","*/seed*/short_recovery.json"))):
        for pattern in globs:
            for src in (root/lane).glob(pattern):
                slimcopy(src,out/"receipts"/src.relative_to(root))
    for src in (root/"videos").glob("*/*"):
        if src.suffix in (".json",".mp4") and ".partial" not in src.name:
            slimcopy(src,out/"videos"/src.relative_to(root/"videos"))
    for src in (root/"attempts").glob("*/*.json"):
        slimcopy(src,out/"execution"/src.relative_to(root))
    for pattern in ("C/handoffs/*.json","B/coordinator_refresh*ack.json","resources/allocation_changes.jsonl"):
        for src in root.glob(pattern):
            slimcopy(src,out/"execution"/src.relative_to(root))
    # A selected learned deployment is small. Full optimizer/replay assets retain their cloud paths.
    for selected in (root/"B/models").glob("*/seed*/best.json"):
        info=read(selected)
        if (root/"B/candidate_freeze.json").is_file():
            slimcopy(Path(info["deploy"]),out/"models"/info["method"]/f"seed{info['seed']}"/"deploy.pt")
    if (root/"A/completion.json").is_file():
        for seed,s in read(root/"A/completion.json").get("seeds",{}).items():
            if s.get("best_deploy"):
                slimcopy(Path(s["best_deploy"]),out/"models/L16"/f"seed{seed}"/"deploy.pt")


def scored(n,total):
    return f"{n}/{total}" if total else "待评测"


def task_tables(root, rows, formal):
    table=[]
    local=[r for r in rows if r["lane"]=="A" and r["group"]=="development"]
    if local:
        table+=["## L16 独立工程评测","| 低层种子 | 工作块 | 同时满足全部工程判据 | 计划案数 |",
                "|---:|---:|---:|---:|"]
        for seed,block in sorted({(r["seed"],r["block"]) for r in local}):
            subset=[r for r in local if (r["seed"],r["block"])==(seed,block)]
            table.append(f"| {seed} | {block} | {scored(sum(r['success'] for r in subset),len(subset))} | 40 |")
        table+=["工程通过同时要求支撑、停车、漂移、运动方向响应及安全条件。单轮载荷和停车段速度保存在各案原始路径。"]
    b=[r for r in rows if r["lane"]=="B"]
    prefixes=[r for r in b if r.get("mode")=="prefix"]
    if prefixes:
        table+=["## 真实教师前缀后的学生续演",f"已结束 {len(prefixes)} 案，{sum(r.get('prefix_reached') is True for r in prefixes)} 案实际切换到学生，"
                f"{sum(r['success'] and r.get('prefix_reached') is True for r in prefixes)} 案继续完成全部事件。"]
    table+=["## 正式纯学生评测"]
    if formal:
        table+=["| 方法 | 微调种子 | 已公开 20 案 | 新组合 16 案 | 已停稳 | 已触门 |",
                "|---|---:|---:|---:|---:|---:|"]
        for method,seed in sorted({(r["method"],r["seed"]) for r in formal}):
            subset=[r for r in formal if (r["method"],r["seed"])==(method,seed)]
            blind=[r for r in subset if r["scene"].startswith("te_mm03")]
            public=[r for r in subset if not r["scene"].startswith("te_mm03")]
            table.append(f"| {method} | {seed} | {scored(sum(r['success'] for r in public),len(public))} | "
                         f"{scored(sum(r['success'] for r in blind),len(blind))} | {sum(r['ordered_events']>=2 for r in subset)} | "
                         f"{sum(r.get('robot_door_contact_steps',0)>0 for r in subset)} |")
    else:
        table.append("主评测计划为三个方法、三个微调种子，每包 20 已公开回归案和 16 新组合案。目前无已完成的正式成绩。")
    dev=[r for r in b if r.get("mode")=="pure" and r["group"].endswith("development")]
    if dev:
        table+=["## 最近完成的完整开发矩阵","| 方法 | 微调种子 | 轮次 | 全程成功 | 驶近 | 停稳 | 首败最多的原因 |",
                "|---|---:|---:|---:|---:|---:|---|"]
        for method,seed in sorted({(r["method"],r["seed"]) for r in dev}):
            pack=defaultdict(list)
            for r in dev:
                if (r["method"],r["seed"])==(method,seed):pack[r["round"]].append(r)
            rounds=[k for k,v in pack.items() if len(v)==8]
            if not rounds:continue
            rr=max(rounds); subset=pack[rr]
            reasons=Counter((r.get("first_failure") or {}).get("reason","") for r in subset if not r["success"])
            reason="、".join(f"{k} ({n})" for k,n in reasons.most_common(2)) or "—"
            table.append(f"| {method} | {seed} | {rr} | {sum(r['success'] for r in subset)}/8 | "
                         f"{sum(r['ordered_events']>=1 for r in subset)}/8 | {sum(r['ordered_events']>=2 for r in subset)}/8 | {reason} |")
    return table


def snapshot(root,repo,milestone):
    out=repo/OUT
    out.mkdir(parents=True, exist_ok=True)
    rows=case_rows(root)
    cost=budgets(root,rows)
    states=active(root)
    cfg=read(root/"launch_config.json")
    complete=(root/"B/completion.json").is_file() and (root/"C/selection.json").is_file() and (root/"A/completion.json").is_file()
    base=read(out/"manifest.json")
    videos=read(root/"videos/mm02/index.json").get("videos",[])
    best=[read(p) for p in sorted((root/"B/models").glob("*/seed*/best.json"))]
    manifest={**base,"status":"completed" if complete else "in_progress","as_of_beijing":now(),"milestone":milestone,
              "runtime":states,"config":cfg,"raw_case_table":"physical_cases.jsonl","budget":"budget.json",
              "resource_samples":resource_bounds(root),"best_packages":best,
              "latest_locations":[str(p) for p in sorted((root/"B/models").glob("*/seed*/latest.json"))],
              "C_selected":read(root/"C/selection.json").get("selected_model_variant"),"mm02_original_videos":len(videos),
              "first_pure_success":read(root/"videos/mm03/first_case.json") or None,
              "candidate_freeze":read(root/"B/candidate_freeze.json") or None,"planned_formal_cases":324,
              "new_blind_opened":any(r["scene"].startswith("te_mm03_") for r in rows if r.get("scene")),
              "B_current":read(root/"B/physical_progress.json"),"A_current":read(root/"A/progress.json"),
              "C_current":read(root/"C/current.json"),"hardware_motion_commands":0}
    write(out/"manifest.json",manifest)
    write(out/"budget.json",cost)
    (out/"physical_cases.jsonl").write_text("".join(json.dumps(r,ensure_ascii=False,separators=(",",":"))+"\n" for r in rows))
    mirror_records(root,out)
    resc=[r for r in rows if r["lane"]=="A" and r["group"]=="rescue"]
    teach=[r for r in rows if r["lane"]=="B" and r["group"]=="teachers"]
    formal=[r for r in rows if r["lane"]=="B" and (r["group"]=="formal" or r["group"].startswith("formal/"))]
    status=", ".join(f"{k} {v.get('state','pending')}" for k,v in states.items() if k in "ABC")
    summary=(f"A 已有 {len(resc)}/44 个干预或教师参考案。B 的新完整教师通过 {sum(r['success'] for r in teach)}/{len(teach)}"
             f"（计划 96），已回执的正式纯学生案 {len(formal)}/324。L16、B 高层、C 分支、WM、bridge "
             f"累计实付分别为 {cost['low_updates']:,}、{cost['B_high_updates']:,}、{cost['C_actor_updates']:,}、"
             f"{cost['wm_updates']:,}、{cost['bridge_updates']:,} 次。")
    stamp=manifest["as_of_beijing"]
    report=[f"# MM03 多模态腿臂仿真实验",f"{stamp}（北京时间），{milestone}。",summary,
        "原生 MuJoCo 3.3.0，2 ms 伺服、20 ms 学习控制、100 ms 腕部 RGB-D。按原 12 事件判分。真实硬件运动命令 0。",
        "## A 通道替换和轮腿学习","| R6 父包 | 替换通道 | 完成 / 实跑 | 驶近 | 停稳 | 触门 |","|---|---|---:|---:|---:|---:|"]
    for key in sorted({(r.get("branch",""),r.get("variant","")) for r in resc}):
        grp=[r for r in resc if (r.get("branch",""),r.get("variant",""))==key]
        report.append(f"| {key[0]} | {key[1]} | {sum(r['success'] for r in grp)}/{len(grp)} | {sum(r['ordered_events']>=1 for r in grp)} | {sum(r['ordered_events']>=2 for r in grp)} | {sum(r.get('robot_door_contact_steps',0)>0 for r in grp)} |")
    report+=["","A 的每个 2 ms 子步日志保存在 AutoDL 对应 case_dir/physics_2ms。旧 CPU 推理复测、逐轮失载分析及额外代价见 receipts/A。",
        "## B 全程学习与 C 同父对照",f"微调种子为 1701、1702、1703。候选冻结状态为 {bool(manifest['candidate_freeze'])}，新盲测启动状态为 {manifest['new_blind_opened']}。"
        " 完整教师、真实教师前缀后的学生续演、从 frame0 执行的纯学生及低层工程试验在逐案表有独立身份。",
        "| C 分支 | 微调种子 | 实付 / 保留更新 | 开发成功 / 实跑 | 短窗存活 / 实跑 | 训练额外真物理子步 |","|---|---:|---:|---:|---:|---:|"]
    for f in cost["C_forks"]:
        gd=[r for r in rows if r["lane"]=="C" and r["group"]=="development" and r.get("training_seed")==f["seed"] and r.get("branch")==f["variant"]]
        short=next((s for s in cost["C_short"] if (s["variant"],s["seed"])==(f["variant"],f["seed"])),{})
        report.append(f"| {f['variant']} | {f['seed']} | {f['paid']}/{f['retained']} | {sum(r['success'] for r in gd)}/{len(gd)} | {short.get('survived',0)}/{short.get('cases',0)} | {f['native_substeps']:,} |")
    report+=task_tables(root,rows,formal)
    report+=["","## 视频与恢复",f"MM02 的四条原轨迹共 {len(videos)} 个全程或局部视频。[同回合视频索引](../{OUT.as_posix()}/videos/mm02/index.json)"]
    for example in read(root/"videos/mm03/examples.json").get("videos",[]):
        label="完整教师" if example["teacher_decisions"] else "全程学生"
        report.append(f"[{label} · {example['episode']} · {example['ordered_events']}/12 事件](../{OUT.as_posix()}/videos/mm03/{example['file']})")
    if manifest["first_pure_success"]:
        report.append(f"[MM03 首次纯学生全程成功](../{OUT.as_posix()}/videos/mm03/first_student_full_1080p.mp4)")
    report+=["进入 AutoDL 的 /root/autodl-tmp/dog-and-arm-mm03 后执行下列命令。","\x60\x60\x60bash\nbash scripts/multimodal/mm03_session.sh /root/autodl-tmp/mm03-20261126\n.venv/bin/python -m scripts.multimodal.mm03_launch status\n\x60\x60\x60",
        f"[状态与可恢复包](../{OUT.as_posix()}/manifest.json) · [实际预算](../{OUT.as_posix()}/budget.json) · [逐案结果](../{OUT.as_posix()}/physical_cases.jsonl)"]
    # Consecutive table lines belong together; prose and headings are separated by blank lines.
    body="";prev=""
    for line in report:
        body+=("\n" if line.startswith("|") and prev.startswith("|") else "\n\n" if body else "")+line
        prev=line
    (repo/REPORT).parent.mkdir(exist_ok=True)
    (repo/REPORT).write_text(body.rstrip()+"\n")
    state=repo/"PROJECT_STATE.md"
    s=state.read_text()
    start,end="<!-- mm03-live -->","<!-- /mm03-live -->"
    i=s.find(start);j=s.find(end)
    entry=(f"{start}\n## {stamp[:16].replace('T',' ')} 北京时间 · MM03 实际进度\n\n{summary} "
           f"云端 {status}。原始回合与完整包位于 {root}。"
           f"[实测报告]({REPORT.as_posix()}) · [恢复清单]({OUT.as_posix()}/manifest.json)\n{end}")
    if i<0:
        title,rest=s.split("\n",1);s=title+"\n\n"+entry+"\n"+rest
    else:
        if j<i:raise ValueError("Incomplete live status section")
        s=s[:i]+entry+s[j+len(end):]
    state.write_text(s)
    log=repo/"DAILY_WORK_LOG.md"
    with log.open("a") as f:
        f.write(f"\n### {stamp[:16].replace('T',' ')}｜MM03 {milestone}（北京时间）\n\n{summary} "
                f"已结束且有回执的物理回合 {len(rows):,} 个，累计 {cost['episode_substeps']:,} 子步。"
                f"额外真前向、恢复短窗、方向检查及在跑进程分别见[账本]({OUT.as_posix()}/budget.json)"
                f"与[恢复清单]({OUT.as_posix()}/manifest.json)。发布时保留原始轨迹、完整包及各次退出日志。\n")
    return manifest

