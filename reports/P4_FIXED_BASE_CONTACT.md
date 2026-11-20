# P4 固定基座单门接触：前拉与背推记录

日期：2026-11-20（Asia/Shanghai）。起点为 P3 可见检查提交 `4bbf1e5`。本轮没有导入 SDK、CAN、ROS 相机或操作实机。

## 背侧推门与门角反馈

本轮在相同的门和把手高度下把 M1 放在门后 [1.88, 0, 0.54266] m，底盘朝向 90°。把手随门向远离机器人的方向移动。先用背侧 U 形把手、两指夹持做 25° 名义圆弧，松开后实测 22.098246°。这个基准的接触仅限两指和把手。其运行汇总内含原始配置，可用于重建。[基准时序](../results/p4/push_25/timeseries.csv)

同站位下，仅加大夹持力的两次试验实际得到 22.020° 和 22.028°。随后恢复原来的夹爪指令，在保持阶段读取仿真铰链角，通过积分误差在两条已求解的关节路径之间插值，额外手部圆弧限于 4°。松爪和退离沿用最后一次修正。关节执行器带动机器人接触门，铰链由物理积分推进。时序中 planned_angle_deg 与 tcp_error_m 均相对于原始名义轨迹，angle_trim_deg 单列反馈补偿。

执行 `bash scripts/project_env.sh python scripts/p4_fixed_door.py --config config/p4_push.yaml --live --video --output results/p4/push_feedback`，35 s / 17,500 步。最终修正 3.015°，松爪退离后门角 25.076175°，机器人与门扇接触力为零。过程接触对象包括背侧把手与两指，以及把手与夹爪基座（单点峰值 7.728 N）。机器人–门扇接触力范数之和峰值 9.067 N，最大软穿透 0.819 mm，机器人–门框、自碰撞的非零接触力均未记录到，执行器均在设置范围内，警告计数为 0。此结果使用仿真铰链角，较大角度的背侧推门和扰动重复留待后续。[视频](../results/p4/push_feedback/contact.mp4) · [曲线](../results/p4/push_feedback/contact_timeseries.png) · [桌面截图](../results/p4/push_feedback/desktop.png)

## 后续前侧拉门

底盘在 [0.65, 0.30, 0.54266] m 处转 45°，抓住竖直把手后腕部从 0° 缓慢转到 −10°。退离增加 4 cm 抬升和 10 cm 后退，修正早期退离时碰门板的问题。380 个采样姿态通过路径检查。随后在桌面执行 `bash scripts/project_env.sh python scripts/p4_fixed_door.py --config config/p4_pull_60.yaml --live --video --hold-final`。

38 秒内实际拉到 59.963319°，19,000 步，峰值臂力矩 11.856 Nm。警告计数为零，两指与把手以外的机器人–门扇接触为零。松爪退离后门角保持。名义目标 60°，严格达标字段为 false。单次名义条件。 [数据、曲线与桌面截图](../results/p4/pull_60_trial01/)。

## 首段 19.261° 的实际结论

已在用户本机 MuJoCo 3.3.0 桌面运行真实接触：机械臂接近、夹住前侧 U 形把手、沿 20° 名义圆弧拉动、保持、松爪、退离。门实际由 **0° 到 19.261°**，结束时保持该角度。它是固定基座、名义参数的一段有效接触结果。在这个早期节点结束时，尚未完成60°拉门、另一侧推门、自由基座或双门；后续前拉/背推见本报告上方，P5见其独立报告。

- [26 秒运行视频](../results/p4/pull_20deg/contact.mp4)：1280×720、25 fps、650 帧；画面标注物理时间、阶段和实测门角。这是运行时 MuJoCo Renderer 输出，不称作桌面屏幕录像。
- [门角、夹爪、接触力与力矩曲线](../results/p4/pull_20deg/contact_timeseries.png)，另有 SVG。
- [100 Hz 时序 CSV](../results/p4/pull_20deg/timeseries.csv)、[运行汇总](../results/p4/pull_20deg/summary.json)、[IK 规划误差](../results/p4/pull_20deg/plan.json)。
- [修正后试验的桌面截图](../results/p4/trial_03/desktop.png) 证明本机 GUI 显示，独立于离线渲染。最后一次补截桌面时窗口已随试验结束关闭，没有生成该张截图；`rendered_18s.png` 明确来自视频解码，不冒充桌面证据。本轮未取得新的用户观看确认。

## 场景和控制的边界

复用 `sim/robots/m1_piper.xml`、`build_assembly` 的变换/相机函数和 `build_doors.component`，由 `scripts/p4_fixed_door.py` 生成 `sim/scenes/p4_fixed_pull.xml`。官方资产、主模型和安装参数没有修改。

专用 P4 场景只移除 M1 根 free joint，将根固定在 `[0.70,0.38,0.54266] m`，保留所有腿/轮关节、几何与惯量。固定根承担整机支撑；这不是轮足站稳结果。主联合模型仍 `nq31/nv30/nu23/neq1`、一个自由根、43.537064081 kg。P4 加被动门后为 `nq25/nv25/nu23/neq1`、无自由根、55.537064081 kg。

P4 专用把手高度由 1.0 m 改为 **0.85 m**，是可达性场景设计，未改原门配置或实物规格。门宽/质量/铰链/无锁舌/无闭门器/U 形把手保留。附件载荷仍 omitted，相机仍 synthetic_aligned_rgbd。

关节使用 force-limited position servo（隐式积分处理阻尼），bias补偿通过相同执行器，受同一力矩上限约束；`qfrc_bias`包含重力、科氏和离心项。臂六轴上限 `[35,35,30,12,12,8] Nm`，单夹爪上限 10 N；腿/轮为 50/15 Nm。这些是本实验仿真参数，不是实机连续输出能力。步长 0.002 s，integrator=implicitfast。

IK 在独立 scratch MjData 内计算，不写物理状态。物理 qpos 仅在运行初始化设置一次，随后只更新 `ctrl` 并调用 `mj_step`。门没有 actuator、外力、预设角轨迹或把手 weld；仅保留原夹指之间的 equality。早期20°与后续60°前拉采用已知名义门/把手位姿预规划关节目标；后续背推在保持阶段追加仿真门角反馈插值修正，见上方。这些都不是视觉闭环。

## 正式记录的数值

| 指标 | 结果 |
| --- | --- |
| 动力学时长 / 步数 | 26 s / 13,000 |
| 时序记录 | 2,600 行，100 Hz |
| 名义手部圆弧 / 实际最终门角 | 20° / 19.261095°，差约 0.739° |
| 最大机器人–门接触力范数之和 | 2.303406 N；各接触点力范数相加，不是单个力矢量的合力 |
| 接触对象 | 仅 front_handle_grip 与两只真实夹指 |
| 最大机器人–门软接触穿透 | 0.698329 mm |
| 最大臂关节力矩 | J2 10.589513 Nm；六轴均未超各自上限 |
| 最大夹爪执行器力 | 2.213421 N |
| 机器人自接触力 / MuJoCo 警告 | 无非零自接触力 / 全部警告计数 0 |
| 最大 IK 位置 / 姿态误差 | 1.993e-5 m / 8.387e-5 rad |

松爪后接触力归零，退离和最终保持阶段门角没有继续变化。成功初试与最终补录使用同一名义条件，最终补录调整了观察视角并增加记录字段；这不构成随机扰动或跨条件鲁棒性验证。有限的软接触穿透、源凸包近似与名义夹爪摩擦仍影响误差，不能据此预测真实夹持力或开门精度。

## 真实失败与修正

1. 最初 60° 规划在原站位/抓取朝向下不连续可达，最大位置误差约 0.260 m，未启动物理仿真。小规模其它站位/朝向的 IK 探索也未找到该完整路径；不能推断所有固定基座方案均不可行。
2. 缩短为 20° 后，原退离方向仍触及腕关节限位，最大位置误差约 0.0584 m。改为松爪后同时调整手部朝向再退离，规划通过，没有改关节限位。
3. 首次真实动力学在根 `[0.82,0.38,0.54266] m`、把手高 1.0 m 时只到 16.829°：门板碰 M1 机身并导致失夹，门板–机身单接触峰值约 16.408 N。保留 [失败汇总](../results/p4/trial_02_obstructed/summary.json)、[失败时序](../results/p4/trial_02_obstructed/timeseries.csv) 和桌面图。
4. 根后移 0.12 m，把手降低 0.15 m，保留全部碰撞；有效试验达到 19.261°，没有门板–底盘接触。没有通过关闭碰撞或直接设置门角制造结果。

## 实际命令与复跑

```bash
bash scripts/project_env.sh python scripts/p4_fixed_door.py --plan-only
bash scripts/project_env.sh python scripts/p4_fixed_door.py --live --video --output results/p4/pull_20deg
bash scripts/project_env.sh python scripts/plot_p4.py results/p4/pull_20deg
```

上面的正式输出目录已存在。下次复跑省略 `--output`，程序会用新的 UTC 时间目录保留结果：

```bash
bash scripts/project_env.sh python scripts/p4_fixed_door.py --live --video
```

本机仅新增 `.venv` 内的 Matplotlib 3.10.9 用于时序图，依赖范围已记录在 requirements.txt。代码编译检查、两个 MJCF 的维度/自由根复核，以及 650 帧视频完整解码均通过。

以上复跑与26秒数据属于早期19°节点。当时下一步是扩大P4开角并进入P5；这两项已有本报告上方和P5报告的后续证据。当前下一步是 [P6连续自由基座单门](../docs/P6_SINGLE_DOOR_PLAN.md)。2026-11-20的 [基线复核](P6_NEXT_STAGE_REVIEW_20261120.md) 进一步区分了背推门角达标与非预期接触、前拉缺失的门框字段，以及阶段时间结束与任务成功的差别；没有改写旧实验结果。
