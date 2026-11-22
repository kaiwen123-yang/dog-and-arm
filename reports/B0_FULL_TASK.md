# B0-05 连续单门

2026-11-22，北京时间。规定完整初态到终点停车的首次单侧及统一模型名义结果已实测。每例由同一 Actor 读取本体历史和指定参考，每 20 ms 输出全部 23 个目标，物理事件逐 2 ms 独立判定。各配方、后端、参考与完整条件分别计数。

## 共同模型首次完成两侧名义

[同一个 seed0 包](../results/b0/full_s0_joint_prior_r1/actual_config.json) 的 u0 含动态门 WM 和两侧全程监督 Actor。固定[加长持姿参考协议](../config/b0/full_hold_margin_v2.json)后，原生名义前拉 59.9794°、背推 25.0396°，分别运行 37,583 与 27,576 子步，均通过全部 13 阶段。每次退臂后保持和终点停车各自连续 1,500 子步。该包针对全程做了 3,000 次两侧联合动作监督，初始化后全程 H32 更新为零。后续 u50 用同一初值再做 50 次 H32、500 个 WM 与 1,000 个 Critic minibatch，81,715 条有效在线转移。[前拉逐步事件和视频](../results/b0/full_joint_margin_u0_native_r1/pull/full/nominal/) · [背推逐步事件和视频](../results/b0/full_joint_margin_u0_native_r1/push/full/nominal/) · [在线训练计数](../results/b0/full_s0_joint_prior_r1/outcome.json)

在原 0.5 s 教师持姿参考下，原生 u0 的两侧都在已开到目标角后失抓。持姿判据分别只连续达到 211/250 和 126/250 个子步。加长参考时仅把新采教师的持姿延长到 1.5 s，策略仍须实测连续 250 步。Warp 上同一 u0 包使用原参考及加长参考都在预抓取提前碰门。[原生 v1](../results/b0/full_joint_u0_native_r1/cases.csv) · [Warp v2](../results/b0/full_joint_margin_u0_warp_r1/cases.csv)

## Warp 上的同一双侧权重与跨端对照

用 3.16 Warp 的 20 ms 真实恒目标训练双侧参考残差 Actor，同包包含预训练门 WM。在原参考上前拉走到终点，门角 60.0729°、最后停车 1,483/1,500 步，背推在 25.0504° 保持阶段失抓。先以同一包只延长教师末端停车一秒，前拉 60.0767° 全程通过、背推仍失抓。再采用真实采集的抓持 1.5 s、终点停车 4 s，两侧名义均通过。独立物理裁判始终要求抓持 0.5 s、退臂后和最终停车各 3 s。[参考登记](../config/b0/full_warp_hold_and_park_margin.json) · [只延长停车](../results/b0/full_warp_tail_u0_warp_r1/cases.csv) · [实采数组索引](../data/b0/full_held_reference_index.csv)

| 同一方向对使用的包和参考 | 原生 3.3.0 名义前拉 / 背推 | Warp 3.16 名义前拉 / 背推 |
| --- | --- | --- |
| 原生参考监督包 u0，持姿延长 | 59.9794° / 25.0396°，均完成 13 阶段 | 两侧预抓取提前碰门，均失败 |
| Warp 参考监督包 u0，抓持与终点停车延长 | 前拉 60.1663° 后退臂超时，背推 6.2714° 时抓持几何失败 | 59.9506° / 25.0258°，均完成 13 阶段 |

Warp 本后端成功分别用 37,374 和 27,513 个物理子步，两个任务的两段停车都各自连续满足 1,500 步；两例接触与约束缓冲溢出标志为零。后端提示 capsule–mesh 类型至多产生一个接触点；这条提示没有单独确定后端差异的原因。两个成功包具有不同的 SHA，不跨包合计成功。5 个完整学习检查点已在第二平台重新载入，主机路径、预训练源、实际更新、normalizer 和最新队列恢复文件位置见[权重清单](../results/b0/full_baseline_seed0/checkpoint_inventory.json)。[Warp 前拉及视频](../results/b0/full_warp_hold_park_u0_warp_r1/pull/full/nominal/) · [Warp 背推及视频](../results/b0/full_warp_hold_park_u0_warp_r1/push/full/nominal/) · [同包原生逐案](../results/b0/full_warp_hold_park_u0_native_r1/cases.csv)

全程 H32 u50 单独计分。原生参考包在本后端到达 59.9837° / 25.0449°，两侧都在倒车阶段耗尽参考。Warp 参考包 u50 的两侧则在本后端预抓取触碰门体。独立单侧前拉 u50 在原生完成 59.9992° 名义，C01–C20 为 9/20（单侧监督为 8/20）。[原生共同包 u50](../results/b0/full_joint_margin_u50_native_r1/cases.csv) · [Warp 共同包 u50](../results/b0/full_warp_hold_park_u50_warp_r1/cases.csv) · [单侧 H32 逐案](../results/b0/full_pull_prior50_native_r1/cases.csv)

## 平移开发条件的观测

在原生单侧监督前拉的 C02–C05 中，X/Y 分别平移 ±50 mm。实测相对于 nominal，初始 77 维传感输入和 Actor 参考差均为零，WM 参考最大差为 0.03536。前 51 次实际动作逐元素相同，四种偏移在头 1 s 的变化均小于 8e−16 m，四案全程均失败。这定位了接触前全局平移在现有 Actor 输入中的不可观测性；其他偏航、门初角、摩擦工况有各自的物理失败记录。未用 H 条件作此诊断。[五案输入与原始动作对照](../results/b0/full_pull_supervised_native_r1/start_observability.json)

## 11 月 22 日首次完整前拉成功及同权重跨后端对照

正式输入为完整规定初态，历史只在第零帧用初态填满，随后每 20 ms 由网络给出 23 个目标。每个 2 ms 物理步由独立裁判计分。原生 3.3.0 新采前拉恒目标教师的训练/验证分别产生 3,712/3,708 个完整转移，另保留各自不满 20 ms 的尾部。原生名义重放 37,121 步通过。在 Warp 3.16 上重放同一串原生目标，第 8,170 步预抓取超时。该结果确定了开环目标的后端差异，尚不能解释学习策略的全部误差。[新采教师](../results/b0/full_held_r2/pull_60_train.json) · [Warp 重放](../results/b0/full_pull_teacher_warp_r1/result.json)

| 前拉名义 | 原生 3.3.0 | Warp 3.16 |
| --- | --- | --- |
| 冻结片段监督初始化直接进入全程 | 驶近超时，16,001 步，0° | 驶近超时，16,001 步，0° |
| 继承片段监督 Actor，使用整条前拉单独监督 3,000 更新 | 13 阶段通过，36,630 步，60.0076° | 预抓取第 4,473 步站位越界，0° |

原生成功轨迹包含两个分开的 1,500 步保持，抓持确认 100 步，无中途重置。该策略仅做了整程动作监督，WM/H32 联训与固定条件另列。C01 即名义配置，回归分母仍按注册的 20 例计算。[原生连续成功及视频](../results/b0/full_pull_supervised_native_r1/pull/full/nominal/) · [Warp 连续失败及视频](../results/b0/full_pull_supervised_warp_r1/pull/full/nominal/) · [监督配置](../results/b0/full_s0_pull_supervised_r1/actual_config.json)
