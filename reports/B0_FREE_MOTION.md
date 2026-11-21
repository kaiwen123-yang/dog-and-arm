# B0-03 seed0 无接触跟踪

## 首次物理学习闭环

本机 16 GiB RTX 5080 Laptop 使用 8 个研究版 mjlab 世界。GenCoord dt=20 ms、解析积分系数 0.55，WM/Actor/Critic 的主层宽、latent32、history10、运动参考编码器、官方 normalizer、replay、ReturnSampler 和 Muon/Adam 参数分组来自固定 O1。使用 10×32 的 8 状态 WM 窗口、16 条 H32 的 Actor rollout、replay_ratio=16、采集噪声 0.1。将实际两指增量和误差缩放到 m、m/s，分别使用 2 mm 和 0.05 m/s 名义误差。无接触物理和想象评分共用 O1 的六项身体跟踪奖励与速度、软限位惩罚，参考速度以世界系表示。[动作、配置和源码版本](../config/b0/baseline.yaml)

从三条原生无接触教师回合预填 replay，留出第四条扰动回合。8 个世界中有重复的教师片段，独立教师转移数为 1,050。每 160 个实测策略转移做 10 个 WM minibatch 和一次 Actor/Critic 联合更新。两轮共 320 个当前策略转移。WM 在 Actor 更新中冻结，真实执行中的上一动作与 WM 接收的均为裁剪后 23 维。第 1、2 次 Actor 梯度范数分别为 125.06、41.18，最后一层权重的最大变化均约 2.00e-4。第二批物理交互发生于第一次更新之后。[实际更新记录](../results/b0/free_s0_integration_r1/updates.jsonl)

```bash
bash scripts/b0/env.sh python scripts/b0/train.py --run free_s0_integration_r1 --updates 2 --integration
bash scripts/b0/env.sh python scripts/b0/train.py --run free_s0_u2_independent_eval --updates 2 --from-checkpoint results/b0/free_s0_integration_r1/checkpoint_000002.pt --eval-only
```

从完整初态在研究环境的 CPU MuJoCo 3.16.0 中独立评估更新 2 的冻结策略。支撑、移动变臂姿、停车分别为 **0/20、0/20、0/20**。回合在 0.100–0.176 s 终止，达到轮失载或倾角门槛。三类名义目标各长 7 s。此处的硬失败独立于 WM 的软终止。[逐案结果](../results/b0/free_s0_u2_independent_eval/eval_000002/physical/summary.json)

| 留出回合，128 个起点，TCP RMSE | 1 步 | 7 步 | 32 步 |
| --- | ---: | ---: | ---: |
| WM，更新 2 | 5.81 mm | 21.89 mm | 767.86 mm |
| 恒速积分 | 0.55 mm | 6.07 mm | 34.15 mm |

一步、七步和三十二步的 3D 根位置 RMSE 分别为 5.92、7.19、331.21 mm。关节、轮速、夹口宽度和持位外推另列。[分组误差](../results/b0/free_s0_u2_independent_eval/eval_000002/model_errors.csv)

权重及归一化器、优化器在本机 `results/b0/free_s0_integration_r1/checkpoint_000000.pt` 和 `checkpoint_000002.pt`，原始交互切片在 `results/raw_large/b0/free_s0_integration_r1/`。恢复入口重新开始物理回合并用教师重建 replay。首轮只检验接口和梯度连接，接触片段、完整门、统一模型及 seed1/2 尚待后续步骤。本轮无硬件运动。

## 固定八帧采样的运行边界

在补齐 GPU 每个子步的轮地支撑、意外接触及求解容量审计后，seed0 另行从零启动正式配置。前 49 次更新实际抽到的长窗口中教师占比平均 99.57%。教师窗口离开环形缓冲区后，最后仅剩短的失败片段。第 160 次更新已完成，第 161 次的真实采集也已完成，随后八个世界各自最近 1,000 帧的缓冲区中无连续八帧有效窗口，官方 sampler 报错退出。累计 25,760 次真实策略转移。该进程未到正式保存节点，已保留更新 0 权重、逐次损失及失败原因。[采样记录](../results/b0/free_s0_formal_r1/updates.jsonl) · [失败记录](../results/b0/free_s0_formal_r1/failure.json)

更新 2 的冻结 WM 对 7 步预测 TCP 的 3×7×23 动作 Jacobian 均可反向传播，各时刻 Frobenius 范数从首步 0.5573 至末步 0.02994。该检查的输出只取预测几何，所有 WM 参数继续冻结。梯度的实际控制价值需要物理评测。[数值](../results/b0/free_s0_integration_r1/frozen_gradient.json)

### free_s0_boundary_r1 的预设修改

动作拆分实验证实，原初始策略腿目标足以在 0.1 s 触发失载，大幅臂目标单独执行也会碰撞。新配置从零建立相同网络，将末层权重乘 0.02，偏置设为模型 home 的 23 路编码。训练后所有层均可更新，评测没有 home 接管。训练用官方同一个 WM 网络及优化器，按固定顺序先做 8 个七步监督批次，再做 2 个一步监督批次，合计仍为 10 次 WM minibatch。一步批次的监督包含真实末状态，保留短失败片段。长窗每批优先抽 75% 合法在线窗口，加 25% 训练参考教师窗口。在线池尚无长窗时长窗批次使用教师数据，一步批次仍全部来自在线。Actor 始终从在线 replay 的真实起点采样，带入采集器保存的完整十帧历史。该配置的新 replay 比例仍按官方状态窗口数量定义，8 个世界每 17 个策略步更新一次。节点为 0/50/200/1000，收集策略和独立物理门槛见配置。[配置](../config/b0/free_replay_home.yaml)

### 执行至更新 200 的诊断与下一组尺度

boundary 变体 u50 在固定的 60 条条件上都连续走完 7 s，三类均 0/20。Warp 的支撑/移动/停车 TCP RMSE 分别为 81.7–98.1 / 240.1–255.4 / 194.1–210.7 mm。u200 的 CPU 3.16 评测中 60 条均在 0.100 s 持续失载。仅使腿回到站姿的独立 3.3.0 消融可走完 0.8 s。冻结 WM 在同一验证点的一步动作→TCP Jacobian 对真实物理差分的余弦从 u50 的 0.789 提高到 u200 的 0.942，七步为 0.334 和 0.484。独立桌面 nominal 实测用 `bash scripts/b0/env.sh python scripts/b0/eval_native33.py --run free_s0_boundary_u50_desktop --checkpoint results/b0/free_s0_boundary_r1/checkpoint_000050.pt --live`。真实求解每步推进，显示窗口从独立 MjData 只读呈现实测状态。[桌面截图](../results/b0/free_s0_boundary_u50_desktop/mujoco_desktop.jpg) · [u50 GPU 物理结果](../results/b0/free_s0_boundary_u50_warp/physical/summary.json)

为检验动作量纲是否使探索过于激烈，另预注册 **free_s0_servo_units_r1**，从 seed0 独立随机初始化，端点 1,000 次 Actor 更新，增加 50、200 两个开发评测节点。原 G1 固定源码将一个动作单位设为 0.25 × 力矩上限 / 位置增益，并以站姿为偏置。将此原则应用到 P6 位置和轮速伺服，得到腿 0.01923 rad、轮 0.5 rad/s、六臂 0.025–0.050 rad、夹口 0.003333 m。0.1 采集噪声在这个网络输出坐标中施加；动作仍映射到同一 23 维规范并使用原物理限幅，参考与真动作数据不重标也不变更。独立结果保留原 O1 tracking 奖励和之前的边界采样适配。[固定 G1 代码](https://github.com/HybridRobotics/mjlab_research/blob/dd51a9fcc98791a2f0b018b3c7f71a3eefd5ecdd/src/mjlab/asset_zoo/robots/unitree_g1/g1_constants.py) · [实验配置](../config/b0/free_servo_units.yaml)


### 本机 1000 次更新与云端独立环境

replay/home seed0 完成 10,000 次 WM 小批更新、1,000 次 H32 Actor 更新和其配套 Critic 更新，共产生 136,000 个真实策略转移。第 1000 次更新的留出 TCP RMSE 为 0.84 / 4.22 / 12.59 mm。原生和 Warp 对三类物理任务分别给出 0/20。后续尺度变体在第 50 次更新完成权重写入、尚在评测时按用户隔离要求停止。其已写逐案仅供诊断。[训练记录](../results/b0/free_s0_boundary_r1/outcome.json) · [实测预测误差](../results/b0/free_s0_boundary_r1/eval_001000/model_errors.csv) · [三类 Warp 评测](../results/b0/free_s0_boundary_u1000_warp/physical/summary.json)

云端从零单独检验伺服尺度和更大批量。128 个并行物理环境，WM 和 Actor 每批各 256，H32 rollout 保留输入梯度。按累计状态数交替执行 8 和 9 个物理交互策略步，再训练 10 个 WM minibatch 和 1 个 Actor update。预设 0、50、200、1000 和 5000 节点，观察完整 3×20 物理表现。若达到三类门槛，冻结并独立复核后停止。[云端配置](../config/b0/free_servo_cloud.yaml)

云端实测 Python 3.13.13、MuJoCo 3.16、RTX PRO 6000。原生对照使用另一个项目内 MuJoCo 3.3.0 解释器。双端可在载入各自 Conda shell 后执行以下命令，激活用户指定的环境名。云端与本机均执行过激活和依赖兼容性检查。[云端实测](../results/b0/runtime_autodl.json)

```bash
export CONDA_ENVS_PATH="$PWD/.conda/envs"
conda activate "arm and dog"
```

云端首次启动在更新 0 因部署缺少关节映射而停止。补齐 `description/joint_map.yaml` 后实际验证 23 路模型及 EGL 渲染器，再用新 run `free_s0_cloud_servo_r2` 从零启动。使用的命令为 `bash scripts/b0/env.sh python -u scripts/b0/train.py --seed 0 --run free_s0_cloud_servo_r2 --config config/b0/free_servo_cloud.yaml --updates 1000`。

已有实测轨迹也暴露出奖励尺度问题。在 u50 的 F01 中，三条完整但未过门槛的轨迹仍分别取得原奖励上限的 94.7%、91.5%、92.3%。纯状态增益变体在原有六项及惩罚之外，引入世界坐标 TCP、根位置、轮中心高度和轮角速度的可微参考误差。在相同轨迹上分别为新上限的 75.9%、63.3%、64.7%，三条教师均在 99.8% 以上。它保留监督 WM、H32 Actor/Critic、所有物理阈值及 23 路网络输出。此处是相同实测状态的目标函数对照，训练结果需单独记录。[奖励对照](../results/b0/free_s0_boundary_r1/eval_000050/tracking_objective.json) · [变体配置](../config/b0/free_metric_cloud.yaml)
