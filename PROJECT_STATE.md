# 项目状态：完整多模态腿臂算法主线

## 2026-11-25 21:37 北京时间 · MM-01 已进入实训

AutoDL 自由底盘全机仿真已经完成训练用腕部 RGB-D 采集。两侧的 15° 和 25° 均经同初态 P6 路径核实，新独立裁判在四条物理轨迹上各通过 12 个事件。正式教师采集 24 条，20 条常规路径成功，4 条训练扰动失败。另保留旧 546 混合 u1 原生背推 25° 的 2,719 个合格标签及其合成重渲身份。共同监督策略和感知/接触世界模型已在训练，学生成绩待全程评测。[任务与评分登记](config/multimodal/evaluation.json) · [数据与来源](results/multimodal/mm01_20261125/data/)

## 2026-11-25 21:08｜当前主线：完整多模态算法；桌面部署由用户择时

用户最新明确：固定桌面Piper部署由用户根据自己的时间安排，当前直接推进完整多模态算法。桌面实机、手眼、硬件在线和桌面成功均不是当前研发前置；不把改变顺序写成桌面已经通过。

当前执行MM-01：在自由底盘M1＋Piper＋腕相机环境，贯通RGB-D/语言/本体数据、监督策略、世界模型、可微短时优化和完整物理评测。环境/数据、策略、WM三包并行，依赖就绪后同轮集成。当前源码有相机几何和状态学习链，尚无训练用RGB-D/文本流水线及真正的多模态Actor，这些必须实际实现与训练。

[当前集中计划](docs/MULTIMODAL_MM01_EXECUTION_20261125.md) · [完整算法路线](docs/MULTIMODAL_ALGORITHM_PLAN_20261125.md) · [MM-01登记](results/planning/multimodal_mm01_20261125/registration.json) · [启动词](prompts/MULTIMODAL_START.txt)

桌面[Piper计划](docs/DESKTOP_PIPER_TRANSFER_PLAN_20261125.md)与专用启动词保留，用户择时执行；日后实测数据作为增量接入，不阻塞本轮。当前不发送真实Piper/M1运动命令。NEXT_RUN、MULTIMODAL_START、B0_START同文；PIPER_DESKTOP_START独立。旧两期串行登记和下方历史“先桌面/先标准通过”的调度语句均由本节覆盖。

本次实际完成源码接口审查、当前计划/提示词/状态调整与发布，新增Actor/WM/Critic=0/0/0、物理步=0、硬件动作=0；未在AutoDL启动MM-01训练。原standard-v1/u10000、RefXY2/+200按原成绩封存；旧546混合u1完整成功及1080p视频保留为教师/能力来源，不冒充新多模态结果。

## 2026-11-25｜RefXY2 已执行结案，默认入口为查看已有视频

两支各保留 +200 Actor / +2,000 WM / +4,000 Critic，配对实付 400 / 4,000 / 8,000，回滚为零。主段 252 案，延长复测 12 案。native/pull 的处理支最小 P95 为 10.255 mm，超过 shared_0 最大 P95 9.910 mm，差 0.345 mm。登记的 native 非退化条件未满足。本轮于 +200 结案，RefXY2 完整成功 0/12，V0=0，合格双侧回报 NA。

本聊天显式启动的配对与视频收束工作并行。登记提交为 2bbb9fec，交付基于含视频说明的 de0a4d6c。项目默认继续查看已有 546 维混合策略的双侧视频，后续研究等待另行指定。原 standard-v1 封存于 u10000。

[独立配对实测](reports/B0_REFXY2_TRANSFER_RESULTS_20261125.md) · [逐案与视频清单](results/b0/refxy2_pair_20261125/assessment/physics_manifest.json) · [已有双侧成功视频](reports/SUCCESS_VIDEOS_AND_SCOPE_20261125.md)

## 2026-11-25 18:21｜视频交付范围：已有完整成功视频，停止自动推进标准迁移

用户现在以“能查看比较完整的成功流程仿真视频”为当前收束依据。已核对同一个546维混合策略u1的native双侧原视频：前拉74.28s、背推54.44s，均从frame0连续完成13阶段，原判passed=true。方法含参考前馈、累计15000动作BC及解析补偿；原官方标准链仍未完成，不能混写身份。

[立即查看视频与说明](reports/SUCCESS_VIDEOS_AND_SCOPE_20261125.md) · [视频核验清单](results/b0/success_video_review_20261125/manifest.json) · [当前入口](prompts/NEXT_RUN.txt)

**停止继续自动安排SuperMimic标准迁移；RefXY2计划保留但不启动，原u10000封存。** 原B0-04/null/NA/标准V0=0作为未完成结论保留，不再为本次视频交付追加训练或D/C/seed/H。当前先交付并查看已有成果，后续研究待用户另行指定。本次新增训练/仿真0，没有检查或终止远端未知作业。下方旧“下一轮执行”属于历史，不能覆盖本节。

## 2026-11-25｜当前入口：RefXY2 独立配对已登记，尚未执行

787d5e38 的 A–D 已完成并复核。原平台四案位置合格 0 拍、ready 0/75，最近 7.933–13.826 mm；不存在已证明可直接修复的同契约反例，但原 H32 同一 WM 的 9 组 AD–割线反号仍未闭合。原 standard-v1/u10000 保持 B0-04、候选 null、合格双侧回报 NA、V0=0，Warp/native 接触各 0/10、full 0/4、free 0/60。

[当前审查](reports/B0_PREGRASP_ROUND_REVIEW_20261125.md) · [下一配对计划](docs/B0_REFXY2_TRANSFER_PLAN_20261125.md) · [机器登记](results/b0/pregrasp_review_20261125/next_registration.json) · [目标差距](docs/GOAL_GAP_20261125.md) · [启动词](prompts/NEXT_RUN.txt)

下一执行轮为独立 `SuperMimic-M1Piper-RefXY2-v1` 与等宽恒零控制：完整恢复同一 u10000，仅 Actor 增当前参考根相对自身的 XY2；保留 `execution_recipe=official_flow_s0_v1` 与原 WM/Critic/损失/Ratio/H32/物理/裁判。各 +200，双侧原物理证据支持时同轮同步 +1000。主段实际优化上限 420/4200/8400，延长总上限 2020/20200/40400；全轮共享回滚20/200/400。主段三套原评分252案，完整延长440案，条件资格另列。一次冻结FP64模型内复核并行，不作WM门。

本次只完成审查和计划发布，没有新增训练或仿真。新两维改变Actor信息，结果独立标识，不能改写原标准成功；先迁移冻结，再开发算法/VLA。首个原判完整成功立即交同回合原速V0。以下旧“当前/下一轮/待决定”均按历史日期及当时提交阅读，A–D和原u15000不重复启动；当前执行范围以本节、新计划及启动词为准。

## 2026-11-25｜集中兼容性轮实测完成

原预抓平台四案均有连续 76 拍姿态合格，位置为 0 拍，最近 7.933–13.826 mm。四个锚点确认 Actor 的水平平移输入别名。76 条 0.25 ms 闭环响应均走完 H32；沿原目标正向扰动首动作，真实同钟和端点误差同时改善 3/12。四案超时后按原参考钟继续均未建立双指接触，在参考 open 阶段触发原物理终止。

standard-v1 仍为 B0-04、候选 null、合格双侧回报 NA、V0=0。u10000 原 Warp/native 接触各 0/10、full 0/4、free 0/60。新增优化 Actor/WM/Critic 为 0/0/0。原主链封存于 u10000。 独立适配提案 SuperMimic-M1Piper-RefXY2-v1 只增加当前参考根相对机体的两维水平偏移，以等宽恒零输入作对照；提案仍待单独决定。

[独立实测报告](reports/B0_PREGRASP_COMPATIBILITY_RESULTS_20261125.md) · [机制决定](results/b0/standard_pregrasp_compatibility_20261125/mechanism_decision.json) · [实际成本](results/b0/standard_pregrasp_compatibility_20261125/budget_and_recovery.json) · [诊断视频](results/b0/standard_pregrasp_compatibility_20261125/diagnostic_video_manifest.json)

## 2026-11-25｜u10000 已审查，下一轮集中查明预抓失败

固定79fd3cf的official_flow_s0_v1已结案于u10000，不延长u15000。末点原Warp/native接触各0/10，frame0完整0/4、free0/60；候选null、合格完整双侧回报NA、V0=0，仍B0-04。主链累计10000 Actor/100000 WM/200000 Critic、102414758有效转移。先完成固定官方标准迁移冻结，再开发算法/VLA。

[最新审查](reports/B0_U10000_REVIEW_20261125.md) · [下一集中轮](docs/B0_PREGRASP_COMPATIBILITY_PLAN_20261125.md) · [机器登记](results/b0/official_u10000_review_20261125/next_registration.json) · [目标差距](docs/GOAL_GAP_20261125.md) · [启动词](prompts/NEXT_RUN.txt)

预抓末拍79–113mm是到冻结端点的距离；同时TCP距把手7.84–11.51mm，参考已到grasp。下一轮围绕原平台期一次完成既有12轨迹分解、冻结输入/原目标核对、有限动作响应及4条完整参考钟诊断。默认0优化；仅有具体实现错误时同轮最小修复、control/fix各200原更新，另列一次回滚预留。原主链结案、旧结果与预算保持，不自动换观测/奖励、暂停参考或重开WM门。

本次是仓库审查与计划发布，未新增训练/仿真。后续首次原裁判完整成功立即交同episode连续原速V0；失败后延续诊断视频不能代替成功视频。下方旧“当前/下一轮”按相应日期的历史记录阅读，以本节和新登记为当前入口。

## 2026-11-25 14:35｜u10000 主段完成，本轮不延长

u10000 原 Warp/native 接触各 0/10，双后端双侧完整 0/4、free 0/60。四案均完成停车，在预抓取超时。前拉短入口从无双指载荷建立 362 ms 接触，同包复现；父包已具备的两项背推接触在末点双后端均失去。预算收束，不启动 u15000。B0-04，候选 null，合格双侧回报 NA，V0=0。[最终报告](reports/B0_OFFICIAL_FLOW_CONTINUATION_20261125.md)

## 2026-11-25 14:19｜主段到 u10000，u7500 评分已齐

u10000 完整包已写出，累计 10000 Actor / 100000 WM / 200000 Critic、102414758 有效转移，端点评测进行中。u7500 Warp 接触 1/10，双后端从头完整 0/4，free 0/60。B0-04、候选 null、合格双侧回报 NA、V0=0。见[本轮报告](reports/B0_OFFICIAL_FLOW_CONTINUATION_20261125.md)。

## 2026-11-25 11:44｜u5000 完整回读、u5100 滚动保存，tmux 继续至 u10000

核验时已越过 u5100 并完成 u5102。u5100 处本轮保留新增 109 Actor / 1090 WM / 2180 Critic，回滚成本 0。u5000 独立开发块完成，整段双指 H32 有前拉 2 窗、背推 17 窗。原物理主节点 u7500/u10000 尚待评测。B0-04、候选 null、合格双侧回报 NA、V0=0。[运行报告](reports/B0_OFFICIAL_FLOW_CONTINUATION_20261125.md) · [现场回执](results/b0/standard_official_flow_continuation_20261125/tmux_progress.json)

## 2026-11-25 11:35｜已接用户指令恢复本轮执行

从暂停提交 45c8a0a 接续，AutoDL 重启 u4991 → u10000 主段与独立节点评测。[启动记录](results/b0/standard_official_flow_continuation_20261125/restart_after_pause.json) · [逐案诊断](results/b0/standard_official_flow_continuation_20261125/readiness_u004991.json)。10:58 暂停回执保留为历史记录。

## 2026-11-25｜用户已暂停续训，末点 u4991

固定 be398cc3 的同链新段使用 [运行登记](results/b0/standard_official_flow_continuation_20261125/run_manifest.json)。北京时间 10:58 已依用户指令停止本轮主训练排队、评测排队及监控。新增训练、回滚均为零。下次仅在用户明确要求后，从 u4991 恢复并执行首个新更新 u4992。[父包独立恢复](results/b0/standard_official_flow_continuation_20261125/restored_u004991.json) · [实际四案补采及原轨迹对照](results/b0/standard_official_flow_continuation_20261125/readiness_u004991.json) · [冻结窗口](results/b0/standard_official_flow_continuation_20261125/readiness_windows.json)。B0-04，候选 null，合格双侧回报 NA，V0=0。[暂停回执](results/b0/standard_official_flow_continuation_20261125/pause.json)。

## 2026-11-25｜u4991 审查完成，当前下一轮登记

**同一官方链已学到双后端背推局部保持/5°开门，但完整从头尚未完成预抓取。** 实测末点仍0124ad7的u4991：Warp/native各2/10；本轮70接触案6份通过（相同两项的三组复现）、12阶段事件；20完整回合0成功，20驶近/9停车/0预抓取；free0/300，全部7s且TCP精度失败。B0-04、最终候选null、合格完整双侧回报NA、V0=0。局部成功入口已有200ms真实前缀后的双指，不能当从头抓持已学会。[审查](reports/B0_OFFICIAL_FLOW_CONTINUATION_REVIEW_20261125.md) · [复算](results/b0/official_flow_review_20261125/evidence_audit.json) · [差距](docs/GOAL_GAP_20261125.md)

u4991完整任务首失败分别为Warp前拉预抓早触门14.066s、Warp背推轮失载11.594s、native前拉预抓超时15.564s、native背推停车超时11.994s。末帧XY/航向均在20mm/2°内；native背推最佳稳定770ms/1s，三条预抓回合最佳连续ready0/150ms。下一轮贯通端点/姿态与连续ready欠项，不以TCP到把手距离替代端点误差。J2上端缺口现仅参考跨度1.031%，旧59.6%不再是现状；u3000当前策略合法all层H32约12.9/11.6mm，整段双指H32仍零，旧四格不重复。

**下一轮完整恢复u4991至累计u10000，有实测物理依据延长至u15000。** 主段保留新增5009/50090/100180，延长后本轮累计10009/100090/200180；整轮回滚预留100/1000/2000，仅支付未保留执行。u5000是保存/开发点，不单独停一轮。旧40000WM实付上限与additional_budget_authorized=false原样封存，新段独立登记。[计划](docs/B0_OFFICIAL_FLOW_NEXT_PLAN_20261125.md) · [预算](results/b0/official_flow_review_20261125/next_registration.json) · [一致启动词](prompts/B0_START.txt)

父现场 /root/autodl-tmp/dog-and-arm-b0-temporal-v1/.official-continuation-bdb72d8；父recovery位于results/b0/standard_official_flow_continuation_20261124/recovery.json，配套raw目录的resume_004991/checkpoint_004991.pt。累计4991/49910/99820、valid51124715；Ratio pending0，距下一阈值3605有效转移。下一轮恢复全部网络/优化器/统计/replay/RNG/live lanes/solver/servo，不仅载权重。新输出使用20261125独立段，先适配旧入口硬编码的u1000父校验、首更新u4992、路径/节点与滚动一致保存；学习cfg严格相同。

本轮只审查并登记计划，未改学习核心、cfg、旧结果或运行新训练/仿真。有限日志与输出适配也尚待执行轮实施。先标准迁移冻结，再开发算法；真实完整成功立即交连续原速视频，同轮继续原资格。以下为历史事实和当时计划，不覆盖本节。

## 2026-11-25 03:35 封存状态（旧段预算记录）

u3000 主段完成后依据同钟双侧物理改善继续。u4000 Warp 原接触首次通过背推 `open_5` 和 `stable_grip`；u4991 同包 Warp 与 native MuJoCo 3.3.0 都为 2/10，同样两项通过。五节点完整从头 0/20、free 0/300。B0-04，最终候选空，合格完整双侧回报 NA，完整成功视频 0。保留主链累计 4,991 Actor / 49,910 WM / 99,820 Critic，51,124,715 有效转移。本轮实际支出含中断为 3,997 / 40,000 / 79,940，原 WM 上限已用尽。剩余到 u5000 的 9 次更新待额外预算授权。[实训报告](reports/B0_OFFICIAL_FLOW_CONTINUATION_20261124.md) · [独立 manifest](results/b0/standard_official_flow_continuation_20261124/baseline_manifest.json) · [预算决定](results/b0/standard_official_flow_continuation_20261124/budget_decision.json) · [下一入口](prompts/NEXT_RUN.txt)

## 2026-11-25 01:53 北京时间｜同一标准链已冻结 u2000

已完成 u1500 和 u2000 物理评测，两节点 Warp 原十项均 0/10，完整双后端均 0/4，free 均 0/60。u2000 Warp 背推恢复停车；纯 Actor 背推保持入口有 2 ms 双指，未到第二次策略查询。继续在同链跑向 u3000。当前 B0-04、候选空、合格回报 NA、V0 为 0。[本轮报告](reports/B0_OFFICIAL_FLOW_CONTINUATION_20261124.md) · [计数与逐案](results/b0/standard_official_flow_continuation_20261124/baseline_manifest.json)

## 2026-11-24 23:40 北京时间｜同链续训已保留 u1001

现场 u1001 完整快照已在独立进程恢复。父 u1000 的四组统计、replay、RNG、在线 Ratio 以及三网络和优化器均已继承。四次中断的额外训练成本另列。两项冻结诊断和 u1000 的 256×64 独立策略开发块已经完成。目前处于 B0-04，u1500 以后物理验收待跑；续训状态、命令和预算见[本轮报告](reports/B0_OFFICIAL_FLOW_CONTINUATION_20261124.md)。大包和工作进程位于 AutoDL 的 `.official-continuation-bdb72d8`，以新目录的 `recovery.json` 和 `node_*.json` 为恢复入口。

## 2026-11-24 北京时间｜51a0133 已审查，同链从 u1000 接续

**官方在线主环已实际完成1000次H32；任务仍B0-04、候选null、合格完整双侧回报NA，完整成功视频0。** 本轮110个接触名义案0通过/0接触事件；24次frame0完整尝试0成功，但有15个驶近、11个停车完成事件，最远尚未完成预抓取。新Actor原free评测0/240，全部完成7s，失败是TCP精度（81案还失根位置精度），不能说全部摔倒。[审查](reports/B0_OFFICIAL_FLOW_ROUND_REVIEW_20261124.md) · [逐案复算](results/b0/official_flow_review_20261124/evidence_audit.json)

同一握持起点J2首命令持续趋近参考：u0→u1000前拉.80839→1.49640rad、背推.81404→1.14450rad；u1000仍饱和，原十项仍0/10。u200/u500两后端均完成双侧驶近和停车，u1000 Warp退回停车失败。新阶段/接触仍无突破，不能只用命令改善声称迁移成功。

下一轮执行[官方主链续训计划](docs/B0_OFFICIAL_FLOW_CONTINUATION_PLAN_20261124.md)：**完整恢复u1000，先累计u3000（新增2000H32/20000WM/40000Critic），有物理依据延长到u5000（本轮增量上限4000/40000/80000）**。保留proprio/history10、原官方在线统计/Ratio/10H7/H32与原物理门槛；不重启Actor，不切换rep_state/冷WM，不恢复WM误差放行门。checkpoint扩展、独立输出/父恢复和≤500tick覆盖留档是必要运行配套；cfg相等及完整恢复语义保持。

并行有限核对同包后端首分歧/overflow，以及u0/u1权重×统计四格前向；当前策略独立开发块按计划上限采集，不回灌训练、不作新门。主节点实评原十项、Warp/native双侧full、新Actor free和纯Actor接触；真完整成功立即交连续视频，同轮继续另一侧和已满足的原验收。没有确认bug也照常推进可运行的主链。

现场仍 /root/autodl-tmp/dog-and-arm-b0-temporal-v1/.official-flow-695f3d7；父包 results/raw_large/b0/official_flow_20261124/resume_001000 与 checkpoint_001000.pt，pending=0，剩4990有效转移到下一Ratio阈值。现场以真实包复核。新段输出/增量单列，旧结果与祖先成本保留。[预算登记](results/b0/official_flow_review_20261124/continuation_registration.json) · [启动词](prompts/B0_START.txt) · [目标差距](docs/GOAL_GAP_20261124.md)

本次是审查与计划发布，未运行新增训练/仿真/现场权重重载。以下原实验与历史计划保留当时语境，不覆盖本节。

## 2026-11-24 22:00 北京时间｜固定官方流程实训与完整任务尝试

独立 official_flow_s0_v1 已从 +850 WM-only 完成 u1000，实做 1,000 次 H32、10,000 个 H7 WM 批及 20,000 个 Critic 批。u1000 原 2 ms Warp 接触 0/10，完整名义 Warp 0/2、native 3.3.0 0/2。当前 B0-04，最终候选 null，合格完整双侧归一化回报 NA。 u1000 用尽本轮登记预算。原 Warp 前拉在停车阶段超时，背推在停车阶段出现夹指与非抓取部位的把手接触；native 双侧均在预抓取阶段失去工位约束。两端原接触十项各 0/10，末节点六个闭环接触验证入口均无双指持续，完整任务仍无成功。 原失败轨迹和恢复包均已留存。[独立报告](reports/B0_OFFICIAL_FLOW_RESULTS_20261124.md) · [manifest](results/b0/standard_official_flow_20261124/baseline_manifest.json) · [下一入口](prompts/NEXT_RUN.txt)

## 2026-11-24 北京时间｜完整官方流程对齐，新增完整任务视频交付

**用户再次明确：根本目标始终是完整按照固定官方SuperMimic迁移，达到或接近论文参照并冻结独立标准结果。** 完整任务仿真视频V0是新增交付，不能替代0.90参照/0.88接近带或B0正式资格。最新65c121b仍在B0-04、候选null、完整双侧回报NA；原正式0/10，新H32=0。本次只审查和发布计划，没有新增训练、仿真或成功视频。

下一轮按[官方完整流程对齐](docs/B0_OFFICIAL_FLOW_ALIGNMENT_20261124.md)和[执行计划](docs/B0_FULL_TASK_TRANSFER_PLAN_20261124.md)，校正真实采集→统计更新→Ratio→每次10批H7 WM（8存储帧/7次后继）→H32 Actor一次/Critic二十批的主环。原25%双块AND与50mm都是项目自设诊断，今后用于报告和定位，不再当Actor更新前置；65c121b在旧条件下的失败事实保持。

新主链为独立official-flow seed0：+850仅作WM-only warm-start，读取dyn及其中统计；Actor/Critic、优化器和online replay均按官方新建，学习率2e-4。+850不含sim_context，相关上下文由登记任务与配置补齐核验。旧B003/共同u0/旧优化器和gain32不作为新链初始化，既有训练成本全部披露，不能宣称从零复现。

H1混合、teacher固定配额、冻结WM统计、gain32等历史项目配方需要逐项追溯官方并明确处置，不能静默保留后称为原样迁移。精细物理时钟、混合动作单位、solver缓存与lane数据资格属于必要平台映射。撤销尚未发布、未执行的独立参考覆盖预训练分支，所有实际学习围绕同一官方主线推进；需要的参考支持核验按官方任务/数据接口落实。

从frame0开始的标准Actor完整nominal真实成功时，立即导出连续全程视频并继续另一侧。视频保留单episode物理trace/原判定，参数按[比例协议](docs/B0_FULL_TASK_VIDEO_PROTOCOL.md)同时列绝对量和分母；不凭一部视频宣布最终基线完成。[审查](reports/B0_JOINT_CONTACT_ROUND_REVIEW_20261124.md) · [复算](results/b0/joint_contact_review_20261124/audit_summary.json) · [启动词](prompts/B0_START.txt) · [目标差距](docs/GOAL_GAP_20261124.md)。

现场仍/root/autodl-tmp/dog-and-arm-b0-temporal-v1；+850/+990与两支旧u10 pending=2保留原身份。新初始化及恢复语义按官方对齐清单登记。下面旧“下一轮/前置资格”按历史阅读，不覆盖本节。

## 2026-11-24 北京时间｜联合接触轮已结束

B0-04，标准候选为 null，完整双侧回报为 NA。新增 30 个诊断 WM 批和 991 个预适配批（990 个留存、1 个计费中断步）。99 个十批块仅 +850 单点通过，+860 即有三项长窗重新越线；连续两块通过为 0/98。共同 u0 原 2 ms Warp 十项 0/10，六项首微步超 6 N。新 seed0 H32 更新为 0。

[独立报告](reports/B0_JOINT_CONTACT_RESULTS_20261124.md) · [manifest 与恢复](results/b0/standard_joint_contact_20261124/baseline_manifest.json) · [全节点分数](results/b0/standard_joint_contact_20261124/adapt/all_nodes.csv) · [唯一逐日日志](DAILY_WORK_LOG.md)。旧两支 u10 各 pending=2 原样保留；+850/+990 均是诊断恢复节点。本轮剩余 9 批不足另一完整资格块。

## 2026-11-24 北京时间｜870796a已审查，下一轮推进联合WM与接触闭环

**已审查870796a：B0-04、最终候选null、完整双侧物理回报NA。原正式50案全失败，30案首2ms超力；48个反复开发起点组合的纯Actor闭环均未在停止前建立双指。下一轮执行首十批WM定位、真实伺服饱和辨识、原联合分布预适配和单条seed0主链，首段目标u50，有物理收益继续并当轮接后续验收。**

本次复算50案result/return与48案闭环，预算与原分母一致。修正报告把u10在线H7损失误标为u1的一处文案；原数据未变。首10批WM后独立握持H32 TCP由约15–18mm增至0.54–0.89m；u0→u1 Actor统计未变。离线2H1→8H7与联合8H7→2H1、源比例和优化器初始化的切换须精确重放分离，尚未证为单一bug。两支各15360在线H7中open/hold与双指均为0，321个open/hold Actor抽样是失效前初态，不能当失败后污染删除。

按[新计划](docs/B0_JOINT_CONTACT_PLAN_20261124.md)：两支首十批＋一个顺序对照共30WM诊断批；先读已有首动作原数组，缺覆盖才补最多112条边界短轨迹；单链原联合源预适配首段≤500、证据支持累计≤1000（含交界预演），两个真实联合块后通过预登记开发保留线即进入H32，不必耗满预算。首段目标u50，u1/u10为检查点，有物理收益自动继续u100/u200及后续。原2msWarp/native3.3、6N和正式协议保持；不增加算法支线。

[审查](reports/B0_DYNAMICS_ROUND_REVIEW_20261124.md) · [机器复算](results/b0/dynamics_review_20261124/audit_summary.json) · [实验结果](reports/B0_DYNAMICS_TRANSFER_RESULTS_20261124.md) · [目标差距](docs/GOAL_GAP_20261124.md) · [完整启动词](prompts/B0_START.txt) · [NEXT_RUN](prompts/NEXT_RUN.txt)

现场 `/root/autodl-tmp/dog-and-arm-b0-temporal-v1`；大资产 `results/raw_large/b0/dynamics_20261124/`，旧两支u10各pending=2仅留诊断。新小结果计划另开 `results/b0/standard_joint_contact_20261124/`。本次未新训、未仿真、未重读现场大权重。以下历史“下一轮”不覆盖本节。

## 2026-11-24 北京时间｜细步训练与两支原 H32 集中轮已结束

**当前 B0-04，最终候选为空，完整双侧物理归一化回报 NA。** 11 个固定 Warp 窗口和四窗深度复核支持 0.25 ms 训练，外部伺服保持 2 ms，策略保持 20 ms。三源重采后，两套 C20 各预热 1,000 批。重标 +1000 六项预登记验证均优于同物理旧统计 +1000，在查看原 H32 结果前锁定为唯一实验 WM；控制为同身份 +0。历史 ff2d1e8 的 selected_wm 仍为空。

两支各到 u10，实际新增合计 20 H32、200 联合 WM、400 Critic，物理有效转移去重 23,921。新共用 u0 及两臂 u1/u10 原 Warp 正式十项共 50 案，全部失败、零阶段事件。实验 u10 正式前拉接近存续 2.720 s，背推接近 0.036 s，碰撞时 139.91 N；稳定握持两侧首 2 ms 为 51.04/33.18 N。48 案冻结策略闭环复测在停止前均未建立双指接触。两支均未达到延长条件，D、完整 Warp/C/native、独立 seed 和 H 均未进入。先完成并冻结标准迁移，再开发算法。[实验报告](reports/B0_DYNAMICS_TRANSFER_RESULTS_20261124.md) · [独立清单](results/b0/standard_dynamics_20261124/baseline_manifest.json) · [恢复入口](prompts/NEXT_RUN.txt)

## 2026-11-24 北京时间｜ff2d1e8已审查，下一轮执行C20有限H32与集中迁移

**仍在B0-04，原八节点未过WM保留条件，最终候选为空，完整双侧回报NA。** 本轮C20/T2各1000WM批、冻结u0正式0/10/6首2ms超力/0事件与预算已复算；新增Actor为0。连续solver bias接口已解决，当前T2递推失稳配方封存。C20首开度误差接近原q/v分量损失的解析折中28.537/43.351mm；它的首TCP/J2预测已改善，旧H32保持仍退化，不能追认原选模通过。

当前执行[新集中计划](docs/B0_DYNAMICS_TRAINING_PLAN_20261124.md)：实际训练Warp内固定11窗做2/1/0.5ms、同2ms外部控制缓存时钟的物理比较；需要数值适配则当轮统一接口与数据身份。复用已有首层函数保持重标做一套C20原损失对照，再按预登记规则锁一个实验WM，与C20+0开展有限u1/u10真实H32。两支合计20H32/200联合WM/400Critic，预热另记。新development_h32_pilot资格只用于机制实验，不改写ff2d1e8的selected_wm=null，不降低6N与原正式门槛。原2msWarp/native3.3成绩保留，细步证据单列。

有可重复物理改善即选一条链继续，不以u200默认收工；同包十项10/10后当轮D、连续双侧Warp/C/native，条件具备继续独立seed与三seed冻结H。先迁移成功、冻结独立结果，再开发算法。本次为审查/计划发布，未新增训练或仿真，未访问AutoDL重读大权重/原始数组。

[审查报告](reports/B0_TEMPORAL_ROUND_REVIEW_20261124.md) · [复算摘要](results/b0/temporal_review_20261124/audit_summary.json) · [原实验](reports/B0_TEMPORAL_TRANSFER_RESULTS_20261124.md) · [原manifest](results/b0/standard_temporal_20261124/baseline_manifest.json) · [完整启动词](prompts/B0_START.txt) · [NEXT_RUN](prompts/NEXT_RUN.txt) · [目标差距](docs/GOAL_GAP_20261124.md)

现场 `/root/autodl-tmp/dog-and-arm-b0-temporal-v1`，原response u200恢复另存且Ratio pending=1，先核现场并保留已有工作树。以下为实验回执和历史审查，旧“当前/下一轮”不覆盖本节。

## 2026-11-24 北京时间｜时间配对完成，B0-04 仍无有效 WM 出口

真实 2 ms 积分闭合。已修连续求解器 bias 并重采 12 个训练、6 个验证起点。C20/T2 使用同一保存的真实索引，各完成原 H1/H7 的 1,000 批；八个节点均未同时保住双侧首动作和原 H32 握持/多模式表现。T2 +1000 开度误差 16.89/30.72 mm，原握持 H32 TCP P95 达 434.56/488.61 mm。+200 时漏查 H7 裁剪前梯度峰值，后续 800 批 T2 单列为事后诊断。封存 u0 的正式十项在新树复测 0/10、6 案首 2 ms 超力、0 个阶段事件。新增 H32 更新为 0，候选为空，完整回报 NA。

从合法窗实测到高腕速并复现 native3.3 和 CPU/Warp3.16 在力限处的速度导数差；三个引擎两侧验证 hold 仍在首 2 ms 超力。现场 `/root/autodl-tmp/dog-and-arm-b0-temporal-v1`。原 response u200 及其 60 案继续保留。

[本轮报告](reports/B0_TEMPORAL_TRANSFER_RESULTS_20261124.md) · [独立 manifest](results/b0/standard_temporal_20261124/baseline_manifest.json) · [接续入口](prompts/NEXT_RUN.txt)

## 2026-11-24 北京时间｜753f1bc已审查，下一轮扩大为集中迁移推进

**B0-04、候选为空、完整双侧回报NA。** 最新独立60案/36案首2ms超力/0阶段事件和200H32/217,971有效在线区间已核对。数据贯通已完成，不能继续沿用旧轮“multimode没进联训”的解释。原20ms端点速度oracle仍低估两侧开度30.70/46.63mm；固定官方公式基于恒加速度合成。solver登记forward与连续采集的派生缓存身份还有一项未证实疑点。20ms残差含正式失败后诊断，不直接等于首2ms失败根因。本次只审查/复算和发布计划，未新训、未仿真、未读取现场大权重/原2ms数组。

用户追加要求一次性多推进。下一轮执行[集中迁移计划](docs/B0_TEMPORAL_COMPATIBILITY_PLAN_20261124.md)：并行核对时间/solver、数据/WM退化、原目标；集中修复已证平台问题；有证据才有限验证C20/T2时间适配，原网络/损失/外层H32保持；有效出口立即实训与原正式评分。u50/u200是检查点，有物理进展继续；停止无效配方后在同轮处理下一项明确问题。同一候选10/10即接D、完整双侧Warp/C/native，条件具备继续独立seed/三seed冻结H，不等另一份计划。算法开发仍在迁移成功之后。

[最新审查](reports/B0_RESPONSE_ROUND_REVIEW_20261124.md) · [复算摘要](results/b0/response_review_20261124/audit_summary.json) · [原实验报告](reports/B0_CONTACT_RESPONSE_RESULTS_20261124.md) · [实验manifest](results/b0/standard_response_20261124/baseline_manifest.json) · [完整启动词](prompts/B0_START.txt) · [简要接续](prompts/NEXT_RUN.txt) · [目标差距](docs/GOAL_GAP_20261124.md)

现场AutoDL `/root/autodl-tmp/dog-and-arm-b0-response-v1`；u200恢复 `results/b0/response_s0_to200_v1/cohort_state.pt` 有1次Ratio pending。旧轮与用户其他树修改保留；先核实现场再执行。以下是实验回执与历史审查，其中旧“下一轮”不覆盖本节。

## 2026-11-24 北京时间｜首动作响应与 WM 数据贯通轮已封存至 u200

**B0-04，最终候选为空，完整双侧物理回报 NA。** 12 个训练起点与 6 个独立验证起点已完成同状态 u0/旧 u200 首动作物理分支。旧 grip、多模式和本轮响应持续进入 H1/H7。新增预热 1,000 批后按独立验证保留情况选 +0，从 B0-03 新开 seed0，实际完成 200 H32、2,000 联合 WM、4,000 Critic 和 217,971 个有效在线区间。六节点原正式十项各 0/10，共 60 案、36 案首 2 ms 超力、0 阶段事件。背推释放存续从 40 到 964 ms，u200 前拉/背推 stable_grip 首步为 39.62/16.50 N，门槛 6 N。上一轮 27284e2 的 60 案独立保存。

现场为 AutoDL 的 dog-and-arm-b0-response-v1，u200 恢复文件有一次待调度 Ratio 更新。下一项是利用现有 2 ms 记录定位夹口端点积分残差和 J2 对夹口的局部响应。原裁判与标准链门槛继续执行。[本轮结果](reports/B0_CONTACT_RESPONSE_RESULTS_20261124.md) · [manifest](results/b0/standard_response_20261124/baseline_manifest.json) · [下一步](prompts/NEXT_RUN.txt)

## 2026-11-24 北京时间｜已审查 27284e2，下一轮处理首动作响应与 WM 数据贯通

**仍在 B0-04：六节点各 0/10，完整双侧物理回报 NA，没有最终候选。先完成标准迁移并冻结独立结果，再做算法开发。** 本次只核读代码/已提交结果、独立复算并发布计划，没有新训练或仿真，也未重新加载 AutoDL 的大权重/原始 NPY。

新增明确发现：新 `lanes_modes_v1` 数据进入 WM 预热，却未进入后续联训离线池；在线 open/hold 仅 1,087/219,677 区间且全部 terminal。同窗双指 H32 P95 在预热 15.65/16.45 mm 后，u10 回退到 127.19/149.47 mm。现有 u50 两状态首命令诊断满 20 ms 真实夹口 68.35/66.51 mm，两套 WM 只预测约 22–26 mm；该诊断含失败后积分，且训练 phase 与正式 event phase 不同，不能混成正式首 2 ms 的成绩。

下一轮执行 [首动作与 WM 数据计划](docs/B0_CONTACT_RESPONSE_PLAN_20261124.md)：补齐训练身份现场 Actor 查询及臂/夹口分支，持续接入新训练数据到原 H1/H7，分解原目标梯度，再从标准 B0-03 Actor 与选定 WM 新开一条固定 seed0 主链，实际 H32 与正式评分。旧 u200 不无依据机械续长。22 mm 条件范围不是动作安全上限，不加新奖励/BC/参考直通/解析补偿；其他算法与 VLA 后置。

[本轮审查](reports/B0_LANES_ROUND_REVIEW_20261124.md) · [只读复算](results/b0/lanes_review_20261124/audit_summary.json) · [独立实验结果](reports/B0_STANDARD_TRANSFER_BASELINE.md) · [最新实验 manifest](results/b0/standard_lanes_20261124/baseline_manifest.json) · [完整启动词](prompts/B0_START.txt) · [下一入口](prompts/NEXT_RUN.txt) · [目标差距](docs/GOAL_GAP_20261124.md)

现场接续 AutoDL `/root/autodl-tmp/dog-and-arm-b0-lanes-v1`，先核实进程、回执与资产。u200 恢复有 2 次 Ratio 待更新，不算已执行；已有修改保留。按北京时间维护唯一 [DAILY_WORK_LOG](DAILY_WORK_LOG.md)。以下保留本轮执行回执与更早快照，历史“下一轮”不覆盖本节。

## 2026-11-24 11:33 北京时间｜单配方逐 lane 迁移已实训至 u200

**B0-04 未通过，最终候选为空，完整双侧回报 NA。** 从 ee41ee3 接续，逐 lane 真实前缀/复位与跨块 episode 内 H7 已实现并实测。相同冻结策略、同等 128,000 个物理子步下，有效策略转移由旧采集的 3,135 条增至 7,593 条。新采训练/验证分别 512/192 lanes；原 H1/H7 预热新增 1,000 minibatch，冻结握持集 H32 TCP P95 由 50.53/40.36 降到 15.65/16.45 mm，选为出发权重。教师只参与世界模型动力学监督。

一条 seed0 链在 u0/1/10/50/100/200 各自的原入口正式十项均为 0/10。200 H32 对应 219,677 个有效策略转移，其中两侧各有 0 个整段 20 ms 持续双指。u200 稳定握持前拉/背推首 2 ms 即达 50.24/25.10 N，六个握持/开门条目首子步超力，所有阶段事件为 0。u200 背推接近耗尽参考仍无接触，释放等待到时限仍未就绪。同包 D、完整 Warp/C/native、独立 seed 和 H 未开启。老轮 230 案与新轮 60 案各保留原预算和身份。

主配方暂停追加更新。u50 策略在稳定握持入口发出 43.07/69.63 mm 夹口命令，同相位整段持续双指的 Warp 离线训练样本最大为 22.04/22.47 mm；同初态首动作替换也观察到联训 WM 长窗误差增大。下一轮先在训练身份覆盖实际首命令响应，检查到独立轨迹的误差，再决定联合学习预算。[独立结果](reports/B0_STANDARD_TRANSFER_BASELINE.md) · [新轮 manifest](results/b0/standard_lanes_20261124/baseline_manifest.json) · [恢复回执](results/b0/standard_lanes_20261124/restart_receipts.json) · [下一入口](prompts/NEXT_RUN.txt)

以下是本轮执行前的历史快照。

## 2026-11-24 北京时间｜已审查7180672，下一轮专注迁移

**先完成标准迁移并冻结独立结果，之后再做算法开发。** 当前仍为 B0-04，无最终候选，完整双侧物理归一化回报 NA。当前执行 [11月24日计划](docs/B0_STANDARD_TRANSFER_PLAN_20261124.md)，完整启动词 [B0_START](prompts/B0_START.txt)，简要接续 [NEXT_RUN](prompts/NEXT_RUN.txt)。

### 已确认的最新实验

实验端点 [7180672](https://github.com/kaiwen123-yang/dog-and-arm/commit/71806725b66e1aec0ac03536737edf31e669ac40)。八条 seed0 配置链、23组正式十项 Warp 名义，230案均失败，其中129案首2ms超力。两条单位配对u500各0/10，十片段共同effort均值0.22961/0.25963，不能代替完整任务回报。去重1,350 H32、13,500 WM、27,000 Critic、3,081,019完整有效转移。D、完整任务/C、同包native完整名义、独立seed1/2和H未开启。[审查](reports/B0_STANDARD_ROUND_REVIEW_20261124.md) · [独立结果](reports/B0_STANDARD_TRANSFER_BASELINE.md) · [实验manifest](results/b0/standard_baseline_20261124/baseline_manifest.json)

effort/reset、ReturnSampler、实际Ratio、逐clip末帧、握持WM数据/统计、lane-age已有真实实施和训练。u500是保持旧采样/调度的单位对照；最完整对齐组lane_age_s0_v1只有u50，不混用预算。固定统计u50的H7 15,707窗没有open/hold起点；Actor/H1 24,812起点中572为open/hold。已保留指力样本没有整个首20ms持续双指，其他样本力未知。首次物理失败的完整数值有效20ms仍入H1/Actor，不预设其被过滤。

### 下一轮实际工作

1. 以固定双源abc124c/dd51a9f和已对齐机制建立一条主配方，至多一个明确的小预算对照。
2. 对齐终止lane复位后持续采集；保留真实200ms前缀、独立时钟/history/上一动作和显式episode边界，H7不跨reset，预算/恢复准确。
3. 补训练身份的真实多接触模式20ms数据，以原H1/H7目标预热WM，再实际进行H32联合学习。教师仅用于WM；Actor仍为标准B0-03来源，想象初态来自当前在线replay。
4. 按双侧真实接触存续、门力、首次失效、阶段事件和独立WM误差决定后续训练。正式十项通过后再D、连续双侧Warp/C与同包native、独立seed、冻结后H；完整回报同时达协议0.90/0.88要求。

新采集生命周期与预热尚为计划。本次只读审查、文档修订和GitHub发布，没有新增训练或仿真。原始实验代码/配置/结果保留。标准迁移前不添加动作BC、参考直通、解析补偿、新奖励/风险头/phase-TD、课程、新网络或新任务；VLA等开发后置。[目标差距](docs/GOAL_GAP_20261124.md)

### 现场与交接

历史现场 AutoDL /root/autodl-tmp/dog-and-arm-b0-pair-v1，权重及cohort_state.pt恢复位置见 [训练清单](results/b0/standard_baseline_20261124/contact_training.json)。下次先核实工作树、进程/退出回执和大资产，已回收队列不重开，不清理其他工作树。P1–P6与B0-03 seed0继续继承，R/J混合成绩单列。详细问题处理按北京时间持续写 [DAILY_WORK_LOG](DAILY_WORK_LOG.md)。

## 历史：11月23日启动前审查

以下11月23日内容至早期快照全部保留当时语境，其中“当前/下一轮/未接入”不覆盖本页顶部及11月24日计划。

更新：2026-11-23，北京时间。最新已结束实验端点为 [638fddc](https://github.com/kaiwen123-yang/dog-and-arm/commit/638fddcb2f025006595f79f27a977a8fba41cbc2)，22:50:39 回收；本次仅核读论文/官方源码、审查结果并发布下一计划，没有新训练、物理评测或硬件动作。

### 历史目标与结果入口（11月23日）

用户明确要求：**根据开源SuperMimic详细研究与标准迁移，以达到或接近论文指标为目标，单独形成结果供后续比较；之后才做新开发、多模态/VLA。** 当前仍是B0-04接触阶段，WM、可微动力学和H32本来就在本阶段。

独立结果：[B0_STANDARD_TRANSFER_BASELINE.md](reports/B0_STANDARD_TRANSFER_BASELINE.md) · [机器可读清单](results/b0/standard_baseline_20261123/baseline_manifest.json)。目标方法ID `SuperMimic-M1Piper-standard-v1`，本轮快照 `b0-standard-s0-638fddc`；状态为未完成的中间基线，无合格最终候选。

### 历史实测（638fddc）

| 标准配置最终节点 | 接触H32累计 | 有效转移累计 | 正式接触 |
| --- | ---: | ---: | --- |
| control-u50 | 50 | 69,480 | Warp 0/10 |
| gain32-u200 | 200 | 345,268 | Warp/native各0/10 |
| gripdata-u50 | 50 | 73,163 | Warp 0/10 |
| padding-u50 | 50 | 82,748 | Warp 0/10 |
| wmcoords-u50 | 50 | 86,911 | Warp 0/10 |

五条链均为seed0、额外动作BC=0，确实调用固定官方网络/learner。合计400 H32、4,000 WM、8,000 Critic、657,570有效转移，已经去掉续训前缀重复；不是五个独立seed或一个模型的预算。

415条nominal/55评测run全部失败，303条首2 ms超力。正式组合275条=27套完整十项＋native gain50五项；该u50的另外五项hold-margin未评，后续u200双端已完整0/10。D、完整任务、seed1/2、H本轮均未执行。[逐案审查](reports/B0_STANDARD_ROUND_REVIEW_20261123.md)

WM双指H32 TCP P95：gain200为551.98/278.53 mm、wmcoords-u50为100.66/82.60 mm；held_r2为50.53/40.36、常速为13.95/11.86。前拉412窗/51 lanes、背推450窗/56 lanes，均为记录动作开环重叠窗。数据/坐标适配改善部分退化，仍未产生物理接触成功。

gain200首个真实20 ms后继tracking可达0.09080（上界0.1），但其首2 ms仍30.64 N>6 N，而且该诊断失败后继续积分。不能把它当作论文完整回合0.908。当前完整归一化回报、可比论文WM误差和可靠总GPU小时均NA。

### 历史待办（11月24日已完成相关对齐）

已核读论文v3和固定官方核心。论文BONES-SEED的0.90是SONIC参照线；SuperMimic超过该线及25/129,514、0/129,514是G1训练动作覆盖，不能等同本门任务成功率。迁移结果另记完整物理回报，目标≥0.90、接近数值带≥0.88（本项目预登记0.02容差），同时保持原物理门槛。[指标协议](docs/B0_PAPER_BASELINE_PROTOCOL.md)

[代码审查](docs/B0_OFFICIAL_IMPLEMENTATION_AUDIT_20261123.md)已确认：当前action-rate在canonical动作坐标计分，等物理J2动作跳变的惩罚约弱3,948倍；ReturnSampler尚未接入；replay_ratio=16未控制固定cohort调度；前瞻尾部零槽不同于官方逐clip夹取末帧。它们是已证实现差异，不是已证全部失败因果。固定官方8帧窗口实际监督7次后继，H7不能盲改为H8；固定代码Muon＋Adam也不同于论文表中统称Adam。

**下一优先项：同初始化/数据资格/预算，先真实配对训练原动作率坐标与固定O1 effort坐标；再恢复官方采样和实际调度、验证WM接触精度，持续推进接触→完整任务。** 不仅复做诊断，也不无条件将gain200续到u1000。具体执行、归一化完整回报与预算见 [下一计划](docs/B0_STANDARD_TRANSFER_PLAN_20261123.md)。

### 历史恢复说明（当前现场见页首）

标准锚点仍为`results/b0/free_s0_cloud_servo_r2/checkpoint_001000.pt`与`results/b0/contact_s0_wm_held_r2/wm_002000.pt`；本轮各完整cohort状态保留作控制/有据续训。固定来源abc124c / dd51a9f，原native3.3保留；上游5fb9229仅candidate_not_applied。

B0-03无接触与P1–P6工程已通过，不重复整阶段；旧r3 u1000两端0/10继续保留。540参考前馈/15,000动作BC与546解析补偿仍作单列对照，后者u1三端双侧nominal、Warp C各9/20，不填入标准成绩。

最终标准候选依序完成：十项接触nominal/各D≥18/20；同包Warp完整双侧nominal/C各≥18/20；同包native双侧完整nominal与持续H32；独立seed1/2各自B0-03；三seed配方/候选冻结后开H，每seed/侧≥40/50。论文导向回报和误差同时形成独立结果；标准仍未过时继续报告具体缺口，不自动进入R1–R8。

当前现场历史位置为AutoDL `/root/autodl-tmp/dog-and-arm-b0-standard`、第二平台`/home/kaiwen/research/dog-and-arm-standard`。已提交结果回收完成，不等于本次实时检查了所有现场进程；下轮先核实再接续。

入口：[完整启动词](prompts/B0_START.txt) · [现场下一项](prompts/NEXT_RUN.txt) · [目标差距](docs/GOAL_GAP_20261123.md) · [每日详细日志](DAILY_WORK_LOG.md)。以下保留早期历史快照，其“当前/下一轮/运行中”不覆盖本页顶部。

## 历史：2026-11-23 21:12 北京时间｜tmux 物理评分回收

- recovery_b_phase_td_u10_nominal_r1：pull 名义失败，开发未测；push 名义通过，开发未测
- recovery_b_stance_u1_full_c_r1：pull 名义通过，开发9/20；push 名义通过，开发9/20
- recovery_b_stance_u5_nominal_r1：pull 名义失败，开发未测；push 名义通过，开发未测
- recovery_b_tracking_u1_full_c_r1：pull 名义通过，开发9/20；push 名义通过，开发9/20
- recovery_c_integrated_warp316_r1：pull 名义通过，开发9/20；push 名义通过，开发9/20
- recovery_endpoint_hinge_tail_warp_r2：pull 名义通过，开发未测；push 名义通过，开发1/1
- recovery_planar_arm_native_tmux_r1：pull 名义通过，开发未测；push 名义通过，开发未测
- recovery_planar_arm_screen_warp_r1：pull 名义通过，开发2/6；push 名义通过，开发3/6
- recovery_planar_screen_warp_r1：pull 名义通过，开发0/4；push 名义通过，开发1/4

逐案物理结果及实际分母见 results/b0/recovery_round_20261123/case_index.csv 和各 run 目录。独立 seed 与 H 保持封存。

## 历史项目状态与原始交接

## 历史：2026-11-23 北京时间 20:45｜B0 已交给 tmux（21:11 已回收完成）

第二开发平台管理 AutoDL 的 b0-recovery-20261123。Windows 执行以下命令可直接接入。按 Ctrl-b，再按 d 可分离会话。

    ssh -t dev2-ubuntu-lan "ssh -t autodl-dog-arm tmux attach -t b0-recovery-20261123"

第二平台回收窗口使用 `ssh -t dev2-ubuntu-lan tmux attach -t b0-receive-20261123`。云端独立树 /root/autodl-tmp/dog-and-arm-b0-recovery，实时状态 results/raw_large/b0/recovery_tmux_20261123/status.json。8项登记及交接快照见 results/b0/recovery_tmux_20261123；终态日志与单案例原始结果在各自run。GitHub只在普通推送回读后算交付。

546维同一真实H32-u1已在native3.3、CPU3.16、Warp3.16名义前拉/背推全部通过。原生完整C，监督u0为9/20、9/20；H32-u1为9/20、10/20（新增背推C08）。Warp完整C尚在进行。当前已知失败数足以排除这一候选通过双侧18/20。十项局部监督历史成绩仍属于原监督包，独立seed和H保留。运行中的下一份逐案结果由已登记进程生成，不重复启动同名回归。

更新日期：2026-11-23（Asia/Shanghai）。

## 接续执行（2026-11-23，北京时间）

已从 b9a1129 恢复真实权重与固定 Warp 参考，完成启动检查、相对站位输入接入及 A0/A1 的配对 seed0 监督训练。工作包 A/B/C 的新结果见 [接续实测](reports/B0_RECOVERY_RESULTS_20261123.md) 和 [逐日日志](DAILY_WORK_LOG.md)。上轮冻结的成绩保留如下。

## 上轮审查与计划（2026-11-23）

**当前仍在 B0：局部接触监督基线通过、完整单门 seed0 限制基线已交付；完整开发与同包跨后端门槛未通过，H32 的统一双侧收益尚未建立。** 依据为 main@2c15d35 的已结束实验，本次只审查和发布文档，没有新增训练、仿真评测或硬件动作。

- 同一接触参考残差监督包在 native/Warp 各十项、每项 20/20；这是 200 个局部条件各测两端，共 400 次，扰动 XY±0.5 mm、yaw±0.025°，有 100 个物理子步初始化前缀。该包 BC3000、WM2000、接触 H32=0。
- 两套分别来源于 native/Warp 的共同双侧 u0 包在各自后端 nominal 通过；四组完整 C 均 9/20（仅 C01、C10–C17），低于每侧 18/20。完整任务从规定初态连续运行，无教师前缀；同包交叉后端双侧均未通过。
- 纯 tracking 接触 H32 u1000 在两端各 0/10；统一双侧全程 u50 退化。两个 full H32 run 实际都在 Warp 训练，不能把 native 参考来源当成 native 在线训练。部分局部 H32 与单侧前拉有成果，不能拼为双侧通过。
- 已确认 C02–C05 的平移在当前 Actor 输入中不可区分；真实接触硬失败没有完整进入想象 soft termination/Critic 目标；同集双指 H32 WM 误差在 u0→u50 全部恶化。Critic 实际能看到门，bootstrap 是否导致退化仍待受控验证。
- 下一轮按新计划并行准备：A 站位输入与扰动教师覆盖；B 回报/终止、Critic 与模型梯度诊断；C 三后端差异定位。先同条件诊断，再集成最小有效适配并继续完整评测。seed1/2 和 H01–H50 继续保留，满足门槛后按原 B0-06 顺序推进。

当前入口：[审查报告](reports/B0_REVIEW_20261123.md) · [接续执行计划](docs/B0_RECOVERY_PLAN_20261123.md) · [启动提示词](prompts/B0_START.txt) · [只读/复核入口](prompts/NEXT_RUN.txt) · [每日详细记录](DAILY_WORK_LOG.md)。以下保留此前阶段的原始交接与历史表述，当前执行顺序以上文和新计划为准。

## 上轮冻结状态（2026-11-22，B0-04–06 限制基线已交付）

B0-04 同一 seed0 接触监督包在原生和 Warp 后端均通过十项名义和每项 20/20 开发。B0-05 在两个后端各有一个能执行两侧全程的统一 WM/Actor 包。原生前拉/背推 59.9794°/25.0396°，Warp 59.9506°/25.0258°，四个成功名义均有完整视频和两段独立 3 s 停车。两套包的全程 H32 均为 u0；有 50 次 H32 的单侧前拉原生包可完成名义，双侧 u50 未同时通过。两套包交叉换后端时两侧均失败。

原生、Warp 各自的完整前拉/背推 C01–C20 全部计分，四组均 9/20；每组通过 C01、C10–C17。未达到 B0-06 的每侧开发 18/20，seed1/2 独立训练与 H 任务测试未执行。冻结部分通过、物理失败、权重和下一项观测适配。P6 与 B0-03 seed0 原结果保留。[基线交付](reports/B0_BASELINE_REPORT.md) · [逐案清单](results/b0/full_baseline_seed0/full_case_index.csv) · [每日记录](DAILY_WORK_LOG.md) · [复核入口](prompts/NEXT_RUN.txt)

## B0-04 片段实施时的历史入口

B0-03 seed0 保持冻结。B0-04 已实现动态门 WM、真实 20 ms 恒动作采集、变长参考与 2 ms 只读评测。固定的参考残差监督 Actor 在原生 MuJoCo 3.3.0 通过全部十项名义，每项均为 20/20，共 200/200 个开发条件。五项采用原 v1，五项采用提前登记、另采一秒真实持姿的 v2；Warp 十项名义已过，开发清单按实际物理继续运行。成绩对应接触联训 u0 的单一 seed0 WM/Actor 包。纯 tracking u1000 完成 572,118 条在线有效转移，两端各 0/10。以通过的原生候选接续 B0-05 连续前拉 60°；全程学习结果单独记录。专用工作树为 `dog-and-arm-b0-contact`，SSH 别名为 `autodl-dog-arm`。[接触逐项](results/b0/contact_hold_margin_v2_summary/actor_native33.csv) · [全程报告](reports/B0_FULL_TASK.md) · [当日记录](DAILY_WORK_LOG.md)

## 865835c 发布时的入口与冻结交接

用户在完成仓库梳理后要求：增加一个单独文件详细记录每天的工作与解决的问题，并将下一步计划和 Codex 启动提示词推送 GitHub。本次新增 [DAILY_WORK_LOG.md](DAILY_WORK_LOG.md) 和 [B0 接触执行计划](docs/B0_CONTACT_EXECUTION_PLAN.md)，同步更新项目规则、总路线与启动入口；只做文档编辑和一致性检查，没有启动新训练、仿真任务或实机动作。

下一轮由用户下达 [B0_START.txt](prompts/B0_START.txt) 后，按 B0-04 动态门与接触片段 → B0-05 连续前拉/背推和统一模型 → B0-06 独立训练种子与留出测试推进。已完成的 P6、环境与 B0-03 seed0 不无条件重跑。每个有意义节点维护当日日志；详细记录问题证据、修复与复测、失败、未完成项、命令与产物。

首先处理的是与 20 ms 策略周期一致的真实接触转移、独立门动态表示、变长参考和只读物理事件评估器。已有高频完整门教师成功只证明后端可行，不能直接作为恒定 20 ms 动作 replay。`door_held_out.json` 仍只做了几何有效性检查，保留到冻结策略后的 B0-06 任务测试。

## B0-03 已通过的冻结结果

seed0 的第 1000 次更新是本轮冻结检查点。训练用固定 O1 双源、原 tracking 奖励和 23 路全身策略，实际产生 1,088,000 个在线物理转移，完成 10,000 次 WM 小批更新、1,000 次 H32 Actor 更新及 20,000 次 Critic 小批更新。1000 次 Actor 更新均记录了冻结 WM 和非零 Actor 权重变化。CUDA 梯度链路另有七步物理输出反传诊断。支撑伸收臂、移动变臂姿、停车在 MuJoCo-Warp 3.16 和 CPU MuJoCo 3.16 上均为 20/20，原工程 MuJoCo 3.3.0 分别为 20/20、20/20、19/20。停车 F02 完成 7 s，TCP RMSE 为 30.75 mm，超过 30 mm 门槛。三个名义任务也在 Warp 和 3.3.0 全部通过。每案从完整初态连续执行 7 s，逐个检查 3,500 个物理子步。留出回合的 1、7、32 步 TCP 预测 RMSE 为 0.36、2.04、2.82 mm。[检查清单](results/b0/free_s0_cloud_servo_r2/review.json) · [逐案与视频](reports/B0_FREE_MOTION.md)

完整权重在本机与云端项目内的 `results/b0/free_s0_cloud_servo_r2/checkpoint_001000.pt`。云端目录为 `/root/autodl-tmp/dog-and-arm-b0`。865835c 发布时，已执行研发停在 B0-03，B0-04～06 只发布了计划。当前执行与冻结复核入口见 [NEXT_RUN](prompts/NEXT_RUN.txt)。

## B0 环境迁移与初期无接触学习历史记录

下文保留当时的启动和失败过程；其中“已启动”“继续 B0-03”等表述由顶部冻结结果和当前入口更新，不代表此刻又启动了历史 run。

2026-11-21 本机 `git pull --ff-only origin main` 快进至规划提交 `f6333ec`，保留未跟踪 P5 数据。现场 GPU 为 RTX 5080 Laptop 16 GiB，主机内存 30 GiB。固定双源和 O1 实际配置已核对。单门仍用 `rail_bridge_front60_v2` 与冻结 P6 控制 `86ade86`。

- 三类无接触参考各实跑 350 个 20 ms 转移，另有独立扰动验证回合。按名映射 12 腿＋4 轮＋6 臂＋1 夹爪，原生 3.3.0 重放四条，共 1,400 个策略步。最大 TCP RMSE 为 1.81e-13 m。
- 为补采整条 500 Hz 参考，冻结教师额外实跑前拉和背推 nominal 各一次。终态 60.052° 和 25.081°。门操作命令随子步变化，仅无接触恒定目标回合可直接用于本版动作 replay。
- 原始数组在 `results/raw_large/b0/native_teacher_20261121_r1/`，执行命令与字段见 [数据报告](reports/B0_DATA_READINESS.md)。[来源锁](config/b0/source_lock.json)、[索引](data/b0/reference_manifest.json)、[重放数值](data/b0/native_teacher_checks.json)。
- 独立环境 `bash scripts/b0/setup_env.sh`，O1 双 pin、129 个包，Torch 2.14.0/cu130、MuJoCo/Warp 3.16.0。四阶段 GPU/CPU 对照和固定 3.3.0 的三条教师轨迹见 [环境报告](reports/B0_ENV_ADAPTATION.md)。
- seed0 实际运行 `bash scripts/b0/env.sh python scripts/b0/train.py --run free_s0_integration_r1 --updates 2 --integration`。GPU 8 个场景累计 320 个策略转移（3,200 个 2 ms 物理步）、20 个 WM minibatch、2 次 H32 Actor 与 40 个 Critic minibatch，均从新初始化的网络起步。权重在 `results/b0/free_s0_integration_r1/checkpoint_000002.pt`。
- 独立加载同一权重，3 类各 0/20。第 2 次更新的留出 TCP 误差为 5.81 / 21.89 / 767.86 mm（1/7/32 步）。[学习记录](reports/B0_FREE_MOTION.md)。继续 B0-03；接触片段与完整学习任务待无接触通过。

### 后端接触验证及 seed0 第一次正式训练

训练后端额外完成两侧 C01 教师的原任务全程。前拉 36,863 步、60.04931°，背推 27,043 步、25.07761°，两侧退臂后和终点的 1,500 步保持独立通过。原生工程的 MuJoCo 3.3.0 也独立执行了更新 2 的冻结策略，三类 nominal 均在 0.100 s 触发持续失载。[两侧教师、保持和警告范围](reports/B0_DATA_READINESS.md) · [冷启动动作分块诊断](reports/B0_EVALUATION.md)

启动 `bash scripts/b0/env.sh python scripts/b0/train.py --run free_s0_formal_r1 --updates 1000`，每 2 ms 加入 GPU 轮载和异常接触审计。实际完成 160 次 Actor 更新，共采集 25,760 个当前策略转移。随后官方 replay 报错 `no valid sequences L=8 n=1000`。该次退出前最后一个已保存的此配置检查点是更新 0；更新 160 无可恢复权重。原始整数步计数和采样比例在 [失败记录](results/b0/free_s0_formal_r1/failure.json)。

已以独立 run 启动 **free_s0_boundary_r1**。每批分开从真实终止后继做一步监督，并保留长窗口教师和策略数据。输出层从模型 home 附近的小随机残差开始；冻结评测仍由网络独立输出全部 23 路命令。实际入口为 `bash scripts/b0/env.sh python scripts/b0/train.py --config config/b0/free_replay_home.yaml --run free_s0_boundary_r1 --updates 1000`。检查更新 0、50、200、1000 的真实物理结果。阶段结论依冻结评测。[变体定义](config/b0/free_replay_home.yaml)

## 历史规划节点：R0 → B0

2026-11-21 用户已明确要求读取当前仓库，将“先在本场景跑通官方 SuperMimic，再开展多模态融合”的详细规划推送到 GitHub，并提供 Codex 提示词。本次新增的是规划与续接入口；没有运行 B0 训练、P6 复跑、双门实验或实机动作。

- 下一步执行 [B0_START.txt](prompts/B0_START.txt)，先 R0 最小定义与 B0-01 环境/动作适配，再参考/replay、无接触学习、接触片段、完整单门和基线冻结。
- [总路线](docs/RESEARCH_ROADMAP.md) → [B0 详细计划](docs/B0_SUPERMIMIC_PLAN.md) → [数据与模型约定](docs/B0_DATA_MODEL_CONTRACT.md)。R0/B0 的实现、训练与学习策略验收均为待执行，不把文档完成记成算法完成。
- 继承 `rail_bridge_front60_v2` 与冻结控制 `86ade863de712dd6cd402714229b12b1bdae5b13`；本次读取的结果快照为 `dc961f35034ad3083a46eecd1c0ff5f21607eb0c`。P6 最新覆盖是下文的前拉/背推各 20/20，旧暂停记录保留为历史。
- SuperMimic 默认继承已验证 O1 双源 `abc124c1bd5976341034668af3d12c087f2f1f55`＋`dd51a9fcc98791a2f0b018b3c7f71a3eefd5ecdd`；用户复现仓库 `00e45d4` 已闭项，不重跑 G1。
- 最终目标保持为腕部 RGB-D＋语言＋本体历史的多模态/VLA、世界模型与可微动力学联合，并完成实机验证。双门作为后续扩展；当前不以双门完成为 B0 前置条件。

本次仅核对与规划相关的仓库源码、配置、报告和结果表并检查文档一致性；没有访问现场机器人、恢复 H 盘归档或重新执行既有实验。后续实际 B0 命令与结果须由执行轮次补充。

## 已完成的 P6 工程基线

冻结控制 `86ade86`、`rail_bridge_front60_v2` 安装的同版固定清单已在 Linux 桌面全部执行。前拉 20/20、背推 20/20 通过。本机已完成前移安装的可见重载、收臂外观、碰撞及腕相机核对。两侧终态门角分别为 59.963–60.224° 和 25.043–25.089°，开门段分别为 31.394–35.382 s 和 11.766–14.586 s。前拉与背推的 J5 最小余量（°）分别为 1.473（C20）与 20.042（C05、C19 并列）。总计 1,290,099 个 2 ms 物理步，六轴有符号余量越界步数 0。各案的极小值和发生时刻均与原始 500 Hz 记录一致。出现非预期接触的案例数为 0，有原生求解器警告的案例数为 0。

11 月 21 日执行 `git pull --ff-only origin main`，保留未跟踪 P5 结果。前拉中断组以 `bash scripts/project_env.sh python scripts/p6_cases.py 15 16 17 18 19 20 --stage mobile --output results/p6/rail_bridge_front60_v2_20261120T133724Z/mobile_C_resumed` 重新完整运行。背推以同一入口 `--stage push` 运行 C02–06、C07–11、C12–16、C17–20，输出至 push_A–D。定位 C20 左后轮碰左门柱后只改背侧航向至 95°，依次分格实跑 1/2/3/7/18/20、4/5/6/8/9/10、11–16、17/19，输出至 push95_A–D。暂停记录、调参失败及旧座成绩各自保留。通过 `scripts/p6_condition_report.py` 合并实际配置一致的清单；另用 `scripts/p6_approach_clearance.py` 复核背侧驶近门框净空。[逐案表](results/p6/rail_bridge_front60_v2_20261120T133724Z/conditions.csv) · [完整报告与命令](reports/P6_FREE_BASE_DOOR.md) · [本机装配检查](docs/MOUNT_RAIL_BRIDGE.md)

研究顺序已按用户最新决定调整为先 R0/B0；原双门几何继续保留，后续再扩展。当前物理任务证据覆盖单扇门，尚无整机学习策略或视觉语言闭环成绩。手眼、标定板及附件称重继续后置。

## 历史实施记录

以下保留各节点当时的命令、结果和安排。涉及“下一轮”“待执行”的旧表述已经被顶部当前阶段与后续完成记录替代，不作为自动执行入口。

**前移模型的云端准备记录。** 用户要求安装板靠近狗头，故将板、两支座和整台 Piper 沿 M1 机身 +X 前移一档孔距，版本为 `rail_bridge_front60_v2`。臂根由 [0.050, 0, 0.0945] m 改为 [0.110, 0, 0.0945] m，板心 X 由 0.010 改为 0.070 m，选孔由每排第 3/4/5 改为第 4/5/6（按 X 递增编号）；完整导轨基准与高度不变。

本轮在独立云端检查环境（Python 3.12.14 / MuJoCo 3.3.0）实际重建 URDF/MJCF、编译前拉/背推场景，三组 FK 与腕相机刚性检查通过。板下机身凸包净空下界 4.410643 mm，相同 home 姿态的整机质心前移 6.500053 mm，质量仍 43.537064 kg。保存 [前后静态对照](results/assembly/rail_bridge_front60_v2/forward_comparison.png)、[模型检查](results/assembly/rail_bridge_front60_v2/model_check.json) 和 [源网格净空](results/assembly/rail_bridge_front60_v2/source_mesh_clearance.json)。**本轮无 GUI、无 mj_step、无硬件操作；没有新增推拉通过结果。** 用户的 `/home/kaiwen/research/dog-and-arm` 未从本会话直接访问。

P6 现在从编译模型读取真实安装版本，每个物理步记录六臂关节限位最小余量；分组入口增加 `--stage mobile|push`，可分别执行前拉 60°与背推 25°的 C01–C20。下一轮先可见检查前移装配，再做名义前拉、名义背推及 C13，最后按同一安装/控制版本完成两侧条件清单。背推 20 条是新增待测覆盖；旧座 20/20 前拉与旧版名义背推不能算作新座结果。[完整本机提示](prompts/MOUNT_FORWARD_PUSH_PULL.txt)

**前一安装版本 rail_bridge_v1 的 P6 名义前拉通过。** `rail_bridge_v1_mobile_01` 在 Linux 桌面连续运行 82.474 s / 41,237 步，从 0.30 m 外驶近、停车、双指前拉、松爪、退臂及保持、收臂、倒车至终点停车。最终 60.048936°，操作漂移 0.949 mm，抓持偏移 2.670 mm，门对机器人合力峰值 2.840 N。机器人与门仅两指接触目标杆。两个 3 s 窗口通过，2,062 帧全程录像已解码。松爪附近的 25 Hz 日志中，J5 距下限仅 0.141°。新座目前仅有这条名义前拉。[视频](results/p6/rail_bridge_v1_mobile_01/motion.mp4) · [报告与逐阶段记录](reports/P6_FREE_BASE_DOOR.md)

实际命令为 `bash scripts/project_env.sh python scripts/p6_single_door.py mobile --live --video --hold-final --output results/p6/rail_bridge_v1_mobile_01`，完成后用 `scripts/plot_p6.py results/p6/rail_bridge_v1_mobile_01` 出图。该版本当时安排先复查 C13；现由上文 front60_v2 的完整推拉复测替代，C13 仍是重点。保留旧版 20 案例和背推汇总。H0 本轮无操作，手眼、标定板与称重继续后置。

**双导轨安装座 rail_bridge_v1 已完成模型替换与桌面检查。** 运行 `bash scripts/project_env.sh python scripts/build_assembly.py --stage combined` 与 `bash scripts/project_env.sh python scripts/check_assembly.py --report results/assembly/rail_bridge_v1/kinematics.json`，重建组合 URDF、MJCF 和安装板网格。固定近景重载旧座与新座并切换碰撞/整机视图。Piper 臂根降低 85.5 mm；名义板下外观净空 14.5 mm，板中心到机身碰撞凸包净空约 4.41 mm。三组 FK 通过，整机质量 43.5371 kg，附加载荷继续省略。[连接件说明与桌面截图](docs/MOUNT_RAIL_BRIDGE.md)

**旧方块安装座 P6 自由底盘前拉已在 Linux 桌面完成。** 20 个预先列明的条件全部完成驶近、停稳、双指拉门、松爪、退臂、保持、收臂、底盘倒车和终点稳定。最终门角 59.9698°–60.2421°，20 例最大抓持偏移 3.133 mm、操作漂移 2.912 mm、倾角 0.2433°。C13 开门段用时 54.898 s，55 s 时限的余量很小。完整条件与逐案限制见 [P6 报告](reports/P6_FREE_BASE_DOOR.md) 和 [最终清单](results/p6/conditions_final.csv)。

**旧座背推完成。** `bash scripts/project_env.sh python scripts/p6_single_door.py push --live --video --hold-final --output results/p6/push_02`。首次背推沿指深滑脱触发 5 mm 门槛；改为斜入竖杆后 54.200 s / 27,100 步完成 25.055163°、释放和底盘退离，仅两指接触背侧目标杆。[背推视频](results/p6/push_02/motion.mp4)。新座结构与名义基准另列。

- 本轮先 `git pull --ff-only origin main` 至 b04f604，保留原先未跟踪的 P5 结果。用 `bash scripts/project_env.sh python scripts/p6_single_door.py <阶段> --live --video --hold-final` 依次运行 support、small、pull、mobile，输出至 results/p6/ 下独立目录。自由根/有限 23 通道/被动门，物理 500 Hz，IK 100 Hz，日志和画面 25 Hz。H0 本轮无操作。
- A 在门前站位承重、伸臂、空走并停稳，门保持 0°；B 小角最终 14.957607°，正式驻停前拉 60.120818°。C 首个完整移动拉门 82.162 s / 41,081 步，最终 60.055003°；两个 3 s 停车窗口分别通过。[名义连续任务视频](results/p6/mobile_01/motion.mp4)。
- D 原清单 10/20 完成。默认接触锥的小角超时、到站超时/髋部饱和、C14 退爪碰板及部分终点停车超时均保留。采用椭圆锥、有限轮速与腿部辅助定向、世界 −X 退爪及驻停纠偏回差，最终四组实际重跑 `scripts/p6_cases.py`，参数依次为 1/2/6/14/18/20、3/4/5/7/19、8/9/10/11/12/13、15/16/17，目录 final_A–D。中间 recheck_A 父进程返回 143，保留到约 50 s 的短片和各进程完整落盘数据；final_A 重新运行通过。
- GitHub 自然节点包括 65a91a7（承重与伸臂）、dac8bf1（15°）、ed8b28c（60°）、6ed7373（连续移动拉门）、de6abd7（初版 20 案例）、e7a1ce7（驶近和退臂）、e815178（驻停切换）。

**P3 桌面装配检查已完成。P4 固定底盘从前侧拉门，单次名义 60° 试验实际达到 59.963319°。** 随后松爪退离，38 秒 / 19,000 步。门与机器人只有前把手和两夹指接触，接触力范数之和峰值 2.2433 N。严格 60° 阈值尚差 0.0367°。背侧实测已从 22.098° 提升至 25.076°，P5 已在自由整机上跑通承重、慢行、转向、停车和伸臂试验。

**P5 当前结果。** 自由根整机在平地承重、前进、按车头方向转弯、伸臂慢行并停车。左转 12° 的桌面试验最终为 12.170°；右转 −12° 的无窗口对照转向段变化为 −12.139°，完整运行最终约 −12.137°。两次各 40 s / 20,000 步。左转试验先直行 0.360 m，转后伸臂慢行 0.221 m，最终水平速度 0.063 mm/s。轮地水平切向滑动峰值 0.117 m/s，不是纯横向侧滑。当前证据覆盖名义平地，尚无门反力下的驻停验证。

实际运行 `bash scripts/project_env.sh python scripts/p5_free_base.py --config config/p5_heading.yaml --live --video --hold-final --output results/p5/heading_12`，用 `scripts/plot_p5.py results/p5/heading_12` 绘图。复跑省略 `--output` 自动保留新目录。视频完整解码 1,000 帧。最终桌面查看窗口可手动关闭，结果已落盘。 [P5 报告](reports/P5_FREE_BASE.md) · [40 秒视频](results/p5/heading_12/motion.mp4)。

P5 自由根实测 33 s / 16,500 步。直行 0.360 m，速率控制左转 10.40°（参考积分 28.42°），伸臂行驶 0.221 m 后停稳。这个基准位于提交 `e7e4556`，后续航向反馈结果见上。实际入口 `bash scripts/project_env.sh python scripts/p5_free_base.py --live --video`。 [P5 报告](reports/P5_FREE_BASE.md) · [视频与数据](results/p5/free_base_nominal/)。固定基座背推节点已提交 `e13a48f`。

背侧固定根 [1.88, 0, 0.54266] m、朝向 90°。35 s / 17,500 步，门角反馈补偿 3.015°，退爪后门停在 25.076°。两夹指及夹爪基座接触背把手。运行 `bash scripts/project_env.sh python scripts/p4_fixed_door.py --config config/p4_push.yaml --live --video`。[详细数据](results/p4/push_feedback/summary.json) · [报告](reports/P4_FIXED_BASE_CONTACT.md)。前侧提交 `29eab00`。

固定根移至 [0.65, 0.30, 0.54266] m 并转 45°，把手高度 0.85 m。松爪后退 0.10 m 并抬高 0.04 m。桌面运行命令为 `bash scripts/project_env.sh python scripts/p4_fixed_door.py --config config/p4_pull_60.yaml --live --video --hold-final --output results/p4/pull_60_trial01`。3,800 行时序与 950 帧视频已核对，按本次记录结束时仍为 59.963319°。 [桌面截图](results/p4/pull_60_trial01/desktop_final.png) · [曲线](results/p4/pull_60_trial01/contact_timeseries.png)

- 机械臂本体验机：**用户此前已完成**，本轮不启动 SDK 或实机。
- H0 相机＋机械臂联调：**此前回合实机完成**；[报告](reports/H0_HARDWARE_REPORT.md)、[会话清单](results/hardware/h0/20261116_2051/manifest.json)、[操作说明](docs/H0_RUNBOOK.md)。
- P1 官方资产、P2 单体生成、P3 名义联合模型：**准备环境已实现并编译／离线检查**；[装配报告](reports/assembly_report.md)。
- 本机 `.venv`：Python 3.10.12 / MuJoCo 3.3.0 已建立；M1/Piper/整机已实际桌面显示；关节/夹爪、检查相机和碰撞视图有桌面证据；Piper 的 F10 与 XML watch 重载完成。
- 手眼标定、标定板采购、相机/支架称重及惯量：**继续后置**。
- 当前按 [prompts/NEXT_RUN.txt](prompts/NEXT_RUN.txt) 推进 R0/B0；P6 已完成的记录按原版本保留，不重做 H0、不重复安装原环境或 P3 装配检查。

## P6 准备与基线复核：2026-11-20

- 复核源提交 `9c43f530360ce3398018b954f46eac11b96e0d73`。读取P4/P5代码、场景和已提交的JSON/CSV、视频关键帧；没有新增仿真、桌面操作或硬件动作。派生统计见 [P6_BASELINE_AUDIT.json](reports/P6_BASELINE_AUDIT.json)。
- 前拉60°样本比背推更适合作为首条P6基线：前拉机器人–门扇接触对仅夹指/把手；背推反馈样本含夹爪基座碰把手。前拉旧汇总缺少门框接触字段，不把缺项写成测得零。
- P5停车根高约0.531984m，比P4固定根低约10.68mm。P6须按实际根姿态求IK；轮速分配须由世界Y假设改成车体系相对几何。
- 现P4会固定根并重建物理状态、覆盖全部ctrl；P6须一个连续物理状态、明确腿轮臂爪通道、一个控制写入处，不能顺序调用现有P5/P4的run。
- 次序已明确：自由根操作站位与伸臂保持 → 小角度/约60°前拉 → 短距离接近与退离的完整任务 → 小范围条件变化及背推接触改善。工程门槛是待验证建议；没有将计划写成通过。
- 文档保留P4/P5历史记录并修正旧“下一步仍P4”和右转终值口径。当前新增的是下一步可执行计划，控制器和旧结果文件没有改变。

## P4 首个有效接触片段：2026-11-20

- P3 收尾节点 `4bbf1e5` 已普通推送；之后实际进入 P4，没有启动实机或 ROS。
- 新入口 `scripts/p4_fixed_door.py` 复用既有组合模型/门生成器，配置 `config/p4.yaml`；专用 `sim/scenes/p4_fixed_pull.xml` 固定 M1 根，保留腿/轮与全部几何。主模型仍是唯一自由根的 31/30/23/1，未被替换成固定底盘。
- 初始 60° 路径 IK 失败；20° 原退离路径也失败，修正松爪后的手部朝向后通过。首次真实步进被门板–机身碰撞挡在 16.829°，保留失败数据；后移根 0.12 m、将 P4 专用把手降至 0.85 m 后，实际到达 19.261095° 并松爪/退离。
- 实际桌面运行 `bash scripts/project_env.sh python scripts/p4_fixed_door.py --live --video --output results/p4/pull_20deg`，26 s / 13,000 步。门无执行器、无状态写入、无把手 weld，只有两指与把手接触；力矩未超限、无警告/非零自接触力。并非 60° 任务完成，也并非轮足站稳。
- 保存 `results/p4/pull_20deg/` 的 26 s/650 帧视频、2,600 行/100 Hz CSV、JSON、曲线与视频解码图；`trial_02_obstructed/` 为真实碰撞失败；`trial_03/` 保留实际桌面图与有效初试汇总。重复初试的完整视频/CSV 仍留 `results/tmp/p4_trial_03_full/`，不重复上传。未新建压缩归档。
- `plot_p4.py` 从真实 CSV 绘图；只在项目 .venv 增加 Matplotlib，未动系统 ROS/Conda/CUDA。视频完整解码、代码编译和 MJCF 维度复核通过。
- 详见 [P4 报告](reports/P4_FIXED_BASE_CONTACT.md)。剩余：名义 20° 与实际 19.261° 的偏差、60° 连续可达性及碰撞路径、另一侧推门、跨条件重复。此处为 19° 节点当时的未完成项，后续结果见顶部。
- 下一条复跑命令：`bash scripts/project_env.sh python scripts/p4_fixed_door.py --live --video`（默认新时间目录）。继续开发先读 P4 报告，不能把复跑近 20° 当成解决 60°。

## 本机可见检查收尾：2026-11-20

- 从 `078839e` 接续，工作区干净；正常 `pull --ff-only origin main` 已是最新。复用既有 Python 3.10.12 / MuJoCo 3.3.0 / X11 :1。
- `live_assembly.py` 显式调用 `mjv_defaultFreeCamera`，按已有 scene statistic 初始化自由视角；本次截图确认腕部和四轮完整入画。没有改安装参数。
- 终端 A `bash scripts/project_env.sh python scripts/live_assembly.py --watch --events results/assembly/live_20261120/combined_events.jsonl`；终端 B `build_assembly.py --stage combined`，实际发生 XML_changed → 编译 → 关闭旧窗口 → 新窗口恢复 home，桌面截图确认重载后画面。
- `bash scripts/project_env.sh python scripts/check_assembly.py`：三组独立 FK 继续通过；新增 3 个腕关节姿态 × 0/40/100 mm 夹爪开口共 9 个名义关系检查。开合引起的相机世界位姿变化为 0；相对 gripper_base 的位置/旋转最大差约 5.93e-17 m / 5.55e-16。
- 实际打开 `live_assembly.py --model sim/scenes/assembly_with_door.xml --watch --events results/assembly/live_20261120/door_events.jsonl`，F8 桌面显示被动门板和 U 形把手。使用既有同一 optical frame 和 synthetic_aligned_rgbd；不是实物标定。
- 证据：`results/assembly/live_20261120/` 的 default_view、reloaded_view、wrist_door PNG 及事件；量化数据在 `reports/assembly_kinematics.json`。本轮没有新的用户明确观看确认，不代填反馈。
- 以上仅 `mj_forward`，时间为 0；P4 实验将单独生成固定基座场景并使用有限执行器与 `mj_step`，不更改主模型自由基座。

## 本机可见调试：2026-11-16

工作区初始干净，`git pull --ff-only origin main` 从 `284c1f3` 快进至 `b545796`。实际桌面 X11 `DISPLAY=:1` 可连接。仅创建项目 `.venv`，没有修改 ROS/Conda/CUDA 或启动硬件。

- 已执行 `bash scripts/setup_env.sh`、`bash scripts/project_env.sh python scripts/fetch_sources.py`、`scripts/inspect_sources.py`。两处官方源仍为锁定提交，资产完整。
- 终端 B 执行 `bash scripts/project_env.sh python scripts/build_assembly.py --stage m1`；终端 A 实际打开 `bash scripts/project_env.sh python scripts/live_assembly.py --model sim/scenes/m1_preview.xml --watch --events results/assembly/live_local/m1_events.jsonl`。
- X11 桌面捕获确认 M1 四轮轮足可见；FAR hip +6°、knee −4°、wheel +6°，F11 恢复，F12 正常退出。截图、18 s 桌面录像及事件在 `results/assembly/live_local/`。尚未收到用户明确的观看反馈，不代填“用户确认”。
- 修复碰撞外观重叠：F9 显示碰撞凸包/盒体并隐藏视觉组 1/2；F6 切换现有概览/侧面/正面/腕部局部相机。实测处理 MuJoCo 原生 F6 的坐标轴副作用。均只改变显示，不改碰撞参数。
- M1 模型 `nq23/nv22/nu16`，38.82051 kg；生成 URDF 的极小尾数差来自本机数值库。全部仍是 `KINEMATIC_PREVIEW`，没有 `mj_step`。
- Piper：终端 B `build_assembly.py --stage piper`，终端 A `live_assembly.py --model sim/scenes/piper_preview.xml --watch --events results/assembly/live_local/piper_events.jsonl`。J1/J2 各 +4°、J3 −4°；Space 双指 100→0 mm，F6 腕部近景，F9 碰撞，F8 腕相机，F10 实际重开窗口并恢复 home。
- Piper 单体包含名义腕部附件和相机。空场景腕相机主要看见背景/远地面，属实际显示结果；尚未添加目标。用户明确回复“能看到，继续”，对应 Piper 腕部近景与夹爪开合，不扩大为全部阶段确认。
- Piper `nq8/nv8/nu7/neq1`、4.716554081 kg；保存截图、24 s 桌面录像与事件。M1 节点 `f8786a8`、Piper 节点 `728fc8a` 均已推送。首次 HTTPS push 发生 TLS 中断，重试发现未配置 HTTPS credential helper；复用已有 gh keyring 登录、按命令临时指定 helper 后成功，没有修改全局认证配置。
- 联合模型已执行 `build_assembly.py --stage combined`，桌面打开默认 `live_assembly.py --watch --events results/assembly/live_local/combined_events.jsonl`。已检查侧面/正面、腕部局部、100→0 mm 开合和碰撞专用视图，未修改 `config/assembly.yaml` 的名义安装参数。
- 本机 `bash scripts/project_env.sh python scripts/check_assembly.py` 通过三组 FK，最大位置差 3.044e-16 m、旋转矩阵差 9.806e-16；仍仅运动学一致性。
- 用户暂停后已 F12 关闭本轮 viewer，关闭本轮桌面终端；没有启动任何硬件、接触或轮足动力学。
- 未完成：联合带门场景的本机腕视角、开合时相机固定关系的单独量化、联合场景重建/重载收尾；初始自由视角上沿裁掉部分腕部，F6 侧面/正面/局部视角正常，默认取景待修正。Piper 在 combined 构建重写单体 XML 后已收到 XML_changed 并成功重载。
- 下次先完成上述可见检查，之后才进入固定基座单门接触，再进入自由基座轮足保持/慢行。当时已暂停；2026-11-20 已按用户要求恢复，当前进度见上。

## 基础联合模型回合：实际成果

实际在独立 Linux／Python 3.12.14／MuJoCo 3.3.0 环境执行官方源获取、清单、全模型构建、三姿态 FK、EGL 图像与视频导出。未接入用户的 ROS、CAN、相机或机械臂环境。

- `scripts/build_assembly.py --stage m1|piper|combined|all` 可重建；不修改 vendor。场景在临时 XML 编译成功后才替换，支持稳定的查看器重载。
- `description/m1_derived.urdf`、`piper_h.urdf`、`m1_piper.urdf`、`joint_map.yaml` 已生成。
- `sim/robots/m1_piper.xml` 和 `sim/scenes/{m1,piper,assembly}_preview.xml` 已生成；`assembly_with_door.xml` 提供被动单门的可视对照，没有门电机。
- 联合模型 `nq=31, nv=30, nu=23, neq=1`；唯一浮动基座，16 个 M1 关节＋6 轴臂＋双真实夹指。源模型质量之和 43.537064081 kg，不含附件和名义安装座额外载荷。
- 配置背部安装 xyz `[0.05,0,0.18] m`；源注释站姿的根高由穿地的 0.52 m 调为名义 0.54266 m。支架／相机固定在 `piper_gripper_base`，外参未测量。
- 三组独立 URDF/MJCF FK 对照通过；最大位置差约 3.044e-16 m、旋转矩阵元素差约 9.806e-16，两指 mimic 误差 0。这是数字模型间一致性，非标定精度。
- `results/assembly/` 有整机、侧面、正面、腕部局部、原始理想 RGB／米制深度及 8 秒／240 帧运动学视频；`with_door/` 有同一相机看到门和把手的对照。
- `scripts/live_assembly.py` 支持关节选择／微调、夹爪、腕相机、碰撞显示、home 与 XML 重载。同一加载函数已核对实际模型；**准备环境无 DISPLAY/WAYLAND，未执行桌面 viewer**。

基础联合模型准备回合当时仅 `mj_forward`；后来P4真实接触、P5自由基座承重和轮速控制分别记录在上方，不把后续结果归入该准备回合。Piper 外观采用官方 collision STL，未转换 DAE 精细外观；官方质量和惯量保留。M1 原生动力学数值未改变。原始大网格由固定源重建，`assets/converted/` 不提交。

官方有 MATRiX_Robot_MC 的 ZGWS/ZGWS_ARM 运行包，但当前未下载／接入，不能把 native 模型的 16 个 motor 当成已验证运控。P5使用本项目的名义轮腿控制，不表示已适配官方运控或验证实机部署。

## H0 回合实际环境、命令和文件

- 从 `7bb3c1b` 克隆本仓库。原工程 `/home/kaiwen/research/OSCBF-research` 对应 OSCBF-learn `2ea3f1f`；解释器 `envs/piper-sdk/bin/python` 中实际是 pyAgxArm 1.0.0 / python-can 4.6.1，SDK 源提交 `d90e234b`，PIPER_H/V189 配置。未重装机械臂环境或升级固件。
- 实际 `can0` 初始 DOWN；确认 USB-CAN `1d50:606f`、序列号 `004F00374548570120353731` 后，用户执行 `sudo bash scripts/h0_host_prepare.sh` 补齐缺失相机依赖、USB 权限并启用 1 Mbps CAN。准备脚本及接收器不发电机指令。
- 相机为 DC1，RGB `2bc5:0557`、深度 `2bc5:0657`，序列号 `CC16762023M`，USB 480 Mbps。`bash scripts/h0_build_camera.sh` 构建 Astra `f7e71d9c`；首次缺 `nlohmann/json.hpp` 的失败和解包头文件后的成功均保留。驱动源/编译产物在忽略目录 `hardware/camera_ws/`，未修改上游。
- 相机入口 `bash scripts/h0_camera.sh`；最终相机/接收器经 `scripts/h0_ros_env.sh` 使用 domain 88、localhost、Fast DDS 64 MiB SHM。ROS 与机械臂解释器分开，未使用仿真 `.venv`。
- `h0_record_camera.py` 保存 RGB/原始深度/CameraInfo/视频/时间；`h0_record_arm.py` 只接收 SDK/CAN 状态。两者独立进程；`h0_operator_motion.py` 是现场唯一运动入口，复用原 `PiperDevice`，记录实际 MOVE_J/夹爪发送调用。
- 成功现场命令使用原解释器、`--execute --recording-directory .../continuous --start-deg 83.551 2.821 0 -1.132 24.567 5.556`，输出到 `.../continuous/retry`。完整命令和事件见报告及证据；这些绝对角度仅属于当次现场，不能盲目重放。
- 离线用 `/usr/bin/python3 scripts/h0_analyze.py <run>` 计算接收间隔和关联，用 `h0_export_window.py` 导出事件窗口。真实配置已填入 [config/hardware_session.yaml](config/hardware_session.yaml)。

## H0 实测结果

| 项目 | 结果 |
| --- | --- |
| RGB / 原始深度 | 640×480 rgb8 / 640×400 16UC1；1 count = 1 mm，0 无效；未对齐、未缩放保存数组 |
| 两路 CameraInfo | 完整保存 D/K/R/P、尺寸、frame、ROI、binning；各自匹配图像，K 可与设备服务核对；RGB D 的已知差异见下 |
| 静止联合记录 | 65 s RELIABLE 窗口完成；最终 240 s：RGB 7179、深度 7204、关节 48006 行 |
| 最终接收性能 | RGB 29.912 Hz、深度 30.017 Hz、关节 200.025 Hz；最大间隔分别 40.023/39.860/8.104 ms；无 >100 ms 间隔、倒退、队列丢帧或 CAN 错误 |
| 小幅动作 / 正常停止 | 第二次 J6 实测范围 1.962°，慢转、保持、返回；初始明确调整 J3 +1.611°→0°，没有全零回位 |
| 夹爪 / 现场观察 | 约 39.5→15.1→39.5 mm；用户确认“这次动作、停止、支架和线缆都正常” |
| 相机正常重启 | 成功退出并恢复两路流/参数；新传输配置下完成 90 s＋240 s 静止复核 |

最终 RGB–depth 最近接收时间差中位数/P95/最大值 8.399/16.305/17.915 ms；RGB–joint 为 1.219/2.374/3.681 ms。相机 header 来自驱动回调 `node->now()`，不是已证明的曝光时刻。CAN 保留内核时间、SDK 更新时间和主机单调接收时间；约 10 Hz 缓存快照不用于反馈率。实际相机/记录节点 `use_sim_time=false`。这些结果仅是同一主机的软件接收关联，未验证硬件同步。

## 失败记录与剩余限制

- 首次 BEST_EFFORT 接收 RGB 仅约 6.52 Hz；匹配发布者改为 RELIABLE 后短窗口恢复。约 720 s 连续记录又在约 182 s 后出现 RGB 成批到达；最终改项目独立 SHM 配置，90 s＋240 s 静止复核恢复到约 40 ms 最大间隔。成功运动段仍属于修改前的传输配置，**未在最终配置下再次做动作复核**，不得给旧运动数据套用最终时序指标。
- 首次动作六轴不动、夹爪开合；保留用户反馈和失败包。修正原封装关闭自动模式帧发送与 MOVE_J 入口不一致的问题后，现场第二次运动成功。未提高速度/幅度或关闭保护。返回斜坡结束时短暂未到位，随后保持段到位，没有持续控制器故障。
- RGB CameraInfo 发布的 D 为零，但设备服务返回非零 `r_k`；需在几何视觉使用前核实，不能声称内参精度已验证。`RD1001` 是驱动返回的 sensor platform string，不是已验证完整固件版本。
- 本轮只验证正常目标保持停止，未实测急停、断流看门狗、全工作空间线缆或视觉闭环。Astra 退出时有参数清理提示，进程正常结束并已成功重启；原日志保留。
- 结束时记录显示机械臂仍为 MOVE_J、六轴使能、无故障，约 `[83.551,2.737,0,-1.132,24.567,5.557]°`，夹爪约 39.5 mm；没有自动失能/reset/回零。相机及本轮接收进程已正常结束。后续硬件任务仍须读当时实时状态。

## 证据位置

- [H0 报告](reports/H0_HARDWARE_REPORT.md)、[成功动作短片](results/hardware/h0/20261116_2051/evidence/motion_success/clip.mp4)、[动作与接收时序图](results/hardware/h0/20261116_2051/evidence/motion_success/motion_and_timing.png)。
- `results/hardware/h0/20261116_2051/evidence/` 包含真实 RGB、uint16 深度小样本、两路内参、静止/失败/成功/重启短片、真实关节/夹爪及全部接收时间；最终 240 s 验证在 `evidence/final_validation/`。为提交体积抽取的 SDK 缓存快照明确标为约 1 Hz，原始时间不变。
- 完整本地运行目录及全部周期样本/AVI 保留但不提交；大 CAN/rosbag 在 `results/raw_large/hardware/h0/20261116_2051/`。bag 只覆盖若干运行开头的 10 s，不能称作较晚运动的全量 bag。没有删除唯一原件或另建压缩归档。

## 模型路线的既有成果与未完成项

开工包已有环境隔离/源下载脚本、来源锁定清单、门生成器、配置/查看器、支架 OBJ/预览/来源说明、四张用户安装照片和装配规则。既有单/双门 XML 曾在独立准备环境用 MuJoCo 3.3.0 编译并静止步进 2 s；[开工验证](reports/KICKOFF_VALIDATION.md) 不含机器人控制，也不是本轮 Linux 的整机验证。

模型生成、本机装配、P4/P5 与 P6 单门已有上方分版本记录；当前 front60_v2 单门清单已完成，双门仍是后续扩展。下一步研究实施以顶部 R0/B0 为准。使用已有生成器，不重新从零编写整套装配逻辑。

遵守 `accessory_payload_mode=omitted` 和 `synthetic_aligned_rgbd`：附件显式零质量，仿真理想对齐 RGB-D 不冒充本次实物标定。手眼及称重不阻塞名义装配。

下一轮先查看 `git status` 并正常拉取；仿真环境缺失时运行 `bash scripts/setup_env.sh`。本地完整流程见实时调试文档，默认查看命令为 `bash scripts/project_env.sh python scripts/live_assembly.py --watch`。本轮续接不执行任何 `h0_*` 硬件入口。


### 2026-11-23 20:08 接续实测索引

固定时钟下的扰动教师已实采 50,776 个 20 ms 转移。A0–A4 五组配对 BC 已训练，A0/A1 各侧 C02–C05 均 0/4。全程原机制 H32-u1 两侧 Warp 名义通过，u5、u10 前拉重新失败。另一个只拟合单个补偿系数的共同 seed0 监督包已在原始 native3.3、CPU3.16 与 Warp3.16 各自双侧名义闭环通过；标准 Actor、收集和想象接口均已接入。完整 C 与新包 H32 单列。详细证据见 reports/B0_RECOVERY_RESULTS_20261123.md、reports/B0_H32_RECOVERY_20261123.md、reports/B0_RECOVERY_BACKENDS_20261123.md。
