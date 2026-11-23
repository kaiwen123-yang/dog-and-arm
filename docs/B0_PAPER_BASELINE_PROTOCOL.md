# B0 独立结果协议：SuperMimic 标准迁移与论文指标对照

日期：2026-11-23（Asia/Shanghai）。用户要求：依据已开源的 SuperMimic 详细研究和迁移，以达到或接近论文指标为目标，单独形成可供后续比较的结果。本文把这一要求落实为当前 B0 的结果定义、计分和冻结规则；不改变“标准迁移 → 后续新开发”的顺序。

**独立方法名称：`SuperMimic-M1Piper-standard-v1`。** 当前应持续保存它的真实中间结果和失败，最终交付同一方法在 M1＋Piper H 上的独立基线。记录一个负结果不等于宣布标准迁移完成；达到功能门槛与论文参考数值带仍是当前目标。实际最新成绩以 [标准迁移实测](../reports/B0_STANDARD_TRANSFER_RESULTS.md) 和 [本轮审查](../reports/B0_STANDARD_ROUND_REVIEW_20261123.md) 为准。

## 1. 论文指标与本项目目标必须同时明确

本次直接核读的是 [论文 v3，2026-11-19](https://arxiv.org/pdf/2610.28480v3)（§3–4、附录 A/C/D/F）、[作者项目页](https://supermimic.github.io/)以及下节列出的固定官方源码。表中数值来自原论文/作者说明；迁移任务的评测规则由本项目单独固定。

| 论文证据 | 原始数值和口径 | M1＋Piper 标准迁移如何使用 |
| --- | --- | --- |
| BONES-SEED，§4.1 / 附录 F | 129,514 条过滤后的**训练**动作；SONIC 回报 0.90；SuperMimic 在 1 H100×3 h 后超过 0.90 | 0.90 是明确的论文参考回报线，具体是 SONIC 线；不冒充 SuperMimic 最佳回报。迁移结果另报相同形式的完整回合指标 |
| 训练动作覆盖，表 A.8 | SONIC 179 条失败；SuperMimic 为 25 条（1×3 h）及 0 条（2×9.8 h） | 保留原分母、任务和计算预算。几十次门任务通过不能推出同等失败率，更不能写成未见条件泛化已达论文 |
| LAFAN1，图 4(a) | 40 clips、2.45 h；SuperMimic 1 GPU 在 1.2 h 内达到评测回报 0.82 | 与 BONES-SEED 的 0.90 分开；本项目不能把不同数据集/时长的分数混为同一个指标 |
| 世界模型，图 3(c) | 随动作数据从 1 h 到 264 h 增长，状态预测误差 0.007–0.011；按预设 nominal error 归一化、在策略轨迹上测量 | 这是状态预测统计，不是 TCP 米数，也不是任务成功率。先对齐实际计算定义再比较数值 |
| 计算效率，图 5 | H100 上常用批量 WM rollout 相对 Warp 超过 10 倍；另一比较约节省 64 倍 imagined steps | 本项目记录实际 GPU、批量、精度、物理子步和完整训练耗时；未做匹配对照时不声称获得同倍数加速 |

论文附录 F 的每条动作从第一帧开始，只跑一次；固定足部摩擦 1.0，无域随机化/观测噪声，以根高/倾斜训练终止计失败。它不以抓持力、门角、释放和撤离判成功。论文 §6 也把地形和对象交互列为尚待扩展的范围。因此，本项目可以达到“迁移场景的论文参考回报数值带”，并单独证明门操作能力；**不能把跨机器人、跨任务的两个标量相等写成复现了同一个 benchmark。**

历史 G1 O1 已关闭。[source_lock.json](../config/b0/source_lock.json) 保存其 40 clips、平均回报 0.8744398924。这里仅引用既有记录；它不是 129,514 动作的成绩，也不作为本次重新启动 G1 训练的理由。

## 2. 固定官方实现，逐项登记平台迁移

正式来源继续锁定 SuperMimic `abc124c1bd5976341034668af3d12c087f2f1f55`、mjlab_research `dd51a9fcc98791a2f0b018b3c7f71a3eefd5ecdd`。本次查看到的上游后续变更只作来源研究；`source_lock.json` 的 `candidate_not_applied` 不会自动成为当前训练代码。

| 需要核对的源码 | 具体核对与迁移要求 |
| --- | --- |
| [models.py](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/models.py) | Dynamics 的状态/动作统计、动作物理变换；MultiEncoderAE 的参考编码、共享解码与 32 维 tanh latent。官方非主 encoder 的 latent 对齐不等于教师动作 BC |
| [representations.py](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/representations.py) | GenCoord、积分、物理子步系数、本体历史、参考边界。固定官方参考末端采用最后有效帧夹取；本项目的零填充/归一化后 mask 必须登记为平台参考适配，不能声称完全相同 |
| [wm_learner.py](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/learners/wm_learner.py) 和 [replay_buffer.py](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/replay_buffer.py) | 固定代码 `horizon=8` 采八个存储帧，循环 `actions.shape[1]-1`，实际监督七次后继。论文称 k=8。记录 `stored_frames / scored_transitions / prediction_horizon`，不因名称差一就擅改训练。当前 H1/H7 配方单列；40 步采集不等于在线 H32 监督 |
| [policy_learner.py](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/learners/policy_learner.py) | H32、冻结 WM 参数但保留导数、软生存权重、Critic bootstrap、GAE。日志 `Policy/reward` 含想象/价值项和尺度处理，不是本协议的物理完整回报 |
| [learner_utils.py](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/learners/learner_utils.py) | 论文超参数表写 Adam；固定源码实际对隐藏二维权重使用 Muon、其余使用 Adam。保存本次实际实例化的 optimizer、参数分组及恢复状态；不把表格摘要等同于已核查的执行代码 |
| [tracking_reward.py](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/utils/tracking_reward.py) | 六项 tracking 核、动作变化与关节限位项、每步乘 dt；身体目标按根 xy/yaw 重锚。必须记录本项目 tracked bodies 和动作惩罚所在坐标；绝对 TCP/把手误差另报 |
| [supermimic_runner.py](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/runners/supermimic_runner.py) | 采集、统计更新、WM/Actor/Critic 调度与 reset 采样。默认 history=1/rep_state 与论文的十帧本体并不相同；本项目应明确实际配置为 proprio/history=10，不只写“官方默认”。原 4096 环境时 `4096/(10×2048×8)×16=0.4`，不能把 replay_ratio=16 直接叫作论文 update-to-data=16 |
| [g1_constants.py](https://github.com/HybridRobotics/mjlab_research/blob/dd51a9fcc98791a2f0b018b3c7f71a3eefd5ecdd/src/mjlab/asset_zoo/robots/unitree_g1/g1_constants.py) | 官方动作单位 `0.25×effort_limit/stiffness`；映射到轮速、臂角与总夹口宽时逐通道说明单位、偏置、裁剪、探索幅度和前动作，不把 G1 数值机械套用 |

论文的网络/机制与实际配方分开登记。论文附录 C/D 的 WM 为 2048×3；Actor 编解码隐藏宽度 2048/1024/512/256；Critic 256/128；H32、γ=0.99、GAE λ=0.95，10 个 WM minibatch 与 20 个 Critic minibatch。其大规模预算、320,000 迭代、学习率调度和资源规模不能由“导入同一个类”推定已一致。当前较小批量、预训练继承、采样配比、优化器是否恢复均记录原值和实际值，按真实数据与更新数比较。

固定mjlab源码的分箱是全拼接时间轴约0.2 s（`bin_count=int(total_frames//(0.2/step_dt))+1`），ReturnSampler用整数帧映射；论文附录D.1写1 s，两者分开登记。适配ragged MotionID和合法起点时保持不跨clip/terminal的边界，不把论文文字静默替换固定源码。

本轮还已证实一个应进入适配表的差别：固定官方动作变化惩罚作用于 effort-scale 之前的 policy output；当前 [EffortScaledActor](../learning/b0/model.py) 输出 home＋scale 后的公共规范命令，[接触训练](../learning/b0/contact_training.py) 将此规范命令送入 tracking。因此“调用原函数”不代表动作正则的物理权重已相同。原尺度和 gain32 的当前计分坐标彼此相同，gain32 不能因此被误写为奖励已扩大 32 倍。下一轮应先登记并配对修复这一语义；最终评分坐标必须提前冻结，旧坐标结果保留原身份，不能跨坐标直接宣称回报提高。

`EffortScaledActor`＋原 tracking/softdone 的标准链为主。BC 初始化、ReferenceResidualActor、StanceArmActor、解析补偿、phase-TD、风险头和不同任务协议分别命名；即便某分支使用同一 WM/H32，也不能并入标准成绩。标准链的修复限于有证据的平台接口、数值实现、参考/数据资格与可比训练组织；不默认新增奖励或控制头。

## 3. 完整物理回报的计算与“接近”数值带

### 3.1 单条回合计分

评测 manifest 在跑分前固定 reference 身份、起点、长度、目标保持段、任务/裁判版本、后端和噪声条件。令 `T_i` 是该条**预先规定的完整计划时长除以20 ms得到的等效控制步数**，末端不足20 ms时它可以不是整数；`r_max` 是实际冻结奖励的理论20 ms上界，当前原 tracking 为0.1。等价分母是 `5 × planned_duration_seconds`（须核实冻结正项上界仍为5）。不得从观测到的最大值估计上界，也不默默把末个部分区间向上取整。

`R_i = sum(r_i[t], t=1..T_i) / (T_i × r_max)`。

求和使用真实物理后继状态、当步实际执行命令、前一实际命令和相同参考时钟计算的原 tracking；不含 Critic、discount、想象 reward 或后续重试。提前物理失败的未执行余段按吸收态零回报计入**完整分母**，失败区间若不足一个 20 ms 则按已执行子步时长计奖励，不能获得完整 20 ms 的奖励。成功提前结束时，须按预登记保持规则实际跑完评分区间；无法还原完整区间的历史记录为 NA，不补造后续奖励。不裁掉真实负惩罚以抬高成绩。

实际积分区间用 `dt_j`、真实后继和明确保存的 `reference_query_time/frame` 计算；部分失败步和部分末步沿同一冻结参考时钟约定查询目标，只按实际dt加权，并记录所用规则。完整任务reset的previous-action零值可能是“无历史”哨兵；应保存 `previous_action_valid`，按官方重置语义单独定义奖励首步，不能把哨兵当已执行canonical零命令再做effort转换而凭空产生大惩罚，也不静默改变Actor历史输入。有已重建教师前缀的片段，使用最后真实执行的clipped命令。

每个 reference 先得一个 `R_i`，再对预登记条目等权平均，防止长静止段淹没短难段；同时报告中位数、最差条目及分阶段指标。阶段指标是解释失败的辅助结果，不代替完整平均。`r_max`、dt、条目权重和 `T_i` 随数据保存；改了奖励尺度/动作惩罚坐标或任务长度必须另列协议版本。

主线物理任务评估沿用本项目原裁判，包含接触/力/阶段时限，故这一分数命名为 **`B0 full-episode normalized tracking return`**。它与论文在归一化形式上相对应，在机器人、数据、身体集合及终止定义上不同。若另报只有官方根高/倾斜终止的 tracking 诊断，必须另有真实完整轨迹并单列，不能把已在力超限处结束的记录当作跑完了该诊断。

片段评测按冻结起点重建的教师前缀不计为策略能力，也不计入其回报；它们明确标注 `segment_from_registered_start`。完整任务必须从 frame 0/任务初始状态连续执行，无教师接管和中途 reset，标注 `full_from_start`。这两种成绩不混表求同一个完整回合均值。

### 3.2 本项目预登记的目标数值

| 结果标签 | 数值要求 | 同时需要满足的条件 |
| --- | --- | --- |
| 达到论文参考回报数值线（迁移场景） | 每个最终 seed、每侧完整预登记评测集合的平均 `R_i ≥ 0.90` | 本节口径有效；下节物理门槛通过；每 seed/侧/split 单独列数 |
| 接近论文参考回报数值带（迁移场景） | 上述每个 seed/侧平均 `R_i ≥ 0.88`，但存在未到 0.90 的项 | 相同口径与物理门槛；明确距离目标还有多少，不把“接近”写成超过论文 |
| 未达到或尚不可比较 | 任一必要项 <0.88；或完整评分/候选/独立 seed 尚缺 | 保存实际指标、失败和 NA 的原因，继续当前标准阶段的有据修复与训练 |

**0.88 来自本项目事先选定的 0.02 绝对容差，是工程目标；不是作者对“接近”的定义。** 0.90 也只是论文明确报告的一条参考线，不是论文所有最佳指标的合格证。训练集 coverage、开发集、H 泛化集合分别给分，不用跨 split 总平均掩盖弱项。不同 checkpoint 的最好前拉/背推不得拼成一个模型。

当前只能把这些完整回报字段写为 **NA / 尚未按此口径评测**。最新证据中的单个后继 tracking（例如 0.09080/0.1）不能推出完整回报约 0.908；该次后继所在回合仍可能首步力超限。

## 4. 物理能力、世界模型和计算预算共同组成结果

### 4.1 原物理门槛不变

遵循 [标准迁移计划](B0_STANDARD_TRANSFER_PLAN_20261123.md)：同一标准候选十项接触 nominal 通过，每项 D01–D20≥18/20；同一包 Warp 双侧完整 nominal 与 C01–C20 每侧≥18/20；同包原 native3.3 双侧完整 nominal 通过；有持续真实 H32 更新和多个节点的物理能力证据。接触 v1 与已登记 hold-margin 分别保留身份。CPU3.16 仍是必要时的诊断，不额外增加正式出口。

然后冻结 seed0 的方法配方，开展 seed1/2 独立初始化与采集，各自先通过 B0-03；三 seed 的配方、选模规则和候选全冻结后，再打开各侧 H01–H50，每 seed/侧要求≥40/50。原名义门槛是 10/10，不是拿累计多包的总通过数凑十项。当前尚无标准候选完成该链，不进入多模态/VLA 来替代本阶段。

### 4.2 世界模型误差按真实定义和模式报告

官方 `wm_learner._compute_losses` 对各组平方误差以 `1/nominal_error²` 加权，再按通道数平均；项目又有夹指/门状态及其尺度。保存每个组的维数、单位、尺度、平均方法及有效 mask。先用相同真实窗口复算已有官方状态 loss，再说明与论文图 3(c) 的剩余差别；未对齐前，不以“TCP=0.01 m”宣称进入论文 0.007–0.011 区间。

H1、固定 O1 实际七次后继、真正第八次后继诊断、H32 分别命名；新增第八步诊断不改变在线训练配方。区分记录动作开环预测与 Actor 在预测状态上闭环展开。按自由运动、接近、夹持、推拉、释放/撤离以及前拉/背推报告误差、终止模式和覆盖数，保留简单保持/常速外推对照。重叠窗口数与独立 episode/lane 数同时写，不能把大量重叠窗口当成等量独立试验。WM 误差下降仍需真实冻结策略验证。

### 4.3 训练和效率记账

为每条标准链记录继承与新增的 Actor/WM/Critic 次数、动作 BC 次数、有效真实转移、真实模拟区间、采样窗口数与 H、Actor imagined steps、replay 继承/更新、预训练数据、GPU 型号和数量、精度、批量、各阶段耗时。接续 run 的累计计数不再次相加。固定评测耗时单列；数据采集/WM 预热算作训练成本，不能从总成本中隐去。当前标准链继承 B0-03 与 held_r2，不能把 u0 写成从零成本。

回报曲线同时画对真实转移数、Actor imagined steps、累计训练 GPU-hours；数值不完整时只报告有证据的轴，不估造墙钟时间。达到目标的时间采用预登记检查点中首次达到且后续确认保持的节点；保留原始非单调曲线和失败预算。论文 3 h 是参考预算，不是本项目强制终止时间，也不因硬件不同承诺相同速度。

需要测吞吐时，在同一设备/实际批量/相同 20 ms 控制跨度下同步计时，写明是否包括 Actor/观测、图编译与反向传播。固定官方 `scripts/benchmark.py` 是**速度 benchmark**，不是 129,514 动作覆盖评测器。当前物理为 10×2 ms，论文为 4×5 ms；这个差别必须随倍率列出。没有匹配实验时，不报告“迁移实现了 >1000× 或 64× 加速”。

## 5. 独立结果的保存、选模与后续公平比较

最终标准基线需要一个单独报告与可解析 manifest：方法身份、上游/项目提交、必要适配表、每个 seed 的唯一冻结 checkpoint 及恢复位置、解析配置、奖励/裁判版本、数据/参考/开发/H 身份、完整预算、逐案结果、回报、失败原因、WM 模式误差和必要成功/失败视频。原始证据继续按 run 保存，不能覆盖成最后一次好结果。缺失字段填 NA 和原因，不填零。

开发选模先满足安全和物理通过门槛，再按预登记开发完整回报选择；并列时按较早节点，不使用 H 选 checkpoint。没有合格候选时不授予“标准迁移完成”状态。有限的相同 case 集合报告精确分子/分母；三 seed 单独列出并给均值、标准差/范围，不把同条件重复或相邻窗口当成独立样本制造窄置信区间。

动作率坐标对照的训练目标可以不同，但选模/主比较须把各候选放到同一预登记评分坐标下重算，并同时保留原口径诊断；不能拿两个不同reward定义的数字直接比较提高幅度。

后续新方法必须复用冻结的模型/物理/数据资格/测试身份和计分代码；同 case、同 seed 做配对差值，报告达到同目标的预算和相同预算下的结果。若新方法添加视觉、额外教师数据、动作 BC、解析控制或更大网络，把差别及其成本列入方法行；用于隔离贡献的对照单独定义。标准 baseline 的 frozen 行继续保留，不能随新方法改裁判后覆盖。

用户要求的每日详细过程继续只追加到根目录 [DAILY_WORK_LOG.md](../DAILY_WORK_LOG.md)，包括当天查到的官方差别、失败、真实修复、未完成指标与下一步。本文随当前 GitHub 计划交付；本轮研究本身不冒充已经进行了新训练或补充物理评测。
