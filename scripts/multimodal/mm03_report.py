"""Summarize durable MM03 receipts at a publication boundary without touching simulation data."""
from collections import Counter, defaultdict
import csv
from pathlib import Path
import json
import os
import shutil

from scripts.multimodal.mm03_launch import UNITS, alive, now, read, state_file, write

OUT = Path("results/multimodal/mm03_20261126")
REPORT = Path("reports/MULTIMODAL_MM03_RESULTS.md")
SLUG = "kaiwen123-yang/dog-and-arm"
CF_LATENCY = Path("performance/20261126-cf-latency")


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
        receipt=read(folder/"receipt.json")
        rec=receipt or read(folder/"progress.json")
        if not rec:continue
        retained=int(rec.get("retained",rec.get("step",0)))
        paid=rec.get("paid",retained)
        spend=rec.get("paid_model_cost",rec)
        if not receipt and (folder/"applied.jsonl").is_file():
            # An optimizer can advance past its most recent durable recovery package.
            applied=list(lines(folder/"applied.jsonl"))
            paid=max(paid,len(applied))
            spend={k:max(spend.get(k,0),sum(row.get(k,0) for row in applied))
                   for k in ("native_substeps","model_queries")}
        b.append(dict(stage=spec["stage"],method=spec.get("method"),seed=spec.get("seed"),
            round=spec.get("round",0),retained=retained,paid=paid,path=str(folder),
            native_substeps=spend.get("native_substeps",0),model_queries=spend.get("model_queries",0),
            full=rec.get("full"),deploy=rec.get("deploy")))
    c=[]
    for f in sorted((root/"C").glob("*/seed*/applications.jsonl")):
        recs=list(lines(f))
        stable=read(f.parent/"receipt.json") or read(f.parent/"progress.json")
        c.append(dict(variant=f.parent.parent.name,seed=int(f.parent.name[4:]),paid=len(recs),
            retained=stable.get("retained",stable.get("step",0)),bc_rows_paid=256*len(recs),
            model_gradient_updates=sum(s["model_queries"]>0 and s["grad_trajectory"]>0 and s["coefficient"]>0 for s in recs),
            model_queries=sum(s["model_queries"] for s in recs),native_substeps=sum(s["native_substeps"] for s in recs),
            full=str(f.parent/"final.pt") if (f.parent/"final.pt").is_file() else None))
    cs=[]
    for f in sorted((root/"C").glob("*/seed*/short_recovery.json")):
        data=read(f)
        cs.append(dict(variant=f.parent.parent.name,seed=int(f.parent.name[4:]),cases=len(data),
            survived=sum(x["survived_32"] for x in data),native_substeps=sum(x["physical_substeps"] for x in data),
            wm_queries=sum((x["physical_substeps"]+9)//10 for x in data)))
    bridge=read(root/"C/bridge/bridge.json") or read(root/"C/bridge/progress.json")
    direction=read(root/"C/directional_response.json")
    parity=read(root/"A/cpu_parity/comparison.json")
    additional={"C/true_forward_optimization":sum(x["native_substeps"] for x in c),
                "C/short_recovery_evaluation":sum(x["native_substeps"] for x in cs),
                "C/directional_check":direction.get("native_substeps",0),
                "B/true_forward_optimization":sum(x["native_substeps"] for x in b)}
    perf=root/"performance/20261126-throughput"
    additional["performance/native_replay_and_judge_checks"]=(
        read(perf/"cf_native_profile.json").get("true_physics_substeps",0)
        +read(perf/"native_scoring_comparison.json").get("diagnostic_native_substeps",0)
        +read(perf/"cached_native_windows.json").get("diagnostic_native_substeps",0))
    latency=root/CF_LATENCY
    transfer=root/"performance/20261127-cf-transfer"
    additional["performance/native_transfer_comparison"]=read(transfer/"live_native_overlap.json").get("actual_diagnostic_substeps",0)
    storage_incidents = list((root/"B/rounds").glob("r*/H9-WM/seed*/paired/recovery_disk_full/receipt.json"))
    if storage_incidents:
        additional["B/interrupted_native_writes"] = sum(read(p)["uncommitted_native_substeps"] for p in storage_incidents)
    additional["performance/cf32_latency_diagnostics"]=sum(read(latency/file).get(field,0) for file,field in (
        ("full_h9_parity.json","captured_native_substeps"),("partial_direct23_parity.json","captured_native_substeps"),
        ("live_native_overlap.json","actual_diagnostic_substeps"),("cf_profile.json","native_substeps"),
        ("native_wheel_results.json","diagnostic_native_substeps")))
    recovery=read(latency/"r08_recovery.json")
    if recovery:
        additional["B/checkpoint_state_reconstruction"]=recovery["recomputed_native_substeps"]
    high=sum(x["paid"] for x in b if x["stage"] not in ("wm","bridge"))
    high_by_stage=Counter()
    for x in b:
        high_by_stage[x["stage"]]+=x["paid"]
    diagnostics={"C_cap_calibration":read(root/"C/calibration.json").get("steps",0),
                 "C_model_and_native_direction":direction.get("model_queries",0),
                 "C_local_fp64_direction":read(root/"C/directional_local_fp64.json").get("model_queries",0),
                 "C_short_recovery":sum(x["wm_queries"] for x in cs)}
    return dict(as_of_beijing=now(),low_updates=sum(x["paid"] for x in a),B_high_updates=high,
        B_updates_by_stage=dict(high_by_stage),B_primary_high_updates=high-high_by_stage["cost"],
        B_cost_sensitivity_updates=high_by_stage["cost"],C_diagnostic_model_queries=diagnostics,
        B_training_model_queries=sum(x["model_queries"] for x in b),
        C_training_model_queries=sum(x["model_queries"] for x in c),
        C_actor_updates=sum(x["paid"] for x in c),wm_updates=sum(x["paid"] for x in b if x["stage"]=="wm"),
        bridge_updates=sum(x["paid"] for x in b if x["stage"]=="bridge")+bridge.get("paid",0),critic_updates=0,
        completed_episodes=len(rows),episode_substeps=sum(physics.values()),
        extra_substeps=additional,accounted_native_substeps=sum(physics.values())+sum(additional.values()),
        physical_by_group=dict(sorted(kinds.items())),A_stages=a,B_stages=b,C_forks=c,C_short=cs,
        C_comparison_bridge=bridge,parity_receipt=parity,
        recovery_optimizer_applications=recovery.get("recomputed_optimizer_applications",0),
        accounting="Completed native case receipts and logged optimization/short-window steps. An open episode counts when it commits. Render playback integrates zero steps. Recovery recomputation and performance checks are listed separately.",
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
    small=("background_handoff.json","A/design.json","A/channel_results.json","A/command_reference.json","A/budget.json","A/low/compatibility.json",
           "A/completion.json","A/complete.json","B/teacher_registration.json","B/candidate_freeze.json",
           "B/completion.json","C/parent.json","C/calibration.json","C/directional_response.json","C/contact_anchor_inventory.json",
           "C/directional_local_fp64.json","C/development_anchors.json","C/selection.json","C/bridge/bridge.json",
           "service/upgrade1.json","resources/native_models/index.json","A/low/summary.json","A/low/development_results.json",
           "A/cpu_parity/comparison.json","A/low/block2_design.json","parent_receipt.json","resources/worker_targets.json","B/low_abi_readback.json","B/prefix_p6_parity_pull.json",
           "B/prefix_p6_parity_push.json","C/native_pool_changes.jsonl")
    for name in small:
        slimcopy(root/name, out/"receipts"/name)
    for lane,globs in (("A",("low/seed*/block*/train_result.json","parity/*.json")),
                       ("B",("models/*/seed*/*.json","rounds/r*/block.json","rounds/r*/collection_complete.json",
                             "warm/schedules/*.json","rounds/r*/schedules/*.json","rounds/r*/low_seed*.json",
                             "rounds/r*/*/seed*/*/receipt.json","rounds/r*/wm/seed*/receipt.json","cost/seed*/train/receipt.json")),
                       ("C",("*/seed*/receipt.json","*/seed*/short_recovery.json","schedules/*.json"))):
        for pattern in globs:
            for src in (root/lane).glob(pattern):
                slimcopy(src,out/"receipts"/src.relative_to(root))
    for src in (root/"videos").glob("*/*"):
        if src.suffix in (".json",".mp4") and ".partial" not in src.name:
            slimcopy(src,out/"videos"/src.relative_to(root/"videos"))
    for src in (root/"attempts").glob("*/*.json"):
        slimcopy(src,out/"execution"/src.relative_to(root))
    for pattern in ("C/handoffs/*.json","B/coordinator_refresh*ack.json","resources/allocation_changes.jsonl",
                    "B/rounds/r*/H9-WM/seed*/paired/recovery_disk_full/receipt.json"):
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
            if s.get("latest_deploy") and s["latest_deploy"]!=s.get("best_deploy"):
                slimcopy(Path(s["latest_deploy"]),out/"models/L16"/f"seed{seed}"/"latest_deploy.pt")
    winner=read(root/"C/selection.json").get("selected_model_variant")
    if winner:
        for src in (root/"C"/winner).glob("seed*/deploy.pt"):
            slimcopy(src,out/"models/C"/winner/src.parent.name/"deploy.pt")


def scored(n,total):
    return f"{n}/{total}" if total else "待评测"


def case_csv(path, rows):
    if not rows:
        return
    from learning.multimodal.judge import PHASES
    fields=["method","seed","partition","scene","side","goal","success","ordered_events","teacher_steps",
            "physics_steps","failure","failure_phase","max_door_deg","checkpoint","source_case"]
    with path.open("w",newline="",encoding="utf-8-sig") as f:
        writer=csv.DictWriter(f,fieldnames=fields+[phase+"_s" for phase in PHASES],lineterminator="\n")
        writer.writeheader()
        for row in rows:
            value={k:row.get(k) for k in fields}
            first=row.get("first_failure") or {}
            value.update(failure=first.get("reason"),failure_phase=first.get("phase"),
                         max_door_deg=row.get("maximum_hinge_deg"),source_case=row["result"])
            for e in row.get("events",[]):
                value[e["phase"]+"_s"]=e["time_s"]
            writer.writerow(value)


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
    from scripts.multimodal.mm03_speed_receipt import FILES, SUBDIR, summarize, paragraph
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
    archive = read(root/"storage/cold_archive.json")
    if archive:
        manifest["cold_archive"] = "execution/storage/cold_archive.json"
        write(out/manifest["cold_archive"], archive)
    mapped_dir=root/"performance/20261127-mapped-seeds"
    mapped_check=read(mapped_dir/"full_membership.json")
    mapped_decision=read(mapped_dir/"decision.json")
    if mapped_check:
        dest=out/"performance/shared_camera"
        for name in ("parity.json","full_membership.json","gradient_repeat.json",
                     "production_registration.json","production_allocation.json",
                     "window_1.json","window_2.json","window_3.json","decision.json",
                     "windows.py","check.py","forecast.json","forecast_mapped.py",
                     "production_prepare_stages.json","prep_observer.py"):
            slimcopy(mapped_dir/name,dest/name)
        manifest["shared_camera_evidence"]="performance/shared_camera/full_membership.json"
        if mapped_decision:
            manifest["shared_camera_concurrency"]="performance/shared_camera/decision.json"
    transfer=root/"performance/20261127-cf-transfer"
    transfer_result=read(transfer/"decision.json")
    h7=read(transfer/"h7_comparison.json")
    if h7:
        dest=out/"performance/native_transfer"
        for name in ("h7_comparison.json","h7_check.py","h7_baseline.json","full_h9_parity.json","partial_direct23_parity.json",
                     "live_native_overlap.json","registration.json","decision.json","production.json","compare.py","forecast.json"):
            slimcopy(transfer/name,dest/name)
        manifest["h7_sampling_evidence"]="performance/native_transfer/h7_comparison.json"
        if transfer_result:
            manifest["native_transfer_comparison"]="performance/native_transfer/decision.json"
    speed = summarize(root)
    if speed:
        manifest["performance_evidence"]="performance/summary.json"
        for name in (*FILES,"summary.json"):
            slimcopy(root/SUBDIR/name,out/"performance"/name)
    latency=root/CF_LATENCY
    latency_summary=read(latency/"summary.json")
    latency_text=""
    if latency_summary:
        evidence=out/"performance/cf32_latency"
        for name in ("summary.json","forecast.json","elastic_registration.json","elastic_trial.json",
                     "b_ordinary_overlap.json","b_ordinary_lease_test.json","b_ordinary_production_lease.json",
                     "full_h9_parity.json","partial_direct23_parity.json","live_native_overlap.json","cf_profile.json",
                     "native_wheel_results.json","ordinary_tail_trial.json","ordinary_capacity.json","native_loading.json",
                     "r08_recovery.json","latency_forecast.py","prepare_latency_evidence.py","README.md"):
            slimcopy(latency/name,evidence/name)
        for test in sorted(latency.glob("r[0-9][0-9]-eight")):
            for name in ("registration.json","baseline.json","challenger.json","decision.json"):
                slimcopy(test/name,evidence/test.name/name)
        for name in ("registration.json","baseline.json","challenger.json","decision.json","single_tail.py"):
            slimcopy(latency/"r08-tail"/name,evidence/"r08-tail"/name)
        manifest["cf32_latency_evidence"]="performance/cf32_latency/summary.json"
        if (latency/"forecast.json").is_file():
            manifest["current_forecast"]="performance/cf32_latency/forecast.json"
        latency_text=latency_summary["summary_zh"]
    trial_dir=root/"performance/cf32-three-seeds-20261126"
    comparison=read(trial_dir/"decision.json")
    compare_text=""
    if comparison:
        dest=out/"performance/cf32_concurrency"
        for name in ("README.md","registration.json","two.json","three.json","decision.json","forecast.json",
                     "measure.py","control.py","forecast.py"):
            slimcopy(trial_dir/name,dest/name)
        old,new=(read(trial_dir/f"{key}.json") for key in ("two","three"))
        chosen_name={"two":"两路","three":"三路"}[comparison["winner"]]
        compare_text=(f"在同一轮 H9-WM 真物理配对中，两路每分钟实付 {old['updates_min']:.1f} 次更新，"
                      f"三路实付 {new['updates_min']:.1f} 次，已采用{chosen_name}。"
                      f"两种配置分别测量 {old['elapsed_s']:.0f} 和 {new['elapsed_s']:.0f} 秒。")
        manifest["cf32_concurrency_comparison"]="performance/cf32_concurrency/decision.json"
        if (trial_dir/"forecast.json").is_file():
            manifest["cf32_concurrency_forecast"]="performance/cf32_concurrency/forecast.json"
    write(out/"manifest.json",manifest)
    write(out/"budget.json",cost)
    (out/"physical_cases.jsonl").write_text("".join(json.dumps(r,ensure_ascii=False,separators=(",",":"))+"\n" for r in rows))
    mirror_records(root,out)
    resc=[r for r in rows if r["lane"]=="A" and r["group"]=="rescue"]
    teach=[r for r in rows if r["lane"]=="B" and r["group"]=="teachers"]
    formal=[r for r in rows if r["lane"]=="B" and (r["group"]=="formal" or r["group"].startswith("formal/"))]
    case_csv(out/"formal_cases.csv",formal)
    case_csv(out/"diagnostic_evaluation.csv",[r for r in rows if r["lane"]=="B" and
             (r["group"] in ("cost/disclosed","isolated_teacher","first_success_reloads"))])
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
    if speed:
        report+=["## 训练吞吐",paragraph(speed),
                 f"[等预算阶段、实际GPU采样和数值对照](../{OUT.as_posix()}/performance/summary.json)"]
    if compare_text:
        report+=[compare_text+f" [逐分钟数据与完成时间估算](../{OUT.as_posix()}/performance/cf32_concurrency/README.md)"]
    if latency_text:
        report+=[latency_text+f" [同批次计时、生产吞吐与最新估时](../{OUT.as_posix()}/performance/cf32_latency/README.md)"]
    report+=["","## 视频与恢复",f"MM02 的四条原轨迹共 {len(videos)} 个全程或局部视频。[同回合视频索引](../{OUT.as_posix()}/videos/mm02/index.json)"]
    for example in read(root/"videos/mm03/examples.json").get("videos",[]):
        label="完整教师" if example["teacher_decisions"] else "全程学生"
        report.append(f"[{label} · {example['episode']} · {example['ordered_events']}/12 事件](../{OUT.as_posix()}/videos/mm03/{example['file']})")
    if archive:
        report.append(f"已完成阶段的旧评测数组和完整 CF32 曝光原件按云端原路径在 H 盘建索引。"
                      f"训练使用的回放字段、回合判分和学生视频渲染输入保留在 AutoDL。"
                      f"当前有 {archive['released_groups']}/{archive['planned_groups']} 个批次已通过 H 盘回读并在云端完成释放。"
                      f" [恢复位置与逐项查找方法](../{OUT.as_posix()}/{manifest['cold_archive']})")
    if mapped_check:
        report.append(f"在第 21 轮同一份冻结成员上，{mapped_check['episodes']:,} 条轨迹共享原始相机文件。"
                      f"完整读取测试的显存峰值为 {mapped_check['peak_cuda_GiB']:.2f} GiB。"
                      f" [图像与批次核验](../{OUT.as_posix()}/performance/shared_camera/parity.json)")
    if mapped_decision.get("complete"):
        rates="、".join(f"{k} 个种子 {v:.1f}" for k,v in mapped_decision["rates"].items())
        report.append(f"第 22 轮同轮配对每分钟实付更新为 {rates}。后续优先允许 {mapped_decision['winner']} 个种子并发，"
                      f"每轮再按实际可用内存和显存分配。 [配对实测](../{OUT.as_posix()}/performance/shared_camera/decision.json)")
    if h7:
        report.append(f"H7 对 {h7['files']:,} 份旧回放建立索引，已验证的索引重读用时 {h7['index_seconds'][-1]:.2f} 秒。"
                      f"相同行序与 RNG 状态下，物理窗口准备吞吐为原来的 {h7['loader_throughput_ratio']:.2f} 倍。"
                      f" [H7 抽样与恢复核验](../{OUT.as_posix()}/performance/native_transfer/h7_comparison.json)")
    if transfer_result and transfer_result.get("valid"):
        report.append(f"CF32 单项传输与合并传输的同轮实付吞吐分别为 {transfer_result['reference_updates_min']:.1f} "
                      f"和 {transfer_result['candidate_updates_min']:.1f} 次/分。"
                      f" [四个生产窗口与所选配置](../{OUT.as_posix()}/performance/native_transfer/decision.json)")
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
    speed_note=(latency_text+" ") if latency_text else ""
    entry=(f"{start}\n## {stamp[:16].replace('T',' ')} 北京时间 · MM03 实际进度\n\n{summary} "
           f"云端 {status}。原始回合与完整包位于 {root}。"
           f"{speed_note}[实测报告]({REPORT.as_posix()}) · [恢复清单]({OUT.as_posix()}/manifest.json)\n{end}")
    if i<0:
        title,rest=s.split("\n",1);s=title+"\n\n"+entry+"\n"+rest
    else:
        if j<i:raise ValueError("Incomplete live status section")
        s=s[:i]+entry+s[j+len(end):]
    state.write_text(s)
    log=repo/"DAILY_WORK_LOG.md"
    day=stamp[:10]
    new_day=not any(line.startswith("## "+day) for line in log.read_text().splitlines())
    with log.open("a") as f:
        if new_day:
            f.write(f"\n## {day}（北京时间）\n")
        f.write(f"\n### {stamp[:16].replace('T',' ')}｜MM03 {milestone}（北京时间）\n\n{summary} "
                f"已结束且有回执的物理回合 {len(rows):,} 个，累计 {cost['episode_substeps']:,} 子步。"
                f"额外真前向、恢复短窗、方向检查及在跑进程分别见[账本]({OUT.as_posix()}/budget.json)"
                f"与[恢复清单]({OUT.as_posix()}/manifest.json)。发布时保留原始轨迹、完整包及各次退出日志。\n")
        if speed and "提速" in milestone:
            f.write("\n"+paragraph(speed)+f" [测量记录]({OUT.as_posix()}/performance/summary.json)\n")
        if compare_text and "三种子并行" in milestone:
            f.write("\n"+compare_text+f" [配置、原始更新计数与估时]({OUT.as_posix()}/performance/cf32_concurrency/)\n")
        if latency_text and "空闲算力" in milestone:
            f.write("\n"+latency_text+f" [逐段计时与预算]({OUT.as_posix()}/performance/cf32_latency/README.md)\n")
    return manifest

