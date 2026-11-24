# B0 下一轮：按固定官方主流程校正迁移并完成真实策略任务

2026-11-24，北京时间。接续实验 [65c121b](https://github.com/kaiwen123-yang/dog-and-arm/commit/65c121b0d7a2519b9c503589024f075e7b7889ba)。**本文件是前瞻计划，尚未完成其中的新实现、训练或完整视频。** 当前仍 B0-04、候选 `null`、完整双侧物理归一化回报 `NA`。

## 1. 根本目标与此次纠正

用户再次明确：先完整按照 SuperMimic 官方学习流程完成 M1＋Piper 标准迁移，以达到或接近论文参照指标为目标，单独冻结结果，再开发算法。加快速度不能改变这个目标。完整任务仿真视频是新增交付，不能替代标准迁移、0.90 参照／0.88 工程接近带、双侧物理任务和独立评测。

固定源为 SuperMimic `abc124c1bd5976341034668af3d12c087f2f1f55`、mjlab `dd51a9fcc98791a2f0b018b3c7f71a3eefd5ecdd`。以[官方流程对照](B0_OFFICIAL_FLOW_ALIGNMENT_20261124.md)的永久源码链接为准；论文、固定代码和场景适配分别记录。官方主顺序为：

**真实仿真采集 → replay／历史／ReturnSampler → WM 与 Actor 归一化统计更新 → Ratio 调度 → 10 个 H7 WM minibatch → H32 Actor 一次与 Critic 二十次 → 继续采集。**

H7 指官方配置 horizon=8 个存储帧形成的七个监督后继。官方只有 replay 就绪检查，没有把独立 TCP 误差训练到某条线才允许 Actor 更新的阶段。

此前核心网络和学习器有官方依据，但固定 WM 统计、8H7＋2H1、在线／离线配额、gain32、WM 预适配和误差放行门属于项目改动，不能将整套流程称为官方原样复现。本次明确纠正：

- 取消“四项 1.25E0 连续两块通过”与“50 mm 复评”对 Actor 的额外阻断，保留误差诊断。65c121b 按当时规则未放行的结论不改，不补造 qualified.json。
- 撤销本次尚未发布草稿中的独立 B 姿态覆盖预训练支线。覆盖检查只服务于接口和参考资产核验，不建立额外学习课程。
- 项目训练配方不得放在“必要平台适配”名下静默继承。逐项恢复官方主环与默认算法配置；机器人映射必须有单位、形状、时钟和源码依据。

新链独立记账，不重新命名历史成绩。必须实际执行并核验后才能评价流程对齐程度，不能在计划提交时宣布已经完整复现。

## 2. 新链初始化与配置

新运行身份建议 `official_flow_s0_v1`；方法总名继续 `SuperMimic-M1Piper-standard-v1`，manifest 增加 execution_recipe 与旧配方差异表。原 B0-03 通过记录、B0-04 全部失败和两支 u10 的 pending=2 均保留。

### 2.1 默认采用官方支持的 WM-only warm-start

复用已有 +850 世界模型，减少重做动力学学习。选择依据是既有开发长窗，不使用 held-out H。读取 `results/raw_large/b0/joint_contact_20261124/adapt/wm_000850.pt` 中的 dyn 及绑定 normalizer。**该文件没有独立 sim_context，也不是现成官方完整 bundle**；context 从已登记任务／环境配置映射，并逐项核验语义。

按官方构造新的 seed0 Actor、Critic 和全部优化器，默认学习率 2e-4；新建 online replay、统计更新队列及 Ratio／ReturnSampler。WM 自带已学习统计作为初始化，随后按官方真实采集更新；Actor 统计从新初始化开始更新。

不继承 +850 的优化器、5e-5、训练 RNG、旧 replay；不继承 B0-03／旧 u10 的 Actor、Critic、策略优化器或 gain32。**这不是旧训练连续恢复，也不是论文同机器人从零复现。** +850 的预热、预适配、训练数据和历史成本全部列明，不从比较中删掉。默认 Actor/Critic 新建是对齐官方训练入口，并非宣布旧 B0-03 实验无效。

若 state/context/action schema 不一致，修正有明确物理语义的映射后进入同一主环；不能只凭 shape 相同宣布兼容，不能静默换 checkpoint 或恢复旧配方。

### 2.2 必须落实的配置处置

| 项目 | 新链规定 |
| --- | --- |
| WM 来源 | 当前 Actor 的真实在线 replay；旧 native／Warp 教师池保留诊断，不注入默认主环 |
| WM 时域／频次 | 官方 horizon=8，每次十批 H7；关闭额外 H1／H32 WM 分支 |
| 归一化 | 真实采集后更新 WM state、processed-action 和 Actor 输入统计；不冻结，不加官方没有的每拍函数重标补偿 |
| 网络／目标 | 固定官方 MultiEncoderAE、Dynamics、GenCoord 学习机制、原 tracking／action-rate／softdone、当前 Critic bootstrap |
| 默认数值 | WM batch 2048、Actor batch 4096、WM／policy LR 2e-4、H32、gamma .99、lambda .95、1 Actor＋20 Critic、noise .1、replay ratio 16；原 Muon＋Adam与裁剪 |
| 动作坐标 | 官方基础 effort 对应物理尺度映射，gain32 不继承；真实、想象、奖励、噪声和 replay 坐标一致 |
| WM 诊断 | 记录四项 H32 TCP、H1／H7误差和梯度；25%／50 mm 不调度 Actor |
| 学习前置 | 必要接口正确性、正常 replay 就绪、有限数值；没有额外预适配资格阶段 |

先在现有 GPU 核实默认配置实际显存。确有资源阻塞才预登记实际 batch／并行数、资源证据与对应 Ratio 计算，标明数值配置差异；不静默改损失、更新顺序或另开配置扫描。资源允许就使用官方默认。

官方 MultiEncoderAE 对 latent 使用 tanh，decoder 末端不是基础 effort 的 ±1 截断。必须核对“网络原输出→物理目标→实际执行边界”全链；不能把 gain32 改成 1 后错误截断网络输出，使 J2 只能在 home±.025 rad 活动。+850 的 action_scale/action_offset、normalizer 和 Dynamics.proc 一起核验坐标兼容；真实／想象和固定基础 effort 动作率一致。这是接口校正，不是新增控制器。

## 3. 集中实施，不再只推进诊断

### 3.1 官方调用与机器人接口一次核对

优先复用固定官方 runner／learners，通过机器人环境与表示适配接入。必须保留项目 wrapper 时，以实际调用顺序、数据张量、统计计数、原损失和优化器步数证明逐项对应，不能仅凭 import 官方类声明全流程一致。旧 joint_main.py 依赖 qualified.json、旧 Actor、混合配方和 50 mm 暂停线，不是新计划的直接启动命令。

核对 state／goal／history 的维度、顺序与单位，六臂／夹口、两真实夹指、被动门、reset、prev-action、terminal/truncated、参考时间／末帧、processed action 和 FK。训练／开发／正式集合继续隔离。

保留已验证的逐 lane 复位、真实 200 ms 前缀、solver 缓存及合法区间身份；前缀不计 Actor 成绩。replay 与 episode 边界按固定官方语义映射，记录终止字段和资格，不把 reset 拼成物理后继。Ratio 按实际采集及有效样本记账，不伪造额度。

接触训练保持 0.25 ms 物理／2 ms 外部 servo／20 ms Actor／80 微步／c=.50625；原 2 ms Warp、native3.3 正式身份和 6 N 门槛保持。复用已结束的步长研究与 112 个边界分支，不重做相同 J2／jaw 扫描，不改 PD、力上限或任务判据。

并行只读检查完整训练参考、六臂／jaw、归一化与目标编码。B0-03 教师 J2 命令约 .8–.974533 rad 是已知支持范围，不能冒称全部实际状态范围或唯一失败原因。确有参考资产／单位错误就修正并登记；合格参考进入同一主环，不开独立覆盖课程、不加 BC 或参考动作直通。

### 3.2 首更新回执和连续训练

新 u0 保存源码／配置、初始化谱系、统计和物理身份。首个实际联合更新记录：真实采集、统计更新、Ratio、十个 H7 WM step、一个 H32 Actor step、二十个 Critic step；保存原目标分项、有限梯度、动作坐标及第一批索引。正常完成后继续，不要求独立 WM 验证分数先下降。

首段目标 **u200＝200 次 H32、2,000 个联合 WM minibatch、4,000 个 Critic minibatch**，按实际 Ratio 获得额度；u0／u1／u10／u50／u100／u200 保存节点。checkpoint 是观测点，不是每修一项就结束回合的理由。有限但较大的 WM 误差或 u10 仍 0/10 均不自动阻断官方循环。

真实非有限、接口／时间／恢复错误或进程故障需要保存现场并修复，然后继续原计划；这些是正确性问题，不包装为新的学习阶段。每个主要节点由同一 Actor 每 20 ms 根据真实后继出动作，不能用第一拍 Actor＋参考尾段证明策略能力。

u200 后依据真实跟踪、接触持续、阶段事件和完整任务进展，登记并执行有据延长到 u500／u1000。无进展则保存负结果及具体阻塞，不无限堆预算、不切换新算法求演示，不预先保证下一轮成功。

## 4. 标准资格与新增完整视频

[原协议](B0_PAPER_BASELINE_PROTOCOL.md)保持：同包十项 contact nominal；每项 D≥18/20；同包双侧完整 Warp nominal、C 每侧≥18/20；同包 native3.3 双侧完整 nominal；独立 seed1/2；三 seed 配方和候选冻结后 H 每 seed／侧≥40/50。旧 B0-03 成绩与新 Actor 能力分开列；不能冒用旧通过记录。新链在同一官方主环中证明必要无接触／全程能力，不新增外置预训练课程。

u0／u50／u100／u200 等冻结节点可提前做 full_from_start 名义开发尝试，记录完整分母和首次失败，不等于最终资格。首个一侧完整成功立即交原速连续视频，同轮继续另一侧；同包双侧能力必须来自同一包。视频须从 frame0 至任务结束真实闭环，无中途 reset、教师／解析接管、直接摆 qpos、门主动驱动或跨 checkpoint 拼接。详见[视频协议](B0_FULL_TASK_VIDEO_PROTOCOL.md)。当前两部失败诊断视频不能替代此交付。

0.90 是论文明确的 SONIC 参考线，不是 SuperMimic 最佳分数；0.88 是本项目预登记接近带。不同机器人／任务仅按协议比较无量纲形式并明确限制，不声称等价复现论文 benchmark。没有完整双侧物理回报就仍写 NA，不用单片段 reward、TCP 毫米误差或一个视频代替论文比较。

## 5. 比例、成本与交接

参数同时报官方值、映射规则、项目值、实际值和单位。TCP／关节误差按各自 nominal-error 归一化；门力报 N 和对适用相位 6 N 的比值；伺服报力／限幅与误差驱动力／限幅，不按尺寸简单缩放 PD，不混用力与力矩。列出继承 WM 成本、新链成本、物理步、有效转移、实际优化步与墙钟，不只比较 u 编号。

现场仍用 /root/autodl-tmp/dog-and-arm-b0-temporal-v1；旧资产 results/raw_large/b0/joint_contact_20261124/ 保持。新小结果建议 results/b0/standard_official_flow_20261124/，大资产 results/raw_large/b0/official_flow_20261124/；跨日保留启动 ID，不覆盖旧目录。完整优化器／RNG／replay 恢复包是项目运行保障扩展，不谎称官方原生完整恢复功能。

执行者同轮连续完成：源与差异登记、接口实现、真实首更新、预算内联训、物理评测、可用完整视频、报告／manifest和下一入口。唯一 DAILY_WORK_LOG.md 按北京时间记录每天工作、解决与未解决问题、证据和实际命令。普通推送 GitHub 并回读真实报告、manifest、提示词和视频链接。不能只再交审计，把可运行的训练留到以后。

本次审查只更新文档及审查索引，新增仿真／训练／优化器步数均为零；65c121b 原始成绩、预算、资格和恢复资产不改。
