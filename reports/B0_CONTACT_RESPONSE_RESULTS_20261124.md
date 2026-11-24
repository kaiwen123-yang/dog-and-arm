# B0-04 首动作响应、WM 数据贯通与 seed0 正式结果

> 2026-11-24 后续审查：本报告保持753f1bc实验原始结果。逐案/预算复算、q/v时间兼容与solver疑点、梯度解释边界见[独立审查](B0_RESPONSE_ROUND_REVIEW_20261124.md)。下一步按用户要求扩大为[集中迁移推进](../docs/B0_TEMPORAL_COMPATIBILITY_PLAN_20261124.md)，检查点不作为默认终点；本次审查没有新增实验。

2026-11-24，北京时间。实验从 main 的 `0c81d82` 接续，联训实现为 `ad29c8a`。本轮在 AutoDL 的独立树实际采集、训练并评分。**标准迁移仍在 B0-04。u0/1/10/50/100/200 各 0/10，合计 60 案、36 案首个 2 ms 超门力、0 个阶段事件。最终候选为空，完整前拉和背推回报 NA。** 本轮与上一轮 `27284e2` 的 60 案分别保存。[本轮 manifest](../results/b0/standard_response_20261124/baseline_manifest.json) · [逐案成绩](../results/b0/standard_response_20261124/nominal_segments.csv) · [正式打分分项](../results/b0/standard_response_20261124/nominal_score_details.jsonl)

## 首命令与其真实物理后继

12 个训练起点为每侧两个既有训练参考的接触前沿、握持或推拉、释放入口；6 个验证起点来自独立物理轨迹，目标时钟与对应训练参考按相位入口对齐。每个起点实际积分 100 个 2 ms 子步，保存求解器状态、十帧测量历史及同一份传感噪声、上一已执行命令、参考时钟和目标。冻结 Actor 使用各自的归一化，现场输出 23 路命令。首动作不另加探索噪声。原组合、仅换夹口、仅换六臂、臂夹皆换及局部方向共享该起点；其余 31 步使用共同参考命令。每个起点 28 个相关分支，504 个分支源自 18 个起点。[登记矩阵](../results/b0/standard_response_20261124/registration.json) · [逐起点与逐分支回执](../results/b0/standard_response_20261124/collection.json)

下表是训练握持入口上 B0-03/u0 的 **20 ms 末端两指实际总开度**。轮腿在前四个分支均执行同一 Actor 命令。只改夹口时，目标总开度为 10 mm。背推的实际张口还受六臂动作及接触组合影响。[首动作和预测表](../results/b0/standard_response_20261124/response_w0.csv)

| 侧 | 原组合 | 仅换夹口 | 仅换六臂 | 臂夹皆换 | 全参考 |
|---|---:|---:|---:|---:|---:|
| 前拉 | 50.8 mm | 29.3 mm | 49.7 mm | 21.5 mm | 21.4 mm |
| 背推 | 70.5 mm | 88.2 mm | 53.9 mm | 21.7 mm | 21.7 mm |

训练 hold 入口的首子步参考 phase 为 grasp；相应正式 stable_grip 片段从 hold 判定。训练起点 u0 前拉/背推在训练判定第 4/4 子步首次失败，独立事件计数均在第 1 子步失败。诊断轨迹上的事件计数从各正式 run_spec 所指片段的注册起始时钟及首阶段开始，终止后的 phase 用 −1 标记。逐案训练时钟和独立事件时钟均存于现场 NPZ。正式 60 项由原脚本另行运行。所有 H1 的真实 20 ms 末端量均与正式失败时刻分开报告。[事件时钟复读回执](../results/b0/standard_response_20261124/event_clock_receipt.json)

固定 +0 WM 在独立验证握持入口，u0 前拉/背推真实开度为 50.41/71.58 mm，预测 21.85/22.34 mm。把真实端点夹指速度代入原 GenCoord 公式，所得开度仅 19.71/24.94 mm，分别低于真实值 30.70/46.63 mm。旧 u200 Actor 的相同两例低估 29.95/37.56 mm。该积分残差与网络端点速度误差已逐案独立保存。验证局部扰动中，按原中心、重复中心和扰动分支的十个双指接触模式与首次训练失败 tick 匹配，再要求位移超过重复差异。对剩余有限分支，+0 WM 的夹口自响应与真实同向 43/48，J2 对总开度的交叉响应同向 4/21。分支共用起点，这些计数只描述本矩阵。22 mm 仍是原握持条件子集的命令范围。[J2 与夹口有限差分](../results/b0/standard_response_20261124/h1_local_directions.csv) · [旧 u200 WM 对照](../results/b0/standard_response_20261124/previous_u200.csv)

## 原损失预热和联合更新的实抽

固定 SuperMimic `abc124c1` 与 mjlab_research `dd51a9fc`，保留主要网络、GenCoord、原 tracking/softdone、固定基础 effort、gain32、Muon＋Adam、H32 Actor/Critic、ReturnSampler、Ratio、逐 lane 和 clip 末帧。预热继承 held_r2 的 2,000 次和上轮的 1,000 次，自上轮 WM 出口固定统计、新建优化器，又实际执行 1,000 个 batch。仅训练 split 进入训练。原 native 有 H1/H7 合法窗 13,640/13,580；旧 grip 有 14,396/11,644；多模式有 18,223/15,242；本轮响应 300 条非重复训练分支有 3,696/2,718。完整首失败区间保有 H1 资格，终止后的长尾只留作开环响应诊断。[预热配置](../results/b0/response_wm_v1/config.json) · [预热逐 batch](../results/b0/response_wm_v1/samples.jsonl)

| WM 节点 | 旧独立握持集 H32 TCP P95，前拉 / 背推（mm） | 多模式验证集双指 H32 TCP P95，前拉 / 背推（mm） |
|---|---:|---:|
| 本轮预热 +0 | 15.65 / 16.45 | 20.83 / 15.60 |
| +200 | 102.42 / 27.83 | 108.24 / 27.36 |
| +1000 | 39.51 / 25.37 | 37.84 / 26.74 |
| 联训 u1 | 285.77 / 351.33 | 303.28 / 345.25 |
| u10 | 443.34 / 343.79 | 463.21 / 351.55 |
| u50 | 52.05 / 46.18 | 48.78 / 48.53 |
| u100 | 107.59 / 42.07 | 120.24 / 41.93 |
| u200 | 73.55 / 35.84 | 85.51 / 34.77 |

+1000 在双侧 u0 验证握持入口改善了 H1 TCP 和六臂角误差。两侧旧、新独立集均失去 +0 的 H32 精度，前拉六个真实 Actor 首命令的平均张夹绝对误差还从 24.88 升至 28.60 mm。两侧各六个读数来自三个验证起点、两个行为 Actor。按登记的选点依据，**新 seed0 用本轮 +0 WM 和标准 B0-03 Actor 启动**。新增预热 1,000 次计入本轮花费，选入权重的新增预热为零。[+1000 首命令误差](../results/b0/standard_response_20261124/response_w1000.csv) · [旧握持验证](../results/b0/response_w1000_recovery_b_grip_challenge_r1/errors.csv) · [多模式验证](../results/b0/response_w1000_lanes_modes_v1/errors.csv)

联训每次 H32 前使用 2 个 H1、8 个 H7，batch 均为 256。H1 每批 192 在线、64 登记 Warp；H7 每批 192 在线、32 native、32 登记 Warp。三个 Warp 源按合法 lane 与 age 抽样，余数按固定 minibatch 序号轮转。2,000 个实际 WM batch 的在线份额均抽足。Actor 的 256 个起点来自当前在线 replay。每次 H32 配 20 个 Critic minibatch。逐 batch 文件含源、侧、phase、接触模式、episode 数、后继数与 stored positions。[联合配置](../config/b0/standard_response_v1.yaml) · [u0–50 实抽](../results/b0/response_s0_v1/wm_draws.jsonl) · [u50–100 实抽](../results/b0/response_s0_to100_v1/wm_draws.jsonl) · [u100–200 实抽](../results/b0/response_s0_to200_v1/wm_draws.jsonl)

| 实抽窗数 | 在线 | native | 旧 grip | 多模式 | 本轮响应 |
|---|---:|---:|---:|---:|---:|
| H1，400 批 | 76,800 | 0 | 8,534 | 8,533 | 8,533 |
| H7，1,600 批 | 307,200 | 51,200 | 17,066 | 17,067 | 17,067 |

## 原目标梯度与更新后的实际命令

正常 u1 更新在实际官方反传图中读取同一批在线起点和同一份噪声。256 个起点对应 149 个 episode，72 个为 terminal 区间，35 个来自 open/hold。按每个样本的首命令物理单位计算回报上升方向。open/hold 的夹口动作率贡献平均 −13.28/m，末端 Critic 贡献 +109.81/m，含 tracking、乘积法则的 survival 项、限位和原辅助项后的完整梯度为 +97.41/m。J2 的动作率贡献 +7.45/rad，完整梯度 +7.55/rad。全批夹口与 J2 的分项和对完整梯度相对 L2 残差分别是 0.357% 和 0.125%；报告保留了逐通道数值差。Critic 上限为 10，其项表示学习目标内的影响。[实际梯度](../results/b0/response_s0_v1/gradient_u1.json) · [含 open/hold 分组及残差的 manifest](../results/b0/standard_response_20261124/baseline_manifest.json)

在原验证握持求解器状态与完全相同的 history、previous action、goal 上重查 u0/u1/u10，前拉首命令总开度为 44.14→43.61→48.22 mm，背推为 49.48→53.08→61.23 mm；对应真实末端开度前拉 50.41→50.22→57.30 mm，背推 71.58→67.29→68.79 mm。六个分支的独立事件判断均在第 1 子步终止。u200 同样复查后，前拉命令/实际为 32.75/26.88 mm，背推为 63.72/63.89 mm，联训 WM 预测分别为 18.86 和 28.99 mm。夹口单通道均值梯度和一条训练分支不能预测两个独立物理入口的动作更新。[u1/u10 重查](../results/b0/standard_response_20261124/response_actual_u10.csv) · [本轮 u200 重查](../results/b0/standard_response_20261124/response_actual_u200.csv)

## 正式物理结果与预算

| seed0 节点 | 原十项 | stable_grip 首个 2 ms 净门力，前拉 / 背推（N） | 背推释放峰力（N） | 背推释放首次失败（ms） |
|---|---:|---:|---:|---:|
| u0 | 0/10 | 51.07 / 33.15 | 106.02 | 40 |
| u1 | 0/10 | 51.06 / 33.16 | 98.06 | 40 |
| u10 | 0/10 | 51.03 / 33.18 | 84.74 | 40 |
| u50 | 0/10 | 51.03 / 33.15 | 36.47 | 60 |
| u100 | 0/10 | 28.47 / 19.40 | 28.95 | 204 |
| u200 | 0/10 | 39.62 / 16.50 | 24.84 | 964 |

u50 背推释放的力与存续支持延长至 u100；u100 六个入口实际降力，支持延长至 u200。u200 背推释放从手指非抓持部位碰撞变为工位漂移，前拉入口门力较 u100 回升。两侧握持入口仍超 6 N；三个训练段累计 1,094 个 open/hold 有效区间，其中 1,091 个 terminal，所有相位中完整 20 ms 双指持续区间为零。本轮在所要求的 u200 端点封存。完整任务与 0.90、0.88 的分差均为 NA。十项 10/10 后才有 D、完整双侧 Warp/C 和同包 native，随后才是独立 seed1/2 与三 seed 冻结后的 H。[正式成绩与失败分类](../results/b0/standard_response_20261124/nominal_summary.json) · [u50 背推接近至参考耗尽的实测视频](../results/b0/standard_response_20261124/u50_push_approach_grasp.mp4)

新链三段新增 50＋50＋100，共 200 H32、2,000 联合 WM、4,000 Critic、1,638,400 个想象步。实际 276,480 个控制区间含 217,971 个有效在线区间与 58,509 个前缀区间。27,668 个失败后诊断子步已包含在物理采集内。联合 WM 共抽 512,000 个窗、2,969,600 个真实后继目标、3,481,600 个 stored positions。另继承 B0-03 的 1,000 Actor、10,000 WM、20,000 Critic、1,088,000 个有效在线转移。本轮首次响应采集 41.98 s，预热 24.23 s，三段联训进程计时合计 326.27 s，正式逐案物理计时合计 137.69 s；共享 GPU 的各项计时有重叠。未开展额外旧/新保留配方因果对照。[预算、回执、权重与恢复路径](../results/b0/standard_response_20261124/baseline_manifest.json)

恢复时按既定行政截断重建真实前缀，父末点与子起点的 Actor、WM、Critic 张量分别相等。现场 u200 完整状态为 `/root/autodl-tmp/dog-and-arm-b0-response-v1/results/b0/response_s0_to200_v1/cohort_state.pt`，含六个优化器、32 个 replay 块、RNG、ReturnSampler 和 Ratio。尚有 1 次待调度更新。只读复抽 H1/H7 的状态、命令、上下文和来源计数逐项相等。下一轮优先使用已有 2 ms 子步解释夹口端点积分残差和 J2 交叉方向失配，先定位可修的平台接口，再决定标准迁移的下一步。[恢复复抽](../results/b0/standard_response_20261124/resume_draw_check.json) · [接续入口](../prompts/NEXT_RUN.txt)
