# B0-04 接触片段

## 实施起点

2026-11-22 从 main@865835c 建立独立工作树。原生 MuJoCo 3.3.0 与研究环境 MuJoCo 3.16 均可导入；两侧旧教师原始数组可读。P6 原始目标的子步更新频率不同于策略，新采集将保存 10 个子步保持同一物理目标后的真实后继。冻结 seed0 的 review.json 在仓库，本机已从 AutoDL 取回完整 .pt，已用 torch.load 核对计数和 normalizer/模型状态；旧 boundary 检查点另属失败试验。各侧接触学习、nominal、20 条开发集目前均未验收。环境与命令记录见根目录 DAILY_WORK_LOG.md。

## 04-A 接触数据、参考与只读评估

原生 3.3.0 新采主集 20 个完整 episode。按独立运行分 train 10 / validation 10，分别有 13,640 / 13,541 条完整 20 ms 转移。20 个部分末段另存终态、步数与 mask。两侧练习各有接近闭爪、抓持保持、5°、15°、释放退臂。固定时钟的未来参考保留实际长度，策略输入把超出区间的槽位置零，WM 窗口保留真实终止后继。主集及实际段边界见 [数据索引](../data/b0/contact_segments_held_r1.json)。原始主集在两棵接触工作树的 `results/raw_large/b0/contact_held_r1`，另采的完整失抓终止转移见 [索引](../data/b0/contact_terminal_r1.json)。

- 5° 名义教师前拉终角 4.848°、背推 5.087°。初版 0° 目标使教师在双指刚抓住时反向纠偏，同一步前拉合力从 1.139 增至 14.414 N、背推从 1.353 增至 6.201 N。新变体保持闭爪末姿，原 6 N 及 0°±2° 门槛下两侧 train/validation 共 4/4 通过；两侧名义终角 0.115°、0.443°。5°、15° 实际保持各 1,500 个 2 ms 步，另有 4 个真实张爪失抓负例。两个方向的达标收益来自教师采集。各案有实际命令、动作尺度与结局。[逐案](../results/b0/contact_held_r1)
- 只读评估器读取冻结期望位姿/时钟与求解区间实际状态，按侧归类双指，以整数计数触发抓持、失抓和两段停车；历史数据缺命令位姿时用原生 FK 推得的冻结端姿并标注。真实历史完整教师在 native 回放时 qpos 逐步最大差为零，两侧各 13/13 阶段通过、每侧 12 项事件步号相同，抓持均早 1 个子步。旧背推 C20 在 1.640–1.642 s 对左柱施加 13.078 N，评估器正确识别。开发初态按真实 100 子步前缀重建，10 组各 20 个有效扰动及独立 nominal。[校准](../results/b0/contact_event_calibration_r1) · [开发清单](../config/b0/contact_dev_v1.json)
- 新采 5° 数据在 native 3.3.0、CPU 3.16、Warp 3.16 上各复现同一 32 条恒目标动作，两侧各 320 个计分子步。三后端首次双指步号分别均为前拉 42、背推 40。Warp 混合 128 世界实测 330 个物理步的缓存峰值为 2304/16384 个接触、单世界 57/256 个约束，容量溢出为零。短窗独立于策略任务成功率。[跨后端数据](../results/b0/contact_backend_r1)

## 04-B 动态门模型

完整物理状态 63 维；O1 输入表示 75 维，含独立门角/速、相对根/手的门轴、两侧杆和朝向；5 维逐回合 context。预测 31 个速度增量，2 ms × 10 的积分系数为 0.55。夹指保留两真实自由度。迁移 B0-03 内层与 30 个机器人输出行，输入层、门输出、归一化重新初始化。Actor 沿用 77×10 本体历史和给定运动参考。几何重算与真实 MuJoCo 位姿对照在两侧旧参考中的最大位置差约 1.3 微米。

分开的 8 个训练与 8 个验证 episode 用于 WM 预训练，实际可用 10,808 / 10,726 转移。200 个 WM minibatch 时验证 TCP 的 1/7/32 步 RMSE 0.862/4.098/35.901 mm；续至 2000 时为 1.138/3.246/29.383 mm。门角 0.0011/0.0146/0.2005°，双指模式 H32 的 TCP RMSE 23.220 mm，高于抓持 5 mm 容差。每个窗口首次模式、三种预测器、样本数、高分位与发散情况见表。原生两侧各扰动 J5 和夹口，四个局部 7 步比较里两个门角导数方向相反。该现象只能定位这四个接触邻域。[模型配置](../results/b0/contact_s0_wm_held_r2/config.json) · [预测误差](../results/b0/contact_s0_wm_held_r2/validation.csv) · [局部扰动](../results/b0/contact_s0_wm_held_r2/gradient_native.json)

## 04-C 迁移初值的真实失败

冻结 B0-03 Actor 在十项接触 nominal 上 native 3.3 为 **0/10**，Warp 3.16 为 **0/10**。两侧各三个抓持/开门起点第一步即越过 6 N 门槛，native 前拉 51.091 N、背推 33.140 N。同一物理初态仅将教师六臂目标替换为 Actor 输出也触发首步超力（67.024/49.748 N），纯教师为 1.173/1.120 N。已证实入口臂命令可单独造成超力。15° 教师的部分臂通道离 home 达 62–72 个原网络标准幅度。正在按原 tracking 配方训练，以及单列有物理依据的 Actor 初始化诊断。各后端成绩与完整失败影像分开保存。[native 逐项](../results/b0/contact_u0_native33_r1/cases.csv) · [Warp 逐项](../results/b0/contact_u0_warp316_r1/cases.csv) · [动作分块](../results/b0/contact_u0_native33_r1/entry_action_blocks.json)

### 200 次 H32 更新与接触动作的初始化

原配方在 128 worlds 中完成 200 次 Actor 更新，127,122 条有效在线转移。200 次均在 WM 冻结时改变 Actor 权重，实际使用的七步窗有 75% 来自在线物理。更新 50、200 的 Warp 真实名义成绩均为 0/10。200 时，新 WM 在相同八个验证 episode 上的 1/7/32 步 TCP RMSE 为 1.554/21.242/62.205 mm，稳定双指 H32 为 30.026 mm。[训练记录](../results/b0/contact_s0_tracking_r2/outcome.json) · [名义结果](../results/b0/contact_s0_tracking_u200_warp_r2/cases.csv) · [同集模型误差](../results/b0/contact_s0_tracking_r2/independent_wm_u200.csv)

为检验初始臂姿偏差的作用，单列 arm/jaw 网络输出单位 32 倍的 Actor 教师监督初始化。六个独立 episode 的动作误差在固定训练参考下由六轴 0.89948 降至 0.00756 rad、夹口 32.65 降至 0.934 mm。这个 Actor 初次在 Warp 完成 3 s 前拉稳定抓持，在原生完成前拉接近闭爪与 3 s 抓持。逐案评测与该初始化后的 O1 更新分开登记。[监督初始化](../results/b0/contact_s0_bc_effort32_r1/actual_config.json) · [独立验证](../results/b0/contact_s0_bc_effort32_r1/final_validation.json)

### 固定目标对照、真实窗口和策略训练差异

- 只读裁判在 v1 的真教师恒目标上取得 native 10/10、Warp 9/10。背侧 0° 在 Warp 成功连续 1,489 步，截止时距规定的 1,500 步差 11 步。追加同一已有目标实积分 22 ms 达标。独立采集 v2 增留 1 s 的真实持姿，原截止前的 10,276 个状态、10,275 个下发控制及双指载荷逐元素一致。v2 教师在 native 第 1,525 步、Warp 第 1,536 步通过。同一监督 Actor 在 Warp 的 v1/v2 都于 1.78 s 首次越出 ±2°，末角 4.577°/6.825°，均未积得一个完全就绪的保持步。四个 5°/15° 片段的真教师恰在原截止步达标，记录该时限特性，保留原协议与全部失败。[v1 原生](../results/b0/contact_reference_native33_r1/cases.csv) · [v1 Warp](../results/b0/contact_reference_warp316_r1/cases.csv) · [v2 实采](../results/b0/contact_held_margin_v2/measured_comparison.json) · [v1/v2 同权重对照](../results/b0/contact_held_margin_v2/frozen_bc_comparison.json)
- 监督 Actor（3,000 次）在 native 3.3 前侧接近闭爪与稳定抓持均达到 nominal + 20/20，其他八个 nominal 失败。训练时随机换部分历史的单独变体在 native 仅前侧接近闭爪通过，开发 20/20。各项名义独立于 D01–D20。[普通监督逐案](../results/b0/contact_s0_bc_u3000_native33_r1/cases.csv) · [换历史逐案](../results/b0/contact_s0_bc_historyswap_u3000_native33_r1/cases.csv)
- 从普通监督 Actor 继续原 tracking 200 次 H32 更新，收集 270,118 条有效在线转移。相同冻结清单上，native 和 Warp 均 0/10。native 前侧释放第 472 步撞面板，背侧释放在 3,911 步耗尽参考。Warp 对应失败为第 473 步撞板和第 2,064 步背侧站位偏差。两侧各三个在抓持中起步的名义案例均在第一个 2 ms 越过 6 N。前侧稳定抓持 Warp 为 15.449 N，背侧 14.094 N。[native](../results/b0/contact_s0_bc_joint_u200_native33_r2/cases.csv) · [Warp](../results/b0/contact_s0_bc_joint_u200_warp_r2/cases.csv)
- 对相同 100 个物理子步重建的两侧抓持初态，按比例混合监督 Actor 与联合更新 50 的首动作。纯监督→纯联合命令的真实 20 ms 窗内合力峰值分别为前侧 2.007→7.018 N，背侧 1.410→13.199 N；两侧均在第一个 2 ms 超限，原 tracking 的真实步奖励仅由约 0.099999 降到 0.099965、0.099874（上界 0.1）。这个局部动作干预量化了软回报对已知硬失败的敏感性，解释范围限于这两个起点。[十个实测区间及 WM 对照](../results/b0/contact_s0_bc_joint_r1/entry_reward_u50.json)
