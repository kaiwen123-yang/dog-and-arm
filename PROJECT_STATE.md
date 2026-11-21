# 项目状态

更新日期：2026-11-21（Asia/Shanghai）。

## B0-03 用户检查点


云端原 O1 tracking 奖励配合伺服尺度后，seed0 u200 在 Warp 完整 7 秒物理评测取得支撑 20/20、移动 11/20、停车 19/20。所有失败均为 TCP 超过 30 mm。三组的 TCP RMSE 范围为 16.7–26.1、22.4–41.4、20.0–34.6 mm。完整初态三组需分别至少 18/20。当前继续 B0-03。[逐案物理成绩](results/b0/free_s0_cloud_servo_u200_warp/physical/cases.csv)


本轮止于 B0-03，阶段结果推送后等待用户检查。seed0 的真实学习闭环已运行。replay/home 变体在第 1000 次 Actor 更新累计 136,000 条物理转移。独立 GPU 物理评测中，支撑伸收臂、移动变臂姿、停车各 0/20，60 条均在 0.100 s 出现持续失载。留出回合一步、七步、32 步 TCP 预测 RMSE 分别为 0.84、4.22、12.59 mm。原始工程教师与学习结果分别保存在报告中。[评测报告](reports/B0_EVALUATION.md) · [轮载几何误差](reports/B0_WHEEL_SUPPORT_GEOMETRY.md)

本机八世界伺服尺度试验在 u50 保存权重后停止，u50 的物理评测中断。B0 新训练转至独立 AutoDL 目录 `/root/autodl-tmp/dog-and-arm-b0`。本机与云端的项目 Conda 环境路径均为 `.conda/envs/arm-and-dog`。Conda 拒绝包含空格的名字。运行入口限制 Python、Warp、Torch 和 CUDA 缓存至本项目。云端 RTX PRO 6000 97,887 MiB，容器配额 25 核和 120 GiB。保留本机已有 venv、原始结果与检查点。

## 当前研究阶段：B0 环境迁移与无接触学习

2026-11-21 本机 `git pull --ff-only origin main` 快进至规划提交 `f6333ec`，保留未跟踪 P5 数据。现场 GPU 为 RTX 5080 Laptop 16 GiB，主机内存 30 GiB。固定双源和 O1 实际配置已核对。单门仍用 `rail_bridge_front60_v2` 与冻结 P6 控制 `86ade86`。

- 三类无接触参考各实跑 350 个 20 ms 转移，另有独立扰动验证回合。按名映射 12 腿＋4 轮＋6 臂＋1 夹爪，原生 3.3.0 重放四条，共 1,400 个策略步。最大 TCP RMSE 为 1.81e-13 m。
- 为补采整条 500 Hz 参考，冻结教师额外实跑前拉和背推 nominal 各一次。终态 60.052° 和 25.081°。门操作命令随子步变化，仅无接触恒定目标回合可直接用于本版动作 replay。
- 原始数组在 `results/raw_large/b0/native_teacher_20261121_r1/`，执行命令与字段见 [数据报告](reports/B0_DATA_READINESS.md)。[来源锁](config/b0/source_lock.json)、[索引](data/b0/reference_manifest.json)、[重放数值](data/b0/native_teacher_checks.json)。
- 独立环境 `bash scripts/b0/setup_env.sh`，O1 双 pin、129 个包，Torch 2.14.0/cu130、MuJoCo/Warp 3.16.0。四阶段 GPU/CPU 对照和固定 3.3.0 的三条教师轨迹见 [环境报告](reports/B0_ENV_ADAPTATION.md)。
- seed0 实际运行 `bash scripts/b0/env.sh python scripts/b0/train.py --run free_s0_integration_r1 --updates 2 --integration`。GPU 8 个场景累计 320 个策略转移（3,200 个 2 ms 物理步）、20 个 WM minibatch、2 次 H32 Actor 与 40 个 Critic minibatch，均从新初始化的网络起步。权重在 `results/b0/free_s0_integration_r1/checkpoint_000002.pt`。
- 独立加载同一权重，3 类各 0/20。第 2 次更新的留出 TCP 误差为 5.81 / 21.89 / 767.86 mm（1/7/32 步）。[学习记录](reports/B0_FREE_MOTION.md)。继续 B0-03；接触片段与完整学习任务待无接触通过。

### 后端接触验证及 seed0 第一次正式训练

训练后端额外完成两侧 C01 教师的原任务全程。前拉 36,863 步、60.04931°，背推 27,043 步、25.07761°，两侧退臂后和终点的 1,500 步保持独立通过。原生工程的 MuJoCo 3.3.0 也独立执行了更新 2 的冻结策略，三类 nominal 均在 0.100 s 触发持续失载。[两侧教师、保持和警告范围](reports/B0_DATA_READINESS.md) · [冷启动动作分块诊断](reports/B0_EVALUATION.md)

启动 `bash scripts/b0/env.sh python scripts/b0/train.py --run free_s0_formal_r1 --updates 1000`，每 2 ms 加入 GPU 轮载和异常接触审计。实际完成 160 次 Actor 更新，共采集 25,760 个当前策略转移。随后官方 replay 报错 `no valid sequences L=8 n=1000`。该次退出前最后一个已保存的此配置检查点是更新 0；更新 160 无可恢复权重。原始整数步计数和采样比例在 [失败记录](results/b0/free_s0_formal_r1/failure.json)。

已以独立 run 启动 **free_s0_boundary_r1**。每批分开从真实终止后继做一步监督，并保留长窗口教师和策略数据。输出层从模型 home 附近的小随机残差开始；冻结评测仍由网络独立输出全部 23 路命令。实际入口为 `bash scripts/b0/env.sh python scripts/b0/train.py --config config/b0/free_replay_home.yaml --run free_s0_boundary_r1 --updates 1000`。检查更新 0、50、200、1000 的真实物理结果。阶段结论依冻结评测。[变体定义](config/b0/free_replay_home.yaml)

## 历史规划节点：R0 → B0

2026-11-21 用户已明确要求读取当前仓库，将“先在本场景跑通官方 SuperMimic，再开展多模态融合”的详细规划推送到 GitHub，并提供 Codex 提示词。本次新增的是规划与续接入口；没有运行 B0 训练、P6 复跑、双门实验或实机动作。

- 下一步执行 [B0_START.txt](prompts/B0_START.txt)，先 R0 最小定义与 B0-01 环境/动作适配，再参考/replay、无接触学习、接触片段、完整单门和基线冻结。
- [总路线](docs/RESEARCH_ROADMAP.md) → [B0 详细计划](docs/B0_SUPERMIMIC_PLAN.md) → [数据与模型约定](docs/B0_DATA_MODEL_CONTRACT.md)。R0/B0 的实现、训练与学习策略验收均为待执行，不把文档完成记成算法完成。
- 继承 `rail_bridge_front60_v2` 与冻结控制 `86ade863de712dd6cd402714229b12b1bdae5b13`；本次读取的结果快照为 `dc961f35034ad3083a46eecd1c0ff5f21607eb0c`。P6 最新覆盖是下文的前拉/背推各 20/20，旧暂停记录保留为历史。
- SuperMimic 默认继承已验证 O1 双源 `abc124c1bd5976341034668af3d12c087f2f1f55`＋`dd51a9fcc98791a2f0b018b3c7f71a3eefd5ecdd`；用户复现仓库 `00e45d4` 已闭项，不重跑 G1。
- 最终目标保持为腕部 RGB-D＋语言＋本体历史的多模态/VLA、世界模型与可微动力学联合，并完成实机验证。双门作为后续扩展；当前不以双门完成为 B0 前置条件。

本次仅核对与规划相关的仓库源码、配置、报告和结果表并检查文档一致性；没有访问现场机器人、恢复 H 盘归档或重新执行既有实验。后续实际 B0 命令与结果须由执行轮次补充。

## 已完成的 P6 工程基线

冻结控制 `86ade86`、`rail_bridge_front60_v2` 安装的同版固定清单已在 Linux 桌面全部执行。前拉 20/20、背推 20/20 通过。本机已完成前移安装的可见重载、收臂外观、碰撞及腕相机核对。两侧终态门角分别为 59.963–60.224° 和 25.043–25.089°，开门段分别为 31.394–35.382 s 和 11.766–14.586 s。前拉与背推的 J5 最小余量（°）分别为 1.473（C20）与 20.042（C05、C19 并列）。总计 1,290,099 个 2 ms 物理步，六轴有符号余量越界步数 0。各案的极小值和发生时刻均与原始 500 Hz 记录一致。出现非预期接触的案例数为 0，有原生求解器警告的案例数为 0。

11 月 21 日执行 `git pull --ff-only origin main`，保留未跟踪 P5 结果。前拉中断组以 `bash scripts/project_env.sh python scripts/p6_cases.py 15 16 17 18 19 20 --stage mobile --output results/p6/rail_bridge_front60_v2_20261120T133724Z/mobile_C_resumed` 重新完整运行。背推以同一入口 `--stage push` 运行 C02–06、C07–11、C12–16、C17–20，输出至 push_A–D。定位 C20 左后轮碰左门柱后只改背侧航向至 95°，依次分格实跑 1/2/3/7/18/20、4/5/6/8/9/10、11–16、17/19，输出至 push95_A–D。暂停记录、调参失败及旧座成绩各自保留。通过 `scripts/p6_condition_report.py` 合并实际配置一致的清单；另用 `scripts/p6_approach_clearance.py` 复核背侧驶近门框净空。[逐案表](results/p6/rail_bridge_front60_v2_20261120T133724Z/conditions.csv) · [完整报告与命令](reports/P6_FREE_BASE_DOOR.md) · [本机装配检查](docs/MOUNT_RAIL_BRIDGE.md)

研究顺序已按用户最新决定调整为先 R0/B0；原双门几何继续保留，后续再扩展。当前物理任务证据覆盖单扇门，尚无整机学习策略或视觉语言闭环成绩。手眼、标定板及附件称重继续后置。

## 历史实施记录

以下保留各节点当时的命令、结果和安排。涉及“下一轮”“待执行”的旧表述已经被顶部当前阶段与后续完成记录替代，不作为自动执行入口。

**前移模型的云端准备记录。** 用户要求安装板靠近狗头，故将板、两支座和整台 Piper 沿 M1 机身 +X 前移一档孔距，版本为 `rail_bridge_front60_v2`。臂根由 [0.050, 0, 0.0945] m 改为 [0.110, 0, 0.0945] m，板心 X 由 0.010 改为 0.070 m，选孔由每排第 3/4/5 改为第 4/5/6（按 X 递增编号）；完整导轨基准与高度不变。

本轮在独立云端检查环境（Python 3.12.14 / MuJoCo 3.3.0）实际重建 URDF/MJCF、编译前拉/背推场景，三组 FK 与腕相机刚性检查通过。板下机身凸包净空下界 4.410643 mm，相同 home 姿态的整机质心前移 6.500053 mm，质量仍 43.537064 kg。保存 [前后静态对照](results/assembly/rail_bridge_front60_v2/forward_comparison.png)、[模型检查](results/assembly/rail_bridge_front60_v2/model_check.json) 和 [源网格净空](results/assembly/rail_bridge_front60_v2/source_mesh_clearance.json)。**本轮无 GUI、无 mj_step、无硬件操作；没有新增推拉通过结果。** 用户的 `/home/kaiwen/research/dog-and-arm` 未从本会话直接访问。

P6 现在从编译模型读取真实安装版本，每个物理步记录六臂关节限位最小余量；分组入口增加 `--stage mobile|push`，可分别执行前拉 60°与背推 25°的 C01–C20。下一轮先可见检查前移装配，再做名义前拉、名义背推及 C13，最后按同一安装/控制版本完成两侧条件清单。背推 20 条是新增待测覆盖；旧座 20/20 前拉与旧版名义背推不能算作新座结果。[完整本机提示](prompts/MOUNT_FORWARD_PUSH_PULL.txt)

**前一安装版本 rail_bridge_v1 的 P6 名义前拉通过。** `rail_bridge_v1_mobile_01` 在 Linux 桌面连续运行 82.474 s / 41,237 步，从 0.30 m 外驶近、停车、双指前拉、松爪、退臂及保持、收臂、倒车至终点停车。最终 60.048936°，操作漂移 0.949 mm，抓持偏移 2.670 mm，门对机器人合力峰值 2.840 N。机器人与门仅两指接触目标杆。两个 3 s 窗口通过，2,062 帧全程录像已解码。松爪附近的 25 Hz 日志中，J5 距下限仅 0.141°。新座目前仅有这条名义前拉。[视频](results/p6/rail_bridge_v1_mobile_01/motion.mp4) · [报告与逐阶段记录](reports/P6_FREE_BASE_DOOR.md)

实际命令为 `bash scripts/project_env.sh python scripts/p6_single_door.py mobile --live --video --hold-final --output results/p6/rail_bridge_v1_mobile_01`，完成后用 `scripts/plot_p6.py results/p6/rail_bridge_v1_mobile_01` 出图。该版本当时安排先复查 C13；现由上文 front60_v2 的完整推拉复测替代，C13 仍是重点。保留旧版 20 案例和背推汇总。H0 本轮无操作，手眼、标定板与称重继续后置。

**双导轨安装座 rail_bridge_v1 已完成模型替换与桌面检查。** 运行 `bash scripts/project_env.sh python scripts/build_assembly.py --stage combined` 与 `bash scripts/project_env.sh python scripts/check_assembly.py --report results/assembly/rail_bridge_v1/kinematics.json`，重建组合 URDF、MJCF 和安装板网格。固定近景重载旧座与新座并切换碰撞/整机视图。Piper 臂根降低 85.5 mm；名义板下外观净空 14.5 mm，板中心到机身碰撞凸包净空约 4.41 mm。三组 FK 通过，整机质量 43.5371 kg，附加载荷继续省略。[连接件说明与桌面截图](docs/MOUNT_RAIL_BRIDGE.md)

**旧方块安装座 P6 自由底盘前拉已在 Linux 桌面完成。** 20 个预先列明的条件全部完成驶近、停稳、双指拉门、松爪、退臂、保持、收臂、底盘倒车和终点稳定。最终门角 59.9698°–60.2421°，20 例最大抓持偏移 3.133 mm、操作漂移 2.912 mm、倾角 0.2433°。C13 开门段用时 54.898 s，55 s 时限的余量很小。完整条件与逐案限制见 [P6 报告](reports/P6_FREE_BASE_DOOR.md) 和 [最终清单](results/p6/conditions_final.csv)。

**旧座背推完成。** `bash scripts/project_env.sh python scripts/p6_single_door.py push --live --video --hold-final --output results/p6/push_02`。首次背推沿指深滑脱触发 5 mm 门槛；改为斜入竖杆后 54.200 s / 27,100 步完成 25.055163°、释放和底盘退离，仅两指接触背侧目标杆。[背推视频](results/p6/push_02/motion.mp4)。新座结构与名义基准另列。

- 本轮先 `git pull --ff-only origin main` 至 b04f604，保留原先未跟踪的 P5 结果。用 `bash scripts/project_env.sh python scripts/p6_single_door.py <阶段> --live --video --hold-final` 依次运行 support、small、pull、mobile，输出至 results/p6/ 下独立目录。自由根/有限 23 通道/被动门，物理 500 Hz，IK 100 Hz，日志和画面 25 Hz。H0 本轮无操作。
- A 在门前站位承重、伸臂、空走并停稳，门保持 0°；B 小角最终 14.957607°，正式驻停前拉 60.120818°。C 首个完整移动拉门 82.162 s / 41,081 步，最终 60.055003°；两个 3 s 停车窗口分别通过。[名义连续任务视频](results/p6/mobile_01/motion.mp4)。
- D 原清单 10/20 完成。默认接触锥的小角超时、到站超时/髋部饱和、C14 退爪碰板及部分终点停车超时均保留。采用椭圆锥、有限轮速与腿部辅助定向、世界 −X 退爪及驻停纠偏回差，最终四组实际重跑 `scripts/p6_cases.py`，参数依次为 1/2/6/14/18/20、3/4/5/7/19、8/9/10/11/12/13、15/16/17，目录 final_A–D。中间 recheck_A 父进程返回 143，保留到约 50 s 的短片和各进程完整落盘数据；final_A 重新运行通过。
- GitHub 自然节点包括 65a91a7（承重与伸臂）、dac8bf1（15°）、ed8b28c（60°）、6ed7373（连续移动拉门）、de6abd7（初版 20 案例）、e7a1ce7（驶近和退臂）、e815178（驻停切换）。

**P3 桌面装配检查已完成。P4 固定底盘从前侧拉门，单次名义 60° 试验实际达到 59.963319°。** 随后松爪退离，38 秒 / 19,000 步。门与机器人只有前把手和两夹指接触，接触力范数之和峰值 2.2433 N。严格 60° 阈值尚差 0.0367°。背侧实测已从 22.098° 提升至 25.076°，P5 已在自由整机上跑通承重、慢行、转向、停车和伸臂试验。

**P5 当前结果。** 自由根整机在平地承重、前进、按车头方向转弯、伸臂慢行并停车。左转 12° 的桌面试验最终为 12.170°；右转 −12° 的无窗口对照转向段变化为 −12.139°，完整运行最终约 −12.137°。两次各 40 s / 20,000 步。左转试验先直行 0.360 m，转后伸臂慢行 0.221 m，最终水平速度 0.063 mm/s。轮地水平切向滑动峰值 0.117 m/s，不是纯横向侧滑。当前证据覆盖名义平地，尚无门反力下的驻停验证。

实际运行 `bash scripts/project_env.sh python scripts/p5_free_base.py --config config/p5_heading.yaml --live --video --hold-final --output results/p5/heading_12`，用 `scripts/plot_p5.py results/p5/heading_12` 绘图。复跑省略 `--output` 自动保留新目录。视频完整解码 1,000 帧。最终桌面查看窗口可手动关闭，结果已落盘。 [P5 报告](reports/P5_FREE_BASE.md) · [40 秒视频](results/p5/heading_12/motion.mp4)。

P5 自由根实测 33 s / 16,500 步。直行 0.360 m，速率控制左转 10.40°（参考积分 28.42°），伸臂行驶 0.221 m 后停稳。这个基准位于提交 `e7e4556`，后续航向反馈结果见上。实际入口 `bash scripts/project_env.sh python scripts/p5_free_base.py --live --video`。 [P5 报告](reports/P5_FREE_BASE.md) · [视频与数据](results/p5/free_base_nominal/)。固定基座背推节点已提交 `e13a48f`。

背侧固定根 [1.88, 0, 0.54266] m、朝向 90°。35 s / 17,500 步，门角反馈补偿 3.015°，退爪后门停在 25.076°。两夹指及夹爪基座接触背把手。运行 `bash scripts/project_env.sh python scripts/p4_fixed_door.py --config config/p4_push.yaml --live --video`。[详细数据](results/p4/push_feedback/summary.json) · [报告](reports/P4_FIXED_BASE_CONTACT.md)。前侧提交 `29eab00`。

固定根移至 [0.65, 0.30, 0.54266] m 并转 45°，把手高度 0.85 m。松爪后退 0.10 m 并抬高 0.04 m。桌面运行命令为 `bash scripts/project_env.sh python scripts/p4_fixed_door.py --config config/p4_pull_60.yaml --live --video --hold-final --output results/p4/pull_60_trial01`。3,800 行时序与 950 帧视频已核对，按本次记录结束时仍为 59.963319°。 [桌面截图](results/p4/pull_60_trial01/desktop_final.png) · [曲线](results/p4/pull_60_trial01/contact_timeseries.png)

- 机械臂本体验机：**用户此前已完成**，本轮不启动 SDK 或实机。
- H0 相机＋机械臂联调：**此前回合实机完成**；[报告](reports/H0_HARDWARE_REPORT.md)、[会话清单](results/hardware/h0/20261116_2051/manifest.json)、[操作说明](docs/H0_RUNBOOK.md)。
- P1 官方资产、P2 单体生成、P3 名义联合模型：**准备环境已实现并编译／离线检查**；[装配报告](reports/assembly_report.md)。
- 本机 `.venv`：Python 3.10.12 / MuJoCo 3.3.0 已建立；M1/Piper/整机已实际桌面显示；关节/夹爪、检查相机和碰撞视图有桌面证据；Piper 的 F10 与 XML watch 重载完成。
- 手眼标定、标定板采购、相机/支架称重及惯量：**继续后置**。
- 当前按 [prompts/NEXT_RUN.txt](prompts/NEXT_RUN.txt) 推进 R0/B0；P6 已完成的记录按原版本保留，不重做 H0、不重复安装原环境或 P3 装配检查。

## P6 准备与基线复核：2026-11-20

- 复核源提交 `9c43f530360ce3398018b954f46eac11b96e0d73`。读取P4/P5代码、场景和已提交的JSON/CSV、视频关键帧；没有新增仿真、桌面操作或硬件动作。派生统计见 [P6_BASELINE_AUDIT.json](reports/P6_BASELINE_AUDIT.json)。
- 前拉60°样本比背推更适合作为首条P6基线：前拉机器人–门扇接触对仅夹指/把手；背推反馈样本含夹爪基座碰把手。前拉旧汇总缺少门框接触字段，不把缺项写成测得零。
- P5停车根高约0.531984m，比P4固定根低约10.68mm。P6须按实际根姿态求IK；轮速分配须由世界Y假设改成车体系相对几何。
- 现P4会固定根并重建物理状态、覆盖全部ctrl；P6须一个连续物理状态、明确腿轮臂爪通道、一个控制写入处，不能顺序调用现有P5/P4的run。
- 次序已明确：自由根操作站位与伸臂保持 → 小角度/约60°前拉 → 短距离接近与退离的完整任务 → 小范围条件变化及背推接触改善。工程门槛是待验证建议；没有将计划写成通过。
- 文档保留P4/P5历史记录并修正旧“下一步仍P4”和右转终值口径。当前新增的是下一步可执行计划，控制器和旧结果文件没有改变。

## P4 首个有效接触片段：2026-11-20

- P3 收尾节点 `4bbf1e5` 已普通推送；之后实际进入 P4，没有启动实机或 ROS。
- 新入口 `scripts/p4_fixed_door.py` 复用既有组合模型/门生成器，配置 `config/p4.yaml`；专用 `sim/scenes/p4_fixed_pull.xml` 固定 M1 根，保留腿/轮与全部几何。主模型仍是唯一自由根的 31/30/23/1，未被替换成固定底盘。
- 初始 60° 路径 IK 失败；20° 原退离路径也失败，修正松爪后的手部朝向后通过。首次真实步进被门板–机身碰撞挡在 16.829°，保留失败数据；后移根 0.12 m、将 P4 专用把手降至 0.85 m 后，实际到达 19.261095° 并松爪/退离。
- 实际桌面运行 `bash scripts/project_env.sh python scripts/p4_fixed_door.py --live --video --output results/p4/pull_20deg`，26 s / 13,000 步。门无执行器、无状态写入、无把手 weld，只有两指与把手接触；力矩未超限、无警告/非零自接触力。并非 60° 任务完成，也并非轮足站稳。
- 保存 `results/p4/pull_20deg/` 的 26 s/650 帧视频、2,600 行/100 Hz CSV、JSON、曲线与视频解码图；`trial_02_obstructed/` 为真实碰撞失败；`trial_03/` 保留实际桌面图与有效初试汇总。重复初试的完整视频/CSV 仍留 `results/tmp/p4_trial_03_full/`，不重复上传。未新建压缩归档。
- `plot_p4.py` 从真实 CSV 绘图；只在项目 .venv 增加 Matplotlib，未动系统 ROS/Conda/CUDA。视频完整解码、代码编译和 MJCF 维度复核通过。
- 详见 [P4 报告](reports/P4_FIXED_BASE_CONTACT.md)。剩余：名义 20° 与实际 19.261° 的偏差、60° 连续可达性及碰撞路径、另一侧推门、跨条件重复。此处为 19° 节点当时的未完成项，后续结果见顶部。
- 下一条复跑命令：`bash scripts/project_env.sh python scripts/p4_fixed_door.py --live --video`（默认新时间目录）。继续开发先读 P4 报告，不能把复跑近 20° 当成解决 60°。

## 本机可见检查收尾：2026-11-20

- 从 `078839e` 接续，工作区干净；正常 `pull --ff-only origin main` 已是最新。复用既有 Python 3.10.12 / MuJoCo 3.3.0 / X11 :1。
- `live_assembly.py` 显式调用 `mjv_defaultFreeCamera`，按已有 scene statistic 初始化自由视角；本次截图确认腕部和四轮完整入画。没有改安装参数。
- 终端 A `bash scripts/project_env.sh python scripts/live_assembly.py --watch --events results/assembly/live_20261120/combined_events.jsonl`；终端 B `build_assembly.py --stage combined`，实际发生 XML_changed → 编译 → 关闭旧窗口 → 新窗口恢复 home，桌面截图确认重载后画面。
- `bash scripts/project_env.sh python scripts/check_assembly.py`：三组独立 FK 继续通过；新增 3 个腕关节姿态 × 0/40/100 mm 夹爪开口共 9 个名义关系检查。开合引起的相机世界位姿变化为 0；相对 gripper_base 的位置/旋转最大差约 5.93e-17 m / 5.55e-16。
- 实际打开 `live_assembly.py --model sim/scenes/assembly_with_door.xml --watch --events results/assembly/live_20261120/door_events.jsonl`，F8 桌面显示被动门板和 U 形把手。使用既有同一 optical frame 和 synthetic_aligned_rgbd；不是实物标定。
- 证据：`results/assembly/live_20261120/` 的 default_view、reloaded_view、wrist_door PNG 及事件；量化数据在 `reports/assembly_kinematics.json`。本轮没有新的用户明确观看确认，不代填反馈。
- 以上仅 `mj_forward`，时间为 0；P4 实验将单独生成固定基座场景并使用有限执行器与 `mj_step`，不更改主模型自由基座。

## 本机可见调试：2026-11-16

工作区初始干净，`git pull --ff-only origin main` 从 `284c1f3` 快进至 `b545796`。实际桌面 X11 `DISPLAY=:1` 可连接。仅创建项目 `.venv`，没有修改 ROS/Conda/CUDA 或启动硬件。

- 已执行 `bash scripts/setup_env.sh`、`bash scripts/project_env.sh python scripts/fetch_sources.py`、`scripts/inspect_sources.py`。两处官方源仍为锁定提交，资产完整。
- 终端 B 执行 `bash scripts/project_env.sh python scripts/build_assembly.py --stage m1`；终端 A 实际打开 `bash scripts/project_env.sh python scripts/live_assembly.py --model sim/scenes/m1_preview.xml --watch --events results/assembly/live_local/m1_events.jsonl`。
- X11 桌面捕获确认 M1 四轮轮足可见；FAR hip +6°、knee −4°、wheel +6°，F11 恢复，F12 正常退出。截图、18 s 桌面录像及事件在 `results/assembly/live_local/`。尚未收到用户明确的观看反馈，不代填“用户确认”。
- 修复碰撞外观重叠：F9 显示碰撞凸包/盒体并隐藏视觉组 1/2；F6 切换现有概览/侧面/正面/腕部局部相机。实测处理 MuJoCo 原生 F6 的坐标轴副作用。均只改变显示，不改碰撞参数。
- M1 模型 `nq23/nv22/nu16`，38.82051 kg；生成 URDF 的极小尾数差来自本机数值库。全部仍是 `KINEMATIC_PREVIEW`，没有 `mj_step`。
- Piper：终端 B `build_assembly.py --stage piper`，终端 A `live_assembly.py --model sim/scenes/piper_preview.xml --watch --events results/assembly/live_local/piper_events.jsonl`。J1/J2 各 +4°、J3 −4°；Space 双指 100→0 mm，F6 腕部近景，F9 碰撞，F8 腕相机，F10 实际重开窗口并恢复 home。
- Piper 单体包含名义腕部附件和相机。空场景腕相机主要看见背景/远地面，属实际显示结果；尚未添加目标。用户明确回复“能看到，继续”，对应 Piper 腕部近景与夹爪开合，不扩大为全部阶段确认。
- Piper `nq8/nv8/nu7/neq1`、4.716554081 kg；保存截图、24 s 桌面录像与事件。M1 节点 `f8786a8`、Piper 节点 `728fc8a` 均已推送。首次 HTTPS push 发生 TLS 中断，重试发现未配置 HTTPS credential helper；复用已有 gh keyring 登录、按命令临时指定 helper 后成功，没有修改全局认证配置。
- 联合模型已执行 `build_assembly.py --stage combined`，桌面打开默认 `live_assembly.py --watch --events results/assembly/live_local/combined_events.jsonl`。已检查侧面/正面、腕部局部、100→0 mm 开合和碰撞专用视图，未修改 `config/assembly.yaml` 的名义安装参数。
- 本机 `bash scripts/project_env.sh python scripts/check_assembly.py` 通过三组 FK，最大位置差 3.044e-16 m、旋转矩阵差 9.806e-16；仍仅运动学一致性。
- 用户暂停后已 F12 关闭本轮 viewer，关闭本轮桌面终端；没有启动任何硬件、接触或轮足动力学。
- 未完成：联合带门场景的本机腕视角、开合时相机固定关系的单独量化、联合场景重建/重载收尾；初始自由视角上沿裁掉部分腕部，F6 侧面/正面/局部视角正常，默认取景待修正。Piper 在 combined 构建重写单体 XML 后已收到 XML_changed 并成功重载。
- 下次先完成上述可见检查，之后才进入固定基座单门接触，再进入自由基座轮足保持/慢行。当时已暂停；2026-11-20 已按用户要求恢复，当前进度见上。

## 基础联合模型回合：实际成果

实际在独立 Linux／Python 3.12.14／MuJoCo 3.3.0 环境执行官方源获取、清单、全模型构建、三姿态 FK、EGL 图像与视频导出。未接入用户的 ROS、CAN、相机或机械臂环境。

- `scripts/build_assembly.py --stage m1|piper|combined|all` 可重建；不修改 vendor。场景在临时 XML 编译成功后才替换，支持稳定的查看器重载。
- `description/m1_derived.urdf`、`piper_h.urdf`、`m1_piper.urdf`、`joint_map.yaml` 已生成。
- `sim/robots/m1_piper.xml` 和 `sim/scenes/{m1,piper,assembly}_preview.xml` 已生成；`assembly_with_door.xml` 提供被动单门的可视对照，没有门电机。
- 联合模型 `nq=31, nv=30, nu=23, neq=1`；唯一浮动基座，16 个 M1 关节＋6 轴臂＋双真实夹指。源模型质量之和 43.537064081 kg，不含附件和名义安装座额外载荷。
- 配置背部安装 xyz `[0.05,0,0.18] m`；源注释站姿的根高由穿地的 0.52 m 调为名义 0.54266 m。支架／相机固定在 `piper_gripper_base`，外参未测量。
- 三组独立 URDF/MJCF FK 对照通过；最大位置差约 3.044e-16 m、旋转矩阵元素差约 9.806e-16，两指 mimic 误差 0。这是数字模型间一致性，非标定精度。
- `results/assembly/` 有整机、侧面、正面、腕部局部、原始理想 RGB／米制深度及 8 秒／240 帧运动学视频；`with_door/` 有同一相机看到门和把手的对照。
- `scripts/live_assembly.py` 支持关节选择／微调、夹爪、腕相机、碰撞显示、home 与 XML 重载。同一加载函数已核对实际模型；**准备环境无 DISPLAY/WAYLAND，未执行桌面 viewer**。

基础联合模型准备回合当时仅 `mj_forward`；后来P4真实接触、P5自由基座承重和轮速控制分别记录在上方，不把后续结果归入该准备回合。Piper 外观采用官方 collision STL，未转换 DAE 精细外观；官方质量和惯量保留。M1 原生动力学数值未改变。原始大网格由固定源重建，`assets/converted/` 不提交。

官方有 MATRiX_Robot_MC 的 ZGWS/ZGWS_ARM 运行包，但当前未下载／接入，不能把 native 模型的 16 个 motor 当成已验证运控。P5使用本项目的名义轮腿控制，不表示已适配官方运控或验证实机部署。

## H0 回合实际环境、命令和文件

- 从 `7bb3c1b` 克隆本仓库。原工程 `/home/kaiwen/research/OSCBF-research` 对应 OSCBF-learn `2ea3f1f`；解释器 `envs/piper-sdk/bin/python` 中实际是 pyAgxArm 1.0.0 / python-can 4.6.1，SDK 源提交 `d90e234b`，PIPER_H/V189 配置。未重装机械臂环境或升级固件。
- 实际 `can0` 初始 DOWN；确认 USB-CAN `1d50:606f`、序列号 `004F00374548570120353731` 后，用户执行 `sudo bash scripts/h0_host_prepare.sh` 补齐缺失相机依赖、USB 权限并启用 1 Mbps CAN。准备脚本及接收器不发电机指令。
- 相机为 DC1，RGB `2bc5:0557`、深度 `2bc5:0657`，序列号 `CC16762023M`，USB 480 Mbps。`bash scripts/h0_build_camera.sh` 构建 Astra `f7e71d9c`；首次缺 `nlohmann/json.hpp` 的失败和解包头文件后的成功均保留。驱动源/编译产物在忽略目录 `hardware/camera_ws/`，未修改上游。
- 相机入口 `bash scripts/h0_camera.sh`；最终相机/接收器经 `scripts/h0_ros_env.sh` 使用 domain 88、localhost、Fast DDS 64 MiB SHM。ROS 与机械臂解释器分开，未使用仿真 `.venv`。
- `h0_record_camera.py` 保存 RGB/原始深度/CameraInfo/视频/时间；`h0_record_arm.py` 只接收 SDK/CAN 状态。两者独立进程；`h0_operator_motion.py` 是现场唯一运动入口，复用原 `PiperDevice`，记录实际 MOVE_J/夹爪发送调用。
- 成功现场命令使用原解释器、`--execute --recording-directory .../continuous --start-deg 83.551 2.821 0 -1.132 24.567 5.556`，输出到 `.../continuous/retry`。完整命令和事件见报告及证据；这些绝对角度仅属于当次现场，不能盲目重放。
- 离线用 `/usr/bin/python3 scripts/h0_analyze.py <run>` 计算接收间隔和关联，用 `h0_export_window.py` 导出事件窗口。真实配置已填入 [config/hardware_session.yaml](config/hardware_session.yaml)。

## H0 实测结果

| 项目 | 结果 |
| --- | --- |
| RGB / 原始深度 | 640×480 rgb8 / 640×400 16UC1；1 count = 1 mm，0 无效；未对齐、未缩放保存数组 |
| 两路 CameraInfo | 完整保存 D/K/R/P、尺寸、frame、ROI、binning；各自匹配图像，K 可与设备服务核对；RGB D 的已知差异见下 |
| 静止联合记录 | 65 s RELIABLE 窗口完成；最终 240 s：RGB 7179、深度 7204、关节 48006 行 |
| 最终接收性能 | RGB 29.912 Hz、深度 30.017 Hz、关节 200.025 Hz；最大间隔分别 40.023/39.860/8.104 ms；无 >100 ms 间隔、倒退、队列丢帧或 CAN 错误 |
| 小幅动作 / 正常停止 | 第二次 J6 实测范围 1.962°，慢转、保持、返回；初始明确调整 J3 +1.611°→0°，没有全零回位 |
| 夹爪 / 现场观察 | 约 39.5→15.1→39.5 mm；用户确认“这次动作、停止、支架和线缆都正常” |
| 相机正常重启 | 成功退出并恢复两路流/参数；新传输配置下完成 90 s＋240 s 静止复核 |

最终 RGB–depth 最近接收时间差中位数/P95/最大值 8.399/16.305/17.915 ms；RGB–joint 为 1.219/2.374/3.681 ms。相机 header 来自驱动回调 `node->now()`，不是已证明的曝光时刻。CAN 保留内核时间、SDK 更新时间和主机单调接收时间；约 10 Hz 缓存快照不用于反馈率。实际相机/记录节点 `use_sim_time=false`。这些结果仅是同一主机的软件接收关联，未验证硬件同步。

## 失败记录与剩余限制

- 首次 BEST_EFFORT 接收 RGB 仅约 6.52 Hz；匹配发布者改为 RELIABLE 后短窗口恢复。约 720 s 连续记录又在约 182 s 后出现 RGB 成批到达；最终改项目独立 SHM 配置，90 s＋240 s 静止复核恢复到约 40 ms 最大间隔。成功运动段仍属于修改前的传输配置，**未在最终配置下再次做动作复核**，不得给旧运动数据套用最终时序指标。
- 首次动作六轴不动、夹爪开合；保留用户反馈和失败包。修正原封装关闭自动模式帧发送与 MOVE_J 入口不一致的问题后，现场第二次运动成功。未提高速度/幅度或关闭保护。返回斜坡结束时短暂未到位，随后保持段到位，没有持续控制器故障。
- RGB CameraInfo 发布的 D 为零，但设备服务返回非零 `r_k`；需在几何视觉使用前核实，不能声称内参精度已验证。`RD1001` 是驱动返回的 sensor platform string，不是已验证完整固件版本。
- 本轮只验证正常目标保持停止，未实测急停、断流看门狗、全工作空间线缆或视觉闭环。Astra 退出时有参数清理提示，进程正常结束并已成功重启；原日志保留。
- 结束时记录显示机械臂仍为 MOVE_J、六轴使能、无故障，约 `[83.551,2.737,0,-1.132,24.567,5.557]°`，夹爪约 39.5 mm；没有自动失能/reset/回零。相机及本轮接收进程已正常结束。后续硬件任务仍须读当时实时状态。

## 证据位置

- [H0 报告](reports/H0_HARDWARE_REPORT.md)、[成功动作短片](results/hardware/h0/20261116_2051/evidence/motion_success/clip.mp4)、[动作与接收时序图](results/hardware/h0/20261116_2051/evidence/motion_success/motion_and_timing.png)。
- `results/hardware/h0/20261116_2051/evidence/` 包含真实 RGB、uint16 深度小样本、两路内参、静止/失败/成功/重启短片、真实关节/夹爪及全部接收时间；最终 240 s 验证在 `evidence/final_validation/`。为提交体积抽取的 SDK 缓存快照明确标为约 1 Hz，原始时间不变。
- 完整本地运行目录及全部周期样本/AVI 保留但不提交；大 CAN/rosbag 在 `results/raw_large/hardware/h0/20261116_2051/`。bag 只覆盖若干运行开头的 10 s，不能称作较晚运动的全量 bag。没有删除唯一原件或另建压缩归档。

## 模型路线的既有成果与未完成项

开工包已有环境隔离/源下载脚本、来源锁定清单、门生成器、配置/查看器、支架 OBJ/预览/来源说明、四张用户安装照片和装配规则。既有单/双门 XML 曾在独立准备环境用 MuJoCo 3.3.0 编译并静止步进 2 s；[开工验证](reports/KICKOFF_VALIDATION.md) 不含机器人控制，也不是本轮 Linux 的整机验证。

模型生成、本机装配、P4/P5 与 P6 单门已有上方分版本记录；当前 front60_v2 单门清单已完成，双门仍是后续扩展。下一步研究实施以顶部 R0/B0 为准。使用已有生成器，不重新从零编写整套装配逻辑。

遵守 `accessory_payload_mode=omitted` 和 `synthetic_aligned_rgbd`：附件显式零质量，仿真理想对齐 RGB-D 不冒充本次实物标定。手眼及称重不阻塞名义装配。

下一轮先查看 `git status` 并正常拉取；仿真环境缺失时运行 `bash scripts/setup_env.sh`。本地完整流程见实时调试文档，默认查看命令为 `bash scripts/project_env.sh python scripts/live_assembly.py --watch`。本轮续接不执行任何 `h0_*` 硬件入口。

