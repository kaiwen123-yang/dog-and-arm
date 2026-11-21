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
