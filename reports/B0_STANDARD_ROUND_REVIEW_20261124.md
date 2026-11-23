# 7180672 标准迁移轮审查与下一步依据

审查日期：2026-11-24（Asia/Shanghai）。范围：规划提交 `95159f7` 后四个实验提交至 [71806725b66e1aec0ac03536737edf31e669ac40](https://github.com/kaiwen123-yang/dog-and-arm/commit/71806725b66e1aec0ac03536737edf31e669ac40)，变更清单共 119 个文件。本次重点核对实际配置/代码、全部正式逐案分数及训练清单，回读固定官方 collector/replay 源码；没有重新载入 AutoDL 大权重/全部原始数组，没有新训练、仿真、视频复跑或硬件执行。机器复算见 [audit_summary.json](../results/b0/standard_review_20261124/audit_summary.json)。

## 1. 结论和用户决定

**标准迁移仍未通过 B0-04，最终候选为空。下一轮集中完成迁移，成功后才做算法开发。** 原实验报告的主要计数和预算复算一致。已对齐的机制应继承；下一轮具体工作是对齐逐 lane 终止/复位的采集生命周期、补足真实接触覆盖、以原损失预热 WM，再推进单一标准配方的实际联合学习。[执行计划](../docs/B0_STANDARD_TRANSFER_PLAN_20261124.md)

## 2. 逐案与成本复算

| 项目 | 核对结果 |
| --- | --- |
| 配置/种子 | 8 条配置链，全部 seed0 |
| 正式名义 | 23 个 checkpoint×backend 组合，各十项 Warp；230 条均失败 |
| 首个 2 ms | 129/230＝56.087%，全部为 door_force_limit |
| 登记阶段事件 | 仅 canonical u350 的前拉 release；后续 retreat_arm 未完成 |
| 分项闭合 | 230 案×两坐标＝460 条，归一化分项和最大残差 2.22e−16 |
| 训练过程 | 15 个进程退出码均为 0；续训前缀按父节点去重 |
| 新增学习 | 1,350 H32、13,500 WM、27,000 Critic minibatch |
| 数据/想象 | 3,081,019 完整数值有效在线转移；7,296,000 lane 控制区间；11,059,200 imagined steps |
| 时间 | 进程合计 2.069350 小时；重叠合并墙钟 0.664912 小时；独占 GPU 小时 NA |

来源：[逐案 CSV](../results/b0/pair_units_v1/nominal_segments.csv)、[分项 JSONL](../results/b0/pair_units_v1/nominal_score_details.jsonl)、[训练清单](../results/b0/standard_baseline_20261124/contact_training.json)及各 run 的 outcome/updates。这里的完整有效转移采用训练采集器的数值/容量口径，可包含首次任务门槛失败所在的完整 20 ms，不等于成功控制区间。230 次评分重复的是同一组十项，不是 230 个独立泛化任务。

其他失败原因：operation_station_drift 43、finger_non_grasp_handle 25、reference_exhausted 9、grip_base_or_handle_error 9、wheel_support_or_tilt 7、release timeout 5，gripper_base_handle/robot_panel/夹爪持续饱和各 1。

## 3. 已修复项与训练预算不能混称

固定 effort 的真实/想象奖励和 reset 哨兵已验证：1,640 个合法完整区间的六项 tracking 和限位项相同，J2 同物理变化动作率罚比 3947.84。两条 u0 网络逐张量一致，后续到 u500 均有实际采集/训练/正式评分。[单位测量](../results/b0/pair_units_v1/measured.json)

ReturnSampler、有效转移驱动 Ratio、逐参考末帧、握持 WM 数据、统计固定、逐样本 lane/age 都有真实执行路径和回执，不能继续写为未实现。**但两条 u500 保留旧采样/调度作为单位对照；最完整的 lane_age_s0_v1 只有 u50、54,028 条有效转移。** 不能把单位实验的 u500 预算套给整合配方。

固定统计、gain32、2H1＋8H7 minibatch 和离线教师数据是平台配方，不是官方默认。它们的来源、成本和效果继续单列。固定官方八存储帧监督七次后继，不把 H7 当成漏训一步。

## 4. 接触覆盖：事实与尚未证明的原因

固定统计 u50 保存的在线 replay 如下。来源：[重放抽样核验](../results/b0/pair_sampling_audit_v1/replay_draw_grip_fixed_stats_u50.json)。

| pool | 合法起点 | reference open/hold | 有指力记录 | 整个首区间持续双指 |
| --- | ---: | ---: | ---: | ---: |
| H7 WM | 15,707 | 0 | 594 | 0 |
| H1 WM / H32 Actor | 24,812 | 572 | 933 | 0 |

原抽样的 Actor open/hold 采样概率约 2.305%，lane/age 约 2.601%。持续双指是首个控制区间全部十个子步两指都 >0.01 N，不是起始瞬间是否接触；其他未保留指力的样本是未知。新抽样改善 episode 多样性，不能生成不存在的接触长窗。

审查特别核清：`contact_warp.step_contact` 在任务失败后继续十子步，`valid_full_interval` 由数值/容量决定；`collect` 把该首次失败完整区间加入 H1/Actor，下步才移除 lane。因此“首2ms失败起点全部被 Actor 过滤”的解释不成立，不应据此新建教师 Actor 起点池。正式评估器首失效停止计分，训练和评分语义必须分别记清。[采集器](../learning/b0/contact_training.py) · [物理步进](../learning/b0/contact_warp.py)

更具体的未对齐流程是：当前 lane 终止后等同步 40 步 cohort 结束才重新采集；固定 [mjlab 环境](https://github.com/HybridRobotics/mjlab_research/blob/dd51a9fcc98791a2f0b018b3c7f71a3eefd5ecdd/src/mjlab/envs/manager_based_rl_env.py)逐 lane 自动复位，固定 [SuperMimic runner](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/runners/supermimic_runner.py)持续存 pre-step 行。当前快失败 episode 一行即停，长 episode 可多行，改变覆盖和资源利用。这个差异已证，是否是控制失败主因还没有配对结果。下一轮对齐时必须维护独立真实前缀/history/clock，以及显式 episode 边界；现有仅按连续 valid 建 H7 的写法不能直接跨 reset 复用。

## 5. WM 和首命令给出的实际线索

相同冻结双指 H32 集的 TCP P95，单位 mm：

| WM | 前拉 | 背推 |
| --- | ---: | ---: |
| 常速外推 | 13.95 | 11.86 |
| held_r2 | 50.53 | 40.36 |
| 加握持窗 u50 | 238.55 | 264.18 |
| 再固定统计 u50 | 104.18 | 107.70 |
| 再逐 lane/age u50 | 242.02 | 196.77 |
| canonical u500 | 251.55 | 85.34 |
| effort u500 | 262.48 | 24.32 |

前拉 412 窗/51 lanes、背推 450 窗/56 lanes，相互重叠，不能当成同数独立试验。固定统计缓解部分退化，没有解决双侧接触；常速在近静止集上较好，也不证明它能代替动作条件动力学。[误差表](../results/b0/pair_wm_comparison_v1/physical_errors.csv)

27 次 WM 评分、新独立采集 80 cohorts/5,120 lanes/28,769 完整有效转移/4,716 提前终止与清单一致。它们是同一训练参考上的独立轨迹，不是 H 未见任务。H7 状态 loss 落在 0.008527/0.006413 也不能直接声称达论文 G1 图3误差，状态通道/尺度/场景不同。[WM 索引](../results/b0/pair_wm_comparison_v1/index.json)

native u50 同初态分块诊断中，教师可完整执行首 20 ms；仅替换策略六臂指令，两侧首 2 ms 已超力。只替换夹爪导致开口、无接触力，不能当稳定握持改善。[canonical 入口](../results/b0/pair_units_v1/native_entry_canonical_u50.json) · [effort 入口](../results/b0/pair_units_v1/native_entry_effort_u50.json)

已有 H7 梯度只测 native 两状态、J5/夹爪和单一幅度，部分正负响应小于非线性二阶量；它提出 WM 动作响应疑点，不构成 Warp/H32 全域梯度结论。encoder 的 J4 归一化幅度存在分布偏移，但 latent 饱和比例小于 0.12%，不支持默认重建网络。[encoder](../results/b0/pair_units_v1/encoder_u10.json) · [梯度脚本](../scripts/b0/check_contact_gradient.py)

## 6. 下一轮决定与目标差距

下一轮保持一个主配方，最多一个解释明确的小预算控制；先对齐采集生命周期和边界，补训练身份的多接触模式数据，用原 H1/H7 WM 目标预热，然后真实 H32 联训。已有修复和失败均保留，不再重复单位实验，不使用新奖励/BC/解析反馈补一个“标准成功”。

正式出口仍是同一标准候选十项 nominal→各 D≥18/20→连续双侧 Warp 各1条 nominal 通过、C每侧≥18/20及同包 native 两侧各1条完整 nominal 通过→独立 seed1/2→冻结后各 seed/侧 H≥40/50，完整回报按协议同时达 0.90 或项目 0.88 接近带。

当前接触名义 0/10，后续 D、完整任务、C/native、seed1/2、H 未执行，完整回报及距离 0.88/0.90 都是 NA。十片段均值 0.22961/0.25963、一个释放片段 0.97191 均不能替代它。独立结果组织已建立，但标准功能基线尚未获得；没有可信的整体完成百分比或必然完成日期。

本次只修订计划/记录和入口一致性，原实验数据、配置与代码不变。旧计划和指标解释保留历史身份，当前启动词见 [B0_START](../prompts/B0_START.txt)，每日细节见 [DAILY_WORK_LOG](../DAILY_WORK_LOG.md)。
