# SuperMimic-M1Piper-standard-v1 联合 WM 与接触实验

2026-11-24，北京时间。接续审查提交 `528a9d7`。本轮仍为 **B0-04，最终候选 null，完整双侧物理回报 NA**。99 个实际联合十批块中，只有 +850 同时通过四项长窗保留和独立在线改善检查，前后两块均越线。没有满足连续两块的放行条件。新 seed0 主链 H32 / 联合 WM / Critic 更新为 0 / 0 / 0。共同 u0 新跑的原 2 ms Warp 十项为 0/10。

[机器 manifest](../results/b0/standard_joint_contact_20261124/baseline_manifest.json) · [开跑登记](../results/b0/standard_joint_contact_20261124/registration.json) · [全部节点](../results/b0/standard_joint_contact_20261124/adapt/all_nodes.csv) · [逐案正式判定](../results/b0/standard_joint_contact_20261124/h32/seed0_u0_formal.csv)

## 联合更新在哪里开始漂移

使用实际共同 u0、原采集 replay 和随机状态，物化两支的原八个 H7 和两个 H1 批，每批 256 行。保存三条复演链各 11 个权重和优化器状态。两支原顺序第 10 批的全部 WM 与优化器张量逐值等于原 u1 的 WM 后、Actor 前快照，首末四项长窗也与原记录相等。重标支第一个 H7 批后，grip 前拉／背推 TCP P95 从 17.85／14.69 mm 升到 50.87／68.47 mm。原顺序 +10 时，前拉 grip 固定探针的 H7 末步 J2 有符号位置和速度均值变为 −0.219 rad、−2.333 rad/s，TCP 位移的关节与基座分量均值为 80.47 和 11.68 mm。唯一的同样本 2H1→8H7 对照在 +10 的四项长窗仍为 628–759 mm。保留原联合顺序。

在 8,681,503 个相同参数坐标上，以真实十批的全部样本和原损失权重分别计算源梯度。重标起点 online 对 native、grip、multimode、response 的加权梯度余弦为 −0.098、−0.124、−0.217、−0.138。第一次实际参数变化沿 online 下降方向的归一化投影为 +0.2195，四个离线源均为负；后续点存在变号。源比例、输入状态和优化器动量还不足以分离出单一原因。原两支 u10 各自 pending=2 完整保留。[逐批复演、梯度和恢复索引](../results/b0/standard_joint_contact_20261124/replay/summary.json)

## 命令与真实伺服力

读取 240 条已有首动作，共 10,800 个原 solve。六臂和主动指均以求解前状态、实际 ctrl、模型 gain/bias、ctrlrange 和 forcerange 核算。第一外部周期使用归档缓存，后续 2 ms 周期的缓存用已保持的 ctrl 与归档目标反推；后者的证据身份是反推值。七路裁后力与实际输出最大绝对差为 4.53×10⁻⁵（各通道自身力或力矩单位）。

在细步开发 hold，原 u0 与既有实验 u10 的 J2 分别在全部 80/80 个物理步饱和。距首拍非饱和区的距离，以真实采集标准差计，前拉从 684.31σ 降至 637.62σ，背推从 156.62σ 降至 79.51σ。相同两节点主动指首拍距离前拉为 39.71／60.23σ，背推为 55.00／92.72σ；主动指在 20 ms 内可以退出饱和。该观察适用于这两个起点和指定命令。[240 条原数组复算](../results/b0/standard_joint_contact_20261124/physics/archived_servo_rows.csv)

四个已登记 hold 起点、每点七个一次性动作、两种物理步长、两遍，共 112 条 20 ms 分支、5,040 个新增物理微步，使用原先真实积分的前缀。第一 solve 跨边界的实际力已核对。只有细步训练起点第一遍的 14 条完整首 terminal 提供新 H1。它们属于原 response 池，优化时实抽 175 次；新增 H7 为 0。对重复噪声以上且接触模式可解释的 66 个细步输出分量，重标起点、+850、+990 的局部导数分别有 38、47、47 个与真实差分同号。后两节点各包含训练起点 26/36、开发起点 21/30。这些分量共享四个起点，且较宽区间上的割线与局部斜率可能不同。[边界逐案](../results/b0/standard_joint_contact_20261124/physics/boundary_cases.csv) · [起点导数](../results/b0/standard_joint_contact_20261124/physics/boundary_derivatives.csv) · [末点导数](../results/b0/standard_joint_contact_20261124/adapt/node_000990/boundary_derivatives.csv)

## 单链预适配与放行结果

初始化为重标 +1000 的 WM、共同 u0 的标准 Actor、全部归一化缓冲和 Critic。Actor 可追溯至 B0-03 seed0 的 1,000 次更新和 1,088,000 次采集。训练使用 0.25 ms 物理、2 ms 外部 servo、20 ms policy、N80、c=0.50625。原 H1/H7 损失、官方 Muon 与 Adam、1.0 裁剪及固定 WM 统计均沿用。H1 为 192 online＋64 Warp；H7 为 192 online＋32 native＋32 Warp。两种时域的 Warp 份额沿用原三源轮换。解析边界仅写入 response 辨识数据。

共同训练块有 2,086 个 H1 和 1,315 个 H7。新的连续训练块使用种子 112401，新增 3,429 个 H1 和 3,096 个 H7，含 156 个合法首 terminal。独立开发块使用种子 112402，在六条 validation 轨迹按同阶段对应位置取得物理初态，保留原训练参考时钟和 200 ms 实积分前缀；有 1,816 个 H1 和 1,149 个 H7，含 176 个合法首 terminal。两个新增块各推进 5,120 个策略区间、409,600 个细步，并逐项验证 Actor 参数和统计与共同 u0 相等。开发块只用于逐合法起点评分。相邻训练十批块交替使用共同块和新增块。[采集回执](../results/b0/standard_joint_contact_20261124/collection/train.json) · [独立开发回执](../results/b0/standard_joint_contact_20261124/collection/development.json) · [分层合法窗](../results/b0/standard_joint_contact_20261124/collection/eligible_windows.csv)

第 +10 至 +100 的四项固定长窗中位数为 164.54／186.51／168.73／185.72 mm，第 +410 至 +490 降至 45.62／40.00／51.94／39.73 mm，独立 H7 J2 位置 RMSE 的中位数从 0.0767 降至 0.0258 rad。后九个块间仍有 69–92 mm 的极差。以此作为延长证据，+490 后一次性将两个 WM 优化器的学习率由 2×10⁻⁴ 降至 5×10⁻⁵，沿同一参数、优化器、采样顺序和 RNG 继续。[延长依据](../results/b0/standard_joint_contact_20261124/adapt/extension.json) · [唯一调整](../results/b0/standard_joint_contact_20261124/adapt/adjustment.json)

| 固定双指 H32 TCP P95，mm | 窗数 | 原 E0 | 开发上限 | +840 | +850 | +860 | +990 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| grip 前拉 | 386 | 17.85 | 22.32 | 17.41 | 20.72 | 20.35 | 31.94 |
| grip 背推 | 446 | 14.69 | 18.36 | 30.19 | 14.49 | 26.32 | 52.16 |
| multimode 前拉 | 199 | 17.57 | 21.97 | 37.60 | 21.89 | 37.96 | 49.48 |
| multimode 背推 | 199 | 18.65 | 23.31 | 36.46 | 18.51 | 30.00 | 58.55 |

每个十批块末，独立开发 H1/H7 的原损失和 J2 位置、速度 RMSE 均较 E0 改善。到 +990，H1/H7 原损失分别从 2.939／2.415 降至 0.749／0.231，H7 的 J2 位置 RMSE 从 0.4992 降至 0.0149 rad，速度 RMSE 从 3.3229 降至 0.1989 rad/s。+850 是唯一同时满足四条长窗线的末点；+860 有三项重新越线，98 对相邻检查均未取得双通过。数值均有限，990 个留存更新裁剪前 P95 为 6.694，峰值 24.550，605 批触发裁剪。独立进程重载 +840/+850/+860/+980/+990 的权重，五个节点所有长窗与在线指标的复评绝对差均为 0。前拉 multimode 的同一批 199 个双指窗上，+850→+860 时 H32 的 TCP 关节分量均值从 17.28 升至 19.67 mm，基座分量从 4.97 升至 5.58 mm。该分解固定真实关节计算基座项，两分量的范数不作标量相加。[独立重载](../results/b0/standard_joint_contact_20261124/adapt/independent_reload.json) · [固定窗误差分解](../results/b0/standard_joint_contact_20261124/adapt/relapse_components.csv)

预算共 30 个诊断 WM 批、991 个预适配批。后者包括完整链 990 批与一次发生在首个优化步骤之后的记录器故障，修复后从已保存零点接续，丢失的 1 批单独计费。更早的一次编译中断发生在反向传播期间，尚未执行优化步骤。剩余 9 批不足另一个十批块。预适配所有实抽合计（留存部分）为 online H1 38,016、H7 152,064；online H1 含 3,173 个 open/hold 起点，online H7 中 open/hold 为 0，两时域的 two_finger 实抽均为 0。H32 起点实抽为 0。[实抽明细](../results/b0/standard_joint_contact_20261124/adapt/draw_accounting.json) · [中断记账](../results/b0/standard_joint_contact_20261124/adapt/execution_accounting.json)

## 真实后继闭环与原评分

共同 u0 纯 Actor 在六个开发起点（前拉／背推各 grasp、hold、release）重建前缀、每 20 ms 从本 lane 的真实后继重新查询。两种物理身份各独立跑两遍。每个身份各有 8/12 例活过首 20 ms 并实际发出第二动作，四个 hold 组合均在第一微步超力。两种身份都为 0/12 在原裁判停止前出现双指，0 事件。2 ms／细步分别查询 Actor 86／140 次，实际计分微步 796／10,790。六个起点来自两条开发轨迹，重复分母按组合计。[24 个开发闭环](../results/b0/standard_joint_contact_20261124/physics/pure_actor_shared_u0_cases.csv) · [前拉视频](../results/b0/standard_joint_contact_20261124/physics/pull_shared_u0_actor.mp4) · [背推视频](../results/b0/standard_joint_contact_20261124/physics/push_shared_u0_actor.mp4)

共同 u0 用本轮独立路径重跑原 2 ms Warp 十项，0/10 通过、0 事件。双侧 stable_grip、open_5、open_15 共六项均在首个 2 ms 超出 6 N。stable_grip 首力为前拉 51.069 N、背推 33.150 N。其余四项中，前拉 approach_grasp、release_retreat、背推 approach_grasp 发生操作工位漂移，背推 release_retreat 在 40 ms 出现指面与非抓握把手接触。本轮原判定共计 1,628 个评分微步、1,000 个前缀微步。逐案保留原 result.json / return.json 及段分母。[逐案表](../results/b0/standard_joint_contact_20261124/h32/seed0_u0_formal.csv) · [原判定目录](../results/b0/standard_joint_contact_20261124/formal)

## 目标差距与恢复

第一个未满足的训练条件是同一链上两个连续真实块末点均能保留四项固定长窗。第一个正式物理条件仍是同包十项 10/10。D、完整 Warp nominal／C、原 native 3.3 完整双侧、独立 seed1/2 和冻结 H 均未在本轮运行。完整任务回报继续 NA，尚无与 0.90 参照或 0.88 接近带的数值差。旧 870796a 的 50 个正式个案、旧 u10 预算与本轮另列。

AutoDL 现场为 `/root/autodl-tmp/dog-and-arm-b0-temporal-v1`。大资产在 `results/raw_large/b0/joint_contact_20261124/`，末点为 `adapt/wm_000990.pt`，包含 WM、两个优化器与 CPU/CUDA/NumPy RNG。连续训练 lane / replay / ReturnSampler / Ratio 在 `collection/train/state.pt`，完整 solver 在同目录 `solver.npz`；共同 Actor/Critic 位于旧轮 `dynamics_20261124/h32_shared/first.pt`。复核命令为 `bash scripts/b0/env.sh python -u -m scripts.b0.joint_verify`。+850 与 +990 均保留诊断身份。后续接续以实际恢复和原资格条件为准。[运行记录](../DAILY_WORK_LOG.md) · [恢复索引](../results/b0/standard_joint_contact_20261124/baseline_manifest.json)
