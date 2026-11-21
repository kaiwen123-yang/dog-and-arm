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
