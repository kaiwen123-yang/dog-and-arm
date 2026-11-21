# P6 自由轮足底盘单门试验

> **当前有效基线（2026-11-21）：** `rail_bridge_front60_v2`、冻结控制 `86ade86`，前拉 60°与背推 25°各 20/20（背推名义底盘航向 95°），通过依据见本文末尾“2026-11-21 前移安装的最终双侧清单”及[最终逐案表](../results/p6/rail_bridge_front60_v2_20261120T133724Z/conditions.csv)。此前各节是分版本历史，不能混合统计。下一步研究入口已改为 [B0 官方方法迁移](../docs/B0_SUPERMIMIC_PLAN.md)，没有因为本次规划新增实验结果。

历史 `rail_bridge_v1` 双导轨安装座的名义前拉整任务已完成，最终门角 60.048936°，其结果在后文单列。A–D、mobile_01、旧版两轮 20 案例和旧版背推使用方块安装座，不归入当前 front60_v2 清单。[安装座版本决定](../docs/MOUNT_RAIL_BRIDGE.md)

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

## C　0.30 m 驶近、抓门和底盘退离

`bash scripts/project_env.sh python scripts/p6_single_door.py mobile --live --video --hold-final --output results/p6/mobile_01`。独立桌面试验用一个自由基座从后方 0.30 m 处出发。41,081 个 2 ms 步共 82.162 s，实测实时比 1.000。13 个阶段全部完成，script_completed 与 task_success 均为 true。右上角的近景从这一轮开始随门扇转动。

| 事件 | 物理时刻 | 实测 |
| --- | ---: | --- |
| 到站并连续停稳 1 s | 7.042 s | XY [0.64836, 0.29841] m，距名义站位 2.29 mm |
| 双指握持持续确认 0.2 s | 17.544 s | 双指接触门前竖杆，门 0.064° |
| 拉门、稳定握持后开始释放 | 60.254 s | 门 59.833° |
| 退臂后在操作位保持满 3 s | 68.054 s | 已松爪，与门无接触，门 60.055° |
| 收臂、倒车、终点连续停车满 3 s | 82.162 s | XY [0.43950, 0.09009] m，距停车目标 2.77 mm；门 60.055003° |

抓持几何偏移峰值 2.575 mm、操作漂移 0.950 mm、整轮最大倾角 0.191°。门对整机合力峰值 2.614 N，无非预期接触、饱和或求解警告。底盘退离约 0.295 m（收臂结束至最终停车两点的平面距离）。此轮冻结为条件试验 C01。横向/纵向滑速、四轮实际载荷、指力和实际执行器输出见同目录 CSV。

[状态与阶段证据](../results/p6/mobile_01/summary.json) · [全程实时画面](../results/p6/mobile_01/motion.mp4) · [事件对齐图](../results/p6/mobile_01/signals.png)

## D　冻结初版的 20 条条件对照

C01 使用上面的名义整任务。其余条件用 `bash scripts/project_env.sh python scripts/p6_cases.py CASES --output DIRECTORY` 原生桌面分格并列显示。分别运行 2–6（conditions_A）、7–12（B）、13–17（C）、18–20（D）。每格实时接收独立物理进程的状态，桌面用只渲染的状态副本绘图，物理进程各自只有一个积分实例。每条的 500 Hz 峰值、事件、5 Hz 摘录及实际接触对摩擦见对应 Cxx 子目录，25 Hz 详细记录保留在本机 results/raw_large/p6/ 下。

[完整结果表](../results/p6/conditions_v1.csv)。10/20 完成。C02–C07、C18–C20 在 32 s 驶近时限内未满足到站条件，均未抓门。C02 在末时还距目标 79.4 mm，早期未对准就开始向前，转向修正达上限后不能及时沿新方向收敛。C14 门开至 60.235°，退爪碰门板，接触点力 0.732 N。其余通过项包括门初角 2°/5°、轮地或指杆摩擦 0.8/1.2 倍和高/低铰链阻尼。实际 wheel_ground 与 finger_handle 接触对记录验证了各自倍率已生效。下一步复查驶近纠偏并增加前拉退臂净空，再按相同的20条清单重跑。此轮未达到 18/20 工程门槛。

## D　驶近和退爪修正

对 C02、C06、C18、C20 单独运行 `bash scripts/project_env.sh python scripts/p6_cases.py 2 6 18 20 --arrival-only --output results/p6/arrival_02`。同案例此前的 arrival_01 提高差速后在 1.59–3.73 s 触发髋部持续饱和，原因与实际输出一起保留。arrival_02 将行驶差速指令限至 0.36 rad/s，在前后轮接地点用腿的局部雅可比生成小幅反向侧摆关节参考以辅助偏航。转向姿态补偿限为 ±16°，实际只能通过 12 个腿部位置执行器改变腿姿。底盘先定向、再滚动，到达后对准操作航向。力矩、倾角、四轮承重和停车门槛保持首次声明值。

| 案例 | 连续停稳 1 s 的时刻 | 操作位 XY 误差 | 偏航误差 |
| --- | ---: | ---: | ---: |
| C02 | 9.500 s | 1.17 mm | +0.745° |
| C06 | 7.580 s | 2.35 mm | −0.797° |
| C18 | 8.360 s | 0.56 mm | +0.763° |
| C20 | 8.168 s | 0.58 mm | −0.758° |

四个到站诊断均无输出饱和。未在这些短诊断中伸臂，task_success 仍为 false。[初次饱和记录](../results/p6/arrival_01/) · [改动后的到站数据](../results/p6/arrival_02/)。

C14 原失败状态对应夹爪基座碰门板。用其实际根姿态、60.235° 门角进行独立运动学筛查，原路径出现约 0.29 mm 穿透；仅将前侧释放后的回撤平移改为世界 −X，维持 0.10 m 回撤、0.04 m 抬升和原腕姿，退臂/折臂/回转各 101 个采样的最小净空约 8.78 mm。后续以真实步进确定通过情况。

### 六个整任务的停车复核

用 recheck_A 先复跑 C01、C02、C06、C14、C18、C20。C14 在世界 −X 回撤路线下完整通过，最终 60.242°。C06 释放后停车超时，C02/C18 倒车终点停车超时。检查显示约 0.3° 的偏航误差会触发频繁制动/再纠偏，物理步速度打断 3 s 合格窗口。六份独立物理数据均已落盘；这组中间复查的桌面父进程返回 143，留存的视频只覆盖至约 50 s。通过独立原始日志补导出六份摘要，后续重新全程运行。

保留 5 mm/s、0.5°/s、连续 3 s 的验收条件，将驻停航向纠偏设为 1.10° 触发、0.55° 制动；沿车头方向的位置纠偏设为 4.0 mm 触发、1.8 mm 制动。偏移再次超过触发阈值会重新纠偏。按相同六个条件在 final_A 桌面复跑，全部通过，两段连续 3 s 都完成。门最终分别为 60.060°、60.065°、60.056°、60.242°、60.059°、60.113°。采用分格显示时按各格物理时钟读数；早期分格视频是抽帧短片。

[停车修正前](../results/p6/recheck_A/) · [相同六例修正后](../results/p6/final_A/)。

## D　最终固定清单

保持同一控制参数与门槛，实际运行以下桌面组。每个案例均用自己的单一连续物理状态完成全套任务。20/20 的 task_success 为 true。与首次的 10/20 相比，已修复初态偏移时的到站、退爪碰板和连续停车问题。

| 输出目录 | C 编号 | 用途 |
| --- | --- | --- |
| final_A | 01、02、06、14、18、20 | 名义、初始偏差、低铰链摩擦、组合条件 |
| final_B | 03、04、05、07、19 | 反方向初始偏差与组合条件 |
| final_C | 08、09、10、11、12、13 | 门初角、实际轮地与指杆摩擦 |
| final_D | 15、16、17 | 高铰链摩擦、低/高阻尼 |

命令均为 `bash scripts/project_env.sh python scripts/p6_cases.py <编号列表> --output results/p6/<输出目录>`，编号参数使用十进制整数。逐案复核原始 25 Hz 时序、物理步数、13 项事件顺序、双指持续确认、释放后与退车后两段完整停车窗口，以及每步汇总的接触/几何门槛。

最终门角 59.9698°–60.2421°。20 例中抓持点对把手的平移偏差峰值 3.133 mm，操作站位平面漂移峰值 2.912 mm，门对整机合力峰值 4.035 N，横滚/俯仰绝对值峰值 0.2433°。C13 指杆滑动摩擦系数为 1.2，开门段耗时 54.898 s，距 55 s 时限余 0.102 s。这个范围只覆盖计划中的仿真工况。原始固定清单及失败记录保留。

[逐案最终结果](../results/p6/conditions_final.csv) · [初版对照](../results/p6/conditions_v1.csv) · [初态变化实时分格](../results/p6/final_B/live_grid.mp4) · [摩擦变化实时分格](../results/p6/final_C/live_grid.mp4)。

## 背侧 25° 整任务，旧方块安装座

桌面运行 `bash scripts/project_env.sh python scripts/p6_single_door.py push --live --video --hold-final`，两次各用新输出目录。push_01 的 165° 水平入抓在约 4.25° 后回落，两指仍接触，抓持几何偏差超过 5 mm，试验以 3.090° 停止；保留该失败。第二次采用 120° 斜入、绕局部闭合轴俯仰 +20°，随门角增加一半偏航。独立 scratch 用实际沉降姿态对预抓、推门、退离与收臂离散检查，再在桌面启动新的物理试验。

push_02 完整驶近和停车，从门背侧双指夹持并推开至 25.055163°，松爪退臂、保持、收臂、倒车并再停车。54.200 s / 27,100 步，最大抓持几何偏移 2.568 mm，操作漂移 0.913 mm，门对机器人合力峰值 2.100 N。两指只接触目标背侧竖杆，意外接触为空；全过程无求解警告，两段 3 s 合格窗口均通过。本次只验证了背推名义工况。

[成功样本及事件](../results/p6/push_02/summary.json) · [全程视频](../results/p6/push_02/motion.mp4) · [时序图](../results/p6/push_02/signals.png) · [首次失败](../results/p6/push_01/summary.json)。

## 双导轨安装座的名义连续前拉

`rail_bridge_v1_mobile_01` 使用更新的组合模型和原站位 [0.65, 0.30] m、45°。控制参数、接触条件、停车标准沿用最终版前拉。Linux 桌面实际运行以下命令，起点在站位后 0.30 m。

```bash
bash scripts/project_env.sh python scripts/p6_single_door.py mobile --live --video --hold-final --output results/p6/rail_bridge_v1_mobile_01
```

每次复跑可省略 `--output`，自动保存新目录。安装版本和实际臂根位置已记入 config.json。在同一物理状态下，机器人驶近并停车、伸臂抓住前把手、拉门、松爪退臂、保持、收臂、倒车并再次停稳。13 个阶段通过，82.474 s 共 41,237 个 2 ms 物理步，桌面视频 2,062 帧已全程解码。[全程视频](../results/p6/rail_bridge_v1_mobile_01/motion.mp4) · [物理事件与门槛](../results/p6/rail_bridge_v1_mobile_01/summary.json)

| 实际事件或观测 | 新安装座名义结果 |
| --- | --- |
| 驶近停车持续 1 s 时 | 根高 0.53516 m，四轮 107.0 / 108.0 / 105.1 / 108.5 N |
| 松爪及退离 | 62.048 s 松爪阶段结束，终点门角 60.048936° |
| 两段独立停车 | 退臂后、倒车后各连续 3 s，均在门角和速度范围内 |
| 操作站位及抓持 | 最大平面漂移 0.949 mm，最大抓持偏移 2.670 mm |
| 受力与倾角 | 门对机器人合力峰值 2.840 N，整轮横滚/俯仰绝对值最大 0.188° |
| 接触与执行器 | 机器人与门仅两指接触前侧竖杆，意外接触和求解警告均为零，各通道连续饱和时间为零 |

新臂根降低 85.5 mm。在 25 Hz 实际关节时序中，松爪段 60.80 s 时 J5 为 −1.5596143 rad，距模型下限 −1.5620696 rad 仅 **0.141°**。后续针对同一安装版本复查条件变化时，要同时跟踪这个余量。当前新座证据覆盖一个名义前拉。桌面终态保留界面的重复文字已修正，通过本次保存的最终姿态重新显示并截图。[关节与受力时序](../results/p6/rail_bridge_v1_mobile_01/timeseries.csv) · [接触明细](../results/p6/rail_bridge_v1_mobile_01/contacts.csv) · [时序图](../results/p6/rail_bridge_v1_mobile_01/signals.png) · [保存终态的桌面视图](../results/p6/rail_bridge_v1_mobile_01/desktop.png)

## 安装整体前移 60 mm：准备完成，动力学复测待执行

2026-11-20 用户要求安装板向狗头靠近，并重做完整推拉。当前 `rail_bridge_front60_v2` 把板、支座、臂同步沿机身 +X 移动 60 mm，臂根 [0.110,0,0.0945] m；完整模型/运动学离线记录见 [连接件说明](../docs/MOUNT_RAIL_BRIDGE.md)。本次没有 GUI 或 mj_step，既有 v1 成绩仍属于 v1。

为避免把前移模型误记为 v1，P6 改从编译模型 custom text 读取安装版本；summary/config 均记录实际臂根坐标。新增六轴每物理步的带符号最小关节限位余量及发生时间、阶段，字段 `arm_joint_limit_min`；25 Hz 时序与条件精简 trace 也保留六轴角及余量。未更改控制、目标、碰撞或任务门槛。

分格入口新增 `--stage mobile|push`，单次 `push --case N` 也可使用原 C01–C20 扰动。静态加载前拉/背推各 20 份配置确认目标分别为 60°/25°；两侧名义派生场景编译成功。背推 20 条是新增待运行覆盖，不是已有结果。下一轮先桌面核对装配，名义推拉及 C13，再统一版本完成两侧条件清单，重点检查 J5 余量、开门耗时、松爪/收臂净空和两次停车窗口。[执行提示](../prompts/MOUNT_FORWARD_PUSH_PULL.txt)

## 前移 60 mm 的本机复测

已完成当前安装的桌面预览与重载。动力学从原控制参数的名义前拉开始。每个 2 ms 步的实际六轴限位余量另存本机 CSV，摘要保留各轴最小值及发生的时刻和阶段。退臂、释放后保持、收臂、倒车和终点的机门碰撞面净空在 25 Hz 观测点计算，所有参与碰撞的机器人和门几何均纳入。

### baseline_mobile_C01

前拉 C01，unexpected_contact:robot_panel。终态 61.18086°，29,951 步。开门段 39.472 s。六轴最小余量依次为 0.931° / 39.099° / 37.424° / 44.082° / -0.081° / 95.632°。J5 最小值发生在 52.210 s（open）。两段停车分别为 未完成、未完成。59.900 s 的接触点落在夹爪基座与门板之间。

实际命令为 `bash scripts/project_env.sh python scripts/p6_single_door.py mobile --case 1 --live --video --hold-final --output results/p6/rail_bridge_front60_v2_20261120T133724Z/baseline_mobile_C01`。每步六轴原表与 25 Hz 接触/状态留在本机 `results/raw_large/p6/rail_bridge_front60_v2_20261120T133724Z/baseline_mobile_C01/`。核对物理步数、六轴极小值和视频解码帧数。[运行证据](../results/p6/rail_bridge_front60_v2_20261120T133724Z/baseline_mobile_C01/)

### station_mobile_C01

前拉 C01，流程完成。终态 60.04388°，40,824 步。开门段 41.554 s。六轴最小余量依次为 3.704° / 31.250° / 34.144° / 45.862° / 1.752° / 98.056°。J5 最小值发生在 60.038 s（release）。两段停车分别为 3.0 s、3.0 s。前侧操作位 X 从 0.650 m 改为 0.600 m，Y 和腕姿保持。开门全段双指接触，退臂/收臂 25 Hz 最小机门间距为 11.46/19.04 mm。

实际命令为 `bash scripts/project_env.sh python scripts/p6_single_door.py mobile --case 1 --live --video --hold-final --output results/p6/rail_bridge_front60_v2_20261120T133724Z/station_mobile_C01`。每步六轴原表与 25 Hz 接触/状态留在本机 `results/raw_large/p6/rail_bridge_front60_v2_20261120T133724Z/station_mobile_C01/`。核对物理步数、六轴极小值和视频解码帧数。[运行证据](../results/p6/rail_bridge_front60_v2_20261120T133724Z/station_mobile_C01/)

### station_push_C01

背推 C01，流程完成。终态 25.04485°，27,105 步。开门段 14.554 s。六轴最小余量依次为 48.101° / 45.764° / 36.596° / 26.883° / 23.211° / 74.411°。J5 最小值发生在 12.276 s（approach_arm）。两段停车分别为 3.0 s、3.0 s。背侧站位沿用原值。倒车时左后轮到左门柱的 25 Hz 最近距离仅 0.68 mm；本例没有非预期接触。

实际命令为 `bash scripts/project_env.sh python scripts/p6_single_door.py push --case 1 --live --video --hold-final --output results/p6/rail_bridge_front60_v2_20261120T133724Z/station_push_C01`。每步六轴原表与 25 Hz 接触/状态留在本机 `results/raw_large/p6/rail_bridge_front60_v2_20261120T133724Z/station_push_C01/`。核对物理步数、六轴极小值和视频解码帧数。[运行证据](../results/p6/rail_bridge_front60_v2_20261120T133724Z/station_push_C01/)

### station_mobile_C13

前拉 C13，timeout:open。终态 56.01962°，36,261 步。六轴最小余量依次为 9.323° / 31.250° / 34.144° / 46.766° / 2.674° / 107.105°。J5 最小值发生在 72.522 s（open）。两段停车分别为 未完成、未完成。指杆摩擦为 1.2 倍，55.002 s 开门阶段内始终保持双指接触，峰值合力 2.957 N。

实际命令为 `bash scripts/project_env.sh python scripts/p6_single_door.py mobile --case 13 --live --video --hold-final --output results/p6/rail_bridge_front60_v2_20261120T133724Z/station_mobile_C13`。每步六轴原表与 25 Hz 接触/状态留在本机 `results/raw_large/p6/rail_bridge_front60_v2_20261120T133724Z/station_mobile_C13/`。核对物理步数、六轴极小值和视频解码帧数。[运行证据](../results/p6/rail_bridge_front60_v2_20261120T133724Z/station_mobile_C13/)

### lead_mobile_C13

前拉 C13，流程完成。终态 60.05255°，37,753 步。开门段 35.382 s。六轴最小余量依次为 3.709° / 31.250° / 34.144° / 45.849° / 1.752° / 98.053°。J5 最小值发生在 53.850 s（release）。两段停车分别为 3.0 s、3.0 s。前侧跟随领先上限调整到 0.40°，55 s 时限仍有 19.618 s 余量。完整退臂采样净空 11.56 mm。

实际命令为 `bash scripts/project_env.sh python scripts/p6_single_door.py mobile --case 13 --live --video --hold-final --output results/p6/rail_bridge_front60_v2_20261120T133724Z/lead_mobile_C13`。每步六轴原表与 25 Hz 接触/状态留在本机 `results/raw_large/p6/rail_bridge_front60_v2_20261120T133724Z/lead_mobile_C13/`。核对物理步数、六轴极小值和视频解码帧数。[运行证据](../results/p6/rail_bridge_front60_v2_20261120T133724Z/lead_mobile_C13/)

背侧原站位的世界坐标起点筛查发现 C03、C20 在 home 与左门柱分别重叠 4.312/22.920 mm。背侧站位 X 外移 40 mm 至 1.92 m，静态初态重算，20 条中的最小净空为 6.753 mm（C20）。沿用 120° 入杆腕姿和 0.30° 领先量。[两站位各 20 个规定初态的距离](../results/p6/rail_bridge_front60_v2_20261120T133724Z/back_initial_clearance.csv)。

### post_push_C01

背推 C01，unexpected_contact:finger_non_grasp_handle。终态 0.00001°，5,341 步。六轴最小余量依次为 64.816° / 45.764° / 48.523° / 48.534° / 39.950° / 109.250°。J5 最小值发生在 10.682 s（pregrasp）。两段停车分别为 未完成、未完成。预抓取 10.680 s 处，第二夹指碰到背把手上支杆，接触力范数 3.514 N。

实际命令为 `bash scripts/project_env.sh python scripts/p6_single_door.py push --case 1 --live --video --hold-final --output results/p6/rail_bridge_front60_v2_20261120T133724Z/post_push_C01`。每步六轴原表与 25 Hz 接触/状态留在本机 `results/raw_large/p6/rail_bridge_front60_v2_20261120T133724Z/post_push_C01/`。核对物理步数、六轴极小值和视频解码帧数。[运行证据](../results/p6/rail_bridge_front60_v2_20261120T133724Z/post_push_C01/)

### lead_mobile_C01

前拉 C01，流程完成。终态 60.05158°，37,138 步。开门段 34.190 s。六轴最小余量依次为 3.707° / 31.250° / 34.144° / 45.862° / 1.748° / 98.065°。J5 最小值发生在 52.650 s（release）。两段停车分别为 3.0 s、3.0 s。使用与 C13 相同的 0.40° 上限。退臂/收臂采样净空分别为 11.53/18.93 mm。

实际命令为 `bash scripts/project_env.sh python scripts/p6_single_door.py mobile --case 1 --live --video --hold-final --output results/p6/rail_bridge_front60_v2_20261120T133724Z/lead_mobile_C01`。每步六轴原表与 25 Hz 接触/状态留在本机 `results/raw_large/p6/rail_bridge_front60_v2_20261120T133724Z/lead_mobile_C01/`。核对物理步数、六轴极小值和视频解码帧数。[运行证据](../results/p6/rail_bridge_front60_v2_20261120T133724Z/lead_mobile_C01/)

### clear_push_C01

背推 C01，流程完成。终态 25.08521°，27,125 步。开门段 14.568 s。六轴最小余量依次为 41.678° / 36.500° / 27.775° / 12.182° / 21.303° / 53.171°。J5 最小值发生在 12.260 s（approach_arm）。两段停车分别为 3.0 s、3.0 s。背侧 X=1.935 m，预抓取距离 105 mm、入杆腕偏航 125°、终态腕偏航 137.5°。退臂/收臂/倒车实测采样净空依次 16.99/38.49/55.68 mm。

实际命令为 `bash scripts/project_env.sh python scripts/p6_single_door.py push --case 1 --live --video --hold-final --output results/p6/rail_bridge_front60_v2_20261120T133724Z/clear_push_C01`。每步六轴原表与 25 Hz 接触/状态留在本机 `results/raw_large/p6/rail_bridge_front60_v2_20261120T133724Z/clear_push_C01/`。核对物理步数、六轴极小值和视频解码帧数。[运行证据](../results/p6/rail_bridge_front60_v2_20261120T133724Z/clear_push_C01/)

上述背侧站位在 C01–C20 初态的最小机门间距为 21.695 mm。预抓取路径的运动学筛查取初始门角 0/2/5° 和到站航向误差 ±1°，展开取 65 点，局部 IK 筛查不列入任务成绩。后续用同一实际控制版本分组复测。[初态距离](../results/p6/rail_bridge_front60_v2_20261120T133724Z/back_deployment_initial_clearance.csv) · [路径筛查](../results/p6/rail_bridge_front60_v2_20261120T133724Z/back_deployment_ik.csv)。

**mobile_A**　前拉 C02、C03、C04、C05、C06、C07，逐案审核 6/6 通过。本组 J5 最小余量 1.577°。桌面分格视频已解码 607 帧。 使用 `bash scripts/project_env.sh python scripts/p6_cases.py 2 3 4 5 6 7 --stage mobile --output results/p6/rail_bridge_front60_v2_20261120T133724Z/mobile_A`。已核对六轴每步极小值，成功案例的两段停车再用 25 Hz 速度/接触时序复核。[各案摘要与分格视频](../results/p6/rail_bridge_front60_v2_20261120T133724Z/mobile_A/)

**mobile_B**　前拉 C08、C09、C10、C11、C12、C14，逐案审核 6/6 通过。本组 J5 最小余量 1.744°。桌面分格视频已解码 596 帧。 使用 `bash scripts/project_env.sh python scripts/p6_cases.py 8 9 10 11 12 14 --stage mobile --output results/p6/rail_bridge_front60_v2_20261120T133724Z/mobile_B`。已核对六轴每步极小值，成功案例的两段停车再用 25 Hz 速度/接触时序复核。[各案摘要与分格视频](../results/p6/rail_bridge_front60_v2_20261120T133724Z/mobile_B/)

**mobile_C · 用户暂停**　实际执行 `bash scripts/project_env.sh python scripts/p6_cases.py 15 16 17 18 19 20 --stage mobile --output results/p6/rail_bridge_front60_v2_20261120T133724Z/mobile_C`。收到暂停指示后正常关闭分格窗口，六条均在开门阶段 47.562 s 中断，原始字段为 `window_closed`。已保存摘要、每步关节表与 382 帧分格录像。本组不参加完整任务成绩统计。冻结版本当前完成前拉 C01–C14 和背推 C01。[中断记录](../results/p6/rail_bridge_front60_v2_20261120T133724Z/mobile_C/)

**2026-11-21 · mobile_C_resumed**　前拉 C15–C20 完整任务通过 6/6。本组 J5 最小余量 1.473°。 按每个 2 ms 物理步复核六轴最小余量与对应时刻，并核对完整案例的两个 3 s 停车窗口。分格录像完整解码 607 帧。实际命令为 `bash scripts/project_env.sh python scripts/p6_cases.py 15 16 17 18 19 20 --stage mobile --output results/p6/rail_bridge_front60_v2_20261120T133724Z/mobile_C_resumed`。[本组轨迹与录像](../results/p6/rail_bridge_front60_v2_20261120T133724Z/mobile_C_resumed/)

**2026-11-21 · push_A**　背推 C02–C06 完整任务通过 5/5。本组 J5 最小余量 20.396°。 按每个 2 ms 物理步复核六轴最小余量与对应时刻，并核对完整案例的两个 3 s 停车窗口。分格录像完整解码 467 帧。实际命令为 `bash scripts/project_env.sh python scripts/p6_cases.py 2 3 4 5 6 --stage push --output results/p6/rail_bridge_front60_v2_20261120T133724Z/push_A`。[本组轨迹与录像](../results/p6/rail_bridge_front60_v2_20261120T133724Z/push_A/)

**2026-11-21 · push_B**　背推 C07–C11 完整任务通过 5/5。本组 J5 最小余量 20.990°。 按每个 2 ms 物理步复核六轴最小余量与对应时刻，并核对完整案例的两个 3 s 停车窗口。分格录像完整解码 444 帧。实际命令为 `bash scripts/project_env.sh python scripts/p6_cases.py 7 8 9 10 11 --stage push --output results/p6/rail_bridge_front60_v2_20261120T133724Z/push_B`。[本组轨迹与录像](../results/p6/rail_bridge_front60_v2_20261120T133724Z/push_B/)

**2026-11-21 · push_C**　背推 C12–C16 完整任务通过 5/5。本组 J5 最小余量 21.303°。 按每个 2 ms 物理步复核六轴最小余量与对应时刻，并核对完整案例的两个 3 s 停车窗口。分格录像完整解码 436 帧。实际命令为 `bash scripts/project_env.sh python scripts/p6_cases.py 12 13 14 15 16 --stage push --output results/p6/rail_bridge_front60_v2_20261120T133724Z/push_C`。[本组轨迹与录像](../results/p6/rail_bridge_front60_v2_20261120T133724Z/push_C/)

**2026-11-21 · push_D**　背推 C17–C20 完整任务通过 3/4。本组 J5 最小余量 20.269°。失败记录为 C20 unexpected_contact:robot_frame|warning_or_contact。 按每个 2 ms 物理步复核六轴最小余量与对应时刻，并核对完整案例的两个 3 s 停车窗口。分格录像完整解码 459 帧。实际命令为 `bash scripts/project_env.sh python scripts/p6_cases.py 17 18 19 20 --stage push --output results/p6/rail_bridge_front60_v2_20261120T133724Z/push_D`。[本组轨迹与录像](../results/p6/rail_bridge_front60_v2_20261120T133724Z/push_D/)

### 90° 背侧航向的完整对照

控制 7e3c5e0 的 40 个完整试验均已执行，前拉 20/20、背推 19/20。背推 C20 起点与左门柱有 21.695 mm 净空，在 1.640 s 采样时左后轮已与左门柱重叠约 0.0065 mm，1.642 s 收到终止，接触点力范数 18.495 N。其余 39 例完成 13 个阶段并通过限位及停车复核。 按 25 Hz 的实际位姿复核驶近至首次停稳的碰撞面距离，C03 最近为 18.157 mm。继续在同一站位把背侧名义底盘航向从 90° 调至 95°，使驶近时左后轮远离左门柱。初始世界坐标扰动、控制门槛、臂和门的物理参数均沿用。统计按背侧航向分列。[40 条配置与结果](../results/p6/rail_bridge_front60_v2_20261120T133724Z/conditions_90deg.csv) · [背侧驶近门框距离](../results/p6/rail_bridge_front60_v2_20261120T133724Z/back_approach_frame_90deg.csv) · [C20 失败原始摘要](../results/p6/rail_bridge_front60_v2_20261120T133724Z/push_D/C20/summary.json)

**2026-11-21 · push95_A**　背推 C01、C02、C03、C07、C18、C20 完整任务通过 6/6。本组 J5 最小余量 20.081°。 按每个 2 ms 物理步复核六轴最小余量与对应时刻，并核对完整案例的两个 3 s 停车窗口。分格录像完整解码 462 帧。实际命令为 `bash scripts/project_env.sh python scripts/p6_cases.py 1 2 3 7 18 20 --stage push --output results/p6/rail_bridge_front60_v2_20261120T133724Z/push95_A`。[本组轨迹与录像](../results/p6/rail_bridge_front60_v2_20261120T133724Z/push95_A/)

**2026-11-21 · push95_B**　背推 C04、C05、C06、C08、C09、C10 完整任务通过 6/6。本组 J5 最小余量 20.042°。 按每个 2 ms 物理步复核六轴最小余量与对应时刻，并核对完整案例的两个 3 s 停车窗口。分格录像完整解码 442 帧。实际命令为 `bash scripts/project_env.sh python scripts/p6_cases.py 4 5 6 8 9 10 --stage push --output results/p6/rail_bridge_front60_v2_20261120T133724Z/push95_B`。[本组轨迹与录像](../results/p6/rail_bridge_front60_v2_20261120T133724Z/push95_B/)

**2026-11-21 · push95_C**　背推 C11–C16 完整任务通过 6/6。本组 J5 最小余量 20.367°。 按每个 2 ms 物理步复核六轴最小余量与对应时刻，并核对完整案例的两个 3 s 停车窗口。分格录像完整解码 435 帧。实际命令为 `bash scripts/project_env.sh python scripts/p6_cases.py 11 12 13 14 15 16 --stage push --output results/p6/rail_bridge_front60_v2_20261120T133724Z/push95_C`。[本组轨迹与录像](../results/p6/rail_bridge_front60_v2_20261120T133724Z/push95_C/)

**2026-11-21 · push95_D**　背推 C17、C19 完整任务通过 2/2。本组 J5 最小余量 20.042°。 按每个 2 ms 物理步复核六轴最小余量与对应时刻，并核对完整案例的两个 3 s 停车窗口。分格录像完整解码 437 帧。实际命令为 `bash scripts/project_env.sh python scripts/p6_cases.py 17 19 --stage push --output results/p6/rail_bridge_front60_v2_20261120T133724Z/push95_D`。[本组轨迹与录像](../results/p6/rail_bridge_front60_v2_20261120T133724Z/push95_D/)

## 2026-11-21　前移安装的最终双侧清单

冻结控制 `86ade86`、`rail_bridge_front60_v2` 安装的同版固定清单已在 Linux 桌面全部执行。前拉 20/20、背推 20/20 通过。前侧世界站位 [0.600, 0.300] m、45°、角度领先上限 0.40°；背侧 [1.935, 0.000] m、95°、预抓取距离 105 mm、腕部入杆/退离偏航 125°/137.5°、领先上限 0.30°。先补齐原 90° 背侧航向的 25 例，得到前拉 20/20、背推 19/20；随后仅将背侧名义航向增大 5°，重新实际运行背推 C01–C20。起点按操作位沿车尾方向取 0.30 m，航向调整也把 C20 的初始 XY 从 [1.8850, −0.3000] m 改为 [1.9111, −0.2989] m；两版均叠加原定义的世界坐标扰动。前拉 20 份记录的有效配置与最终版本逐项一致，沿用其原始动力学数据。每侧分别比对实际生效的完整控制配置与预定世界坐标扰动。机器人自由根、无执行器的单扇门与初始 0.30 m 驶近均贯穿各案例。

| 指标 | 前拉，目标 60° | 背推，目标 25° |
| --- | ---: | ---: |
| 完整通过 / 预定条件 | 20 / 20 | 20 / 20 |
| 终态门角（°） | 59.963–60.224 | 25.043–25.089 |
| 开门段用时（s） | 31.394–35.382 | 11.766–14.586 |
| 全任务用时（s） | 71.480–75.758 | 51.436–57.646 |
| 开门段双指同时接触的最低占比 | 100.000% | 100.000% |
| 开门段指 1 / 指 2 最小法向力（N，25 Hz） | 2.467 / 1.748 | 2.522 / 2.420 |
| J1–J6 各轴全组最小余量（°，500 Hz） | 2.822 / 30.634 / 32.545 / 45.773 / 1.473 / 97.627 | 44.644 / 40.496 / 35.480 / 15.225 / 20.042 / 57.455 |
| 最小 J5 余量（°） | 1.473（C20） | 20.042（C05、C19 并列） |
| 退臂 / 收臂 / 倒车最近机门距离（mm，25 Hz） | 9.394（C14） / 16.431（C14） / 66.046（C07） | 15.155（C06） / 15.046（C06） / 16.252（C06） |
| 退臂后保持、倒车后停车各满 3 s | 20/20 | 20/20 |
| 上述两窗口各自的最大水平速度（mm/s，25 Hz） | 1.742 / 4.947 | 1.691 / 4.820 |
| 上述两窗口各自的最大偏航速率绝对值（°/s，25 Hz） | 0.277 / 0.364 | 0.248 / 0.430 |
| 最大抓持偏移 / 操作位漂移（mm） | 3.202 / 2.414 | 2.724 / 2.525 |
| 开门时四轮中最低法向载荷（N） | 75.14 | 69.91 |
| 抓取至松爪期间最大轮地切向滑速（m/s） | 0.0131 | 0.0131 |
| 门对机器人峰值合力（N）/ 最大倾角（°） | 3.499 / 0.249 | 1.789 / 0.292 |
| 最长连续执行器饱和（s） | 0.000 | 0.000 |

总计 1,290,099 个 2 ms 物理步，六轴有符号余量越界步数 0。各案的极小值和发生时刻均与原始 500 Hz 记录一致。出现非预期接触的案例数为 0，有原生求解器警告的案例数为 0。按原验收条件，终态门角允许偏离目标 ±2°，两次停车窗口分别要求连续 3 s、水平速度 <5 mm/s、偏航速率绝对值 <0.5°/s。用 25 Hz 详细时序另外复核了窗口内速度、门角及机门接触力。退臂、收臂、倒车的净空取所有实际参与碰撞的机器人和门几何对的 25 Hz 最小值。净空数值受 25 Hz 采样限制，接触门槛在每个 500 Hz 物理步评估。

背侧驶近和到站停稳的 25 Hz 已积分位姿中，整机碰撞面到两门柱及顶梁的最近距离为 **16.881 mm**，发生于 C06、7.800 s，几何对为 `m1_FBL_FOOT_LINK[geom45]` 与 `door_single_right_post`。该工况起点有 155.070 mm 净空。C20 在 90° 版本于 1.642 s 停于左后轮碰柱，接触力峰值 18.495 N；在 95° 版本驶近时全机器人到门框的最小采样距离（同一对几何）为 43.653 mm，并完成开门和两段停车。距离复核使用日志中的世界根位姿、各关节角、两指实际开口和被动门角。只在独立数据副本更新运动学，开门与停车成绩均取自原始连续动力学。

[40 条逐案清单](../results/p6/rail_bridge_front60_v2_20261120T133724Z/conditions.csv) · [逐步限位与停车复核](../results/p6/rail_bridge_front60_v2_20261120T133724Z/parking_audit.csv) · [20 条背侧驶近净空](../results/p6/rail_bridge_front60_v2_20261120T133724Z/back_approach_frame.csv) · [逐案时间、关节与净空图](../results/p6/rail_bridge_front60_v2_20261120T133724Z/condition_metrics.png)

前拉最紧的几项来自不同条件。C20 在 51.070 s 松爪时 J5 距下限 1.473°；C14 退臂时夹爪基座与门板最近 9.394 mm。C13 的开门时间最长，为 35.382 s，距 55 s 时限 19.618 s。C09 的终点停车窗口内最大采样水平速度为 4.947 mm/s，接近 5 mm/s 门槛。背推六轴中实际最紧的是 C06 的 J4，余量 15.225°。

可复算清单，以下命令在项目根目录执行。

```bash
runs=results/p6/rail_bridge_front60_v2_20261120T133724Z
bash scripts/project_env.sh python scripts/p6_condition_report.py --output "$runs/conditions.csv" "$runs/lead_mobile_C01" "$runs/lead_mobile_C13" "$runs"/{mobile_A,mobile_B,mobile_C_resumed,push95_A,push95_B,push95_C,push95_D}/C*
raw=results/raw_large/p6/rail_bridge_front60_v2_20261120T133724Z
bash scripts/project_env.sh python scripts/p6_physics_audit.py "$runs/conditions.csv" "$raw" --output "$runs/parking_audit.csv"
bash scripts/project_env.sh python scripts/p6_approach_clearance.py "$raw"/push95_{A,B,C,D}/C* --output "$runs/back_approach_frame.csv"
```

上文保留早期前拉碰板、C13 超时、背推展开碰上支杆的失败尝试、90° 背侧 C20 左后轮碰门柱及 11 月 20 日主动中断的 mobile_C。各旧安装座成果沿用原目录和统计。[原 90° 背侧航向的全清单](../results/p6/rail_bridge_front60_v2_20261120T133724Z/conditions_90deg.csv) · [90° 背侧驶近距离](../results/p6/rail_bridge_front60_v2_20261120T133724Z/back_approach_frame_90deg.csv)。[冻结版前拉名义视频](../results/p6/rail_bridge_front60_v2_20261120T133724Z/lead_mobile_C01/motion.mp4) · [95° 背推含 C01、C20 的分格视频](../results/p6/rail_bridge_front60_v2_20261120T133724Z/push95_A/live_grid.mp4) · [前拉 C13 视频](../results/p6/rail_bridge_front60_v2_20261120T133724Z/lead_mobile_C13/motion.mp4)

