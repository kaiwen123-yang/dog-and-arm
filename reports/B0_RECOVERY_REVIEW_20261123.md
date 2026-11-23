# B0 恢复轮独立审查：标准迁移、混合策略成果与能力边界

审查日期：2026-11-23。实验时间沿用原记录的北京时间；本报告审核的最后实验提交为 `23c90684522a030e2625bf0e44118fa86884ebf4`。

**结论：本轮同一混合策略在三个原始后端完成双侧名义任务，并在一次真实 H32 更新后保留能力；但这不等于官方 SuperMimic 的标准接触迁移已经通过。** 真正沿原 Actor/原 tracking 的接触分支，1,000 次 H32 后两端仍各 0/10；成功的 540/546 全程包有参考前馈、累计 15,000 次分阶段 BC，546 另有解析补偿。混合候选完整开发主要仍为每侧 9/20，多次更新会破坏任务。

用户在本次审查中再次明确：**当前是根据 SuperMimic 进行迁移的标准阶段，先完成 B0，再开展多模态/VLA 融合。** 下一轮应从标准迁移链核查并修复必要的平台接口、参考/真实数据与学习调用，原方法和额外适配分别计分；不因混合策略成功或遇到目标冲突而默认切换新裁判、新奖励或新控制方法。

下一步以 [标准迁移执行计划](../docs/B0_STANDARD_TRANSFER_PLAN_20261123.md) 为准；完整目标差距见 [GOAL_GAP_20261123.md](../docs/GOAL_GAP_20261123.md)。本报告所引用的结构化复核结果集中在 [audit_summary.json](../results/b0/recovery_review_20261123/audit_summary.json)。本次审查与文档交付没有新增训练、仿真或硬件动作。具名历史对话检索只返回相关摘要，不声称已读取完整原文；阶段约束以本次可见用户指令和已登记项目顺序为准。

## 1. 来源、审查范围与证据口径

### 1.1 八个提交构成的完整恢复轮

比较基线为 `b9a11293a6930b1c95e335c090641bbdae649c62`，结束点为 `23c90684522a030e2625bf0e44118fa86884ebf4`。范围内共八个提交，按实现顺序如下。

| 提交 | 本轮内容 |
| --- | --- |
| `bccb5f2` | 原/特权平移输入与匹配 BC 配方 |
| `f160969` | 轮地/夹指接触差异定位，扰动教师的固定时钟评分 |
| `1223501` | 配对监督、教师失败、一次 H32 能力保持 |
| `3c9106a` | 标准 Actor 中的根位移—六臂补偿，统一物理/想象入口 |
| `eb79802` | 同包双引擎验证，背推扰动教师与冻结任务对齐 |
| `f081200` | 真 H32 三端保持、价值目标配对及站位恢复 |
| `d00936b` | 已启动物理评测交接给脱离终端的 tmux 工作流 |
| `23c9068` | 回收最终评测结果、补全本轮实际分母 |

代码审查覆盖新增 `scripts/b0/h32*.py`、`learning/b0/contact_policy.py`、`contact_training.py`、新增 `stance_arm.py`、`stance_base.py`、`approach_legs.py`、`endpoint_policy.py`，以及完整评测入口的改动。教师、后端、状态与目标审查同时核对相应生成器、裁判和原始小结果。官方机制按固定 SuperMimic 源提交 `abc124c1bd5976341034668af3d12c087f2f1f55` 核对，mjlab_research 固定提交仍为 `dd51a9fcc98791a2f0b018b3c7f71a3eefd5ecdd`。

主要原始说明为 [本轮结果](B0_RECOVERY_RESULTS_20261123.md)、[H32 实测](B0_H32_RECOVERY_20261123.md)、[三后端诊断](B0_RECOVERY_BACKENDS_20261123.md)、[教师与固定任务](B0_RECOVERY_TEACHER_20261123.md)。其中 20:40 交接段的“仍在运行”属于当时快照，现以最后提交中的逐案 `result.json` 和 21:12 回收记录为准，不再当作未完成工作。

### 1.2 387 条记录不等于 387 次独立随机试验

结构化复核读取了本轮在 `results/b0`、`data/b0`、`config/b0` 下变更的 926 个文件，共 101,749,329 字节。这里是明确目录和提交范围的读取口径，不延伸为“所有历史会话、远端大数组和未提交权重均已在本机验证”。

原 [case_index.csv](../results/b0/recovery_round_20261123/case_index.csv) 有 384 条记录，来自 50 个 run：98 条 nominal、286 条 C。复核实际新增/变更的完整任务 `result.json` 共 387 条、51 个 run：100 条 nominal、287 条 C。差异来自索引漏收 `recovery_endpoint_hinge_tail_warp_r2` 的以下三条，均已有真实终局：

| 漏收记录 | 物理步数 | 最终门角 | 裁判结果 |
| --- | ---: | ---: | --- |
| [pull nominal](../results/b0/recovery_endpoint_hinge_tail_warp_r2/pull/full/nominal/result.json) | 37,374 | 59.95095° | 通过 |
| [push nominal](../results/b0/recovery_endpoint_hinge_tail_warp_r2/push/full/nominal/result.json) | 27,512 | 25.02635° | 通过 |
| [push C08](../results/b0/recovery_endpoint_hinge_tail_warp_r2/push/full/C08/result.json) | 27,512 | 24.95855° | 通过 |

另有六条 nominal 由 `--extend-from` 继承，分别是三对来源：

- `recovery_b_stance_u1_full_c_r1` ← `recovery_b_stance_u1_nominal_r1`；
- `recovery_b_stance_u1_native_full_c_r1` ← `recovery_b_stance_u1_native_r1`；
- `recovery_c_integrated_native33_full_c_r1` ← `recovery_c_integrated_native33_r1`。

这六条与其来源记录字节一致、原始数据目录相同，不能重复计算为新物理实验。384 与 387 条记录分别对应 378 与 381 个不同 `raw_directory` 字符串；这仍不是统计独立试验数，因为各分支共享 seed、参考、初始化和开发条件。不得把所有变体的通过率汇总成某一候选的任务成功率。

全部 387 条完整任务记录均从连续任务初态开始，教师前缀为零。165 条成功记录具备完整 13 阶段，并满足抓持确认 100 子步、目标保持 250 子步、退臂后/最终停车各 1,500 子步的相应事件记录。这验证的是记录与判据的一致性，不代替每个候选独立的 C 分母。

### 1.3 视频与大文件边界

本轮新增的 102 个 MP4 均完整解码，合计 135,066 帧，解码错误为零。团队另对其中 30 个视频各查看首、中、尾三帧，共 90 帧，涵盖名义、失败、后端与教师分支。**完整解码不等于逐帧目视；本次没有声称人工看完全部 135,066 帧。** 成败主要依据 2 ms 裁判和逐案结构化记录，视频用于核对运动、接触与失败阶段是否明显矛盾。

大权重、优化器、replay、RNG 与原始物理数组仍以既有两平台保存位置及 [恢复材料清单](../results/b0/recovery_c_s0_stance_integrated_r1/recovery_inventory.json)、[H32 包清单](../results/b0/recovery_b_inventory_r1/packages.json) 为依据。本次没有重新执行远端训练或把清单可读性等同于本机重新加载全部权重。

## 2. 本轮最终能力：名义跨端已建立，完整开发门槛未过

### 2.1 同包完整 C 的最终结果

下表均为同一个候选包在指定后端自身反馈上的完整任务计分。nominal 与 C 分开，C01 也不因数值接近 nominal 而从开发分母中删除。

| 候选与后端 | 双侧 nominal | 前拉 C01–C20 | 背推 C01–C20 | 证据 |
| --- | --- | ---: | ---: | --- |
| 546 维监督/解析补偿 u0，native 3.3 | 均通过 | 9/20 | 9/20 | [逐案](../results/b0/recovery_c_integrated_native33_full_c_r1/cases.csv) |
| 同源 546 维真实 H32-u1，native 3.3 | 均通过 | 9/20 | 10/20 | [逐案](../results/b0/recovery_b_stance_u1_native_full_c_r1/cases.csv) |
| 546 维监督/解析补偿 u0，Warp 3.16 | 均通过 | 9/20 | 9/20 | [逐案](../results/b0/recovery_c_integrated_warp316_r1/cases.csv) |
| 同源 546 维真实 H32-u1，Warp 3.16 | 均通过 | 9/20 | 9/20 | [逐案](../results/b0/recovery_b_stance_u1_full_c_r1/cases.csv) |
| 原 540 维无动作先验 H32-u1，Warp 3.16 | 均通过 | 9/20 | 9/20 | [逐案](../results/b0/recovery_b_tracking_u1_full_c_r1/cases.csv) |

除 native 546-u1 的背推额外通过 C08 外，上述通过项均为 C01 与 C10–C17。也就是说，初始 XY、yaw、门初角及组合扰动仍构成主要缺口。native 背推的 9→10 是本轮确实测到的开发差异，应保留；但它来自一个 seed、一个已参与开发的条件，Warp 同条件没有复制这项改善，尚不足以证明普遍稳定的 H32 增益。

距完整任务每侧 **≥18/20** 的门槛，主训练后端 Warp 的共同 H32-u1 每侧还少 9 个通过条件；native 按相同数值参照前拉还少 9 个，背推还少 8 个，正式跨端入口仍沿用原 native 双侧 nominal 要求。这个差值是具体开发清单的缺项数，不是整个项目“只剩某个百分比”，也不新增 CPU3.16 或 native 完整 C 的正式出口门槛。

### 2.2 选定子集与局部通过不能扩展成完整 C

| 独立分支 | 已评分范围 | 实测结果 | 可以说明什么 |
| --- | --- | --- | --- |
| 解析 planar 反馈 | 每侧 C02–C05 | 前拉 0/4、背推 1/4 | 某些站位纠偏开始有效，完整任务仍弱 |
| planar＋六臂补偿 | 每侧 C02–C07 | 前拉 2/6、背推 3/6 | 指定六案子集的进展，不是 2/20、3/20 或完整 C 通过 |
| endpoint terminal 反馈 | 背推 C08 | 1/1 | 这一专项 BC/反馈分支解决一个已知开发例，未证明更宽初角覆盖 |

证据：[planar](../results/b0/recovery_planar_screen_warp_r1/cases.csv)、[planar＋arm](../results/b0/recovery_planar_arm_screen_warp_r1/cases.csv)、[endpoint C08](../results/b0/recovery_endpoint_hinge_tail_warp_r2/push/full/C08/result.json)。这些分支也不能与 546 H32 包拼接成一个“最佳策略”。

## 3. 标准主线、参考残差与解析补偿的准确身份

### 3.1 三类方法不能互相代填验收

| 类别 | 实际 Actor 与初始化 | 目前最好证据 |
| --- | --- | --- |
| 标准迁移链 | [EffortScaledActor](../learning/b0/model.py)：官方 MultiEncoderAE＋固定 home/伺服单位转换/限幅；B0-03 u1000 与动态门 WM2000，无额外接触动作 BC/参考旁路/解析补偿 | 无接触已通过；[接触原 tracking u1000](../results/b0/contact_s0_tracking_r3/outcome.json) 为 572,118 有效转移、1,000 H32/10,000 WM/20,000 Critic，原 v1 十项 nominal 两端各 0/10 |
| 540 维参考残差链 | ReferenceResidualActor，六臂/夹爪参考姿态前馈＋BC 残差；后续使用原 tracking/H32 | 旧监督接触包通过；最新 full u1 Warp nominal 2/2、C各9/20，native nominal 0/2 |
| 546 维解析补偿链 | StanceArmActor，在上一底座上直接加入 Jacobian 根平移臂补偿 | u0/u1 三端双侧 nominal，完整 C 仍未达标 |

标准链恢复点为 `results/b0/free_s0_cloud_servo_r2/checkpoint_001000.pt` 与 `results/b0/contact_s0_wm_held_r2/wm_002000.pt`；接触失败终点 `contact_s0_tracking_r3/checkpoint_001000.pt` 继续保留。r3 已继承 r2，计数不能再相加。[接触完整报告](B0_CONTACT_SEGMENTS.md)保留原 v1 负结果和后来片段 hold-margin 版本，不能跨协议作无条件因果比较。

540/546 全程包的实际 BC 血统是五段各 3,000 次：[`contact_s0_bc_reference_residual_r1`](../results/b0/contact_s0_bc_reference_residual_r1/actual_config.json) → [`full_s0_pull_supervised_r1`](../results/b0/full_s0_pull_supervised_r1/actual_config.json) → [`full_s0_push_supervised_r1`](../results/b0/full_s0_push_supervised_r1/actual_config.json) → [`full_s0_joint_supervised_r1`](../results/b0/full_s0_joint_supervised_r1/actual_config.json) → [`full_s0_joint_warp_supervised_r1`](../results/b0/full_s0_joint_warp_supervised_r1/actual_config.json)。逐项 `initial_actor` 与末条实际更新计数相符，累计 **15,000 次分阶段动作 BC**。这是不同数据/目的的继承链，不是同一批数据的一次训练；旧接触监督包单独仍是 BC3000。

名称含 `tracking` 只描述更新回报，不能证明 Actor 没有参考前馈或 BC。关闭训练动作先验也不会移除这些结构。官方多编码器内部的 latent 对齐 `bc_loss` 不是这里的教师动作 BC。当前标准接触/全程尚未跑通，不能据混合分支通过而进入多模态阶段。

### 3.2 546 维包做了什么

“546 维”指 `goal_motion` 的参考/任务分量宽度，Actor 仍使用十帧、每帧 77 维的本体历史。其构成是原 540 列加 6 个六臂几何修正，不能理解成全部观测只有 546 维，也不能与追加十槽根平移的 570 维变体混淆。

在 [contact_policy.py](../learning/b0/contact_policy.py) 中，`ReferenceResidualActor.raw()` 已将给定参考的六臂/夹爪目标作为动作基线，网络学习其残差。`DoorMotions.goals()` 对 `reference_translation_arm_map` 另外计算：

1. 当前参考根位置减去当前真实/预测根位置；
2. 乘以固定公共参考姿态预计算的六臂 Jacobian 逆映射；
3. 将六个关节修正限幅至 ±0.05 rad；
4. `StanceArmActor.raw()` 以固定增益 1.0 直接加到六臂输出。

[stance_arm.py](../learning/b0/stance_arm.py) 使用位置/姿态 Jacobian、0.12 m 姿态长度尺度、0.01 阻尼及近收臂姿态的平滑门控。补偿直接响应根平移，尚不是完整的根旋转/门目标闭环。共享增益由 886 个对齐教师标签拟合，未约束解 1.339 按事前区间 [0,1] 取 1.0。

标准化打包把原网络/normalizer 复制，新增六列 encoder 权重置零，归一化均值零、标准差 0.05 rad。此时解析动作通路已经起效；装包没有新增 BC/H32 更新。后续 H32 可以更新神经列，但不会消除直接反馈路径。详见 [标准包](../results/b0/recovery_c_s0_stance_integrated_r1/package.json)、[打包实现](../scripts/b0/recovery_backend_package.py)。

因此，方法身份应明确写为：**固定参考臂/夹爪前馈＋BC 全身残差＋解析根平移补偿＋真实 H32 更新**。解析补偿属于新增任务适配/控制结构，不是官方原网络自行学习出的全部能力，也不是视觉状态估计。

没有发现该标准入口在执行时使用未来真实状态、按后端 ID 换控制器、在线教师动作表或 IK 接管。固定参考和 Jacobian 表属于已声明先验，当前根量在真实环境来自实测状态，在想象中来自 WM 预测。物理/想象入口一致是有效修复；**u0 已三端名义通过，所以 u1 三端通过首先证明能力保持。** 576/577 维组合包的字段迁移通过，不代表已经取得其完整物理成绩。

## 4. 真 H32 已被证明，持续稳定学习尚未被证明

### 4.1 固定官方调用链与真实更新

[h32_recovery.py](../scripts/b0/h32_recovery.py) 加载完整 Actor、WM、Critic 和 normalizer；在 `ContactRun` 的默认部分迁移之后，额外严格载入完整 frozen Critic。每轮真实采集 64 个 world、40 个 20 ms 区间，WM 更新之后进入官方 H32 Actor-Critic。原机制组不加动作先验，matched-detached 组只对 Actor 切断末端 bootstrap 梯度，Critic 仍训练。

核对的官方源为 [WorldModelEnv](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/envs/world_model_env.py) 与 [ActorCriticPolicyLearner](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/learners/policy_learner.py)：冻结 WM 参数但保留动作/状态梯度，展开 32 步，累计即时回报与末端 Critic 项，先更新 Actor，再做 20 个 Critic minibatch。匹配分支恢复同批起点、噪声、Actor/Critic/优化器和 RNG，已具备归因价值，不需要下一轮重复搭建。

546-u1 的 [梯度分解](../results/b0/recovery_b_stance_u1_r1/first_gradient.json) 与 [更新日志](../results/b0/recovery_b_stance_u1_r1/updates.jsonl) 给出以下直接证据：

| 项目 | 实测 |
| --- | ---: |
| 真实有效转移 | 1,558 |
| 想象长度 | 32 |
| tracking / bootstrap 对首动作梯度 L2 | 0.04407 / 0.27199 |
| tracking / bootstrap 对 Actor 梯度 L2 | 0.13381 / 0.58677 |
| 两类 Actor 梯度余弦 | 0.01788 |
| Actor 输出层最大权重变化 | 0.000006251 |
| WM / Critic 输出层最大变化 | 0.001889 / 0.001684 |
| 本轮 BC loss | 0 |

这足以排除“只是把 checkpoint 的更新编号改成 u1”。`Policy/reward` 含 bootstrap 并按 H×dt 归一化，不应读成实际任务成功率或纯即时回报。

### 4.2 多次更新的退化不止一种

| 分支 | 早期结果 | 继续后的结果 | 证据 |
| --- | --- | --- | --- |
| 原 540 维 tracking | u1 双侧名义通过 | u5、u10 前拉预抓超时，背推通过 | [u5](../results/b0/recovery_b_matched_u5_nominal_r1/cases.csv)、[u10](../results/b0/recovery_b_matched_u10_nominal_r1/cases.csv) |
| 仅更换全程 WM 初始化 | 独立 WM 某些指标改善 | u5 双侧预抓超时 | [逐案](../results/b0/recovery_b_wminit_u5_nominal_r1/cases.csv) |
| 真实终止 TD | u5 双侧名义通过 | u10 双侧预抓超时，7,883/7,882 步 | [u10](../results/b0/recovery_b_td_terminal_u10_nominal_r1/cases.csv) |
| phase/grip 真实目标 TD | u5 双侧名义通过 | u10 前拉在退臂阶段 31,310 步超时，背推通过 | [u10](../results/b0/recovery_b_phase_td_u10_nominal_r1/cases.csv) |
| 546 维解析补偿＋tracking | u1 三端双侧名义通过 | u5 前拉退底盘阶段耗尽参考，背推通过 | [u5](../results/b0/recovery_b_stance_u5_nominal_r1/cases.csv) |

546-u5 前拉已完成抓持、退臂、独立保持和收臂，门角 59.9544°，但退底盘终点站位偏差约 11.59 mm，超过 10 mm 到位门槛，37,868 步参考耗尽。phase_td-u10 前拉则开至 59.5428° 后退臂超时。把它们统一写成“又在预抓失败”会抹去本轮的重要阶段差异。

同批完整/分离 bootstrap 的 u1 都保留双侧名义；额外真实 TD 的“终止截断”与“继续 bootstrap”两组 u5 也都保留双侧名义。因此，目前不能把早期能力保持或后续失败唯一归因于某一个 bootstrap 项。正确结论是：**已有真实更新链和多个有效诊断，仍未形成可持续保留完整任务能力的学习配方。** 在已出现明确失败时没有继续凑 u50，是合理收口，不是漏做必须完成的预算。

## 5. 完整任务目标、训练 done 与 Critic target 仍未统一

### 5.1 三种语义目前不同

| 环节 | 当前实际使用的内容 | 尚缺内容 |
| --- | --- | --- |
| 完整真实评分 `ContactEvents` | 实际事件推进、就绪连续窗口、超时、固定端点、接触/力、停车、成功 | 作为冻结任务判据已经存在 |
| 真实训练 `ContactPlant` | 按固定参考 phase 检查 2 ms 接触、受力、支撑、限位等，保存首失败后继 | 不能等同完整阶段状态机、预抓就绪/超时、reference exhaustion、最终成功 |
| 官方想象 soft done | 相对参考的根高度、重力方向/倾斜 | 没有覆盖大部分接触失败与完整任务事件 |

证据：[contact_training.py](../learning/b0/contact_training.py)、[contact_warp.py](../learning/b0/contact_warp.py)、[完整评测](../scripts/b0/eval_contact_segments.py)。把 replay 写入 `terminated`，并不自动意味着完整任务 done 已进入想象优化。

在 546-u1 的首批 64 个想象起点中，存在真实 terminal interval，32 步 final survival 却全部为 1。独立 validation 的 79 个真实训练终止，直接用**实测后继根**计算原 soft done，阈值 0.5 时检出 0/79。这排除了“只是 WM 根状态预测不准”的解释，但仍不能评价未标入该数据集的完整任务超时。

### 5.2 phase_td 只改了真实 Critic 一侧

[h32_real_critic.py](../scripts/b0/h32_real_critic.py) 在 open/hold 的真实 replay 中，把 tracking reward 乘以四项质量：合法双指占用、TCP—把手几何、接触合力、门角进展。随后 8 个真实 TD minibatch 使用这些实测 reward 和真实 hard done。

但是 Actor 的 H32 rollout 仍用标准 tracking 和根高度/倾斜 soft done；Actor 更新后，Critic 又用这套想象轨迹做 20 个 GAE minibatch。**真实 TD 和想象 GAE 的任务语义没有闭合。** 这不是未来真值泄漏，因为真实质量只作 replay target；问题在于它没有同步成为想象中的同一目标。

这是一项可由代码明确指出的变体不一致，不能直接断言其单独造成所有失败。8 与 20 的 minibatch 数量也不能代替真实的目标冲突或梯度贡献测量。标准主线先恢复原 tracking/官方 target 并核对平台语义；phase-TD 属于额外变体，不默认继续扩展。若未来另做任务奖励适配，应同时定义真实/想象目标，而不能只加一侧惩罚并期待自动对齐。

### 5.3 failure head 被拒绝接入是正确决定

新增事件头以当前状态、动作、context 和固定参考 phase 预测下一 20 ms 硬失败，按完整 cohort 分 train/calibration/validation。独立验证 5,124 条区间含 79 个失败，其中 78 个超力、1 个失抓。阈值 0.98 的 TP/FP/FN/TN 为 17/94/62/4,951，precision 15.3%、recall 21.5%、FPR 1.86%，未满足 precision/recall≥50%、FPR≤1% 的预登记门槛，未接入想象。

证据：[实现](../scripts/b0/h32_failure_head.py)、[混淆矩阵](../results/b0/recovery_b_event_r1/confusion.csv)、[失败分布](../results/b0/recovery_b_event_r1/failure_reasons.csv)。这些样本主要来自原 u0 加噪声 RSI 采集，不能视为最新 546/u5 完整轨迹的失败分布。更不能靠改善现有分类器，自动学到标签中没有的 pregrasp timeout 或最终停车失败。应先补任务语义和候选分布，再决定预测头形式与接入条件。

## 6. WM 数据覆盖向前走了一步，真实学习方向仍不稳定

### 6.1 40 步收集和独立 H32 拟合已经完成

旧的 16 步 cohort 无法直接提供连续在线 H32 窗口，本轮已改为 40 步真实收集。独立 [h32_fit_recovery_wm.py](../scripts/b0/h32_fit_recovery_wm.py) 用一半固定全程教师、一半新在线训练窗口拟合 100×64，按每十批 H1/H7/H32=2/6/2；episode/cohort 分离，窗口不跨 reset 或 terminal，失败区间保留一步真实后继。

| H32 TCP RMSE，完全相同验证窗口 | 原 WM | 新 WM | 解释边界 |
| --- | ---: | ---: | --- |
| 旧教师前拉双指 | 27.30 mm | 27.70 mm | 未改善 |
| 旧教师背推双指 | 25.24 mm | 19.28 mm | 该分组改善 |
| 独立策略前拉双指，146 窗 | 42.37 mm | 27.76 mm | 该分布改善 |
| 独立策略背推双指，1 窗 | 35.57 mm | 32.13 mm | 样本不足以判断稳定性 |
| 旧教师背推释放 | 25.20 mm | 35.41 mm | 退化 |

见 [分模式验证](../results/b0/recovery_b_full_wm_r1)。轨迹预测误差与某一瞬时 5 mm 抓持容差是不同统计量，不能直接用一个除另一个推导成功概率。

本轮还采了 832 条扰动 lane 尝试；独立验证中 97 条出现双指中断，36 条在硬失败前且干预结束后恢复连续 20 ms 双指。首次触碰另采 18 个分支、990 个真实转移，避免把再接触误称首次接触。它们解决了旧计划的数据空缺，未证明完整任务恢复能力。[恢复数据](../results/b0/recovery_b_grip_challenge_r1/cohorts.json) · [首次接触](../results/b0/recovery_b_first_touch_r1/branches.json)

**仍需区分独立预拟合与常规 joint。** `ContactRun.update()` 普通路径的在线 WM 窗口仍为 H1/H7；旧 long-horizon 选项增加的是 teacher H32。收集 40 步并不等于每轮 joint 已在使用当前策略在线 H32。把新的在线长窗配方合入主训练，必须作为明确、可比较的变化。

### 6.2 “H32 6/12 同号”的正确含义

[h32_branch_direction.py](../scripts/b0/h32_branch_direction.py) 从实测起点出发，向 WM 喂该真实闭环分支**记录下来的动作序列**，开环展开 1/7/32 步后比较端点差异。它没有在每个预测状态重新生成未来 Actor 动作，因此不是对完整 BPTT 闭环梯度的有限差分验真。

严格共享起点下，用 u1 WM 比较 12 个无额外扰动的 u0→u1 分支，H32 的 TCP—把手标量距离方向 6 个同号、6 个反号。12 个分支来自双侧六阶段，不是 12 个完整任务，也不是独立训练样本。release 阶段距离增加可能正确，同号也不意味着更安全或更接近成功；力方向尚无合格 WM 预测量。代码对很小物理效应另设数值带，不能把这些方向统计改写成“梯度正确率 50%”。[逐条方向](../results/b0/recovery_b_directions_exact_r1/directions.csv) · [分母](../results/b0/recovery_b_directions_exact_r1/summary.csv)

## 7. 教师“同阶段正标签”与冻结任务确有冲突

### 7.1 A0–A4 不能只解释成“加输入没用”

原 Actor 对起始平移 C02–C05、部分组合，以及门初角 C08/C09 存在已测的输入不可区分问题。十槽根平移使 XY 变化进入输入；门角仍需额外对象信息。配对 BC A0–A4 各增加 128 次更新：A0/A1 保留名义，但各侧 C02–C05 都 0/4；加入扰动标签的 A2–A4 拟合误差下降，却均在双侧名义第 8,173/8,183 步提前碰门。[输入审计](B0_RECOVERY_TEACHER_20261123.md) · [BC 结果](B0_RECOVERY_RESULTS_20261123.md)

16 条扰动教师共 50,776 个真实完整 20 ms 转移，工程教师自己的任务完成 14/16，冻结完整裁判只通过 3/16：前拉 1/8、背推 2/8。所谓 39,229 条“正监督”实际满足的是有效区间、同 phase、在参考范围内、未干预且未硬失败等掩码；[recovery_teacher.py](../scripts/b0/recovery_teacher.py) 没有因此保证固定端点或阶段内进度一致。

例如带初角的训练例在教师自己的 pregrasp 目标附近达到 0.028 mm，却距冻结端点 52.322/55.873 mm，远超 3 mm 标准。同一阶段名称并不等于同一动作任务。故这批数据能够用于动力学和失败研究，却不能无条件当作当前冻结任务的成功动作标签。A2–A4 退化可能同时涉及标签矛盾、参考时钟、输入与训练预算，不能仅据此否定对象信息的必要性。

### 7.2 已有正例和局部冲突必须同时保留

| 新教师身份 | 真实结果 | 结论 |
| --- | --- | --- |
| 背推初角 +2.8068°，固定端点且不早于原 release 时刻松夹 | 冻结裁判 27,527 步通过，13 阶段，两次 1,500 步停车 | 一个真实兼容正例；不是所有非零初角都与 v1 冲突 |
| 前拉初角 +2.2557° | 冻结裁判 37,365 步通过，13 阶段，两次 1,500 步停车 | 又一个真实正例，未混入此前 A0–A4 拟合 |
| 前拉 +3.6832° | approach_arm 中夹爪基座碰把手，失败 | 当前固定门角/进入路径存在实际冲突 |
| 背推 +4.0998° | 未形成合格抓持，冻结裁判抓持超时 | 现有高角教师没有提供合法成功标签 |

详见 [教师证据](B0_RECOVERY_TEACHER_20261123.md)、[释放校时正例](../results/b0/recovery_endpoint_release_teacher_r2)、[小角前拉](../results/b0/recovery_endpoint_lower_pull_r1)、[高角背推](../results/b0/recovery_endpoint_upper_r1)。

正式 C09 前拉门初角 5°时，固定名义 approach_arm 端点的夹爪基座与把手相交约 24.71 mm，512 个容差边界采样均相交。[固定端点几何](../results/b0/recovery_round_20261123/fixed_endpoint_geometry_C.json) 只证明该固定门角下的局部端点姿态冲突。`ContactEvents` 在 pregrasp 禁碰，在 approach_arm 允许合法指面接触；尚未排除先合法移动被动门，再到达原端点的连续轨迹。**不能从静态样本断言 v1 整个任务全局无解，也不能以此直接放宽裁判。**

下一轮首先在标准迁移范围内核对参考可执行性、motion/reference 身份、教师路径与时钟；有效物理转移可用于 WM，不把错配动作标签注入 Actor。保持现行任务、绝对目标门角、接触/力/保持/停车约束与时限，不默认登记对象相对 v2。若标准协议确有无法合理表达目标任务的证据，单列限制和后续任务适配问题；不能边改裁判边宣布原标准通过。

## 8. 后端原因已经定位，不应下一轮重新做同一诊断

原 540 维 Warp u0 在 CPU3.16/Warp3.16 名义通过，native3.3 双侧失败。三端同初态、同目标的短窗把早期差异定位到首次轮胎着地：3.3 与 3.16 的轮地支撑点生成不同；稳定抓持还存在夹指 MULTICCD 接触差异。单独改变轮地支撑即可改变完整闭环成败；组合干预可在 CPU/Warp 重现 native 失败阶段与近似物理步号。[完整因果链](B0_RECOVERY_BACKENDS_20261123.md)

这些诊断干预仅用于定位，没有替换正式评分后端。标准 546-u0/u1 之后在原始 native3.3、CPU3.16、Warp3.16 分别用同一各自编号包闭环，双侧 nominal 均通过，构成真正的迁移进展。CPU3.16 没有据此自动取得完整 C 成绩，更没有实机结论。

下一轮保留这一固定跨端基线，只有共享改动影响迁移时做必要回归。无需再重做接触点定位、泛化参数扫描或用修改物理参数的诊断模型充当正式环境。

## 9. 旧计划哪些已完成，哪些只是部分完成

对照 [上一轮接续计划](../docs/B0_RECOVERY_PLAN_20261123.md)：

| 原计划项 | 本轮状态 | 下一轮处理 |
| --- | --- | --- |
| 起点信息审计，补平移/门初角区分 | 已完成明确诊断与 schema 迁移 | 引用现有证据，补必要对象/实际阶段信息 |
| 真实扰动教师、完整 episode 划分、配对 BC | 已执行，暴露标签/任务冲突 | 先修任务与标签，不直接扩大同配方监督 |
| 同批 H32 与 bootstrap 分解 | 已完成，真实梯度及匹配对照成立 | 不重复；用于新目标的最小对照 |
| u0/u1/u5/u10 能力检查 | 已完成多个配方，持续退化有证据 | 保留锚点，不为凑预算盲训 u50 |
| 真实 done 与价值对照 | 诊断/额外真实 TD 已完成，完整语义适配未闭合 | 标准主线恢复原目标，额外 TD/终止适配单列，不默认接入 |
| 在线长窗、分模式 WM、first touch/recontact | 已真实采集和独立验证 | 补候选实际分布，谨慎合入常规 joint |
| 三后端首次差异、单变量反事实、同包闭环 | 已完成名义链条 | 固定 546 基线，必要时回归 |
| 完整 C 每侧≥18/20 | 未完成 | 仍为 seed0 出口门槛 |
| 最终 H32 候选十项接触，每项 D01–D20≥18/20 | 未完成该最终候选回归 | 不能用旧 BC 十项通过代填 |
| seed1/2 与封存 H | 未启动，符合门槛顺序 | 配方通过开发后再启动 |

停止持续堆叠 `ApproachWheelActor`、`ApproachLegWheelActor`、`PlanarStanceFeedback`、`HingeFeedbackActor` 作为默认方向。它们分别是额外拟合或解析反馈，已提供局部研究信息，但继续混合会让能力来源更难解释。保留结果与实现，下一主线只增加与已证实缺口直接对应的必要适配。

## 10. 下一步结论与最终目标距离

下一轮按标准迁移顺序推进，具体工作与恢复入口见 [新执行计划](../docs/B0_STANDARD_TRANSFER_PLAN_20261123.md)。

1. **固定官方血统与必要平台接口。** 从已通过的 B0-03 Actor 和动态门 WM 接续标准链，使用 EffortScaledActor；保存接触 u1000 的负结果，修复有证据的单位/映射/参考/normalizer 问题，不重做整个 B0-03。
2. **保持原机制并补可用真实数据。** 参考、动作和真实后继身份一致；标准 WM 与 tracking/H32 调用按固定来源核对，分模式验证当前策略数据。既有 phase-TD/风险头/解析反馈只作为额外变体，不能自动成为标准默认项。
3. **标准 Actor 先接触再完整任务。** R/J 混合包作为能力对照，不能代 S 验收。标准候选按实际更新节点连续训练，接触 nominal/开发通过后进入双侧全程与 C；达到冻结门槛后才独立 seed/H。必要 BC 初始化单列，不能改称官方默认训练。

本轮离目标的距离已经可以分层描述：

- **数字环境与接触执行基础**已经成立，P6 工程教师、B0-03 无接触学习及既有 BC 接触基线继续有效。
- **同包名义跨端**取得实质进展，546-u0/u1 各自可在三个未经修改的后端完成双侧名义。
- **标准接触与全程迁移**尚未成立：原 Actor/原 tracking 接触 u1000 两端各 0/10；混合候选的 Warp 完整 C 每侧 9/20 不能换算成标准方法已完成 45%。多次 H32 会失去混合包的完整名义；最终候选的十项接触、每项 D01–D20≥18/20 仍缺。
- **统计与封存验证**尚未开展：seed1/2 和 H01–H50 保持封存。B0-06 的每 seed、每侧 C≥18/20 与 H≥40/50 不能由当前 seed0 名义结果替代。
- **最终研究路线**还包括腕部 RGB-D/语言/本体历史融合、VLA 与世界模型/可微动力学联合，以及标定和实机闭环验证；当前仿真特权几何与解析补偿不等于这些工作已经完成。更完整的分层差距见 [目标差距报告](../docs/GOAL_GAP_20261123.md)。

目前最有价值的下一步，是在用户确定的标准迁移阶段把来源、平台接口、参考与真实学习闭环核准并实际推进。已有混合成果保留为对照，已完成诊断直接继承；新增控制头、新裁判或新奖励的成功不能替代官方标准链尚缺的证据。
