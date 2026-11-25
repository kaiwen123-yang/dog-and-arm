"""Publish the measured terminal MM-02 artifacts into an isolated Git checkout."""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from scripts.multimodal.mm02_summary import BRANCHES, PHASES, main as aggregate


CODE = Path(__file__).resolve().parents[2]
DEST = Path("results/multimodal/mm02_20261125")
REPORT = "reports/MULTIMODAL_MM02_RESULTS.md"
BJ = timezone(timedelta(hours=8))
NAMES = dict(zip(BRANCHES, ("监督", "模型式 H32")))
EVENTS = ("驶近", "停稳", "到把手", "抓持", "开到目标", "持稳", "释放", "撤臂", "释放后保持", "收臂", "退出", "最终停稳")
TOKEN = "mm02-frozen-20261125"


def read(p):
    return p.read_text(encoding="utf-8")


def data(p):
    return json.loads(read(p))


def jsonlines(p):
    return [json.loads(s) for s in read(p).splitlines() if s]


def write(p, s):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name+".mm02-tmp")
    tmp.write_text(s.rstrip()+"\n", encoding="utf-8")
    tmp.replace(p)


def put(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name+".mm02-tmp")
    shutil.copyfile(src,tmp)
    tmp.replace(dst)


def sha(p):
    digest=hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):
            digest.update(chunk)
    return digest.hexdigest()


def score(r):
    return f"{r['pure_student_successes']}/{r['pure_student_denominator']}"


def counts(v):
    return "、".join(f"{k} ×{n}" for k,n in sorted(v.items(),key=lambda x:(-x[1],x[0]))) or "无"


def table(headers, rows):
    def line(items):
        return "| " + " | ".join(str(x).replace("|","／") for x in items) + " |"
    return "\n".join([line(headers),line(["---"]*len(headers)),*(line(r) for r in rows)])


def moment(s):
    return datetime.fromisoformat(s.replace("Z","+00:00")).astimezone(BJ)


def round_table(a, rounds):
    rows=[]
    for n in range(1,rounds+1):
        key=f"round{n}"
        phys=a["partitions"]
        rec=phys[key+"/recovery_train"]
        val=phys[key+"/recovery_validation"]
        def coverage(groups):
            vals=[r["recovery"] for r in groups.values()]
            return f"{sum(r['statuses'].get('h32_complete',0) for r in vals)}/{sum(r['attempts'] for r in vals)}"
        mixed=[phys[key+"/collection"][b]["mixed"] for b in BRANCHES]
        dev=[phys[key+"/development"][b]["pure"] for b in BRANCHES]
        rows.append([n,score(dev[0]),score(dev[1]),"/".join(str(sum(r["completed_event_counts"].values())) for r in dev),
                     coverage(rec),coverage(val),f"{100*sum(r['teacher_decisions'] for r in mixed)/sum(r['decisions'] for r in mixed):.1f}%"])
    return table(["轮次","监督开发","H32 开发","顺序事件总数 监督/H32","训练恢复完整/实际","验证恢复完整/实际","混合回合教师决策占比"],rows)


def angle_table(pairs):
    rows=[]
    for p in sorted(pairs,key=lambda x:(x["scene"],x["side"],x["branch"])):
        if p["partition"]!="formal":
            continue
        ratios=["NA" if v is None else f"{v:.4f}" for v in p["ratio_15_25"]]
        rows.append([p["scene"],p["side"],NAMES[p["branch"]],*(f"{v:.3f}" for v in p["final_deg"]),
                     f"{p['angle_difference_25_minus_15_deg']:.3f}"," / ".join(ratios)])
    return table(["场景","方向","学生","15° 指令终角","25° 指令终角","终角差（25−15）","实测进度比（15/25）"],rows)


def render(run, a, learning, freeze, decision, teacher, pairs, reloads, first, finish, video):
    rounds=freeze["round"]
    formal=[a["partitions"]["formal"][b]["pure"] for b in BRANCHES]
    gain=a["matched_model_gain"]["formal"]["all"]
    main=f"第 {rounds} 轮固定末点，监督纯学生 {score(formal[0])}，模型式 H32 纯学生 {score(formal[1])}。同初态完整成功率之差为 {gain['model_gain_percentage_points']:+g} 个百分点。"
    chosen=learning["pilot"]["physical_selection"]
    p=chosen["scores"]
    leaves=a["formal_by_scene_role"]
    col=[]
    for branch,f in zip(BRANCHES,formal):
        subset=leaves[branch]
        col.append([NAMES[branch],*(score(subset[s]) for s in ("nominal","validation","disclosed_regression","new_blind")),
                    score(f),f["cases_with_door_contact"],f["cases_with_bilateral_contact"]])
    terminal=table(["末点学生","训练名义","验证","旧测试回归","两个新盲场景","合计","触门案","双指案"],col)
    fail="\n".join(f"- {NAMES[b]}的首次失败为 {counts(r['first_failure_reason'])}。终止阶段为 {counts(r['first_failure_phase'])}。"
                   for b,r in zip(BRANCHES,formal))
    stage=table(["独立裁判事件","监督通过案","H32 通过案"],[[name,*(f["completed_event_counts"][key] for f in formal)]
               for key,name in zip(PHASES,EVENTS)])
    row=learning["actual_budget"]
    opt=table(["新增优化","保留","回滚","实付"],[[k, row[prefix+"_retained"],row[prefix+"_rollback"],row[prefix+"_actual"]]
              for prefix,k in (("actor","Actor（含 H32）"),("wm","WM H7"),("bridge","视觉映射"),("critic","Critic"))])
    times=learning["optimizer_block_wall_s"]
    choice=(f"按登记执行第 5、6 轮，较早轮次新增完整成功的匹配案有 {len(decision['new_complete_success'])} 个，"
            f"新增顺序事件涉及 {len(decision['new_side_goal_combinations'])} 个方向／目标组合。" if decision["extend"] else
            ("第 4 轮同一冻结学生已在两侧取得完整成功，训练于该轮结束。" if decision["round4_bilateral"] else
             f"第 3/4 轮相比第 1/2 轮的最佳匹配案，新增完整成功 {len(decision['new_complete_success'])} 案，新增顺序事件涉及 {len(decision['new_side_goal_combinations'])} 个方向／目标组合。按登记止于第 4 轮。"))
    rr=[]
    for r in reloads:
        rr.append([NAMES[r["branch"]],r["scene"],r["side"],r["goal"],r["physics_steps"],len(r["events"]),
                   "成功" if r["success"] else r["first_failure"]["reason"]])
    addr=str(run)
    count=lambda role:sum(r["success"] for r in teacher if r["case_role"]==role)
    technical=("第一次 R1 BC 数据加载遇到 mmap 文件描述符上限。日志保留在 AutoDL 的 logs/r1_*_bc.log，"
               "在优化器尚未更新时修复。") if any("Too many open files" in read(pth)
               for pth in (run/"logs").glob("r1_*_bc.log")) else ""
    timespan=f"首批学生与末包重载评分记录覆盖 {first:%Y-%m-%d %H:%M} 至 {finish:%Y-%m-%d %H:%M}（北京时间）"
    if first.date()!=finish.date():
        timespan+=f"，实验于 {first:%m 月 %d 日} 启动、{finish:%m 月 %d 日} 完成末包复测"
    threshold=next((name for i,name in enumerate(EVENTS) if all(f["completed_event_counts"][PHASES[i]]==0 for f in formal)),None)
    gap=(f"正式 40 案中，首个两支均未达成的顺序事件为「{threshold}」。" if threshold else
         f"完整任务通过覆盖可从正式盲测分母和独立复测逐案核对。")
    movie=(f"首个纯学生完整通过来自 `{video['episode_id']}`。同一物理回合从 frame0 连续回放，"
           f"{video['frames']} 帧，物理时长 {video['physics_s']:.3f} s，1920×1080、25 fps 原速。[首个完整成功视频](../{DEST.as_posix()}/videos/first_student_success_1080p.mp4)"
           if video else "全部纯学生回合均未完成原判 12 事件，本轮纯学生完整成功视频为 0。")
    totals=a["costs"]
    collect=sum(v["cases"] for k,v in totals.items() if k.endswith("/collection"))
    development=sum(v["cases"] for k,v in totals.items() if k.endswith("/development"))
    repeats=sum(v["cases"] for k,v in totals.items() if k.startswith("repeats/"))
    training=sum(v["cases"] for k,v in totals.items() if k.endswith("/recovery_train"))
    validation=sum(v["cases"] for k,v in totals.items() if k.endswith("/recovery_validation"))
    wmrows=[]
    for g,group in learning["rounds"][-1]["dynamics"]["prediction_validation"].items():
        h=group["horizons"].get("32",{})
        for name,title in (("recorded_action_open_loop","记录动作开环"),("student_imagined_closed_loop","学生想象闭环")):
            v=h.get(name) or {}
            fmt=lambda k: "NA" if v.get(k) is None else f"{v[k]:.4f}"
            wmrows.append([g,title,h.get("windows",0),fmt("angle_mae_deg"),fmt("handle_error_mm"),
                           fmt("vision_rmse_at_exposures"),fmt("held_start_rmse_same_exposures")])
    text=f"""# MM-02 全身在轨纠正与多模态开门实测

{timespan}。{main} {gap}

{terminal}

纯学生从 frame0 连续积分，M1 自由基座与被动铰链门使用 native MuJoCo 3.3.0。2 ms 物理、20 ms 决策、100 ms 腕部曝光和 23 路动作保持原定义。两个新盲场景的 16 案已计入 40 个正式案。延长决定与最终冻结在盲测之前完成。桌面 Piper 由用户择时，本轮真实 Piper/M1 运动命令为 0。

## 从纠正标签到端点冻结

P6 教师在 frame0 固定臂 home 与腿 leg_rest，依据实际后继每 2 ms 更新底盘、每 10 ms 更新机械臂，在 20 ms 边界给出整组 pre-bias 标签。四个名义接口案 {count('adapter')}/4，原教师与提取接口的边界姿态、请求和 12 个事件时刻均一致。两个新盲场景的隔离教师为 {count('blind_teacher_only')}/8。教师依赖仿真状态，以上均为教师控制物理回合。

共同 12,000 步完整父包提供初始 12 个训练回合。BC 用有效专家请求，WM 使用实际执行动作及真实后继，学生的上一动作来自实际执行者。旧示范 17 个来源、35,026 个合格标签。fixed/adaptive 各完成 512 次匹配更新，开发完整成功 {p['fixed']['success']}/8、{p['adaptive_slope_only']['success']}/8，顺序事件总数 {p['fixed']['events']} 和 {p['adaptive_slope_only']['events']}，限位／自碰首败 {p['fixed']['limit_self']} 和 {p['adaptive_slope_only']['limit_self']}。登记选择 `{chosen['chosen']}` 作为两个主分支的共同父点。

每轮重新采集两条学生各 12 个纯回合和 12 个训练混合回合。每 200 ms 选择全身执行者，块内每 20 ms 重查控制。两支共享合格数据，每批 128 旧示范和 128 新纠正，实际行序、预算与权重继承已按两支的训练账本逐轮核对。模型支的 H32 锚点来自真实学生访问状态，独立恢复求解器、教师、10 拍历史与曝光相位，按教师动作实际积分。教师未来只用于轨迹损失。执行学生仅用当前及历史腕 RGB-D、本体、语言和实际动作时标。

{round_table(a,rounds)}

{choice} 依据仅含固定节点的纯学生开发回合。混合回合及恢复短分支均单列。[延长决定](../{DEST.as_posix()}/extension_decision.json) · [末点冻结](../{DEST.as_posix()}/terminal_freeze.json)

## 物理失败、目标指令与模型收益

{fail}

{stage}

同一正式分支、场景和方向内，15°/25° 的初始物理、腕部帧和本体观测相同。进度为（终角减初角）除以（目标角减初角），保留负值及超过 1 的数值。末角差为 25° 指令减 15° 指令。

{angle_table(pairs)}

模型式分支在 20 个配对案中的顺序事件数比监督多 {gain['model_event_wins']} 案、相等 {gain['model_event_ties']} 案、少 {gain['model_event_losses']} 案。六个关节按每个真实子步的实测角相对当拍伺服目标计算 RMSE，再分别除以各自的允许角度范围。逐案表保留最小带符号限位余量、驻站误差、触门和双指时长、介入拍及失败时刻。[完整逐案索引](../{DEST.as_posix()}/physics/aggregates_cases.jsonl) · [角度配对](../{DEST.as_posix()}/physics/aggregates_goal_pairs.jsonl)

末点独立验证的 H32 统计使用同一批实际曝光拍比较预测视觉与保持起帧。学生在轨组开环使用记录的实际动作，教师恢复和原成功示范组开环使用实际教师动作。学生想象闭环每拍重查策略。表内为预测误差，正式原生物理成功率见开篇。

{table(["验证来源","预测方式","32 拍窗","门角 MAE（°）","把手误差（mm）","视觉 RMSE","保持起帧 RMSE"],wmrows)}

## 计算支出、视频与恢复

{opt}

模型式策略实际保留 {row['h32_actor_retained']:,} 次 H32 更新，含在 Actor 总数内。训练想象查询保留 {row['h32_queries_retained']:,}、实际 {row['h32_queries_applied']:,} 次。首批梯度与有限差分诊断另用 {row['h32_diagnostic_queries']:,} 次，独立预测验证另用 {row['validation_student_imagined_queries']:,} 次。已继承共同 Actor 12,000 次与 WM 2,800 次。监督配对更新累计 {times.get('supervised_aggregate_paired',0):.1f} s，模型式配对更新 {times.get('model_trajectory_paired',0):.1f} s，另计 WM {times.get('wm',0):.1f} s、桥接 {times.get('bridge',0):.1f} s。以上为相应优化循环实测用时，部分重叠运行。{technical}

新采训练 {collect} 回合，轮末开发 {development} 案，另有初始 12、短配对开发 16、教师接口 4、隔离教师 8、正式 40、末包重载 {len(reloads)}、成功复测 {repeats}。训练和验证恢复分别 {training}/{validation} 条，32 拍不足的分支保留合法前缀。全部记录的原生 2 ms 子步为 {a['total_recorded_physics_steps']:,}，含恢复与独立快照复走。完整预算、优化器、各阶段采样、首批 H32 梯度和冻结方向导数见[学习账本](../{DEST.as_posix()}/learning_evidence.json)、[动力学与真实恢复核对](../{DEST.as_posix()}/dynamics_summary.json)和[物理汇总](../{DEST.as_posix()}/physics/aggregates.json)。

{movie} 旧 P6 教师和旧 546 混合策略视频保留原控制身份。

末点两条主链各从完整训练包在独立进程重新加载，使用原名义前拉 15° 的同一开发场景。

{table(["重载学生","场景","方向","目标°","子步","顺序事件","结果"],rr)}

AutoDL 代码在 `{CODE}`，完整实验在 `{addr}`。每轮实际输入数据成员、真实快照、教师状态、恢复短轨迹、采样序列、优化器、随机状态与全部中间节点留在运行目录。发布树保留两份末点训练包和部署包、WM 完整包、绑定末点编码器的视觉桥接、末轮样本序列与成员清单。可从[恢复清单](../{DEST.as_posix()}/manifest.json)逐项定位。后续首先从已冻结的逐案物理记录审查最早未通过的顺序事件，再决定新轮登记。
"""
    return text,main,gap,movie


def add_section(path, body, *, date=None):
    s=read(path)
    first=f"<!-- {TOKEN}-start -->"
    last=f"<!-- {TOKEN}-end -->"
    block=f"{first}\n{body.strip()}\n{last}"
    if first in s:
        updated=re.sub(re.escape(first)+r".*?"+re.escape(last),lambda _:block,s,count=1,flags=re.S)
    elif date:
        heading=re.search(rf"(?m)^## {re.escape(date)}(?:[^\n]*)$",s)
        if heading:
            following=re.search(r"(?m)^## ",s[heading.end():])
            position=heading.end()+following.start() if following else len(s)
            updated=s[:position].rstrip()+"\n\n"+block+"\n\n"+s[position:].lstrip()
        else:
            updated=s.rstrip()+f"\n\n## {date}（北京时间）\n\n"+block+"\n"
    else:
        title,rest=s.split("\n",1)
        updated=title+"\n\n"+block+"\n\n"+rest.lstrip()
    write(path,updated)


def close(run, repo):
    if not (repo/".git").exists() or repo.resolve()==run.resolve():
        raise ValueError("A publication Git checkout distinct from the raw run is required")
    freeze=data(run/"terminal_freeze.json")
    decision=data(run/"extension_decision.json")
    last=freeze["round"]
    reloads=data(run/"reload/cases.json")
    if (last!=(6 if decision["extend"] else 4) or freeze["decision"]!=decision
            or len(reloads)!=2 or {r["branch"] for r in reloads}!=set(BRANCHES)
            or any(r["sha"]!=freeze["branches"][r["branch"]]["training_sha256"] for r in reloads)):
        raise ValueError("Terminal choice or independent two-checkpoint reload receipts are incomplete")
    if data(run/"current.json")["phase"]!="physics_and_training_complete":
        raise ValueError("Await the training and terminal physics completion receipt")
    root=repo/DEST
    physical=run/"aggregates"
    aggregate(run,physical,True)
    learn=run/"learning_evidence.json"
    if not learn.is_file() or data(learn).get("partial") or data(learn).get("completed_rounds")!=last:
        torch_python=CODE/".conda/envs/arm-and-dog/bin/python"
        subprocess.run([str(torch_python),"-m","scripts.multimodal.mm02_learning_evidence",str(run)],cwd=CODE,check=True)
    ev,agg=data(learn),data(physical/"aggregates.json")
    teach=data(run/"teacher_audit/teacher_cases.json")
    pairs=jsonlines(physical/"aggregates_goal_pairs.jsonl")
    cases=jsonlines(physical/"aggregates_cases.jsonl")
    if len(teach)!=12 or len(ev["rounds"])!=last or ev["partial"] or agg["stage"]!="frozen":
        raise ValueError("Missing measured final training, teacher or physics evidence")
    videos=run/"videos"
    video=None
    if any(r["mode"]=="pure" and r["success"] for r in cases):
        video=data(videos/"first_student_success_1080p.json")
        if (not video["success"] or not video["full_decode_and_pts_verified"] or
                (video["width"],video["height"],video["fps"],video["first_step"])!=(1920,1080,25,0)):
            raise ValueError("Expected the verified original-speed first pure student success video")
        for name in ("first_success.json","first_student_success_1080p.json","first_student_success_1080p.mp4"):
            published = root/"videos"/name
            if published.is_file():
                if sha(published) != sha(videos/name):
                    raise ValueError(f"First-success artifact differs from the previously published one: {name}")
            else:
                put(videos/name,published)
    for path in physical.glob("aggregates*"):
        put(path,root/"physics"/path.name)
    for name in ("learning_evidence.json","collection_pilot.json","restore_probes.json","terminal_freeze.json","extension_decision.json"):
        put(run/name,root/name)
    dynamics = run/"dynamics_summary.json"
    if not dynamics.is_file() or data(dynamics).get("terminal_freeze") != freeze:
        subprocess.run([str(CODE/".conda/envs/arm-and-dog/bin/python"),"-m","scripts.multimodal.mm02_dynamics_summary",str(run)],cwd=CODE,check=True)
    put(dynamics,root/"dynamics_summary.json")
    put(run/"teacher_audit/teacher_cases.json",root/"teacher/teacher_cases.json")
    for name in ("formal","reload"):
        put(run/name/"cases.json",root/"physics"/(name+"_cases.json"))
    term=run/f"round{last}"
    files={}
    for b in BRANCHES:
        p=freeze["branches"][b]
        for key,filename in (("training","full.pt"),("deployment","deploy.pt")):
            src=Path(p[key])
            if sha(src)!=p[key+"_sha256"]:
                raise ValueError(f"Frozen checkpoint bytes changed in {src}")
            dest=root/"terminal"/b/filename
            put(src,dest)
            files[f"{b}/{key}"]=dict(source=str(src),published=dest.relative_to(repo).as_posix(),sha256=p[key+"_sha256"])
    for name in ("wm.pt","trajectory_bundle.pt"):
        src=term/"dynamics"/name
        dest=root/"terminal"/"dynamics"/name
        put(src,dest)
        files[name]=dict(source=str(src),published=dest.relative_to(repo).as_posix(),sha256=sha(src))
    for name in ("actor_members.json","wm_membership.json","schedule.json","schedule.npy"):
        put(term/name,root/"terminal"/name)
    for n in range(1,last+1):
        src=run/f"round{n}"
        out=root/"rounds"/f"round{n}"
        for srcpath,target in ((src/"dynamics/wm_validation.json",out/"wm_validation.json"),
                               (src/"model_trajectory/paired/trajectory_diagnostic.json",out/"h32_first_batch.json"),
                               (src/"dynamics/bridge_training.json",out/"bridge_training.json"),
                               (src/"dynamics/wm_training.json",out/"wm_training.json"),
                               (src/"actor_members.json",out/"actor_members.json"),
                               (src/"wm_membership.json",out/"wm_membership.json")):
            put(srcpath,target)
    first=min(moment(r["recorded_utc"]) for r in data(run/"initial/cases.json"))
    finish=max(moment(r["recorded_utc"]) for r in reloads)
    text,head,gap,movie=render(run,agg,ev,freeze,decision,teach,pairs,reloads,first,finish,video)
    manifest=dict(method=ev["method"],status="completed_frozen",registration_base="ea30e5fb8b686e084e6a49e1cfa6845aa3dcb7e4",
                  round=last,terminal_freeze_utc=freeze["utc"],last_reload_beijing=finish.isoformat(),
                  code_root=str(CODE),run_root=str(run),parent="/root/autodl-tmp/mm01-20261125",terminal_packages=files,
                  training_recovery=dict(round_directory=str(term),schedule="schedule.npy",members="actor_members.json",
                                         raw_cases="roundN/{collection,development,recovery_train,recovery_validation}",
                                         solver_teacher_history="roundN/collection/<case>/snapshots/<tick>.pkl",
                                         selected_anchors="roundN/recovery_{train,validation}/selection.json",
                                         full_actor_optimizer_rng="roundN/<branch>/paired/final.pt",
                                         full_wm_optimizer_rng="roundN/dynamics/wm.pt",bound_bridge="roundN/dynamics/trajectory_bundle.pt"),
                  actual_budget=ev["actual_budget"],inherited=ev["inherited_not_charged"],physical_cost=agg["costs"],
                  total_recorded_native_steps=agg["total_recorded_physics_steps"],
                  formal=agg["matched_model_gain"]["formal"],video=video,hardware_motion_commands=0)
    write(root/"manifest.json",json.dumps(manifest,indent=2,ensure_ascii=False,allow_nan=False))
    write(repo/REPORT,text)
    when=f"{finish:%Y-%m-%d %H:%M} 北京时间"
    short=f"## {when} · MM-02 已结束\n\n{head} {gap}"
    start_date=first.date().isoformat()
    end_date=finish.date().isoformat()
    crossed=(f"实验从 {start_date} 跨至 {end_date}。" if first.date()!=finish.date() else "")
    refs=f"[MM-02 实测报告]({REPORT}) · [冻结权重与恢复清单]({DEST.as_posix()}/manifest.json) · [接续入口](prompts/NEXT_RUN.txt)"
    for name in ("AGENTS.md","README.md","PROJECT_STATE.md"):
        add_section(repo/name,short+"\n\n"+crossed+"正式两支各 20 案，新盲测共 16 案；教师适配 4 案、隔离教师可行性 8 案另列。桌面 Piper 由用户择时。\n\n"+refs)
    for name in ("MULTIMODAL_ALGORITHM_PLAN_20261125.md","RESEARCH_ROADMAP.md"):
        add_section(repo/"docs"/name,short+f"\n\n[原生物理末点、预算和恢复目录](../{REPORT})")
    add_section(repo/"docs/GOAL_GAP_20261125.md",short+"\n\n"+movie+
                f"\n\n[末点评测与目标角](../{REPORT}) · [逐案物理与干预](../{DEST.as_posix()}/physics/aggregates_cases.jsonl)")
    budget=ev["actual_budget"]
    journal=(f"### {finish:%H:%M}｜MM-02 末点冻结、盲测与独立重载（北京时间）\n\n"
             f"{crossed}{head} 两支完整末包已各独立重载 1 案。实付 Actor {budget['actor_actual']:,}、WM {budget['wm_actual']:,}、"
             f"bridge {budget['bridge_actual']:,}、Critic {budget['critic_actual']}。新增仿真 {agg['total_recorded_physics_steps']:,} 子步。"
             f"真实硬件运动命令 0。\n\n{refs}")
    add_section(repo/"DAILY_WORK_LOG.md",journal,date=end_date)
    prompts=(f"接续 kaiwen123-yang/dog-and-arm 的 MM-02 冻结实测，阅读 PROJECT_STATE.md 顶部、DAILY_WORK_LOG.md 最新北京时间条目、"
             f"{REPORT}、{DEST.as_posix()}/manifest.json 和 physics/aggregates.json（在同一结果目录）。\n\n"
             f"{head} {gap} 两个新盲场景已完成末点评价，下次使用时列为已揭晓回归。"
             f"原完整权重、优化器、数据成员、采样器、教师和求解器快照由 manifest 指向 {run}。"
             "需要审查时先逐案复核匹配的成功、失败和同初态目标角差，保留原 12 事件、新盲测与旧回归分母。"
             "新增训练或新方法按后续用户指定另行登记，桌面 Piper 由用户择时。")
    for name in ("MULTIMODAL_START.txt","NEXT_RUN.txt","B0_START.txt"):
        write(repo/"prompts"/name,prompts)
    print(json.dumps(dict(status="artifacts_written",end_round=last,output=str(root),report=str(repo/REPORT)),ensure_ascii=False))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run",type=Path)
    parser.add_argument("publish_checkout",type=Path)
    args=parser.parse_args()
    close(args.run.resolve(),args.publish_checkout.resolve())
