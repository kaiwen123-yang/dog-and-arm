# B0-04–06 冻结交付：seed0 限制基线

2026-11-22（北京时间）。接触片段达到 B0-04 门槛。完整任务在原生 MuJoCo 3.3.0 和 MuJoCo-Warp 3.16 上各有一套能从规定初态分别完成前拉 60°、背推 25°的统一 WM/Actor 包。两套包在各自后端的前拉和背推开发回归均为 **9/20**，低于每侧 18/20。B0-06 按限制基线交付，独立 seed1/2 和 H01–H50 的任务成功率未测。[冻结记录](../results/b0/full_baseline_seed0/freeze.json) · [全程分表](../results/b0/full_baseline_seed0/full_scores.csv) · [逐案证据及视频索引](../results/b0/full_baseline_seed0/full_case_index.csv)

## 接触片段

同一 seed0 监督初始化在两侧各五个子任务均通过名义。原生、Warp 各自十项的 D01–D20 均为 20/20。这个包有 3,000 次教师动作监督、2,000 个 WM 教师 minibatch，接触 H32 更新为零。带物理动作先验的实际 H32 u50 在 Warp 的五项 v2 任务也各为 20/20，纯 tracking u1000 的两端十项名义均失败。[原生分项](../results/b0/contact_hold_margin_v2_summary/actor_native33.csv) · [Warp 分项](../results/b0/contact_hold_margin_v2_summary/actor_warp316.csv) · [训练、预测误差与物理失败](B0_CONTACT_SEGMENTS.md)

## 从规定完整初态的实测

两个 seed0 包各自在两侧共用同一组神经网络权重。原生来源包为 `full_s0_joint_prior_r1/checkpoint_000000.pt`，Warp 来源包为 `full_s0_joint_warp_prior_r1/checkpoint_000000.pt`。两者均含门 WM 和全程监督的 Actor；Actor 每 20 ms 读取本体历史和给定参考，直接输出 23 个目标，原生评测的网络推理在 CPU、Warp 评测的网络推理在 GPU。物理裁判每 2 ms 打分，记录首个失败子步。

| 权重与固定参考 | 物理后端 | 前拉名义 | 背推名义 | 前拉 C01–C20 | 背推 C01–C20 |
| --- | --- | --- | --- | ---: | ---: |
| 原生来源，教师抓持 1.5 s、终点停车 3 s | 原生 3.3.0 | 通过，59.9794° | 通过，25.0396° | 9/20 | 9/20 |
| 同一原生来源包及参考 | Warp 3.16 | 失败，预抓取提前碰门 | 失败，预抓取提前碰门 | 名义失败，未展开 | 名义失败，未展开 |
| Warp 来源，教师抓持 1.5 s、终点停车 4 s | Warp 3.16 | 通过，59.9506° | 通过，25.0258° | 9/20 | 9/20 |
| 同一 Warp 来源包及参考 | 原生 3.3.0 | 60.1663° 后退臂超时 | 6.2714° 时抓持几何失败 | 名义失败，未展开 | 名义失败，未展开 |

名义成功均通过顺序完整的 13 个阶段，从 0.30 m 外驶近，连续完成抓持、推拉、释放、退臂保持、收臂、倒车和终点停车。抓持保持判据仍为 0.5 s，退臂后与终点各有 1,500 个连续达标子步。四段成功视频都已逐帧解码。原生和 Warp 包属于同一独立训练种子；各后端的相同 C 编号也复用相同开发条件。[成功视频与时长](../results/b0/full_baseline_seed0/nominal_media.json) · [原生逐案](../results/b0/full_joint_margin_u0_native_r1/cases.csv) · [Warp 逐案](../results/b0/full_warp_hold_park_u0_warp_r1/cases.csv)

四组开发通过编号均为 **C01 和 C10–C17**。C01 为名义配置，C10–C17 改变轮地摩擦、夹指摩擦、铰链摩擦和阻尼。C02–C09、C18–C20 含初始平移、偏航、门角或组合扰动。前拉在各后端的 11 个失败由操作阶段外碰门 5、驶近超时 4、抓持超时 1、夹爪基座碰把手 1 构成。背推也各失败 11 例，涉及门板或把手的意外接触、抓持超时，原生另有 1 例停稳超时。各案例从统一初态独立执行，无教师接管和中途重置。

## 学习和后端对照说明了什么

- 在 C02–C05，沿世界 X/Y 的 ±50 mm 平移在初始 Actor 输入中不可区分。原生统一包在前 51 次输出的最大差为零，Warp 前拉/背推该差均仅约 1e−7。相对位置变化在 WM 目标输入中可见。偏航或门初角扰动另有失败，这个平移观测结论只解释相应条件。[原生前拉输入](../results/b0/full_joint_margin_u0_native_r1/pull_start_observability.json) · [Warp 背推输入](../results/b0/full_warp_hold_park_u0_warp_r1/push_start_observability.json)
- 源于原生的同一组恒目标用 CPU 3.16 / Warp 3.16 重放，分别在第 8,169 / 8,170 个子步预抓取超时；Warp 实采目标在 Warp 回放则完成第 36,869 步。真实参考加长时重新积分，两次 Warp 前拉采集在新增末端之前的根位置已有最高 1.995 mm 差异，不能把所有变化归于延长时间。[对照与计时](B0_FULL_TASK.md) · [固定目标及参考来源](../data/b0/full_held_reference_index.csv)
- 完整单侧前拉的原生监督策略 C 为 8/20，加入 50 次 H32 联训后为 9/20。共同模型在原生来源和 Warp 来源的配方中分别做了 50 次 H32、500 个 WM 和 1,000 个 Critic minibatch，有效在线转移 81,715 / 81,684。对应的 u50 共同包在本后端加长参考上的两侧名义均失败。原生包在倒车阶段耗尽参考，Warp 包在预抓取提前碰门。初始化包 u0 的双侧成功单独列示。[原生训练计数](../results/b0/full_s0_joint_prior_r1/outcome.json) · [Warp 训练计数](../results/b0/full_s0_joint_warp_prior_r1/outcome.json)
- 逐完整验证 episode 的模型预测另行评分。Warp u50 前拉 1/7/32 步 TCP RMSE 为 0.60/7.96/52.52 mm，背推为 0.84/9.01/49.59 mm，窗口长度分别为 20/140/640 ms。物理任务的 5 mm 抓持误差约束仍由真实逐子步裁判执行。[Warp 分模式预测](../results/b0/full_s0_joint_warp_prior_r1/warp_validation_000050.csv) · [原生分模式预测](../results/b0/full_s0_joint_prior_r1/native_margin_validation_000050.csv)

## 冻结边界与恢复

seed0 参与配方开发。完整策略在两个后端都未达到每侧开发 18/20，未形成可进入三条独立训练链的配方。seed1 和 seed2 未训练；原登记的每侧 H01–H50 仅有历史初态几何检查，未做策略任务测试。完整 C/H 门槛、多种子方差和实机性能没有通过结论。本轮保留原 P6 和 B0-03 冻结结果。

项目轻量证据和代码由 Git 管理。5 个完整检查点已在第二平台通过 torch.load 核对，SHA256 与 AutoDL 文件相符。两套成功包所需的实际训练命名参考均已直接保存到第二平台；全量相关原始 episode 和训练队列恢复状态按清单保存在 AutoDL 接触工作树。编号 checkpoint 用于推理或 warm start，继续同一训练需用对应的 cohort_state.pt 恢复 replay、优化器与 RNG。[权重和绝对路径](../results/b0/full_baseline_seed0/checkpoint_inventory.json) · [SSH 复核命令与后续实验边界](../prompts/NEXT_RUN.txt) · [北京时间逐日工作记录](../DAILY_WORK_LOG.md)
