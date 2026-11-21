# B0-03 轮地间隙与连续失载

在已保存的教师和 boundary 策略记录中，用**真实整机姿态**计算的轮碰撞网格最低点可以辨别四轮是否达到 1 N 支撑。使用 **WM 预测姿态**时，u1000 在已经承重的轮上仍常常算出正间隙，尤其是 7 步和 32 步预测。几何项可以提供可微的高度误差信号，目前的证据不足以用它判定实际失载。

## 同一物理步的对照

四轮均取活动的带碰撞网格，半径约 96 mm。模型实际编译后的凸包顶点来自 `mesh_graph` 的顶点映射，包含编译器处理过的网格原点和主轴变换。每次 `mj_step` 后直接取该次求解的 `geom_xpos`、`geom_xmat` 和地板法向，将全部凸包顶点到地板的有符号投影取最小值。力标签由 P6 `ContactMeter` 在同一次求解的各轮地接触点上累加法向力，使用配置中的 ≥1 N。地板及轮的碰撞 margin 为零。

四条教师记录在原生 MuJoCo 3.3.0 中按其保存的每步 `ctrl` 重放，所有下一状态和轮载与原文件逐步一致。策略使用评测时的 CPU MuJoCo 3.16.0，引入原来的初态、保存的 23 维确定性动作及实际子步数。策略边界 `qpos` 与保存记录的最大绝对差为 0。全部复核使用 CPU，检查点和训练状态均保持原样。

| 数据 | 轮步 | 达到 / 未达 1 N | 以网格间隙 ≤0 判支撑的错分轮步 | 真实连续失载到达 0.10 s |
| --- | ---: | ---: | ---: | --- |
| support、moving_arm、park 及独立扰动教师 | 56,000 | 55,871 / 129 | 0 | 0/4 |
| boundary u50，三类参考各 F01/F10/F20 | 126,000 | 125,631 / 369 | 0 | 0/9 |
| boundary u200，三类各 F01–F20 | 12,000 | 6,240 / 5,760 | 0 | 60/60 在第 50 个物理步 |
| boundary u1000，同 60 个条件 | 12,000 | 5,460 / 6,540 | 0 | 60/60 在第 50 个物理步 |

每个物理子步有四个轮步。u200 的 3,000 个物理子步中，有 2,880 个同一时刻一部分轮承重、另一部分轮失载。仅使用机身高度无法区分这些轮子。u200 和 u1000 使用网格间隙连续累计 50 个子步，均还原了每一条实际失载终点。在这两组持续失载样本中，每个策略周期末抽一次几何状态也在第 5 个周期触发。20 ms 周期内短暂的重新加载仍可能被抽样遗漏，原物理验收继续按 2 ms 计时。[教师数据](../results/b0/wheel_support_geometry_r1/teacher.json) · [u50 数据](../results/b0/wheel_support_geometry_r1/policy_u50_9.json) · [u200 数据](../results/b0/wheel_support_geometry_r1/policy_u200_60.json) · [u1000 数据](../results/b0/wheel_support_geometry_r1/policy_u1000_60.json)

## 可微几何及模型误差

网格的最低点是有限个顶点投影的最小值。最低顶点唯一时，梯度可经该顶点和根、腿、轮的 FK 回传。在最低顶点切换处存在不可微点。当前 tracking FK 为计算轮的任务朝向屏蔽了轮相位。精确的轮胎最低点需要完整相位，也可对原网格绕真实轮轴取旋转包络。包络允许每一顶点绕轴转到最低处，仅依赖轮轴位置和倾角。在本组轨迹中它最多将间隙低估 0.0821 mm；u50 有 18 个实测失载轮步被包络判成承重。

u50 两次极接近零且符号相反的间隙分别为 −0.000466 mm 和 +0.0000756 mm，对应载荷为 50.34 N 和 0 N。刚体几何只给出位置，接触约束还要使用相对速度、阻尼和系统其他接触来解力。本次数据中没有出现“穿入但低于 1 N”的反例，这不能推出任意受力工况下二者等价。

将同一个网格运算直接用于已保存的 WM 想象轨迹。取独立 `moving_arm_wm_validation`，在每个预测终点使用由该状态开始求解的下一个 2 ms 物理步作为载荷真值。末端无后继物理步的一帧已排除。下表中的真实参考轮全部达到 1 N，实测姿态对应的间隙分类全对。因缺少失载真值，这一预测对照只能量化假失载。

| 检查点 | 指标 | 1 步 | 7 步 | 32 步 |
| --- | --- | ---: | ---: | ---: |
| u200 | 绝对间隙误差 P95，mm | 1.242 | 3.718 | 6.297 |
| u200 | 预测假失载轮数 / 已承重轮数 | 143/512 | 134/512 | 159/508 |
| u1000 | 绝对间隙误差 P95，mm | 0.836 | 1.802 | 2.155 |
| u1000 | 预测假失载轮数 / 已承重轮数 | 26/512 | 145/512 | 165/508 |

u1000 的 7 步、32 步间隙误差足以跨过真实参考中亚毫米的轮地边界。若引入软终止，应先用实际成功和失败 episode 验证分轮模型预测、连续失载时间及其误报，再评估 Actor 的真实支撑表现。本轮诊断未修改训练目标。[u200 预测对照](../results/b0/wheel_support_geometry_r1/held_out_u200.json) · [u1000 预测对照](../results/b0/wheel_support_geometry_r1/held_out_u1000.json)

## 复查命令

在仓库根目录执行，输出路径须使用新的文件名。动作、检查点和参考均来自原记录。

```bash
bash scripts/project_env.sh python scripts/b0/check_wheel_clearance.py --teacher results/raw_large/b0/native_teacher_20261121_r1 --output /tmp/b0_teacher_wheel_check.json
bash scripts/b0/env.sh python -m scripts.b0.check_wheel_clearance --evaluation results/b0/free_s0_boundary_r1/eval_000050 --cases F01 F10 F20 --output /tmp/b0_policy_wheel_u50.json
for milestone in 000200 001000; do
    run="results/b0/free_s0_boundary_r1/eval_${milestone}"
    bash scripts/b0/env.sh python -m scripts.b0.check_wheel_clearance --evaluation "$run" --output "/tmp/b0_policy_wheel_${milestone}.json"
    bash scripts/b0/env.sh python -m scripts.b0.check_wheel_clearance --wm-evaluation "$run" --validation-episode results/raw_large/b0/native_teacher_20261121_r1/moving_arm_wm_validation --output "/tmp/b0_wm_wheel_${milestone}.json"
done
```
