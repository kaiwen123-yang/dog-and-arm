# MM03 多模态腿臂仿真实验

2026-11-27T00:37:28+08:00（北京时间），r16 工作块。

A 已有 44/44 个干预或教师参考案。B 的新完整教师通过 96/96（计划 96），已回执的正式纯学生案 0/324。L16、B 高层、C 分支、WM、bridge 累计实付分别为 60,000、393,216、7,680、48,000、87,000 次。

原生 MuJoCo 3.3.0，2 ms 伺服、20 ms 学习控制、100 ms 腕部 RGB-D。按原 12 事件判分。真实硬件运动命令 0。

## A 通道替换和轮腿学习

| R6 父包 | 替换通道 | 完成 / 实跑 | 驶近 | 停稳 | 触门 |
|---|---|---:|---:|---:|---:|
| model_trajectory | student | 0/4 | 0 | 0 | 0 |
| model_trajectory | teacher_arm_grip7 | 0/4 | 0 | 0 | 0 |
| model_trajectory | teacher_legs12 | 0/4 | 3 | 3 | 0 |
| model_trajectory | teacher_legs_wheels16 | 0/4 | 4 | 4 | 0 |
| model_trajectory | teacher_wheels4 | 0/4 | 0 | 0 | 0 |
| supervised_aggregate | student | 0/4 | 4 | 0 | 0 |
| supervised_aggregate | teacher_arm_grip7 | 0/4 | 2 | 0 | 0 |
| supervised_aggregate | teacher_legs12 | 0/4 | 2 | 2 | 0 |
| supervised_aggregate | teacher_legs_wheels16 | 0/4 | 4 | 4 | 0 |
| supervised_aggregate | teacher_wheels4 | 0/4 | 4 | 0 | 0 |
| teacher | teacher_all23 | 4/4 | 4 | 4 | 4 |



A 的每个 2 ms 子步日志保存在 AutoDL 对应 case_dir/physics_2ms。旧 CPU 推理复测、逐轮失载分析及额外代价见 receipts/A。

## B 全程学习与 C 同父对照

微调种子为 1701、1702、1703。候选冻结状态为 False，新盲测启动状态为 False。 完整教师、真实教师前缀后的学生续演、从 frame0 执行的纯学生及低层工程试验在逐案表有独立身份。

| C 分支 | 微调种子 | 实付 / 保留更新 | 开发成功 / 实跑 | 短窗存活 / 实跑 | 训练额外真物理子步 |
|---|---:|---:|---:|---:|---:|
| C0 | 1701 | 512/512 | 0/8 | 28/32 | 0 |
| C0 | 1702 | 512/512 | 0/8 | 28/32 | 0 |
| C0 | 1703 | 512/512 | 0/8 | 28/32 | 0 |
| C32 | 1701 | 512/512 | 0/8 | 29/32 | 0 |
| C32 | 1702 | 512/512 | 0/8 | 28/32 | 0 |
| C32 | 1703 | 512/512 | 0/8 | 28/32 | 0 |
| C32G | 1701 | 512/512 | 0/8 | 28/32 | 0 |
| C32G | 1702 | 512/512 | 0/8 | 27/32 | 0 |
| C32G | 1703 | 512/512 | 0/8 | 29/32 | 0 |
| C8 | 1701 | 512/512 | 0/8 | 29/32 | 0 |
| C8 | 1702 | 512/512 | 0/8 | 29/32 | 0 |
| C8 | 1703 | 512/512 | 0/8 | 29/32 | 0 |
| CF32 | 1701 | 512/512 | 0/8 | 29/32 | 5,201,867 |
| CF32 | 1702 | 512/512 | 0/8 | 29/32 | 5,206,904 |
| CF32 | 1703 | 512/512 | 0/8 | 29/32 | 5,214,005 |

## L16 独立工程评测

| 低层种子 | 工作块 | 同时满足全部工程判据 | 计划案数 |
|---:|---:|---:|---:|
| 1701 | 0 | 13/40 | 40 |
| 1701 | 1 | 2/40 | 40 |
| 1701 | 2 | 0/40 | 40 |
| 1702 | 0 | 13/40 | 40 |
| 1702 | 1 | 0/40 | 40 |
| 1702 | 2 | 0/40 | 40 |
| 1703 | 0 | 13/40 | 40 |
| 1703 | 1 | 1/40 | 40 |
| 1703 | 2 | 1/40 | 40 |

工程通过同时要求支撑、停车、漂移、运动方向响应及安全条件。单轮载荷和停车段速度保存在各案原始路径。

## 真实教师前缀后的学生续演

已结束 1763 案，1763 案实际切换到学生，70 案继续完成全部事件。

## 正式纯学生评测

主评测计划为三个方法、三个微调种子，每包 20 已公开回归案和 16 新组合案。目前无已完成的正式成绩。

## 最近完成的完整开发矩阵

| 方法 | 微调种子 | 轮次 | 全程成功 | 驶近 | 停稳 | 首败最多的原因 |
|---|---:|---:|---:|---:|---:|---|
| D23 | 1701 | 16 | 0/8 | 5/8 | 0/8 | wheel_support_or_tilt (6)、timeout:settle (2) |
| D23 | 1702 | 16 | 0/8 | 6/8 | 0/8 | wheel_support_or_tilt (6)、timeout:settle (2) |
| D23 | 1703 | 16 | 0/8 | 4/8 | 0/8 | wheel_support_or_tilt (5)、timeout:settle (3) |
| H9 | 1701 | 16 | 0/8 | 1/8 | 1/8 | timeout:approach_base (4)、unexpected_contact:robot_panel (4) |
| H9 | 1702 | 16 | 0/8 | 3/8 | 1/8 | door_contact_outside_manipulation (4)、operation_station_drift (1) |
| H9 | 1703 | 16 | 0/8 | 2/8 | 1/8 | timeout:approach_base (4)、door_contact_outside_manipulation (2) |
| H9-WM | 1701 | 16 | 0/8 | 1/8 | 0/8 | timeout:approach_base (7)、timeout:settle (1) |
| H9-WM | 1702 | 16 | 0/8 | 0/8 | 0/8 | timeout:approach_base (7)、unexpected_contact:robot_panel (1) |
| H9-WM | 1703 | 16 | 0/8 | 2/8 | 0/8 | timeout:approach_base (5)、timeout:settle (2) |

## 训练吞吐

三个种子的 D23 和 H9 共六条训练链完成相同更新预算，第 2 轮耗时 766.1 秒，第 4 轮耗时 376.9 秒，训练阶段吞吐为原来的 2.03 倍。整卡 GPU 利用率在优化前的短窗口平均为 27.2%，双优化器重叠时为 84.8%，另一个包含物理采集的窗口为 39.9%。 H9-WM 实付配对在等长 120 秒窗口内从 47 次增至 98 次，原生物理吞吐从 4,011 升至 8,363 子步/秒。

[等预算阶段、实际GPU采样和数值对照](../results/multimodal/mm03_20261126/performance/summary.json)

在同一轮 H9-WM 真物理配对中，两路每分钟实付 51.3 次更新，三路实付 72.0 次，已采用三路。两种配置分别测量 180 和 180 秒。 [逐分钟数据与完成时间估算](../results/multimodal/mm03_20261126/performance/cf32_concurrency/README.md)

第六轮三个种子每个从 6 增至 7 个物理进程，实付更新由 65.3 增至 70.0 次/分。同锚点 H32 真前向及完整反传从 4.10 秒缩至 3.57 秒，单个原生进程的轮地接触读取对照达到原吞吐的 1.49 倍。第八轮 H9 采集的两个 24 案批次，以 4 和 12 个进程分别完成 2,884 和 6,433 个物理子步/秒。仅余种子 1702 时，6/12 进程同种子生产对照分别实付 28.7/28.7 次/分，剩余更新采用 6 进程。 [同批次计时、生产吞吐与最新估时](../results/multimodal/mm03_20261126/performance/cf32_latency/README.md)



## 视频与恢复

MM02 的四条原轨迹共 8 个全程或局部视频。[同回合视频索引](../results/multimodal/mm03_20261126/videos/mm02/index.json)

[完整教师 · teacher_26112600_tr_nominal_pull15 · 12/12 事件](../results/multimodal/mm03_20261126/videos/mm03/teacher_pull15_1080p.mp4)

[全程学生 · warm_development_D23_1701_tr_nominal_pull15_pure · 0/12 事件](../results/multimodal/mm03_20261126/videos/mm03/warm_d23_pull15_1080p.mp4)

[全程学生 · warm_development_H9_1701_tr_nominal_pull15_pure · 1/12 事件](../results/multimodal/mm03_20261126/videos/mm03/warm_h9_pull15_1080p.mp4)

进入 AutoDL 的 /root/autodl-tmp/dog-and-arm-mm03 后执行下列命令。

```bash
bash scripts/multimodal/mm03_session.sh /root/autodl-tmp/mm03-20261126
.venv/bin/python -m scripts.multimodal.mm03_launch status
```

[状态与可恢复包](../results/multimodal/mm03_20261126/manifest.json) · [实际预算](../results/multimodal/mm03_20261126/budget.json) · [逐案结果](../results/multimodal/mm03_20261126/physical_cases.jsonl)
