# B0-04 真实积分、求解器修复与 C20/T2 配对结果

**后续审查入口：** [ff2d1e8审查](B0_TEMPORAL_ROUND_REVIEW_20261124.md)及[下一集中计划](../docs/B0_DYNAMICS_TRAINING_PLAN_20261124.md)。本报告原实测、选模结论与预算保持；新增计划中的物理步长/C20重标/H32试验尚未执行。

2026-11-24，北京时间。实验从 main `b5831d7` 接续，上一轮实验封存在 `753f1bc`。**本轮没有选出可启动新 H32 的世界模型。当前仍为 B0-04，候选为空，完整双侧归一化物理回报 NA。** 新增计算为一次原损失 WM 配对、独立物理重采和封存 Actor 的十项正式复测。[本轮 manifest](../results/b0/standard_temporal_20261124/baseline_manifest.json) · [预登记计划](../docs/B0_TEMPORAL_COMPATIBILITY_PLAN_20261124.md) · [物理指标定义](../docs/B0_PAPER_BASELINE_PROTOCOL.md)

## 真实微步与连续求解器

登记的 12 个训练起点来自 4 条源轨迹，6 个验证起点来自另 2 条源轨迹。每起点 28 个相关物理分支。原始记录的逐指 2 ms 位置增量与真实末速度相符，最大残差 3.58×10⁻⁹ m。旧路径将完整积分后的状态复制到登记分支并调用全批 forward，旁 lane 复位也会触发该调用。伺服读取的 qfrc_bias 因此改变。两侧 hold 的 u0 与 ref_arm 共四例，从完整 live Warp Data 快照实跑连续、登记、旁 lane 复位与相同命令重复。背推 Actor 修前最大开度差 0.005135 mm。登记时保留先前求解的 bias，局部复位时保留连续 lane 的 bias 后，首个 ctrl、bias、warmstart 与连续路径逐元素相同，四例首次训练失败子步相同。修后所有对照的最大开度差为 0.0000611 mm，最大门力差为 0.000104 N。[四组对照](../results/b0/standard_temporal_20261124/solver_route_comparison.csv)

已在修正路径重采全部 18 起点，50,400 个前缀世界子步、161,280 个分支世界子步，耗时 43.09 s。旧 grip 与 multimode 都使用完整批清零、连续前缀和连续策略区间，可继续使用。新训练响应排除同命令重复后有 3,698 个合法 H1、2,720 个 H7，独立验证有 1,535 和 1,066 个。失效后的整段诊断尾保存在现场。[资格与来源](../results/b0/standard_temporal_20261124/solver_source_qualification.json) · [修后逐分支残差](../results/b0/standard_temporal_20261124/solver_fixed_closure/temporal_residuals.csv)

修后 2/4/10/20 ms 分块开度误差 RMS 分别为 0.00000055、0.564、2.937、10.445 mm。两侧独立 hold/u0 首 20 ms，以真实起末速度代入官方粗积分，开度分别低估 30.695/46.629 mm；仅替换机械臂命令也分别低估 27.073/30.114 mm。54 个同命令重复对的开度差最大为 0.005314 mm。按实际时钟，部分粗区间包含首个正式失败后的诊断子步。对两档正负扰动作逐 tick 模式、饱和、失败和重复差异筛查后，验证集 J2→J2、J2→开度、夹口→开度分别仅有 2、2、8 组可解释。[两指和 J2 时序图](../results/b0/standard_temporal_20261124/solver_fixed_closure/temporal_velocity_displacement.png) · [逐组方向](../results/b0/standard_temporal_20261124/solver_fixed_closure/temporal_directions.csv)

## 同一真实抽样下的原损失训练

两臂从 response_wm_v1/wm_000000.pt 同一组张量与固定输入统计开始，各自使用新的官方 Muon/Adam。先将实际抽样的来源和状态索引写盘，两臂按相同顺序读取。每臂 200 H1＋800 H7，batch 256。每批 32 个 native、224 个 Warp，三个 Warp 源等份轮换。H7 在连续的第 1–7 个 20 ms 端点评分。T2 内部独立绑定 2 ms、c=1 的 GenCoord，各步 31 路预测乘一次 0.1，共用原网络和保持不变的命令与 context。独立验证与原始微步轨迹均未参与优化。[保存的索引](../results/b0/standard_temporal_20261124/paired_indices.npz) · [来源及索引解释](../results/b0/standard_temporal_20261124/paired_sources.json)

下表每格为前拉／背推。开度列为两条独立验证源中 hold/u0 首 20 ms 开度绝对误差。后两列为原握持与多模式独立集合中双指窗口的 H32 TCP P95。所有数值单位为毫米。每来源、侧别、模式、时域的可用窗口与实际评分数，以及其他手指、速度、TCP、臂、门指标均有逐项记录。[全部节点](../results/b0/standard_temporal_20261124/wm_validation/node_summary.json)

| 模型与新增批数 | 首命令开度误差 | 原握持 H32 TCP P95 | 多模式 H32 TCP P95 |
|---|---:|---:|---:|
| C20 +0 | 28.49 / 49.22 | 15.65 / 16.45 | 20.83 / 15.60 |
| C20 +50 | 28.59 / 42.12 | 241.60 / 211.41 | 247.03 / 210.64 |
| C20 +200 | 28.53 / 43.60 | 39.22 / 78.53 | 39.34 / 79.60 |
| C20 +1000 | 28.04 / 43.44 | 20.97 / 30.20 | 23.33 / 32.21 |
| T2 +0 | 28.79 / 49.47 | 23.61 / 22.46 | 25.33 / 26.52 |
| T2 +50 | 21.59 / 38.56 | 74.72 / 53.16 | 76.92 / 55.59 |
| T2 +200 | 23.42 / 37.39 | 51.97 / 64.82 | 50.91 / 65.58 |
| T2 +1000，事后诊断 | 16.89 / 30.72 | 434.56 / 488.61 | 454.30 / 496.73 |

T2 +1000 对两侧首命令预测的开度峰值速度为 1.02/1.34 m/s，物理轨迹为 3.70/3.58 m/s。逐微步指位置 RMSE 为 8.67/12.08 mm，指速度 RMSE 为 0.855/0.933 m/s。C20 +1000 的 14 个有数据的多模式 H32 TCP P95 分层全部较 C20 +0 恶化。八个节点均未满足原定选点条件。[T2 内部轨迹](../results/b0/standard_temporal_20261124/wm_validation/T2_1000/microsteps.csv) · [C20 长程分层](../results/b0/standard_temporal_20261124/wm_validation/C20_1000/long_validation.csv)

每臂 1,484,800 个粗后继监督实例，C20/T2 分别为 1,484,800/14,848,000 次内部网络前向样本，两臂合计 16,332,800，未含反向和独立验证。各段 shell 启动至成功退出的进程墙钟见[实测时间](../results/b0/standard_temporal_20261124/process_timing.json)。三段优化循环墙钟累计 31.14/113.79 s，共享 GPU；PyTorch 峰值分配 0.353/1.484 GiB。C20/T2 有 960/1,000、1,000/1,000 批触发原范数裁剪。历史 B0-03 的 1,000 次 Actor 更新、held_r2 的 2,000 批以及 lanes 的 1,000 批 WM 成本保留。旧 response 额外预热 1,000 批、已封存 H32 的 200 次更新另列。[预算和各节点现场恢复位置](../results/b0/standard_temporal_20261124/baseline_manifest.json)

**执行偏差。** +200 决策时检查了有限输出、验证误差和末批梯度，漏查整段 H7 的反向峰值。T2 在 +51..200 的裁剪前梯度范数 P95 已达 8.68×10⁶、最大 6.07×10⁸。按原计划应先暂停排查。随后执行的 800 批 T2（160 H1＋640 H7，11,878,400 个内部前向样本）已计入总预算，仅作为事后诊断。该段峰值达到 6.60×10¹⁷。训练入口已改为在每个落点输出两个时域的整段 P50/P95、最大梯度与裁剪次数；本轮六份区间回执由原始逐批日志重建。[+200 梯度回执](../results/b0/standard_temporal_20261124/T2_review_000200.json) · [逐批账本](../results/b0/standard_temporal_20261124/T2_training.jsonl)

## 无有效出口后的分源与物理复测

从已保存的配对索引取首个 H1 和首个 H7 批，按来源重算七个粗边界损失和梯度。T2 +0 到 +1000，所取响应 H7 原损失从 31.479 降至 4.499，而 native、旧握持和多模式分别由 0.00596/0.01288/0.02448 升至 0.1017/0.1324/0.1509。旧 u0→u1 用同窗另作复算，也观察到响应与在线源改善、另外三源退化。保存样本中的权衡可以解释选点失败的表现，其结论限于这些窗口。[配对分源复测](../results/b0/standard_temporal_20261124/wm_validation/paired_source_loss.json) · [历史 u1 原损失](../results/b0/standard_temporal_20261124/wm_validation/historical_u1_loss.json)

实际抽样中，两侧训练 hold/u0 原首命令分别进入 H1 45/54 次，均在训练时钟第 4 个 2 ms 子步失败，各自只有首个合法粗区间。更换为各自参考臂命令后，连续合法区间足够，其首窗口分别进入 H7 18/13 次。两侧验证共 6 个起点均排除在抽样之外。36 条实际命令、360 个子步中，原 PD、bias 与限幅重算的主动指和 J2 最大力残差为 3.19×10⁻⁶ N、5.62×10⁻⁵ N·m。两侧验证 hold/u0 的 J2 均有 10/10 子步接近力限，主动指分别为 4/10、7/10。原生和研究模型在已核传动、增益、力限和软等式字段一致。[实际抽样](../results/b0/standard_temporal_20261124/hold_actual_draws.csv) · [执行器实测](../results/b0/standard_temporal_20261124/hold_actuation_audit.json)

固定统计来自 8 条 native 训练轨迹的 10,808 个合法输入。重算全维均值和标准差的最大差分别为 2.38×10⁻⁷、4.89×10⁻⁶。修后训练/验证的合法非终止 J6 角速度达到 90.09/88.38 rad/s，旧在线首 cohort 达到 −112.25 rad/s。相应标准化输入绝对值约为 806/790/1004。原始物理记录与状态导出的列、单位及固定统计已对应复核。旧握持和多模式训练源的全维最大标准化值低于 10.7。[输入支持及分组](../results/b0/standard_temporal_20261124/wm_validation/input_support.json)

封存 Actor 的实际 u0→u1 先执行 8 H7 与 2 H1，再执行 H32 与 20 个 Critic 批。54 个可训练张量中有 36 个改变，完整参数位移 L2 为 0.32748。35 个 open/hold 在线初态均来自触发训练失败的转移，夹口动作导数 16 个为正。冻结验证 hold 首命令两侧开度变化 −0.521/+3.596 mm，其中单换观察归一统计贡献 −0.283/+0.835 mm；夹口梯度分项仍有 0.365% 相对残差。[旧 u1 实际参数](../results/b0/standard_temporal_20261124/historical_u1_actor.json) · [同状态命令](../results/b0/standard_temporal_20261124/historical_u1_frozen_commands.csv)

## +200 梯度与饱和腕速的独立复算

取 +1..200 中 T2 H7 梯度最大的第 85 个实际批，对冻结 +200 的同一组 256 窗重算。原训练精度下 C20/T2 梯度范数为 3.019/7.471，换作 FP32 highest 为 3.020/108.947。第 85 批训练时使用 +84 权重，其 6.07×10⁸ 峰值不可拿 +200 当成同权重复实验。取其中同一个旧握持窗，FP64 原 H7 参数梯度为 C20 1.662、T2 12,489.78。显式 70 微步和原 learner 七个边界、损失和参数梯度复算吻合。第 28 个微步的局部导数 4.422993 与三档中心差分相符。该窗的递推放大在 FP64 可复现；没有发现把 0.1 解码两次、缓存更新或四元数积分失真的证据。[+200 复算、选窗方法与边界伴随](../results/b0/standard_temporal_20261124/wm_validation/recurrence_u200.json)

从修后训练与独立验证中选取两侧 J4/J6 非终止速度极值，共 7 个不同的真实窗口，并补测两侧 hold 的 u0/完整参考命令 4 窗。前拉训练极值从同一起点重放七个先行登记命令后，第八个粗端点 J4/J6 速度为 Warp −69.61/+90.09 rad/s、CPU 3.16 −69.56/+90.04、原 native 3.3 −0.08/+0.10。该窗口已进入首动作后的参考命令序列。两引擎使用相同 2 ms、implicitfast、Newton 和原模型字段。在其中一个只有 J4/J6 饱和的首步，冻结实测的质量矩阵、平滑力和约束力，单独交换两个速度导数，3.3 的首步速度由 −49.684/+69.067 变为 +15.113/−25.608 rad/s，与 3.16 实测 +15.115/−25.610 对齐。3.3 在力限处保留伺服速度导数，3.16 和现用 Warp 将其置零；无接触单铰链复测也重现差异。[native 3.3 结果](../results/b0/standard_temporal_20261124/nonterminal_wrist_replay_3.3.0.json) · [3.16 结果](../results/b0/standard_temporal_20261124/nonterminal_wrist_replay_3.16.0.json) · [3.3 官方实现](https://github.com/google-deepmind/mujoco/blob/3.3.0/src/engine/engine_derivative.c#L812) · [3.16 官方实现](https://github.com/google-deepmind/mujoco/blob/3.16.0/src/engine/engine_derivative.c#L2313)

独立验证 hold/u0 首 2 ms 在三个引擎上的门力均约为 51.31/32.98 N。前拉 20 ms 开度（Warp / CPU 3.16 / 原 native 3.3）为 50.345/50.376/85.811 mm，背推为 71.562/71.972/104.033 mm。版本差异可改变失败后的轨迹，但三端均在该差异放大前超过力门槛。从原配对索引反查，每臂 32,000 个 native 窗对应 185,600 个实际监督后继实例。两腕轴 J4/J6 命中各自执行器力限的实例均为零，采样内没有证据支持这条饱和分支直接改变 native 监督目标。[实际 native 索引与原始载荷](../results/b0/standard_temporal_20261124/native_wrist_draws_3.16.0.json)

单次保存态重启所能恢复的 warmstart 和派生缓存、直接重放与从登记状态重放的区别已列入原始回执。原物理后端和正式裁判保持登记配置。

## 正式物理结果和恢复

新树使用原冻结 u0 Actor 重跑全部 10 个 Warp 正式片段名义案，2 套 manifest 各 5 案。结果 **0/10、6 案首 2 ms 超过 6 N，0 个阶段事件**。前拉/背推 stable_grip 首步门力为 51.07/33.15 N。前拉释放在第 502 个子步因工位漂移失败，上次同包为第 504 个子步；10 项失败原因均与封存 u0 一致。此次含 1,000 个前缀子步与 1,628 个正式控制物理子步，各案物理墙钟之和 18.10 s。原 60 案与本轮十案保留各自分母。两段视频使用修后的独立验证 hold/u0 真实轨迹，力与时钟和正式基准个案分别记录。[十案逐例](../results/b0/standard_temporal_20261124/anchor_nominal.csv) · [前拉视频](../results/b0/standard_temporal_20261124/hold_pull_validation_u0.mp4) · [背推视频](../results/b0/standard_temporal_20261124/hold_push_validation_u0.mp4)

AutoDL 现场为 `/root/autodl-tmp/dog-and-arm-b0-temporal-v1`。原始 2 ms 轨迹在 `results/raw_large/b0/temporal_entries_v1/`，各臂 0/50/200/1000 权重、优化器及 RNG 在 `results/raw_large/b0/temporal_pair_v1/{C20,T2}/`。恢复任一检查点做只读评分时使用其 temporal_id，并使用修后 registration/raw。旧 u200 保留在 response 工作树的 cohort_state.pt，原有 1 次 Ratio pending。当前无可训练的已选 WM，新增 H32/联合 Critic/独立 seed 均为零，D/C/H 和完整双侧 native 验收尚未达到启动条件。[接续入口](../prompts/NEXT_RUN.txt)
