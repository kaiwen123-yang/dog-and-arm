# P6 自由轮足底盘单门试验

## A　操作站位承重与伸臂

在 Linux 桌面 X11 :1 运行下列命令。主画面显示全机和单门，右上角追踪把手。桌面截取的是 16.72 s 时的空走动作。Space 暂停物理，Esc 关闭窗口。结果落盘后保持画面，停留时间不计入物理试验。

```bash
bash scripts/project_env.sh python scripts/p6_single_door.py support --live --video --hold-final --output results/p6/support_01
```

单个物理实例从 home 出发，以 2 ms 步长走完 12,660 步（25.32 s）。在 [0.65, 0.30] m、45°处自然沉降。首次持续停稳 1 s 时，根高 0.533838 m，四轮分别承重 107.2、109.3、106.7、108.4 N。在关门前伸臂、沿前拉工作区的空中弧线往返，门角全程 0°。操作阶段平面漂移峰值 0.82 mm，整轮横滚/俯仰最大绝对值 0.176°。扫弧时四轮各自最小法向力 107.0、94.1、105.7、90.4 N。末端对中间参考的位置误差峰值 16.50 mm，扫弧结束后回到预抓位并连续停稳 3 s。

[汇总及阶段事件](../results/p6/support_01/summary.json) · [桌面实拍](../results/p6/support_01/desktop.png) · [同窗视频](../results/p6/support_01/motion.mp4)

## 控制与测量

- 场景从组合预览和单扇门组件生成，保留一个自由根、一张地面、双指耦合和被动门铰。动力学循环每步合并腿 12、轮 4、臂 6、爪 1 路控制。接近、驻停、操作、退离共用同一物理状态；每个独立试验只初始化一次。腕部附件沿用 omitted。
- 轮速按车体侧向轴和相对轮心分配。车体从原点移至操作站位并转 45° 后，0.07 m/s 前进对应四轮 +0.729167 rad/s，±0.10 rad/s 转向对应左右反号的 0.178125 rad/s。两站位的轮速差在 1.2e−16 rad/s 内，属于几何校验。
- 操作点位于夹爪主体局部 z=0.115 m。100 Hz IK 从当前物理状态复制实际根、腿、轮、门、夹指坐标到独立 scratch。物理门扇由接触驱动。25 Hz CSV 使用每个积分区间的起始时刻，控制输出与接触量取该步求解；峰值及持续时间按 500 Hz 统计。命令、每个执行器实际输出及限幅分别记录。
- contacts.csv 的点力和点力矩是世界系对 geom2 的作用。timeseries.csv 的 door_F 和 door_M_base 分别为门对机器人的合力及绕当步底盘原点的力矩，hand_F 仅含手端，door_norm_sum_N 为逐点力模之和。支撑力独立记录。正纵向为车头方向，正横向为车体左侧。
- 各次 config.json 固定实际站位、门参数、角度、判据和时限。结果区分 stage_pass（所选节点）、script_completed（阶段序列全部完成）、task_success（含驶近和退离的整任务）。最新阶段见下文；每次重跑请省略 --output 或提供新目录。

## B　操作站位前拉 15°

三次均从同一名义初态独立启动 `bash scripts/project_env.sh python scripts/p6_single_door.py small --live --video --hold-final`，依次指定新目录 small_01、small_02 和 small_03。碰撞模型和铰链参数保留，严格按持续接触/停稳条件转换阶段。

| 试验 | 抓取和求解条件 | 结果 |
| --- | --- | --- |
| [small_01](../results/p6/small_01/summary.json) | 闭爪指令 18 mm，角速率上限 2.6°/s，默认锥 | 保持双指接触，55 s 开门阶段超时；门角 3.401° |
| [small_02](../results/p6/small_02/summary.json) | 闭爪指令 10 mm，1.5 s 起步斜坡，速率上限 1.8°/s，默认锥 | 门角增至 7.839° 后超时。实际夹持开口约 21 mm |
| [small_03](../results/p6/small_03/summary.json) | 同一指令；椭圆锥，切向/法向阻抗比 10，Newton 容差 1e−10 | 14.957607°；释放、退臂和连续 3 s 门角/底盘稳定均通过 |

小角通过样本共 29.02 s，14,510 物理步。抓持几何偏移峰值 1.807 mm，操作漂移 0.496 mm，最大倾角 0.191°。开门阶段四轮最小载荷分别为 115.2、100.0、106.2、88.2 N；门对整机合力模全程峰值 2.405 N。无非预期接触、持续饱和或求解警告。开门时两指对竖杆的接触范数之和峰值 8.091 N，含方向相反的夹紧力。下一节点 60° 采用 6 N 合力诊断上限，约为此样本全程峰值的 2.5 倍，仅用于本仿真。

[小角时序图](../results/p6/small_03/signals.png) · [小角同窗视频](../results/p6/small_03/motion.mp4)。失败样本的配置、汇总和曲线随仓库保存，完整 CSV 和视频在本机 results/raw_large/p6/ 下对应目录。接触求解设置参考 [MuJoCo 3.3 模型说明](https://mujoco.readthedocs.io/en/3.3.0/modeling.html#solver-settings)。

## B　操作站位前拉 60°

桌面命令 `bash scripts/project_env.sh python scripts/p6_single_door.py pull --live --video --hold-final --output results/p6/pull_01`。同一自由根连续步进 61.982 s（30,991 步）。开门阶段 42.134 s 持续双指接触，实测末角 60.120818°。抓取点对实际把手的最大偏移 2.568 mm；全程门对机器人合力峰值 2.689 N，小于开跑前的 6 N。操作漂移 0.496 mm，最大倾角 0.191°；开门中四轮各自最小载荷 107.2、93.7、106.2、88.2 N。

松爪、退臂后持续稳定 3 s；结束时实际开口 90.0 mm，抓取点距把手 107.4 mm。无非预期接触、饱和或求解警告。此样本在操作站位起步；下一步接入短程行驶。

[事件与汇总](../results/p6/pull_01/summary.json) · [同时序曲线](../results/p6/pull_01/signals.png) · [57.84° 的桌面截图](../results/p6/pull_01/desktop.png) · [运行视频](../results/p6/pull_01/motion.mp4)
