# 27284e2 轮审查：接触首动作与世界模型联训

审查日期：2026-11-24（北京时间）。实验截止 [27284e2e7792d17376410a0d7459398f7ca1927b](https://github.com/kaiwen123-yang/dog-and-arm/commit/27284e2e7792d17376410a0d7459398f7ca1927b)，本轮从 ee41ee3 接续。**标准迁移仍在 B0-04；最终候选为空，完整双侧物理归一化回报 NA。** 下一轮继续固定 SuperMimic 核心，先处理首动作响应与 WM 数据衔接，迁移成功并冻结独立结果后再开发算法。

本次审查读取代码、配置、已提交逐案 JSON/CSV/JSONL 和固定官方源码，独立复算评分与预算；没有重新读取 AutoDL 大 checkpoint/原始 NPY，没有新训练、物理仿真或硬件动作。不将只读复算称为原始仿真重放。[复算清单](../results/b0/lanes_review_20261124/audit_summary.json) · [原始实验 manifest](../results/b0/standard_lanes_20261124/baseline_manifest.json) · [下一轮计划](../docs/B0_CONTACT_RESPONSE_PLAN_20261124.md)

## 1. 主要成绩成立，当前缺口仍是物理接触

| 审查项 | 复算结果 | 含义 |
| --- | --- | --- |
| 六个冻结节点 u0/1/10/50/100/200 | 各 0/10，共 60 案，36 案首 2 ms 超门力，0 个阶段事件 | 没有接触名义候选；旧 7180672 的 230 案另计 |
| 评分分项与分母 | 60 案 × 两坐标共 120 项，最大归一化残差 1.11×10⁻¹⁶ | 未发现分项求和/吸收余长算术错误 |
| 真实 H32 联训 | 200 次 Actor、2,000 个 WM、4,000 个 Critic minibatch | 三段新增为 50＋50＋100，不能相加累计端点成 350 |
| 有效策略 / 前缀 / 总控制区间 | 219,677 / 56,803 / 276,480 | 前缀不算策略经验；首次硬失败的完整数值有效区间可以用于动力学 |
| 想象步 / 失败后诊断子步 | 1,638,400 / 25,868 | 后者是 2 ms 子步，已含在完整采集区间内，不能另加成策略存续 |
| 恢复 | u50、u100 显式行政截断后重建真实前缀；父末点与子起点包相同 | 不是物理状态无缝恢复；u200 的 2 次待调度更新尚未执行 |
| 三个联训进程时长 | 合计 310.127 秒 | 不包含补采/预热/评分，也不是共享 GPU 独占成本 |

逐案依据：[nominal_segments.csv](../results/b0/standard_lanes_20261124/nominal_segments.csv)、[评分分项](../results/b0/standard_lanes_20261124/nominal_score_details.jsonl)、[恢复回执](../results/b0/standard_lanes_20261124/restart_receipts.json)。u200 十片段 effort 均值为 0.18180，这个分母不是完整任务，不能用 0.90 或 0.88 减它。

逐 lane 复位是真实改进：同一冻结策略、相同采样种子、各 128,000 个 2 ms 子步，有效策略区间 3,135→7,593，占比 24.49%→59.32%，为原来的 2.422 倍。两种采集都没有完整 20 ms 的持续双指区间，说明它解决了空等浪费，尚未解决握持。[匹配对照](../results/b0/lanes_matched_v1/comparison.json)

## 2. 新证据一：预热数据没有全部留在联训中

`lanes_modes_v1` 的 512 条训练 lane、18,223 个 H1 区间和 15,242 个 H7 窗，确实进入了新增 1,000 minibatch WM 预热。预热同时使用旧 Warp grip 数据和 native 数据，验证 split 不参与训练。[预热配置](../results/b0/lanes_wm_v1/config.json) · [数据覆盖](../results/b0/standard_lanes_20261124/coverage.json)

但 `standard_lanes_v1.yaml` 只替换 collector、WM 初始化和检查节点，继承的 `wm_grip_cohorts` 仍只有旧 `recovery_b_grip_challenge_r1`。在线窗口可用时，联训的实际规则为：

| 每次 H32 前的 WM 更新 | 在线 | native teacher | 旧 Warp grip | 新 lanes_modes_v1 |
| --- | ---: | ---: | ---: | ---: |
| 每个 H1 batch，2 个 | 256 | 0 | 0 | 0 |
| 每个 H7 batch，8 个 | 192 | 32 | 32 | 0 |

在线不足时会使用既有离线回填规则，但新多模式数据仍没有加载入口。**数据源断点已经证实；它是否造成全部预测退化或策略失败，尚未证实。** 下一轮应让必要训练数据实际持续参与原 H1/H7，而不是只在 YAML 写一个未被消费的路径。[联训实际配置](../results/b0/lanes_s0_v1/actual_config.json) · [加载入口](../scripts/b0/train_contact.py) · [实际更新](../learning/b0/contact_training.py)

同一个冻结双指验证集（前拉 412 窗/51 lanes，背推 450 窗/56 lanes）出现明显早期回退：

| H32 TCP P95，mm | 前拉 | 背推 |
| --- | ---: | ---: |
| held_r2 | 50.53 | 40.36 |
| 预热 +1000 | 15.65 | 16.45 |
| 联训 u10 | 127.19 | 149.47 |
| 联训 u50 | 54.07 | 37.96 |
| 联训 u100 | 79.26 | 52.48 |
| 联训 u200 | 26.65 | 19.91 |

u10 是预热出口的约 8.13/9.09 倍；u200 有恢复但仍差于预热。新多模式验证集的双指 P95 也从预热 20.83/15.60 mm 变为 u200 的 24.71/23.06 mm。下一轮必须在 u1/u10 等早期节点同时看响应和物理能力，不能只看最后一次验证。[预热](../results/b0/lanes_val_001000_recovery_b_grip_challenge_r1/errors.csv) · [u10](../results/b0/lanes_joint10_grip/errors.csv) · [u200](../results/b0/lanes_joint200_recovery_b_grip_challenge_r1/errors.csv)

## 3. 新证据二：有效转移很多，握持起点仍很少且立即结束

三段在线采集按参考相位累计：

| 相位 | 有效策略区间 | terminal 区间 |
| --- | ---: | ---: |
| approach_arm | 41,800 | 416 |
| grasp | 41,764 | 695 |
| open | 625 | 625 |
| hold | 462 | 462 |
| release | 4,999 | 210 |
| retreat_arm | 36,794 | 689 |
| post_release_hold | 93,233 | 1,696 |

open/hold 只有 **1,087/219,677＝0.4948%**，前拉 591、背推 496，全部是 terminal 区间。这些在 open/hold 开始、一个控制区间就终止的 episode 不能提供合法 H7 起始窗。首次失败区间仍可进入 H1/Actor 池，不能把问题描述为“所有失败数据被过滤”。下一轮要查看真正抽中的 minibatch 与 Actor 起点，而不是根据采集总量猜覆盖。[复算相位表](../results/b0/lanes_review_20261124/audit_summary.json)

所有策略区间中，双指载荷在十个 2 ms 子步上始终同时大于 0.01 N 的数量为 0。这个定义不等于没有发生过接触；数十牛的首步门力正是强接触。也不能把包含失败后积分的 `valid` 区间称为安全存续。

## 4. 新证据三：首 20 ms 的张夹响应被两套 WM 明显低估

现有 u50 诊断在前拉/背推各一处重建前缀上施加保存的策略首命令，此后 31 步采用相同记录参考命令。两模型和真实物理均用 `q29−q30` 得到两指总开度，单位一致。

| 该诊断分支第一段 20 ms | 前拉 | 背推 |
| --- | ---: | ---: |
| 真实总开度 | 68.35 mm | 66.51 mm |
| 预热 WM 预测 | 22.41 mm | 25.98 mm |
| 联训 u50 WM 预测 | 22.04 mm | 25.95 mm |
| 真实该区间峰力 | 51.08 N | 33.19 N |

因此，预热 WM 的 H32 TCP 误差 18.91/19.20 mm 并不能说明策略首动作已被准确建模；第一步的夹爪变化被低估，后续公共参考动作又改变了轨迹。联训 u50 的 H32 TCP 误差为 582.12/69.76 mm，属于另一个长窗问题。[分支原始 JSON](../results/b0/standard_lanes_20261124/entry_response_matched_u50.json) · [脚本](../scripts/b0/measure_lane_response.py)

该证据有三项边界：

1. 这是两处 u50 状态的失败后积分诊断，不是 u200，也不是正式评分首 2 ms 的开度，更不是 Actor 自主闭环 H32。
2. 脚本借用正式评分保存的 `clipped_action`，没有在重建训练 state/history/clock 上现场重新查询 Actor。下一轮要补齐这一点。
3. 脚本使用教师逐子步 phase；对齐入口的前三个子步仍为 grasp，正式 stable_grip 从首子步就按 hold 检查 6 N。诊断首失败 tick 为 4/5，正式为 1，不能直接混比。脚本背推还硬编码旧参考目录；v2 登记旧前缀相同，不能据此直接判物理错误，但应从实际 source 显式读身份。正式裁判和阈值保持不变。

## 5. 22 mm 是条件范围，原目标也并非没有张口惩罚

22.04/22.47 mm 是 **open/hold 且完整 20 ms 双指持续成立**的条件样本最大夹口命令，不是所有训练数据上限。全部相位下，native 两侧覆盖 10–90 mm，新多模式两侧约 9.79–100 mm，旧 grip 前拉约 9.79–36.12 mm、背推约 9.80–50.82 mm。不能由条件范围证明“模型从未见过 42–55 mm”，也不能直接把夹口裁到 22 mm。[动作覆盖](../results/b0/standard_lanes_20261124/coverage.json) · [条件统计](../results/b0/standard_lanes_20261124/held_action_support.json)

要查的是**同一握持状态、前一动作、臂/腿轮组合下的局部状态—动作后继**。前缀最后命令为 10 mm，真实起点总开度约 21.44/21.74 mm，这两个量也必须分开。

按已记录的 u200 命令与固定基础 effort 单位复算，20 ms 动作率项为 `−0.02×0.1×(Δu/unit)²`：

| u200 入口 | 仅夹口动作率 | 仅 J2 动作率 | 六个正 tracking 项总上界 |
| --- | ---: | ---: | ---: |
| 前拉 | −0.18767 | −0.74225 | +0.1 |
| 背推 | −0.35863 | −0.01057 | +0.1 |

这只是现有公式与命令的代数复算，不是新仿真或正式 2 ms 截断回报。它说明当前原目标已经对这些突变给出显著惩罚；还不能把张夹归因为“没有握持奖励”。应核验当前 replay 初态、WM 对动作的导数、未来 tracking、生存权重和 Critic bootstrap 如何影响真实更新方向。[首命令](../results/b0/standard_lanes_20261124/grip_commands.csv) · [固定动作单位](../results/b0/standard_transfer_action_audit/action_units.json) · [官方更新](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/learners/policy_learner.py)

## 6. 已查接口与尚未证明的原因

Actor、WM 和物理的 canonical 裁剪/scale/offset 路径一致；总夹口转换为单指 servo 时乘 0.5，状态测量再取两指差，没有发现重复倍数。gain32 是网络参数化，不是物理伺服增益；保存命令已经包含它。固定 WM 统计通过显式更新入口控制，没有证据表明 `.train()` 暗中改变统计。lane reset 的真实前缀、episode 内 H7 与行政恢复语义可追溯。[模型映射](../learning/b0/model.py) · [物理映射](../learning/b0/physics.py) · [lane 采集](../learning/b0/contact_lanes.py)

手指速度输出单位 0.02 是 m/s 增量换算，不是预测开度硬上限。对真实端点速度增量使用原 GenCoord 积分，可另作离线残差分解，区分网络预测与积分近似；未实测前不改步长、积分器或加新网络。

本次没有证明：数据断点是唯一根因、夹爪是唯一失败通道、原 tracking 必然无法完成任务、固定积分必然错误。下一轮依次核验这些具体不确定项，实施数据适配后完成真实 H32 与原正式评分。[执行计划](../docs/B0_CONTACT_RESPONSE_PLAN_20261124.md)

## 7. 决定与目标距离

保留已完成的逐 lane 采集、固定 effort、ReturnSampler、Ratio、clip 末帧、lane/age、固定统计及原 H1/H7/H32 核心。下一轮实施训练身份首动作分支，让必要数据持续进入联训，分解原目标并按一条固定 seed0 配方实训；至多一个明确的 WM 数据保留小对照。继续标准迁移，不启动算法开发。

尚待：同一候选十项 10/10 → 每项 D≥18/20 → 连续双侧 Warp nominal 与 C 每侧≥18/20、同包 native 双侧完整 nominal及持续 H32 → 独立 seed1/2 → 三 seed 冻结后 H 每 seed/侧≥40/50。完整回报目标 0.90 或本项目 0.88 接近带，必须同时通过物理门槛。当前完整回报 NA，不给虚构的完成百分比、剩余分数或天数。[详细差距](../docs/GOAL_GAP_20261124.md)
