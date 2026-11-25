# 固定官方 SuperMimic 向 M1＋Piper 迁移，11 月 25 日续训

北京时间 11:44:58，AutoDL 的 tmux 会话 `b0-official-20261125` 已持续训练至 u5102，最近完整滚动恢复点为 u5100。u5000 正式包已由另一进程完整回读。主段目标为 u10000；u7500/u10000 原物理结果、延长裁决与最终回报在交接时尚未产生。B0-04，候选 null，合格双侧回报 NA，V0=0。[现场核验](../results/b0/standard_official_flow_continuation_20261125/tmux_progress.json) · [当日日志](../DAILY_WORK_LOG.md)

## tmux 交接和本轮实付

用户在 10:58 暂停，11:35 明确恢复。先从父包 u4991 执行九个保留更新，在 u5000 原子发布后切换到 tmux。交接前后最近完整物理 tick 均为 13,676，优化器计数均为 5,000 / 50,000 / 100,000（Actor / WM / Critic），交接丢弃优化步为零。两段启动都读取完整一致状态。u5000 独立核验包括 4,096 条 lane、136 个 solver 数组、162 个优化器张量、采样器和 RNG。[交接边界](../results/b0/standard_official_flow_continuation_20261125/tmux_handoff.json) · [独立恢复](../results/b0/standard_official_flow_continuation_20261125/restored_u005000.json)

u4992–u5100 连续 109 次更新，保留新增 Actor 109、H7 WM 1,090、Critic 2,180，完整有效转移新增 1,115,748。u5100 累计 52,240,463 个有效转移，下一拍训练已在同一 tmux 进程继续。两侧训练有效区间中，整段两指最小力均高于 0.01 N 的计数为前拉 11,154、背推 13,019。Git 中的更新和计数日志截到交接核实的 u5100；此后的实时进度以 AutoDL 为准。[逐更新](../results/b0/standard_official_flow_continuation_20261125/updates.jsonl) · [逐 tick 双指覆盖](../results/b0/standard_official_flow_continuation_20261125/physical_contact_counts.jsonl)

u5000 独立开发块使用 seed 825001，256 lanes × 64 ticks 共 16,384 个区间，其中有效 11,251 个、有效 terminal 270 个、有效整段双指 1,911 个。H32 的全体合法窗前拉/背推分别 1,943/1,237 个，TCP P95 分别 6.203/5.058 mm。H32 整窗双指有 2/17 个，TCP P95 为 3.179/2.444 mm。该块使用冻结统计，优化步为零，未回流训练；2 个前拉长窗只代表本块相应样本。u5000 完整任务、接触十项及 free 均未重评。[独立评分](../results/b0/standard_official_flow_continuation_20261125/current_policy/u005000/scores.json) · [按参考、phase、年龄及物理接触分层](../results/b0/standard_official_flow_continuation_20261125/current_policy/u005000/strata.csv)

训练、评测及端点判断分别在 train、eval、decision 窗口。端点脚本读取 u4991/u7500/u10000 的逐案与就绪证据。若 u10000 双后端共同确认新增原接触通过或完整阶段、另一侧保住原能力且通过退化检查，可自动启动同链延长；需要单后端复核、纯 Actor 新抓持或双侧窗口判断时保留原数据待审。达到资格或 V0 时转入相应证据核查。延长启动命令只接受已批准的物理决定。交接时这些结果均待执行。[运行登记](../results/b0/standard_official_flow_continuation_20261125/run_manifest.json)

## 父点恢复与本轮记账

已实载 4,991 次 Actor、49,910 批 WM、99,820 批 Critic 的状态，在物理 tick 13,652 处恢复 4,096 条 lane、上拍动作与连续物理状态。逐值核验 136 个 solver 数组、162 个优化器张量、采样器及 RNG。四组统计、51,124,715 个有效转移和 Ratio 均与冻结回执一致。尚需 3,605 个有效转移触发下一次更新。[独立恢复回执](../results/b0/standard_official_flow_continuation_20261125/restored_u004991.json)

直接 WM 祖先成本 14,850 批。主链 0–1000、旧续训 1001–4991 和本轮使用独立账目。旧续训的保留成本为 3,991 / 39,910 / 79,820，回滚为 6 / 90 / 120，以上顺序均为 Actor / WM / Critic。本轮暂停时实付为 0 / 0 / 0。暂停当时 u5000 尚未运行，其后结果见上文。原父点 Warp/native 接触各 2/10，已通过片段在真实前缀后具有双指抓持。

## 原裁判就绪诊断

先用 u4991 已存的四条连续 frame0 轨迹登记固定窗。原 servo 轨迹保存状态、实际阶段及夹指力，缺逐拍四轮法向载荷与裁判各阶段的 last_not_ready。为补齐这些量，用父冻结包在原 Warp 2 ms、native MuJoCo 3.3.0 2 ms 各重放前拉和背推，共 4 案。四案首次失败、时长、阶段事件名称和事件步均复现。native 两案的 qpos、qvel、原始动作与步号逐值相同。Warp 两案的原始动作最大绝对差分别为 1.38×10⁻⁵ 和 9.91×10⁻⁶。下表的就绪量来自补采回合。[固定物理窗口](../results/b0/standard_official_flow_continuation_20261125/readiness_windows.json) · [逐案、逐量轨迹比较](../results/b0/standard_official_flow_continuation_20261125/readiness_u004991.json)

| 后端与侧别 | 首次失败 | 时刻 (s) | 末拍实际 / 参考阶段 | 末拍冻结端点距离 / 姿态误差 | 连续就绪 当前 / 最好 / 要求 (2 ms 拍) |
|---|---|---:|---|---|---:|
| warp 前拉 | door_contact_outside_manipulation | 14.066 | pregrasp / approach_arm | 50.174 mm / 0.00833 rad | 0 / 0 / 75 |
| warp 背推 | wheel_support_or_tilt | 11.594 | pregrasp / pregrasp | 34.218 mm / 0.01018 rad | 0 / 0 / 75 |
| native 前拉 | timeout:pregrasp | 15.564 | pregrasp / grasp | 56.199 mm / 0.00252 rad | 0 / 0 / 75 |
| native 背推 | timeout:settle | 11.994 | settle / approach_arm | — | 14 / 385 / 500 |

预抓要求同时达到 3 mm、0.02 rad，并连续 75 拍。三个预抓末拍的距离分别为门槛的 16.72、11.41 和 18.73 倍，姿态误差分别为门槛的 0.42、0.51 和 0.13 倍。Warp 前拉原判定因提前触门停止。Warp 背推在第 5,748–5,797 拍连续 100 ms 至少一轮载荷低于 1 N，达到原失载时限。native 背推的第一个停车就绪段在第 3,167 拍中断，四轮载荷均超过 100 N，但线速达 5.175 mm/s，超过 5 mm/s 的原停车要求。该停车阶段共有 15 次由就绪转为未就绪。

本段诊断产生四条完整失败轨迹及逐微步就绪数组，新增优化步和训练经验均为零。父节点的正式任务分母维持原登记。完整成功视频等待标准 Actor 在原裁判的 frame0 回合实际通过。
