# SuperMimic-M1Piper-standard-v1｜0.25 ms 训练与原 H32 开发对照

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
