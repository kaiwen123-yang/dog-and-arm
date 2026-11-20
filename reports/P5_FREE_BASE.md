# M1 与 Piper H 自由底盘慢行

2026-11-20 在本机 MuJoCo 3.3.0 用联合模型运行。由已有带地面场景生成 `sim/scenes/p5_free_base.xml`，保留一个自由根、全部机器人质量/碰撞与两指约束。从已有 home 初始化一次，此后仅发关节执行器指令并调用 mj_step。四轮初始轮轴逐一测得为世界 +Y。轮速由目标前进速度、各轮横向偏移和名义滚动半径 0.096 m 计算。腿关节保持参考姿态。负载采用同一套名义腕部附件配置。

## 按车头方向停车

在上述轮速控制外增加车头方向反馈。以本段开始时的车头为零，5 秒内把目标平滑变到 12°。控制器读取仿真姿态，将角度误差变为有上限的偏航速度指令。测得误差首次进入 0.12° 后，四轮制动。这个数值是触发制动的门槛，车身随后仍会轻微滑动。

实际桌面命令如下。地面短线间隔 10 cm。数据在最后一帧停留前写入磁盘，关窗即可退出。

```bash
bash scripts/project_env.sh python scripts/p5_free_base.py --config config/p5_heading.yaml --live --video --hold-final
```

- 完整左转运行 40 s，共 20,000 步，CSV 有 2,000 行，视频有 1,000 帧。直行 0.360 m 后转向，转向段车头实际改变 12.167°，伸臂再走 0.221 m，整段结束时车头为 12.170°，水平速度 0.063 mm/s。采样最大绝对横滚和俯仰分别为 0.021°、0.048°，轮地切向滑动速度峰值 0.117 m/s，峰值出现于转向。 [运行视频](../results/p5/heading_12/motion.mp4) · [曲线](../results/p5/heading_12/motion.png) · [桌面最终姿态](../results/p5/heading_12/desktop_final.png) · [原始时序](../results/p5/heading_12/timeseries.csv)
- 在同一场景只将目标改为 −12°，独立无窗口步进 40 s，最终车头 −12.139°。保存原始配置和从 50 Hz 时序抽取的 10 Hz 航向数据。两个方向的执行器力矩均在配置上限内，警告计数为 0，只有轮子与地面发生非零接触力。验证范围为同一平地、名义载荷和这两个目标方向。 [右转汇总](../results/p5/heading_minus12_check/summary.json) · [右转时序](../results/p5/heading_minus12_check/heading_10hz.csv)

下一阶段 P6 把已验证的低速接近、制动与把手接触放进同一自由底盘场景。需记录接触过程中底盘的位置、轮滑、把手受力及松爪后的门角。

## 首次完整记录

运行 `bash scripts/project_env.sh python scripts/p5_free_base.py --live --video --output results/p5/free_base_nominal` 得到 33 s / 16,500 步、50 Hz 的 1,650 行数据与 825 帧视频。复跑时省略输出目录，使用新的时间目录。 [桌面截图](../results/p5/free_base_nominal/desktop.png) · [视频](../results/p5/free_base_nominal/motion.mp4) · [曲线](../results/p5/free_base_nominal/motion.png)

| 观察段 | 实测结果 |
| --- | --- |
| 自由站立 | 初始从 0.543 m 落到约 0.532 m，随后 2 秒保持阶段水平漂移约 0.021 mm |
| 慢行、停车 | 直行 0.360 m，随后 2 秒制动再前移 3.1 mm，制动段末水平速度 0.085 mm/s |
| 左转 | 7 s 轮速差控制期间参考角速度积分 28.42°，实转 10.40°。50 Hz 采样最大轮地切向滑动速度 0.117 m/s |
| 伸臂慢行 | J1/J2/J3 指令分别增加 8°/10°/8°，保持伸臂慢行 0.221 m 后收回。最终水平速度 1.08 mm/s |
| 支撑 | 全程采样最大绝对横滚/俯仰 0.041°/0.045°，落地后有三轮承重样本。只有轮子与地面发生非零力接触，执行器在设定范围内，MuJoCo 警告为零 |

CSV 包含每个已驱动关节的位置、速度和执行器力/力矩，以及根姿态和逐轮法向力。轮地滑动量取承重点相对静止地面的水平速度，分解到轮轴方向和与之垂直的滚动方向。一个轮有多个承重点时记录滑动最大点，空载记 NaN。总力/力矩上限为仿真设置。所有实验来自本机平地单次名义运行。 [完整时序](../results/p5/free_base_nominal/timeseries.csv) · [汇总](../results/p5/free_base_nominal/summary.json)

该次基准使用固定时长的角速度指令。后续按车头方向停车的结果见本报告上方。
