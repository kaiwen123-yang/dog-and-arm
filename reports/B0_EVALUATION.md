# B0 物理评测与留出预测误差

2026-11-21，`rail_bridge_front60_v2`。冻结条件已登记；下表是 native MuJoCo 3.3.0 的教师动作接口对照。学习策略逐案结果另由每个检查点目录的 `physical/cases.csv` 记录。

## 初态与判据

[无接触开发条件](../config/b0/eval_cases.json)固定了 20 个初态，对 support、moving_arm、park 使用同一表。初态 world XY 各在 ±10 mm、绕世界 Z 的 yaw 在 ±2° 内，保持参考与世界坐标系固定。每个回合只初始化一次，独立重建 Actor 历史。NativePlant 逐 2 ms 检查限位、支撑、失稳、饱和、接触与求解器警告；真实策略比较采用 20 ms 策略边界（包括起点和末帧）。提前中止保留末态与首个原因；非整策略步的末态不与后续参考帧配对。

每类目标 ≥18/20。根位置与 p4_grasp TCP 的指标是世界系欧氏距离 RMSE，门槛分别为 0.05 m 和 0.03 m；根姿态是 SO(3) 最短旋转角 RMSE，门槛 5°。12 个腿关节和 6 个臂关节分别计算角度 RMSE / 各自关节范围，各关节均须 ≤5%。四轮角速度按 rad/s，双指实际开口按 m 单列。逐案文件同时记录底盘位移、六轴峰值展开、终态回收偏差、夹爪范围与末秒车速。单条 nominal 诊断没有 20 条开发条件的分母。

[完整门预留条件](../config/b0/door_held_out.json)已按固定 RNG 保存前拉、95° 背推各 50 个扰动组合，和原 C01–C20 去重。现场只检查初态几何。每侧 50/50 均有效，排除数 0，初态机器人—门最小几何净空分别 0.529295 m 与 0.058647 m。无接触三类各 20/20 初态有效，最小净空 1.022990 m。这些数量仅表示初态有效。详见[逐案几何数据](../results/b0/native_replay_audit_r1/initial_geometry.json)。

## 真实动作重放

在原 3.3.0 工程中，从各教师回合的初始 qpos/qvel 开始，将实际存储的 post-clamp 23 维目标经 B0 固定伺服执行 350 次，每次 10 个物理步。下表使用实际执行的 351 帧与对应参考。四条回合皆完成 7 s，均无物理审计失败。没有在步间设置参考状态或教师接管。[逐回合测量](../results/b0/native_replay_audit_r1/teacher_replay.json)

| 回合 | simulation steps | 根位置 RMSE（m） | p4_grasp RMSE（m） |
| --- | ---: | ---: | ---: |
| support | 3500 | 2.75e−14 | 2.55e−14 |
| moving_arm | 3500 | 1.01e−13 | 9.19e−14 |
| park | 3500 | 1.27e−13 | 1.17e−13 |
| moving_arm_wm_validation | 3500 | 1.92e−13 | 1.81e−13 |

## 留出回合预测对照

`moving_arm_wm_validation` 是独立采集、含扰动的教师物理回合，未用于 WM 训练，也不在跟踪参考库。固定选 128 个起点，三个 horizon 使用相同起点。每个起点输入实际执行动作序列，WM 从起点连续递归，不刷新中间真值。持位基线复用起点位置和速度；恒速基线通过 `mj_integratePos` 在自由基座和有名关节上积分，再做同一个 TCP 的 FK。物理速度按原 qvel 表示。预测 divergence 单列失败样本数，不只统计幸存样本。[全部分组误差](../results/b0/native_replay_audit_r1/held_out_baselines.json)

| 跨度（策略步） | 持位根位置（mm） | 恒速根位置（mm） | 持位 TCP（mm） | 恒速 TCP（mm） | 持位/恒速轮速（rad/s） |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1.121 | 0.250 | 1.864 | 0.548 | 0.04558 |
| 7 | 7.670 | 1.841 | 12.377 | 6.067 | 0.09974 |
| 32 | 34.260 | 12.324 | 51.454 | 34.154 | 0.29202 |

`learning.b0.diagnostics.checkpoint_eval` 针对每个训练 seed、Actor update、checkpoint 输出 native CPU 物理版本、真实 3×20 或 3 条 nominal、各 case 的完整性与失败原因、每类第一条轨迹的实测时序和画面、同一留出回合的 WM/两种数值对照表。画面来自物理轨迹的离线回放；不足 0.25 s 的轨迹只输出起止帧和实际时间。完整 50 Hz qpos/qvel 与预测数组单独保存在评测目录 `evaluation.json` 所登记的本地路径。

## 已执行命令

```bash
bash scripts/project_env.sh python -m learning.b0.evaluate results/raw_large/b0/native_teacher_20261121_r1 results/b0/native_replay_audit_r1
bash scripts/project_env.sh python scripts/b0/register_eval_cases.py results/raw_large/b0/native_teacher_20261121_r1 config/b0/door_held_out.json results/b0/native_replay_audit_r1/initial_geometry.json
```

以上写入命令要求新输出路径。独立检查只用 native 物理和现有源资产，未运行 B0-04～06 学习评测。

## seed0，Actor 更新 2 的独立开发评测

从 `results/b0/free_s0_integration_r1/checkpoint_000002.pt` 单独装载，物理执行使用训练解释器中的 native CPU MuJoCo 3.16.0。每条预定时长 7 s。实际 60 条均在 0.100–0.176 s 因轮载或倾斜审计终止，三类均未到伸臂/移动/停车末态。[逐案 CSV](../results/b0/free_s0_u2_independent_eval/eval_000002/physical/cases.csv)

| 参考 | 通过 | 轮载中断 | 倾斜中断 |
| --- | ---: | ---: | ---: |
| 支撑伸收臂 | 0/20 | 19 | 1 |
| 移动变臂姿 | 0/20 | 19 | 1 |
| 减速停车收臂 | 0/20 | 9 | 11 |

同一独立回合的 WM 对 1/7/32 步根位置 RMSE 为 5.925/7.191/331.214 mm，TCP 为 5.811/21.886/767.860 mm。三种跨度上的 TCP 误差都高于恒速外推。两次更新证实了程序中的交互和优化路径；物理开发集验收仍未通过。[预测误差 CSV](../results/b0/free_s0_u2_independent_eval/eval_000002/model_errors.csv)

```bash
bash scripts/b0/env.sh python -u scripts/b0/train.py --run free_s0_u2_independent_eval --seed 0 --updates 2 --eval-only --from-checkpoint results/b0/free_s0_integration_r1/checkpoint_000002.pt
```

原工程 MuJoCo 3.3.0 也已执行同一 u2 Actor 的三个 nominal 从头评测。推理进程使用独立 B0 环境，原物理进程每 20 ms 发送实际 qpos/qvel、接收 23 维策略动作，序列内没有重置或教师动作。三类均在 0.100 s 首次出现持续轮载不足，支撑/移动/停车的实测 TCP RMSE 为 81.28/81.28/85.73 mm（终止前 6 帧）。同一检查点原 integration 的 3.16.0 CPU nominal 结果为 0.174 s 倾斜终止。两版均未完成任一完整 7 s 轨迹。[3.3.0 逐案结果](../results/b0/free_s0_u2_native33/physical/cases.csv)

```bash
bash scripts/b0/env.sh python -u scripts/b0/eval_native33.py --run free_s0_u2_native33 --checkpoint results/b0/free_s0_integration_r1/checkpoint_000002.pt
```

## 冷启动动作的受控实验

从 support 的规定初态进入最前 0.8 s 静止目标，使用原 MuJoCo 3.3.0，每个子步读取四轮法向载荷、实际倾角、饱和和抓持点偏差。共 11 种操作，两个冻结检查点分别执行。动作分组修改后，把实际施加的上一动作送回 Actor 历史。以下数据属于故障诊断，各条件均不作为策略通过案例。[u0 完整逐项结果](../results/b0/free_s0_u0_init_blocks/action_blocks/results.csv)和 [u2 完整逐项结果](../results/b0/free_s0_u2_init_blocks/action_blocks/results.csv)

| 条件 | u0 的物理结果 | u2 的物理结果 |
| --- | --- | --- |
| 原策略或保持首条完整动作 | 两者均 0.100 s 失载 | 两者均 0.100 s 失载 |
| 仅腿使用策略 | 0.100 s 失载 | 0.100 s 失载 |
| 腿保持 home，其余由策略控制 | 0.518 s 非预期接触，终点 TCP 误差 711 mm | 0.600 s 非预期接触，终点 TCP 误差 428 mm |
| 仅臂使用策略 | 0.796 s 非预期接触 | 0.026 s 非预期接触 |
| 仅轮或仅夹爪使用策略 | 两者均完成 0.8 s | 两者均完成 0.8 s |
| 全组使用冻结 home | 0.8 s，最大倾角 0.029°，最长失载 0.016 s | 同左 |

u0 首条策略命令相对 home 的组内最大偏差为腿 16.19°、轮 4.44 rad/s、臂 110.35°、夹爪 24.64 mm；u2 分别为 9.28°、3.57 rad/s、83.14°、13.40 mm。三类参考共 1050 条教师转移，全部 12 个腿目标恒定，6 个臂目标中有 3 个恒定。u0 首条动作 23/23 通道越出三条教师命令的各自范围；u2 为 22/23。前两轮在线采集 320 条真实转移，8 个 lane 跨 41 个 episode_id。264 个候选连续八帧起点中，65 个位于同一物理 episode。教师采样占比在这两次 WM update 分别为 99.375% 与 98.125%。[u0 覆盖](../results/b0/free_s0_u0_init_blocks/action_blocks/teacher_coverage.json)和 [u2 覆盖](../results/b0/free_s0_u2_init_blocks/action_blocks/teacher_coverage.json)

早期两个 Actor 的腿动作单独就足以造成持续失载，臂动作也能独立触发碰撞。有效教师动作范围与策略首条命令的差距，给出了后续核查早期 WM 外推和动作初始尺度的直接依据。该消融只解释这两个检查点和所测初态；其他检查点需要独立评测。

```bash
bash scripts/b0/env.sh python -u scripts/b0/eval_native33.py --action-blocks --run free_s0_u0_init_blocks --checkpoint results/b0/free_s0_integration_r1/checkpoint_000000.pt
bash scripts/b0/env.sh python -u scripts/b0/eval_native33.py --action-blocks --run free_s0_u2_init_blocks --checkpoint results/b0/free_s0_integration_r1/checkpoint_000002.pt
```

另从三类名义初态分别将冻结教师的第一条 home 动作恒定执行完整 7 s，三个实际物理回合均站稳。支撑、移动、停车参考的 TCP RMSE 分别为 81.4、217.2、175.4 mm，后两类根位置 RMSE 为 177.4、133.3 mm。三类均未通过追踪门槛。该对照区分了维持站姿与实际跟踪目标。[全 7 s 恒定命令对照](../results/b0/native_replay_audit_r1/home_only_comparison.json)

## 可微预测的局部动作方向

固定留出回合 `moving_arm_wm_validation` 的第 100 帧（2.00 s）与其后 7 个实际动作。原 3.3.0 从第 0 帧物理重放至该起点，对首条归一化动作的 23 个通道逐一作对称小扰动，之后动作照原记录执行，测 p4_grasp 的 world XYZ。每个分支从同一个 MjData 副本开始（含求解器状态）。首帧前向重建误差为 qpos 2.88e−14、qvel 2.00e−14；无扰动的 1/7 步 TCP 落点误差均小于 6e−16 m。±0.0005 和 ±0.002 的两套步幅给出的 3×23 灵敏度矩阵，1/7 步相对差分别为 3.93e−5、4.50e−6。各分支的有效接触几何对与四轮加载状态均与原轨迹相同。[两套步幅的真实矩阵](../results/b0/native_replay_audit_r1/action_tcp_fd_k100.json)

世界模型从同一起点作连续预测，冻结参数并对其世界系 TCP 坐标反传，仅测首个动作的影响。下表在 ±0.002 的中心差分上计算，全通道余弦为展开矩阵的余弦，相对误差为差矩阵 Frobenius 范数除以真实矩阵范数。

| 检查点 | 1 步余弦 | 7 步余弦 | 1 步相对误差 | 7 步相对误差 |
| --- | ---: | ---: | ---: | ---: |
| 原方案 u2 | 0.176 | −0.167 | 1.015 | 7.065 |
| 更新 replay 与 home 初始化的 u50 | 0.789 | 0.334 | 0.616 | 2.196 |
| 同一变体 u200 | 0.942 | 0.484 | 0.371 | 1.479 |
| 同一变体 u1000 | 0.954 | 0.717 | 0.361 | 0.704 |

u50 比 u2 的一步动作方向明显改善，7 步仍有较大误差。结果描述这一个已加载的自由运动起点；接触切换处、完整参考及策略能力需分别实测。[u2 的分块误差](../results/b0/free_s0_u2_init_blocks/action_tcp_jacobian.json)和 [u50 的分块误差](../results/b0/free_s0_boundary_r1/eval_000050/action_tcp_jacobian.json)

```bash
bash scripts/project_env.sh python scripts/b0/check_physical_gradient.py native results/raw_large/b0/native_teacher_20261121_r1 results/b0/native_replay_audit_r1/action_tcp_fd_k100.json
OMP_NUM_THREADS=3 TORCH_COMPILE_DISABLE=1 bash scripts/b0/env.sh python scripts/b0/check_physical_gradient.py wm results/b0/free_s0_integration_r1/checkpoint_000002.pt results/b0/native_replay_audit_r1/action_tcp_fd_k100.json results/b0/free_s0_u2_init_blocks/action_tcp_jacobian.json
OMP_NUM_THREADS=3 TORCH_COMPILE_DISABLE=1 bash scripts/b0/env.sh python scripts/b0/check_physical_gradient.py wm results/b0/free_s0_boundary_r1/checkpoint_000050.pt results/b0/native_replay_audit_r1/action_tcp_fd_k100.json results/b0/free_s0_boundary_r1/eval_000050/action_tcp_jacobian.json
```

u200 在同一点的一步终点 TCP 误差 1.46 mm，七步 9.20 mm。一步臂块的方向余弦为 0.969，七步腿与轮仅为 0.032 与 −0.047。真实夹爪作用力对 p4_grasp 的短期影响很弱，该块很大的相对误差应结合真实矩阵范数读取。[u200 分块误差](../results/b0/free_s0_boundary_r1/eval_000200/action_tcp_jacobian.json)

## MuJoCo-Warp 训练后端物理评测

在固定 mjlab_research 的 GPU Simulation 上，每类参考并行运行 20 个规定初态。每一子步查询原物理审计与实际状态。失败 lane 取首个失效子步的 qpos/qvel 与具体原因；同批其余 lane 继续积分，已经失败的 lane 后续数据不参与评分。时间为真实子步计数 × 0.002 s。各后端和各参考独立统计。

| 检查点与后端 | 支撑伸收臂 | 移动变臂姿 | 停车收臂 | 物理结果 |
| --- | ---: | ---: | ---: | --- |
| 原 u2，Warp 3.16.0 | 0/20 | 0/20 | 0/20 | 早期失载或倾斜，50–89 个物理步后中止 |
| 变体 u50，Warp 3.16.0 | 0/20 | 0/20 | 0/20 | 全部 60 条完成 7.00 s，跟踪误差越线 |
| 同一变体 u1000，Warp 3.16.0 | 0/20 | 0/20 | 0/20 | 全部 60 条都在 0.100 s 首次触发持续轮载不足 |

u2 三类的失载数分别为 19、19、9，其余均为倾斜终止。u50 三类 TCP RMSE 范围分别为 81.7–98.1、240.1–255.4、194.1–210.7 mm，移动和停车的根位置 RMSE 分别为 197.2–210.6、151.5–166.1 mm。u50 第一个 world 的首条动作与独立单样本 Actor 推理的最大绝对差不超过 3.0e−5（归一化动作），使用相同权重和干净观测。[u2 逐案](../results/b0/free_s0_u2_warp/physical/cases.csv)和 [u50 逐案](../results/b0/free_s0_boundary_u50_warp/physical/cases.csv)

```bash
OMP_NUM_THREADS=3 TORCH_COMPILE_DISABLE=1 bash scripts/b0/env.sh python -u scripts/b0/eval_warp.py --run free_s0_u2_warp --checkpoint results/b0/free_s0_integration_r1/checkpoint_000002.pt
OMP_NUM_THREADS=3 TORCH_COMPILE_DISABLE=1 bash scripts/b0/env.sh python -u scripts/b0/eval_warp.py --run free_s0_boundary_u50_warp --checkpoint results/b0/free_s0_boundary_r1/checkpoint_000050.pt
```

对 replay/home 变体在同一 0.8 s 原生 3.3.0 窗口重复分组实验。u50 首条腿动作最大偏转 4.84°，全部 11 组都能维持到 0.8 s。u200 首条腿动作最大偏转达 9.74°，完整策略和仅腿组均在 0.100 s 失载，固定腿 home 后其余通道由策略输出可维持至 0.8 s。u200 仅臂组也完成了窗口，但终端 TCP 偏差达 106 mm。优化后该点的一步 TCP 局部灵敏度改善，与实际首条腿动作是否保有轮载是不同的观测。[u50 逐组](../results/b0/free_boundary_u50_init_blocks/action_blocks/results.csv)与 [u200 逐组](../results/b0/free_boundary_u200_init_blocks/action_blocks/results.csv)

以上 u1000 的物理评测和 Jacobian 均为旧隔离环境已结束的实验。u1000 的局部模型方向改善，三个实际跟踪组均未越过自由运动门槛。[逐案物理结果](../results/b0/free_s0_boundary_u1000_warp/physical/cases.csv)和 [局部梯度](../results/b0/free_s0_boundary_r1/eval_001000/action_tcp_jacobian.json)

## 冻结参考与 60 个扰动初态的物理可行性

在原生 MuJoCo 3.3.0 CPU 上，每类参考只用其名义教师已记录的 350 条 23 维命令，依次从同一份 F01–F20 初态表运行。对同一参考的 20 次试验，各帧目标完全相同。固定伺服按现场仿真状态每 2 ms 计算补偿。相机、额外对象真值和 case 身份均未参与选择动作。全程使用与 Actor 相同的 NativePlant、原始世界系参考和完整物理评分。60 个回合均运行到 7.000 s，共 210,000 个真实物理子步。[逐案教师对照](../results/b0/free_reference_feasibility_native33_r1/cases.csv)

| 教师命令对应参考 | 物理及误差判据均通过 | 最大根位置 RMSE | 最大根姿态 RMSE | 最大 TCP RMSE |
| --- | ---: | ---: | ---: | ---: |
| 支撑伸收臂 | 20/20 | 13.28 mm | 1.747° | 17.26 mm |
| 移动变臂姿 | 20/20 | 14.19 mm | 1.747° | 20.58 mm |
| 减速停车收臂 | 20/20 | 14.02 mm | 1.747° | 19.90 mm |

三类的根位置、姿态、TCP 门槛分别为 50 mm、5°、30 mm。三类全部有限关节的最大归一化 RMSE 低于 2.1e−14，门槛为 0.05。所有试验均无子步物理失败。三类最差 TCP 均出现在 F10，本轮最小 TCP 门槛余量为 9.42 mm。[完整指标范围](../results/b0/free_reference_feasibility_native33_r1/summary.json)

**对固定参考和观测的结论。** 这 20 个初态每类 ≥18/20 的目标有直接可行解。同一参考下重放一条命令序列即可达到 20/20。进一步按固定 O1 的 Actor 可见参考字段，取未来偏移 0、5、…、45 帧的 24 维目标关节位置和 24 维速度，以 float32 拼接。1050 个实际动作对应 1043 个不同参考窗口；7 对完全相同的窗口均要求相同动作。按此参考字段查回名义命令，最大误差为 0，不需要从观测辨认初态 XY 扰动。该查表只核查这三条已知参考上的精确可辨性，学习网络能否提取并泛化这一映射仍依赖独立训练和物理评测；此处 20/20 均属于教师命令对照。[参考字段核查](../results/b0/free_reference_feasibility_native33_r1/reference_keys.json)

```bash
CUDA_VISIBLE_DEVICES='' bash scripts/project_env.sh python scripts/b0/check_free_reference_feasibility.py results/raw_large/b0/native_teacher_20261121_r1 results/b0/free_reference_feasibility_native33_r1
```
