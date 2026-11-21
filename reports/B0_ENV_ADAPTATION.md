# B0-01 整机训练环境

模型来自冻结 P6 的 `p6_scene.build(settings('mobile',1))`，包含一个自由根、一个无执行器的门铰链、两指和一条耦合等式，编译后 nq=32、nv=31、nu=23、neq=1。几何、质量、接触和名义附件沿用 front60_v2。独立环境调用研究版 `mjlab.sim.Simulation`，训练时钟为 2 ms × 10。实际 `ActionMap` 按腿关节名、轮关节名、Piper 六轴、主动指名查 XML 下标。夹口范围 0–100 mm，只在写 ctrl 时换算为主动指位移。所有位置伺服每子步加对应 `qfrc_bias/kp`，轮速伺服无附加偏置。[全通道单位、增益、力/力矩上限](../results/b0/backend_r1/comparison.json)

| 物理对照 | 实际结果 |
| --- | --- |
| 研究环境 3.16 GPU 与 CPU 执行同一组站立、伸臂闭爪、轮速、刹车开爪命令，各 1 秒 | 各段末根部位置差 0.083–0.397 µm |
| 研究 GPU 与 3.3.0 冻结无接触参考，每条 7 秒 | 根位置 RMSE，支撑 0.746 mm、移动 3.993 mm、停车 2.383 mm；对应 TCP 0.779、3.990、2.387 mm |
| 研究 GPU 与 3.3.0 轮载 | 每回合 35 个同步子步抽样，四轮 >1 N 的布尔判断一致。各轮法向载荷 RMSE 0.966–1.587 N |
| 可微 FK 与 MuJoCo FK | 5 个有实测速度的参考姿态，跟踪点最大坐标差 2.05e-7 m，角速度最大分量差 1.12e-7 rad/s |

运行命令如下。

```bash
bash scripts/b0/env.sh python -m scripts.b0.check_backend --worlds 4 --output results/b0/backend_r1/comparison.json
bash scripts/b0/env.sh python -m scripts.b0.compare_reference --output results/b0/backend_r1/native33_teacher_vs_mjlab.json
```

O1 FK 对机器人子树仅支持 hinge。B0 复用其自由根与上游旋转链，在掌部显式组合两指的独立 slide 位移、速度和任务 `p4_grasp` 点。跟踪轮中心的位置和角速度，评分时消除轮的绝对自旋相位。GenCoord 输入来自原始广义坐标，世界线速度直接取 free qvel 平移，角速度从体坐标旋转到世界坐标。B0-03 只预测机器人 24 个关节含双指，full_state 61 维、rep_state 58 维。门保留在物理中。门角速度预测与相对门几何属于 B0-04。[FK 对照](../results/b0/backend_r1/fk.json) · [参考对照](../results/b0/backend_r1/native33_teacher_vs_mjlab.json)

本机 Warp 编译时报告 capsule–mesh 无多点 CCD 支持，单对至多一个接触点。无接触跟踪对照覆盖轮地；门口双指接触下的后端行为必须另行验证。
