# MM03 多模态腿臂仿真实验

2026-11-28T01:52:44+08:00（北京时间），r32 工作块。

A 已有 44/44 个干预或教师参考案。B 的新完整教师通过 96/96（计划 96），已回执的正式纯学生案 0/324。L16、B 高层、C 分支、WM、bridge 累计实付分别为 60,000、761,856、7,680、96,000、173,400 次。

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

已结束 3461 案，3461 案实际切换到学生，213 案继续完成全部事件。

## 正式纯学生评测

主评测计划为三个方法、三个微调种子，每包 20 已公开回归案和 16 新组合案。目前无已完成的正式成绩。

## 最近完成的完整开发矩阵

| 方法 | 微调种子 | 轮次 | 全程成功 | 驶近 | 停稳 | 首败最多的原因 |
|---|---:|---:|---:|---:|---:|---|
| D23 | 1701 | 32 | 0/8 | 4/8 | 0/8 | wheel_support_or_tilt (7)、timeout:settle (1) |
| D23 | 1702 | 32 | 0/8 | 3/8 | 0/8 | wheel_support_or_tilt (5)、timeout:settle (3) |
| D23 | 1703 | 32 | 0/8 | 4/8 | 0/8 | wheel_support_or_tilt (8) |
| H9 | 1701 | 32 | 0/8 | 0/8 | 0/8 | timeout:approach_base (5)、unexpected_contact:robot_self (3) |
| H9 | 1702 | 32 | 0/8 | 4/8 | 1/8 | timeout:approach_base (4)、timeout:settle (2) |
| H9 | 1703 | 32 | 0/8 | 0/8 | 0/8 | unexpected_contact:robot_self (4)、timeout:approach_base (3) |
| H9-WM | 1701 | 32 | 0/8 | 4/8 | 0/8 | timeout:settle (4)、timeout:approach_base (3) |
| H9-WM | 1702 | 32 | 0/8 | 0/8 | 0/8 | timeout:approach_base (8) |
| H9-WM | 1703 | 32 | 0/8 | 5/8 | 0/8 | timeout:settle (4)、unexpected_contact:robot_self (3) |

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

已完成阶段的旧评测数组和完整 CF32 曝光原件按云端原路径在 H 盘建索引。训练使用的回放字段、回合判分和学生视频渲染输入保留在 AutoDL。当前有 281/281 个批次已通过 H 盘回读并在云端完成释放。 [恢复位置与逐项查找方法](../results/multimodal/mm03_20261126/execution/storage/cold_archive.json)

在第 21 轮同一份冻结成员上，4,644 条轨迹共享原始相机文件。完整读取测试的显存峰值为 6.31 GiB。 [图像与批次核验](../results/multimodal/mm03_20261126/performance/shared_camera/parity.json)

第 22 轮同轮配对每分钟实付更新为 1 个种子 28.0、2 个种子 57.3、3 个种子 87.2。后续优先允许 3 个种子并发，每轮再按实际可用内存和显存分配。 [配对实测](../results/multimodal/mm03_20261126/performance/shared_camera/decision.json)

H7 对 33,792 份旧回放建立索引，已验证的索引重读用时 0.68 秒。相同行序与 RNG 状态下，物理窗口准备吞吐为原来的 1.29 倍。 [H7 抽样与恢复核验](../results/multimodal/mm03_20261126/performance/native_transfer/h7_comparison.json)

CF32 单项传输与合并传输的同轮实付吞吐分别为 81.1 和 83.1 次/分。 [四个生产窗口与所选配置](../results/multimodal/mm03_20261126/performance/native_transfer/decision.json)

教师、纯学生及教师前缀后的学生续演使用相同命令对照，普通回合总用时由 102.1 秒降至 86.6 秒。 [每案判分与逐帧数组校验](../results/multimodal/mm03_20261126/performance/native_transfer/ordinary_comparison.json)

第 22 轮三个 CF32 种子在采集队列空闲时，每种子 7 和 8 个物理进程分别完成 92.0 和 93.3 次更新/分。 [生产对照](../results/multimodal/mm03_20261126/performance/cf32_latency/r22-eight/decision.json)

第 27 轮按世界模型与物理配对各自的资源需求安排三个种子。同轮从两路到三路，实付更新由 59.9 变为 94.6 次/分。 [生产窗口与显存预留](../results/multimodal/mm03_20261126/performance/phase_capacity/decision.json)

第 28 轮每组 24 案的注册采集，12 与 18 个进程各完成 5,370 和 5,840 个物理子步/秒。三种方法按微调种子分组，回合终止时间各异。在同一份第 28 轮世界模型数据上，直接填表使实测显存峰值由 18.76 降至 9.55 GiB。 [逐批回执、调度与全表核验](../results/multimodal/mm03_20261126/performance/ordinary_queue/summary.json)

进入 AutoDL 的 /root/autodl-tmp/dog-and-arm-mm03 后执行下列命令。

```bash
bash scripts/multimodal/mm03_session.sh /root/autodl-tmp/mm03-20261126
.venv/bin/python -m scripts.multimodal.mm03_launch status
```

[状态与可恢复包](../results/multimodal/mm03_20261126/manifest.json) · [实际预算](../results/multimodal/mm03_20261126/budget.json) · [逐案结果](../results/multimodal/mm03_20261126/physical_cases.jsonl)
