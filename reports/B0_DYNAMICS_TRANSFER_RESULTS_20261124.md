# SuperMimic-M1Piper-standard-v1｜0.25 ms 训练与原 H32 开发对照

**标准迁移仍停在 B0-04。** 重标 C20 达到唯一实验 WM 的预登记替代条件。两支各完成 10 次真实 H32；5 组原正式 Warp 十项、50 案全部失败。冻结策略的 48 个闭环开发复测在停止前均无双指接触。本轮没有达到单链延长条件，最终候选为空，完整双侧物理归一化回报为 NA。[机器清单](../results/b0/standard_dynamics_20261124/baseline_manifest.json)

集中轮从 GitHub main `781cd1d` 开始。现场固定 SuperMimic `abc124c` 和 mjlab_research `dd51a9f`，使用 front60_v2 单门场景。正式 Warp 保持 2 ms，原生正式后端保持 MuJoCo 3.3.0，门力上限为 6 N。开发对照共用 seed0 的 B0-03 Actor。原协议中的独立 seed1/2 与 H 另有冻结条件。[预登记](../results/b0/standard_dynamics_20261124/pilot_registration.json) · [正式协议](../docs/B0_PAPER_BASELINE_PROTOCOL.md)

## 物理步长如何影响合法训练标签

11 个已有窗口包括 7 个不同的未终止腕速窗口，以及前拉、背推 hold 的 u0 原命令和 u0 只替换参考臂的命令。每档两次独立复放。固定控制实验保持全部 23 路归档 ctrl；同状态伺服与完整前缀实验每 2 ms 读取上一外部周期起点的 bias，内部每个细步重算动力学。每条轨迹各自记录力、site 的区间起点，q/v 的积分端点，以及裁判获得该次解的时刻。[11 窗清单](../results/b0/standard_dynamics_20261124/warp_windows/registration.json) · [分单位逐窗差异](../results/b0/standard_dynamics_20261124/warp_windows/comparisons.csv)

| 固定开发窗口和读数 | 实测 | 对训练标签的影响 |
| --- | --- | --- |
| 前拉训练 grasp，t7/b23，固定 ctrl 门力峰值 | 2、1、0.5 ms 分别为 0、44.60、14.14 N | 相同控制也会改变接触的有无与幅度 |
| 前拉 hold/u0，真实前缀和伺服，0.25/0.125 ms | 峰值 51.31/51.32 N | 两档在第一个区间起点均超 6 N |
| 背推 hold/u0，同一对照 | 峰值 33.09/33.10 N | 首区间超力也保留 |
| 背推训练 grasp，真实前缀和伺服，0.25/0.125 ms | 峰值 43.80/43.87 N | 峰值接近，个别背推接触脉冲的逐时刻力差仍可达约 31 N |

四个影响决定的窗口复核至 0.125 ms，选 0.25 ms 作为训练 20 ms 端点的数值近似。数据保留全部细步力峰。合计 228 份 Warp 观测，含重建和前缀共 1,225,840 个 world 物理步；两个 CPU 版本的辅助核验共 1,940 步。[逐窗特征](../results/b0/standard_dynamics_20261124/warp_windows/features.csv) · [步长决定和剩余误差](../results/b0/standard_dynamics_20261124/warp_windows/time_step_decision.json)

## 采集、训练输入及部分终止时间

新身份 `warp_250us_servo2ms_continuous_v1` 每 20 ms 积分 80 步，真实 200 ms 前缀为 800 步，GenCoord 系数为 0.50625。固定输入、外部伺服缓存与引擎内部 bias 分开保存和检查。对 2、0.5、0.25 ms 各做双侧实测，外部命令保持与延迟的重算最大差均为零。ReturnSampler 在细步失效时按实际 dt 计分，位置、速度与基座姿态插值到原 2 ms 参考的对应时刻；8 个时刻以 MuJoCo 广义位移积分独立复算，回报最大绝对差为零。[训练时钟](../results/b0/standard_dynamics_20261124/training_clock_250us.json) · [部分终止回报](../results/b0/standard_dynamics_20261124/partial_terminal_reward_clock.json)

| 离线训练源 | 轨迹或 lane | 合法 H1 | 合法 H7 |
| --- | ---: | ---: | ---: |
| 继承的 native 训练轨迹 | 10 | 13,640 | 13,580 |
| 重采 Warp 握持 | 512 | 13,873 | 11,170 |
| 重采 Warp 多模式 | 512 | 18,479 | 15,495 |
| 重采 Warp 首动作响应，去除同命令重复 | 300 | 4,487 | 3,510 |
| **合计** | **1,334** | **50,479** | **43,755** |

响应训练来自 12 个起点，开发验证来自另外的 6 个起点。握持及多模式各保留 192 条验证 lane。合法 H1 保留首个物理失败但积分完整且数值有效的 20 ms；后续尾段用于诊断。新物理身份的两臂共用同一实际索引，保存源张量、合法起点和实际首批的校验值。重采使用既定行为策略生成 WM 的状态转移监督，H32 策略从标准 B0-03 单独初始化。[实际数据资格](../results/b0/standard_dynamics_20261124/data_qualification.json) · [索引和身份](../results/b0/standard_dynamics_20261124/c20_data_identity.json)

旧 2 ms 的 76,719 个合法 H1 另作原单位复算。在原指位/指速两分量下，两侧 hold/u0 开度误差的解析折中是 −28.537/−43.351 mm，旧 C20+1000 实测 −28.039/−43.437 mm。这解释了这两个分量间的折中。完整 WM 仍用原损失训练。[旧数据逐源复算](../results/b0/standard_dynamics_20261124/old_2ms_finger_component_tradeoff.json)

## C20 配对及 H32 前的选择

两臂继承同一原始网络，采用新物理的 GenCoord 系数和相同的新 Muon＋Adam。重标臂按四个训练源的 source/episode/physical_input_index 给每个合法输入一次权重；变换 75 个状态列和 23 个处理后动作列，保留 5 个 context 列。step0 四源的完整原单位状态与动作 Jacobian，前后相对 L2 差最大约 2.8×10⁻⁷。新数据上原损失的指位分量折中保留约 93.98% 残差。C20 旧统计 +1000 的 hold/u0 开度误差为 −25.443/−40.022 mm，两分量解析折中为 −25.531/−38.656 mm。[训练统计与函数保持](../results/b0/standard_dynamics_20261124/c20_rebase_statistics.json) · [新物理逐样本复算](../results/b0/standard_dynamics_20261124/matched_c20_finger_component_tradeoff.json)

| §4.4 唯一替代条件，误差均为 mm | 同身份 C20 +1000 | 同身份重标 +1000 |
| --- | ---: | ---: |
| 前拉 hold 首动作 TCP | 12.080 | 11.527 |
| 背推 hold 首动作 TCP | 12.376 | 12.074 |
| 前拉握持验证，双指 H32 TCP P95 | 19.674 | 17.853 |
| 背推握持验证，双指 H32 TCP P95 | 25.145 | 14.690 |
| 前拉多模式验证，双指 H32 TCP P95 | 18.019 | 17.573 |
| 背推多模式验证，双指 H32 TCP P95 | 22.766 | 18.647 |

两臂各完成 1,000 批，每臂 200 H1＋800 H7，合计 512,000 次窗口抽样、2,969,600 个监督后继。各节点检查整段每批梯度和有限性，并用原单位状态/动作 VJP 判读递推。各自参数坐标内裁剪前范数超过 1 的批数为 96 和 71。六项重复评分差均为零。北京时间 19:16:36 锁定重标 +1000 进入开发 H32，控制使用同身份、旧统计的 +0。此前 ff2d1e8 的原 WM 保留结论仍为 `selected_wm=null`。[六项选择和成本](../results/b0/standard_dynamics_20261124/pilot_wm_locked.json) · [旧统计全程检查](../results/b0/standard_dynamics_20261124/C20_stability_001000.json) · [重标全程检查](../results/b0/standard_dynamics_20261124/rebase_stability_001000.json)
## 真实 H32 的共同起点和原目标

在 128 个 lane 上用冻结 Actor 完成 5,120 个 20 ms 区间，首次 Ratio 到期时有 2,086 个有效转移，待更新数为 2。两支从同一完整 replay、真实 200 ms 前缀、归一化、Critic、原优化器初态和 RNG 恢复。跨进程回读 136 个 Warp 数据数组以及外部伺服缓存、计数器逐项相同。上游 bootstrap 与 GAE 读同一个 Critic。独立回查实际 u1 的 49 组抽样索引和 256 行首批，涵盖 135 个在线 episode；状态、history、相位、上一动作和首次命令均逐值相同。u1 后两臂继续各自的物理采集。[恢复验证](../results/b0/standard_dynamics_20261124/shared_restore.json) · [两支执行锁](../results/b0/standard_dynamics_20261124/pilot_execution_lock.json) · [首批和原图前反向](../results/b0/standard_dynamics_20261124/h32/preflight_pair.json)

| 原 H32 读数 | 控制 C20 +0 | 实验 重标 +1000 |
| --- | ---: | ---: |
| 同首批任何更新前，想象目标均值 | −0.121016 | 1.105141 |
| 该原图 Actor 梯度 L2 | 25.162 | 72.118 |
| 正常 u1 当次 10 个 WM 批后，Actor/Critic 更新前目标 | −0.721625 | 0.650464 |
| 本臂到 u10 的有效 20 ms 转移 | 13,044 | 12,963 |
| 前拉 open/hold 全程双指区间 / 合法起点 | 0/82 | 0/81 |
| 背推 open/hold 全程双指区间 / 合法起点 | 0/70 | 0/68 |

原目标和原单位 state/action 导数均有限。首次探针发现对同一输入开启梯度后，重新正算表示与官方 detach 路径存在最大 1.31×10⁻⁶ 的浮点差。正式读数使用官方路径的精确前向，原单位输入敏感度从同输入作链式 VJP；此次探针修正增加的参数更新数为零。两臂均实际到 u10，合计 20 H32、200 个联合 WM 批、400 个 Critic 批。共同首块计一次，独立物理采集共 23,921 个有效转移、35,840 个策略区间、2,867,200 个 0.25 ms world 物理步。两臂的 u10 恢复点各有 2 个尚未执行的 Ratio 更新。[控制训练](../results/b0/standard_dynamics_20261124/h32/control/outcome.json) · [实验训练](../results/b0/standard_dynamics_20261124/h32/experiment/outcome.json)

## 原 2 ms Warp 正式接触

相同 u0 的新十案由两臂共用。两臂各自 u1、u10 各评十案，合计 **50 案，0 通过，0 阶段事件**。每个节点均有 6 案在首个 2 ms 超力。下表的时长是从规定初态到首次正式失效的时间。

| 正式读数 | 共用 u0 | 控制 u1 | 实验 u1 | 控制 u10 | 实验 u10 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 十项名义通过数 | 0 | 0 | 0 | 0 | 0 |
| 前拉 stable_grip 首区间门力，N | 51.067 | 51.067 | 51.064 | 51.040 | 51.039 |
| 背推 stable_grip 首区间门力，N | 33.151 | 33.148 | 33.149 | 33.142 | 33.179 |
| 前拉 approach_grasp 存续，s | 1.046 | 1.064 | 1.136 | 0.080 | 2.720 |
| 前拉 release_retreat 存续，s | 1.006 | 1.026 | 1.084 | 0.084 | 4.066 |
| 背推 approach_grasp 存续，s | 1.154 | 1.754 | 2.108 | 0.038 | 0.036 |
| 背推 release_retreat 存续，s | 0.040 | 0.040 | 0.024 | 0.038 | 0.040 |

实验 u10 的前拉首次失效推迟，原因仍是底盘离开操作站位。其背推接近在 36 ms 时发生非抓握面接触，门净力约 139.91 N。控制 u10 的前拉也比共同 u0 更早失效。逐项结果随包保存，片段回报采用原完整计划时长、首失败吸收和固定 effort 单位。[共同 u0](../results/b0/standard_dynamics_20261124/h32/shared_u0_formal.csv) · [控制 u1](../results/b0/standard_dynamics_20261124/h32/control_u1_formal.csv) · [实验 u1](../results/b0/standard_dynamics_20261124/h32/experiment_u1_formal.csv) · [控制 u10](../results/b0/standard_dynamics_20261124/h32/control_u10_formal.csv) · [实验 u10](../results/b0/standard_dynamics_20261124/h32/experiment_u10_formal.csv)

## 联合学习后的世界模型

首个真实联合更新改善了训练首批在线 H7 原损失（控制 4.965→1.242，实验 2.467→0.848），相同节点在独立验证的双指长窗退化。下表为终点 TCP 误差的 P95，单位 mm。

| 独立开发验证 | 控制 u0 → u1 → u10 | 实验 u0 → u1 → u10 |
| --- | --- | --- |
| 握持前拉 | 16.64 → 546.86 → 68.68 | 17.85 → 888.95 → 88.61 |
| 握持背推 | 16.51 → 541.43 → 91.42 | 14.69 → 734.46 → 55.25 |
| 多模式前拉 | 20.75 → 577.24 → 115.46 | 17.57 → 927.39 → 97.34 |
| 多模式背推 | 15.44 → 539.54 → 94.55 | 18.65 → 735.59 → 55.24 |

固定 response H7 抽样窗上，实验臂 TCP 误差均值 2.17→102.32→16.87 mm。u1 的正运动学分解中，先替换基座得到 12.78 mm，再替换关节得到 96.06 mm；两项按向量相加。J2 平均绝对误差 0.0022→0.2000→0.0185 rad。H1 开度平均绝对误差在实验 u10 仍为 16.66 mm。固定首批、开发长窗和实际闭环量各保留各自分母。[实际首批分源复算](../results/b0/standard_dynamics_20261124/h32/matched_joint_source_losses.json) · [固定源 u1 原单位探针](../results/b0/standard_dynamics_20261124/h32/experiment/fixed_offline_vjp_u01.json) · [固定源 u10 原单位探针](../results/b0/standard_dynamics_20261124/h32/experiment/fixed_offline_vjp_u10.json)
## 同状态开发复测与延长决定

两臂的 u0/u1/u10 从 6 个固定开发起点回放，在原 2 ms 和训练 0.25 ms 分别保存完整首命令、门力、双指持续、首失效和阶段事件。每次直接同命令重复，又另起进程复核，共 240 条首动作诊断。原 2 ms 背推 grasp 在 u10 首动作后接 31 条共同参考命令，控制/实验最长双指接触达 426/428 ms。首个 20 ms 均没有持续双指。这一现象触发了预登记的物理复测。[原步长同状态](../results/b0/standard_dynamics_20261124/h32/same_state_formal_2ms.json) · [训练步长同状态](../results/b0/standard_dynamics_20261124/h32/same_state_training.json)

追加的闭环复测保留每个起点的同一初态、历史、上一动作和目标时钟。之后每 20 ms 根据真实后继重新查询该冻结 Actor。双侧 grasp/release 共四个起点、三个策略、两种步长、独立反序重复两次，共 48 案。首命令与前项诊断逐值相同。两次重复的首失效时刻和双指持续时间全部相同。

| 背推 grasp 开发起点 | 共用 u0 | 控制 u10 | 实验 u10 |
| --- | ---: | ---: | ---: |
| 原 2 ms 闭环首失效，ms | 24 | 36 | 36 |
| 原 2 ms 裁判内门力峰值，N | 226.17 | 79.21 | 140.68 |
| 训练 0.25 ms 闭环首失效，ms | 33.75 | 34.75 | 34.50 |
| 训练 0.25 ms 裁判内门力峰值，N | 211.19 | 160.76 | 154.19 |

48 案在停止前合计零次双指同时接触、零阶段事件。实验 u10 在这一开发起点延后失效、降低峰力，正式背推接近在另一初态却从 1.154 s 退至 0.036 s。控制 u10 的正式前拉接近和释放也大幅缩短。按 §5.3，两支均结束于 u10，单链 u50/100/200 延长条件未满足。[两次复测与局部改善](../results/b0/standard_dynamics_20261124/h32/physical_extension_evidence.json) · [本轮决定](../results/b0/standard_dynamics_20261124/round_decision.json)

## 当前阻塞与恢复入口

两支各 2,560 个实际 H32 想象起点可按索引回到训练物理记录。控制有 161 个、实验有 160 个 open/hold 起点，这 321 个抽样实例均从首个 20 ms 内触发物理终止的区间起点出发。相应原始输入都在终止之前。整段双指区间在两支的实际在线采集中也均为零。WM 预热、真正执行 H32 和可复现重采的接口已接通，当前标准策略仍未建立能持续的两侧实际抓握。[实际起点与策略变化](../results/b0/standard_dynamics_20261124/h32/actor_state_and_starts.json)

两支复查了标准 Actor 归一化。B0-03、共同 u0、两支 u1 的初始 count 都为 1,089,050。u10 后控制/实验分别增加 10,958/10,877，等于这两臂在共同首块之后新增的有效转移数。按实际顺序重建 77 维含噪最新传感输入和 540 维目标，十次抽样索引与最终 CUDA RNG 均重复一致。传感统计逐位相等，目标统计与保存值的最大差为 9.32×10⁻¹⁰。换用独立 FP64 累积，最大绝对差不超过 4.18×10⁻⁶。六个验证输入上的 motion |z| P95 从 77.94 降至约 10.76，呈现接触输入相对初始统计的分布变化。策略参数同期也有变化，现有证据不足以把物理退化单归因于归一化。[控制专项复算](../results/b0/standard_dynamics_20261124/h32/control/normalization_replay.json) · [实验专项复算](../results/b0/standard_dynamics_20261124/h32/experiment/normalization_replay.json)

**当前阶段 B0-04，最终候选为 null，完整双侧归一化物理回报为 NA。** 原十项有了同一包 10/10 后才进入每项 D 的 18/20、连续双侧 Warp 名义与每侧 C 的 18/20、同包原 native3.3 双侧名义和持续 H32。独立 seed1/2 以及冻结后 H 每 seed/侧 40/50 均未开启。历史 response u200 的 60 案与 ff2d1e8 的冻结十案单列。标准迁移最终基线尚未冻结。

AutoDL 现场为 `/root/autodl-tmp/dog-and-arm-b0-temporal-v1`。新大资产位于 `results/raw_large/b0/dynamics_20261124/`。两臂的 `h32/{control,experiment}/cohort_state.pt` 保存优化器、replay、RNG、ReturnSampler、Ratio；原工作进程结束时各有两个额度待执行。共享首采的完整 live 状态另在 `h32_shared/`。两个 u10 完整包均已从磁盘重载，Actor、Critic、WM 与同名评分包逐张量一致，均含 6 个优化器、4 个 replay 块和 2 个待执行额度。[恢复回读](../results/b0/standard_dynamics_20261124/recovery_verified.json)

从 u10 的常规恢复按已有约定对活动 lane 作管理边界截断并重建 200 ms 真实前缀。[机器清单](../results/b0/standard_dynamics_20261124/baseline_manifest.json) · [恢复与总训练账](../results/b0/standard_dynamics_20261124/h32/pilot_summary.json) · [下一入口](../prompts/NEXT_RUN.txt)
