# 腿臂协同控制项目逐日工作日志

本文件是项目唯一的持续追加工作日志，用来回答：哪一天做了什么、为什么改、实际解决了什么、哪些仍未解决、证据在哪里，以及下一次从哪里继续。按北京时间（`Asia/Shanghai`，UTC+08:00）记日；不要为每一天另建日志文件。

## 记录范围与时间口径

- 首次建立：2026-11-21。本次回填的 Git 历史基线为 `origin/main` 的 `8c53e5a116839021866c64ff87a17d00c0be7e9c`；首个提交为 `2ce7916a5beda814cd06bb13986035d0fd9766a6`。本文件建立以前的条目均标为“历史回填”。
- 回填依据是这个基线可达的提交、仓库已有报告、配置和结果索引。没有获得全部历史对话原文，没有据此补写聊天细节，也不把其他仓库的 G1 复现或邻接项目算成本项目工作。
- **提交时间是成果保存的时间，不是实验的开始或结束时间。** 下文“提交保存区间”只给出当天首末提交的北京时间。历史执行起止没有精确记录的，明确写“未恢复”；不按相邻提交的分钟差估算实验耗时。
- 报告直接标注的执行日期用于归属工作日；精确运行时间仍以对应 run 的日志、原始时间戳和实际步数为准。目录中的 `Z` 时间是 UTC；物理秒、视频时长、墙钟耗时与北京时间分别记录。
- 数值分开标明来源：实机接收数据、原生 MuJoCo 动力学、Warp 动力学、运动学检查、离线分析、规划。后来的复核只增加新条目，不把早期失败、暂停或未执行改写为当时已经成功。
- 2026-11-17、18、19 在上述 main 历史中没有提交，也没有本次可据以回填的独立逐日执行报告。因此不虚构这三天的工作；“无可追溯记录”不等于确认当天没有工作。以后如获得原始证据，按实际日期补入并注明补记日期。
- 本轮建立日志和编写后续计划属于文档工作。下文 11 月 21 日的历史训练是此前已执行的实验，不能计作本轮新启动的训练或硬件操作。

## 持续追加规则

1. 开始工作先在对应日期添加一个有明确任务名的条目，记目标、环境、起点版本和计划命令；结束或暂停后补实际结果。计划与实际执行分栏描述。
2. 同一天可以有多个任务条目。跨日任务每天各记当天实际发生的部分，互相引用上一日与下一日；记录进程是否持续、是否从 checkpoint 恢复、是否另开新物理回合。任务续做不等于同一个物理状态连续恢复。
3. 每个 run 使用新名字与新目录。保留失败、异常退出、用户暂停和未完成记录，不能用新结果覆盖旧结果，不能事后更改预定条件分母。
4. 问题按“现象—证据—原因状态—修改—复测”写。原因未证实时标“假设/待证”；完成代码修改而尚未运行时标“已改、未复测”。
5. 结果与版本绑定：源码提交及未提交 diff、配置、模型/安装版本、物理后端、seed、checkpoint、参考集、评测条件、采样频率和判据都要可定位。教师、学习策略、局部诊断、完整任务分别计数。
6. 大权重和原始数组不在 Git 时写真实保管位置、恢复依据与本次是否实际核验。报告记载文件存在，不等于本轮已经下载或重新验证该文件。
7. 完成有意义节点后由主任务普通提交、推送。提交前写“待提交”；推送成功后记录真实提交和远端结果，不预填“已推送”。本条目的提交可在下一次日志追加时补记，也可由 Git 历史追溯。
8. 下一日事项是当日收尾时的待办，不自动代表今天仍需执行。当前入口始终结合 [PROJECT_STATE.md](PROJECT_STATE.md) 与 [prompts/NEXT_RUN.txt](prompts/NEXT_RUN.txt) 判断。

## 日期索引

| 北京日期 | 当日主要工作 | 记录性质 |
| --- | --- | --- |
| 2026-11-15 | 初始化工程、官方来源与单/双被动门开工包 | 历史回填 |
| 2026-11-16 | H0 真机臂/相机联调；P0–P3 装配与本机可视检查 | 历史回填 |
| 2026-11-20 | P4、P5、P6 连续单门；连接板及前移；前移版测试后暂停 | 历史回填 |
| 2026-11-21 | 完成前移版推拉清单；B0 来源/数据/后端与 seed0 无接触学习 | 历史回填 |
| 2026-11-21 | 建立本日志、编写 B0 后续计划与启动提示词 | 本轮文档记录，未启动新训练 |
| 2026-11-22 | 接续核对计划与日志，完成发布准备 | 本轮跨日文档记录，未启动新训练 |

## 2026-11-15｜初始化与开工包（历史回填）

### 目标、时间与环境

- 目标：为 M1 四轮轮足与 Piper H 建立原生 MuJoCo 工程，先把来源、环境隔离、门组件和后续 P0–P3 入口准备清楚。
- 日期依据：[开工包准备验证](reports/KICKOFF_VALIDATION.md) 明确标注 2026-11-15；当天提交保存区间为 **20:53:20–20:54:49**。执行起止未恢复。
- 执行环境：准备侧独立 Linux、Python 3.12.14、MuJoCo 3.3.0，不是用户 Ubuntu 桌面，也没有操作真实机器人。
- 起止版本：初始化 `2ce7916`，开工包 `b7d1f88`。后续官方来源固定在 [sources.lock.json](config/sources.lock.json)；不能把后来的完整 vendor 下载写成当天已完成。

### 实际做了什么

1. 初始化目录、阶段计划、固定来源、生成/查看入口和隔离环境脚本。检查官方 M1 ZGWS MJCF、Piper H/夹爪描述与解析约定。
2. 实际执行目录初始化和门生成，产出 [单门组件](sim/components/door_single.xml)、[双门组件](sim/components/door_double.xml) 及对应预览场景。
3. 用 MuJoCo 3.3.0 编译门场景，在 0°、30°、60°、90°、110° 作静态几何采样；分别从静止积分 1,000 步，步长 2 ms，共 2 s。
4. 用 EGL 生成双门静态截图，确认门、框和两侧把手可见。此时没有机器人控制器或自动开门动作。

### 问题、原因与修复

| 现象 | 证据与原因状态 | 实际处理 | 复测与边界 |
| --- | --- | --- | --- |
| 只有零质量几何的空门框 body 触发自动质心计算错误 | 开工报告记录了实际编译错误；原因已定位到静态门框建模 | 将静态门框几何直接放进 worldbody，门扇保持显式惯性 | 两个门场景随后成功编译并完成静止步进；没有用虚构质量绕过问题 |
| 需要附件但暂不称重 | 用户确定的阶段边界，尚无真实质量/惯量 | 将名义附件的额外载荷列为 omitted，保留外形/碰撞/相机设计 | 不是实物载荷验证，也没有阻塞后续名义装配 |

### 命令、数据与结论

- 报告记录的实际入口：`scripts/init_workspace.py`、`scripts/build_doors.py`、`scripts/view_model.py` 静态截图模式；没有完整逐行 shell 历史的命令参数不在这里补造。
- 产物：[door_preparation_check.json](reports/door_preparation_check.json)、[双门截图](results/doors/double_closed.png)、[BUILD_PLAN.md](docs/BUILD_PLAN.md)、[MODEL_INTEGRATION.md](docs/MODEL_INTEGRATION.md)。
- 单门 `nq/nv=1/1`、无执行器/约束、门扇 12 kg；双门 `2/2`、无执行器/约束、两门扇合计 24 kg。以上质量为名义模型值。
- 静态角度采样直接设置 qpos，只证明几何；2 s 静止步进没有施力或机器人，不能称推拉门成功。
- 未完成：用户桌面验证、完整官方资产恢复、联合模型/FK、真实相机/硬件、固定基座接触与自由基座控制。
- 当日决定/接续：按 P0–P3 建立可维护的完整装配，不提前用门图片宣称机器人任务完成。首次后续有记录的工作日是 11 月 16 日。
- 提交：`2ce7916`、`b7d1f88`，完整保存时间见文末提交索引。本日志没有独立恢复当时的 push 日志，不据提交时间推断推送时间。

## 2026-11-16｜H0 联调与 P0–P3 装配（历史回填）

### 目标、时间与版本

- 目标：复用已验机的 Piper H 环境，完成 DC1 和机械臂联合采集；同时建立 M1/Piper/整机描述、腕部附件与可见调试入口。
- 日期依据：[H0 准备记录](reports/H0_PREPARATION.md)、[H0 实机报告](reports/H0_HARDWARE_REPORT.md)、[装配报告](reports/assembly_report.md) 与当天提交。提交保存区间 **19:33:10–22:30:01**；精确执行起止未恢复。
- H0 会话为 `20261116_2051`，工作区 `/home/kaiwen/research/dog-and-arm`。会话名不单独当作整个工作起止时间。
- 主要提交：H0 规划 `7bb3c1b` → 实测 `284c1f3` → 装配器 `b545796` → M1/Piper/整机桌面 `f8786a8`、`728fc8a`、`078839e`。

### A. H0 实机：实际工作与解决的问题

执行环境为用户 Linux 工作站；机械臂复用 OSCBF-learn / pyAgxArm 1.0.0、PIPER_H/V189；相机使用已有 ROS2 Humble 与独立相机 workspace。仿真环境与这些硬件环境分开。只操作 Piper H/DC1，没有运动 M1。

1. 确认 DC1 RGB USB PID `2bc5:0557`、深度 PID `2bc5:0657`，启动正确驱动；保存 RGB、原始深度、CameraInfo、设备和传输配置。
2. 建立只接收机械臂/CAN 的记录器、独立图像记录器与单独的现场动作入口。静止联合采集后进行现场启动的小幅腕部动作、停止和夹爪开合。
3. 保留首次动作未真正运动的失败，修正后再运行；正常停止/重启相机并验证恢复。
4. 处理两轮图像传输问题，最终通过项目独立 DDS/共享内存配置完成 90 s 与 240 s 静止连续复核。

| 现象 | 证据 | 原因状态 | 修改与复测 |
| --- | --- | --- | --- |
| 第一轮动作脚本结束，机械臂实际未动 | [attempt1 记录](results/hardware/h0/20261116_2051/evidence/attempt1/motion_observation.json) | CPV 包装器的运动模式设置问题已定位；脚本退出不代表运动 | 改回既有 MOVE_J 对应模式序列；第二轮实际 J6 范围 1.962°，动作/停止/夹爪变化已记录 |
| 初始 RGB 仅约 6.52 Hz | H0 报告与各采集窗口的 timing_summary | 与接收 QoS 设置有关，已通过更改对照 | 改 reliable 后 65 s 窗口约 29.91 Hz；保留原始失败数据 |
| 较长联合采集中 RGB 成批到达、最大间隔约 385 ms | continuous 窗口与运动段记录 | 传输/缓存积压问题经项目独立 DDS 配置修正 | 使用独立 domain/共享内存设置；90 s 与 240 s 静止复核稳定。没有重复运动，因此不把静止改善套用到旧运动视频 |
| RGB/深度分辨率与 CameraInfo 畸变字段不一致 | 两套 CameraInfo 与设备内参记录 | 原生模式不同不是故障；RGB 畸变来源差异尚未解决 | 原样保存并注明来源；未伪称完成重新标定、D2C 或硬件同步 |

**实测口径。** 最终 240 s 静止窗口 RGB 7,179 帧/29.912 Hz、深度 7,204 帧/30.017 Hz、关节反馈 48,006 组/200.025 Hz；对应最大接收间隔 40.023/39.860/8.104 ms。RGB 为 640×480 `rgb8`，深度为 640×400 `uint16` 毫米原始值。软件接收关联不等于曝光同步或端到端延迟。小幅动作包含明确起始位置调整，不能写成除了 J6 其他轴绝对不动。

**命令与 run。** 实际现场命令与参数以 H0 报告、会话 [manifest.json](results/hardware/h0/20261116_2051/manifest.json)、日志和 motion observation 为准。主要入口为 `h0_record_arm.py`、`h0_record_camera.py`、`h0_operator_motion.py`；这里不重建缺失的现场命令行，也不提供自动执行硬件动作的快捷替代。

**证据与保管。** 小样本在 [results/hardware/h0/20261116_2051/](results/hardware/h0/20261116_2051/)，包含 [最终时序统计](results/hardware/h0/20261116_2051/evidence/final_validation/timing_summary.json)、[成功动作记录](results/hardware/h0/20261116_2051/evidence/motion_success/)、原始深度小样本及短片；完整大记录按历史报告保存在用户本机 `results/raw_large/hardware/h0/20261116_2051/`。本次日志回填没有重新访问设备或恢复这些大文件。

**未完成。** 手眼、实物几何/质量惯量标定、硬件同步、视觉闭环、实机开门、M1 联动、完整工作空间线缆验证及紧急处理路径实测。H0 的限定结论是联合运行与采集可用；这些后置项不抹去 H0 的实际完成，也不被它代替。

### B. 装配与桌面：实际工作与解决的问题

1. 准备侧用独立 Python 3.12.14 / MuJoCo 3.3.0 获取固定官方来源，生成 M1、Piper H、联合 URDF/MJCF、关节映射、附件与相机，完成编译和三姿态独立 FK 对照。
2. M1 保留源模型物理参数；其衍生 URDF 用等价完整张量表达惯性。Piper 去除自带 world 固定根，处理真实双指与虚拟 master，不重复添加夹爪。
3. 解决 binary STL 以 `solid` 开头造成的识别问题，只规范确认是二进制 STL 的头部，三角形数据不变。Piper visual 明确采用官方 collision STL；没有把未做的 DAE 精细外观转换写成完成。
4. 生成整机、腕部、同一虚拟相机的 RGB/深度及 8 s 运动学片；实现原生实时查看、关节/夹爪操作、相机切换、碰撞显示和安全重载。
5. 随后在用户本机分别完成 M1、Piper 与整机可见检查，记录关节变化、夹爪开合和腕部关系；按用户要求在整机检查后暂停。准备侧报告的“无 DISPLAY”与后来本机可见验证是不同执行环境。

**命令/产物。** 装配报告记录了 `scripts/build_assembly.py --stage all`、`scripts/check_assembly.py`、`scripts/capture_assembly.py --video` 等入口。桌面事件与小规模证据在 [results/assembly/live_local/](results/assembly/live_local/)。描述与来源见 [description/joint_map.yaml](description/joint_map.yaml)、[source_versions.json](reports/source_versions.json)、[assembly_kinematics.json](reports/assembly_kinematics.json)。这些文件部分已被后续装配更新；要恢复当日具体内容需按当天提交读取，不能将当前 front60_v2 几何倒记到 11 月 16 日。

**指标边界。** 组合模型 `nq=31/nv=30/nu=23/neq=1`、一个自由根；模型质量约 43.537064 kg，不含被明确省略的附件/安装座额外载荷。相机刚性与 FK 只在数字模型中检查。当天预览为 `KINEMATIC_PREVIEW`，不是站稳、接触控制或完整开门。

**当日决定与接续。** 保留 H0 成果，手眼/称重继续后置；已有模型、环境和来源复用。暂停后再接本机整机取景/重载和 P4。11 月 17–19 没有足够证据补写工作；下一次有记录的接续发生于 11 月 20 日。

## 2026-11-20｜P4–P6 与前移安装复测（历史回填）

### 目标、时间与环境

- 目标：完成真实有限执行器接触，从固定底盘到自由底盘连续单门任务，再把用户要求的安装板向狗头前移 60 mm，重新验证推拉。
- 日期依据：P4/P5/P6 报告、安装说明、当天提交；提交保存区间 **19:13:57–21:58:07**。精确墙钟起止未恢复；下文秒数均为对应仿真物理时长。
- 环境：用户 Linux 桌面，native MuJoCo 3.3.0，项目独立 `.venv` / `scripts/project_env.sh`。本日这些任务没有操作实机。
- 模型顺序：旧方块座 `block_v1` → 双导轨 `rail_bridge_v1` → 整体前移 `rail_bridge_front60_v2`。同日有三套安装，成绩不能合并。

### A. 完成桌面装配与 P4 固定基座接触

`4bbf1e5` 保存整机取景、重载、腕相机检查。随后 `335f8bb`、`29eab00`、`e13a48f` 记录 P4：另建固定根场景，保持主模型自由根，用有限位置伺服、独立 IK scratch 和实际 `mj_step` 推动被动门；没有运行中写门角或焊接把手。

- 小角前拉实测约 19.261°；较大目标曾受机器人与门板几何阻碍。调整可达站位与把手高度后，前拉实测 **59.963319°**。旧严格 `>=60°` 标志未通过，不能用后来 ±2° 判据倒改。
- 背侧推门增加实测门角反馈，达到 **25.076175°**；该阶段含夹爪基座碰把手，尚不是干净双指接触的完整自由底盘任务。
- 证据：[P4_FIXED_BASE_CONTACT.md](reports/P4_FIXED_BASE_CONTACT.md)、[results/p4/](results/p4/)。历史每条具体命令、轨迹和失败口径以报告为准。

### B. P5 自由根慢行与停车

`e7e4556`、`9c43f53` 保存自由底盘站立、慢行、转向、携臂运动和按实测航向刹车的结果。只在 home 初始化一次，随后由 12 腿位置、4 轮速度、6 臂与夹爪执行器连续控制。

- `free_base_nominal`、`heading_12` 与 `heading_minus12_check` 分别记录名义和两方向检查；完整证据在 [P5_FREE_BASE.md](reports/P5_FREE_BASE.md) 与 [results/p5/](results/p5/)。
- 自由根自然沉降约 0.531984 m，比 P4 固定根低约 10.68 mm；P4 的静态关节表不能直接当 P6 自由根目标。
- 当时世界 Y 轮轴/轮心分配、一次性 `heading_stopped` 与驻停边界仍不足以支持门反力任务。转向有滑动与短时三轮承重样本，不能宣称全工况稳定。
- 后续 P6 修复了相对车体几何与可重新纠偏驻停；当前 P5 源码也引用新的轮几何函数。上述问题是当天旧版记录，不是声称当前代码仍原样存在。

### C. P6 连续自由根单门与旧座 20 条清单

`b04f604` 先做 P4/P5 证据复核并明确 P6 连续性。后续从承重、15°、60°到整任务逐级运行：

| 节点/run | 实际工作与结果 | 保存提交 |
| --- | --- | --- |
| `support_01` | 自由站位承重、伸臂与空中扫弧，25.32 s；门角仍 0° | `65a91a7` |
| `small_01`、`small_02`、`small_03` | 前两次开门超时；修正接触求解后第三次 14.957607°，释放和保持完成 | `dac8bf1` |
| `pull_01` | 操作位前拉 60.120818°，61.982 s；尚未包含初始驶近 | `ed8b28c` |
| `mobile_01` | 0.30 m 驶近到倒车停车的 13 阶段，82.162 s，终角 60.055003° | `6ed7373` |
| 初版 `conditions_A`～`conditions_D` | 20 条固定条件仅 10/20；保留未到站及退爪碰板失败 | `de6abd7` |
| `arrival_01`、`arrival_02` | 初次提高差速造成髋饱和；有界差速及腿姿助转后四条到站诊断通过；不是整任务成绩 | `e7a1ce7` |
| `recheck_A` → `final_A` | 修正退爪方向后仍有停车窗口被反复纠偏打断；加入驻停迟滞后六条完整通过 | `e815178` |
| `final_A`～`final_D` | 同版旧方块座前拉最终 20/20，完整两个 3 s 停车窗口 | `a91425b` |
| `push_01` → `push_02` | 第一轮抓持偏移失败；斜入腕姿后名义背推 25.055163°，仅双指接触目标杆 | `d0a626e` |

这些 run 均位于 [results/p6/](results/p6/)，依据为 [P6 总报告](reports/P6_FREE_BASE_DOOR.md)、[旧座首次清单](results/p6/conditions_v1.csv) 和 [旧座最终清单](results/p6/conditions_final.csv)。

**已记录命令示例（历史，不是本轮重新执行）：**

```bash
bash scripts/project_env.sh python scripts/p6_single_door.py mobile --live --video --hold-final --output results/p6/mobile_01
bash scripts/project_env.sh python scripts/p6_cases.py 2 6 18 20 --arrival-only --output results/p6/arrival_02
```

### D. 安装座变更与前移版失败/修复

`1ca8750` 保存采用双导轨跨接板与官方 Piper H 70×70 mm 接口的决定。`9bba777` 完成 rail_bridge_v1 桌面几何；`f09cb0a` 名义连续前拉实测 **60.048936°**。此时 25 Hz 时序曾看到 J5 余量仅 **0.141°**，只是一个名义新座样本。

`5cb8403` 将整套安装沿 +X 前移 60 mm，臂根从 `[0.050,0,0.0945]` 变为 `[0.110,0,0.0945] m`，其他完整导轨基准与高度保持。`d1696e4` 完成本机可见装配，并加入六轴每个 500 Hz 物理步的有符号限位余量。前移不能继承旧座成绩，因此另开 `rail_bridge_front60_v2_20261120T133724Z`。

| 问题现象与 run | 证据/原因状态 | 修改 | 复测状态 |
| --- | --- | --- | --- |
| `baseline_mobile_C01` 前拉夹爪基座碰门板；J5 最小余量 −0.081° | `84d13fd` 记录实际接触与全步余量，不能只看门已开到 61.18° | 前拉站位 X 从 0.650 移到 0.600 m，Y/腕姿保持 | `station_mobile_C01` 完整通过，60.04388°，`d50f0cf` |
| `station_push_C01` 虽通过，但倒车左后轮距门柱采样仅 0.68 mm | `b1ae766`，缺少扰动净空；不是已发生碰柱 | 检查预定初态，移动背侧站位 | 后续仍需实际展开与清单验证 |
| `station_mobile_C13` 双指仍接触，但 55 s 开门截止仅到 56.01962° | `4389873`，保留超时；不放宽原截止 | 前拉领先上限由原值改为 0.40° | `lead_mobile_C13` 60.05255°、开门 35.382 s、余量 19.618 s，`5f8d4b6` |
| 更外背侧站位的 `post_push_C01` 第二指碰上支杆 | `9f1553b` 保存预抓阶段实际非目标接触 | 背侧 X=1.935 m，预抓距离 105 mm，入杆/退离腕偏航 125°/137.5° | `clear_push_C01` 完整通过 25.08521°，`7e3c5e0` 冻结当时前/背控制 |
| 前拉修复须同时适用名义和 C13 | `536078e` | C01 与 C13 用同一 0.40° 设置 | `lead_mobile_C01` 完整通过 60.05158° |

来源：[安装说明](docs/MOUNT_RAIL_BRIDGE.md) 与 [前移版结果根目录](results/p6/rail_bridge_front60_v2_20261120T133724Z/)。`MOUNT_FORWARD_PUSH_PULL.txt` 是本轮历史执行约定，不是当前下一步入口。

### E. 当天收尾、失败保留与跨日接续

- 前移版 `mobile_A`（C02–C07）6/6、`mobile_B`（C08–C12、C14）6/6 加同版 C01、C13，形成前拉 C01–C14 通过；背推当时只有名义 C01 完整通过。
- `mobile_C`（C15–C20）收到用户暂停后关闭分格窗口，六条均在开门阶段 47.562 s 以 `window_closed` 中断。`59838b1` 保存记录，`25124d7` 保存暂停点。**当天不能写前移版前拉 20/20 或背推 20/20。**
- 下一次工作需继续未完成条件并保留原中断目录；11 月 21 日的 `mobile_C_resumed` 是另开目录、从各规定初态重新跑完整任务，不是把旧物理状态接着积分。
- 当日指标口径：物理控制/门槛 500 Hz、IK 100 Hz、详细时序 25 Hz、条件精简 trace 5 Hz；几何净空由 25 Hz 已积分位姿复算，有采样限制。一个真实物理 MjData 连续完成整任务；查看器镜像只作显示。
- 原始大时序按历史记录在用户本机 `results/raw_large/p6/`；Git 保存配置、摘要、条件表、精简时序和必要影像。安装座质量、相机外参/载荷仍为名义/omitted。
- 未完成：前移版剩余条件、双门、学习策略、实机协同。旧方块座 20/20、v1 名义样本与前移版必须分别统计。

## 2026-11-21｜P6 收尾与 B0-03 通过（历史回填）

### 时间、环境与起点

- 日期依据：当天提交、P6 追加报告与 B0 各报告。提交保存区间 **16:53:57–22:51:50**；这不是六小时实验用时，精确运行起止按各 run 原日志恢复。
- 前半段延续用户本机 native MuJoCo 3.3.0/P6；后半段在本机独立 B0 环境和 AutoDL 独立工作区进行研究版 mjlab/MuJoCo-Warp 实验。没有实机运动。
- 接续版本 `25124d7`；历史最终快照 `8c53e5a`。P6 工程控制冻结基线 `86ade863de712dd6cd402714229b12b1bdae5b13`；通过的 B0 云端训练代码记录为 `56f639618ebe3aa1e81d5539214611c8bf757bae`。报告提交、训练实现提交与 checkpoint 是三个不同对象。

### A. 补齐 P6，定位背侧碰柱并完成同版 40 条清单

1. `mobile_C_resumed` 重新运行 C15–C20，6/6 完整通过。随后背推 `push_A/B/C` 分别 5/5，`push_D` 3/4；90°背侧 C20 在 1.642 s 左后轮碰左门柱，不能因其余 39 条成功而漏报。
2. `974172a` 用真实轨迹复算驶近门框距离，定位 C20 接触；原始接触峰值 18.495 N。保持世界坐标扰动语义、物理和验收门槛，将背侧名义航向 90°改为 95°。
3. `push95_A/B/C/D` 对背推 C01–C20 全部重新实际执行，20/20。前拉 20 条的完整有效配置与最终版相同，沿用其真实动力学数据，不伪造重跑。
4. `dc961f3` 发布 front60_v2 最终清单：前拉 20/20、背推 20/20。90° 19/20、用户暂停和调参失败继续独立保留。

| 最终同版指标 | 前拉 60° | 背推 25° |
| --- | ---: | ---: |
| 通过数/预定条件 | 20/20 | 20/20 |
| 最终门角范围 | 59.963–60.224° | 25.043–25.089° |
| 开门阶段时间 | 31.394–35.382 s | 11.766–14.586 s |
| 全任务时间 | 71.480–75.758 s | 51.436–57.646 s |
| 两段各连续 3 s 停车窗口 | 20/20 完成 | 20/20 完成 |
| J5 最小全步余量 | 1.473° | 20.042° |
| 退臂最小 25 Hz 采样净空 | 9.394 mm | 15.155 mm |

总计 1,290,099 个 2 ms 物理步，六轴越界步数 0；最终清单非预期接触、求解器警告、持续饱和均为 0。前拉 C09 终点窗口最大采样速度 4.947 mm/s，接近 5 mm/s 门槛；背推实际最紧六轴是 C06 的 J4 15.225°。背侧驶近门框最小采样距离 16.881 mm，仅是 25 Hz 轨迹采样值。

**证据与命令。** [conditions.csv](results/p6/rail_bridge_front60_v2_20261120T133724Z/conditions.csv)、[parking_audit.csv](results/p6/rail_bridge_front60_v2_20261120T133724Z/parking_audit.csv)、[back_approach_frame.csv](results/p6/rail_bridge_front60_v2_20261120T133724Z/back_approach_frame.csv)、[P6 总报告](reports/P6_FREE_BASE_DOOR.md)。例如已执行：

```bash
bash scripts/project_env.sh python scripts/p6_cases.py 15 16 17 18 19 20 --stage mobile --output results/p6/rail_bridge_front60_v2_20261120T133724Z/mobile_C_resumed
bash scripts/project_env.sh python scripts/p6_cases.py 1 2 3 7 18 20 --stage push --output results/p6/rail_bridge_front60_v2_20261120T133724Z/push95_A
```

### B. 从工程控制转入 B0：来源、数据与后端

`f6333ec` 发布 R0 → B0 → R1–R8 的研究顺序；`b5fbc8d` 开始固定 O1 来源与目标平台教师数据。目标是先迁移官方学习机制，再逐步进入接触、统一任务及后续多模态/实机；不重启其他仓库已经关闭的 G1 复现。

- 固定源码：SuperMimic `abc124c1bd5976341034668af3d12c087f2f1f55`、mjlab_research `dd51a9fcc98791a2f0b018b3c7f71a3eefd5ecdd`，见 [source_lock.json](config/b0/source_lock.json)。保留 O1 世界模型监督学习、H32 可微 Actor 更新与 Critic，机器人状态/动作等必要适配另记。
- 本机实际为 RTX 5080 Laptop 16 GiB、Python 3.13.13、研究环境 MuJoCo 3.16；原生 3.3.0 环境继续独立。后续云端为 RTX PRO 6000，独立目录 `/root/autodl-tmp/dog-and-arm-b0`；独立 Conda 物理前缀 `.conda/envs/arm-and-dog`，shell 别名 `arm and dog`。
- 旧 P5/P6 时序缺少 B0 所需的完整每步状态/两指速度/恒定 20 ms 动作，因此没有用插值伪造 replay。重新采集三条各 7 s 无接触参考、一个独立扰动 WM 验证回合、前拉与 95°背推 C01。
- 无接触教师每条有 350 个真实 20 ms 转移；门教师保留 500 Hz/100 Hz 原控制更新，因此作为动态参考及接触段来源，**不直接进入 20 ms 恒定动作 WM replay**。
- 训练后端固定 P6 教师实际完成前拉 60.04931°、背推 25.07761°与两次保持；这是教师后端可行性，不能称学习策略开门成功。
- B0-03 的 full_state/representation 为 61/58 维，包含机器人双真实手指；场景仍有被动门，但门角/门速预测与接触状态扩展留待 B0-04。

**已执行的数据入口：**

```bash
bash scripts/project_env.sh python scripts/b0/collect_reference.py support moving_arm park moving_arm_wm_validation --output results/raw_large/b0/native_teacher_20261121_r1
bash scripts/project_env.sh env OPENBLAS_NUM_THREADS=1 python scripts/b0/collect_reference.py pull --output results/raw_large/b0/native_teacher_20261121_r1
bash scripts/project_env.sh env OPENBLAS_NUM_THREADS=1 python scripts/b0/collect_reference.py push --output results/raw_large/b0/native_teacher_20261121_r1
```

依据：[B0_SOURCES.md](reports/B0_SOURCES.md)、[B0_DATA_READINESS.md](reports/B0_DATA_READINESS.md)、[B0_ENV_ADAPTATION.md](reports/B0_ENV_ADAPTATION.md)、[reference_manifest.json](data/b0/reference_manifest.json)、[native_teacher_checks.json](data/b0/native_teacher_checks.json)。这些命令是历史执行记录，旧输出目录已经存在，后续不得直接覆盖。

### C. 学习试验中的失败、诊断、修复与复测

下面按实验演进记录。提交分钟只定位成果保存，run 的精确起止不根据表中顺序推断。

| run/问题 | 实际证据与原因状态 | 修改/处理 | 复测与仍未完成 |
| --- | --- | --- | --- |
| `free_s0_integration_r1` 两轮已接通梯度，但真实策略失败 | 320 条真实策略转移；独立三类均 0/20，0.100–0.176 s 失载/倾斜。动作分块对照确认早期腿命令足以失载、臂命令也可独立碰撞 | 保存冻结策略、状态和分块对照，区分接口接通与任务成功 | u2 只是接通证据，不能记 B0-03 通过；详见 B0_EVALUATION |
| `free_s0_formal_r1` 长窗 sampler 退出 | u160 已完成，u161 实际采集后无连续 8 状态有效窗口；累计 25,760 转移 | 增加短失败片段的一步监督与长窗/教师分配规则，另开 run | 原 run 只保留 u0 权重，没有把未保存的 u160 权重写成存在 |
| `free_s0_boundary_r1` home/replay 变体 | u50 全 60 条走完 7 s，但各类均 0/20；u200/u1000 又出现 0.1 s 失载。u1000 136,000 转移，WM 预测/局部 Jacobian 改善 | 保留失败，核查动作初始尺度、参考可行性和奖励量纲 | 模型误差下降不代表控制通过；该变体 u1000 仍未通过 |
| `free_s0_servo_units_r1` | 按伺服力矩/增益比例设动作尺度；u50 已写权重，评测尚在进行 | 按用户环境隔离要求停止，转到云端独立环境继续新 run | 没有完成原预定 u1000；已写部分逐案仅作诊断 |
| 云端 servo 首次启动 | u0 因部署缺 `description/joint_map.yaml` 停止 | 补齐映射、检查 23 通道与渲染，另起 `free_s0_cloud_servo_r2` 从零训练 | 首次失败不并入 r2 的通过成绩 |
| r2 u50/u200 | u50 三类 0/20；u200 为 20/20、11/20、19/20，失败均为 TCP RMSE 越 30 mm | 保持原 O1 tracking 奖励和既定门槛继续训练 | u200 尚未三类同时过门槛，继续至 u1000 |
| 独立 `free_s0_cloud_metric_r1` 支线 | 第 4 次 Actor 更新进入 CUDA capture 时轮索引触发 CPU→GPU 拷贝；前三次完整，4,352 转移 | 初始化时按名称创建设备索引张量，另起 `free_s0_cloud_metric_capture_r2` | 5 次新更新至 u8 验证 capture/replay；这是技术修复，非通过的策略基线 |
| 固定参考是否本身不可达 | 原生 3.3.0 用同一参考教师命令各跑 20 初态，三类均 20/20；参考字段核查无冲突动作 | 将教师可行性作为对照保留 | 只证明这些固定参考有可行解，不代替学习结果或泛化验证 |

主要依据：[B0_FREE_MOTION.md](reports/B0_FREE_MOTION.md)、[B0_EVALUATION.md](reports/B0_EVALUATION.md)、[轮地支撑几何审阅](reports/B0_WHEEL_SUPPORT_GEOMETRY.md)。原始 failure/outcome、updates.jsonl 与每个 run 的独立逐案保留在 [results/b0/](results/b0/)。

### D. 通过的 B0-03 seed0：准确范围

`free_s0_cloud_servo_r2` 使用 [free_servo_cloud.yaml](config/b0/free_servo_cloud.yaml)，从 seed0 随机初始化，128 个并行物理世界；到 u1000 产生 **1,088,000 条真实当前策略转移、10,000 个 WM 小批、1,000 次 H32 Actor 更新及配套 Critic 更新**。原 O1 tracking 奖励，非 metric 支线。冻结 Actor 独立输出全部 23 路动作，评测只保留固定 2 ms 低层伺服，参考时钟 20 ms。

| 固定 7 s 任务，每类 20 个开发初态 | Warp 3.16 | CPU 3.16 | 原生 3.3.0 |
| --- | ---: | ---: | ---: |
| 支撑伸收臂 | 20/20 | 20/20 | 20/20 |
| 移动变臂姿 | 20/20 | 20/20 | 20/20 |
| 停车收臂 | 20/20 | 20/20 | 19/20 |

- 原生 3.3.0 唯一失败为停车 F02：完整 3,500 子步/7 s，TCP RMSE **30.74979975 mm**，超过 30 mm 门槛；不能写成所有后端 60/60。预定每类 ≥18/20，因此 B0-03 通过。
- 同一独立扰动验证回合选 128 个起点，1/7/32 策略步（20/140/640 ms）TCP 递推 RMSE 为 **0.3595/2.0364/2.8211 mm**；128 起点不是 128 个独立回合，也不是开门接触预测验证。
- Warp 与 native 3.3.0 各另有 3 条名义初态通过。它们不加入 20 条开发条件分母；不同后端重复执行也不增加条件覆盖数。
- 保留 [review.json](results/b0/free_s0_cloud_servo_r2/review.json)、[Warp 逐案](results/b0/free_s0_cloud_servo_u1000_warp/physical/cases.csv)、[CPU 3.16 逐案](results/b0/free_s0_cloud_servo_r2/eval_001000/physical/cases.csv)、[native 3.3.0 逐案](results/b0/free_s0_cloud_servo_u1000_native33_full/physical/cases.csv) 及代表视频。
- 权重为 `results/b0/free_s0_cloud_servo_r2/checkpoint_001000.pt`，报告登记大小 160,968,966 字节，并登记用户本机与 AutoDL 两处工作区。本 Git 快照不含 `.pt` 和完整 `raw_large` 数组；本轮日志回填没有访问远端实际权重，不能写成本轮已恢复/校验。

**历史实际训练命令：**

```bash
bash scripts/b0/env.sh python -u scripts/b0/train.py --seed 0 --run free_s0_cloud_servo_r2 --config config/b0/free_servo_cloud.yaml --updates 1000
```

**当日结论与暂停。** `8c53e5a` 冻结 B0-03 通过结果并等待用户检查。B0-04 接触/门状态预测、完整单门学习、统一任务、多 seed、多模态及实机验证尚未完成。仅仅场景里保留门不表示 Actor 已经学会推拉门；P6 教师的 40 条通过和 B0-03 无接触策略通过是两套证据。

## 2026-11-21｜建立日志与发布 B0 后续计划（本轮文档记录）

### 目标、时间、环境与版本

- 用户本轮要求：新增一个单独文件，详细记录每天工作和解决的问题；同时整理后续计划与启动提示词并推送。
- 本条记录建立时钟读数为 **2026-11-21 23:50:10 北京时间**（工具返回 UTC 15:50:10 后换算）；这是文档工作中的记录时刻，不是全轮审阅开始时间。文档编辑/发布结束时间留待完成后据实补记。
- 执行环境：当前远程工作区的仓库检出 `/workspace/scratch/bdf34e707b47/dog-and-arm`，基线 `8c53e5a`。这不是在用户本机或 AutoDL 训练，也没有硬件连接。
- 本轮编辑范围是日志、B0 后续计划、启动提示词和项目状态/规则入口；实验代码、配置、权重和既有结果未改。

### 实际工作、发现与处置

1. 根据 main 真实提交时间和已有工程/实验报告回填 11 月 15、16、20、21 日的工作、失败、修复、版本与接续关系；明确 17–19 日证据空缺。
2. 把历史运行与本轮只读审阅、文档编辑分开；把提交时间、物理时长与现场动作起止分开。
3. 汇总旧文档/派生模型的版本差异：`mount_interface_reference.json` 尚有历史 pending 文案；旧 `p6_free_door.xml` 是 v1，而现行 P6 从 front60_v2 的 `assembly_preview.xml` 动态组合；旧 P4/P5 与 `assembly_build_all.json` 保存早期座。当前状态以最新有效配置和成果为准。本日志不借这些发现改写实验结果。
4. 写成 [B0 接触执行计划](docs/B0_CONTACT_EXECUTION_PLAN.md)，将下一轮明确为接口/数据与门动态 → 接触片段 → 连续两侧任务 → 统一模型和多 seed/留出验证；同步启动提示词与状态入口。计划条目没有写成已经执行的实验。

### 验证、产物、未完成与决定

- 已做基础文档自检：本文件所有实际 Markdown 仓库相对链接均存在，5 个代码围栏块闭合，无 NUL 字符和行末空格；提交索引从 `origin/main` 实际生成，共 62 条（11 月 15/16/20/21 日分别 2/6/34/20 条），author 与 committer 时间一致并按北京时间显示。后续计划的拟定路径以正文登记，发布前由主任务核实。未运行仓库实验入口，未生成新策略指标。
- 产物：本文件、B0 后续计划和提示词，以及同步的项目规则/状态/路线。用户授权发布文档，并不把本条记录改成已执行 B0-04。
- 本轮未执行：新训练、接触数据采集、策略评测、仿真窗口、实机动作；历史权重/大数组没有因文档发布自动恢复。
- 下一次工作：读取最新状态、后续计划和启动提示词，从用户实际选择的 B0 接触节点继续；用新 run 保存真实执行，按下面模板当天追加。
- **跨日接续：** 23:50 建立记录，最终文档一致性核对与发布准备继续到 11 月 22 日；见后续日志追加区。当前条目随本次文档提交保存，提交号和远端发布以 Git 历史为准。

## 后续每日记录模板

将以下模板复制到本文件后续日志区，同一文件按日期持续追加。各字段可以写“无/不适用/未恢复”，不要为填满表格制造精度或成果。

```markdown
## YYYY-MM-DD｜任务名（北京时间；当日记录/历史补记）

### 1. 今日目标与承接

- 要解决的问题、明确完成门槛：
- 上一日/上一条记录及未完成部分：
- 本日类型：文档/源码修改/静态或 FK/仿真教师/学习训练/冻结评测/实机。
- 若为补记：补记日期、原始依据、时间精度、仍不可恢复的信息。

### 2. 起止时间与执行环境

- 实际开始：YYYY-MM-DD HH:mm:ss +08:00；实际结束/暂停：
- 精度来源：现场日志/进程日志/报告日期/只有提交时间；未知部分明写。
- 主机与工作区：本机/AutoDL/准备侧；OS、GPU、解释器、环境入口。
- 物理后端与版本：native 3.3.0 / CPU 3.16 / Warp 3.16 / 不运行物理。
- 实机设备及操作者条件（仅实机填写）：
- 跨日：进程是否持续、是否恢复 checkpoint、是否新建物理回合；两日记录互链。

### 3. 代码、配置、模型与数据版本

- 源码 commit、分支、执行时未提交 diff 的定位：
- 配置路径与 actual_config；安装版本/模型文件；source_lock：
- seed、checkpoint、更新计数、数据/reference manifest：
- 训练集/开发集/留出集用途与禁止混用项；评测条件与预先声明分母：

### 4. 实际命令与 run 路径

- 计划命令（尚未执行的明确标注）：
- 真正执行的命令、工作目录、环境变量/参数：
- run 名、输出目录、父进程/作业定位；开始、完成或异常退出状态：
- 恢复时从什么权重开始；optimizer/normalizer/replay/环境状态各自如何处理：
- 历史命令缺失时只引用可验证入口，不补造完整 shell 历史。

### 5. 今日实际工作

1. 具体操作/修改、为什么需要、涉及哪些文件：
2. 实际观察到的变化和对应证据：
3. 代码已写/已运行/已评测/已人工查看分别标明：

### 6. 问题闭环

| 编号 | 现象与影响 | 证据/run/时刻 | 原因及状态（已证/假设/未知） | 修复或处理 | 复测及剩余问题 |
| --- | --- | --- | --- | --- | --- |
| P-日期-01 | | | | | |

### 7. 数据与指标口径

- 完整任务/片段/教师/策略/运动学/技术诊断各自的分母与结果：
- 物理步长、策略周期、采样率、持续窗口、时间/坐标/单位定义：
- 通过门槛、实际值、失败原因与最紧余量：
- WM 开环预测：独立 episode、起点数、horizon、是否刷新真值、数值对照：
- 不确定性：抽样净空/未测硬件/缺失文件/后端差异等实际限制：
- 表格/原始数据/视频路径；视频来自实测轨迹还是静态或运动学回放：

### 8. 失败、暂停、未完成

- 未通过或异常退出的 run、最后成功节点、已落盘与未落盘内容：
- 暂停来自用户还是技术问题；是否仍有后台进程；有无恢复检查点：
- 尚未运行的计划、未完成的复测；不得写成已通过：

### 9. 决定与下一工作日事项

- 本次确认/推翻的决定，依据与适用版本：
- 下一具体节点、前置条件、预计产物与停止门槛：
- 最小启动入口；新 run 命名；需人工就绪的实机步骤：
- 下一天实际发生后回链，不能事后把次日结果算到今天。

### 10. 提交、推送与产物

- 修改文件、报告/小数据/必要影像：
- 大权重/原始数据实际位置、恢复依据、本次核验范围：
- 提交：待提交/真实 commit；推送：待推送/真实远端分支与验证结果：
- 文档/路径检查结果；本次没有执行的验证：
```

## 首次回填的 Git 提交索引

下表以本文件首次回填时 `origin/main` 的全部可达提交为边界，按 Git 输出的拓扑顺序列示；各日的时间为提交的 author/committer ISO 时间统一转换到北京时间。本次基线两种时间相同。合并提交只是历史集成，不自动代表新增实验。后续新提交由日记条目登记，不必重复生成旧表。

| 北京日期 | 提交时间 | 提交 | 原始提交标题 |
| --- | --- | --- | --- |
| 2026-11-15 | 20:53:20 | [2ce7916](https://github.com/kaiwen123-yang/dog-and-arm/commit/2ce7916a5beda814cd06bb13986035d0fd9766a6) | Initialize M1 and Piper H MuJoCo project |
| 2026-11-15 | 20:54:49 | [b7d1f88](https://github.com/kaiwen123-yang/dog-and-arm/commit/b7d1f8831363f9054e45a007969f5441994115ba) | Add Linux MuJoCo kickoff package for M1 and Piper H |
| 2026-11-16 | 19:33:10 | [7bb3c1b](https://github.com/kaiwen123-yang/dog-and-arm/commit/7bb3c1b6e73f244f7ded4c4cb0b8b44b35c3bfc3) | Add H0 Piper H and wrist camera hardware integration round |
| 2026-11-16 | 21:38:10 | [284c1f3](https://github.com/kaiwen123-yang/dog-and-arm/commit/284c1f3f1bb9d5096003433f6153a9c5e95d6189) | Complete H0 Piper H and DaBai DC1 hardware integration |
| 2026-11-16 | 22:14:53 | [b545796](https://github.com/kaiwen123-yang/dog-and-arm/commit/b545796e009735e0bc9cc842cc49fc4d3a079333) | feat: assemble M1 and Piper H with live MuJoCo preview |
| 2026-11-16 | 22:24:44 | [f8786a8](https://github.com/kaiwen123-yang/dog-and-arm/commit/f8786a812d7bcc7798f7414d3b1b9c2e0ff19c1b) | Verify local M1 desktop preview and clarify collision inspection |
| 2026-11-16 | 22:26:35 | [728fc8a](https://github.com/kaiwen123-yang/dog-and-arm/commit/728fc8adcfe7faeb1b7ba95e84df21487118f151) | Record visible Piper H joints gripper and wrist inspection |
| 2026-11-16 | 22:30:01 | [078839e](https://github.com/kaiwen123-yang/dog-and-arm/commit/078839e08195f6b8ce9bcd5a9a2341b709b63429) | Save local combined assembly inspection and user-requested pause |
| 2026-11-20 | 19:13:57 | [4bbf1e5](https://github.com/kaiwen123-yang/dog-and-arm/commit/4bbf1e5de87b0647ecb7808c9bce6d84cfe32c5f) | Finish local assembly framing reload and wrist camera checks |
| 2026-11-20 | 19:29:14 | [335f8bb](https://github.com/kaiwen123-yang/dog-and-arm/commit/335f8bb736181b200220e05434bfd377e58f3832) | Add finite-actuator fixed-base door contact and measured 19 degree pull |
| 2026-11-20 | 19:41:44 | [29eab00](https://github.com/kaiwen123-yang/dog-and-arm/commit/29eab00e940a1b129875311f29b38065f12bf36f) | Record the 59.963 degree fixed-base pull with its release trajectory |
| 2026-11-20 | 19:47:39 | [e13a48f](https://github.com/kaiwen123-yang/dog-and-arm/commit/e13a48fed2103a91fb25ad093a03a6aa481ee9f6) | Push the passive door from the back and correct the measured angle before release |
| 2026-11-20 | 19:51:26 | [e7e4556](https://github.com/kaiwen123-yang/dog-and-arm/commit/e7e455695f4c06359ef7cfebe365edcf19e04294) | Run and measure the free M1 base standing, rolling, turning and carrying the arm |
| 2026-11-20 | 19:54:46 | [9c43f53](https://github.com/kaiwen123-yang/dog-and-arm/commit/9c43f530360ce3398018b954f46eac11b96e0d73) | Brake by measured heading and verify left and right turns with the arm aboard |
| 2026-11-20 | 20:17:41 | [b04f604](https://github.com/kaiwen123-yang/dog-and-arm/commit/b04f60470520b20754eff35e063af5839d09e1e2) | Review P4/P5 evidence and plan continuous free-base single-door P6 |
| 2026-11-20 | 20:28:57 | [65a91a7](https://github.com/kaiwen123-yang/dog-and-arm/commit/65a91a7d7eb5291f0ce11d356de939368562515b) | Verify free-base support and arm deployment on the Linux desktop |
| 2026-11-20 | 20:32:47 | [dac8bf1](https://github.com/kaiwen123-yang/dog-and-arm/commit/dac8bf1f4a985d76403016f861cd12602311c637) | Measure the free-base 15 degree pull and resolve tangential contact drift |
| 2026-11-20 | 20:34:38 | [ed8b28c](https://github.com/kaiwen123-yang/dog-and-arm/commit/ed8b28cf5b070dd3a001f31eea08afeae9e9388b) | Verify 60 degree passive door pull with the base supported by four wheels |
| 2026-11-20 | 20:36:25 | [6ed7373](https://github.com/kaiwen123-yang/dog-and-arm/commit/6ed73730d44b3e4338162654940a1487dbe25348) | Complete the continuous approach, pull, release and reverse parking task |
| 2026-11-20 | 20:42:01 | [de6abd7](https://github.com/kaiwen123-yang/dog-and-arm/commit/de6abd7768fa53d5f8b7ab2f3fd8cb3116205e21) | Record all 20 frozen mobile pull conditions and isolate ten failures |
| 2026-11-20 | 20:44:16 | [e7a1ce7](https://github.com/kaiwen123-yang/dog-and-arm/commit/e7a1ce799ba87b2ba7576166ec4505fabe2362e5) | Align the four-wheel approach with bounded leg assistance and clear the panel on retreat |
| 2026-11-20 | 20:48:47 | [e815178](https://github.com/kaiwen123-yang/dog-and-arm/commit/e8151781db41d0e26c662c1318cc3e65fd2dea12) | Stabilize both parking windows and recheck the collision and arrival cases |
| 2026-11-20 | 20:50:12 | [1ca8750](https://github.com/kaiwen123-yang/dog-and-arm/commit/1ca875035e7334fdca23b85c024f33de6fd27e8e) | Adopt rail-bridge mount and verify Piper H 70 mm interface |
| 2026-11-20 | 20:54:14 | [a91425b](https://github.com/kaiwen123-yang/dog-and-arm/commit/a91425b12211be693bdfc1e49c76dd78ce5e2170) | Verify the continuous 60 degree mobile pull across all 20 fixed conditions |
| 2026-11-20 | 20:56:23 | [da1761a](https://github.com/kaiwen123-yang/dog-and-arm/commit/da1761a4f9812ea80500e36e6623c7533b67c151) | Merge remote-tracking branch 'origin/main' |
| 2026-11-20 | 20:59:57 | [d0a626e](https://github.com/kaiwen123-yang/dog-and-arm/commit/d0a626ee575d148f8c53e6b15d0b27c276d401b9) | Push the passive door from the back with verified finger-only contact |
| 2026-11-20 | 21:11:38 | [9bba777](https://github.com/kaiwen123-yang/dog-and-arm/commit/9bba7774802f90083663fa3b0c4cb065fa489808) | Mount the original Piper flange on two M1 rails and verify desktop geometry |
| 2026-11-20 | 21:13:17 | [f09cb0a](https://github.com/kaiwen123-yang/dog-and-arm/commit/f09cb0a1f74eb8b94994cb116896df915ce82365) | Verify the 60 degree continuous mobile pull on the lower rail bridge |
| 2026-11-20 | 21:28:35 | [5cb8403](https://github.com/kaiwen123-yang/dog-and-arm/commit/5cb84039a109020522984a6be3340a023f8611d4) | Move rail bridge 60 mm forward and prepare complete push-pull retest |
| 2026-11-20 | 21:37:55 | [d1696e4](https://github.com/kaiwen123-yang/dog-and-arm/commit/d1696e41e07dd7af77de33223cf91750a605d514) | Inspect the forward rail mount and instrument joint limits and retreat clearance |
| 2026-11-20 | 21:40:13 | [84d13fd](https://github.com/kaiwen123-yang/dog-and-arm/commit/84d13fd91e4803a8b82dfecfd3ac1ab52f31537e) | Record the near-limit wrist and panel contact on the forward-mount baseline pull |
| 2026-11-20 | 21:42:29 | [d50f0cf](https://github.com/kaiwen123-yang/dog-and-arm/commit/d50f0cff006fb67ef3d15f5da6644bdecf29c959) | Move the pull station 50 mm back and verify the continuous 60-degree task |
| 2026-11-20 | 21:43:56 | [b1ae766](https://github.com/kaiwen123-yang/dog-and-arm/commit/b1ae76616f9058f94b5589bcb26572725146efc1) | Verify the 25-degree nominal push and measure rear-wheel proximity to the post |
| 2026-11-20 | 21:45:43 | [4389873](https://github.com/kaiwen123-yang/dog-and-arm/commit/43898733497a84aa9bd144ca8c2cbe54a3fb820d) | Preserve the C13 pull timeout at the unchanged opening deadline |
| 2026-11-20 | 21:47:28 | [5f8d4b6](https://github.com/kaiwen123-yang/dog-and-arm/commit/5f8d4b672ce963e3a31cf0811ad8d8108f14715d) | Recover C13 within its deadline and clear the post at perturbed back starts |
| 2026-11-20 | 21:48:54 | [9f1553b](https://github.com/kaiwen123-yang/dog-and-arm/commit/9f1553bb0084bbf5d57b03c252f52b21249203cb) | Keep the upper-handle contact found while deploying at the wider back station |
| 2026-11-20 | 21:50:40 | [536078e](https://github.com/kaiwen123-yang/dog-and-arm/commit/536078e24e654cfde2a76287fea97c570f0a8312) | Verify the nominal pull on the same feedback settings as the recovered C13 |
| 2026-11-20 | 21:52:00 | [7e3c5e0](https://github.com/kaiwen123-yang/dog-and-arm/commit/7e3c5e050da1977597db5419b0a5337ba55532a5) | Freeze the front and back controllers after clearing the back handle deployment |
| 2026-11-20 | 21:53:26 | [4dfdc10](https://github.com/kaiwen123-yang/dog-and-arm/commit/4dfdc104e86abd2a51bf2f788e6be45cd8aa50c7) | Record forward-mount mobile condition group A (2 3 4 5 6 7) |
| 2026-11-20 | 21:55:41 | [f65d9f8](https://github.com/kaiwen123-yang/dog-and-arm/commit/f65d9f8149104be29b14252ee5d38fc8f7c76298) | Record forward-mount mobile condition group B (8 9 10 11 12 14) |
| 2026-11-20 | 21:57:12 | [59838b1](https://github.com/kaiwen123-yang/dog-and-arm/commit/59838b14da01c4391d9d69c1da957078ad4deda3) | Record forward-mount mobile condition group C (15 16 17 18 19 20) |
| 2026-11-20 | 21:58:07 | [25124d7](https://github.com/kaiwen123-yang/dog-and-arm/commit/25124d7fb1933040302093d94a49ddb378c7197d) | Checkpoint the user-requested pause after 14 pulls and one push |
| 2026-11-21 | 16:53:57 | [dc3b72a](https://github.com/kaiwen123-yang/dog-and-arm/commit/dc3b72a845cee2d34f4f0782425ae08203203f42) | Record forward-mount mobile_C_resumed trials and verify joint and parking measurements |
| 2026-11-21 | 16:55:03 | [f4ddd76](https://github.com/kaiwen123-yang/dog-and-arm/commit/f4ddd762b00bc83306432839c1fd4ecce2615080) | Record forward-mount push_A trials and verify joint and parking measurements |
| 2026-11-21 | 16:56:13 | [98b4114](https://github.com/kaiwen123-yang/dog-and-arm/commit/98b4114403587f64a99451bc5fef3b72e19778a1) | Record forward-mount push_B trials and verify joint and parking measurements |
| 2026-11-21 | 16:57:21 | [426a557](https://github.com/kaiwen123-yang/dog-and-arm/commit/426a55773bc1e8a6152d9bb71db29a9cba927228) | Record forward-mount push_C trials and verify joint and parking measurements |
| 2026-11-21 | 16:58:35 | [8f39aa8](https://github.com/kaiwen123-yang/dog-and-arm/commit/8f39aa893a02e598fc7f86a2853bab83b3a4abcb) | Record forward-mount push_D trials and verify joint and parking measurements |
| 2026-11-21 | 17:00:04 | [974172a](https://github.com/kaiwen123-yang/dog-and-arm/commit/974172a053185b0cc709dd4e464d2f6eb8dcb6bb) | Measure the back approach from logged poses and locate the C20 post contact |
| 2026-11-21 | 17:00:57 | [86ade86](https://github.com/kaiwen123-yang/dog-and-arm/commit/86ade863de712dd6cd402714229b12b1bdae5b13) | Record forward-mount push95_A trials and verify joint and parking measurements |
| 2026-11-21 | 17:02:02 | [65e3e02](https://github.com/kaiwen123-yang/dog-and-arm/commit/65e3e0290241007c760ae56cffd4f5d06fe810be) | Record forward-mount push95_B trials and verify joint and parking measurements |
| 2026-11-21 | 17:03:10 | [198318f](https://github.com/kaiwen123-yang/dog-and-arm/commit/198318f9e1410b8630589d7f9050c41d844d0f26) | Record forward-mount push95_C trials and verify joint and parking measurements |
| 2026-11-21 | 17:04:20 | [96cfcb7](https://github.com/kaiwen123-yang/dog-and-arm/commit/96cfcb75ef5197cf6f5f2203750780e75038548a) | Record forward-mount push95_D trials and verify joint and parking measurements |
| 2026-11-21 | 17:06:12 | [dc961f3](https://github.com/kaiwen123-yang/dog-and-arm/commit/dc961f35034ad3083a46eecd1c0ff5f21607eb0c) | Publish the 40-case forward-mount pull and push results with measured margins |
| 2026-11-21 | 21:25:42 | [f6333ec](https://github.com/kaiwen123-yang/dog-and-arm/commit/f6333ec4f9b55a94050f19301f0c4c8a3a94ce41) | docs: plan SuperMimic B0 migration and multimodal research stages |
| 2026-11-21 | 21:42:07 | [b5fbc8d](https://github.com/kaiwen123-yang/dog-and-arm/commit/b5fbc8d3e2a6099aa122adb32adb191e525cf228) | Pin O1 sources and collect named whole-body and passive-door teacher trajectories |
| 2026-11-21 | 21:47:10 | [fe311eb](https://github.com/kaiwen123-yang/dog-and-arm/commit/fe311ebcae484e5aadc0eb4b2f759cb3ee63ff90) | Run O1 GenCoord and H32 policy updates on the free M1/Piper, measure physical failures |
| 2026-11-21 | 21:55:29 | [86ef007](https://github.com/kaiwen123-yang/dog-and-arm/commit/86ef007bfc94c8107a429a26f1ab80cad78f0f41) | Verify both passive-door teachers on Warp and adapt supervision for short policy episodes |
| 2026-11-21 | 22:17:49 | [56f6396](https://github.com/kaiwen123-yang/dog-and-arm/commit/56f639618ebe3aa1e81d5539214611c8bf757bae) | Measure free-motion transfer at 1000 updates and isolate B0 in project Conda |
| 2026-11-21 | 22:26:07 | [fe6cc85](https://github.com/kaiwen123-yang/dog-and-arm/commit/fe6cc857b5b2960ad5363c8c1b3365aaabdf3b8d) | Verify fixed references in all 60 cases and calibrate B0 tracking rewards |
| 2026-11-21 | 22:35:44 | [b0dd4a6](https://github.com/kaiwen123-yang/dog-and-arm/commit/b0dd4a69658fa038c57f51de3313d9cc2ab0e43a) | Record two physical gates at update 200 and keep wheel reward indexing on device |
| 2026-11-21 | 22:39:25 | [bdd2a0e](https://github.com/kaiwen123-yang/dog-and-arm/commit/bdd2a0e09dbc7e36df591e28ba3a518b36e0fff6) | Verify cloud model errors and the repaired CUDA graph on real updates |
| 2026-11-21 | 22:51:50 | [8c53e5a](https://github.com/kaiwen123-yang/dog-and-arm/commit/8c53e5a116839021866c64ff87a17d00c0be7e9c) | Freeze passing B0-03 whole-body tracking checkpoint and pause for review |

## 后续日志追加区

后续工作从这里按北京时间追加。首次发布前的状态可在上面的本轮文档条目据实补全；已发布的历史结论若需纠正，追加更正依据与日期。


## 2026-11-22｜接续完成 B0 计划与每日记录的发布准备（本轮文档记录）

### 时间、目标与实际工作

- 接续上一日文档工作；**00:00:57 北京时间**已重新查询时钟及 GitHub 两个分支头。这是核对时刻，不是本轮开始/结束时刻。`main` 仍为 `8c53e5a`，现场分支仍为 `7ab40e3`，未合并或改写现场分支。
- 本日工作是对新计划、日志及入口进行最终一致性核对并准备普通发布；没有重新训练、仿真评测或实机动作。
- 形成十个文档文件的同一次更新：`AGENTS.md`、`PROJECT_STATE.md`、`README.md`、`DAILY_WORK_LOG.md`、三份既有 B0/研究约定、`docs/B0_CONTACT_EXECUTION_PLAN.md`、`prompts/B0_START.txt`、`prompts/NEXT_RUN.txt`。实验源代码、物理配置和旧结果未改。

### 这次明确并写入计划的问题

| 问题 | 已核对依据 | 计划中的处理 | 当前验证状态 |
| --- | --- | --- | --- |
| 旧状态头仍说 B0 未训练、从 R0 开始 | 与 B0-03 冻结结果及最新 PROJECT_STATE 不一致 | 更新当前入口为 B0-04～06，保留历史过程 | 文档已改，未重跑冻结实验 |
| 完整门教师命令频率与学习动作不一致 | 数据报告明确腿轮500Hz/臂100Hz，门轨迹reference_only | 新采20ms保持物理目标的真实接触转移，不用抽帧伪造监督 | 已列执行要求，尚未采集 |
| P6近位/开门条件依赖教师内部IK和ramp | 读取实际控制代码确认 | 映射到冻结目标及只读物理事件，并核对语义一致性 | 已列实现任务，未声称评估器完成 |
| 首失败子步可能早于完整20ms | 原生与训练采集停止方式不同 | 同时保存首失败事件、真实跨度与terminal successor，部分区间不伪装成固定dt | 已写数据契约执行细则 |
| 小角度3s保持不天然包含于连续开门参考 | 当前教师持续开门，无该新片段保证 | 新采真实保持episode或先验证参考可执行性 | 新协议，尚未执行 |
| 抓持RSI存在合法目标接触 | 完整任务初态筛选不能直接套用 | contact_dev按阶段定义允许接触与重建；不使用H条件调参 | 已写开发集协议 |
| 同一B0-03权重分叉不等于完整三次独立训练 | 权重继承关系与seed定义不同 | seed1/2各自训练链；共享预训练诊断单列 | 待执行，未虚报多seed |
| 先看seed0的H结果再调其余seed会改变测试身份 | 现有H仅几何验证，没有任务成绩 | 三条链候选和规则全部冻结后才查看H任务结果 | 已保留原v1条件与门槛 |

### 文档核对、交付与接续

- 实际执行：`git fetch origin --prune`、`git ls-remote --heads origin`、`git diff --check`；读取现有代码/报告和各日Git元数据。未调用训练或硬件入口。
- 对本次10个文档做UTF-8、换行、Markdown围栏、仓库相对链接及旧当前状态措辞检查；检查时无缺失实际链接、无未闭合围栏、无NUL/行末空格。日记的62条历史提交与初始main基线对应，不能把随后文档提交算入这份历史实验索引。
- 新计划和提示词明确按验收逐级继续；每日单文件记录已写入AGENTS和交付要求，任务跨日继续记录，不设后台墙钟强制终止。
- 本次文档提交标题：`docs: add daily work log and plan B0 contact-to-door execution`。本条随同一提交保存；其完整SHA、提交时间和远端是否可见以Git历史为准，下一次工作可补记已确认的提交号，不为预填自身SHA反复制造提交。
- 下一项：用户把当前 `prompts/B0_START.txt` 交给执行Codex后，从04-A实际接口/数据与评估器开始；先查真实环境/权重/数组，再按计划推进。所有接触学习和完整门策略成绩仍为待执行。

### 13:03 北京时间核查｜B0-04 实施启动

- 在 /home/kaiwen/research 下定位主仓 dog-and-arm。执行 `git status --short --branch`、`git branch -vv`、`git worktree list`、`ps -eo pid,ppid,etime,pcpu,pmem,comm`、`git fetch origin --tags`、`git ls-remote --heads origin`。远端 main 确认为 865835cab27891b6627aa94b52287c27d5f3971c，现场分支为 7ab40e3；原 main 在 fe6cc85，PROJECT_STATE、H0_RUNBOOK、两份 H0 脚本有修改，P5 有未跟踪目录。未发现正在运行的 B0 训练/仿真。通过 `git worktree add -b b0/contact-baseline-20261122 ../dog-and-arm-b0-contact origin/main` 建立独立工作树。原树和两分支上的既有工作全部保留。
- 实机主机 kaiwen-Legion-Y9000P-IAH7H，`nvidia-smi` 实测 RTX 3060 Laptop 6144 MiB、20 个逻辑 CPU、约 15 GiB 系统内存。原树的 .venv、.conda、vendor、assets/converted 以及两处原始教师目录通过本地符号链接复用；新数据写在独立树的 results/raw_large/b0。双 pin 由 git rev-parse HEAD 核对一致。原生 Python 3.10.12、MuJoCo 3.3.0；研究环境实际导入 Torch 2.14.0+cu130、MuJoCo 3.16.0、Warp 1.18.0，CUDA 可用。原生历史教师目录 119 MiB，含 pull、push、三项 free-motion 和独立验证。
- 冻结权重路径和本机历史记录出现差异。`rg --files -uuu /home/kaiwen -g checkpoint_001000.pt -g '!**/site-packages/**'` 只找到 free_s0_boundary_r1 的不同配置检查点。目标 run 的 Git 结果可读，指定 .pt 在本机项目缺失。目前无现成 AutoDL SSH 别名，已向用户请求可读路径或连接方式。启动接触采集、评估器、门模型开发和跨后端真步进准备，保留 seed0 继承关系。未执行接触策略验收、H 条件或实机。
- 本轮先检验两侧 20 ms 恒目标是否能在名义几何下产生双指抓持及保持。计划比较同一初态和动作的 CPU 3.3.0、CPU 3.16、Warp 3.16 真实反应，再按真实结果确定训练与修复。正式训练、原始采集与诊断分别命名。

### 13:06–13:07 北京时间｜恢复冻结 seed0 与云端运行入口

- 用户提供当前 AutoDL 入口并授权在本机固定配置。在本机创建专用 ED25519 密钥及 SSH 别名 `autodl-dog-arm`，安装公钥后以 `ssh -o BatchMode=yes autodl-dog-arm` 成功登录。凭据未写入项目。云端 RTX PRO 6000 Blackwell Server Edition 实报 97,887 MiB；cgroup cpu.max 为 2500000/100000，memory.max 为 128849018880 字节。已有其他研究的运行进程，保留。
- 云端旧树在 56f6396，有未跟踪实验与研究文件。只从中读取冻结权重、环境与资产；接触阶段另建工作树 /root/autodl-tmp/dog-and-arm-b0-contact。云端原生教师目录仅有四组无接触数组，两侧门数组来源以本机为准。
- 运行 `rsync -a --partial autodl-dog-arm:/root/autodl-tmp/dog-and-arm-b0/results/b0/free_s0_cloud_servo_r2/checkpoint_001000.pt results/b0/free_s0_cloud_servo_r2/`；本机 `torch.load(...,map_location='cpu',weights_only=False)` 实读 160968966 字节，seed=0、updates=1000、collected=1088000，actor/dyn/critic 状态字典分别有 68/24/10 项，附优化器。前项权重缺失已解决；接触模型更改维度，后续按迁移初始化处理。
- 本机 git 无可用 HTTPS 写入凭据，`GIT_TERMINAL_PROMPT=0 git push --dry-run origin HEAD:main` 报缺 Username，`gh auth status` 未登录。云端已有用户的 GitHub 配置，`gh api repos/kaiwen123-yang/dog-and-arm --jq .permissions.push` 返回 true；通过云端代推本地同一普通提交，回读 main 核实。实验结果另列后续节点。

### 13:05–13:14 北京时间｜20 ms 物理教师、门 WM 和冻结 Actor 的入口失败

- 已核实起步提交 67244fa069109cdafecbf6b5581a160c10fb5d08 普通推送至 main。云端接触工作树与原训练树链接的权重最初少回退一级，`ls -lL` 报 missing；改为原云端权重绝对路径，再验证可读。两棵旧树的原始内容保留。
- 先后运行 `bash scripts/project_env.sh env OPENBLAS_NUM_THREADS=1 python -u -m scripts.b0.collect_contact pull 5 train --output results/raw_large/b0/contact_held_r1 --evidence-dir results/b0/contact_held_r1` 及同 CLI 的 push、0/15、validation、负对照和 0° 持姿变体；完整逐案命令与分组见 data/b0/contact_segments_held_r1.json 和 results/b0/contact_held_r1。首先尝试的 0° 双侧四案失败。首分歧点合力与 5° 对照、修正原理、复测终角列在 reports/B0_CONTACT_SEGMENTS.md。未降低 6 N、5 mm 或 3 s 门槛。张爪失抓及实际不足 20 ms 的末段另存。另采一训练和一验证失抓回合，在相同 MjData 内完成余下五步，保存首失败区间与真实 20 ms 后继。
- 原动作数据实测可由物理范围表达，但早期门姿离旧网络 home 很远。短序列 `scripts/b0/compare_held_contact.py` 用 native33、cpu316、warp316 三入口，均真实执行 2×320 个计分子步，两侧双指标签计数为 278/320、280/320；详细证据在 results/b0/contact_backend_r1。云端和本机的新原始主集按目录 rsync，原始数组不入 Git。
- `scripts/b0/calibrate_contact_events.py` 校准历史完整轨迹、新 held 成功、张爪失抓及旧 C20 碰柱；端点和物理事件来源见片段报告。开发清单 `scripts/b0/register_contact_dev.py` 用阶段合法接触筛选 10×20 个扰动。首次固定上限 1 mm 会排除已验证的名义释放姿态（1.0143 mm），改为不超过同一名义接触穿深加 1 nm，重新筛选，两侧各五项收齐；筛选不访问策略成绩或 H 回合。
- AutoDL `scripts/b0/fit_contact_model.py` 使用成功和失败 episode 真实采集（8训8验）、原 O1 优化器，批量 256；权重和结果分别放 results/b0/contact_s0_wm_held_r1/wm_000200.pt 与 contact_s0_wm_held_r2/wm_002000.pt。第一次预训练 H32 稳定双指 TCP 误差 33.77 mm，续至 2000 个 minibatch 后 23.22 mm；独立样本、模型误差、恒速对照及两处局部导数符号差异见片段报告。继续采用该模型做策略试验，并保留预测限制。
- `scripts/b0/eval_contact_segments.py` 加载实读 B0-03 权重，在 native 3.3/Warp 3.16 各实测十个片段名义初态并留全段视频，两者均 0/10；开发 20 清单未用。动作组替换诊断确认六臂目标单独足以导致前、背首步超力。定位动作范围/初始化风险后，单列尺度和教师监督初始化对照，评测始终使用 Actor 实际输出。
- 首次云端 `bash scripts/b0/env.sh python -u -m scripts.b0.train_contact --run contact_s0_tracking_r1 --updates 200` 未完成正式更新。Warp 拒绝将 torch.int32 以 Python int 传给 from_torch，改为 wp.int32；混合128世界/6400子步复测，前后各64，GPU求得的双指法向力与同一求解的CPU读回最大差 0 N，容量溢出0。另修复前缀有效性，累计检查所有十帧。新 run contact_s0_tracking_r2 从冻结 Actor 和预训练 WM 2000 接续，以相同命令实际启动。冻结 H、C 连续任务和 seed1/2 均未执行。

### 13:15–13:23 北京时间｜接触联合训练、动作标定与真实名义评估

- GitHub main 已回读 0ba3dbdc309322d3005e927153b1fb0d0f6ca5f8，含采集、模型、两后端评估及轻量证据。本机通过已授权 SSH 别名把同一普通 commit 送到云端，再由已登录的 gh credential helper 正常推送；无强推。归档 CSV 的默认 CRLF 曾被 git diff --check 报作行末空白，已转换成 LF，验证表数值不变。
- contact_s0_tracking_r2 在云端于 200 次 Actor 更新端点正常结束。原 O1 机器人 tracking，H32，128 个世界，每个 cohort 先用十个真实 20 ms 动作重建历史，再采至多十六个策略步。共 409,600 个并行 lane 区间，其中 127,122 条属于失败前或可用的真实终止转移；失败后其它 lane 继续积分的状态排除在 replay 外。十帧前缀违规数 0。200 次均记录冻结 WM 与 Actor 权重变化。2,000 次 WM、4,000 次 Critic minibatch；409,600 个七步监督窗中的 307,200 个来自在线物理，余下来自独立教师池。真实计数见 results/b0/contact_s0_tracking_r2/{updates.jsonl,outcome.json}。
- 同一冻结的十项 Warp nominal，更新 50 与 200 均 0/10。200 时六个抓持/开门回合仍在首个 2 ms 超力，前拉约 50.95 N、背推 33.15 N；另外四项的逐案失败见 results/b0/contact_s0_tracking_u200_warp_r2/cases.csv。重新在相同 8 个独立验证 episode 评估联训后的 WM：总体 1/7/32 TCP RMSE 变为 1.554/21.242/62.205 mm，双指 H32 为 30.026 mm；同期总体夹口 H32 误差降至 2.559 mm。可核对训练分布改变时误差分项变化，尚不足以认定单一原因。云端 `scripts/b0/score_contact_checkpoint.py --checkpoint results/b0/contact_s0_tracking_r2/checkpoint_000200.pt --episodes results/raw_large/b0/contact_held_r1/{pull,push}_{0_validation,5_validation,15_validation,5_validation_drop} --output results/b0/contact_s0_tracking_r2/independent_wm_u200.csv`。冻结检查点和 393 MiB 的 cohort_state.pt 分开保存。以 `--run contact_s0_tracking_r3 --resume results/b0/contact_s0_tracking_r2/cohort_state.pt --updates 1000` 恢复了模型、优化器、采样 RNG 和 cohort replay，完成首批新增更新；1000 结果待实际落盘。
- 针对首步六臂目标引起超力，独立变体 `bash scripts/b0/env.sh python -u -m scripts.b0.calibrate_contact_actor --run contact_s0_bc_effort32_r1 --updates 3000`。将六臂与夹口输出单位扩大 32 倍，以末层相反缩放保持初始动作不变；只训练同一 Actor。六条成功教师共 9,705 个有完整历史的训练帧，六个独立验证 episode 共 9,653 帧；给验证使用训练参考，未用验证专属动作/参考作条件。验证上的六轴动作 RMSE 从 0.89948 降至 0.00756 rad，夹口从 32.65 降至 0.934 mm。这是给定实测历史时的动作误差。固定取第 3,000 次监督更新，不按物理结果挑步数。
- 初步真实闭环：该监督初始化（尚未接受接触 H32 更新）在 Warp 名义前拉稳定抓持实际连续 1,500 个 2 ms 步，终角 0.14144°；原生前拉接近闭爪 2,682 步通过。Warp 同项在 approach_arm 参考耗尽。对失败位置的四种同帧离线换历史实验，原状态/只换本体/只换上一动作/两者均换名义历史的六臂误差分别 0.43685/0.15107/0.24264/0.00122 rad；说明两部分均会影响该轨迹上的输出。该判定来自真实动作干预与反事实诊断。另训练 historyswap 命名对照，仅训练时改变部分历史；评测输入仍为实时本体与已施加动作。
- 中断时两条云端正式训练仍在运行，本机部分物理评测停止。确认 `ssh -o BatchMode=yes autodl-dog-arm` 及远端 pid 后保留训练；原生 BC 首批已保存 22 个 case，Warp 首批 17 个，按可核对的轨迹/动作补齐已登记清单。纯 tracking U200 空输出目录保留，新目录 _r2 完成。开发只运行本后端名义通过的子项；完整 C/H 未动。
- 联合初始化对照 `scripts/b0/train_contact.py --config config/b0/contact_calibrated.yaml --run contact_s0_bc_joint_r1 --updates 200`，原 O1 tracking，保持监督初始化所得统计量及原物理采集噪声，Actor 步长取原来的 1/32 以对应新的输出单位；Critic/WM 沿用原步长。另以同一初始化启动 `--config config/b0/contact_task_reward.yaml --run contact_s0_taskreward_r1 --updates 200`，仅增加真实后继/预测后继都可计算的门角、TCP—目标杆、夹口三项，单位分别按 2°/5 mm/2 mm。O1 软奖励与固定成功评估各自保存。已启动的试验仍需独立物理验收，不能用优化步数或离线误差记为通过。

### 13:24–13:31 北京时间｜两后端固定目标，真实窗口修订与联合更新回归

- GitHub 首次传输 c7d564e 时 GnuTLS -110 中断。云端已有完整 Git 对象，原样重试普通 push，本机随后 fetch，HEAD 与 origin/main 都为 c7d564e08e75e57deb20b52dd9c3dda2647a16ce。两端主工作树与大型数组保留。
- 对照命令使用 `scripts/b0/check_contact_reference_segments.py` 及 `scripts/b0/check_contact_hold_tail.py`，固定 20 ms 教师目标与 Actor 共用只读 2 ms 判定器。v1 名义原生 10/10，Warp 9/10；背侧稳定抓持到第 1525 步已有连续 1489/1500 步。复算最后一个真实控制目标跨 11 步即达标。随后 `scripts/b0/collect_contact.py` 单独注册 `config/b0/contact_push_hold_margin_v2.json`，新数据延长真实持姿 1 s；从起点到 v1 原截止位置的 qpos/qvel、ctrl 和真实指载相同。原生/Warp v2 教师分别在 1525/1536 步通过。冻结同一普通监督 Actor 的背侧抓持 v1/v2 均在 1.78 s 首次越角，末角 4.577°/6.825°，两者最长就绪 0/1500，排除该 Actor 仅因旧时限失败。实采与脚本产物见接触报告。
- `--dev --video --resume` 只复用有逐案结果、原始输入与动作可对齐的既有案例。评测脚本新加 resume 后一处函数内 directory 错误使联合模型两端的第一个 trial 中断，原日志和 spec 保留。修正后重新启动两端，重新检查逐案数组与视频。普通监督 native 2/10 nominal，通过的前侧闭爪/抓持各 20/20 开发，50 例总计 110,760 个评测子步。historyswap native 1/10，前侧闭爪 20/20；对应 30 例共 72,041 步。原普通监督中断前已完成的 native 名义与 12 个前侧闭爪开发案、Warp 两名义与 15 个前侧抓持开发案保留。清单 SHA256 c1ddf0486613dfc6786fd695c1f785f63bdc9fb2b8d00c1a10548574c998b525，两监督权重的首八位分别 b667294b、24e11ac2。原生与 Warp 成绩单独统计。
- contact_s0_bc_joint_r1 完成 200 次 O1 联训，270,118 条有效转移。通过 `scripts/b0/eval_contact_segments.py --checkpoint results/b0/contact_s0_bc_joint_r1/checkpoint_000200.pt --dev --video` 运行 native 与 Warp。两者名义均 0/10；两侧各三个在双指抓持中起步的任务均首个物理步超 6 N，失败未进入开发项。两端完整表在 `contact_s0_bc_joint_u200_{native33,warp}_r2`。继续用原奖励与门几何奖励分开判断是否保留监督初始化的闭环能力。
- 为量化首步超力与回报的关系，云端运行 `python -m scripts.b0.compare_contact_entry_reward --initial results/b0/contact_s0_bc_effort32_r1/actor_003000.pt --updated results/b0/contact_s0_bc_joint_r1/checkpoint_000050.pt --output results/b0/contact_s0_bc_joint_r1/entry_reward_u50.json`。每一端各 5 个比例，10 个真实 2 ms 子步都积分以保留奖励后继及最早越界步。前/背从 2.007/1.410 N 升至 7.018/13.199 N，真实 tracking 回报下降仅 0.000034/0.000125。局部回报对真实超力不敏感已证；是否能在想象中预测超力还需检验。启动 `python -m scripts.b0.fit_contact_force --run contact_force_local_r1`，训练和验证独立来源，复用相同初态附近真实恒动作扰动，另以原在线 Actor cohort 检验可迁移性。此诊断尚无政策通过结论。
