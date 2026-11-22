# B0-05 连续单门

2026-11-22，北京时间。规定完整初态到终点停车的首次单侧及统一模型名义结果已实测。每例由同一 Actor 读取本体历史和指定参考，每 20 ms 输出全部 23 个目标，物理事件逐 2 ms 独立判定。各配方、后端、参考与完整条件分别计数。

## 共同模型首次完成两侧名义

[同一个 seed0 包](../results/b0/full_s0_joint_prior_r1/actual_config.json) 的 u0 含动态门 WM 和两侧全程监督 Actor。固定[加长持姿参考协议](../config/b0/full_hold_margin_v2.json)后，原生名义前拉 59.9794°、背推 25.0396°，分别运行 37,583 与 27,576 子步，均通过全部 13 阶段。每次退臂后保持和终点停车各自连续 1,500 子步。该包针对全程做了 3,000 次两侧联合动作监督，初始化后全程 H32 更新为零。后续 u50 用同一初值再做 50 次 H32、500 个 WM 与 1,000 个 Critic minibatch，81,715 条有效在线转移。[前拉逐步事件和视频](../results/b0/full_joint_margin_u0_native_r1/pull/full/nominal/) · [背推逐步事件和视频](../results/b0/full_joint_margin_u0_native_r1/push/full/nominal/) · [在线训练计数](../results/b0/full_s0_joint_prior_r1/outcome.json)

在原 0.5 s 教师持姿参考下，原生 u0 的两侧都在已开到目标角后失抓。持姿判据分别只连续达到 211/250 和 126/250 个子步。加长参考时仅把新采教师的持姿延长到 1.5 s，策略仍须实测连续 250 步。Warp 上同一 u0 包使用原参考及加长参考都在预抓取提前碰门。[原生 v1](../results/b0/full_joint_u0_native_r1/cases.csv) · [Warp v2](../results/b0/full_joint_margin_u0_warp_r1/cases.csv)

## 平移开发条件的观测

在原生单侧监督前拉的 C02–C05 中，X/Y 分别平移 ±50 mm。实测相对于 nominal，初始 77 维传感输入和 Actor 参考差均为零，WM 参考最大差为 0.03536。前 51 次实际动作逐元素相同，四种偏移在头 1 s 的变化均小于 8e−16 m，四案全程均失败。这定位了接触前全局平移在现有 Actor 输入中的不可观测性；其他偏航、门初角、摩擦工况有各自的物理失败记录。未用 H 条件作此诊断。[五案输入与原始动作对照](../results/b0/full_pull_supervised_native_r1/start_observability.json)

## 11 月 22 日首次完整前拉成功及同权重跨后端对照

正式输入为完整规定初态，历史只在第零帧用初态填满，随后每 20 ms 由网络给出 23 个目标。每个 2 ms 物理步由独立裁判计分。原生 3.3.0 新采前拉恒目标教师的训练/验证分别产生 3,712/3,708 个完整转移，另保留各自不满 20 ms 的尾部。原生名义重放 37,121 步通过。在 Warp 3.16 上重放同一串原生目标，第 8,170 步预抓取超时。该结果确定了开环目标的后端差异，尚不能解释学习策略的全部误差。[新采教师](../results/b0/full_held_r2/pull_60_train.json) · [Warp 重放](../results/b0/full_pull_teacher_warp_r1/result.json)

| 前拉名义 | 原生 3.3.0 | Warp 3.16 |
| --- | --- | --- |
| 冻结片段监督初始化直接进入全程 | 驶近超时，16,001 步，0° | 驶近超时，16,001 步，0° |
| 继承片段监督 Actor，使用整条前拉单独监督 3,000 更新 | 13 阶段通过，36,630 步，60.0076° | 预抓取第 4,473 步站位越界，0° |

原生成功轨迹包含两个分开的 1,500 步保持，抓持确认 100 步，无中途重置。该策略仅做了整程动作监督，WM/H32 联训与固定条件另列。C01 即名义配置，回归分母仍按注册的 20 例计算。[原生连续成功及视频](../results/b0/full_pull_supervised_native_r1/pull/full/nominal/) · [Warp 连续失败及视频](../results/b0/full_pull_supervised_warp_r1/pull/full/nominal/) · [监督配置](../results/b0/full_s0_pull_supervised_r1/actual_config.json)
