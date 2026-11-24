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
| 2026-11-22 | 发布准备；从冻结 B0-03 转入真实接触采集、动态门模型、联合训练与双后端验收 | 发布记录及当日实际执行，见下方分时段条目 |

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

### 13:31–13:34 北京时间｜实测夹持合力的可预测性及针对性联训

- 49a199dc7acde606d3457a796a4fec5ee3774884 已在 GitHub main 回读，内含教师时间窗对照和两后端已收齐的联合训练评分。普通监督 u3000 的 Warp 清单也已收齐，前侧 3 s 抓持唯一名义通过，独立 D01–D20 为 20/20；其他 9 项名义失败。本后端共跑 30 例、56,743 个计分子步、5,678 次实时网络动作，见 contact_s0_bc_u3000_warp_r1。
- 为得到可微但独立于硬裁判的力估计，云端 128 worlds 对两侧各 0/5/15° 的独立 train/validation episode 采样 open/hold 全长区间。每条从 100 子步真实历史恢复，在实际教师动作附近施加随机臂/夹口偏移，保存施加的动作、入口几何、10 个 2 ms 真合力和参考来源（六组训练、六组验证）。命令为 `bash scripts/b0/env.sh python -m scripts.b0.fit_contact_force --run contact_force_local_r1`，12,288 条训练、4,608 条独立来源验证，2000 次固定监督更新。验证前/背 2,304 条各自 MAE 0.945/0.665 N，实超 6 N 的 681/629 条中漏判 66/29，误报 77/43。估计器只能支持软优化，裁判仍使用真实合力。
- 不用新扰动拟合结果替代策略实际分布。单列 `python -m scripts.b0.check_contact_force --weights results/b0/contact_force_local_r1/force_002000.pt --train-config results/b0/contact_s0_bc_joint_r1/actual_config.json --cohorts results/raw_large/b0/{contact_s0_bc_joint_r1,contact_s0_taskreward_r1,contact_s0_tracking_r2}/cohort_{000050,000200} --output results/b0/contact_force_local_r1/online_check.json`。两个监督初始化联训配方 50/200 的原始在线区间共 214 条，其中真实超力 208 条，漏报 0、误报 5；远离标定动作的初始 tracking 队列虽然也都识别超限，其幅值 MAE 高达约 110–420 N，严重超出局部回归适用域。
- 基于上述结果，新命名 `bash scripts/b0/env.sh python -m scripts.b0.train_contact --config config/b0/contact_peak_force.yaml --run contact_s0_peakforce_r1 --updates 200`。沿用同一监督初始化、WM、H32 梯度与几何任务奖励，仅在参考十个子步全属 open/hold 时乘以 1/(1+(F/6N)^4)。物理 F 取十子步合力范数最大值，想象 F 用冻结的当前预测状态＋当前动作回归，不查询真实未来。原价值上界保持 0.16/(1−0.99)=16。代码摘要和模型校验和随本次运行写入 actual_config.json。第 24 次后已实际写入 37,756 条有效转移，等待固定节点与独立裁判。
- 门角/几何奖励变体 contact_s0_taskreward_r1 已完成 200 次 Actor 更新、273,746 条有效转移，原生 3.3 名义 0/10。八个原始 WM 验证 episode 的 1/7/32 步分母为 10,726/10,678/10,478；失抓/滑动为 14/2/0（H32 无样本）。2,422 个稳定双指 H32 窗口的 TCP RMSE：常速度外推 2.94 mm，预训练 23.22、tracking u200 30.03、监督初始化联合 tracking u200 82.79、几何奖励 u200 23.74 mm。与独立物理成绩并列，等待原 tracking u1000 同一评分。

### 13:35–13:43 北京时间｜真实预压、参考残差、长时 TCP 预测与新对照

- 远端 GitHub main 已核对 85ff312d88124ac88237712450a282130b13297f。历史扰动监督变体的 Warp 开发收齐：唯一阳性的前侧闭爪在 D01–D20 通过 10/20，10 个失败均为参考耗尽。普通监督同一后端前侧稳定抓持 20/20。分开保存两种权重。峰值力变体正式完成 200 次 H32 Actor 更新、299,761 条有效在线转移；第 50 次 Warp 0/10，失败形态改变。两侧稳定抓持的首故障从 2 ms 超力变为第 55/41 个子步抓持几何越过 5 mm，两指实际载荷都为零。第 200 次 Warp/native 均 0/10，六个抓持/开角入口均在约 60–64 ms 出现抓持几何失败。复算该变体第 50/200 两个 128-world cohort，完整 open/hold 区间中有 89/40 条整个 20 ms 双指均空载；这 129 条的真实峰值力奖励因子全部大于 0.99。具体证明这个软信号会同时奖励脱离杆件的状态。[原数组复算](results/b0/contact_force_local_r1/contact_occupancy.json)
- 以当时给网络的参考臂姿和两指间距直接作目标，和 6 条训练、6 条独立验证的实际恒目标分别相减。独立验证六臂/夹口 RMSE 为 0.03549 rad/6.776 mm；真实 open/hold 中实际夹口目标比给定参考宽度约小 11.5–11.8 mm。Warp 配对诊断用旧 Actor 保留腿轮 16 路，仅替换臂/夹口 7 路为给定参考，前侧抓持/开 5° 在第 185/445 步失抓，背侧两项各第 75 步失抓，4/4 失败时至少一指实测为 0 N。未以教师动作作推理输入。证据在 contact_q_reference_action_errors_r1 与 contact_q_reference_action_warp_r1。
- 由预压数据决定训练 `bash scripts/b0/env.sh python -u -m scripts.b0.calibrate_contact_actor --run contact_s0_bc_reference_residual_r1 --reference-residual --updates 3000`。给定参考姿态提供六臂和夹口基值，Actor 学习所需伺服偏移；其它十六路仍由同一网络输出，实时使用本体历史，H32 想象用同一参考时钟。固定第3000次监督更新（权重 82b0c16079be0c87b431fb95bdda0e990765e7b2ceeef3b4630bc3d39c346a52），训练臂/夹口 RMSE 0.000729 rad/0.0807 mm，验证为0.02435 rad/3.111 mm，其中持姿阶段夹口为0.049–0.148 mm。Warp 前侧5°实际开到5.0179°且连续满足1489/1500个保持步；背侧5°末角5.19954°、1341/1500。原生同一权重 v1 名义 5/10，通过前侧闭爪/抓持/释放与背侧闭爪/释放，两侧5°/15°均保持不足。监督对照与接触联合学习单列。启动同参数的 `scripts/b0/train_contact.py --config config/b0/contact_reference_residual.yaml --run contact_s0_refres_joint_r1 --updates 200`。本次筛查已验证权重能学习预压及双侧开小角度，v1 的 3 s 标准照常执行。
- 四项小角度固定教师先前均在参考截止的最后一个物理步才达标。新参考协议在新采集之前登记 `config/b0/contact_hold_margin_v2_plan.json`，两侧每个目标统一实采额外 1 s；门角、载荷、安全及连续3秒要求沿用原判据。实际新采完整 20 ms 转移为前5° 1647、前15° 1925、背5° 1639、背15° 1916。新旧协议各自保留，继续同一冻结权重和固定开发扰动重新跑物理。
- 针对 WM 稳定双指 H32 TCP 误差高于常速度对照，在云端从同一 `wm_002000.pt`、同一数据/种子/优化器/RNG 分叉，每组加 400 个 256 样本 minibatch。命令为 `scripts/b0/fit_contact_model.py --episodes results/raw_large/b0/contact_wm_input_r1/* --resume-wm results/b0/contact_s0_wm_held_r2/wm_002000.pt --minibatches 2400 --run <名>`：contact_wm_h7_control_r1 原 1/7 窗，contact_wm_h32_r1 加 `--train-h32`（80个H1、240个H7、80个H32），contact_wm_h32_tcp_r1 同窗再加 `--tcp-loss`（通过可微正运动学监督实测TCP，尺度5mm）。独立2422个双指H32窗口：起点23.220 mm，原窗对照33.819 mm，替换长窗24.746 mm，加TCP监督11.301 mm。后者总体1/7/32为0.710/3.533/16.512 mm，但双指H32门角从起点0.353°增至1.095°，几何预测仍不够精确。已开始独立匹配联合试验 `scripts/b0/train_contact.py --config config/b0/contact_reference_residual_wm_tcp.yaml --run contact_s0_refres_tcp_joint_r1 --updates 200`。16动作在线片段只能提供1/7步监督，此变体另取2个完整32步教师batch，绝不跨重置补长。等待物理验收后判定。

### 13:44–13:51 北京时间｜冻结同一权重完成两后端十项名义，逐项开发继续

- GitHub 已回读 ef76c37177cde89e1056915c4329e46e29ee52f9。确认统一初始化包 `contact_s0_refres_joint_r1/checkpoint_000000.pt` SHA256 d1bf31cec519269a942881ada3a2a607919a1febd7ba128d3dfb595b77152db4，与实际评测的残差监督 Actor 全部 70 个 state_dict 张量（含归一化器）键、类型、值精确相同；与接触预训练 WM 全部 24 个张量相同。此包有 3,000 次 Actor 教师监督、2,000 次 WM 教师 minibatch，接触 H32 Actor 更新和接触在线转移均为零。[逐字校验](results/b0/contact_s0_refres_joint_r1/initializer_identity.json)
- 同一 Actor 的 v1 名义 Warp/native 各 5/10，两个方向的闭爪与释放、前侧稳定抓持均成功，另外5项参考截止。新参考事先固定统一多采1秒；105个名义/开发初态在新旧参考上做同一100物理步重建，实测几何一致，原20条件身份保留。每后端 v2 五项全过，结合原本未改变的五项，协议内各 10/10 名义。Warp 前侧5°/15°终角 5.02786°/15.10693°；背侧5°/15°终角 5.19298°/15.12623°，背侧0° 0.60072°。native 对应为 4.84269°/14.80162°、5.15625°/15.16468°和0.46442°。原判定的持续1500步、两指实载、身体及门体合力阈值都要求满足。不同参考长度改变了 Actor 可见的未来参考和终点时限；两者对策略影响没有单独识别。[版本与条件身份](results/b0/contact_hold_margin_v2_summary/registration.json) · [两端教师清单](results/b0/contact_hold_margin_v2_summary/teacher_controls.csv)
- 各项名义通过后已启动其全部独立开发条件。当时 v1 未调整五项的 native 已回收 82/82 个开发成功（完整五项以最终逐案表为准）；v2 五项的开发在途。持续执行至完整分母。C01–C20 全程及 H 未触碰。
- 相同残差初始化继续原 tracking，`contact_s0_refres_joint_r1` 更新50的 Warp v1 0/10，六个抓持入口首步超6 N，前侧 11.22–11.37 N、背侧 7.68 N，另一组四个站位任务在第1316–2028步偏离站位。动作基值改善了初值的真实表现，原 O1 联训再次偏离可行抓持。为定位和缓解这种偏离，新增独立 `scripts/b0/train_contact.py --config config/b0/contact_reference_residual_prior.yaml --run contact_s0_refres_prior_r1 --updates 200`：训练时在同一想象本体历史与给定参考上，用冻结监督 Actor 对当前 23 维命令加分组 Huber 先验，原 tracking 奖励/Critic 不变。在线动作和验收动作均只有更新后的 Actor。第3次等节点已实记 WM 冻结、参数非零更新与非零先验成本；真实结果待独立评估。本机 6 GiB GPU 负责其更新50名义物理，远端正式训练不设墙钟结束。

### 13:52–14:05 北京时间｜原生 B0-04 达标，进入 B0-05 连续前拉

- GitHub 已回读 f235324f3ef04db6ad5d4c32370c8acc19fe1817。冻结残差监督 Actor 的原生开发全部收齐：五组沿用 v1、五组 v2，每组独立名义加 20 个开发条件，十组都为名义通过且 20/20。结果为同一 seed0 初始化包，含 3,000 次监督 Actor 而接触 H32 为 0。[原生逐组清单](results/b0/contact_hold_margin_v2_summary/actor_native33.csv)。
- 原 tracking 从保存完整 cohort 状态继续至 u1000，572,118 条有效转移、1,981,312 个仿真 lane 区间；10,000 个 WM、20,000 个 Critic minibatch，1,000 次均实记 Actor 更新和 WM 冻结。Warp、原生 u1000 名义均 0/10；初始抓持拉约49.54 N、推约34.55 N。八验证组 u1000 总体 TCP 1/7/32 步 2.692/17.613/51.388 mm、稳定双指 H32 48.195 mm。另对两条未参与训练的真实有限失抓末转移做20ms单步诊断，门角误差0.003407°/0.009581°，TCP 0.962/3.190 mm。详细分母、来源和情况见分层评分与终止表。
- 参考残差初始化后的普通 tracking 与 TCP 损失 WM 联训各自完成 200 次，271,249/274,281 条有效在线转移。两变体在两个后端各0/10。单列动作偏移先验试验已完成 200 次及308,723条转移。其 u50 Warp v1 保住前侧稳定抓持，1/10；五条长持姿 v2 名义全部实际通过，末门角前侧4.714°/14.529°，背侧0.623°/5.190°/15.106°。后端为本机 RTX 3060；开发分项以原始轨迹为准。第一次复用已测名义时本机旧版原生 Python 缺少 hashlib.file_digest，留下空输出目录；以研究环境 Python 验证原五案动作、时钟、视频、权重/清单并复制为 _r2 的种子记录，已登记开发任务继续实际积分。
- 原生接触十项全部通过后才开始新采连续前拉。旧完整 P6 为高频教师，B0-05 使用新命令 `.venv/bin/python -u -m scripts.b0.collect_contact pull 60 train --full-task --output results/raw_large/b0/full_held_r1 --evidence-dir results/b0/full_held_r1`，同参数另跑 validation。整程从规定初态开始，保留 13 阶段、开门后0.5s联合持姿、退臂后和终点各自3s；策略周期内10个子步恒伺服目标。中断时两案均进入 open，只有 CSV 和配置，未写 summary 或完成数组；保留原目录，独立新目录 full_held_r2 重新实际采集。云端训练/开发进程继续，本机中断的 u200 两后端及 u50 扩展开发按原入口 --resume，已落盘名义不重复。

### 14:09 北京时间｜SSH 续接 B0-05，全程教师与冻结片段策略对照

- 通过 dev2-ubuntu 的 LAN 入口执行 git fetch origin，远端 main 与专用工作树同在 f235324；865835c 为祖先。主工作树 fe6cc85 的 H0/P5 变更及未跟踪实验均留在原处。专用树已有未提交全程采集和评估代码。发现 3 个第二平台策略评测和 3 个 AutoDL Warp 片段评测在运行，沿用原进程。
- full_held_r1 中断保留。发现 full_held_r2/pull_60_{train,validation} 均已写实际数组和摘要，依据独立只读判据测名义教师重放，并将同一检查点直接用于无重置全程。命令分别使用 scripts.b0.check_full_contact_reference 和 scripts.b0.eval_contact_segments --full-task --side pull，结果独立命名 full_pull_teacher_native_r1 和 full_pull_u0_native_r1。后续用固定 3000 次监督更新检验全程数据是否改善。

### 14:10–14:15 北京时间｜整程前拉名义成功、后端差异及背推采集修复

- 查到 AutoDL 接触工作目录为 /root/autodl-tmp/dog-and-arm-b0-contact，另一个无 contact 后缀的目录保留无接触实验。实载 B0-03 PyTorch 包，seed=0、updates=1000、collected=1088000，68 个 Actor 张量含观测/目标 normalizer；vendor 双源 HEAD 与规定 pin 一致。本机原始高频教师在 results/raw_large/b0/{native_teacher_20261121_r1,research_teacher_20261121_r1}，云端此次训练读 contact_held_r1/full_held_r2 等恒目标数组。
- 发现云端已有完整前拉监督权重、原生教师重放和两端 u0 结果。SSH 交接时启动的第二平台两个原生检查与云端重叠，分别重现 37,121 步成功和 16,001 步失败；未计作新独立条件。未重复监督训练。命令 bash scripts/b0/env.sh python -m scripts.b0.eval_contact_segments --checkpoint results/b0/full_s0_pull_supervised_r1/actor_003000.pt --full-task --side pull --references results/raw_large/b0/full_held_r2 --backend warp --dev --video --run full_pull_supervised_warp_r1；原生用 .venv/bin/python、--backend native --device cpu 和独立 run。完整原生成绩 60.0075855°/36,630 步，退臂后与终点各 1,500 步；Warp 4,473 步预抓取站位误差 20.788 mm。监督对照先于在线联训。逐步记录与代表视频在报告链接。
- 同原生目标的 Warp 教师重放也在预抓取超时。启动同样 20 ms 采样、改用真实 Warp 积分的独立前拉训练/验证教师，对比源目标的后端适配。采用完整 13 阶段 RSI 的 config/b0/full_pull_prior.yaml，运行 scripts.b0.train_contact --run full_s0_pull_prior_r1 --updates 50，更新 50 完成 81,244 条有效在线转移。两端分别测冻结 u50。
- Native 前拉名义通过后启动 95° 站位背推 train/validation。云端旧 collect_reference.Recorder.finish 将所有子步 reshape(-1,10,23)，两份物理日志虽完整却在最后非整 20 ms 时失败。与专用工作树核对，云端原文件与其旧 git 版本一致；部署现有按实际边界校验的收集器，保留 full_held_r2/push_25_* 原失败数据，独立 full_push_held_r3 重采。两次完成，终角约 25.087°。正在训练背推策略和运行前拉 C 回归。H 未开启。

### 14:15–14:23 北京时间｜同一包完成两侧名义；定位平移与后端限制

- GitHub main 已读回 4a8f2f141cb1f5e5de57442d2176e4110a659110。第二平台没有登录 gh，使用 Windows 登录通过普通 Git 中转发布，第二平台 git fetch origin 读回同一 SHA。云端目录保留为训练/物理运行目录。
- 先以 full_s0_pull_supervised_r1 的权重训练背推 3,000 次；原生名义到 25.029° 后失抓，保持峰值 143/250 子步。随后用两侧完整训练 episode 同训 3,000 次，验证轨迹独立，名称 full_s0_joint_supervised_r1；命令 python -m scripts.b0.calibrate_contact_actor --references pull_60_train push_25_train --reference-directory results/raw_large/b0/full_native_joint_refs_r1 --reference-residual --warm-actor results/b0/full_s0_push_supervised_r1/actor_003000.pt --updates 3000 --run full_s0_joint_supervised_r1。该参考目录以软链接引用 full_held_r2/pull_60_* 和 full_push_held_r3/push_25_*，没有重复复制原始数据。
- 两侧共享的 python -m scripts.b0.train_contact --config config/b0/full_joint_prior.yaml --run full_s0_joint_prior_r1 --updates 50 完成：81,715 条有效在线转移。u0 在原生原参考两侧分别开到 60.049°、25.063° 后失抓，保持峰值 211/250、126/250；u50 在同协议同样双侧失抓。原生前拉单侧联训 u50 单独通过，59.999°，不得与背推另一个包拼成绩。
- 预登记 config/b0/full_hold_margin_v2.json 后，前后两侧各自 train/validation 使用 collect_contact --full-task --extra-full-hold 新采真实 1.5 s 持姿，完整门角和两次停车定义不变。eval_contact_segments --references results/raw_large/b0/full_native_margin_r1 --full-task --side pull push --dev --video 实跑；同包 u0 原生两侧名义均通过，37,583/27,576 个子步，59.9794°/25.0396°。同一包 Warp 两侧在预抓取碰门，开发清单使用各自名义门槛。已启动 u50 加长参考原生对照。
- 在实际 C02–C05 轨迹上运行 python -m scripts.b0.check_full_start_observation --run results/b0/full_pull_supervised_native_r1 --side pull --output results/b0/full_pull_supervised_native_r1/start_observability.json，证实四个 ±5 cm 平移条件初始 Actor 观测与 nominal 完全相同，前 51 个动作逐项相同，四案均败。该结论只确定这些条件的初期输入差异，不把全部失败归给同一原因。
- 原生恒目标分别在 3.16 CPU 和 Warp 重放到预抓取超时，首故障为 8,169/8,170 步；在 3.3.0 走完全程。为检验同后端示范，在原收集入口加入 --backend warp，实际重采两侧完整、各自独立 train/validation，使用 20 ms 恒目标和每子步重算 bias。训练轨迹终角为 60.0501°、25.083°。已启动 full_s0_joint_warp_supervised_r1 和同配方 full_s0_joint_warp_prior_r1；实际结果按后续物理验收。
- 评测参考库原来同时载入未被 Actor 调用的教师命令数组。本次只在在线训练构造 RSI 时读取这些命令，运行策略只需 metadata、有效区间、qpos、qvel。使用只含这四个文件的临时参考目录复算原生成功前拉的第 0/100/1000/2500/3600 帧，23 维输出每帧最大差全部为 0。完整参考和既有训练权重保留。

### 14:26 北京时间｜B0-04 两后端开发验收收齐

- GitHub 已回读 73afe8afad99739ef0559c8fff705a9325629e17。AutoDL 的 contact_s0_bc_refresid_u3000_warp_rest_r1 最后一个背推释放 D20 已有 result.json。按 registration.json 的五项 v1、五项 v2 回读原始逐案 JSON，逐组验证 checkpoint、后端、nominal 及全部 D01–D20 身份后生成 results/b0/contact_hold_margin_v2_summary/actor_warp316.csv。十组各 20/20、名义全过，与原生分表分别保存。v1 全量筛查的失败仍在原目录；不能把改协议后的结果替换回原 v1。
- 原生/跨端重放对照收齐。同一 native 采集前拉恒目标在 CPU3.16/Warp 的预抓取超时仅差一个 2 ms 步，保留两个原始结果；换为真正来自 Warp 的 20 ms 反馈教师目标，Warp 自身的独立裁判重放 36,869 步通过。该配对对照支持后端参考差异，不能据此承诺学习策略跨端成功。
- 对 full_s0_joint_prior_r1 与 full_s0_joint_warp_prior_r1 各自的 u0/u50，使用 scripts.b0.score_contact_checkpoint 单独加载完整 pull/push 的 validation episode，按 1、7、32 步和物理接触模式评分。原生加长参考训练前/后的 H32 TCP RMSE 为前拉 45.25/42.11 mm、背推 55.13/42.97 mm；Warp 原参考为前拉 46.62/52.52 mm、背推 56.11/49.59 mm。数千个滑窗来自每侧一个独立验证回合，不能作数千个独立任务。 u50 在较短时距的改善不足以建立稳定的 H32 预测或完整任务成功。

### 14:27–14:36 北京时间｜Warp 全程末段差 34 ms，登记实采对照

- 已通过 GitHub API 回读 b2de0f282a333158fa256b3a0e448f113178f4c1。第二平台直连 git fetch 两次发生 GnuTLS 握手中断，使用平台已有的 127.0.0.1:7897 代理执行 git -c http.proxy=http://127.0.0.1:7897 fetch origin 后取得同一提交；未改全局代理。SSH 只读加载了第二平台旧 native 与 Warp 两侧 qpos，形状分别为 (3715,32)/(2714,32) 与 (3688,32)/(2706,32)，四个 metadata 均为 held_action_replay=false。
- full_s0_joint_warp_prior_r1 的 u0 改用两侧 Warp 恒目标监督训练，原 0.5 s 持姿/3 s 停车协议下，Warp 前拉达到 60.0729°、退臂后 3 秒已通过，最后停车 1483/1500 子步，缺 17 个子步即 34 ms。背推达到 25.0504°，保持时双指失载。u50 的真实 H32 训练共 81,684 条有效区间，两侧 Warp 均提前在预抓取碰门。两组权重分开保留。
- 针对两个不同失败先后在 config/b0/full_warp_final_margin.json 与 full_warp_hold_and_park_margin.json 登记实采试验。同后端、同一包、两侧同协议：先只让教师最后实际停车 4 s，再保留末端 4 s 并让抓持实采 1.5 s。物理裁判一律要求 0.5 s 抓持、退臂后 3 s、终点 3 s。收集命令为 collect_contact pull 60/push 25 train --backend warp --full-task --extra-final-park，第二组额外使用 --extra-full-hold，独立结果名 full_warp_final_margin_r1/full_warp_hold_park_r1。训练只使用之前独立的训练 episode，两个新参考用于固定权重测试。其中双延长参考在原生两侧均失败。Warp 逐案进展以原始结果为准。
- 用 compare_full_references 核对新增持姿之前的实采前缀。原生推门两版在前 16,045 步完全相同，原生拉门最大根平移差 0.052 mm。Warp 仅延长末端的新旧前拉在修改阶段之前最大根平移差 1.995 mm，背推为 0.092 mm，不能把不同独立采集的全部差异归给延长出来的秒数。16 份完整参考逐条核对 2 ms 步号、20 ms 有效掩码、物理目标在区间内逐元素恒定及真实后继共 51,757 个完整转移；部分尾区间另外保留。[索引](data/b0/full_held_reference_index.csv)
- 已将两套双侧包的 u0/u50 和单侧全程联训 u50 从 AutoDL 直接复制到第二平台，用 torch.load 实载并核对训练计数、WM/Actor 和 normalizer。5 项实际 SHA、两台主机绝对路径与各自最新可恢复队列状态见 results/b0/full_baseline_seed0/checkpoint_inventory.json。另保存原生两侧已成功参考的 train 原始数组。Windows 仅作 SSH 与轻量 Git 传输，本地无研究数据压缩归档。
- 原生前拉单侧监督 C01–C20 已完整收齐，为 8/20。统一包两侧的 C 清单继续。同一实际工况统计一次，C01 与单报的 nominal 为相同配置。后端对照不增加独立 seed 数。新增脚本 index_full_baseline 将以完整原始阶段事件和两个实际 1,500 步窗口核对逐案表。

### 14:41 北京时间｜Warp 两侧完整名义通过，交叉换后端均失败

- Warp 实采双延长参考使固定 full_s0_joint_warp_prior_r1/checkpoint_000000.pt 完成前拉 59.9505579°/37,374 步，背推 25.0258114°/27,513 步。两端各自 13 个物理阶段、两段独立 1,500 步停车，Warp 的两案 max nefc 56/57、max ncon 均 18、缓冲溢出位均 0；库对 capsule–mesh 的 MULTICCD 提示保留。ffprobe 读得前拉 1,870 帧/74.80 s，背推 1,377 帧/55.08 s。先做的只延长停车对照前拉通过，背推保持失抓。双延长参考在原生的交叉结果为前拉退臂超时、背推 6.271° 抓持几何失败。
- u50 在相同加长协议上的复测：原生参考包两侧退臂后保持及收臂已过，倒车到站未达，分别 59.9837°、25.0449° 耗尽参考；Warp 参考包两侧均在预抓取提前碰门。原生单侧前拉 u50 全部 C 实跑后 9/20，监督 8/20。冻结比较均保留，不用最优单侧拼两侧。
- 两侧共同包的原生和 Warp 完整开发清单继续。新 Warp 入口 --dev-workers 4 先实际跑完各侧名义；每侧使用四个独立进程及独立 case 目录，所有 worker 加载同一检查点、同一两侧参考，逐个取得实际 next state。程序在所有子进程正常结束并读取每个 result.json 后才汇总。单侧对照和已有进行中任务按原进程运行。没有设置后台墙钟终止。

### 14:42 北京时间｜接续进程全部回收，补齐真实 H32 片段成绩

- GitHub 已读回 6cbf2eef0fe9188356f0af47f3b4c440eb9520ac。工作开始时第二平台的三个评测均已自然结束。contact_s0_refres_prior_u50_margin_dev_warp_laptop_r2 收齐 5 个名义和 100 个开发案例，五组各 20/20；v1 版本的 u50 名义仅 1/10。原 v1 下 u200 在 native 5/10、Warp 2/10，通过名义的项目才展开；开发分别是 100/100 和 40/40，逐项分表，保持这些 H32 结果与全十项监督包的区别。原始中断目录仍保留。该数据已纳入接触报告。

### 14:53 北京时间｜两套联合包前拉 C01–C20 均为 9/20

- GitHub 已回读 9987eb353c0f0a12b5ce2878e6767a7820a7b7c1。两套双侧包使用各自冻结的参考、权重和后端，完整前拉开发各 9/20，两端通过编号都为 C01、C10–C17；每案均从原始初态独立积分。C10–C17 依次覆盖轮/指摩擦和铰链摩擦/阻尼两档变化。C02–C09 与 C18–C20 的终止原因按逐案首故障保留，不以到过某一门角计分。
- 对两套统一包再次用实际 C02–C05 与 nominal 的输入比较：初始传感历史和 Actor 参考最大差均为零。原生的前 51 个网络动作精确相同，Warp 的最大绝对差约 1e−7；这组平移差对 WM 的参考输入可见。四条成功名义视频均使用 ffprobe -count_frames 通读，原生前/背 1,881/1,380 帧、Warp 前/背 1,870/1,377 帧，实际视频时长与计分物理时长差小于 0.08 s。背推两端 C 继续。

### 15:04 北京时间｜B0-06 以 seed0 限制基线收尾

- 本轮最后两个全程清单已自然结束并写入 evaluation.json 和 cases.csv。原生和 Warp 的共同包各自前拉、背推均为 9/20；四组通过编号均为 C01、C10–C17。两端完整背推各有 11 个失败，原生包括 4 个操作阶段外碰门、3 个机器人碰面板、2 个抓持超时、1 个非抓持夹指接触、1 个停稳超时；Warp 依次为 4、3、2、2、0。前拉两端均为 5 个提前碰门、4 个驶近超时、1 个抓持超时和 1 个夹爪基座碰把手。
- python3 -m scripts.b0.index_full_baseline --output results/b0/full_baseline_seed0 --runs <24 个实测全程 run> 校验逐案记录，输出 full_case_index.csv 与 full_scores.csv（24 run、40 个分侧名义、120 次完整开发回归，总 160 条；各变体间复用 C 身份）。每个通过项目均查到连续完整的 13 阶段，两个独立保持分别 1,500 步，每个应当展开的 C 清单都含 C01–C20。中断和教师重放不计入这个学习策略索引。原始前拉/背推的失败也完整保留。
- 两套候选分别冻结原生/Warp 的同一双侧包，完整权重在第二平台和 AutoDL 两端逐字节 SHA 相符。已在 AutoDL 确认三次全程联训的最新 cohort_state.pt 均可访问。未达到 18/20 开发门槛，不复制 seed0 冒充独立 seed1/2；两条新训练链和注册 H 两侧各 50 个条件的任务评测均未执行。主模型和原始数据没有 reset/clean，没有实机动作。B0 相关云端训练、评测和第二平台接续进程已结束。
- reports/B0_BASELINE_REPORT.md、reports/B0_FULL_TASK.md、PROJECT_STATE.md、prompts/NEXT_RUN.txt 与本日志按实际出口同步。下一次有明确开发任务时先检验相对站位/把手平移观测；保留现有门角、抓持与停车判据。上述最终材料随本次普通提交保存。


## 2026-11-23｜已结束 B0 最新轮的独立审查与下一步计划

记录时间：2026-11-23 19:27（北京时间，Asia/Shanghai；这是本条文档记录时刻，不是上轮实验起止）。本日这次工作是仓库证据审查与计划发布，新增训练 0、物理任务评测 0、硬件动作 0。

### 用户目标、实际环境与读取范围

用户确认“最新一轮已经结束”，要求仔细审查、把下一步计划推送 GitHub，并给出启动提示词。沿用此前“一个单独文件逐日详细记录做了什么、解决哪些问题”的要求；本文件继续作为唯一逐日日志。

本次在独立审查环境恢复仓库工作副本，读取 origin/main@2c15d35eab4c6c24954ce1d67ae09f0247e1725b；最新提交题为 Include the Warp run manifest and identify the two SSH reproduction checks。相对上一计划提交865835cab27891b6627aa94b52287c27d5f3971c，本轮14次提交、2062个变更文件。没有连接用户现场训练主机，没有触碰其主树H0/P5修改；上轮进程已结束与权重跨主机一致来自已提交记录，本次不冒称重新在线确认。

三个并行审查任务分别负责学习代码/官方调用链、实验数值与视频、报告/日志及原计划约束，主任务交叉核对并统一文档。阅读本轮接触实现、配置继承链、采集/训练/评测与物理裁判，固定O1想象环境和Actor/Critic学习器；读取新增阶段报告、全部新增日记段、初始化/冻结/权重/参考清单。

新变化的results/b0、data/b0、config/b0范围共2020文件、53,690,562字节；1535 JSON全部解析，100 CSV共43,941数据行，24 JSONL共5781记录，无解析错误。新增351视频均读取文件字节，其中40段完整任务视频完整解码36,262帧，人工抽查每段首/中/末共120帧，未见明显报告冲突；其余311段未逐段解码/观看。没有将完整字节读取或解码写成逐帧人工语义审查，也不声称读取了不可见的全部历史对话。

### 逐案核对得到的实际结论

1. 接触400开发＋20名义逐案JSON与CSV一致。两个后端使用相同200个注册条件，各10项×20，全部通过。扰动XY±0.5mm、yaw±0.025°；初态/真实前缀合法性筛选排除了648个候选。每条开发均100物理步初始化前缀，不计入策略保持；训练RSI也有该前缀。小范围片段成绩不能和完整C的±50mm/±5°泛化等价。
2. 完整索引24 run、160记录＝40名义＋120开发，逐条成功、终角、步数和失败身份与JSON一致。全部完整记录从frame0开始且前缀为0。最终四组各9/20，只通过C01/C10–C17；四条当前nominal和36条当前开发成功均有13完整阶段与两段各1500步独立停车。没有发现用到达某门角代替完整成功的计分问题。
3. 两套包分别支持本后端两侧名义，不是同一套权重跨端成功。native来源u0→Warp两侧提前碰门；Warp来源u0→native前拉退臂超时、背推抓持几何失败。未展开的C保持“未执行”，不能记0/20。
4. 成功u0已有教师监督：接触BC3000/WM2000、接触H32=0；全程双侧Actor也已做3000次监督。ReferenceResidualActor将当前参考六臂/夹口显式作为前馈基值，再加网络残差。评测没有教师IK/导航接管，但也不能称23路完全无前馈网络输出。
5. 纯tracking接触1000次H32、572,118有效在线转移（不是1,981,312仿真lane区间），两端0/10。全程两组50次H32都在Warp交互，native来源81,715、Warp来源81,684有效转移；前者“native”不是训练后端。统一双侧u50未保持名义成功。单侧前拉8/20→9/20与五个v2局部H32子项通过保留，不能概括H32永远无用。

### 新识别的问题、证据强度与尚未解决项

- 已证实的输入缺口：C02–C05纯平移在Actor初始输入中不可区分，前51动作native相同/Warp仅浮点差；WM goal能区分。Actor参考540维省去了WM参考570维中的相对根平移。此证据只覆盖四个平移条件，全部修好也仅13/20，不保证偏航/门初角/组合条件通过。
- 已证实的学习信号差异：DoorImagination仍继承只看根高度/倾斜的官方soft done；真实过力、失抓等没有完整进入想象终止。replay真实reward/done被记录，并不自动成为官方Critic的目标；后者使用想象rollout。训练ContactPlant的参考phase审计也不等于完整任务裁判的事件进展/操作区/超时。已有力奖励变体不能忽略，但仅减力会鼓励失去接触，须同时考虑正确抓持与进展。
- 模型证据重新分组：同一验证回合双指H32 TCP误差，native拉26.012→36.769mm/推22.761→52.326mm，Warp拉27.283→48.604mm/推25.324→48.595mm；常速对照1.8–2.6mm。native总体平均反而改善，故总体loss不能代表接触质量。按分组窗口数重汇总与原all指标一致，但本次没有原始预测数组，不能称逐向量重算。四组loss_or_slip均无窗口，亦不能证明失败恢复预测已学会。
- Critic初始化/价值梯度是待验证机制：首层新初始化、后续层迁移，官方先通过末端bootstrap更新Actor再拟合Critic。Policy/reward包含末端价值，不能当纯即时奖励；需要分解后再断言退化来源。已经排除“Critic完全看不到门”的错误猜测，实际输入75+570+5包含门与相对几何。
- 在线最长16步而想象32步、全程u0沿用小角度WM初始化，需要数据分布与长窗验证；现有RSI余长足够，未发现常规H32直接越参考尾端的证据。完整reference_exhausted与未来槽置零敏感性分别处理。MULTICCD警告也不能直接作为后端差异根因。
- 本轮未跑旧计划两个50000更新区块，不能声称耗尽预算证明方法不可行。以具体观测缺口和实测退化转诊断是合理决定。seed1/2与H任务测试继续未执行。

### 本日文档改动与下一轮决定

新增 reports/B0_REVIEW_20261123.md，保存成绩分母、连续物理证据、监督/H32区分、源码机制、模型分组表、后端问题和每项结论的依据。新增 docs/B0_RECOVERY_PLAN_20261123.md，固定Warp参考/采集/评分主线，以已通过u0为能力锚点，安排三个有依赖的工作包：A相对站位输入＋扰动教师覆盖；B真实/想象目标、Critic/模型梯度与H32配对；C三后端首次分歧定位。

交叉审查修正了计划中的两项潜在混杂：历史A0的9/20仅作能力锚点；本轮另做相同初始化/固定参考标签/新增BC预算的配对A0，再比较输入和覆盖。最终H32候选仍须十项接触片段名义与每项开发≥18/20，完整门0.5s保持不能代替小角度3s保持；不要求每个诊断节点重跑旧400案例。短H诊断若必要，要贯通真实CLI/learner/采样余长/窗口/日志，不能仅改YAML。

同步 AGENTS.md、PROJECT_STATE.md、README.md、docs/RESEARCH_ROADMAP.md、docs/B0_SUPERMIMIC_PLAN.md，旧 docs/B0_CONTACT_EXECUTION_PLAN.md顶部标记历史与新入口；重写 prompts/B0_START.txt 与NEXT_RUN。纠正了仍说B0-04尚未实现的过时启动信息，保留旧正文、阈值、冻结和独立seed规则。

下一轮先受控诊断，随后最小适配集成、seed0训练与完整回归；最终同一候选的十项接触、双侧完整C各≥18/20、同包跨端nominal与H32机制证据达标后，才继续独立seed1/2（各自先过B0-03）及三个候选冻结后的H任务测试。H32能力保持与独立收益分开，不把BC改善归给模型式优化；未达标则准确冻结限制，不自动进入R1–R8。继续详细逐日日志、不设置后台墙钟kill、不重做P6/G1、不做硬件或本机压缩归档。

### 核对、提交与执行状态

本轮改动限定11个文档/提示文件，不修改学习代码、任务门槛、原始评测结果或旧失败记录。已完成差异/空白检查，新文档与已改入口的相对链接全部可达；冻结复核命令的参数和环境脚本已按当前源码静态核对。两份新文档经过代码、数值与原协议交叉复核，并修正了A0对照混杂、最终接触回归、独立seed先过B0-03、短H真实接口和Critic迁移语义等问题。没有为文档变更新增测试套件或启动物理实验。远端发布结果在本次回复给出。

已确认读取最新远端2c15d35及旧计划865835c；本条与新计划随题为“Review completed B0 round and define controlled recovery plan”的普通文档提交保存。发布时核对远端未被其他提交推进，以预期旧HEAD进行快进更新，不强推；本提交自身的确切commit在发布完成后回复，后续日志可引用，不为嵌入自己的提交号制造重复提交。

### 19:37–19:41｜接续实作启动，恢复冻结输入

第二平台 b0/contact-baseline-20261122 从 2c15d35 正常 fetch、pull --ff-only 至 b9a11293；当时 origin/main 无后续提交。主树 fe6cc85 的 PROJECT_STATE、H0 文档和脚本以及未跟踪 P5 目录另有工作。专用树既有环境链接和两段视频保留。主机 RTX 3060 Laptop 6144 MiB、空闲内存约 12 GiB、研究分区可用 332 GiB，当前无 B0 训练。经第二平台可访问 AutoDL，RTX PRO 6000 97887 MiB 已用约 6151 MiB，数据盘余 269 GiB，另有 MCP-RL/DN-Splatter 进程；旧云树 67244fa 有既有源码和未跟踪实验，另建接续工作树。固定上游两项 git rev-parse 与规定提交一致。
在第二平台用 scripts/b0/env.sh 的 torch.load 实载 full_s0_joint{,_warp}_prior_r1 两套 u0/u50，四包均包含 Actor 70 项、WM 24 项、Critic、cfg、seed、updates、collected；motion normalizer 原宽 540。实际 CUDA 张量求和通过。full_warp_hold_park_r1 的拉/推 qpos、qvel、action_clipped 与 valid_full_interval 均可读取且有限，动作分别 3787/2803 行；这是打包动作行数，完整 20 ms 行另按 valid 标记过滤。前轮成功、失败包保持冻结。本轮先测相对平移可观测性/教师覆盖、H32 即时与末端价值梯度和三端 2 ms 分歧；截至本条尚无新增策略成绩。

### 19:43–19:46｜训练环境隔离、观测证据和 A0/A1 配对训练

AutoDL 自身 HTTPS fetch 遇到 GnuTLS 连接中断；从已正常 fetch 的第二平台将相对云树已有提交的 Git 对象经 SSH 传到同一 Git 对象库，在 /root/autodl-tmp/dog-and-arm-b0-recovery 建独立 b9a1129 worktree。复用原环境、物理资产、固定参考与四个验证权重的链接，未 checkout 旧云树。云机磁盘 269 GiB 可用，未处理其他 GPU 进程。开发、整合与普通推送使用第二平台的专用树。
在固定 root/参考上用旧 Actor 的真实 Warp 闭环观测比较双侧各 12 个开发初态、各 51 个动作。初始 C02–C05 的平移只在 WM goal 可见；C06/C07 的 yaw 已能区别。C08/C09 的 540 列和 570 列、历史、首动作都相同，前 51 帧最大动作差约 1e−7，而前拉真实把手相对 TCP 的最大分量分别偏 25.21 和 62.74 mm。输入增加平移仍缺门初角信息。结果 results/b0/recovery_a_observation_r1。登记 16 条独立扰动教师（seed 231123），每侧 6 train/2 validation，不取 C/H 轨迹。首条扰动前拉实采全程通过；20 ms 完整转移 3872，固定参考同相、有效的正样本 2788。两条时钟在驶近终点相差约 2.178 s；不能把越相位的物理动作当同帧监督。
实现 privileged_reference_translation，新 goal 把十槽 XYZ 附在旧 540 列后；部署和想象共用 DoorMotions，旧列统计保持，新列固定 0.05 m 标度。云端实际运行 scripts.b0.recovery_bc --variant A0/A1 --run recovery_bc_A0_r1 / recovery_bc_A1_r1，各用相同 6588 个名义完整恒目标样本和 128 个新增 BC minibatch。A1 的旧包动作迁移差 5.96e−8。两者训练集轮速 RMSE 均约 0.005892 rad/s、臂角 RMSE 0.000304 rad，物理任务另行评测。新增 H32=0。配置/更新/拟合误差已回传；完整包和 optimizer/RNG 留在云树。B 和 C 独立目录另行回传实际结果。

### 19:47–19:55｜同包跨引擎定位，固定时钟教师核查，H32 第一节点

配对监督入口 bccb5f25 已普通推送并用 GitHub main API 回读。第二平台仓库未配提交身份及 HTTPS 推送凭据；使用前轮 Codex 提交身份，Windows 认证中转只传正常 Git 提交、快进推送；第二平台的现场修改未进入中转。A0/A1 的前拉与背推 Warp nominal 均连续通过；前拉均 37352 步，背推均 27506 步。C02–05 专项在跑。
固定 Warp u0 与同一参考，在第二平台三套原始引擎上各做双侧闭环。native 3.3 拉 31310 步退臂超时，推 10611 步抓持几何失败；CPU3.16 与 Warp3.16 各两侧通过。还用同一 q/v 及目标做两侧各三段 2 ms 对照；首次轮地接触在第 16–18 ms 区间出现 4 与 10 接触点的分歧。在 CPU3.16 上只改轮胎最深支撑点，预抓 TCP 相对 native 的最大差从 0.819/1.444 mm 降到 0.00000274/0.00000190 mm；两侧闭环却在打开阶段失败。仅关 MULTICCD 双侧均通过。将其与最深轮地支撑合用后，拉同第 31310 步退臂超时，推第 10619 步抓持几何失败。原始引擎及其正式门槛继续沿用。定位窗口、闭环结果和反事实命令见 reports/B0_RECOVERY_BACKENDS_20261123.md。
扰动实采教师另用同一冻结参考回放裁判。原名义教师两侧通过；第二条背推纯 XY 教师也能通过，而首组 XY 的前拉/背推末段分别只保持 1141/1453 步，规定 1500 步。前拉初门角 4.117° 的组合扰动，在距自身预抓端点 <0.1 mm 时距固定评分端点约 52 mm，冻结判据下 17.62 s 超时。同相位布尔掩码无法消除阶段内的物理进度与目标冲突，证据在 results/b0/recovery_a_teacher_r1/judge。接续预登记单列 A4：在 A3 的平移输入后加一个当前减同帧参考的门角（弧度）。再单列只改四轮输出、固定参考驶近阶段激活的残差；第一条平移数据首秒四轮教师目标相比名义 RMS 差 0.669 rad/s，六臂无差异。原冻结 Actor 名义驶近区间相对教师的根平移偏差最大 0.205 mm、yaw 0.00084 rad，因此登记轮路残差死区 1 mm 和 0.002 rad，继续用原判据闭环验证。
H32 原 tracking 对照从同一完整冻结包（包括实际 Critic）出发，关闭训练时动作先验。命令 scripts.b0.h32_recovery --variant tracking --updates 1 --run recovery_b_tracking_u1_r1。64 lane×40 连续区间，收集1558条有效20 ms转移，30个lane有终止。更新10次WM minibatch、H32 Actor 1次、Critic 20 minibatch。64个想象起点的平均折扣即时项2.66565、bootstrap 2.81757，相应Actor梯度L2分别0.29062/0.65457，余弦0.09669，末步生存率均为1。该 u1 前拉59.93878°/37513步，背推25.03537°/27614步，双侧 nominal 能力保持；H32 独立收益和完整 C 仍待同条件评分。

### 19:55–20:06｜完成全批教师与五个配对监督训练，检验首动作与短窗失效

f16096948 已普通推送 main 并读回。云端又实载原两套 u0、u50（SHA 对上原权重清单）及两个 u50 完整 cohort 的 optimizer、replay 队列、CPU/CUDA/NumPy RNG，实读三个根目录共 10 个完整参考/验证 episode 的 q/v、动作、掩码与2ms轨迹。精确物理路径见 results/b0/recovery_round_20261123/recovered_inputs.json，代码与大数组分别保存。原持姿加长 Warp 库只有两条训练参考，验证读自原 Warp 库或新独立 episode。
教师 16 个独立 ID 全部落盘，第二平台前 4，云机后 12；固定模型版本和参考一致。训练 12 条 39864 个有效转移、30939 个可 BC，验证4条10912个、8290个可 BC。两个短开夹回合分别丢双指40/41子步再恢复，两长开夹验证均失抓，补足真实20 ms后继。共同冻结裁判完成3/16；10条预抓超时，3条终点时钟耗尽。没有使用逐 C 教师轨迹。详见 reports/B0_RECOVERY_TEACHER_20261123.md。
云端逐个执行 scripts.b0.recovery_bc --variant A2/A3/A4，各128次，同一冻结时钟。五变体均用同4个独立验证回合评分，A0/A1 的轮速RMSE约0.150591；A2/A3/A4为0.140149/0.140105/0.140105 rad/s。带平移的A3在两侧±50mm干预下最大首轮速变化仅约1.7e−5 rad/s。轮路专项单独拟合1200次，固定接近阶段/动作主干，验证轮速0.38579→0.14783 rad/s，首动作可相差0.7091 rad/s，完整闭环另测。在实际/想象输入检查中，0.05 m世界平移不改变旧540列，新增平移和门角通路对预测根、预测门角的梯度可读，门角导数为1，尾部9个无效XYZ槽为零。
B 的现策略附近另采13个40步cohort，以独立cohort分训练/校准/验证。独立5124真实转移中79次硬终止，冻结官方软终止即使输入测得后继根也未检出；单独事件头真阳性17、漏62、误94，未纳入想象。补100次全程WM更新后，策略前拉双指H32 TCP误差42.37→27.76 mm（146窗口），旧验证背推释放25.20→35.41 mm。新策略分布与旧分布方向不同。多次H32及价值适配另做闭环和分组。

### 20:06–20:08｜出现同包跨端名义改善，转入标准接口与完整开发回归

1223501316 已推送并读回。单纯用对齐标签微调六臂输出层后两端各 0/2；独立的站位补偿实验冻结主干，使用给定参考的离线六关节雅可比和当前根偏移修正臂参考，在 886 个同钟同阶段、TCP目标差≤2 mm、方向差≤1°的真实训练标签上拟合一个受限系数，取 1.0（无约束解 1.339）。同一共同包，无后端ID，在未经修改的三套原始物理的 nominal 两侧均过，native3.3 59.97719°/24.99422°，CPU3.16 59.96336°/25.03851°，Warp3.16 59.96575°/25.02911°。路径 recovery_c_stance_*_r1。这是解析补偿与已监督 Actor 的组合，新增 H32=0。
新标准包 recovery_c_s0_stance_integrated_r1/checkpoint_000000.pt 位于第二平台和独立云树，SHA256 7f86370f47d549ce6a1570a8d66f3996abb80708f50162ba42a5927cb5dff61f。Actor goal 540→546，在原列后加六个基于真实/想象当前根的参考雅可比修正量，71个实测参考/不同根位置上与独立推理对照最大归一化动作差 5.96e−8，导数与有限差分差 <4.7e−7 rad/m。已按标准接口启动 Warp nominal 和全 C、原生 nominal 以及同源 H32 复核。其它分支不与它自动叠加。

### 20:08–20:18｜标准三端验证与站位、门角的后续最小适配

3c9106ac 已普通推送核对。相同 546 维集成包经普通 eval_contact_segments 入口完成原生两侧 37056/27948 步，终角 59.97744°/24.99503°；第二平台 Warp 两侧 37373/27514 步，59.96510°/25.02920°。源初始 Actor 的权重与原 540 列统计保留，6 个新增网络列为零，解析臂修正参与真实/想象前向。标准云树在同一固定参考上逐案扩展完整 C，第二平台同时按 --extend-from recovery_c_integrated_native33_r1 扩展原生完整 C。复用名义前重做两个真实输入时刻的动作，比较配置与参考、保存来源清单。新 C 均从零独立物理评分。
A0/A1 双侧 nominal 全过，但平移各0/4；A2/A3/A4 虽降低未见教师的动作RMSE，双侧名义在8173/8183步均因操作阶段外碰门失败，前拉合力约0.45–0.50 N，尚在禁止碰门阶段。A4 额外门角输入没有使这次训练恢复能力。保留这些失败并继续专项：四轮反馈独立验证降误差、双侧名义保持，但前拉C02–05全部驶近超时。前四条平移/组合教师在前261帧的腿角目标与名义RMS差0.0257–0.0653 rad，最大0.0864 rad，轮速修正缺少相配合的腿姿。按真实教师中12个腿目标的一维偏航分量，单独在同一轮控制上拟合一个有界偏航速率，使用中性姿态足端Jacobian将它映射回腿关节。训练/验证3131/1044帧，1200次小网络Adam更新，未动原Actor或已拟合的轮头，验证偏航速率RMSE从零速对照0.03406降至0.00579 rad/s。完整物理仍由冻结裁判逐案检查，diag离线损失不作为任务成绩。
端点教师分支只用两条训练身份的真实再采。+3.683°前拉在固定接近端点发生夹爪基座碰把手；+2.807°背推可抓持，第一版过早释放在冻结hold阶段失败。只将允许释放的最早物理时刻锁到原有参考，背推独立重采在冻结裁判上27527步完成13阶段、两段停车各1500步，终角25.08054°。另在原 C08/C09 的初门角（2°/5°）做静态端点核查，未改物理。固定接近端点处，前拉夹爪基座到把手的有符号距离分别+12.82/-24.71 mm，背推+48.51/+72.61 mm。前拉5°在512个容差边界扰动样本中均相交；这是固定该门角的几何诊断，不能据此排除接触前已合法改变门角的控制路径。原始表 results/b0/recovery_round_20261123/fixed_endpoint_geometry_C.json。小角度背推合法教师可单列用于后续动作监督，不回填原A0–A4。

### 20:19–20:37｜真实 H32 同包跨三端与完整站位诊断

eb79802e 已普通推送并核对 GitHub main。标准 546 维共同包的无动作先验 H32-u1 使用 1558 个有效在线转移，30 lane 记录物理终止。WM 末层变化0.001889，冻结 WM 后的 H32 Actor 梯度范数0.60341、末层参数最大差6.251e−6，随后 Critic 末层变化0.001684。该更新后单一pt在三端分别读自身实时状态通过双侧 nominal：Warp 前拉59.960025°/37490步、背推25.028641°/27601步；native3.3 前拉59.973016°/37110步、背推24.990748°/27192步；CPU3.16 前拉59.95972°/37489步、背推25.03701°/27600步。原机制在这次真实更新后保留了跨端名义能力。两项适配的作用仍分开：u0获得跨端名义首先来自站位臂补偿；是否有H32独立收益看同信息物理配对。
第二平台同包u0 native完整 C 已逐侧20案跑完，各9/20。云端u0/u1及第二平台原生u1完整C均推进中，有些分支的已观测失败数已使18/20不可达，继续完成冻结清单保留实际分母。没有启动封存H和独立训练。原540维无补偿H32-u1在原生双侧均失败；严格同批u1的末端bootstrap保留或分离两组在Warp nominal都能双侧通过。独立分解进一步以63维初始状态/真实前动作及历史、真实前缀与重启的求解条件完全相同的物理分支对照，u1的12个H32几何方向为6同/6反；分阶段为自由1/4、双指3/4、释放2/4。真实终止TD-u5与忽略终止的额外Critic拟合对照在Warp也均过名义，不能将保持能力单独归给终止掩码。最新逐时距/模式分母见 reports/B0_H32_RECOVERY_20261123.md。
监督四轮专项在Warp双侧平移均0/4。增加腿部偏航速率后，第一版还将最终腿姿延续到停车段，双侧名义参考耗尽。同真实输入对照显示，前拉初始驶近至stow均无额外腿修正，只有retreat_base发生78帧、final发生231帧，最大约0.000710 rad。关闭监督阶段外的延续后保持权重完全相同，双侧名义恢复通过，双侧平移仍各0/4；部分在第2661步失稳。未改时钟或延长停车。
固定端点背推教师用于新增门角臂/夹口监督，原骨干冻结、公共参考分相位进度，所有双侧名义训练帧的附加量为零。新包保住双侧Warp名义；背推C08从以前的抓持超时推进到实际确认双指、打开至24.137°后失抓；C09抓持超时，门被推到约39°，两案均记失败。
因扰动教师的驶近时长与公共时钟失配，另在注册的16个独立扰动起点及两侧名义真实采集至固定settle末端。保持原网络，按中性足端Jacobian将横向/航向误差映射至腿姿，纵向/航向速度误差映射至四轮；三个非零的单标量速率及同批无补偿对照（0/1/2/4 每秒），每组有实测20ms相同行为窗口。预先按12训练回合末600ms的10 mm/1°稳定跟踪和最大平移误差选速率，validation不参与。无补偿3/12、新配方12/12；四个独立验证由0/4至4/4，最后600ms的最大平移误差在4个验证回合的中位为2.684 mm。此次72条完整局部轨迹没有触发采集硬失败。它只检验规定时钟内停到站位；已另建单独包和加上已验证臂补偿的共同包，用完整原始裁判检验全过程。命令 scripts.b0.calibrate_planar_stance --run recovery_planar_calibration_r1，完整物理评价在 recovery_planar_screen_warp_r1 和 recovery_planar_arm_screen_warp_r1。

### 20:40–20:46｜按用户要求切换为第二平台管理的 AutoDL tmux，停止聊天内等待

f0812006 已普通推送并通过 GitHub main 回读。原生 3.3 的同包完整 C 两组已结束：546维站位臂补偿 u0 前拉9/20、背推9/20；同初始化同协议真实H32-u1 前拉9/20、背推10/20，背推新增 C08，其余通过项相同。这是单seed、单侧多通过一个固定开发条件；跨侧≥18/20门槛未过。更新后同一包 native3.3、CPU3.16、Warp3.16 双侧名义均过。u5前拉到退站时11.59mm，超过10mm到位要求，固定参考耗尽。上次只学到端点的前拉高角失败已保留，另独立训练角2.25574°的前拉校时教师实测通过；背推4.09980°教师抓持失败，不作为成功标签。真实权重、优化器与原始物理数组仍按对应平台恢复。
用户要求稳定后退出。第二平台通过 ssh autodl-dog-arm 在 /root/autodl-tmp/dog-and-arm-b0-recovery 启动 tmux b0-recovery-20261123:jobs。守护登记当时仍活动的本轮7个评测工作项及1项本轮平面/臂包的原生名义验证；完成状态以各 run 实际写出的结果文件判定。既有进程继续原位计分，不中断正在仿真的 case；同一 worktree、run、参数和后代进程均已查验后才尝试恢复。标准 evaluator 使用 --resume，已完成案例保留；单案例未完成材料另存 interrupted。退出 SSH 后从第二次新连接核对，tmux detached、pane_alive，守护PID165986，直接派生的实际原生物理评分PID165989已落盘前拉结果，原有长回归完成计数也在增加。登记与20:45实际快照见 results/b0/recovery_tmux_20261123。较晚形成的完整C分母交由后台回收。第二平台 tmux b0-receive-20261123 承接小结果、汇总与普通推送，原始大数组/pt不进Git。没有开启H、独立seed或设备。

## 2026-11-23 21:12 北京时间｜tmux 物理评分回收

- recovery_b_phase_td_u10_nominal_r1：pull 名义失败，开发未测；push 名义通过，开发未测
- recovery_b_stance_u1_full_c_r1：pull 名义通过，开发9/20；push 名义通过，开发9/20
- recovery_b_stance_u5_nominal_r1：pull 名义失败，开发未测；push 名义通过，开发未测
- recovery_b_tracking_u1_full_c_r1：pull 名义通过，开发9/20；push 名义通过，开发9/20
- recovery_c_integrated_warp316_r1：pull 名义通过，开发9/20；push 名义通过，开发9/20
- recovery_endpoint_hinge_tail_warp_r2：pull 名义通过，开发未测；push 名义通过，开发1/1
- recovery_planar_arm_native_tmux_r1：pull 名义通过，开发未测；push 名义通过，开发未测
- recovery_planar_arm_screen_warp_r1：pull 名义通过，开发2/6；push 名义通过，开发3/6
- recovery_planar_screen_warp_r1：pull 名义通过，开发0/4；push 名义通过，开发1/4

逐案物理结果及实际分母见 results/b0/recovery_round_20261123/case_index.csv 和各 run 目录。独立 seed 与 H 保持封存。


## 2026-11-23｜恢复轮结束后的独立审查、标准迁移顺序与下一计划

### 目标、证据起点和实际执行范围

用户要求仔细审查已结束的最新实验，把下一步计划推送GitHub、给出启动提示词，并详细说明与总目标的距离。审查期间用户进一步明确：“分析SuperMimic融入腿臂控制 你读取一下这个项目中的这个对话，别把咱的顺序弄乱了，现在是根据supermimic进行迁移的标准阶段”。本次以该直接指令固定阶段：先完成官方SuperMimic核心机制在M1＋Piper H上的标准迁移B0，再做多模态/VLA融合及后续实机；WM/可微展开本来属于当前B0，不能说留到后续才开始。

审查范围为前次文档提交 b9a11293a6930b1c95e335c090641bbdae649c62 之后、最后实验提交 23c90684522a030e2625bf0e44118fa86884ebf4 为止。八个实验提交依次为 bccb5f2、f160969、1223501、3c9106a、eb79802、f081200、d00936b、23c9068。远端main在本次发布准备时仍为23c9068。本次读取当前源码、报告、配置、原始小结果、提交和可访问历史摘要；没有运行新训练、物理仿真、硬件或远端作业，也没有重新加载现场全部大权重。

针对具名历史对话进行了两次限定检索，返回相关摘要，确认“先官方核心机制原则不变迁移、跑通B0，再多模态”的历史顺序，但没有返回可逐字核对的该对话完整正文。未把摘要伪称全文、未编造用户历史原话，也未将其他项目的π/RoboMIND安排混入当前阶段。本次直接可见的阶段纠正已足以约束本轮计划。

工作环境为隔离审查工作区；通过Git读取项目和GitHub主分支，按分工审查代码、教师/目标和逐案/视频证据。实际检查包括 git status --short --branch、git log、git diff b9a1129..23c9068、rg定位、结构化文件解析、视频完整解码和抽帧目视。官方固定pin的WorldModelEnv/ActorCriticPolicyLearner也与实现核对；MuJoCo轮地接触差异对照固定3.3.0/3.16.0源码。没有升级依赖或修改实验物理代码。

### 全量结果覆盖、漏收与继承问题

1. 两提交之间共979个变更文件。结果、数据和配置的926个变更文件共101,749,329字节完成读取：678 JSON、129 CSV（117,522数据行）、17 JSONL（191条）、102 MP4；文本解析无错误。
2. 原 recovery_round_20261123/case_index.csv 有384条、50个run，98 nominal＋286 C；逐条passed/物理步数/终角/首失败与原始JSON一致，scores汇总可以重建。
3. 实际有387条完整任务result、51个run，100 nominal＋287 C。漏收的是 recovery_endpoint_hinge_tail_warp_r2 的pull nominal（37374步、59.950954°）、push nominal（27512步、25.026353°）和push C08（27512步、24.958551°）；三条通过。保留原索引，用本次audit_summary补充，不把C08的1/1写成完整C。
4. 六条nominal来自三组--extend-from继承，目标与来源result字节一致；索引对应378个不同raw目录，含补充后381个。它们不是新增独立随机试验数。各分支还共享seed和开发条件，不能聚合成某个候选的总成功率。
5. 全部387条是full、起始substep和教师prefix为0；165条通过记录都具备13阶段与抓持100子步、目标保持250子步、两次独立停车各1500子步。
6. 102个视频完整解码135,066帧、零解码错误；团队实际目视30视频各首中尾3帧，共90帧，覆盖三端名义、u5/u10失败、teacher、tail和后端分支。没有声称逐帧看完，也不以视频替代力/时间计数。审计记录原视频路径/取样帧；五张派生接触表只作临时审阅，不重复入库。
7. 最终 results/b0/recovery_tmux_20261123/outcome.json 为2026-11-23 21:11:04+08:00、finished=true，8个登记任务全部completed、pids为空；20:40/20:45“仍运行”属历史。本次没有登录现场再查所有进程，下一执行者需核实现状。

本次新增 results/b0/recovery_review_20261123/audit_summary.json，原case_index、scores、配置和实验结果均保留。

### 标准主线与混合策略身份重新核准

此前仅用“原tracking H32”称呼所有相关包容易混淆方法身份。本次沿build_actor、checkpoint初始化、actual_config与实际更新日志核查三类：

- 标准迁移S：EffortScaledActor是固定官方MultiEncoderAE主体，外加home/effort/gain的机器人单位换算与统一clip，没有六臂/夹口参考前馈或解析补偿。恢复锚点为free_s0_cloud_servo_r2/checkpoint_001000.pt＋contact_s0_wm_held_r2/wm_002000.pt。B0-03已过，不重跑整阶段。contact_s0_tracking_r3/checkpoint_001000.pt记录接触1000 H32、10000 WM、20000 Critic、572118有效转移；两后端原v1十项nominal均0/10。r3从r2恢复，不能把r2再累加。标准接触/完整任务尚未通过。
- 540参考残差R：ReferenceResidualActor直接用当帧六臂/夹口参考作动作基值，再加网络残差。旧contact监督包BC3000；当前full包依次继承contact_refres、full_pull、full_push、full_joint_native、full_joint_warp五段各3000，累计15000动作BC。逐项initial_actor和updates.jsonl最后实际update=3000已核对。不能只报最后一段3000，也不能描述成单一数据实验15000。官方内部latent对齐bc_loss并非这种教师动作BC。
- 546解析补偿J：在R上加入参考Jacobian与当前根平移的直接六臂修正；886个对齐教师帧拟合gain，未约束1.3385、按登记范围取1.0。集成u0新列置零/新增网络训练0，但仍继承15000BC和直接反馈。之后u1做了真实H32更新；这不是标准Actor已经自动学出全部跨端能力。

原540 recovery tracking-u1：Warp nominal两侧通过、完整C各9/20，native nominal0/2。546-u0/u1各有同包三端名义能力。标准S、R、J及所有失败都保留，不能只删六维补偿或关physical prior就把R/J重新标成原样Actor。

### 本轮有效进展与剩余问题

- 同一个546-u1在三端自身反馈上完整执行：Warp前拉37490步/59.960025°、背推27601步/25.028641°；CPU3.16为37489/59.959722°、27600/25.037005°；native为37110/59.973016°、27192/24.990748°。u0已通过，因此u1证明一次真实更新保持能力，不能把跨端收益全归于H32。
- 546-u1真实新增1558有效转移，10 WM/1 Actor H32/20 Critic更新；Actor末层max变化6.251e-6，WM/Critic0.001889/0.001684，BC loss=0。有完整梯度链，非只改update编号。
- 完整C共五组双侧：四组各9/20；546-u1 native为9/20、10/20，额外只过背推C08。Warp混合候选每侧仍距18/20净缺9。native按同数值参照缺9/8，不增加native完整C正式门槛。标准S还没有可借用的全程成绩，不能把混合9/20算成标准迁移完成45%。
- planar-arm 2/6、3/6，planar0/4、1/4，endpoint-tail push C08为1/1，分别属于局部独立分支，不能拼进共同546成绩。
- 后续更新仍退化：546-u5前拉门已59.9544°，退站误差11.5888mm超过10mm，37868步reference exhausted；phase-TD u10前拉31310步退臂timeout、背推通过；其他tracking/TD分支存在pregrasp失败。没有把所有u10误写成同一种失败。
- 同批bootstrap完整/分离u1都通过；真实TD terminal/continue u5也都通过，不能把能力保持唯一归于截断bootstrap。既有拆分可继承，不重做。
- 40步连续收集和独立H32 WM预拟合已完成，普通joint在线仍以H1/H7为主；在线H32配方是另外一项需登记的改变。分模式部分误差下降、部分退化；push某双指组只有1窗，不支持稳定性结论。
- 12个局部H32距离方向6同/6反，实际是两侧六阶段、给WM输入真实分支动作序列的开环诊断，不是完整BPTT梯度50%正确率。
- phase-TD仅改变真实Critic目标，Actor/后续想象GAE仍用原tracking/根高度倾斜，二者不一致；这是额外变体的限制，不能作为默认引入新reward的理由。原softdone对79真实训练失败检出0，但这些主要是局部force/lostgrip，尚非全程timeout标签。
- 事件头验证TP17/FP94/FN62/TN4951，precision15.32%、recall21.52%、FPR1.863%，未达登记条件，未接入正确。分类阈值达标也不能直接把balanced logits当校准每步风险概率。
- 16扰动教师P6自身14/16，冻结全程判据只有3/16；same_phase不保证目标/进度一致。固定门角5°的pull端点相交24.71mm、512个边界样本均相交，但尚未排除先用合法指面接触移动门的路径，不能宣布旧任务全局无解。已有小角两侧合法教师继续保留。
- 轮地接触流形和MULTICCD差异已有受控因果证据，标准正式环境未用诊断改物理。下一轮仅做受影响的必要回归，不重复整套后端定位。

### 计划方向纠正与已完成文档

最初未发布草稿预设了对象相对全程v2及新任务目标作为下一主线。用户强调标准阶段后撤回这一默认安排，未推送该草稿，也没有执行相应代码/训练。新计划是 docs/B0_STANDARD_TRANSFER_PLAN_20261123.md：

1. 锁定官方双pin、标准EffortScaledActor与原tracking/H32组织，分清标准S和参考/解析对照R/J。
2. 从已完成B0-03与动态门WM接续，核对真实动作单位/幅度/限幅、normalizer、参考motion_id、20ms held-action与后继时钟，修复有物理依据的必要接口问题。
3. 独立训练身份采集/复用合法真实转移和匹配参考，WM使用成功/失败，验证不进优化/replay；不以错配same-phase动作标签替代标准训练。
4. 保持原Actor/reward/softdone，当前H1/H7模型组织与H32策略展开；40步采集用于覆盖和长窗诊断。必要数据/输入/输出尺度变体单列原值、依据与匹配结果，不同时叠加方法改变。
5. 标准Actor从接触到完整连续任务实际训练，u0/1/5/10及后续有意义预算持续推进，不止一次诊断、不无依据盲训。新裁判、phase reward、风险头、解析反馈、多模态不默认转成主线。
6. 沿用十项接触每项D≥18/20、主后端两侧全C各≥18/20、同包native名义与持续真实H32证据，再独立seed1/2、全部冻结后H；CPU3.16按需诊断，不增硬门槛。标准未过就报告标准限制，不能用混合成果代填。

新增 reports/B0_RECOVERY_REVIEW_20261123.md（完整审查）、docs/B0_STANDARD_TRANSFER_PLAN_20261123.md（下一标准执行）、docs/GOAL_GAP_20261123.md（标准阶段与最终目标差距）、审计JSON；同步AGENTS、README、PROJECT_STATE、总路线、历史计划页首、B0_START/NEXT_RUN。四份实验原报告只补归档/当前入口说明，原始数字和失败不删除。

目标差距按层说明：标准B0目前最好是无接触学习，接触/全程标准证据还缺；混合候选具备名义能力但鲁棒/持续更新/最终接触/独立seed/H也不齐。B0之后还有RGB-D与语言、本体历史、多模态数据、部分可观测状态/WM、联合训练、泛化恢复和真实M1＋Piper闭环。H0相机/机械臂联调是已有资产，不抹去；也不把它当成整机学习实机通过。不虚构总体完成百分比或剩余天数。

### 验证与交付状态

本次只进行文档/证据一致性检查：逐案分母、S/R/J配置/继承计数、链接路径、当前/历史入口区分、JSON解析和git diff空白检查；不新增与当前改动无关的测试。最终推送前核对远端HEAD，普通提交仅包含本次明确文件，回读GitHub及同步本地后核对内容。本文与本次审查/计划随同一个文档提交保存；当前提交自己的SHA不预填，最终实际提交号在聊天交付，下一日志节点可补记。失败记录、大资产位置、旧协议和用户其他修改保留，不强推、不压缩归档。

### 22:21–22:29 标准迁移开工与 40 步原尺度配对组（北京时间）

核查 GitHub main 为 5e6db44。第二平台主工作树 fe6cc85 有 PROJECT_STATE、H0 和 P5 的在地改动，在同仓库另设 /home/kaiwen/research/dog-and-arm-standard。经第二平台 SSH autodl-dog-arm 管理云端独立工作树 /root/autodl-tmp/dog-and-arm-b0-standard，已核实原始 SuperMimic abc124c / mjlab_research dd51a9f；隔离 .conda、.venv、vendor、网格及两项权重复用已有路径。原云端 recovery 树含未提交改动。现场有其他项目占用同一 RTX PRO 6000，未干预。只运行仿真。原 5e6db44 审查已从 origin/main 读回。

从 B0-03 free_s0_cloud_servo_r2/checkpoint_001000.pt 恢复 Actor 全部参数和统计，接触 WM 用 contact_s0_wm_held_r2/wm_002000.pt（已有 2000 教师 minibatch）。门 Critic 第一层重新初始化，兼容的后续层沿用，无接触优化器、RNG 与 replay 全新起步。种子 0、128 世界、WM/Actor batch 256、40 个真实 20 ms 间隔；正常 joint 每轮 8 个 H7 和 2 个 H1 minibatch、1 次 H32、20 次 Critic。沿用原 6 条参考和另 4 条教师训练轨迹、官方 tracking 与 soft termination。

云端命令 `bash scripts/b0/env.sh python -u scripts/b0/train_contact.py --config config/b0/standard_contact_40.yaml --run standard_s0_control40_r1 --updates 10`。u0/1/5/10 保存，实得 17,736 / 51,200 个 lane 间隔有效，10/100/200 次 Actor/WM/Critic 更新；u0 Warp 原 v1 为 0/10，额外五个已登记 hold-margin 为 0/5。首个前拉 open_5 控制间隔在第 1 个 2 ms 触发 51.07 N 合力。逐节点物理结果正在按实际完成状态收集。

从同一对锚点独立启动 standard_s0_gain32_r1，针对有实测依据的六臂/夹口尺度做初始化等价的单因素比较。夹口发送全宽、单电机乘 0.5，两真实指从反馈计算宽度。机械与动作映射细节、预训练分布和等价复测见 results/b0/standard_transfer_action_audit/action_units.json。两个尺度的规定扭矩/速度/物理限幅、探索和前动作定义相同。十项接触 D、完整任务 C、native 完整名义与多 seed/H 尚未执行。

### 22:30–22:42 配对训练、物理复测及脱离聊天运行

第一节点 e87e1b5 已普通推送并经 GitHub API 回读。开发机直接 HTTPS 推送缺少凭据，改由 Windows 已认证的既有 delivery.git 传送同一提交，未改主树和凭据。云端 train_contact.py 对 original/×32/补握持数据三个 u50 节点分别累计采到 69,480 / 70,425 / 73,163 条有效转移（每组 256,000 个候选 lane 间隔）；各自 50 H32＋500 WM＋1,000 Critic。control u10→50 的新 run 从完整 cohort_state 接续，同一条链只计一次。三组 Warp 正式十项 nominal 均 0/10；×32 同包 native 原 v1 0/10，逐项失败和 native 视频均保存。原尺度与×32 u0/1/5/10 的物理节点已回收。原尺度/×32 前拉 open_5 u50 首步约 51.01/50.87 N，背推 33.12/33.32 N。×32 拉侧接近延长但仍未抓住；其动作/关节力变化支持把该链从 u50 状态继续到 u200，需观察末点是否真实改善。

真实物理和统计的复查，以及每一项配置、机器可读结果、命令入口、失败与分母，记录在 reports/B0_STANDARD_TRANSFER_RESULTS.md。两侧 batch 与独立逐侧相同前缀物理一致，但首步训练源 phase 和正式阶段边界有 3 子步差。20 回合 held 数据的真实后继未见时序错误。发现 raw 零填充在 motion normalizer 后出现 116.85 伪信号；修复使全部 1350 个无效槽为零、96300 个有效槽不变，padding 配对独立训练。既有 u1000 失败入口没有尾槽，不将首步失败归因于该问题。

独立冻结采集 81101–81103 共 2321 个有效转移、142 次物理终止；逐 lane 核 s/a/s_next、上一动作、帧、终端和硬事件。WM 分布诊断发现 control-u50 的两指 H32 TCP P95 前拉/背推 688.06/166.67 mm。仅以预登记训练握持窗替换每个 H7 minibatch 的 32 行后，u50 为 106.62/145.39 mm，仍差于 held_r2 的 50.53/40.36 mm。未向 Actor 加动作监督。单换输入统计会显著改变原模型的物理预测；另做首层权重/bias 等价换算配对，1725 个真实输入的单步 TCP 最大单坐标偏移 12.412→0.000358 mm。该复测只验证数值映射。原官方优化器及其 moment 在新坐标沿用，正式末点待收。

实际入口为云端 bash scripts/b0/env.sh python -u scripts/b0/train_contact.py；配置 standard_contact_40{,_gain32,_gripdata,_goal_padding,_wmcoords}.yaml。×32 后续命令附 --resume results/b0/standard_s0_gain32_r1/cohort_state.pt --run standard_s0_gain32_to200_r1 --updates 200。评测使用 eval_contact_segments.py 配两份冻结 manifest；验证使用 standard_contact_validation.py collect/score。按用户补充要求在 tmux 稳定后结束对话：云端 b0-standard-finish 编排剩余已登记节点（含 u200 双端与同入口受力诊断），第二平台 b0-standard-receive 同步小结果、更新每日记录/状态及普通推送。新标准接触 D、完整 C、独立 seed/H、硬件未执行；云端大权重、RNG、优化器与 replay 保留。

### 标准接触 tmux 回收

北京时间 2026-11-23T22:50:39+08:00。已回收 415 条 nominal 物理记录，含同包不同参考协议的配对。记录索引见 results/b0/standard_handoff_20261123/case_index.csv。

- standard_s0_control40_r1：累计 H32 10 次、有效在线转移 17736。
- standard_s0_control40_to50_r1：累计 H32 50 次、有效在线转移 69480。
- standard_s0_gain32_r1：累计 H32 50 次、有效在线转移 70425。
- standard_s0_gain32_to200_r1：累计 H32 200 次、有效在线转移 345268。
- standard_s0_gripdata_r1：累计 H32 50 次、有效在线转移 73163。
- standard_s0_padding_r1：累计 H32 50 次、有效在线转移 82748。
- standard_s0_wmcoords_r1：累计 H32 50 次、有效在线转移 86911。

已完成末节点的十项原登记组合结果如下。

- results/b0/standard_s0_control40_to50_r1/checkpoint_000050.pt，warp，0/10。
- results/b0/standard_s0_gain32_r1/checkpoint_000050.pt，warp，0/10。
- results/b0/standard_s0_gain32_to200_r1/checkpoint_000200.pt，native，0/10。
- results/b0/standard_s0_gain32_to200_r1/checkpoint_000200.pt，warp，0/10。
- results/b0/standard_s0_gripdata_r1/checkpoint_000050.pt，warp，0/10。
- results/b0/standard_s0_padding_r1/checkpoint_000050.pt，warp，0/10。
- results/b0/standard_s0_wmcoords_r1/checkpoint_000050.pt，warp，0/10。

首步力和后继 tracking 的同起点双侧实测见 results/b0/standard_handoff_20261123/gain200_entry.json。开发 D、完整 C、独立 seed 与 H 本队列未执行。

## 2026-11-23 23:32 北京时间｜论文指标导向的标准迁移独立基线审查与下一计划

用户新增要求：按已经开源的SuperMimic详细研究/迁移，以达到或接近论文指标为准，单独形成结果，后续方法需要比较；最新一轮已结束。继续保持“标准迁移先跑通，再新开发/多模态VLA”顺序。本节点是论文/代码研究、已提交实验审查及文档发布，没有启动新训练、物理评测或硬件。

### 实际读取与实验端点

- 从本地main@5e6db443316f5acec6d840f0be36c6ca1b1bf88a正常fetch/快进至638fddcb2f025006595f79f27a977a8fba41cbc2；新增e87e1b5、a28f765、638fddc三个实验提交，末次22:50:39回收。起始工作树干净，保留现场其他分支/进程及大资产，没有reset/clean。
- 团队逐文件读取该区间687文件、3,512,682字节，并用不可变638fddc的Git blob内容复核；结果/config673文件、3,197,305字节。572JSON、79CSV/12,651数据行、7JSONL/400更新、5YAML均解析。415逐案结果和55评测run与索引一致。10MP4全解码304帧，各末帧10张目视，不称逐帧观看。
- 重新核读论文arXiv:2610.28480v3（19 Nov 2026，19页），作者项目页与固定官方核心；下载PDF并提取全文，在临时审阅目录查看第7/16/17页图表。论文/源码的临时副本不重复归档进项目。上游main仍为5fb92297ab4fe3d86629d9f0c635334791bb0d5f，已是source_lock的candidate_not_applied；没有升级固定abc124c/dd51a9f。

### 已核清的实验结果与失败

1. 五条seed0配置最终：control-u50有69,480有效转移，gain32-u200有345,268，gripdata-u50有73,163，padding-u50有82,748，wmcoords-u50有86,911；Warp正式十项全部0/10，gain200同包native也是0/10。额外动作BC=0，官方核心learner实际调用。
2. 七个训练目录对应五条链；control u10→50和gain u50→200是完整续训，不重复前缀。合计新增400H32、4,000WM、8,000Critic、657,570有效转移、2,048,000 lane控制区间；不是一个模型预算，也不是五个独立seed。
3. 415nominal全部失败：Warp390/native25，v1 280/hold-margin135；正式275、额外v1 140。正式27套完整十项＋native gain50仅五项；gain50原v1 native虽0/10，正式另五项hold-margin未评。303首2ms门受力超限。D、完整nominal/C、seed1/2、H本轮未执行，不填零成绩。
4. 后回收WM结果补齐到审查：gain200双指H32 TCP P95551.98/278.53mm，wmcoords-u50为100.66/82.60，held_r2为50.53/40.36，常速13.95/11.86。前拉412重叠窗/51lanes、背推450/56；自由验证push仅27窗/3lanes。预测改善与退化按模式分开，不称闭环梯度已可靠。
5. gain200同起点首20ms successor tracking前拉.05278→.09080、背推.05609→.08287，但首2ms力30.64/51.98N仍>6N，诊断越限后仍积分满20ms。不能把.09080/.1写成论文完整回报0.908或标准能力已过。

### 论文/源码差异：已证事实和待验原因分开

- 论文BONES-SEED的129,514为训练动作覆盖，0.90是SONIC参考线；SuperMimic1H100×3h超过该线且25失败，2H100×9.8h为0失败。LAFAN1另有40clips/2.45h、1.2h评测回报0.82，不混两套数据。原G1 O1已有40clips/0.8744398924且已关闭，本轮不重开。
- 当前标准核心不是论文完整配方已等价：ContactRun未接官方ReturnSampler，replay_ratio16未驱动固定40cohort/一次Actor调度；官方8storedframes实际监督7后继，额外2H1批是项目适配。每轮14,848WM目标/17,408窗口位置含offline；online分别11,264/13,312；Actor8,192 imaginedsteps，最多5,120attempted。不能将这些分母直接与16混比。
- 官方动作率对effort-scale之前policy输出计分，项目却用canonical物理范围坐标，相同J2物理变化惩罚约弱3,948倍。数学差异成立，是否导致首步超力尚未配对验证。gain32只是优化参数化，不能跟着改变reward单位；完整reset零previous可能是无历史哨兵，转换必须保留有效性/首步约定。
- 固定mjlab采用全拼接timeline约0.2s分箱，与论文附录1s不同；按源代码映射处理取整/clip边界。官方前瞻逐clip夹末帧，项目零槽padding是另一适配；恢复观测夹帧不等于延长任务时限。固定官方隐藏二维权重Muon＋其余Adam，与论文表统称Adam分别记录。
- wmcoords首层坐标代数正确、瞬时函数近似保持，但保留optimizer moment数值不等于优化轨迹等价。padding修掉归一化116.852伪信号仍未解决接触。补握持训练数据未污染验证且没有额外Actor动作监督，均保留有效工作与限制。

### 独立结果和下一执行计划

新建reports/B0_STANDARD_TRANSFER_BASELINE.md和results/b0/standard_baseline_20261123/baseline_manifest.json，快照b0-standard-s0-638fddc、目标方法SuperMimic-M1Piper-standard-v1。当前status为B0-04未完成、final_candidate为空；完整归一化回报、可比论文WM误差、可靠总GPU小时NA。保存负结果不当作标准阶段完成。新建论文指标协议、官方实现审查、最新轮完整审查及可解析audit。

完整物理回报按预登记完整时长/理论上界计，失败余段零，部分区间/参考clock明确，片段教师前缀与完整任务分开。目标≥0.90，接近数值带≥0.88是本项目事先规定0.02容差，非原论文定义；每seed/侧/split单列，并同时通过既有物理门槛。不裁负值、不用想象/单步回报代替。动作坐标对照的训练可不同，正式主评测必须同一定义。

下一轮第一优先是同标准起点/数据资格/预算的canonical vs固定effort动作率单位配对，实际训练及物理复测；然后移入官方采样/实际Ratio、尾观测语义及WM接触精度保护。保留当前网络、原tracking系数、softdone、H32、被动门、v1/hold-margin、物理阈值和时限；不改成BC/参考直通/新force reward/风险头/解析控制。合理利用现场资源，有进展持续训练，不设200或1000为必然终点，也不在明确退化时盲加量。

同一候选依序十项nominal→各D≥18/20→连续双侧Warp C≥18/20与native名义→独立seed1/2→三seed规则和候选全冻结后H≥40/50；原工程/B0-03资产继承。后续方法共享冻结评测与case身份，额外数据/视觉/BC/控制及成本单列。同步PROJECT_STATE、AGENTS、README、总路线、B0总计划、GOAL_GAP、B0_START/NEXT_RUN；原实测报告只加已回收/当前入口说明，原正文不改。

### 复核与发布

三个独立子任务交叉复核新基线数字/manifest、源码计划和论文口径；修正了最初计划把论文1s分箱写成固定源码默认的问题，补首步previous哨兵与不足20ms末段计分说明。仅对本次文档/JSON做相对链接、计数/字段一致、语法和git diff检查，不新增形式化测试套件、不跑训练。推送前核对远端HEAD，普通提交仅含本次明确文档和小结果，回读远端并逐文件核对；本节点文档自身提交号随发布在聊天交付，不预填未生成SHA，后续日志可补记。

## 2026-11-23 23:47–23:56 北京时间｜标准 B0 实施与同源配对

GitHub main 与新检出均为 `95159f77745d754b41ca135c726e2f2ba55c907e`。相对 `638fddc` 的 17 个变更文件为协议、审查、状态和小型结果清单。第二平台旧标准工作树在 a28f765，AutoDL 旧标准目录在 5e6db44，均有未提交结果或源码。AutoDL 的旧 B0 tmux pane 已退出。使用独立 `/root/autodl-tmp/dog-and-arm-b0-pair-v1`，复用项目环境、模型、参考、动作数据和两份标准锚点。实查 RTX PRO 6000 Blackwell、25 核 CPU 配额，首次盘点可用显存 91,655 MiB、数据盘可用 203 GiB。固定 vendor 两库分别为 abc124c 和 dd51a9f。

- `bash scripts/b0/env.sh python scripts/b0/measure_action_rate_units.py --cohort results/raw_large/b0/standard_s0_gain32_r1/cohort_000001 --source-config results/b0/standard_s0_gain32_r1/actual_config.json --output results/b0/pair_units_v1/measured.json`。原训练标记有效 1,725 行，扣去在 20 ms 结束前已经触发物理失败的行，合法后继 1,640。相同状态/参考/命令下，六正项和限位均相同。canonical / fixed effort 的平均动作率项 −0.0002441 / −0.6080893，Piper J2 同位移罚比 3947.84155，动作率对 canonical 动作的平均 L2 梯度 0.0004624 / 1.113626。针对实际批次将分项之和与固定上游函数比对，最大绝对差 1.91e−6。基础 effort 的前动作 reset 哨兵 L2=0，而有效的全零 canonical 命令 L2=33.3881。
- 两条新命令均为 `bash scripts/b0/env.sh python -u scripts/b0/train_contact.py --config config/b0/pair_<canonical|effort>.yaml --run pair_<canonical|effort>_s0_v1 --updates 50`。独立持久进程、相同 seed0/gain32/物理探索幅度，128×40 采集、batch 256；官方 H32、10 WM/20 Critic 每轮。两条 u0 逐张量比较，Actor 68、含统计的 Dynamics 24、Critic 10 张量全部完全相同。运行时数据由策略产生，u1 后允许轨迹分化。新旧结果均保留。
- u0 两条都实测 0/10。相同初始权重在 Warp 双测的前拉 release_retreat 有 500 / 504 子步数值差异，解释后续小差异时保留该现象。独立采集/评分与正式接触训练分开，训练、回报和验证大数组均在同一项目的新现场目录。
- 在 1,636 个真实非终止训练区间测量当前合法 J4 目标。u0 归一化绝对值最大 182.205，而 32 维 motion latent 中绝对值达到 0.99 的比例是 0；u10 两条该比例均低于 0.12%。这些观测支持保留 encoder 架构。

### 23:56–23:59 配对端点及调度核验

首对 u50 已完成。canonical 75,312 有效转移、264.92 s 进程时间，effort 69,610、263.82 s。每支实做 50 H32 / 500 WM / 1,000 Critic、409,600 imagined steps、256,000 attempted lane intervals。u1 官方策略梯度范数 3.3152 / 7.4107。两支 u0/1/5/10/50 的 100 条 Warp 正式接触评分全失败。u50 十片段共同 effort 口径等权均值 −0.03413 / −0.04738。原坐标 u50 的前拉接近走到参考终点、释放走到阶段时限，均未过裁判。effort-u50 背推稳定握持的 J2 首跳从 u0 的 −0.4836 rad 缩至 −0.0400 rad，门力仍为 22.20 N。因局部命令/门力变化，同预算两支从各自 `cohort_state.pt` 续到 u200，命令在上述训练入口加 `--resume results/b0/pair_<mode>_s0_v1/cohort_state.pt --updates 200`，新 run 为 `pair_<mode>_to200_v1`。u50 前缀仅算一次。

固定源码 ReturnSampler 按 9,765 帧全局时间轴形成 977 个 bin。最初适配沿用训练 replay 的 20 ms 后继，但终止可发生在第 1–9 个物理子步；真实记录检出 85 条提前终止，其越限后积分奖励与实际失败时刻计分最大相差 15.619。生产 sampler 改为捕获首次终止的 q/v、同一物理时标的参考和实际 dt。39 条完整 lane 与固定源码逐值一致，注入失效 lane、clip 截止/超时、缓存和 Ratio 断点恢复另有实测。三种对齐训练于 23:57 启动，依次增加 ReturnSampler、有效转移驱动的官方 Ratio、逐 clip 末帧夹取；各组固定 effort、u50 预算。第一 cohort 为 1,734 有效 / 5,120 尝试；Ratio 发出两次更新。正式 hold/截止时间沿用原协议。阶段代码和原配对训练小结果已普通推送并回读 `8232e69d9f7b7fc314497c5d61185094ae4f87b8`。

## 2026-11-24 00:00 起 北京时间｜接触评分、WM 独立覆盖与标准联合学习

- 使用 `bash scripts/project_env.sh python scripts/b0/diagnose_contact_entry.py results/b0/pair_<mode>_s0_v1_u50_warp_hold_margin_v2 --references results/raw_large/b0/contact_held_margin_v2 --output results/b0/pair_units_v1/native_entry_<mode>_u50.json`，在 native 3.3.0 完整重建前缀上做首动作分通道诊断。前拉/背推的原参考首命令为 1.173 / 1.120 N，均通过这 10 个子步；effort-u50 全策略首命令为 50.899 / 22.194 N，仅替换六个臂通道为 66.898 / 38.762 N。动作分块结果只用于解释失效，不参与标准成绩或策略执行。
- 首批 WM 同窗是 412 个前拉窗/51 lanes、450 个背推窗/56 lanes。held_r2 的 H32 双指 TCP P95 为 50.53 / 40.36 mm，canonical-u50 为 339.56 / 129.02 mm，effort-u50 为 717.10 / 241.81 mm。另用两个冻结 u10 策略各采 16×64 lanes，采集种子相同、绝不进入 normalizer/replay。补背推分层时按发起的全部 lanes 记录失败。按同一门 WM 初始化、真实 grip 的 train split 和 H1/H7 预算安排两条有针对性的联合学习，比较累计统计与固定 held 统计；两支均继续优化 WM 权重。

### 00:03–00:17 调度对照、匹配续训与接触覆盖

- 三条实际 u50 正常退出。ReturnSampler-only 42,757/256,000 有效/模拟区间，ReturnSampler+Ratio 54,306/337,920，另加逐 clip 末帧夹取为 53,579/343,040。Ratio 两组累计 WM 存储位置/有效转移 16.028、16.245。恢复包含 sampler 的部分缓冲与 Ratio 欠付次数。六参考的抽样并不均匀：push_0_train_grip 的原均匀配额、return、ratio、cliplast 实测占 16.41%、60.02%、63.96%、63.89%，初始全局均匀 bin 在合法帧上条件化只给该条 12.97%。详见 pair_sampling_audit_v1/motion_exposure.json，有限力记录以实际可观察分母为准。
- 三组 u50 各 0/10。return-only 背推稳定握持门力 6.697 N（门槛 6），前拉 51.014 N，匹配续训 `return_to100_s0_v1` 到 u100 后背推又升至 26.60 N，正式仍 0/10。阶段评分、调度账本及 130 条逐案结果推送并回读 `7ae5753c262f80cfdc05b7f8d9b7f8e0fcf4160d`。
- 配对 u200 正常结束，canonical/effort 累计 384,430 / 452,697 有效转移，均完成 1,024,000 个模拟控制区间、2,000 WM、4,000 Critic、1,638,400 imagined steps。各 0/10；十片段共同坐标均值 0.31312 / 0.13728。固定 effort 背推三项的门力降至 1.45–1.55 N，推进至第8子步触发 grasp geometry 失败，stable_grip 末端双指均为零载荷、开口 39.06 mm、TCP/把手误差 5.79 mm。前拉三项仍在第1子步约 35.4–35.6 N。基于实际失败方式和存续进展，于 00:16 从各自 u200 完整状态续至 `pair_canonical_to350_v1`、`pair_effort_to350_v1` 的 u350 目标。
- `aligned_grip_s0_v1`、`aligned_grip_fixed_stats_s0_v1` 都从相同基础门 WM/标准 Actor 训练至 u50。只用 grip 登记种子71200–71207的512 lanes、14,396实测转移/11,644合法H7窗替换一部分离线H7样本，数据来自历史恢复策略，用途仅为 dynamics。两种统计处理分别53,595/53,704有效转移，正式接触均0/10。固定统计组8个统计缓冲逐元素等于held_r2，另外一组统计count 10,808→64,403。两组14个WM MLP权重/偏置张量均有更新，共同处理相同动作流时的预测精度分开计算。
- 用 `scripts/b0/check_contact_gradient.py` 在 native3.3 对前拉/背推各做一个 J5 和夹口扰动，四个局部7步门角导数，canonical-u50、effort-u50 与 native 中心差分分别有2/4、1/4同号。两个补 grip 的 WM 同号均2/4。保留原始幅值、中心/正负扰动的非线性与TCP三轴；四个局部方向不能代表完整 H32 梯度。
- u50 的固定统计 replay 中 15,707 个在线 H7 合法起点没有一个位于开门/保持参考阶段。覆盖到指力的594个H7起点中13个至少一指有载荷，持续双指为0。固定官方 ReplayBuffer 每个样本独立抽可用 env/lane 及 age；原接触实现整批只来自一个 cohort。相同缓存核验，新抽样使每个192窗WM批的不同物理episode均值19.55→155.77，保持原时间边界、历史和末后继。00:16 另起 `lane_age_s0_v1`，与固定统计组同初始化、同预算实际学习，保留旧抽样对照。

### 00:17–00:40 配对至 u500、独立归档与正式门槛

- lane/age 对照在相同 H7 握持补数及固定统计下实收 54,028/353,280 个有效/模拟区间，u50 真实十项0/10，十片段均值 −0.04576。两侧稳定握持峰力51.03/32.11 N。抽样多样性增加，固定双指窗 H32 TCP P95 为242.02/196.77 mm，对应母线104.18/107.70 mm。样本重排没有补出参考 open/hold 的缺失在线H7窗。三组采样、WM独立核验、u200真实评测及重放修复已提交并回读 7da090d8cde7528658a141fcfe23fa559fea1c9f。
- u350 匹配两支均0/10。canonical 前拉稳定握持首次推至34个2 ms子步；同包前拉释放在第2057个子步完成登记的release事件，最终retreat_arm就绪为0，参考用完。该片段0.971913，整包十片段均值0.36832；effort为0.30215。基于这个新事件，从各自 u350 完整状态继续 `bash scripts/b0/env.sh python -u scripts/b0/train_contact.py --config config/b0/pair_<mode>.yaml --run pair_<mode>_to500_v1 --updates 500 --resume results/b0/pair_<mode>_to350_v1/cohort_state.pt`，本次各追加150更新。每次恢复均取对应优化器、normalizer、RNG和replay。u350前拉释放轨迹按已存实测 qpos 渲染，512×288、25 fps，197 帧全解码通过。u50前拉接近的136帧视频亦全解码。
- u500 两包正常退出并各自完整评完十项，均0/10，两个方向均无任何登记阶段完成，u350的release事件未保住。canonical/effort有效转移累计1,291,256/1,392,696，各2,560,000模拟区间和4,096,000想象步。共同固定effort口径十片段均值0.22961/0.25963。stable_grip 的实际存续/峰力：canonical前拉46 ms/2.198 N、背推2 ms/10.947 N；effort前拉2 ms/16.345 N、背推2 ms/8.312 N。前拉低门力本身不代表有效双指握持。两种训练延长到u500后仍缺同包双侧能力，因此收束本轮预算并保留全部现场恢复入口。
- WM 新验证共80个采集cohort和40个配对种子；5,120 lanes，136,000 attempted、28,769有效、4,716提前终止。验证的政策、种子和真实轨迹独立，使用同一组参考。四组采集进程时间累计222.63s。初次批量合并四元数计算不支持 TorchScript vmap，转为普通批次，将加权总损失和逐组 MSE 与固定 `_compute_losses` 两返回值逐批比对后重测。5个数据集共27次实评分，进程墙钟累计563.54s。u500双指TCP P95 前拉/背推为canonical 251.55/85.34 mm、effort 262.48/24.32 mm。两包H32加权状态损失为0.479136/0.058596和0.645614/0.014859。全部独立验证排除于学习、统计和 replay，实际评分入口为 `scripts/b0/standard_contact_validation.py score --state-loss`。
- `scripts/b0/index_transfer_training.py` 逐 run 核对15个正常训练退出、继承后的连续步号、恢复状态和端点权重摘要。八条seed0配置链合计新增1,350 H32 / 13,500 WM / 27,000 Critic；3,081,019有效/7,296,000模拟控制区间，11,059,200想象步。训练进程累计2.069小时，合并重叠为0.665墙钟小时；继承训练与独占GPU成本NA。完整命令在 results/b0/standard_baseline_20261124/contact_training.json。
- 收回23组正式Warp十项共230条真实评分，0条通过，129条首2ms失败；仅有上述一个登记阶段事件。46个双侧稳定握持首动作由原物理数组与上一 clipped 命令核对，两评分口径逐案例分项闭合，最大误差2.22e−16。完整任务回报、D/C、同包native完整名义、独立seed1/2和H均NA。0.90/0.88仅在完整物理回报与原门槛共同满足后可用。新独立manifest、总报告、PROJECT_STATE、B0_START/NEXT_RUN随本次提交保存。训练/评分大数组与完整恢复权重留在AutoDL。

## 2026-11-24｜7180672轮结束后的审查：集中迁移，算法开发后置

### 用户决定、读取范围与实际操作

用户本次明确：“先专注于做迁移，迁移成功后再做算法的开发”，并要求下一轮计划、启动提示词和GitHub推送。本次将这一顺序写入当前规则、状态和全部执行入口，保持独立方法SuperMimic-M1Piper-standard-v1。实际操作为只读代码/结果审查、文档修改和发布；新增训练、仿真评测和硬件动作均为0。

以本地95159f77745d754b41ca135c726e2f2ba55c907e开始，git status clean；git fetch origin main后核对四个实验提交，fast-forward至71806725b66e1aec0ac03536737edf31e669ac40。GitHub branch main回读同一SHA，tree为424d2eb7e7bb36cd6bcc50cd75ff916cba7fb485。相对95159f7变更清单119文件。读取当前报告、配置/执行路径、原始小结果与近日工作记录，独立复算全部230正式案、460分项和15训练过程账本。没有在本次登录AutoDL加载所有大权重/原始数组，没有声称重新观看本轮视频或逐字读到不可访问的历史对话。

并行完成结果复算、代码语义审查和下一计划评审，由主任务集成。通过GitHub回读固定abc124c的ReplayBuffer、WorldModelEnv、runner，以及dd51a9f的manager_based_rl_env，直接核对采集/复位/因果历史语义。既有论文指标协议保持。

### 实测复算与仍未完成项

23个checkpoint×backend组合各十项，230条全失败，129条首2ms且均door_force_limit。仅canonical u350前拉release产生登记阶段事件，retreat_arm未完成，u500未保留事件。460条坐标分项和按原分母复算最大差2.22e-16。八条配置都是seed0，15个过程退出码均0，按恢复父节点去重新增1350 H32、13500 WM、27000 Critic、3081019完整数值有效转移、7296000模拟lane控制区间、11059200 imagined steps。进程时长合计2.069350小时，重叠合并墙钟0.664912小时，独占GPU小时NA；完整回报/最终候选/D/完整任务C/native/独立seed/H仍未形成。

区分两种预算：u500是保留旧采样/调度的canonical-effort单位配对；包含ReturnSampler、Ratio、clip-last、grip、fixed-stats、lane-age的最完整组只到u50/54028转移。不能把前者的长训失败归给后者。已实现effort/reset、采样/调度/末帧等不重复列为待办，AGENTS原有陈旧条目已更正。

### 查明的问题、排除的解释与下一实现

固定统计u50 replay：H7 15707合法窗open/hold=0；H1/Actor 24812起点中572为open/hold，原抽样约2.305%、lane-age约2.601%。可回查力的594/933样本中整个首20ms持续双指均0，其余力未知。该定义不代表起点瞬间没有握持。

核读contact_warp后明确：训练首物理失效不会截断十子步，valid_full_interval检查数值与容量；首次失败的完整区间仍进入H1/Actor，随后lane退出。审查中曾考虑的“首2ms失效起点被Actor全部过滤”假设已排除，正式计划没有据此重构Actor池或引入教师Actor初态。正式评分器首失效停止的语义与训练collector分开。

更具体的固定来源差异是：官方env逐lane终止后auto_reset，当前40步cohort死亡lane等待至下一批。下一轮对齐这一生命周期，沿已有reset(ids)接口保留真实200ms前缀及独立clock/history/prev_action，增加episode边界避免H7跨reset；前缀、诊断与策略经验分账，Ratio和Sampler不改为新奖励。该差异已证，控制收益仍待实测，不宣称解决了首步超力。完整resume需要物理状态/solver所需状态、接触计数、RNG及所有学习状态；否则明确边界截断后重建前缀。

WM的固定统计u50双指H32 TCP P95为104.18/107.70mm，最完整lane-age为242.02/196.77mm，held_r2为50.53/40.36mm。接触预热与覆盖仍不足；小型native梯度检查不能代表Warp全域H32梯度，encoder证据也不支持全面饱和。下一轮只用原H1/H7损失做训练数据预热，教师仅用于WM，不加新loss/BC/解析控制。新数据初始化不能冒充同清单resume，fit_contact_model旧native held teacher/teacher_samples标签须按真实来源修正。

### 已形成的可执行计划和阶段门槛

新增docs/B0_STANDARD_TRANSFER_PLAN_20261124.md、reports/B0_STANDARD_ROUND_REVIEW_20261124.md、docs/GOAL_GAP_20261124.md与results/b0/standard_review_20261124/audit_summary.json。顺序为：一条标准配方→采集生命周期/接触覆盖→原WM预热→真实H32联训→原物理验收；最多一个明确小对照。建议WM 0/200/1000 minibatch、联训u0/1/10/50及有据u100/200后续检查，均非强制终点。以双侧持续双指、受控门力、失败时刻/阶段和独立误差决定续训，不重复单位试验，也不盲延长旧u500。

迁移成功仍须同候选十项接触、各D≥18/20、Warp两侧各1条完整nominal通过/C每侧≥18/20、同包native两侧各1条完整nominal、持续H32、seed1/2独立B0-03与后续门槛、全冻结后H每seed/侧≥40/50，并同时达到完整物理回报0.90或项目0.88接近带。没有合格结果不进入算法开发。动作BC/参考直通/解析补偿/新reward或风险头/phase-TD/课程/新网络/新任务统一后置。

同步AGENTS、PROJECT_STATE、README、总路线、B0总计划、指标协议的当前实施说明、独立结果入口和B0_START/NEXT_RUN。旧11月23日计划/审查/差距页标注历史，不删除原失败。原实验代码、配置、小结果和manifest不改；本次仅新增独立审查JSON。

### 验证、GitHub交付与下一项

执行文档链接/引用路径、JSON解析、git diff --check、当前/历史入口与指标分母检查。两名独立审查分别核对数值及计划可执行性，修正nominal每侧1案/C每侧20案的歧义，补全恢复物理状态与新WM数据来源标签要求。没有为文档修改新增仿真或无关测试。

普通提交只包含本次明确文档和审查结果，推送前再次核对远端SHA，发布后从GitHub回读main、计划、启动词和审查，再同步本地并核对字节。7180672及其前实验推送状态已确认；本次文档自身提交随本次提交保存，最终实际SHA在聊天交付，不为了预填自身SHA制造循环提交。下一执行者按B0_START实际完成实现、采集、训练与评分，并逐日继续本文件。

## 2026-11-24 11:16–11:26 北京时间｜逐 lane 标准采集与独立 WM 预热

Windows 默认 Tailscale SSH 在密钥交换前关闭。用 `ssh dev2-ubuntu-lan` 实际连通，开发机原 main 有四份跟踪修改及未跟踪 P5 结果。在独立 dog-and-arm-b0-lanes 工作树执行 `git fetch origin main`、`git pull --ff-only origin main`，GitHub API 与 git 均为 ee41ee3。AutoDL 原 pair-v1 为带修改的 detached 95159f7，15 份退出回执均为 0，lane_age 恢复文件约 750 MiB。新现场 /root/autodl-tmp/dog-and-arm-b0-lanes-v1 复用两个固定 vendor、B0 环境和标准锚点；历史教师包软链在 pair-v1 缺权重，已从 recovery 目录链接到新现场并实际加载。未重启旧队列。

固定唯一 seed0 配方 standard_lanes_v1。新 collector 同一批内按 lane 实际积分十个 20ms 前缀，随后只入库有效策略转移。复位依据首失效、数值有效性或参考末尾，各 lane 有独立 clock/history/prev/episode。H7 允许穿过记录块但禁止穿过物理 reset。每块保存所有 lane 的压缩时序，代表块保留子步。连续运行跨块不截断；进程恢复选择显式行政边界，清空未完成的物理片段并重建前缀，保留学习器、replay、采样器及 Ratio 欠账与 RNG。

实际执行 `bash scripts/b0/env.sh python -m scripts.b0.h32_contact_challenge --multimode --run lanes_modes_v1`。沿用旧握持扰动幅度，从 approach_arm/grasp/open/hold/release/retreat_arm 六个参考阶段各侧采集；84100–84107 训练、84200–84202 独立验证。历史策略只产生真实 Warp 动力学监督。训练与验证全部尝试保留。随后 `bash scripts/b0/env.sh python -m scripts.b0.fit_contact_model --episodes results/raw_large/b0/contact_held_r1/* --init-wm results/b0/contact_s0_wm_held_r2/wm_002000.pt --warp-train results/b0/recovery_b_grip_challenge_r1 results/b0/lanes_modes_v1 --run lanes_wm_v1 --minibatches 1000`。输入统计固定，优化器全新；新增200个 H1、800个 H7 minibatch，Actor/Critic 0 次。独立 `standard_contact_validation score --state-loss --device cuda:0` 同窗核对 0/200/1000。冻结握持集两侧 H32 双指 TCP P95 50.53/40.36 → 25.24/28.60 → 15.65/16.45 mm；新验证自由运动 68.99/39.16 → 19.45/24.01 mm，选择新增1000出口。

真实联训 `bash scripts/b0/env.sh python -u scripts/b0/train_contact.py --config config/b0/standard_lanes_v1.yaml --run lanes_s0_v1 --updates 50` 完成：55,723 条有效策略转移，71,680 个含前缀的物理 lane 区间。相同冻结 u0、85201 采样种子、各 128,000 个物理子步的 `compare_lane_collection` 实测：旧 collector 3,135 有效/256 episodes，新 collector 7,593 有效/528 episodes，双方两侧均无完整 20ms 持续双指。同 episode 状态、时钟、上一动作与每个 H7 跨行实际断言通过；数据率改善没有自动产生稳定握持。u0/1/10/50 正式评测独立运行中。

### 11:26–11:35 北京时间｜两次边界恢复、正式评测与首动作定位

实现与首阶段结果普通提交 54e8aa94833d2478619719cf8a1c83480d9141d3 已推送并用 gh api 回读；第二平台独立工作树同步快进。云端执行源基于 ee41ee3 加本轮代码，各进程 actual_config 有执行时源码摘要。提交前另补充 replay 的说明和 fit_contact_model 新清单恢复保护；它们不改变本轮执行结果。

- `bash scripts/b0/evaluate_standard_contact.sh lanes_s0_v1 <0|1|10|50> warp` 四组各 0/10。u50 背推释放首失效第29子步、峰力36.73 N，u0为第20子步、106.01 N（比较使用逐案 CSV 的实测值）。u10前拉释放拖至3001子步仍超时，其真实 qpos/physics_step 已用原 save_video 渲染并全解码，152帧。u50固定握持 WM 验证54.07/37.96 mm；较 u10 有恢复，仍差于预热出口。
- 用同一 config，`train_contact.py --config config/b0/standard_lanes_v1.yaml --run lanes_s0_to100_v1 --updates 100 --resume results/b0/lanes_s0_v1/cohort_state.pt` 加 50 次。原入口 `bash scripts/b0/evaluate_standard_contact.sh lanes_s0_to100_v1 100 warp` 再得0/10。背推释放延长至107子步、31.7 N；持握首2ms门力前拉/背推50.1/23.4 N。验证 H32 双指 TCP P95 79.26/52.48 mm。由此做一次后续节点，`train_contact.py --config config/b0/standard_lanes_v1.yaml --run lanes_s0_to200_v1 --updates 200 --resume results/b0/lanes_s0_to100_v1/cohort_state.pt` 加100次，再用 `bash scripts/b0/evaluate_standard_contact.sh lanes_s0_to200_v1 200 warp` 回收十项。各次训练经 `bash scripts/b0/env.sh python -u scripts/b0/train_contact.py` 启动。三次训练与六个正式评分进程均退出0。
- 两次恢复如实计为行政边界，均有128条已分配 lane，last_episode 分别1604、3474；恢复后重新运行前缀，保留优化器、RNG、replay、Sampler 缓冲与 Ratio 欠账。用 torch.load 重新读取三份 cohort_state，验证更新号、关闭的 sampler horizon、相邻节点权重 SHA-256。u200 留有2次到期未执行更新，未多计。训练合计310.13秒（共享 GPU 进程时间），H32 200、joint WM 2000、Critic 4000、想象1638400步。累计276480物理lane区间=56803前缀+219677有效策略区间，无等待和数值无效策略区间。首失效后的诊断积分25868个2ms子步属于已发出的恒动作转移；正式评测只计首失效时刻。预热和补采成本另列；独占 GPU 小时 NA。
- `python -m scripts.b0.inventory_lane_data` 按来源/身份/侧/相位盘点原生与两套 Warp 数据；新训练512 lanes/18223有效/68终止，新验证192/6925/22。冻结采集对照和所有联训块均按实际十个子步的指载荷统计；联训219677个有效区间中两侧都没有一次持续整段双指。u200正式十项0/10，六个稳定握持/开门首2ms超力；背推接近耗尽参考、门力0且就绪0，背推释放3001子步超时、就绪0。六个节点共60个正式案、36个首2ms、完成阶段事件0。完整物理回报和距0.88/0.90为NA；暂不进入D/C/native、独立seed或H。
- 首次 Warp 两档扰动诊断发现同批独立前缀的前拉状态分量最大差0.00834（混合单位），不足以解释微小中心差分。保留初稿在云端 entry_response_u50.json。改为把同一个实际积分所得前缀的 qpos/qvel/act（如有）/ctrl/time/solver warm-start 及接触计数传给每个分支，forward 后确认分支起始状态差0，并加同命令重复分支。`python -m scripts.b0.measure_lane_response --run lanes_s0_v1 --update 50 --wm results/b0/lanes_wm_v1/wm_001000.pt results/b0/lanes_s0_v1/checkpoint_000050.pt --output results/b0/standard_lanes_20261124/entry_response_matched_u50.json` 实际完成。第一动作采用u50、其后全用相同参考命令的H32记录动作误差，预热18.91/19.20mm，联训u50为582.12/69.76mm；这是两处状态的失败后诊断，正式首失效时间仍看原正式入口。两套Warp训练中整段双指open/hold夹口命令最大22.04/22.47mm，而实测u50策略首命令43.07/69.63mm，u200为42.29/54.64mm。未证明它是失败唯一原因。
- `scripts.b0.index_standard_returns`、`scripts.b0.index_grip_commands` 与 `scripts.b0.index_lane_round` 汇总同包分母、来源、原坐标和固定effort分项、首失效、各侧/相位数据及恢复账本。两个扩展节点仍无阶段事件、无持续双指，暂停同配方。下一轮优先测训练身份下真实策略首命令邻域的动作响应和 joint WM 抽样覆盖。保持原损失与标准Actor，完整成果索引见 reports/B0_STANDARD_TRANSFER_BASELINE.md 和 results/b0/standard_lanes_20261124/。大权重和原数组在独立AutoDL工作树，原主树修改、旧训练现场均保留。


## 2026-11-24｜27284e2轮结束后的审查与下一计划：首动作响应、WM数据贯通

### 范围、时间与接续事实

用户提供了11:40的最新轮交付，继续既定要求：仔细审查，更新下一轮计划和启动提示词，推送GitHub；保持“标准迁移成功并冻结独立结果后，再开发算法”。本次没有启动训练、仿真评分或硬件，没有重新加载AutoDL大checkpoint/原始NPY，也没有把当前不可访问的全部历史对话声称已逐字读过。审查时钟核对为北京时间16:20、16:30；这些是本次审查时刻，不是上午实验起止。

GitHub main已回读确认27284e2e7792d17376410a0d7459398f7ca1927b，tree abf718e56fd2d2f6961b40b75d6568fbeeb1bc04。相对ee41ee39170e5695f34cf62aa150328c000fb09c共279文件变更，两次实验提交为54e8aa9（11:26）和27284e2（11:39）。本机旧临时checkout本次已不存在，首次旧工作目录命令未启动；检查工作区后用 `git clone --filter=blob:none --depth 32 https://github.com/kaiwen123-yang/dog-and-arm.git dog-and-arm` 重建只含正常仓库的工作树，HEAD与origin/main一致且clean，未清理或覆盖用户现场修改。随后均用明确/bin/bash和正确工作目录。几处旧文档/结果路径查找未命中后用rg定位实际路径，没有据此虚构文件或结果。

### 实际复核与数值结论

并行完成逐案/预算复算、采集与WM接口审查、原目标与下一计划评审，主任务集成。读取最新AGENTS/状态/每日记录/报告/manifest/配置及相关代码，回读固定abc124c官方tracking_reward、world_model_env、policy_learner、models等；仍锁定abc124c/dd51a9f。源码取回是本次审查，不是新算法升级。

- 直接复算60条正式评分，0通过、36首2ms门力失败、0阶段事件；canonical与fixed-effort共120分项闭合，最大回报残差1.11e-16，分母浮点差7.11e-15。首失败后的吸收余长闭合。u200十片段均值0.181801只属片段，不可与0.90/0.88相减。
- 三段updates分别50/50/100，共200H32；54个cohort，219677有效策略+56803前缀=276480控制区间，1638400想象步，4793个failed lanes，25868个已包含于完整区间内的失败后2ms诊断子步。联训进程310.127秒不含全轮采集/预热/评分，更非共享GPU独占时间。u200的2次Ratio pending不算执行。
- 匹配collector为3135→7593有效区间，24.49%→59.32%，2.422倍；双方完整20ms双指均0。最新联训open625/hold462，共1087（0.4948%），pull591/push496，全部terminal。其他相位及独立分母存入审查JSON；首次失败区间已能进H1/Actor，未发现“全部被过滤”。
- 固定双指验证412窗/51lanes、450窗/56lanes：warm1000 15.65/16.45mm，jointu10 127.19/149.47，u50 54.07/37.96，u100 79.26/52.48，u200 26.65/19.91。新multimode双指warm20.83/15.60→u20024.71/23.06；自由起点warm19.45/24.01→u20050.65/38.49。

### 已查明的问题与解释更正

代码和actual_config共同确认：新lanes_modes_v1的512训练lanes/18223有效H1/15242 H7只进入fit_contact_model预热。standard_lanes_v1只替换WM初始化，train_contact.add_grip_windows仍加载旧recovery_b_grip_challenge_r1，ContactRun.update在线足够时2个H1均256在线、8个H7各192在线+32native+32旧grip。新multimode没有联训入口。断点是已证事实，是否导致全部退化/首步失败仍是待验证因果。

既有entry_response_matched_u50复算：policy中心满20ms真实夹口pull68.3545/push66.5100mm，warm预测22.4102/25.9767，jointu50预测22.0420/25.9503，第一段峰力51.08/33.19N。真实与WM同用两指q29−q30，单位一致，读数属于两处u50失败后诊断。它不等于u200，也不是正式首2ms。warm H32 TCP18.91/19.20mm不能掩盖首步张夹误差；后31步是公共参考动作，不是Actor自主闭环。

measure_lane_response借用正式保存的clipped_action，没有在重建training history/clock重新查询Actor；还把push v2参考目录写成旧contact_held_r1。v2登记old_prefix_identical，所以不能单凭目录断言短前缀物理错误。失败tick4/5与正式tick1主要有明确判定身份差别：源8750入口前三子步仍grasp，8753才hold，正式stable_grip从第一子步按hold判6N。此前考虑批量重积分可能改变状态，但不能把这两个时刻的差异全归数值漂移。下一轮分别保存training phase/formal eventphase并现场算Actor，正式裁判不改。

22.04/22.47mm是open/hold且持续整段双指的条件命令最大值。全相位native覆盖10–90mm，multimode约9.79–100mm，旧grip最大36.12/50.82mm。不能认定WM从未见过42–55mm，也不把22mm转成夹口限制。前缀最后目标10mm、真实起点21.44/21.74mm分别记录。

主任务用grip_commands.csv及action_units.json复算原固定effort罚：u200夹口20ms为−0.1876728164/−0.3586282466，J2为−0.7422522091/−0.0105749885，六正tracking总上界+0.1。此为代数值而非新仿真或正式2ms回报。故“缺握持reward所以必张口”没有证据；下一轮分解实际replay batch的tracking、rate、survival及Critic路径。未发现gain32遗漏、总/单指双倍错误或train模式暗改固定统计的确定问题；手指速度尺度0.02也不是输出硬上限，不凭猜测改积分器。

### 已写下一轮计划与明确实施范围

新增reports/B0_LANES_ROUND_REVIEW_20261124.md、docs/B0_CONTACT_RESPONSE_PLAN_20261124.md、results/b0/lanes_review_20261124/audit_summary.json。审查JSON来自已提交结果的复算，保留来源与未加载原数组的限制；原standard_lanes实验manifest/代码/配置/结果均未改。

计划按训练身份首动作分支→必要数据持续接入原H1/H7→原目标梯度解释→单一标准seed0实际H32/正式评分执行。起步12训练/6独立验证状态，Actor现场查询B0-03/u0与u200，臂/夹口2×2加参考中心/重复。仅训练身份动力学数据可进WM，验证/D/C/H不进；教师/干预不进Actor。新增平台固定数据配方：2H1每批192online+64Warp，8H7每批192online+32native+32Warp；Warp旧grip/newmultimode/newresponse按登记来源固定等份，窗口仍须合法episode。旧全在线H1与新配方区别透明登记，原网络/损失/H32/Critic不改。

从warm1000接续原损失WM，新增0/200/1000检查，选点看实际首响应与独立误差；不要求任意新导数准确率，也不以H32 TCP一项替代夹口。至多一个冻结Actor/Critic的WM数据保留对照。适配有效后必须用B0-03标准Actor与选定WM新开真实seed0链，u0/1/10/50正式十项；有物理改善再延长u100/u200。连续后续节点无物理改善则不盲目追加预算。所有新算法/VLA/硬件后置，原D/完整WarpC/native/独立seed/冻结H和0.90/0.88协议保持。

更新AGENTS、PROJECT_STATE、README、总路线、B0总计划、指标协议当前入口、目标差距、独立结果顶部及B0_START/NEXT_RUN；旧逐lane计划增加执行完成与新入口，历史实验原文保留。当前仍B0-04、candidate为空、完整回报NA，不将计划写成完成。

### 一致性检查与发布

检查相对文件链接/引用路径、JSON解析、git diff --check、最新与历史入口、预算和评分分母。独立复核新审查的数值与下一计划的标准边界。文档修改不新增训练测试或通用防御框架。普通发布仅包含本次明确文档与审查JSON；远端按expected_sha检查后更新，不强推，随后回读main/计划/提示词/报告并同步本地核对内容。27284e2实验提交已确认；本次文档自身提交随本次提交保存，实际提交号在聊天交付，不为写入自己的SHA制造循环提交。

本次发布前实际检查：15个明确变更文件、321个相对文件链接均存在，审查JSON可解析，git diff --check无错误。独立复审未发现数值或阶段边界阻塞；已补预热误差的直接来源链接，并将下一计划对训练起始phase的描述改为逐案记录，避免把单条参考的三个子步推广。

## 2026-11-24 16:43–16:54 北京时间｜B0-04 首动作与数据贯通

- 16:43 第二平台主树 git status、git fetch origin main 取得 0c81d82，保留已有 H0 修改及 P5 目录。从 origin/main 建立 dog-and-arm-b0-response。AutoDL 新现场 /root/autodl-tmp/dog-and-arm-b0-response-v1 复用既有环境与只读输入。原 lanes-v1 的 compare、response、matched response、三段训练和六次评分退出均 0；未发现其训练/评分进程。u200 完整恢复约 840 MiB，含 32 块 replay、6 优化器、2 个未执行 Ratio 更新。本轮从 B0-03 重开。
- 16:47–16:48 在新现场运行 bash scripts/b0/env.sh python -u scripts/b0/training_entry_response.py。采集前写 registration。12 个训练与 6 个独立验证起点覆盖两侧 grasp 前沿、hold/open 入口、release。现场积分 100 子步，按训练传感噪声查询冻结 u0/u200；每起点 28 分支，共 504 条相关轨迹，之后 31 个共同开环参考动作。完整求解器起点、动作、双 phase、2 ms 力/状态及终止留现场。验证在独立验证物理轨迹重建，目标来自已登记训练 clip。退出 0。诊断不计入正式成绩。
- 背推训练 hold 的 u0 在原组合、仅换夹口、仅换臂、臂夹都换时，20 ms 实际总开度分别为 70.5、88.2、53.9、21.7 mm。10 mm 指令不能单独保证握持。轮腿始终取该 Actor 命令。未引入 22 mm 裁剪。排除重复、验证和终止后长窗，响应 300 条训练分支，H1/H7=3696/2718；旧 grip=14396/11644，multimode=18223/15242，native=13640/13580。
- 16:50 warm_response_wm.py 从 lanes_wm_v1/wm_001000.pt 固定统计、新 Muon/Adam 完成新增 200 H1＋800 H7，每 batch 256，每源抽样实数在 samples.jsonl。继承 held_r2 2000＋前轮预热1000。三点分别运行 score_entry_response.py 与 standard_contact_validation.py score，复算同一批响应及两组独立窗，均退出 0。+1000 改善了两侧 u0 握持入口 TCP（36.67→15.67、29.48→13.37 mm），但旧握持集 H32 TCP P95 从 15.65/16.45 升至 39.51/25.37 mm。+200 两侧旧集也退化。按固定验证保留规则选择本轮 +0。真实端点速度代入原积分，验证 hold 四个真实 Actor 分支 20 ms 仍低估 29.95–46.64 mm。保持原积分和状态。
- 联训登记 standard_response_v1.yaml，H1 为192在线＋64 Warp，H7 为192在线＋32 native＋32 Warp。三 Warp 源合法 lane/age 等份轮转，新代码在原 update 取实际 batch 计数。正常 u1 在同一个官方反传图读原目标有符号梯度，输出留在新运行目录。u0/1/10/50 按原十项评分，由物理结果决定后续。

### 16:54–16:58 北京时间｜新 seed0 u0/1/10/50 及原目标实读

- 普通提交 ad29c8a 并推送 main，正常 fetch 回读同值；AutoDL 独立树切至该提交。命令 bash scripts/b0/env.sh python -u scripts/b0/train_contact.py --config config/b0/standard_response_v1.yaml --run response_s0_v1 --updates 50。Actor/归一化来自 B0-03，WM 为本次 +0，Critic 保留标准形状兼容层，联合优化器、RNG、replay、Ratio 新建。正常 u1 对同一 256 样本原图只读求导，149 个 episode、72 个 terminal、35 个 open/hold。夹口在 open/hold 子集的动作率 −13.28/m、Critic +109.81/m、全目标 +97.41/m。全批 J2/夹口分项和相对 L2 残差 0.125%/0.357%，原训练更新照常执行。
- 完成 50 H32、500 WM、1,000 Critic、54,251 有效区间。四点分别运行 bash scripts/b0/evaluate_standard_contact.sh response_s0_v1 <0/1/10/50> warp；每点 0/10、6 案首 2 ms 超力、0 阶段事件。旧固定握持窗 H32 TCP P95 在 u1 为 285.77/351.33、u10 为 443.34/343.79、u50 为 52.05/46.18 mm。所有每批来源、实际 episode、分相位/模式与窗口都已保存。u50 背推释放峰力从 106.02 降至 36.47 N，失败由第20子步推迟至第30子步，据此追加到 u100。
- 用 requery_response.py 恢复原求解器/历史/前命令/goal，另行查询 u0/1/10。独立前拉 hold 命令为 44.14/43.61/48.22 mm，背推为 49.48/53.08/61.23 mm，均从正式 hold 的第1子步失败。原 u0 命令与保存值逐通道核对。视频由 u50 背推接近正式记录渲染，136 帧、512×288、5.44 s，末点参考耗尽，0事件。

### 16:58–17:05 北京时间｜有据延长到 u100 与 u200

- --resume results/b0/response_s0_v1/cohort_state.pt --run response_s0_to100_v1 --updates 100。显式行政截断后重建 200 ms 前缀。u100 累计 108,390 个有效在线区间。原十项 0/10，stable_grip 前拉/背推首步降为 28.47/19.40 N；背推释放首次失败 204 ms，前拉释放退化至 84 ms。以双侧入口降力为依据延长同一 seed0。
- --resume results/b0/response_s0_to100_v1/cohort_state.pt --run response_s0_to200_v1 --updates 200。u200 仍 0/10；前拉/背推 stable_grip 首步 39.62/16.50 N，六个入口仍首2ms超 6 N。背推释放峰力 24.84 N，到第482子步（964 ms）工位漂移。三段合计 200 H32、2,000 WM、4,000 Critic、1,638,400 想象步、217,971 有效区间、58,509 前缀区间、27,668 失败后诊断子步。六点本轮共60案、36首2ms超力、0阶段事件。open/hold 1,094 区间中1,091个terminal，全部在线区间完整20ms持续双指为0。
- 每节点用原正式脚本，u1/10/50/100/200 也在旧握持及多模式独立集上测 WM。u200 旧握持双指 H32 TCP P95 73.55/35.84 mm，多模式 85.51/34.77 mm。新响应在联合 H1 实抽 8,533 窗，H7 实抽 17,067 窗。此数据通路已实证，新增数据对全部失败的因果份额未单独辨识。u200 已到本轮登记端点，阶段事件仍为0，保存局部改善与回退，候选为空、完整回报NA，D/C/H、完整 native 和额外 seed 未执行。

### 17:05–17:13 北京时间｜恢复、判读更正与独立结果交付

- 逐段加载完整恢复文件，父末点/子起点的三个网络张量分别相等。u200 完整状态 883,906,745 bytes，6个优化器、32块replay、CPU/CUDA/NumPy RNG，Ratio pending=1，不计入已执行预算。用相同恢复 RNG 复抽 H7/H1 各256窗，state/action/context 与样本来源逐项相等，优化器更新0。所有正式2000批均实际取到192在线，无回填触发；复核未触发的空在线分支并修正H1回填为192 native＋64 Warp，单独实抽回执入 resume_draw_check.json。
- 同一保存起点再查询新链 u100/u200 并实测首动作。u200 验证握持前拉命令/实际/WM=32.75/26.88/18.86 mm，背推=63.72/63.89/28.99 mm。局部方向按同模式、同终止子步、超出重复差异筛选；在独立验证剩余扰动中，+0 WM 对夹口自响应43/48同向，对J2交叉响应4/21同向。固定物理动作单位。大状态、逐2ms求解轨迹、模型输出留新 AutoDL 树。
- 复核发现首版前沿分支从 grasp 建独立事件计数器，而正式 approach_grasp 从 approach_arm 起算。使用 relabel_response_events.py 在已保存物理数组上重读正式 run_spec、完整阶段序列和注册时钟；三套起点矩阵都已更正。轮载阈值比较也与原 ContactMeter 的 ≥ 对齐，已存数组没有恰好等于阈值的轮载。训练 phase 与 WM 窗资格均来自原训练参考，正式十项始终走原评测入口。更正次数、逐案判读与失败后 phase=-1 已保存，额外物理积分和参数更新均为0。
- 更新独立报告、manifest、逐案分项、误差、成本、恢复位置、项目顶部状态和 NEXT_RUN。目标仍是先成功完成标准迁移；本轮封存独立负结果。下一项只针对现有子步数据中的开度积分残差、J2交叉响应和接触时钟。普通推送及 GitHub 文件回读结果随聊天交付。


## 2026-11-24｜753f1bc轮审查与集中迁移推进计划

### 目标、时间和读取范围

接续用户已完成的753f1bcca6d4f5dd48b1b2886e3523036c7d366d实验回执，继续执行审查、下一计划、启动词、目标差距和GitHub发布。用户随后明确要求一次性多推进，不能每修一个bug就结束一轮。因此本次计划已改成集中迁移推进：相关问题并行定位、已证平台问题集中修复、原损失实训和持续物理评价；到达一个门槛在同轮接下一层。先迁移成功、冻结独立结果，再开发算法的顺序不变。

本次核对时钟为北京时间17:26、17:38、17:43；这些是审查时间，不是实验起止。GitHub实验提交753f1bc的提交时刻为17:14:05，tree为d4260fa5fd51a990ad6f4161df1703b8d1af271a。当前本机checkout正常fetch/fast-forward到该提交，开始时clean；发布前再次通过GitHub读取main仍为该值，未覆盖他人提交。

本次读取最新AGENTS/状态/每日记录、报告/manifest/配置及相关采集、WM来源、状态映射、物理控制、评分和梯度代码，并对已提交CSV/JSON/JSONL复算。并行分工为实验统计/资格、积分/solver、原目标/更新边界，主任务集成。未登录AutoDL重读大权重或原始2ms NPY/NPZ，没有运行新训练、物理仿真或硬件。未把不可访问的全部历史对话或仓库外资产声称已逐字读取。首次固定官方representations目录路径未命中后，定位正确文件src/supermimic/representations.py；不将未读文件当证据。

### 逐案、预算与抽样复算

- 最新轮仍是u0/1/10/50/100/200各0/10，独立60案、36首2ms门力失败、0阶段事件。canonical/effort共120个分解检查，最大归一化误差1.11e-16，完整分母与执行/吸收时长闭合。u200十片段effort均值0.0397368595，不是完整双侧任务回报，不能与0.90/0.88相减。旧27284e2的60案、7180672的230案分开。
- 三段新增50/50/100共200H32，2000联合WM、4000Critic，1638400想象控制步。54cohorts，217971有效策略+58509前缀=276480物理区间，4974failed lanes；27668失败后诊断子步已含在区间中，不重复加预算。训练进程时长合计326.2678秒，逐案评分physical_wall_seconds合计137.6926秒；两者均不是独占GPU时间、仿真时间或全轮端到端成本。u200 Ratio pending=1未算更新。
- 源manifest记录整段20ms持续双指为0，open/hold1094且terminal1091。本次没有重新从现场子步数组复算这些数，审查JSON标source_recorded。
- 实际WM抽样H1：76800online、8534grip、8533multimode、8533response；H7：307200online、51200native、17066grip、17067multimode、17067response。512000窗口/2969600后继目标/3481600stored positions，全部2000批各256且在线份额实抽满。新数据贯通确已完成。online H7的open/hold起点和two_finger均0；online H1 open/hold853、two_finger0；response H7 open/hold1719、two_finger6659。不能再用新数据未入联训解释全部退化。
- response注册12train来自4条源物理轨迹，6validation来自另2条验证轨迹；28分支/起点互相关，去3个repeat后300训练分支不等于300独立试验。代码保持train-only、连续合法前缀、首失败完整区间、跨终止边界。3696H1/2718H7是源库存记录，缺现场NPZ不冒称本次重建。
- WM旧握持H32 P95：+0 15.65/16.45mm、+200 102.42/27.83、+1000 39.51/25.37、jointu1 285.77/351.33、u200 73.55/35.84。新预热有首响应/J2局部收益但未保住旧/多模式验证，选+0有依据；新增1000预热消耗仍保留。未执行隔离的数据配方因果实验，不从跨轮差异推断独立作用。

### 新明确证据与尚待验证的原因

固定官方abc124c representations.py直接给出c=(N+1)/(2N)，注释是恒加速度下N个半隐式子步合成。本平台dt=.02/c=.55与公式一致，不是已发现系数写错。full_state指位置29:31/速度59:61；raw qvel指速度28:30；总开度动作到主动指乘.5、实际开度q1-q2，没有在该路径发现简单乘二或H1终点错位。

验证hold/u0真实20ms开度50.4096/71.5754mm，+0WM21.8481/22.3399，真实末速度oracle19.7080/24.9447，残差-30.7016/-46.6307mm。此20ms含正式首2ms失败后的诊断积分；不能直接据此宣称首2ms因果。代数e_g=E+.011e_w成立，若两指位置各<=2mm且速度各<=.05m/s，必要|E|<=5.1mm。它说明这些样本无法同时达到现有位置/速度归一尺度，不是新的物理门槛或位置硬误差下界，模型可牺牲速度来拟合位置；真实2ms闭合尚待现场执行。

同一验证hold/u0的ref_arm分支，净门力峰为0、双指同时受载tick为0，oracle仍-27.075/-30.114mm；这不证明各单指载荷或所有门接触都为0。ref_arm_jaw残差-1.380/+0.01849mm，背推该诊断区间4.9348N、10/10双指，不是标准Actor正式通过。因此不能把所有残差归门冲击，也不能宣称GenCoord对夹口一概失效。

明确发现待核代码路径：training_entry_response.register_solver在真实前缀后全批forward；ResearchPlant.reset(ids)也全批forward；step_contact在下一sim.step前读缓存qfrc_bias形成ctrl，连续策略区间不一定额外forward。固定dd51a9f Simulation.forward没有env_ids。代码路径成立，但物理影响未实测，未称bug。计划从尚未额外forward的live状态配对连续/登记forward/旁lane reset，而不是先统一forward再伪造对照。

局部方向4/21与43/48计数成立，但只是同双指布尔模式、同failuretick且高于一次repeat差的单侧割线，不是总体梯度正确率。已有J2两档变化有不一致，先用已有正负两档看尺度/中心差商，不加梯度loss。旧check_contact_gradient为native/H7且channel20=J5，不冒充当前Warp/channel17=J2。

原u1梯度35open/hold的rate-13.28、Critic+109.81、whole+97.41 /m，全256whole+4.419/m。35模式为34loss_or_slip+1release，非35完整稳定握持。该图位于当次8H7+2H1 WM之后，Critic本轮首次拟合之前；接触Critic第一层重建、兼容层继承。首动作导数不等于共享参数经裁剪/Muon/Adam后的更新。实际u0->u1前拉44.14->43.61mm、背推49.48->53.08mm。分解残差全批jaw0.357%、open/hold0.365%、均值约.250/m，原因未闭合，不先当纯浮点误差。源码未发现hook新增RNG或改目标，但没有开关配对回执，未声称实测bitwise等价。

### 用户要求扩大推进范围，已落实为同轮闭环

新增审查reports/B0_RESPONSE_ROUND_REVIEW_20261124.md、计划docs/B0_TEMPORAL_COMPATIBILITY_PLAN_20261124.md、复算摘要results/b0/response_review_20261124/audit_summary.json（原实验manifest保持）。计划要求三个工作面并行、共享模块单一负责人，已有充分证据的实施不等待整份文字完成。先用既有2ms数组核对q/v/时钟、必要solver小配对；修已证接口，只有微步闭合且粗端点不相容时才执行一组T2/C20。

T2是条件数值候选，未实现/验证。相同原网络/初始张量/固定统计，微步2ms/c1复合十次、外层20ms；完整31路prediction持续固定乘h/H=.1再走原解码，不再重复缩末层/velocity_units。独立micro rep/Dynamics，宏步loss/reward不变；官方Dynamics构造保存dt及绑定apply_prediction，不能临时改共享属性。H1在20ms、H7在七个20ms粗边界按原loss评分，微步无新loss/真值回填，Actor H32仍640ms、内部320步完整可微。

配对每臂最多1000WM批（200H1+800H7、batch256），0/50/200/1000检查，相同真实抽样索引，新原优化器；原控制回执完全匹配可复用。每臂1484800粗后继实例，T2约14848000内部前向，C20约1484800，两臂约16332800且未含验证/反向；样本匹配不等于算力匹配。内部2ms路径由粗端点不唯一识别，须独立验证，不能以内部失真换粗端点好看。验证不通过停止候选，在同轮定位/修复下一已证平台问题；不强行用坏WM开H32，不默认加微步监督/新网络/奖励。

有效WM出口后，从标准B0-03 Actor+选点启动一条主链，原u1内嵌必要梯度观察。u0/1/10/50/100/200为检查点，有真实物理改善继续350/500等并登记追加预算，u200不作默认上限。无改善停止配方，在本轮继续最小修复/必要train-only补采/复测，保留旧负结果与新配方身份。原轮u200仍有背推释放改善，停止理由已纠正为登记端点封存。

同一个候选十项10/10后当轮直接D每项>=18/20，再完整双侧Warp nominal、C每侧>=18/20、原native3.3同包完整nominal与持续H32证据；条件具备继续独立seed1/2各自B0-03。三seed配方/选模/候选全部冻结才H，每seed/侧>=40/50，H不得反向选模。开发失败可在本轮按证据处理，但D/C/H个案不能导入训练，也不能拼多个checkpoint/片段。整轮交付为可验收阶段，或已经过必要对照和复测仍在的具体阻塞；单次bug/诊断/预热/u200均不是默认终点。没有保证学习一次成功，迁移前不进入算法/VLA。

### 文档一致性与发布

重写B0_START与NEXT_RUN，更新AGENTS、README、PROJECT_STATE顶部、独立标准结果顶部、总路线、B0总计划、指标协议入口和GOAL_GAP；旧首响应计划补执行回执，原实验报告只加后续审查入口，保留原数值。目标差距明确当前6.60/2.75倍门力仅为两个入口的力距离，完整回报差NA、整体进度不捏造百分比。

逐案/预算复算、源码/代数与计划边界分别复审。已收紧零门力/双指计数含义，给35样本梯度追加manifest来源，标137.69秒为评分墙钟，20ms表附近说明失败后诊断。当前所有运行代码、配置和原实验manifest/数组未改；本次是文档及审查证据交付。发布使用GitHub普通更新、expected_sha检查、不强推，随后回读main/关键文件并同步本地。753f1bc已确认；本次自身提交随本次提交保存，具体SHA在聊天交付，不为内嵌自己的SHA重复提交。

本次发布前实际检查：16个明确文件（文档与审查JSON），392个相对文件链接全部存在；审查JSON可解析且47个source_paths存在，git diff --check通过。数值/代码与阶段边界独立复审完成，修正后各入口均体现用户集中推进要求。本轮未修改学习代码、配置或原始实验manifest。

### 2026-11-24 17:54 北京时间｜集中迁移轮启动与真实积分初核

第二平台原 main 工作树保留四个已修改文件和一个未跟踪目录；正常 git fetch origin 后，确认 origin/main=b5831d7、753f1bc 为其祖先。在第二平台与 AutoDL 各开独立工作树，训练现场 /root/autodl-tmp/dog-and-arm-b0-temporal-v1，链接既有环境和历史大资产。现场一张 RTX PRO 6000 Blackwell；进程共享使用。并行复核真实 q/v、solver 、数据/原损失及原更新路径。18 起点×28 分支的 float32 两指单微步最大残差 3.58e-9 m；按10步速度求和最大 1.50e-8 m。验证两侧 hold/u0 的 20 ms 开度 oracle 残差 30.70/46.63 mm。微步几何闭合成立，尚待同命令 solver 配对与数据资格决定训练入口。

### 2026-11-24 17:56 北京时间｜求解器配对、修复与原数据兼容范围

保留完整 live Warp Data，复走两侧 hold/u0 与 ref_arm 的真实 200 ms 前缀。额外 forward 和旁 lane reset 改变首 ctrl；修前背推最大开度轨迹差约 0.00513 mm，净力差约 0.01136 N。新登记复制连续路径的 bias，旁 lane reset 仅为被重置 lane 更新该缓存。四组修后首 ctrl、bias、warmstart 逐元素一致，首失效子步相同；修后上述两量最大差为 0.0000611 mm、0.000104 N。旧 grip/multimode 使用同批连续路径，旧独立正式评分逐案单 lane。18 个响应起点按修后身份重新执行，旧结果保留。代码见 scripts/b0/check_solver_continuity.py 与独立目录 solver_before.json、solver_retest.json。源资格、宏端点/内部积分验证与真实预热分别记账。

### 2026-11-24 17:57–18:04 北京时间｜原损失配对、双侧验证和正式锚点复测

修后所有 18 起点重采完成。验证 hold/u0 的 20 ms 端点开度残差仍为 −30.695/−46.629 mm。由此按计划各训练一条 C20/T2，从 response_wm_v1/wm_000000.pt 原张量和固定统计起步，用新的 Muon/Adam。实际训练先产生 paired_indices.npz，再分别重放同一批索引；+0/50/200/1000 检查点保留。每臂 1,000 批、200 H1/800 H7，七个 20 ms 边界全部评分。T2 +1000 的独立验证首动作开度绝对误差从 C20 +0 的 28.49/49.22 mm 降至 16.89/30.72 mm，原握持 H32 TCP P95 从 15.65/16.45 mm 升至 434.56/488.61 mm。C20 +1000 对应 28.04/43.44、20.97/30.20 mm，多模式也退化。没有选点或新增 Actor 更新。原实现及物理记录提交 b806b96 已普通推送，从 GitHub main 回读一致。

过程偏差：+200 判断时检查了有限输出、验证曲线和末批梯度；随后才从逐批日志发现 T2 在 +51..200 的 H7 裁剪前 P95 为 8.68e6、最大 6.07e8。按计划应先停在 +200 排查。T2 已多执行 +201..1000 的 800 批（160 H1、640 H7，11,878,400 次内部前向样本），计入总预算；该段仅作事后诊断。补做同节点分源和原图复测，并修正训练入口，使每段落点显示和保存 H1/H7 整段 P50/P95/最大值、裁剪次数与显存。六份节点回执由当时原始日志重建。

以封存的 response_s0_v1/checkpoint_000000.pt 在新树的原正式 Warp 入口独立回归。两套 manifest 各五个名义案，不开 D。共 0/10、6 案首 2 ms 超力、0 个阶段事件。这是同一冻结 Actor 的复测，新增策略候选评分为零。已按实测分别复核八条原 native 数据建立的固定统计、实际双侧训练抽样、编译模型伺服与限幅，以及旧 u1 的实际参数和归一化变化；对合法窗腕速和 T2 早期不稳定继续做真实/原图对照。

### 2026-11-24 18:04–18:12 北京时间｜原失败复测、双后端定位和交付

完成 +200 冻结权重的 C20/T2 原 learner、显式十微步、FP64 局部中心差分对照；没有额外优化器更新。选定相同握持窗，FP64 的 H7 参数梯度 1.662/12,489.78。T2 七个粗端点损失、输出和梯度与原公式相符；第28微步约4.423的局部导数可用三档中心差分复现。历史第85批尖峰对应+84权重，本次+200诊断不能逐次还原历史尖峰。paired_source_loss.json、recurrence_u200.json 在独立目录 wm_validation/。

合法未终止 J6 速度训练/验证达到 90.09/88.38 rad/s。实际重放七个不同极值窗口及两侧四个hold首命令，又用无接触单铰链核对。两引擎参数一致时，native3.3保留饱和执行器速度导数，3.16/Warp在饱和处置零。冻结质量矩阵与力，仅交换J4/J6两个导数可重现选定首步数值分歧。三个引擎两侧验证hold首2ms仍为约51.31/32.98N，原正式冻结锚点各为51.07/33.15N。进一步按实际配对抽样回查每臂32,000个native窗口、185,600个监督后继实例，J4/J6命中饱和均为0。已保存两侧逐案物理重放、分源统计与早期梯度证据；本轮没有可信WM出口。

八个checkpoint重新加载，逐张量检查+0初值、各点固定统计、optimizer/RNG、checkpoint时钟和独立分支身份。更新独立manifest、报告、状态和接续入口。AutoDL 及第二平台均使用独立工作树。第二平台直接HTTPS推送缺少登录凭据，改走Windows已登录账号和普通Git快进推送；b806b96已从GitHub回读。训练代码、预算和物理回执随本次最终交付归档，完整提交号及远端回读结果在交付消息提供。


### 2026-11-24 18:16–18:43 北京时间｜ff2d1e8结束轮审查与下一集中轮发布准备

#### 目标、现场范围与继承

用户提交时间配对轮结束回执，接续既有“审查最新轮、给下一计划/启动词/目标差距并推GitHub”的工作。继续落实用户此前“一次性多推进”，同时保持先SuperMimic标准迁移并冻结独立结果、后算法/VLA的顺序。本次本机checkout正常fetch并快进到ff2d1e8af6a287cbad106fb88c557a080d7ade0a，起始clean；GitHub于18:42回读main仍为该值，tree ddf62bad729868004975fd6e4e181f4ce6dd8659。该实验提交时刻18:13不是本次审查起点或实验训练时长。

读取当前AGENTS/状态/入口、原报告/manifest、实际paired_indices.npz与CSV/JSON/JSONL、物理控制/状态表示/重标/WM训练评分代码；并行由实验资格、模型统计与物理后端三个工作面复核。直接核对固定abc124c的representations、wm_learner、supermimic_runner，以及MuJoCo3.3/3.16官方导数源码与3.3计算说明。使用exec/Python复算、ffprobe读取两视频时长并抽取既有失败帧；没有运行新物理仿真/训练，没有访问AutoDL重读原始2ms数组、大权重/优化器，没有硬件动作。未声称读取不可见的全部历史对话或仓库外内容。

#### 实验结果、预算与样本资格复算

- 冻结u0正式10案/0通过/6首2ms超力/0阶段事件，stable_grip前拉51.0705427N、背推33.1508602N。十案失败原因一致，前拉release_retreat失败tick由历史504变502，不写成全部时刻相同。原60案单列，本轮新Actor/H32和联训Critic均0，最终候选与完整回报null。
- 每臂1000WM批=200H1+800H7、batch256，共256000窗口抽样/1484800监督后继实例。C20网络前向1484800，T214848000，不计为真实采集转移。六训练进程时长和243.377425秒，重叠区间并集163.274359秒；内部训练循环31.140221/113.788937秒、正式物理评分和18.096080秒是其他口径，不混成独占GPU或整个研究轮耗时。
- 同一保存抽样索引实际进入两支，四源窗口按已记录episode长度无越界。训练12起点来自4轨迹，验证6起点来自2轨迹、已多轮用于开发；28命令分支相关。train hold/u0两侧只有一条合法H1/零H7，实际H1抽45/54；参考臂首窗口进H7为18/13。native用状态长度粗算比账本多10窗属terminal partial interval资格排除，未读现场valid数组，不误报账本错误。
- C20+1000旧grip双指H32 P9520.9719/30.2006mm，相对15.6533/16.4461增约34%/84%，多模式14个有数据层均退化。未发现代码实现逐层零退化布尔门，但原“保持”未量化。拒收不只是小层舍入，14个相关层也不是14独立试验。
- T2+51..200 H7裁剪前P95 8.67566e6、最大6.06927e8，120批全裁剪。后800批按事后诊断保留预算。冻结+200定向同窗FP64梯度1.6622/12489.7779，局部差分一致；历史最大第85批用+84权重，不冒称同一权重完整复现历史峰值。全区间记录修复应继承，不能再只看末批。
- 两段视频896×416、25fps、371帧、14.84秒。真实validation响应320个2ms子步约0.64秒，慢放/停顿后才14.84秒；首画面约51.31/32.98N、指载荷0/36.28与23.32/0N，区别于正式锚点51.07/33.15N。u0首20ms后是参考命令，不能当全片由新策略执行或正式存续。

#### 新判断与边界

solver修后12行首ctrl/bias/warmstart零差，最大开度差6.1035e-5mm、门力差1.02997e-4N，关闭为已解决接口，继承preserve_continuous_bias=true。修后hold/u0的20ms oracle开度残差仍-30.69458077/-46.62912993mm；q/v闭合与重复只证明当前离散记账自洽，尚非步长收敛证据。

新解析复算：单指e_q=r+.011e_v；原sigma_q=.002m、sigma_v=.05m/s。只优化这两个原二次分量时位置残差保留系数.9296920395，两指开度折中28.5365074/43.3507309mm。C20+1000实测28.0390472/43.4367371mm、C20+200前拉28.5339870mm。不是网络全局最优、不是位置硬下界，也不证明首2ms因果；但不宜继续要求同公式同loss无限预热消除这两个误差。

同一hold/u0首TCP误差C20+0→+1000为36.708/29.477→15.119/13.794mm，J2速度误差6.087/2.135→.01295/-.25242rad/s，六臂速度RMSE7.232/11.299→1.997/.787。存在局部收益但旧H32退化，支持前瞻有限物理学习试验，不追认原选点。现有C20H1/H7未见T2量级爆炸，Actor H32反向仍未验证。

合法快速腕部J6 z约806/790，旧online最高约1004；两个hold/u0初态state z仅2.21/1.41，不能用其他窗的大z解释全部首动作问题。原统计来自8native/10808合法输入。官方runner会flush新采集WM统计；当前固定是平台配方。首层函数保持重标早已在contact_training实现，11月23日wmcoords-u50为0/10，本次不包装成新发明。step0函数和物理Jacobian保持，后续Muon/Adam优化不等价；参数梯度换坐标不能直接比较数值判稳。

首配对H1/H7响应源loss份额99.34%/99.90%只来自两批，缺源梯度方向，尚未证普遍梯度冲突。native每臂32000实际窗/185600监督后继中J4/J6饱和或98%临界均0；冻结M和力仅换两个饱和导数复现后端差异，支持局部机制，不能因此删除native池、认3.3是真值或解释全部首2ms超力。

#### 下一轮执行变更：有限出口和同轮连续推进

新增docs/B0_DYNAMICS_TRAINING_PLAN_20261124.md、reports/B0_TEMPORAL_ROUND_REVIEW_20261124.md与results/b0/temporal_review_20261124/audit_summary.json。物理主比较在固定实际训练Warp内11窗2/1/.5ms，只有必要关键窗.25/.125；CPU后端复核另列。保持归档完整23ctrl及外部servo原2ms缓存采样相位/preceding-solve延迟，不能冻结引擎内部qfrc_bias或把细步最近bias当原缓存。q/v端点、force/site的solve起点和裁判判定时刻分别保存。按重复差、相邻细化收缩与响应模式判断，不把最细档自动当真值，不要求误差等于浮点噪声。

若原2ms数据可用，直接继续；必要细步训练则在同轮统一时间/schema/c系数和受影响数据，原2msWarp/native3.3正式门槛保持，细步成绩不得填旧表。C20物理2/1/.5ms对应c=.55/.525/.5125；两支相同新物理和数据身份，旧C20+1000退为历史锚点，不能用不同数据归因统计。

B只做一次train-only重标后固定，原索引/原loss，新原优化器；旧物理身份时最多新增1000WM批、旧控制复用，新物理身份时至多两臂各1000。不加微步监督/截断递推/新loss/网络/奖励，当前T2不再追加。先锁唯一H32实验WM：默认C20+1000，重标+1000只有预登记两侧首TCP及旧grip/多模式H32 P95六项不劣且无新失控才替代；H32结果打开后不换第三支。

明确前瞻修改旧“所有H32先过WM保留门”的执行条件，仅新增development_h32_pilot；原ff2d1e8 selected_wm=null不变，新pilot_wm分开。两支同B003Actor、Critic/target、归一化、初始replay/实际首批、优化器配置、RNG/Ratio，更新前和正常u1原图均留证。两支各至u10，合计20H32/200联合WM/400Critic，离线预算另计；除完整性/数值故障外不因u1仍0/10取消u10，不因loss变好越预算。u1配对因果最强，u10采集可自然分化，只比较整体闭环适配。

有限实验有可重复物理收益后选单链到u50/100/200与必要后续；两次检查无改善停止该配方并在本轮处理已证问题。十项10/10即当轮D各≥18/20、连续Warp双侧nominal/C各≥18/20、原native3.3同包完整名义与持续H32；再独立seed1/2各自B003及后续，三seed全部冻结才H每seed/侧≥40/50。数据隔离、6N、原完整回报整段分母/失败吸收、0.90/0.88口径不变。目标差距没有虚构百分比或到达时间。

#### 文档、复审和发布

更新AGENTS、README各实际入口/目录表、PROJECT_STATE顶部、独立结果顶部、B0总计划/总路线、指标协议的开发试验说明、GOAL_GAP、B0_START/NEXT_RUN；旧时间配对计划加封存/新入口，原实验报告只加后续审查链接，原数据/manifest/代码/配置保持。三工作面只读复核后修正外部缓存与内部动力学的区别、主Warp后端身份、力/状态时间戳和有限试验先锁臂后看结果。

发布沿用普通GitHub提交与expected_sha更新，不强推。原ff2d1e8已回读；本次提交自身SHA在聊天交付，文档随本次提交保存，不为自引用反复提交。实际新仿真/训练/硬件均为零。下一次从仓库新入口执行，不把拟做计划当已完成结果。

发布前实际检查：16个明确交付文件，391个相对Markdown文件链接全部存在，审查JSON可解析且非有限数检查通过，两个原损失折中值与有限H32预算复算一致，git diff --check通过。运行代码、配置与原实验manifest/数组未改；原实验报告只加后续审查导航。普通发布后在聊天给最终SHA和回读结果。

末轮事实复核修正：目标差距表明确保留历史pair canonical u350的release阶段事件（随后retreat_arm参考耗尽、回报0.971913），本轮/response轮的零事件不扩大成所有历史零事件。审查中806/790仅称归一化z值，实际分母std+0.01，避免误称严格标准差倍数；数值本身不变。

历史事件补链后的最终相对文件链接数为392，全部存在；交付仍为16个文件。

## 2026-11-24 北京时间 18:55 起｜固定物理时钟与 C20 有限 H32 集中轮

从 AutoDL 的 ff2d1e8 现场正常执行 `git fetch origin main`，与 GitHub API 独立回读均为 `781cd1d4e45fa7acb61dad0f76fb13e72fcb68b7`。原工作树无已跟踪修改，六项环境链接和历史日志保留。新分支 `codex/b0-dynamics-20261124`，新小结果在 `results/b0/standard_dynamics_20261124/`，大结果在 `results/raw_large/b0/dynamics_20261124/`。远端 partial clone 按需取文档时出现 HTTP2/TLS 故障；用 16 个审查提交变更 blob 的 Git 对象 ID 复核内容并导入同一对象库，补齐未检出路径，复查 HEAD 与跟踪文件均一致。原 2 ms 和 native3.3 正式判据依旧。先比较固定 11 窗和原单位 q/v 分量；待数据资格确定后固定统计、实验 WM 与初始批次，再执行有限 H32。分项命令和实际预算随本条目追加。

**19:06 数据资格与重采。** `scripts/b0/dynamics_warp_windows.py` 已完成 11 个登记窗、固定全 23 路 ctrl、2/1/0.5 ms 各两次，另在四个影响决定的窗口复测 0.25/0.125 ms 和真实前缀的同相位 held 路径。前拉训练 grasp/t7/b23 在前三档门力峰为 0/44.60/14.14 N。细档双侧 hold/u0 峰 51.31/33.09 N（0.25 ms），0.125 ms 为 51.32/33.10 N，同样在起点超过 6 N。登记训练数值身份 `warp_250us_servo2ms_continuous_v1`，N=80、c=0.50625。绝对归档状态、重放状态及首次求解的差异随回执保留；细时刻的个别接触峰值仍不宜解释为力真值。原生四源之一已查过实际 native 抽样，继承原 native 教师；三套受影响 Warp 数据按原注册 split 与相同采集器重采。

统一 ContactPlant、C20 representation、采集/前缀/phase、部分终止回报、判定与记录：2 ms 缓存取前一外部周期起点的 bias，内部每步求解。20 ms 边界不改；部分终止点的冻结 2 ms 参考用线性坐标/速度和基座四元数 SLERP 求值。原始细步力、作用时刻、两指和首次失效均保留。实际命令 `scripts/b0/check_dynamics_clock.py --dt .002 .0005`、`--dt .00025`，三档双侧真实前缀均通过，23 路保持与延迟重算最大差为 0，旁 lane reset 后缓存逐位一致。19:06:21 并行启动 `scripts/b0/h32_contact_challenge.py --physics-dt .00025 --run dynamics_v1_grip`、同命令 `--multimode`、`scripts/b0/training_entry_response.py --physics-dt .00025 --preserve-continuous-bias`；每条显式输出目录分别是新轮的 grip、multimode、response。实际输出/日志在新轮 raw 的 logs/collect_*.log。原 2 ms 执行 `scripts/b0/dynamics_component_tradeoff.py`，76,719 个合法 H1，固定 hold/u0 两侧原损失折中和实测 C20 数据已单列。TorchScript 对 vmap 原单位 Jacobian 的数据指针操作报错，改逐输出反传保存四源结果；该探针没有优化器步。

**19:09 固定窗口复核。** 先在真实重建现场复放，少数起始 q/v 与归档最大差约 0.0031/0.066，补做完全相同的归档 q/v 起点，并保留两套结果。主规格 11 窗×3 档×2；四个关键窗另细化至 0.125 ms。实际调用 `scripts.b0.dynamics_warp_windows` 的 fixed_ctrl、archive_ctrl、snapshot_servo、live_servo 四种入口；CPU3.16/3.3 仅复核两窗。`scripts.b0.summarize_dynamics_warp` 汇总 228 份逐次记录，含重建/前缀共 1,225,840 个 Warp world 微步，CPU 两版本合计 1,940 步。脚本初版括号语法检查失败，纠正后实际运行全部退出 0。详细原始力时间轴与精确复测见新轮 warp_windows；不将诊断计入正式案例。两份源代码锁在现场分别为 abc124c、dd51a9f。`scripts.b0.dynamics_h32_pilot prepare` 用冻结 Actor 采到首个 Ratio 到期，128 lanes×40 policy ticks、2,086 有效区间、331 个 episode ID、待更新 2。新进程复核实际初始 Actor/Critic、136 个 Warp 数组、外部 servo 缓存及计数器一致。此时 H32 更新为 0。时间接口/前瞻登记保存在 20cc9ec。现场仓库无默认作者，沿用既有实验提交的一次性 Codex 作者参数。

**19:12–19:17 新源、预热与锁定。** grip 13 组（含校准），multimode 11 组，response 原 18/18 登记起点完成。执行 `scripts/b0/qualify_dynamics_sources.py` 复核排除重复命令、完整合法首失败区间、H7 跨终止、每个 20ms 的80个力样本及原划分；native + 三套 Warp 合计 50,479 个训练输入。部分终止时刻另用 `scripts/b0/check_dynamics_partial_reward.py` 和 MuJoCo 广义坐标插值复核。现场直推首次超时，Windows 中转仅本轮 Git 对象，普通 `git push origin <sha>:refs/heads/main` 成功，GitHub API 和训练现场第二次正常 fetch 均回读已发布的 ea9b09d。

`scripts/b0/dynamics_c20_pair.py register --dt-ms 0.25 --recipe config/b0/standard_dynamics_v1.yaml --identity warp_250us_servo2ms_continuous_v1` 后，两臂按 0→50→200→1000 从统一的 1000×256 真实索引训练。每段用 `dynamics_c20_stability.py` 检查完整参数梯度分布和固定原单位探针，用 `dynamics_c20_score.py score` 计算三个开发源指标；最终重复评分。旧统计与重标新预热各 1000，累计 2,969,600 次监督后继，无新增 T2。19:16:36 执行 `dynamics_c20_score.py lock`；重标 +1000 六项全部更低且重复差为零，锁定它为唯一实验 WM，+0 为控制。旧 selected_wm 保持 null。原 2ms 共同 u0 已重新评分 10 案，0/10、6 个首步超力、0 阶段事件。68 个初始 Actor 参数／缓冲区已逐项匹配。此时两臂均未更新。

**19:17–19:22 原图、联合训练及原正式评测。** 两包执行锁在 `pilot_execution_lock.json`。首次只读前向检查在开启梯度的 representation 正算处因逐位比较中断（两臂，最大差 1.31e−6，零参数更新，保留 preflight_*_01.log）。使用原接口数值，独立从同输入求物理状态的链式 VJP，完整复测两臂通过。执行 `python -m scripts.b0.dynamics_h32_pilot preflight {control,experiment}`、`verify`、`train {control,experiment}`。真实更新第一批 256 行的 49 组抽样索引、物理状态、历史、首次命令逐值匹配；标准 u1 自身在 10 个 WM 后和 20 个 Critic 前的原目标另存。两臂均至 u10，实际 20 H32/200 联合 WM/400 Critic，共享首采去重 23,921 有效转移，恢复各 pending=2。五组独立原正式 Warp 十项合计 50 个新 nominal，0 通过、0 阶段事件。单次共享 u0、两支 u1/u10，各 6 案首 2ms 超力，其余原正式逐案也保存。独立开发长窗、同状态响应和固定首批原单位复算分别落盘。A、B 的普通推送均成功；已从 GitHub 回读 aee8ce4 的选臂收据版本。正在现场核验背推抓取开发窗口对后续动作来源的依赖，再决定是否延长。

**19:22–19:30 延长复核和收尾。** 单首动作试验中，背推 grasp 的 u10 首命令接 31 个共同参考命令后可出现 426/428 ms 双指接触。执行 `python -m scripts.b0.dynamics_h32_score same {formal_2ms,training}` 和其 `--retest`，共 240 条开发诊断；再执行 `python -m scripts.b0.dynamics_closedloop_entries {formal_2ms,training} --repeat {0,1}`，两侧 grasp/release 四起点、共同 u0 和两支 u10、两种物理身份、独立反序重复，共 48 案。每 20 ms 用同一冻结 Actor 和实测后继重出命令。首命令全部与前项一致，停止前均无双指同时接触或阶段事件；两遍首次裁判时刻相同，峰力最大差原 2 ms/训练细步为 0.0252/0.0013 N。602 次 Actor 查询，34,254 个被裁判微步，退出后的 906 步单列。实验 u10 的正式前拉接近与释放延后，但背推接近较共同 u0 从 1.154 s 退到 0.036 s、139.91 N 异常接触；控制前拉接近/释放退到 0.080/0.084 s。按第5.3节结束两臂，单链延长、D、完整双侧 Warp/C/native、独立 seed1/2 和 H 均未开启。历史 response u200 的 60 案未计入，旧 selected_wm 与最终候选均为 null，完整回报 NA。

实测 `python -m scripts.b0.index_dynamics_actor_state` 回查全部实际 H32 起点；共 321 个 open/hold 抽样实例均来自首 20 ms 即终止的真实区间，初态处于失效前。观察到归一化坐标漂移后，`python -m scripts.b0.check_dynamics_actor_normalization {control,experiment}` 分臂重建真实 10,958/10,877 个新增归一化样本，核对全部 10 次实际抽样及最终 RNG。按官方更新复算，sensor 分量逐位一致、goal 最大残差 9.32e−10，计数完全相符。只读专项无额外训练。两份约 249 MB 的 cohort_state.pt 已用 torch.load 从磁盘实读，每份的配置、6 个优化器、4 个 replay 块、ReturnSampler/RNG 和评分包三套同名权重均核对，pending=2 各自保留。当前先验的归一化统计与真实接触分布有明显差异，尚无丢失 count、单位/维度错误或错误恢复的证据。

集中轮实际收据以 `results/b0/standard_dynamics_20261124/baseline_manifest.json` 为入口。已运行 `python -m scripts.b0.index_dynamics_h32`、`python scripts/b0/index_dynamics_round.py --decision results/b0/standard_dynamics_20261124/round_decision.json`，复核 50 份独立原正式 case/return、20/200/400 的实际优化器计数和共同首批/重复采集去重。大权重、求解器数组和恢复包留现场 `results/raw_large/b0/dynamics_20261124/`。本轮最终提交由 Git 历史标识，普通推送及 GitHub 主要文件回读结果在本次交付中记录。

**19:33 发布回执。** 完整实验和恢复清单提交 `c14d6ad6bf926106a3f9f6ded153f03f2b061e1e`，已普通推至 GitHub main。随后用已认证的 `gh api` 实读 main 前后指针及固定提交的 11 个主要文件，逐一重算 Git blob 身份；[实读记录](results/b0/standard_dynamics_20261124/publication_readback.json) 指向该实验版本。训练现场直连 fetch 偶发超时，临时使用仅绑定 loopback 的 SSH 反向端口转发到 Windows 已有 GitHub 代理，再正常 `git fetch --no-tags origin main`；现场 HEAD 与 origin/main 均回读为上述完整 SHA，原有环境链接和历史目录均保留。本条目是该实验版本的发布回执。


## 2026-11-24 北京时间 19:35 起｜870796a只读审查与联合接触集中计划

### 授权、范围与读取边界

延续用户“审查结束轮→下一计划/启动词→目标差距→普通GitHub发布”要求。用户坚持先标准SuperMimic迁移成功，再开发算法，并要求一次性多推进。本地从781cd1d正常fetch、fast-forward到870796a52aaab5cef307d5c2d455377094e5d056，起始工作树无已跟踪修改；GitHub main回读一致。该实验提交为北京时间19:33:56；19:35是本次审查起点，不冒充实验起止。

只审查代码/配置/报告/索引/逐案CSV与JSON，重新做算术和交叉文件核对。没有新增仿真、训练、模型推理或硬件操作，没有现场重载AutoDL大权重/原始物理数组。并行三工作面：正式证据/预算、WM源码/联合边界、物理时钟/动作/伺服。核读固定官方abc124c的原WM/policy learner，不启动关闭的G1支线。机器摘要明确locally_recomputed与source_recorded。

### 证据与预算复算

50行正式成绩逐条与result/return交叉核对：50案、0通过、0事件、30案首2ms>6N，9322评分微步＋5000前缀微步，分母/失败吸收/奖励分项闭合无差异。本轮新共用u0、两支u1/u10各十项；历史response60案另记。48闭环来自4个开发起点×3策略×两步长×两遍，均停止前无双指/无事件，重复首次失败时刻差零；不是48个独立泛化起点。原2ms/细步分别194/408次Actor查询、1858/32396评分微步。首动作后接参考得到426/428ms双指，不能支持纯Actor延长。

实际新增离线2000WM、20H32/200联合WM/400Critic；共享2086有效/5120总区间只扣一次，去重23921有效、35840总、11919前缀、2867200训练微步。两支pending=2不计更新。49组首批索引本地逐数组一致；256行原始状态/权重恢复/FP64统计回放只读现场回执，不冒称重新执行。native+三Warp源1334 episodes/branches、50479H1/43755H7，窗口和分支不等于独立轨迹。

两支各15360实际在线H7都open/hold=0、two_finger=0；背推800/818（5.21/5.33%）。在线H1却有247/245个open/hold。Actor的161/160个open/hold抽样初态在失效之前，后继首20ms终止；不能当失败后污染删除。离线数据贯通已完成，当前缺可持续在线接触序列。

### 已更正的一处文案与上一计划缺项

原实验报告把u0→u10在线H7损失写成“首个真实联合更新”。CSV节点正确；按samples加权：控制u0/u1/u10=4.964847/2.547750/1.242317，实验=2.466599/1.481665/.847665。报告明确注明审查更正，原CSV/manifest/旧commit不改。正式0/50、预算和停止决定保持。

上一计划4.1的WM参数源梯度内积/夹角未交付；已有脚本只求x/a VJP，不能替代。首H7 online标量加权loss占比99.758/99.910%不等于梯度贡献。本次报告与JSON记录该缺项；下一计划前瞻用真实8H7+2H1全部样本做参数源梯度，不追认上轮“每时域十批”原样完成。

### 新收窄的两个机制

最明确异常发生在第一个联合WM块。实验grip TCP P95：H1从1.04/1.15到5.45/6.29mm，H7从2.73/2.29到137.60/121.74，H32从17.85/14.69到888.95/734.46。四离线源J2绝对末误差约.20rad，关节FK贡献远大于基座。u0→u1 Actor统计未变，不能用后期归一化漂移解释最早WM退化。

代码确认离线2H1→8H7、联合8H7→2H1；联合75%online与离线比例不同；共同H32初始明确使用空优化器。三项为已知边界差异，尚未证某一项单独因果，原动量清空不是已证漏载bug。未发现明确C20系数错用、模型严格载入/优化器分组/Actor直接改WM的错误。下一轮实际逐批保存，不能只看10批末分数。

物理同状态命令已变，门力几乎不动：实验u10前拉J2约.91752rad/jaw50.98mm、背推1.10250rad/62.06mm，首力仍约51.3/33.0N。历史hold/u0 J2连续10/10微步饱和35Nm，±.01rad仍饱和；J2采集σ=.0025rad、jaw全宽σ=.333333mm，gain32未放大gain前保存的exploration_scale。支持检查实际力饱和，但最新节点距脱饱和多少σ仍需现场raw。原正式hold前缀总力约5.69/5.93N且双指，首Actor求解才超力；solve起点时间戳不代表用了前缀旧力。历史部分参考臂+jaw有20ms双指且≤6N见证，不能宣称任务整体不可达。

0.25ms训练身份继承，servo2ms/c=.50625保持；细化至.125ms仍有约31N时刻力差和2.67mm个别末开度差，不宣称瞬时完全收敛，也不重复整个步长研究。新物理边界采样保留原2ms/细步两身份。

### 下一轮集中交付、预算和执行修订

新增docs/B0_JOINT_CONTACT_PLAN_20261124.md、reports/B0_DYNAMICS_ROUND_REVIEW_20261124.md、results/b0/dynamics_review_20261124/audit_summary.json。并行两工作面：原两支各10批WM精确复演＋一个10批顺序对照，共30诊断批；读取原240条首动作raw，按solve前状态/真实ctrl/外部bias核对未裁与裁后力，缺边界覆盖才补4个hold×7点×两步长×两遍=112条20ms短轨迹，必要train_open先登记后扩168。解析边界只用于一次性WM辨识，训练/开发分开；仅.25ms训练起点入response H1，2ms只诊断，独立分支不拼H7，真实前缀另计。

单主配方默认重标+1000、标准B003 Actor，以原联合源/原loss预适配。首段≤500，证据支持累计≤1000；最多一次有据调整，调整前后和资格预演全计入。每次放行检查连续两个真实联合10批块，最迟480/980批开始，从第二块实际末点及连续WM优化器/RNG进入H32。固定四项E0、固定开发窗，保留线max(1.25E0,E0+2mm)，同时独立真实online H1/H7与高误差J2有可复算改善。25%只是前瞻工程开发容差，不是论文阈值、统计非劣或物理通过；早节点通过即推进，不耗满1000，不用坏WM再做一轮失败u10。

新单条seed0首段目标u50=50H32/500联合WM/1000Critic；u0/u1/u10/u50检查，物理停滞规则最早用于u10→u50，u50前仅完整性/数值/明确WM失稳暂停。真实每20ms由后继重新动作，交付首20ms存续→第二次查询→持续双指/实际H7→登记事件，不用参考尾段。物理有收益自动继续100/200及必要后续；原十项过后同轮D、连续Warp/C/native、独立seed、三seed冻结H。算法、VLA与新硬件任务后置。预算内最终无出口如实报告，不为多推进虚构通过。

复审明确了8个具体执行点：80细步包含第一拍；细步/2ms数据身份分开；20ms独立分支仅H1；正负饱和边界用力绝对值与正确内外方向；500/1000预算内预留20批；一次修正包含总预算；u1/u10不触发提前物理停滞结束；参数源梯度的真实十批与旧每时域十批区别写清。

### 文档同步与发布口径

更新AGENTS/README入口、PROJECT_STATE顶部、独立结果顶部、总路线/B0总计划/协议执行口径、GOAL_GAP及B0_START/NEXT_RUN。旧计划正文仅加当前导航，保留原预登记；最新实验报告只更正u1/u10时点与导航。原manifest/CSV、学习代码/配置不改。目标差距明确最早十项仍0/10，实验u10门力超出6N为45.039/27.179N；无完整回报不写分数差/完成率/时间承诺；历史canonical u350 release事件保留。

只读过程少数路径查询不存在，已按实际文件路径重读；大段输出截断后改短段读取/机器汇总；一次工具脚本正则写法解析失败，整块未执行，随后修正并执行。均未影响实验文件。发布采用普通单父提交、expected_sha和force=false，保留其他树。完整交付和链接/数值检查在发布前完成；提交自身SHA和远端回读结果在聊天交付，不自引用反复提交。

发布前检查：16个明确交付文件、431个相对Markdown链接全部存在，审查JSON严格解析通过，50案交叉复算无差异，git diff --check通过。原训练代码/配置与实验manifest/CSV均未修改。末次修订明确新冻结u0采集同时冻结Actor参数与统计，使用h32_shared标准u0完整共同包；旧replay保留实际生成身份，不重新贴标签。发布后本地与远端SHA及关键文件内容另行回读，结果在聊天交付。

## 2026-11-24 北京时间 20:10–20:15 联合接触轮开工与实测

经 dev2-ubuntu-lan 执行 git fetch origin main，取回 528a9d7ac1ddbf399a125a93b9ee21bc1af6fd9b，通过 merge-base 祖先检查。原主树有 PROJECT_STATE 和三项 H0 已改文件及 P5 未跟踪目录；新建 ../dog-and-arm-b0-joint 独立树。D57 的 dog-and-arm-b0-temporal-v1 实验源码为 870796a，与审查之间仅文档和审查结果有改动。原两支 pending=2 保留。新小结果与大数组分别在 standard_joint_contact_20261124 和 joint_contact_20261124。

并行实施首十批重放与原 240 条首动作数组核算。两支 WM/优化器十批末逐张量与原快照完全一致，首一个 H7 已越线，调换顺序十批末仍明显退化。现有 hold 首拍 J2 饱和；边界识别按原设计进行。运行 bash scripts/b0/env.sh python -u -m scripts.b0.joint_collection train 和 development，各 128 lane ×40 tick。新开发采集的实际物理初态来自六份 validation 轨迹，按相同 phase 对应到原参考时钟；保留原物理参考前缀、policy 参考与噪声，训练在共同 u0 的实际连续 lane 上采一块。两块参数和全部统计均逐项对照共同包。现场缺 rg 使用 grep；早先 PowerShell 传输字符串类型错误发生在远端命令前，改 UTF-8 传输。

### 20:14–20:21 精确复演、物理辨识、u0 与联合适配登记

AutoDL 命令以 bash scripts/b0/env.sh 为前缀。python -u -m scripts.b0.joint_replay control / experiment / experiment_h1_first 三个独立进程各跑十批；三次 --signed-only 只读补齐有符号误差。两条原顺序模型与优化器逐张量重放差为零。重标支首 H7 后四长窗 50.867/68.473/51.975/68.975 mm；单独调换顺序仍有 628–759 mm 末误差。真实十批全裁剪，P95=11.07366986。起点 online 与 native/grip/multimode/response 的同参数梯度余弦分别 −.098/−.124/−.217/−.138，随后会变号。详见 replay/summary.json。

依次运行 joint_physics_audit.py、joint_physics_boundary.py register 及两种身份各 --repeat 0/1、joint_physics_derivatives.py。原240行七个执行器复算与真实裁后力最大差 4.53e-5。新增112条20ms分支合计5040物理微步，复用已积分前缀。仅细步训练起点第一遍的14条完整首terminal入response/H1。28-lane与7-lane的派生速度出现5.82e-11舍入差，核对原q/v相同后对派生量用2e-7容差复测。joint_physics_closedloop.py 两身份各两遍，六起点共24次，每次实走200ms前缀。原2ms、细步各8/12达到第二动作，各0/12持续双指、0事件。用原裁判终止时刻生成左右两部视频；另经 python -m scripts.b0.joint_formal 0 新跑原十项，0/10、六项首个2ms超力。

每个新冻结采集块各5120物理策略区间，训练新增3429 H1 /3096 H7，其中156个完整首terminal；独立开发1816 H1 /1149 H7，176个完整首terminal。验证逐个合法起点评分。运行 python -m scripts.b0.joint_adapt register，将原联合比例、原损失/裁剪和双优化器、实际重标+1000四项E0、固定开发分母及每连续两块更新末点的资格检查写入 registration.json。为分别覆盖共同/新增实采，在相邻十批间交替使用两个实采块。资格训练与原Ratio分开记账。启动 train 0 200 时发现导入torch的顺序先于固定环境开关，触发了Inductor，第一次反向编译中断，日志0行、未到优化器step。把TORCH_COMPILE_DISABLE提前到torch导入前，从原零点复测；保留中断日志和新的eager运行记录。

20:21 首次 eager 运行在第一个 WM 更新后的记账遇到重复键 h；优化器已走一步，训练状态未写出。修复记录器并单列 discarded_optimizer_steps=1，合计上限内最多保留490/990批整块末点。未消费 u10 包。正常发布先记录可复算诊断与新采数据身份，后续追加真实跨界成绩。

### 20:22–20:31 单链完成、五个节点复测与恢复

在 D57 的 /root/autodl-tmp/dog-and-arm-b0-temporal-v1，依次运行 bash scripts/b0/env.sh python -u -m scripts.b0.joint_adapt train 0 200、train 200 490 和 train 490 990 --adjust 0.00005。各段真实结束北京时间分别为 20:22:58、20:24:18、20:26:26，退出码均为 0。小结果 standard_joint_contact_20261124，实际大状态在 results/raw_large/b0/joint_contact_20261124，各保留十批末点的 dyn/双优化器/RNG 和有序抽样索引均存在。两条旧 u10 没有新增更新。

每十批均复评完整四项窗口及独立在线全部合法 H1/H7，包括首次失败的完整首区间。+50（本段实际留存批数）四长窗126.61/134.24/125.26/134.77 mm，+200为66.88/75.25/79.94/80.53；+490为21.73/22.09/46.45/21.46。预适配前10块与首段后9块的四个长窗中位数均下降，独立H7的J2 q/v中位数从0.0767rad/1.1599rad/s降至0.0258rad/0.3161rad/s；同时末九块各项极差69–92mm。首段已计491批，有继续验证的实测依据。先记录extension.json 与 adjustment.json，再唯一一次把两个WM优化器学习率从2e-4降至5e-5。保持同一个+490权重、两组动量、RNG和样本顺序、固定统计、loss及数据源。没有回滚或更换采样配方。

最终99个真实块中，99块独立在线六指标优于E0；只有+850四项长窗同时合格。+840/850/860 前拉multimode 37.60/21.89/37.96mm，+860另外两项背推也越线。+990终点四项31.94/52.16/49.48/58.55mm；末点H1/H7原损失0.7491/0.2306，H7 J2 q/v RMSE 0.01490rad/0.19887rad/s。两块连续资格0/98，991批已计费、余额9不足新十批。已部署的条件执行器因无qualified.json退出，新主链H32=0、联合WM=0、Critic=0。u1/u10/u50、D、完整Warp/C/native和独立seed/H未启动；无完整回报。

实际运行 joint_coverage、joint_endpoint 850 / 990、joint_index、joint_verify 和 joint_relapse。共990个保存步裁剪605，P95=6.6938，最大24.5499，无两块梯度报警。边界H1 175次实抽，online H1 38016次中3173个open/hold，online H7 152064次中open/hold=0，两时域two_finger均0。38/66的原差分方向在+850和+990均为47/66，其中两个训练起点26/36，两个验证起点21/30；物理短轨迹只算原112条。独立进程重新载入+840/850/860/980/990，逐项长窗和独立online分数绝对差为0；+990恢复包有限、Adam/Muon状态条目12/2，Adam步数990，CPU/CUDA/NumPy RNG实际装载。最后再以固定完整双指窗分解+850→860的TCP基座/关节分量，未新增优化或物理轨迹。观察支持长窗在相邻更新间失去保留；多源梯度、两实采块样本组成、长期动力学和接触饱和尚无单一充分因果解释。

普通推送中间提交816f1aa至GitHub main，正常fetch与回读确认replay/summary.json、registration.json和SHA。第二开发平台HTTPS读权限可用，写入未配置凭据；从独立工作树通过git pack-objects直接传输这次提交的新Git对象，在Windows利用已认证gh的Git凭据执行普通push，无强推。独立报告 reports/B0_JOINT_CONTACT_RESULTS_20261124.md，机器清单 baseline_manifest.json、逐案原result/return、前拉/背推纯Actor视频均在本轮小结果目录。末次提交与线上关键文件回读在聊天交付。原开发主树未经checkout/reset/stash，原四个修改和P5未跟踪目录均在。


## 2026-11-24 北京时间 20:36起｜65c121b审查、官方流程纠偏与视频交付登记

### 授权、读取范围和实际操作

延续用户授权的“审查完成轮→下一步计划/启动词→目标差距→普通GitHub发布”。用户增加完整任务仿真视频和参数比例比较，随后明确加快速度不能改变完整按SuperMimic迁移的根本目标。当前回合只读取仓库、固定官方源码与已提交实验结果，修改文档和审查索引；没有新增仿真、训练、模型推理、AutoDL大权重重载或硬件操作。没有声称读取了远端所有原始字节或不可访问的其他对话。

开始正常fetch并fast-forward到65c121b0d7a2519b9c503589024f075e7b7889ba，GitHub main回读相同，源实验提交时刻20:32:33。并行核查实验证据、WM代码/采样边界、物理/视频；主任务核读固定abc124c官方runner、WM learner与policy learner，后续补官方训练入口、模型及配置/播放路径。没有修改65c原manifest、评分CSV、实验报告正文、权重或训练代码。

### 本轮证据复算

99个保存的真实十批节点只有+850满足原四项保留线，98对相邻节点无连续双通过；30诊断批＋991预适配批，后者990保存＋1实际未保存优化步，新增主链H32/WM/Critic均为0。+490后两个WM优化器LR从2e-4降到5e-5。原2ms正式10案0通过/0事件，6案首2ms超6N；1628评分微步、1000前缀。24个开发组合两种身份各8/12有第二动作，各0/12双指、0事件。现场独立重载的零差异只引述回执，不冒称本次再次运行。

独立online E0→+990：H1 loss 2.938697→.749094（下降74.51%），H7 loss 2.415448→.230621（90.45%），H7 J2 q RMSE .499190→.014900rad（97.02%），v 3.322904→.198868rad/s（94.02%）。这些是预测指标改善，不是任务完成率。正式stable_grip首力51.068990/33.150242N，分别约6N的8.5115/5.5250倍。候选null、完整双侧回报NA保持，不能计算距.90/.88的分差。

预适配代码每十批只用一个online cohort再整块切换，未执行主链则合并两块按lane-age抽样；这是确切数据分布差异，尚非波动单因证明。原边界112条中细步第一遍28分支全在首微步失败，单改J2/jaw不是足够修复。B0-03教师J2命令约.8–.974533rad，与当前接触状态跨度明显；这是教师命令范围，不等于已读全部实际q范围，也不能据此宣布唯一故障。FreeRun并无已证351帧硬截断，真实长度由MotionBank处理，旧三参考名称和采样bin假设单列为输入核验事项。

两部现有视频pull7.76s/push5.08s，每部组合grasp/hold/release三个独立失败入口并带停帧，是诊断视频，不是完整成功。检查使用视频元数据和生成代码，没有冒称逐帧视觉审查。

### 用户质疑后的明确纠正与官方事实

本回合早期未发布草稿曾拟采用+850继续原混合H32并另开B姿态覆盖预训练，同时保留50mm暂停线。用户强调不能自编流程后，这些尚未执行、尚未发布的安排已撤销；不在GitHub提交最终计划时继续保留为默认。草稿本身没有发生训练。根本目标明确为标准迁移成功与论文参照，完整视频仅新增交付。

直接核对固定官方abc124c：真实采集后flush WM状态/processed-action与Actor归一化；Ratio调度十个horizon8窗口（七个监督后继）；紧接H32 Actor一次、Critic五轮四分块共二十次。没有25%双块或50mm开发误差拦Actor。现有H1/H7混合、teacher配额、冻结WM统计、gain32、5e-5及额外预适配属于项目选择，不能因为import官方类就称完整原样复现。新文件B0_OFFICIAL_FLOW_ALIGNMENT_20261124.md逐项列固定源码、保留核心、必要机器人映射和额外配方处置。

官方可选wandb_run_path只先载WM bundle，再构造learner和Actor/Critic；固定训练入口没有完整Actor/optimizer/replay/Ratio/RNG恢复功能。现有完整恢复包是项目运行保障。+850.pt包含dyn/normalizers、optimizers、RNG、批数/dt/c，但无独立sim_context；新官方WM-only warm-start必须从任务/环境补齐context并核对状态和动作坐标，不能声称现成兼容bundle。官方decoder末端不是基础effort±1截断，撤掉gain32时必须防止把J2目标错误限为home±.025rad。

### 已写定的下一轮和新增交付

新独立official_flow_s0_v1以+850的WM-only初始化，按官方新建seed0 Actor/Critic、全部优化器、online replay与调度状态；默认2e-4，十H7在线WM，逐采集更新统计。旧Actor/critic/优化器/RNG/5e-5/gain32/离线配额不隐式继承，+850全部既往成本披露，不称从零同benchmark复现。优先WM2048/policy4096及官方并行默认，确需资源降档先登记证据、实际值和Ratio映射。必要机器人时钟、单位、solver、lane与裁判身份保留，原6N与正式2msWarp/native3.3不降。

新接口必须实际实现并保存首更新调用和计数回执，随后首段u200=200H32/2000联合WM/4000Critic，u0/1/10/50/100/200留存，按真实Ratio推进。有限WM大误差不再是自加门，非有限/接口/恢复错误保存后修复继续。u200有真实物理收益可登记延长500/1000，无收益保留具体负结果。完整任务nominal可在冻结节点开发尝试；首次一侧真实完整成功即交原速连续视频，同轮继续另一侧与原验收。无教师接管、reset、参考尾段、直接摆qpos或拼接。

视频/比例协议要求原单位、分母和比例并列，WM误差/nominal error、适用相位门力/6N、伺服力/限幅、时间尺度及完整物理回报各自定义。0.90是论文SONIC参照、0.88是项目工程接近带，跨机器人任务不声称同benchmark等价。单个成功视频不代替双侧/D/C/native/独立seed/H。所有新训练与成功视频仍是计划，不提前填写结果。

### 修改、核验与发布口径

本次更新AGENTS、README、PROJECT_STATE、B0总计划/论文协议/路线/目标差距/独立结果顶部，新增官方流程矩阵、下一执行计划、视频协议、联合接触审查与机器复算；B0_START和NEXT_RUN同步，原联合计划加历史导航。旧正文和原资格失败不追改。本机一次apply_patch因同一文件delete/add重复被拒，未产生写入，改用明确UTF-8文件写入；一次查询了不存在的learning/b0/joint_main.py，随后按实际scripts/b0路径核读。没有因此改动实验。

发布前检查严格JSON、相对链接、两提示词一致、当前文档口径与git diff --check，确认只含约定文档/审查JSON。发布使用普通单父提交、expected_sha与force=false，不强推，不覆盖其他工作。当前文档自身commit和线上回读在聊天交付，避免自引用提交循环。本轮只读审查的训练与仿真成本均为零。

发布前实际检查完成：17个明确交付文件、424个相对Markdown链接全部存在，审查JSON严格解析通过，两份启动提示词逐字节一致，git diff --check通过；训练代码、配置和原实验数据未改。正式推送及固定提交回读结果在本次聊天交付。

## 2026-11-24 北京时间 21:16–21:30｜official_flow_s0_v1 实现、首更新和 u200

从 GitHub main 695f3d7 接续。第二开发平台原工作树有本地硬件改动，另建工作树；AutoDL 使用原 temporal-v1 的固定依赖、场景及数据，在 .official-flow-695f3d7 运行此版本代码。约 21:16 验证 4096 个物理环境可建，约 21:20 使用官方 WM 2048、Actor 4096 实际开始 seed0。入口为 bash scripts/b0/env.sh python -u -m scripts.b0.official_flow。载入 +850 的 dyn 及其统计，重建并从既有训练数据独立复核五个 context 分量。验证八条训练参考的命令与 23 路物理目标。保留实际前缀、每 lane 连续状态及冻结裁判。每拍插入当前策略物理转移、更新两组统计，按真实有效数运行 Ratio；只从当前 replay 抽取十批各七后继，接原 H32 Actor 和二十批 Critic。

首批在第 19 拍取得，之前两个额度因合法 H7 尚未就绪而跳过。实得 22,678 转移。WM 统计从 50,479 到 73,157，Actor 统计从 0 到 22,678。首批十个 WM 原损失/裁剪前梯度、一个 Actor 及二十个 Critic 的实测损失/梯度、每个抽样索引均写入 results/b0/standard_official_flow_20261124。重读 u1 保存包，20,480 个 H7 窗口中的实测后继及上一动作在相邻时刻相等，4,096 个 Actor 起点均来自该 replay。u1、u200 重载时逐数组比较 136 个求解器字段；两次 4096 路直接状态字段和命令完全匹配。初次核验把四元数旋转重算的世界角速度也要求逐位相同，最大差 5.96e-8 rad/s。改为分别核验存储量和浮点派生量，再次通过。

约 21:28 完成 u200，实际 2,062,412 有效转移、2,000 WM／200 H32／4,000 Critic。u0 原 Warp 完整双侧在驶近超时。u200 原生 3.3.0 同包双侧均通过驶近及停车，随后预抓取驻车漂移失败。21:30 据此登记新增至 u500，使用已保存在线 replay、优化器、RNG、ReturnSampler、Ratio 和求解器状态续训。旧各轮资格与结果继续保留。

### 2026-11-24 22:00 北京时间｜收束官方在线联训、旧物理双端和完整任务

21:30 从 u200 原包延长，首个增量步为 u201→WM 2010、Actor 201、Critic 4020。首实现及 u1/u200 回执普通推送 f109bbe，GitHub main 已回读核对。独立 official_flow_s0_v1 已从 +850 WM-only 完成 u1000，实做 1,000 次 H32、10,000 个 H7 WM 批及 20,000 个 Critic 批。u1000 原 2 ms Warp 接触 0/10，完整名义 Warp 0/2、native 3.3.0 0/2。当前 B0-04，最终候选 null，合格完整双侧归一化回报 NA。 u1000 用尽本轮登记预算。原 Warp 前拉在停车阶段超时，背推在停车阶段出现夹指与非抓取部位的把手接触；native 双侧均在预抓取阶段失去工位约束。两端原接触十项各 0/10，末节点六个闭环接触验证入口均无双指持续，完整任务仍无成功。

实际执行 python -m scripts.b0.official_flow --resume --stop 500，以及各节点的 official_flow_eval formal/full/wm、末节点 native 3.3 复测、official_flow_free 原 3×20、official_flow_servo 六个验证入口，及 official_flow_restore_check、official_flow_coverage。完整任务每 20 ms 重查 Actor，原 judge 保留失败时刻与阶段，详细行见 results/b0/standard_official_flow_20261124/physical_cases.csv。本轮正式片段 0/110，完整任务 0/24。u1000 原 Warp 前拉 approach_base，settle / timeout:settle，背推 approach_base，settle / unexpected_contact:finger_non_grasp_handle。新增 10,255,490 个有效转移、908,328,960 个物理微步。高 WM 长窗误差贯穿实际联训；未设置误差放行门。u500 配对跟踪改善后于 21:41 北京时间登记并执行 python -m scripts.b0.official_flow --resume --stop 1000。u750 仅保存回放覆盖统计所需字段，接续 u500/u1000 环形回放的重叠区间按绝对时钟去重。覆盖统计脚本初版使用 NumPy r_ 拼接字符串标签触发异常，改为 concatenate 后对保存的回放重算；训练未受影响。恢复包另经全字段回读，状态直接字段一致，世界角速度重算最大差 1.2e-07 rad/s。全部旧成绩、旧失败和旧权重保持原身份。

冻结节点的现场北京时间和对应恢复位置见 results/b0/standard_official_flow_20261124/milestones.json。独立报告 reports/B0_OFFICIAL_FLOW_RESULTS_20261124.md 和 manifest results/b0/standard_official_flow_20261124/baseline_manifest.json。下一轮继续标准迁移。先用末包原 Warp/native 同侧轨迹定位驻车分歧出现的第一拍，将真实底座位姿、航向、四轮目标和轮速与同一参考时刻配对；再沿已有首解记录核对 J2 / 夹口命令覆盖和实际饱和力。用同包、同起点复核具体的场景、时钟或伺服映射差异。确认可修接口后登记下一段预算，执行同一官方主环及原双侧物理复测。当前节点按独立负结果封存，保留原成功标准和 V0 交付条件。 本轮末次提交和 GitHub 文件回读在会话交付。

## 2026-11-24 北京时间 22:26起｜51a0133审查、同链续训计划与发布准备

### 任务、范围与读取

延续用户授权的完成轮审查、下一计划/启动提示词、目标差距和普通GitHub发布。用户根本目标仍是完整按照固定官方SuperMimic迁移，先冻结标准结果再开发算法；加快速度和新增完整任务视频不改变该目标。本次仅审查和文档/审查JSON发布，新增训练、仿真、模型推理、现场权重重载与硬件动作均为零。

开始工作树干净，从695f3d7正常fetch/fast-forward至51a0133802983b65602949000099e7d18fa8e835；GitHub main回读相同，原实验提交北京时间22:01:16。三路只读审查分别核对逐案/预算、物理/时钟/观测、官方代码/WM/恢复；主任务复核当前实现和固定官方runner、representations、task_spec及固定mjlab的G1资产。读取的事实来源是已提交结果与代码，AutoDL大数组/权重未再次运行或读取，不声称读取了其他不可访问对话及所有远端字节。

### 逐案、分母和预算复算

134个原result及return与CSV对账一致：接触110案（Warp80/native30）0通过、0接触事件、60案首2ms超6N；完整24案0成功，却有15个驶近、11个停车事件，最远2事件，尚未完成pregrasp。全轮最大末门角约0.0000417°。u1000两端接触首2ms超力从各6降到3，改变的前拉三案变为10ms Warp/16ms native握持几何失败，不能当成接触建立。

新Actor原free四节点各60，共0/240；240案全跑完7s且solver_first_failure为空，全部TCP精度失败，81案另失败根位置门。u1000三类TCP RMSE中位数77.17/72.31/82.04mm。该结果不是全部摔倒，也不能借用旧B003通过资格。完整回报依然用前拉75.736s/背推56.056s的原完整分母和失败吸收尾段；存活前缀接近1的局部分数不是任务完成度。

1000条连续更新计数逐行一致：新增1000H32/10000WM/20000Critic，10255490有效转移+1098622前缀=11354112物理区间、908328960微步。WM20480000窗/143360000后继，Actor131072000想象步。collection.jsonl1192行是抽样日志，实际2772采集tick；不能求稀疏行和当预算。99507条完整terminal保留，首批Actor1483/4096为terminal起点。WM祖先14850批单列。Ratio末pending0、previous_clock10250240，越过5250、还差4990到下一10240额度。

### 官方配置、已排除解释与物理限制

新链官方采集/统计/Ratio/10H7/H32/20Critic已真实运行，不能继续写成尚待接入。核实首次物理失败与数值区间有效性分开，完整80微步terminal未全部过滤；四轮实际range为±99999，不是[0,0]；基础effort decoder不先夹±1，动作目标物理边界映射正确。源码审查没有核实出新的goal/action/proc错列或可直接解释全部失败的单一接口bug。

直接固定源码核实默认rep_state/history1、可选proprio；本项目proprio/history10为O1配置选择。rep_state也只给Actor540目标，30列相对平移仍属WM/Critic的570；不能把添加570或含门75维当恢复官方默认。G1 .9软限位因子与本项目编译range罚项边界是需明示的资产映射差异，未证失败因果，本段不改。官方max_iterations百万计外层collect，不是1000Actor收敛上限。完整恢复为项目运行保障扩展，原WM-only warm-start身份/成本不抹去。

u200/u500双后端双侧full都完成驶近+停车且实际/参考均pregrasp后越界；u1000 Warp落在settle是事件落后，不能移动参考时钟。native前拉XY18.803mm小于20mm，按judge分支推断航向>2°；没有原heading数值，不能写伪精确角度。现存完整q/v/raw_action20ms，2ms事件无完整q/v/heading，下一轮只补有意义区间。float32/64初始非零差不等于接口错误。overflow出处仍未知；134轨迹有限、96Warp capacity0仅排除所存字段/容量问题，不能追认全程无害。

两条完整参考已贡献3621747有效记录，十三phase都有数据；open/hold17887=0.1744%是参考标签不是实际接触成功。J2实际命令上端u200/500/1000为1.00795/1.19302/1.52572rad，参考2.59618；同hold入口前拉.80839→1.00041→1.17914→1.49640，背推.81404→.89030→.96770→1.14450，背推脱饱和距194.91σ→62.73σ。当前仍饱和/无接触，但有实际渐进学习，不将这条主链写成完全停滞。

### 下一轮决定、未采用方案与最小运行改动

曾只读核查官方rep_state58/history1所需完整适配和冷WM可能性，未执行新实验/修改学习代码。主任务综合信息边界、现有正向动作进展及完整任务退步，决定不混入观测/初始化变化：完整恢复u1000，先累计u3000，有原物理收益再u5000。主段新增2000Actor/20000WM/40000Critic，含延长最高新增4000/40000/80000，预算节点不算官方学习阶段。原两种WM误差门不恢复；没有确认bug也可继续。

代码入口NODES仅至1000、OUT/RAW固定、counting fields仅u750留存；下一执行轮必须最小配套扩展节点、显式父恢复/独立结果和≤500物理tick留档，防1000tick环覆盖造成漏账。原子快照先一致再序列化，不异步读仍在修改的GPU张量。新增metadata放CLI/独立登记，恢复cfg逐项相等保持。首次恢复新更新应u1001/WM10010/Critic20020；历史0–1000结果保持封存。

并行有限诊断为：既存u1000双后端首分歧，必要最多四原full+两训练细步full，warning额外最多四案；u0/u1权重×两组完整WMnormalizer四格冻结前向，新增优化0。stats1是首19tick后的73157count，不是首collect；混配是含交互的条件敏感性，不是独立可加因果或可直接上线候选。为判断当前分布，u1000/3000/已执行5000各最多256lane×64tick独立开发块，RNG独立、不回灌训练、空长窗报NA；均非Actor准入门。

固定节点评原十项、Warp/native双侧full、新Actor原free、六个纯Actor接触入口；u3000/末点补native十项。延长优先新接触/新阶段/可重复纯Actor持续双指；只有tracking则在预登记同钟停车/预抓取窗双侧比较并查整段退化，不能只看命令/饱和前力/更长失败时间/更高诊断分。首次真实完整成功立即交连续视频，同轮继续另一侧及原D/C/native/seed/H。0.90/0.88和正式物理门槛保持。

### 文件与发布准备

新增官方u1000审查、同链连续计划、三路审查JSON和机器预算登记；更新AGENTS、README、PROJECT_STATE、总计划/路线/论文协议/数据约定/官方映射/目标差距/标准结果顶部，原首轮计划增加历史导航，两个启动词保持逐字节一致。没有修改训练代码、学习cfg、51a0133原report/manifest/逐案分数或大型恢复资产。工作过程中一次rg查询了错误文件名docs/SUPERMIMIC_OFFICIAL_FLOW_ALIGNMENT.md，按实际B0_OFFICIAL_FLOW_ALIGNMENT_20261124.md继续读取；未影响内容或实验。

发布前将验证JSON严格解析、计划与提示词预算一致、相对链接、源码/原结果未改及git diff --check。发布按expected parent和force=false普通更新main，固定提交逐文件回读内容；实际SHA和回读结果在聊天交付，避免将文件内自引用发布回执循环提交。本次只读审查的训练/仿真预算保持零。

22:50 已完成发布前检查：20个明确交付文件、464个相对Markdown链接全部存在，4份审查/登记JSON严格解析通过，两份启动词逐字节一致。根任务独立复核134案分组/事件及1000条连续优化计数，结果与审查一致；git diff --check通过。原学习代码、cfg和standard_official_flow_20261124原始结果/报告无改动。技术复核确认新增/累计预算、恢复状态、原子保存、环覆盖留档与统计四格解释相互一致，无需额外重复实验。

发布前物理入口复核补充两项执行约束：新OUT/RAW必须贯通eval/free/servo/coverage/恢复与索引，不能只改训练CLI后让评测回写旧轮；训练0.25ms完整诊断须映射80微步Actor、8微步servo、原参考起止步×8和实际秒/原训练bias行为，不能只改eval的model.dt（旧路径每动作10步/frame除10/每步servo会改变身份）。已同步计划、两份启动词和机器登记；没有实际修改或运行这些训练/仿真入口。
