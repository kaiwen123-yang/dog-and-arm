# MM03 多模态腿臂仿真实验

2026-11-26T10:31:28+08:00（北京时间），L16 第 1 个训练块。

A 已有 44/44 个干预或教师参考案。B 的新完整教师通过 96/96（计划 96），已回执的正式纯学生案 0/324。L16、B 高层、C 分支、WM、bridge 累计实付分别为 48,000、19,008、5,507、0、600 次。

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
| C32G | 1702 | 387/384 | 0/0 | 0/0 | 0 |
| C8 | 1701 | 512/512 | 0/8 | 29/32 | 0 |
| C8 | 1702 | 512/512 | 0/8 | 29/32 | 0 |
| C8 | 1703 | 512/512 | 0/8 | 29/32 | 0 |



## 视频与恢复

MM02 的四条原轨迹共 8 个全程或局部视频。[同回合视频索引](../results/multimodal/mm03_20261126/videos/mm02/index.json)

进入 AutoDL 的 /root/autodl-tmp/dog-and-arm-mm03 后执行下列命令。

```bash
bash scripts/multimodal/mm03_session.sh /root/autodl-tmp/mm03-20261126
.venv/bin/python -m scripts.multimodal.mm03_launch status
```

[状态与可恢复包](../results/multimodal/mm03_20261126/manifest.json) · [实际预算](../results/multimodal/mm03_20261126/budget.json) · [逐案结果](../results/multimodal/mm03_20261126/physical_cases.jsonl)
