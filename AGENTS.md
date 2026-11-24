# dog-and-arm 项目指令

当前接续入口为[reports/B0_OFFICIAL_FLOW_RESULTS_20261124.md](reports/B0_OFFICIAL_FLOW_RESULTS_20261124.md)、[最新 manifest](results/b0/standard_official_flow_20261124/baseline_manifest.json)、PROJECT_STATE.md 顶部和 prompts/NEXT_RUN.txt。独立 official_flow_s0_v1 已从 +850 WM-only 完成 u1000，实做 1,000 次 H32、10,000 个 H7 WM 批及 20,000 个 Critic 批。u1000 原 2 ms Warp 接触 0/10，完整名义 Warp 0/2、native 3.3.0 0/2。当前 B0-04，最终候选 null，合格完整双侧归一化回报 NA。 历史计划与历史门槛按原时间阅读。

695f3d7 的历史入口：docs/B0_OFFICIAL_FLOW_ALIGNMENT_20261124.md、docs/B0_FULL_TASK_TRANSFER_PLAN_20261124.md、reports/B0_JOINT_CONTACT_ROUND_REVIEW_20261124.md、PROJECT_STATE.md顶部和prompts/NEXT_RUN.txt。用户再次明确根本目标不变：完整按照固定官方SuperMimic进行迁移，达到或接近既定论文参照并形成独立标准结果。V0完整任务视频仅为新增交付，不能替代0.90参照/0.88接近带和B0正式资格。65c121b仍B0-04、候选null、完整双侧回报NA、原十项0/10、新H32=0。下一轮对齐官方采集→统计更新→Ratio→10批H7 WM→H32 Actor一次/Critic二十批主环；旧25%双块及50mm是项目自设诊断，不再充当Actor前置。H1混合、教师固定配额、冻结统计和gain32须逐项对照官方并登记处置，不能静默继承。以下历史计划不覆盖本段。

## 2026-11-24 计划提交 b5831d7 的接续状态（历史）

先完成标准迁移并冻结独立结果，再开发算法。当时最新实验753f1bc的首动作响应/WM数据贯通/新seed0 u200已结束并审查，六节点各0/10，完整回报NA、无候选，仍在B0-04。当时入口为 reports/B0_RESPONSE_ROUND_REVIEW_20261124.md、docs/B0_TEMPORAL_COMPATIBILITY_PLAN_20261124.md、PROJECT_STATE.md顶部与prompts/B0_START.txt/NEXT_RUN.txt。用户要求一次性多推进：并行定位、集中修复、实际训练与评测，u200不作默认终点；同包过十项后当轮接D、完整双侧/native，条件具备继续独立seed和冻结H。历史轮分别记账。

## 当前目标与授权

- 项目仓库：https://github.com/kaiwen123-yang/dog-and-arm 。用户已授权将本项目代码、配置、阶段结果和下一步计划提交并推送到这里。保留已有修改，普通提交，不强推；不创建本机压缩归档。
- 硬件：智身铜锤 M1 四轮轮足（ZGWS）＋松灵 Piper H＋官方平行夹爪＋官方腕部支架＋Orbbec DaBai DC1。
- 保留 MuJoCo 物理体系与原生模型，不安装智身 UE/GENISOM 仿真。B0 允许在独立环境使用官方 mjlab_research／MuJoCo-Warp 训练后端；原 native MuJoCo 3.3.0 工程保留为物理与任务基准。P0–P3 模型回合不操作真实机器人；用户新增授权的 H0 单独进行 Piper H＋DC1 实机联调，允许复用现有 SDK 的状态读取和现场启动的有限低速已验证动作。H0 不运动 M1。
- 用户明确当前是**根据 SuperMimic 迁移的标准阶段**。先在固定官方核心网络与学习机制下完成 B0，再进入多模态/VLA。世界模型、可微动力学和 H32 Actor/Critic 学习本来就在当前 B0 中实现，不后置到视觉语言阶段。用户新增要求以达到或接近论文指标为目标，单独形成迁移结果供后续比较。按 docs/B0_PAPER_BASELINE_PROTOCOL.md 评分。物理时间尺度集中计划已执行，当前审查和接续见 reports/B0_JOINT_CONTACT_ROUND_REVIEW_20261124.md、docs/B0_FULL_TASK_TRANSFER_PLAN_20261124.md、docs/B0_FULL_TASK_VIDEO_PROTOCOL.md、prompts/NEXT_RUN.txt；11月23日官方源码审查保留为历史依据，其中已完成修复以新审查为准。独立结果入口 reports/B0_STANDARD_TRANSFER_BASELINE.md。总路线和目标差距见 docs/RESEARCH_ROADMAP.md、docs/B0_SUPERMIMIC_PLAN.md、docs/GOAL_GAP_20261124.md。
- P1–P6工程和B0-03 seed0无接触学习已通过。11月23日的历史标准接触轮结束于638fddc：五条seed0配置链，gain32-u200自身345,268有效转移、Warp/native正式十项均0/10，另四组u50 Warp均0/10；415条nominal/55run全部失败，D、完整任务、seed1/2、H本轮未执行。旧r3 u1000两端0/10保留。23c9068恢复轮的540/546包继承15,000动作BC与参考前馈，546另有解析补偿，u1三端双侧nominal及Warp C各9/20属于有效混合对照，不能填入标准成绩。
- 最终目标仍是腕部 RGB-D＋语言＋本体历史的多模态/VLA 与世界模型、可微动力学联合，实现腿臂协同并上实机验证；先完成当前标准迁移。当前先单扇普通被动铰链门；双门是后续扩展，不是 B0 前置。门无闭门器、初版无锁舌，使用固定 U 形把手。
- 用户明确将手眼标定、标定板采购、相机/支架净重和惯量测量后置。这些不是当前开工条件，不要因此暂停或反复提问。

## 工作顺序

- 新会话先读 PROJECT_STATE.md、prompts/NEXT_RUN.txt、DAILY_WORK_LOG.md 最近日期和当前阶段涉及的文档；首次搭建再读 docs/BUILD_PLAN.md、docs/MODEL_INTEGRATION.md。无需每次小改动都重读整个仓库。
- 模型首轮完成 P0–P3：工作目录、隔离依赖、官方资产、单体模型、组合 URDF/MJCF及装配图。不要只列计划或只创建文件夹。
- 用户要求看到实时调试过程。进入本机模型回合，先按 docs/LIVE_DEBUGGING.md 打开 MuJoCo 桌面窗口，按 M1 单体、Piper 单体、整机顺序展示；调整安装参数后重建并在窗口重载，说明改了哪里。不能只做后台数值检查后宣布可视化已完成。
- 本机无 DISPLAY/可用桌面时，说明实际问题并处理显示入口；离线图片和视频可供审阅，但不能替代用户实时观看。当前 live_assembly.py 是 KINEMATIC_PREVIEW，直接 qpos + mj_forward；不得称为动力学站稳、规划或开门控制。
- 用户已完成机械臂本体验机。新增 H0 是机械臂与腕部相机的联调，按 docs/HARDWARE_INTEGRATION.md 和 prompts/HARDWARE_INTEGRATION.txt 执行；P0 后即可进行，可与 P1/P2 交错，结果供 P3 使用。设备不可用时保持 H0 pending，继续模型工作，不将其设为名义仿真的硬门槛。
- P4 固定基座接触、P5 自由基座移动与 P6 单门已完成。当前顺序为 R0 → B0-01～06 → 后续 R1～R8；P7 双门保留到扩展任务阶段。不得按历史提示重复已完成的 P6 批次；为 B0 补采缺失训练字段须另开目录并说明用途。各阶段完成后记录事实和下一步。
- 独立源模型审阅可以并行；组合文件、统一名称映射和 PROJECT_STATE.md 由主任务集成。无需为了占满 GPU 启动无关训练。

## 实现约定

- 官方资产在 vendor/，派生模型在 description/、sim/、assets/converted/。不修改官方源文件；记录上游版本即可，不做文件哈希测试。
- M1 使用官方 model/zgws/zgws.xml。当前这个目录没有 M1 URDF；如需要则从该树衍生并标注来源，不拿 ZSL/xgw 小狗替代。
- Piper 使用 piper_h_with_gripper_description.xacro，处理自带 world 和固定根连接；它不是 parent/prefix 宏，不再重复附加夹爪。
- 名称加前缀；所有转换网格的 basename 也唯一。保留 DAE 场景变换、惯性坐标和单位。不要通过删除网格或默认 balanceinertia 修复来掩盖问题。
- 当前 Piper 第一版采用官方 collision STL 同时作为简化 visual，不解析/转换原 DAE；这是记录在案的外观简化，不改变官方质量和惯量。后续如切换 DAE 精细外观，再完整保留其场景变换。M1 原生 MJCF 保留物理数值，衍生 URDF 以等价完整张量表达惯量。
- MuJoCo 3.3.0 下显式处理夹爪 mimic；保留两真实夹指并用一个耦合约束、一个控制输入。整机只有一个自由基座。
- config/assembly.yaml 为名义安装参数入口。依据官方网格和已有四张照片完成初始装配；有据可依的名义参数可直接确定并注明，不等待实测。
- 2026-11-20用户确定后续连接件采用双导轨跨接转接板、板下避让M1机盖，见 docs/MOUNT_RAIL_BRIDGE.md 和 config/mount_interface_reference.json。Piper H官方手册已确认70×70mm四孔/M5螺钉；附图为4×Ø5.4通孔，与正文孔型措辞的差别应保留。当前生成器使用 rail_bridge_front60_v2：板、两支座和臂沿机身 +X 同步前移 60mm，整体导轨基准与安装高度不变。新位置的 Linux 桌面检查和完整推拉已完成；冻结控制 86ade86 的有效配置清单为前拉 20/20、背推 20/20，当前背推名义航向 95°，见 reports/P6_FREE_BASE_DOOR.md。prompts/MOUNT_FORWARD_PUSH_PULL.txt 与 rail_bridge_v1 结果保留为历史，不作为默认下一轮入口；按安装/控制版本分别记录与统计。
- accessory_payload_mode=omitted：首版不计相机/支架额外载荷，附件几何显式零质量/零密度以免默认密度隐式加重，仍保留外形、碰撞和相机视角。
- 相机先用 synthetic_aligned_rgbd：同一虚拟相机输出 RGB 和深度。它不是实物 DC1 标定结果。

## H0 实机联调约定

- 复用已有 OSCBF-learn / pyAgxArm 的已验机环境、连接和状态读取，不重新安装旧 piper_sdk 或默认升级固件。历史接口/USB 身份先与本机实际情况对照，不自动归零或重跑旧完整动作。
- 相机只选一套与实际 DC1 匹配的驱动，核对实际 USB PID、话题、QoS、流模式和深度单位。分别保存 RGB 与深度 CameraInfo；原始分辨率不同不算故障。
- 先静止联合采集，再由现场操作者用既有控制入口启动少量低速小幅动作与夹爪开合；一次只有一个运动命令发送端。采集器只接收，图像处理/存盘不进入控制循环。开始动作需要现场安装与空间可用，不反复索取已经授予的项目授权。
- 保留原始时间戳及同一主机的单调接收时间。接收时间关联不等于硬件同步，CameraInfo 可读取不等于新标定。未知手眼外参不伪装为已标定 TF。
- H0 保存真实样帧、原始深度、状态/时间数据、短视频和报告，不能用历史验机或仿真数据冒充本轮完成。相机参数与仿真理想 RGB-D 配置分别记录。

## 环境与验证

- Ubuntu 22.04/ROS2 Humble 是用户已有环境参考。先检查本机，不重装已有 ROS、CUDA、驱动，不写 Conda base 或 shell 启动文件。
- 既有 native MuJoCo Python 依赖装在项目 .venv，使用 scripts/project_env.sh 隔离 Python/Conda 变量并保留显示和代理所需变量。B0 官方训练使用独立 .venv-b0 或等效隔离环境与对应启动入口，不能覆盖原依赖或误用指向旧环境的脚本。ROS/Xacro 在单独 ROS 环境处理。
- H0 复用已验证机械臂环境；相机 ROS 命令可经 scripts/hardware_env.sh 加载已有 ROS/overlay。该脚本不使用仿真 .venv、不安装软件、不自动启动硬件。新增相机 workspace 与 vendor 一样可重建，不提交其依赖和编译产物。
- 不建立防御性框架、哈希验证或冒烟测试套件。只做服务当前结果的检查：资源完整性、几组 FK 对照、开合与碰撞、真实动力学步进和任务数据。
- mj_forward/直接设置 qpos 只用于静态、运动学调试；不得把它们记成动力学或开门成功。门没有执行器，不能直接改门角度/焊接把手来冒充真实接触完成。
- 不对后台长任务设置强制墙钟终止时间。任务本身的仿真时长、实机采样区间可以作为明确实验参数。
- 命令失败时处理实际报错，不能隐瞒失败继续标成完成。只有确实缺少必要权限/资料时才问用户，先完成不受阻的部分。

## B0 研究实施约定

- 固定已验证 O1 来源：SuperMimic abc124c1bd5976341034668af3d12c087f2f1f55 与 mjlab_research dd51a9fcc98791a2f0b018b3c7f71a3eefd5ecdd；实际接口以固定源码为准。用户 Supermimic 仓库的 G1 复现已关闭，不重跑旧实验，不恢复全部归档。
- “原样”指保留固定官方主要网络组织、GenCoord、参考条件、原 tracking/软终止、H32 可微 rollout 和 Actor/Critic 更新机制。机器人/门状态、23 路混合动作、伺服单位、参考时刻、数据与环境接口等必要平台映射逐项登记并对照官方语义；不要求把人形机器人的维度、批量或单位机械照搬。不静默混入 O7、最新 main、自研任务奖励、风险终止头、解析控制器或新的任务协议。
- 参考运动、教师交互与当前策略 replay 分开；Actor、WM、Critic 的可见信息分开。学习策略评测禁止教师接管、状态重置或门驱动；固定物理伺服与独立评估器可以保留。
- B0 默认先状态/参考条件学习，腕相机资产继续保留；视觉语言训练、RoboMIND 支线与实机适配按后续阶段推进。当前名义手眼/载荷假设不冒充实测，但不阻塞 B0 仿真。
- 数据与模型细节按 docs/B0_DATA_MODEL_CONTRACT.md 落实。真实学习/物理评测没有执行时明确写未执行；不以计算图接通、预测误差下降或片段成功替代完整任务通过。
- 用户要求唯一详细北京时间日志、审查结果/发布下一计划/启动词/目标差距，并新增完整任务仿真视频和按比例比较参数，要求加快。根本目标仍是完整按官方SuperMimic迁移。下一轮先把采集、统计、Ratio、10批H7与H32 Actor/Critic主环逐项对齐并实际学习；撤销尚未执行的独立参考覆盖预训练分支。视频作为同一标准主线的附加交付，不用纯WM自设25%/50mm诊断长期阻断Actor。
- 新主链为独立official-flow seed0：按固定官方支持的WM-only warm-start只读取既有+850的dyn（含normalizers），Actor/Critic、全部优化器及online replay新建，官方学习率2e-4；不继承B003 Actor/Critic、旧优化器、gain32、5e-5或teacher配额。+850包没有sim_context，任务上下文由登记配置/环境映射构造并核验。既有+850训练成本和全部旧迁移链保留对比，声明warm-start身份，不称from-scratch或同机器人论文复现；精确执行以docs/B0_OFFICIAL_FLOW_ALIGNMENT_20261124.md和新主计划为准。
- 成绩分别标明参考姿态前馈、分阶段 BC 继承、实际 H32 更新、解析反馈、参考协议、训练/评测后端。540/546 全程包的 BC 链为接触→前拉→背推→native 双侧→Warp 双侧，各 3,000 次；最新 H32 更新中 BC loss=0 不会抹去此前 15,000 次监督。包内存在 WM、原 tracking 更新或同包三端通过，都不能替代标准迁移验收。
- 标准候选继承既定门槛：主后端十项接触 nominal 与每项 D01–D20≥18/20、同一候选双侧完整 C 各≥18/20、同包原 native 3.3.0 双侧 nominal 实际通过及真实 H32 学习链证据。CPU3.16 按需要诊断/回归，结果或未执行明确，不增加为正式出口门槛。达到后再按原协议训练独立 seed1/2；新链各自通过 B0-03，三 seed 配方/选模/候选全部冻结后再开 H，每 seed/侧目标≥40/50。 V0开发full_from_start nominal可提前尝试并交付，不以十项/D/C/seed/H完成作为录完整视频前置，正式成绩独立记账。
- 本轮保留已冻结的完整任务规则、参考版本、物理阈值、时限及 C/H 身份；片段已登记的 hold-margin v2 继续按原身份使用。任务定义或参考存在具体冲突时先保存证据并报告对标准迁移的限制，不能自动改成对象相对新任务、追加自研任务奖励/风险头或解析反馈后换一个通过结论；标准迁移未完成则如实报告未完成，不自动进入多模态/VLA。
- 同 phase、P6 教师自身成功、动作 MSE 下降都不是完整学习任务通过的充分证据。保留真实失败、当前事件头未达门槛和 phase-TD 的实际限制，作为诊断资产；不因此自动启用额外方法。实际阶段与参考 clock 分开，真实和想象的时间/单位/状态映射保持一致，不读取真实未来接触、门角或裁判答案。

## 论文指标与独立标准结果

- 方法ID为SuperMimic-M1Piper-standard-v1；本轮之前的实验manifest为results/b0/standard_joint_contact_20261124/baseline_manifest.json，审查为results/b0/joint_contact_review_20261124/audit_summary.json。当前仍B0-04、候选null、完整回报NA。V0完整视频只是新增可见交付，0.90参照/0.88接近带和独立标准基线要求不变，不以一侧视频替代完整双侧及多seed证据。
- 对照论文v3与固定官方源，分别记原论文G1 benchmark、迁移场景的完整归一化tracking/WM误差/训练成本、原物理成功门槛。回报目标0.90、接近数值带0.88（本项目预登记0.02容差），每最终seed/侧/split分别报告且须过物理门槛；0.90是论文SONIC参照线，不是SuperMimic最佳值。缺完整轨迹记NA，不用Policy/reward、单步tracking或失败后诊断积分冒充。
- 已完成并实训：固定基础effort动作率/reset哨兵、ReturnSampler、实际Ratio、逐clip夹末帧和逐样本lane/age。gain32的优化参数化不改变固定正则单位；固定统计、H1/H7混合和离线WM数据是登记平台配方，不是官方默认。standard_lanes_v1 已在终止后按 lane 复位，运行真实 200ms 前缀，跨记录块保留独立 history/clock 和 episode。进程恢复显式截断未完成物理片段并重建前缀。旧同步 collector 保留作冻结采集对照。首次物理失败的完整数值有效20ms已可进入H1/Actor，不预设Actor初态池过滤错误。
- 数据贯通、solver连续bias、细步和伺服力映射已有实证。接触训练.25ms/servo2ms/policy20ms/c=.50625及原2msWarp/native3.3正式评分按必要物理映射保留。动作单位、参考时间、lane资格属于必须落实的平台接口；H1混合/teacher配额/冻结统计/gain32属于项目训练配方，需按官方流程逐项处理。T2封存，不重复已关闭的J2/jaw边界扫描，不增加独立覆盖预训练阶段、BC、参考直通、解析Actor、新loss或网络。
- 固定官方8storedframes实际7scoredtransitions，不盲改H7为H8；官方Muon＋Adam和论文表中的Adam分开记录；fixed mjlab约0.2s全局timeline bins与论文1s分开。论文0.007–0.011不能与TCP毫米误差直接比较。
- 迁移成功并冻结独立结果前，不添加Actor动作BC、参考动作直通、解析补偿、新任务奖励/风险头/phase-TD、自研课程、新网络或对象相对新任务；后续多模态/VLA和算法开发统一后置。有据的数据/接口/采集/数值适配及原损失WM预热属于当前迁移，必须实际训练和物理评分，不只反复审计。
- 独立基线最终保存唯一候选/seed、代码与任务版本、全部继承预算、数据资格和测试身份、逐案分母/失败与必要视频。后续方法同seed/case配对，额外视觉/数据/BC/解析控制及成本单列。未达当前目标不自动切到多模态或新方法。

## 每日详细工作记录

- 根目录 DAILY_WORK_LOG.md 是唯一持续维护的逐日日志，按北京时间（Asia/Shanghai）自然日追加；同一天可多次补充，跨日长任务记录每一天实际进展，不为写日志停止任务。
- 每个有意义的实现、实验、问题处理、交接和提交节点更新当日日志。至少记录目标、执行环境、代码/配置与初始化来源、实际命令/run/产物路径、完成内容、关键指标及分母、失败/中断/未执行、问题现象与证据、原因是已证实还是假设、修复与复测、未解决项、决定与下一步。
- 历史回填写明来源和时间精度，提交时刻不冒充实验起止；没有证据的日期不虚构工作。成功、失败、计划和只读分析分开。更正旧结论注明更正日期与依据，保留有用失败记录。
- PROJECT_STATE.md 保存当前结论，阶段报告保存完整实验论证，DAILY_WORK_LOG.md 保存每天的工作和解决问题过程，彼此用路径关联；不能只写“完成训练”“已修复”而无证据。
- 日志记录已确认的提交/推送。当前文档自身提交可写“随本次提交保存”并在下一次补提交号，不为嵌入自己的 commit 制造反复提交。

## 每轮交付

更新 PROJECT_STATE.md、DAILY_WORK_LOG.md、当前阶段报告及 prompts/NEXT_RUN.txt：实际执行命令、生成文件、关键结果、未完成项、下一步。保留有用图片、短视频和时序数据；避免重复归档。
推送代码、配置、小规模必要结果和下一轮提示词到用户指定仓库；大资产按源清单恢复，不把 .venv、下载的第三方仓库或密钥推上去。
按有意义节点及时普通提交并推送：例如单体可见、名义装配修正、联合检查完成。说明提交内容和 commit；不每帧提交、不强推、不把别人的修改或整目录大录制盲目 stage。用户已授权，无需重复申请上传权限。
用中文解释变化、验证到哪一层、剩余问题及下一条可以执行的命令。没有执行的动作不得写成完成。

