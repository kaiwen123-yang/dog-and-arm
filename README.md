# dog-and-arm：M1＋Piper H 腿臂协同控制

<!-- mm03-plan-20261126-start -->
## 2026-11-26 · MM02 已审查，下一执行轮为 MM03 三路并行

MM02 最终监督/H32 各 0/20，停稳与触门均 0；36 个支撑/倾斜首败的记录倾角均不足 1°，可限定为持续未满足四轮支撑条件，具体失载机制仍须逐轮日志。新纠正池 98.64% 标签在驶近/停稳；旧完整示范仍占每批一半。R2 曾出现的停稳未保留到 R6。仓库没有 MM02 视频，本次实际审查了 MM01 教师/失败及旧混合双侧影片，身份分开。

用户要求扩大并行推进：A 做44案通道救回、失败视频与带臂学习轮腿层；B 补全阶段数据并训练 D23/H9；C 同父比较 BC、H8/H32、梯度受控H32和真实物理前向/模型反向，再接 H9-WM。初始8轮，三个微调种子，按4轮工作块接续；具体预算、候选规则与新盲测在登记中。三路同步开工，不等待旧B0或桌面实机。保存验证最好包与latest。

[详细审查](reports/MULTIMODAL_MM02_REVIEW_20261126.md) · [MM03执行计划](docs/MULTIMODAL_MM03_EXECUTION_20261126.md) · [论文依据](docs/MM03_RESEARCH_BASIS_20261126.md) · [机器登记](results/planning/multimodal_mm03_20261126/registration.json) · [启动词](prompts/MM03_START.txt)

按25核CPU/96GB显存建立有界共享队列并据实际吞吐调整。后台不设墙钟强杀/固定完成时间；原回合仿真时限保留。普通推送GitHub，完整大资产保留AutoDL并登记恢复位置，推送后不在用户电脑做额外归档。真实硬件由用户择时。

**本次仅完成审查、论文调研、计划/启动词与发布；新增Actor/低层/WM/bridge/Critic更新、物理步和硬件动作均0，MM03尚未启动。** 下方历史“当前/下一轮”按原时间阅读，以本节及MM03登记为当前入口。
<!-- mm03-plan-20261126-end -->

<!-- mm02-frozen-20261125-start -->
## 2026-11-26 00:10 北京时间 · MM-02 已结束

第 6 轮固定末点，监督纯学生 0/20，模型式 H32 纯学生 0/20。同初态完整成功率之差为 +0 个百分点。 正式 40 案中，首个两支均未达成的顺序事件为「停稳」。

实验从 2026-11-25 跨至 2026-11-26。正式两支各 20 案，新盲测共 16 案；教师适配 4 案、隔离教师可行性 8 案另列。桌面 Piper 由用户择时。

[MM-02 实测报告](reports/MULTIMODAL_MM02_RESULTS.md) · [冻结权重与恢复清单](results/multimodal/mm02_20261125/manifest.json) · [接续入口](prompts/NEXT_RUN.txt)
<!-- mm02-frozen-20261125-end -->

## 2026-11-25 23:47 北京时间 · MM-02 在 AutoDL 的 tmux 中运行

第 1、2 轮已完成，含短配对累计保留 Actor 11,264 次、WM 2,000 次、bridge 1,200 次。32 个轮末纯学生开发案完整成功 0。第 2 轮模型支名义背推 15° 在 4.742 s 到站、11.186 s 完成停稳，随后偏离操作站位。第 3 轮已重新从初态采集，终末盲测待冻结后执行。

AutoDL 会话为 `dog-arm-mm02-20261125`，运行目录为 `/root/autodl-tmp/mm02-20261125`。调度按登记完成训练、延长判断、末点评测、归档位置登记和普通推送。现场 Piper 由用户择时。 [后台交接](results/multimodal/mm02_20261125/tmux_handoff.json) · [MM-02 报告](reports/MULTIMODAL_MM02_RESULTS.md)

## 2026-11-25 22:32 北京时间 · MM-01已审查，下一执行轮为MM-02

MM-01正式监督/H32各0/12，24案无门接触；首次失败合计自碰12、J2越限5、J5越限7。六臂旧状态补训另0/8，不能把当前瓶颈归为单一J2错误。多模态采集/策略/WM/H32已实际实现，完整学生任务尚未成功。

[当前审查](reports/MULTIMODAL_MM01_REVIEW_20261125.md) · [MM-02集中计划](docs/MULTIMODAL_MM02_EXECUTION_20261125.md) · [机器登记](results/planning/multimodal_mm02_20261125/registration.json) · [启动词](prompts/MULTIMODAL_START.txt)

下一轮提取状态化P6全身纠正教师，分开专家标签与实际动作；一次短fixed/adaptive直连配对后，完成四轮新学生在轨数据聚合。监督与模型两支共享全部合格新数据、匹配BC预算，模型支额外使用学生真实起点的教师32拍物理恢复目标做H32优化。主段192训练回合，末点两支40正式案，其中16新盲测；条件延长两轮已登记。首次纯学生完整成功立即交1080p同回合原速视频。

本次只完成审查、计划/启动词和发布准备，新增优化/物理/硬件均0，尚未启动MM-02。桌面固定Piper由用户择时，当前算法仿真不等待桌面实机；原standard-v1与RefXY2封存。下方历史“当前/下一轮”按原时间阅读，以本节及MM-02登记为当前执行入口。

## 2026-11-25 21:56 北京时间 · MM-01 已完成训练与全机物理评测

监督基线 0/12，加入可微 H32 优化 0/12。24 案均无门接触。模型式支的一案完成底盘驶近，随后在停车阶段自碰。独立六臂纠偏补训在训练/验证开发场景 0/8。第二平台已加载从 GitHub 发布的监督权重，复现名义前拉驶近时 J2 越限。学生完整成功视频 0，已交同回合学生失败与 P6 教师完整成功的 1080p 原速视频。

[MM-01 实测报告](reports/MULTIMODAL_MM01_RESULTS.md) · [运行清单与权重](results/multimodal/mm01_20261125/manifest.json) · [逐案结果](results/multimodal/mm01_20261125/physics/physics_cases.json) · [接续启动词](prompts/NEXT_RUN.txt)

本轮的数据、监督策略、世界模型、H32 策略更新和从初态开始的全程评测均已执行。旧混合 u1 的双侧成功保留为教师能力来源。桌面 Piper 部署继续由用户择时启动。[完整算法路线](docs/MULTIMODAL_ALGORITHM_PLAN_20261125.md) · [桌面专用入口](prompts/PIPER_DESKTOP_START.txt) · [每日日志](DAILY_WORK_LOG.md)

## 已有完整仿真视频（1080p）

- [前拉完整视频，74.28秒](results/b0/success_video_hd_20261125/pull_full_1080p.mp4)
- [背推完整视频，54.44秒](results/b0/success_video_hd_20261125/push_full_1080p.mp4)
- [方法来源、原判定与视频范围](reports/SUCCESS_VIDEOS_AND_SCOPE_20261125.md)

这两部是旧546维混合策略同一权重的原成功回合高清重渲，尚不是桌面Piper或实机结果。

## 已有工程与硬件基础

**基础联合模型已生成：官方 M1 ZGWS＋Piper H＋双指夹爪＋名义腕部支架／相机。**提供可重建的组合 URDF/MJCF、桌面实时关节调试入口和被动单门组合场景。装配查看器仍是 **KINEMATIC_PREVIEW**；另有独立 P4 入口，固定底盘已从前侧拉门至 **59.963°**，从背侧推门至 **25.076°**。

**P6 自由底盘单门。** 安装板、两侧支座和 Piper H 沿机身前移 60 mm。采用 `rail_bridge_front60_v2` 和冻结控制 `86ade86`，本机 Linux 桌面复测前拉 60°、背推 25° 各 20/20 通过。初版背推 C20 驶近时左后轮碰柱，调整背侧航向后重跑整侧。旧版成绩和失败保存在分版本报告中。[完整结果](reports/P6_FREE_BASE_DOOR.md) · [逐案数值](results/p6/rail_bridge_front60_v2_20261120T133724Z/conditions.csv) · [桌面装配](docs/MOUNT_RAIL_BRIDGE.md)

自由底盘可用 `bash scripts/project_env.sh python scripts/p5_free_base.py --config config/p5_heading.yaml --live --video --hold-final` 查看站立、慢行、按 12° 航向转弯、伸臂行走和停车。 [P5 报告](reports/P5_FREE_BASE.md)

本机桌面装配检查已完成，并已显示 P4 固定基座动力学运行。结果和边界见 [P4 接触报告](reports/P4_FIXED_BASE_CONTACT.md)、[26 秒视频](results/p4/pull_20deg/contact.mp4) 和 [时序图](results/p4/pull_20deg/contact_timeseries.png)。实时装配说明见 [LIVE_DEBUGGING.md](docs/LIVE_DEBUGGING.md)。

![基础联合模型运动学预览](results/assembly/overview.png)

生成过程、数值检查和限制见 [装配报告](reports/assembly_report.md)。

**2026-11-16 已完成 H0：Piper H＋DaBai DC1 实机联调。**已保存真实 RGB、原始深度、两路 CameraInfo、静止/慢动作/停止/夹爪联合记录，并验证相机正常重启。最终 240 s 静止记录约 30 Hz 图像、200 Hz 关节反馈；成功动作实测 J6 范围 1.962°。首次失败及后续 QoS/DDS 修正、RGB 畸变参数限制均见 [H0 报告](reports/H0_HARDWARE_REPORT.md) 和 [动作短片](results/hardware/h0/20261116_2051/evidence/motion_success/clip.mp4)。手眼与附件称重仍后置。

## 从创建文件夹开始

在 Linux 终端执行：

    mkdir -p "$HOME/robotics"
    cd "$HOME/robotics"
    git clone https://github.com/kaiwen123-yang/dog-and-arm.git
    cd dog-and-arm
    env -u PYTHONPATH -u PYTHONHOME /usr/bin/python3 scripts/init_workspace.py

接着在本目录打开 Codex，先读 **PROJECT_STATE.md** 和 **prompts/NEXT_RUN.txt**。当前两期接续见 **docs/DESKTOP_PIPER_TRANSFER_PLAN_20261125.md** 与 **docs/MULTIMODAL_ALGORITHM_PLAN_20261125.md**，工程教师基准见 **reports/P6_FREE_BASE_DOOR.md**；H0 操作流程保留在 **docs/H0_RUNBOOK.md**。已有 Codex CLI 时可运行：

    codex

也可在 VS Code 打开此文件夹并使用已有 Codex 扩展。无需更换现有 Codex 配置。AGENTS.md 会提供项目规则，PROJECT_STATE.md 负责保存实际进度；后者是项目约定文件，需要按提示词读取。

如果本地已经有这个仓库，进入已有目录，查看 git status 后正常拉取和接着工作；不要再次 clone 到同名目录，也不要覆盖已有修改。

## 用户现在需要做什么

在开发平台保留已有修改并正常 fetch/pull 最新 main，将 [MM03_START.txt](prompts/MM03_START.txt) 交给 Codex 执行。按 [MM03 集中计划](docs/MULTIMODAL_MM03_EXECUTION_20261126.md) 同时推进轮腿稳定层、完整多模态任务和模型优化三路，完成真实训练与原判评测。NEXT_RUN、MULTIMODAL_START、B0_START 是同文入口。

MM02 原完整训练资产位于 AutoDL `/root/autodl-tmp/mm02-20261125`，按 [原 manifest](results/multimodal/mm02_20261125/manifest.json) 恢复；MM03 使用独立目录。首次纯学习完整成功立即交同回合1080p原速视频，代表失败也发布。后台不加墙钟强杀，GitHub推送后不再在用户电脑归档。[桌面 Piper 专用入口](prompts/PIPER_DESKTOP_START.txt) 由用户择时。

## H0：相机和机械臂联合运行

详细方案见 [HARDWARE_INTEGRATION.md](docs/HARDWARE_INTEGRATION.md)，启动提示词见 [HARDWARE_INTEGRATION.txt](prompts/HARDWARE_INTEGRATION.txt)。本轮按“复用原有环境→相机取流→静止联合采集→已有控制方式的小幅慢动作/夹爪变化→重启采集与报告”完成。

相机/状态采集与运动控制分开运行，保持唯一命令发送端；复用已有 pyAgxArm 接口，不重验机械臂、不自动运行旧完整抓放或 CPV demo。记录 RGB、原始深度、两路 CameraInfo、关节/夹爪反馈及时间信息。软件时间关联、手眼标定和视觉闭环分别记录。

H0 的实际接口已填入 `config/hardware_session.yaml`，结果位于 `results/hardware/h0/20261116_2051/evidence/`。成功动作记录含修正前的 RGB 成批到达，最终 DDS 配置只完成静止复核；不宣称硬件同步或新标定。复跑入口、进程分离及完整本地大录制的范围见 [H0_RUNBOOK](docs/H0_RUNBOOK.md)。

## Codex 模型首轮要完成什么

1. 检查实际 Linux/Python/ROS 环境，在项目 .venv 安装 MuJoCo 依赖。
2. 获取固定来源的 M1 ZGWS 和 Piper H 官方模型，生成源模型清单。
3. 处理 mesh 路径、M1 衍生 URDF 和 Piper 夹爪结构。首版 Piper visual 明确复用官方 collision STL，未转换 DAE 材质外观。
4. 根据官方几何与四张照片完成名义装配，生成组合 URDF 和 MJCF。
5. 交付整机正面、侧面、腕部局部与虚拟相机图；给出模型查看命令。

阶段说明见 docs/BUILD_PLAN.md，转换细节见 docs/MODEL_INTEGRATION.md，已核对的官方来源见 docs/SOURCES.md。

## 已有脚本与运行顺序

以下命令通常由 Codex 执行并处理真实报错；也可以在读完说明后手动运行：

    bash scripts/setup_env.sh
    bash scripts/project_env.sh .venv/bin/python scripts/fetch_sources.py
    bash scripts/project_env.sh .venv/bin/python scripts/inspect_sources.py
    bash scripts/project_env.sh .venv/bin/python scripts/build_assembly.py --stage all
    bash scripts/project_env.sh .venv/bin/python scripts/check_assembly.py
    bash scripts/project_env.sh .venv/bin/python scripts/live_assembly.py --watch

在 MuJoCo 窗口中：左右方向键选择关节，上下方向键微调；空格开合夹爪；F6 检查视角；F8 腕部/自由视角；F9 外观/碰撞专用凸包视图；F10 重载；F11 回到仿真 home；F12 退出。终端显示当前选择和数值。`--watch` 在 XML 成功重新生成后重开查看器；XML 修改失败会保留旧模型。

`config/assembly.yaml` 是安装关系入口。在另一终端修改参数后运行 `build_assembly.py --stage combined`；运行中的查看器会更新。只改 YAML 而不重建 XML 不会改变画面。

单体实时查看分别加 `--model sim/scenes/m1_preview.xml` 或 `--model sim/scenes/piper_preview.xml`；带静止被动单门的整机场景为 `sim/scenes/assembly_with_door.xml`。完整逐阶段流程见实时调试文档。

可选的运动学演示和离线证据：

    bash scripts/project_env.sh .venv/bin/python scripts/live_assembly.py --scripted-demo
    MUJOCO_GL=egl bash scripts/project_env.sh .venv/bin/python scripts/capture_assembly.py --video

二者都不调用 `mj_step`。离线图片／视频不能替代用户本机的实时开窗检查。

P4 固定基座接触复跑（仅仿真，默认保存到新的时间目录）：

    bash scripts/project_env.sh python scripts/p4_fixed_door.py --live --video

结果目录中的 `timeseries.csv` 可由 `scripts/plot_p4.py <结果目录>` 绘图。P4 场景使用独立固定根和专用把手高度；不代表 M1 具有站立控制。

原有被动门入口仍保留：

    bash scripts/project_env.sh .venv/bin/python scripts/build_doors.py
    bash scripts/project_env.sh .venv/bin/python scripts/view_model.py sim/scenes/door_single.xml

查看双门：

    bash scripts/project_env.sh .venv/bin/python scripts/view_model.py sim/scenes/door_double.xml

view_model.py 默认只做静态显示和 mj_forward，不运行无控制的整机动力学。显式添加 --simulate 才进行 mj_step。场景中的门是被动铰链，初始静止；门不会自行打开。

已用 MuJoCo 3.3.0 编译单门/双门，并分别从静止步进 2 s。下面是双门静态渲染，完整验证边界见 [准备验证记录](reports/KICKOFF_VALIDATION.md)。

![双扇被动铰链门静态预览](results/doors/double_closed.png)

无桌面环境时，可尝试显式选择本机可用的 EGL 渲染：

    MUJOCO_GL=egl bash scripts/project_env.sh .venv/bin/python scripts/view_model.py sim/scenes/door_double.xml --snapshot results/doors/double_closed.png

该截图命令不运行动力学。若本机 EGL 不可用，根据实际驱动报错处理，或使用桌面查看器；不要为此重装已有 CUDA/ROS。

## 目录用途

| 目录/文件 | 内容 |
| --- | --- |
| AGENTS.md | Codex 项目规则与用户偏好 |
| PROJECT_STATE.md | 当前完成情况、验证范围及下一步 |
| DAILY_WORK_LOG.md | 北京时间逐日详细工作、问题处理、实验结果与交接记录 |
| docs/B0_DYNAMICS_TRAINING_PLAN_20261124.md | 当前集中计划：物理步长、C20统计适配、有限H32与原完整验收 |
| reports/B0_DYNAMICS_ROUND_REVIEW_20261124.md | 870796a审查：联合WM漂移、真实接触覆盖、物理饱和与结果更正 |
| docs/B0_JOINT_CONTACT_PLAN_20261124.md | 下一轮联合分布预适配、原H32单链与完整验收 |
| reports/B0_TEMPORAL_ROUND_REVIEW_20261124.md | ff2d1e8审查：C20原损失折中、T2失稳、数据/物理资格与执行出口 |
| results/b0/temporal_review_20261124/audit_summary.json | 当前十案/预算/抽样复算、代数与计划边界 |
| docs/B0_TEMPORAL_COMPATIBILITY_PLAN_20261124.md | 已执行C20/T2时间配对计划及封存回执 |
| reports/B0_RESPONSE_ROUND_REVIEW_20261124.md | 753f1bc轮审查：数据已贯通、q/v兼容、solver疑点和梯度解释边界 |
| results/b0/response_review_20261124/audit_summary.json | 历史753f1bc独立60案、预算/抽样复算与证据范围 |
| docs/B0_CONTACT_RESPONSE_PLAN_20261124.md | 已执行：训练首动作响应、WM数据持续保留、原目标诊断与真实联合训练 |
| reports/B0_LANES_ROUND_REVIEW_20261124.md | 27284e2轮逐案/预算复算、数据断点、首响应与判定身份审查 |
| docs/B0_STANDARD_TRANSFER_PLAN_20261124.md | 已执行逐lane轮的历史计划与回执 |
| reports/B0_STANDARD_ROUND_REVIEW_20261124.md | 7180672轮历史审查 |
| docs/GOAL_GAP_20261124.md | 最新B0、论文参考指标与长期目标的逐项差距 |
| results/b0/standard_review_20261124/audit_summary.json | 历史7180672轮230案、15训练过程去重预算与覆盖复核；不含新仿真 |
| docs/B0_RECOVERY_PLAN_20261123.md、reports/B0_REVIEW_20261123.md | 前一恢复计划与审查，作为历史保留 |
| docs/B0_CONTACT_EXECUTION_PLAN.md | 已执行轮的历史计划与继续继承的任务/冻结门槛 |
| prompts/ | 首轮、续接、后续动力学阶段提示词 |
| docs/HARDWARE_INTEGRATION.md | H0 实机联调步骤、验收依据和接口核查 |
| config/hardware_session.yaml | H0 实测设备/驱动/流/时间域配置 |
| config/ | 来源版本、名义安装、门、观测配置 |
| materials/photos/ | 用户提供的四张腕部安装照片 |
| assets/accessories/ | 已提取的官方支架候选几何、来源与预览 |
| assets/converted/ | 按固定源重建的唯一命名网格，不提交重复大资产 |
| vendor/ | 脚本下载的上游源模型，默认不提交 |
| description/ | 衍生 M1、Piper H、组合 URDF 和名称映射 |
| sim/components/ | 被动门组件和后续机器人组件 |
| sim/robots/ | 组合机器人原生 MJCF |
| sim/scenes/ | 单体、整机、整机＋被动单门、单／双门场景 |
| controllers/ | 后续仿真控制器 |
| hardware/ | 本机相机 workspace/依赖；下载和编译目录不提交 |
| scripts/ | 可执行入口 |
| reports/、results/ | 阶段报告和必要实验结果 |

## 已决定的简化

- 原生 MuJoCo 为唯一仿真环境；只从智身官方仓库取资产。
- M1 背部安装参数先用明确的名义值，按网格碰撞关系调整。
- 相机/支架暂不贡献额外载荷，但保留视觉和碰撞；真实重量以后补。
- 腕部第一版输出理想对齐 RGB-D；真实 DC1 内参、双光心、噪声及手眼标定以后接入。
- 门无闭门器、无锁舌、无门电机；初期采用固定 U 形把手。
- 先单扇、后双扇；先固定基座验证接触，再释放 M1 基座完成移动操作。

## 仓库存储

本仓库是项目代码与阶段记录的保存位置。按有意义的可见调试节点提交并及时推送代码、配置、报告及必要小规模结果。无需另外制作本机压缩归档。vendor/、assets/converted/ 和 .venv 可按脚本重建，默认不提交；新拉取模型后先执行 fetch_sources.py 和 build_assembly.py，才能解析所引用的本地网格。四张实物照片已在仓库，无需重新下载或补拍。

源码引用和第三方资产许可见 THIRD_PARTY_NOTICES.md。
