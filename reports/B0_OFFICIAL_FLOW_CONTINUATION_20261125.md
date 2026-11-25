# 固定官方 SuperMimic 向 M1＋Piper 迁移，11 月 25 日续训

父实验为 official_flow_s0_v1 的 u4991，启动版本为 be398cc3c9532d90c852a7f221fbf64c2b7e4e10。北京时间 09:59，AutoDL 的独立恢复进程与父包四案就绪诊断已完成。主段训练脚本等待共享显存分配。当前 B0-04，候选 null，合格双侧回报 NA，V0=0。[运行登记](../results/b0/standard_official_flow_continuation_20261125/run_manifest.json) · [当日日志](../DAILY_WORK_LOG.md)

## 父点恢复与本轮记账

已实载 4,991 次 Actor、49,910 批 WM、99,820 批 Critic 的状态，在物理 tick 13,652 处恢复 4,096 条 lane、上拍动作与连续物理状态。逐值核验 136 个 solver 数组、162 个优化器张量、采样器及 RNG。四组统计、51,124,715 个有效转移和 Ratio 均与冻结回执一致。尚需 3,605 个有效转移触发下一次更新。[独立恢复回执](../results/b0/standard_official_flow_continuation_20261125/restored_u004991.json)

直接 WM 祖先成本 14,850 批。主链 0–1000、旧续训 1001–4991 和本轮使用独立账目。旧续训的保留成本为 3,991 / 39,910 / 79,820，回滚为 6 / 90 / 120，以上顺序均为 Actor / WM / Critic。本轮截至 09:59 实付为 0 / 0 / 0。u5000 开发与独立恢复、u7500/u10000 物理评分、延长裁决及正式资格均待运行。原父点 Warp/native 接触各 2/10，已通过片段在真实前缀后具有双指抓持。

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
