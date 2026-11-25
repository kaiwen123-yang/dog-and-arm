# 固定官方 SuperMimic 主循环与 M1＋Piper 迁移实现对照

## 2026-11-25｜当前适配登记与原标准边界

原 A–D 实测提交787d5e38已完成，下一执行轮见[RefXY2计划](B0_REFXY2_TRANSFER_PLAN_20261125.md)、[最新审查](../reports/B0_PREGRASP_ROUND_REVIEW_20261125.md)和[机器登记](../results/b0/pregrasp_review_20261125/next_registration.json)。本次新增训练/仿真0；原standard-v1/u10000仍B0-04、候选null、合格双侧回报NA、V0=0。

独立RefXY2与等宽零控制仅改变Actor当前根XY信息，542输入不冒充固定官方原540接口。官方核心及execution_recipe、WM/Critic、原物理与裁判保持；完整u10000迁移首层Adam旧状态与原统计，各+200、有双侧原物理依据再配对至+1000。原结果与新增方法分别保存，算法/VLA后置。具体预算、固定窗/ready条件、并行FP64限额和首个完整视频交付以新登记为准；下方旧“当前/下一轮”属于历史，不恢复A–D或原u15000。

## 2026-11-25｜u10000已执行核验与当前兼容性问题

同一官方主链已实跑10000 H32 Actor、100000 H7 WM和200000 Critic，102414758有效转移。79fd3cf末点正式任务仍失败，按原双侧证据结案不延长。当前[审查](../reports/B0_U10000_REVIEW_20261125.md)与[集中计划](B0_PREGRASP_COMPATIBILITY_PLAN_20261125.md)替代旧u4991续训入口；本次没有新学习执行。

再次直接核对固定源码的goal540、77×10本体输入、原reward reanchor和policy learner。参考根相对平移30维的移除来自官方motion task；当前proprio配置对共同根XY平移不区分。robot58仍无XY，contact75还含17维门真值，因此不能凭“切默认”静默换信息边界。当前推导不等于已经数值/物理证明名义失败根因。原0.3m位置reward核宽不是任务容差；原3mm裁判不据此修改。

[官方输入与目标审查](../results/b0/official_u10000_review_20261125/model_audit.json)同时标明源码事实、推导、未做物理验证项。下一轮集中验证原预抓窗口和真实响应；没有具体实现错误时交付独立适配提案，不制造bug或自编新目标混入旧标准结果。下方历次执行记录保留。

## 2026-11-25｜u4991 连续执行核验

同一official_flow_s0_v1已保留4991 H32/49910 H7 WM/99820 Critic和51124715有效转移；本轮3991更新逐行计数及统计一致。u4991原两后端接触均2/10，完整0/20。当前按[下一计划](B0_OFFICIAL_FLOW_NEXT_PLAN_20261125.md)完整恢复至u10000、有据至u15000，保留下列官方机制与必要平台映射；本次未改学习cfg或核心。

B0阶段、预算与门裁判属于本项目，不能称为作者训练课程。初次WM warm-start祖先14850批继续披露。训练参考phase物理终止与formal独立事件就绪的差异保留，不凭差异自动改训练。全终局ready记录和父恢复/节点路径适配是下一执行轮的运行配套，不是新算法或WM放行门。[审查](../reports/B0_OFFICIAL_FLOW_CONTINUATION_REVIEW_20261125.md)

## 2026-11-24｜51a0133 的执行核验与剩余配置边界

本轮已经实际运行本表要求的采集→统计→Ratio→十H7 WM→H32 Actor一次/二十Critic，共1000轮更新，首批与累计计数、terminal纳入和恢复均有提交回执。下方695f3d7登记中的“待实现”不再表示主环尚未接通。[首更新](../results/b0/standard_official_flow_20261124/first_update.json) · [当前审查](../reports/B0_OFFICIAL_FLOW_ROUND_REVIEW_20261124.md) · [下一段完整恢复计划](B0_OFFICIAL_FLOW_CONTINUATION_PLAN_20261124.md)

| 源码与配置事实 | 项目实值及声明 |
| --- | --- |
| 固定runner默认actor_obs=rep_state、history_length=1；官方也支持proprio/history | 本项目沿O1选proprio/history10。属于官方支持配置的选择，不等于逐项采用默认；下一段保持 |
| make_motion_task始终取compute_wm_goal第二项；actor_goal_dim=num_goals−30 | Actor goal540，WM/Critic goal570；切rep_state也不会多出参考平移。门几何不透传Actor |
| G1资产soft_joint_pos_limit_factor=.9；Representation.bind读取soft_joint_pos_limits | M1/Piper当前罚项直接用编译jnt_range；四轮±99999。资产映射差异如实登记，尚未证为失败原因，本段不更改 |
| 固定runner max_iterations=1000000 | 它计外层采集，不计Actor update；本轮u1000为项目预算，不是官方收敛上限 |
| 官方warm-start先装WM/context后建学习器 | 本轮首次加载+850 dyn含统计、环境重建context，新建Actor/Critic/优化器/replay已实际完成；祖先WM14850批披露 |
| 项目完整恢复额外保存优化器/replay/RNG/solver/lane | 下一段恢复u1000全部状态，不再重做WM-only warm-start，不称为官方原生恢复特性 |
| 官方核心支持目标环境终止映射 | 训练逐lane按参考phase/物理失败，正式另有station XY/heading与独立事件；差异明示，不据此添加新训练目标 |

固定来源：[runner](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/runners/supermimic_runner.py)、[representation](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/representations.py)、[task](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/tasks/task_spec.py)、[G1资产](https://github.com/HybridRobotics/mjlab_research/blob/dd51a9fcc98791a2f0b018b3c7f71a3eefd5ecdd/src/mjlab/asset_zoo/robots/unitree_g1/g1_constants.py)。项目实现见 learning/b0/model.py、contact_model.py、contact_lanes.py、official_replay.py、scripts/b0/official_flow.py。

当前已核主环和接口不能被表述为论文结果复现成功，仍B0-04/候选null/完整回报NA。也不能把合法的proprio配置、完整terminal行或连续轮范围误报为新bug。以下保留原固定源码与首轮处置登记；新预算/保存入口以连续计划为准。

2026-11-24，北京时间。核对固定官方 SuperMimic `abc124c1bd5976341034668af3d12c087f2f1f55` 与项目实验端点 [65c121b0d7a2519b9c503589024f075e7b7889ba](https://github.com/kaiwen123-yang/dog-and-arm/commit/65c121b0d7a2519b9c503589024f075e7b7889ba)。本次为源码审查与后续实施约定，没有新增训练、仿真或成功视频。

**根本目标不变：按固定官方机制完成 SuperMimic 在 M1＋Piper 场景的标准迁移，以达到或接近已登记论文参照为目标，独立保存结果，再开发新算法。完整任务视频是新增交付，不替代0.90／0.88指标、物理门槛或独立B0结果。**

现行代码确实复用了官方网络、GenCoord和Actor/Critic learner，但已加入H1/H7混合、教师数据配额、固定WM统计、gain32及额外WM验收门等项目选择。因此，不能把65c121b整套训练流程称为固定官方代码的整体原样复现。本文件明确哪些是必要机器人映射、哪些是官方机制、哪些是需要移除或单列的项目配方。

## 1. 已直接核读的固定官方来源

| 固定文件 | 本次核对内容 |
| --- | --- |
| [supermimic_runner.py](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/runners/supermimic_runner.py) | `_init_common`、`step`、`_flush_normalization`、`run`、Ratio、WM warm-start、模型保存 |
| [wm_learner.py](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/learners/wm_learner.py) | 默认批量/时域/学习率、WM统计更新、原分组损失、实际7次后继、优化与裁剪 |
| [policy_learner.py](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/learners/policy_learner.py) | H32、Actor反传、当前Critic bootstrap、GAE和20次Critic优化 |
| [models.py](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/models.py) | Dynamics状态/动作统计、proc动作坐标、MultiEncoderAE输出和latent辅助项 |
| [learner_utils.py](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/learners/learner_utils.py) | Muon与Adam参数分组、反向/裁剪/优化器步、捕获图状态 |
| [train.py](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/scripts/train.py) | 实际训练CLI、默认4096环境、本地参考文件、直接构造runner并运行 |
| [train_utils.py](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/scripts/train_utils.py) | 环境创建与参考资源解析 |
| [run_config.py](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/runners/run_config.py) | 从已序列化运行配置重建配置；本身不是训练状态恢复器 |
| [play.py](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/scripts/play.py) | 加载WM/Actor做推理；不等于恢复训练优化器/replay |

本项目固定mjlab来源仍为 `dd51a9fcc98791a2f0b018b3c7f71a3eefd5ecdd`。不自动追随官方新main，也不重新启动已关闭的G1复现。

## 2. 官方真实执行顺序

### 2.1 每次真实采集之后更新统计

`SuperMimicRunner.step()` 从实际环境读状态、本体和参考时刻，构造任务Actor输入，查询当前Actor并加入配置动作噪声。环境真实推进后，将动作、动作前状态、上一动作、时钟、终止/截断、sim context及需要的历史字段写入replay；随后处理历史、日志与ReturnSampler。

该步结束后调用 `_flush_normalization()`，明确执行两类更新：

1. WM状态统计使用本次新采集状态经representation后的值；WM动作统计使用 `Dynamics.proc(action)` 后的动作值。
2. Actor观测及参考输入统计使用真实采集时保存的Actor输入。

这些统计更新发生在真实采集之后、下一轮学习之前；不是仅在初始化时计算一次。不得将项目的 `freeze_wm_statistics=true` 描述成官方默认。动作统计所见的物理坐标必须与Dynamics前向相同，不能将canonical动作、基础effort输出与处理后的伺服目标混用。

### 2.2 Ratio调度WM与Actor/Critic连续学习

`run()` 的正常主循环为：

1. 真实环境采集一拍，并完成上述统计更新。
2. Ratio依据已登记replay ratio决定本拍执行多少次学习。
3. replay已有所需窗口后，采样配置的10个WM minibatch，执行WM更新。
4. 随即调用一次policy learner，执行H32可微想象、Actor更新和Critic拟合。
5. 回到真实采集，并按原日志/保存间隔输出结果。

固定默认Ratio系数为 `num_envs / wm.num_batches / wm.batch_size / wm.horizon * replay_ratio`，调用自变量是实际主循环step。项目如因真实200ms前缀、终止lane或无效区间而改变可计数数据量，须明确列出计数映射；不能仅保留变量名Ratio就声称调度数量完全相同。

**官方主循环没有WM验证TCP误差、四项1.25E0、连续两块通过或50mm拦截Actor的分支。** 其数据就绪检查是replay有足够窗口，不是先把WM训到一组开发指标。项目的25%和50mm均为后来加入的工程规则，恢复官方主循环时移除其额外学习门槛身份，保留诊断记录。真实非有限数值、错误数据schema或恢复失败仍是程序/接口问题，应修正实际错误，不伪造有效更新。

### 2.3 官方Actor与Critic更新

policy learner将Dynamics和Representation设为eval并冻结其参数，在WM中进行H32可微rollout。原tracking、softdone、生存权重与当前Critic bootstrap形成Actor目标。Actor更新后，使用该想象rollout计算GAE回报，并拟合当前Critic。

ActorCritic默认每次policy update为1次Actor优化；Critic对四个分块做五轮，共20次优化。没有独立target Critic。WM冻结的是Actor反传期间的参数更新，不是永久停训WM。

## 3. 官方默认数值与资源处理

| 项目 | 固定官方默认 | 65c121b现有配置/事实 | 新官方流程的处置 |
| --- | --- | --- | --- |
| 真实并行环境 | train.py默认4096 | 128 | 先按官方值与实际M1模型核验资源；确需降档才记录实际原因及预登记值 |
| WM batch | 2048 | 256 | 以2048开始；资源降档须单列数值配置 |
| policy batch | 4096 | 256 | 以4096开始；不把256称官方默认 |
| WM每次批数 | 10 | 8个H7＋2个H1 | 恢复10个官方horizon=8窗口 |
| WM horizon | 8个存储帧，实际7次监督后继 | H1/H7额外混合 | 恢复原7次监督后继，不因命名盲改成8次后继 |
| WM/Actor学习率 | 2e-4 | WM后期5e-5 | 新建官方优化器，默认2e-4；旧5e-5不隐式继承 |
| replay ratio | 16 | 16，按项目有效区间调度 | 使用官方Ratio公式并核对真实采集计数映射 |
| policy时域 | 32 | 32 | 保留H32 |
| AC gamma/lambda | .99/.95 | 原learner默认 | 保留 |
| 动作采集噪声 | .1，官方Actor输出坐标 | .1×旧基础exploration_scale，gain32前保存 | 按官方动作输出坐标映射；报告实际各通道物理噪声，不能只比“.1”字符串 |
| 网络 | WM 2048³；Actor 2048/1024/512/256；Critic256/128；latent32 | 主要网络维度已继承 | 保留固定网络组织，仅按M1任务输入/输出维度绑定 |

数值默认不等于必须忽略现场资源。可核验实际显存、模型副本与并行吞吐，必要时调整batch或环境数；该操作是有证据的资源配置，应在训练前登记，并重新报告对应Ratio与实际数据量。不得为省事默默继承128/256，也不得把减批量后成绩写成使用了官方默认资源配置。

## 4. Warm-start、保存和恢复不能混称

### 4.1 固定官方代码实际支持什么

官方 `_init_common()` 先构造WM；若配置 `wandb_run_path`，加载该运行的 `world_model.pt`，随后才构造WM learner与优化器。该可选warm-start加载的是WM bundle，其字段为Dynamics与SimContext状态。Actor、Critic和各自优化器随后按官方构造流程新建。

核读的 `train.py` 没有Actor/优化器/replay/Ratio/RNG的完整resume入口。`run()` 保存 `world_model.pt`、`actor.pt`及有Critic时的`critic.pt`，不保存完整优化器、replay、Ratio或随机状态。`play.py`会加载Actor做推理，`run_config.py`重建配置；两者都不能据此称为官方完整训练续训功能。

项目现有六优化器/RNG/replay/live lanes恢复能力是本项目附加的运行工程功能，可以保留以防长任务中断，但不得声称该序列化包就是官方warm-start协议。

### 4.2 本轮+850初始化的确切身份

如果使用 `joint_contact_20261124/adapt/wm_000850.pt`，其选择依据来自已经查看过的开发验证，不是H集选择，也不是最终候选。该包保存了 `dyn`、两个优化器、RNG、累计批数、物理dt和C20系数；**它没有单独的 `sim_context` 状态字段**。

新独立official-flow seed0链只提取该WM的Dynamics参数及绑定的state/action normalizer，完成明确schema和动作坐标映射后，作为已有WM warm-start。接触context的五个语义为back_side、ground_friction、finger_friction、hinge_frictionloss、hinge_damping，须从同一已登记M1任务配置/实际环境绑定形成官方所需context接口；来源写为配置/环境映射，不能声称从+850读取了不存在的字段。

逐项核对状态顺序、物理单位、31路预测、75路representation、23路动作、5维context及积分绑定；如果shape相同而语义不同，仍不兼容。原包的 `action_scale/action_offset` 和动作normalizer也属于物理函数的一部分，不能只加载MLP而忽略坐标。发现不兼容先修接口，不静默换权重、丢失字段或降低验收。

**新链不载入+850的旧优化器/5e-5，不载入旧Actor/Critic或其统计，不导入旧replay/Ratio/RNG来冒充连续恢复。** Actor/Critic按官方构造新建，优化器按官方默认新建，在线replay从新链真实采集建立。这样是“已有WM初始化的新官方流程迁移链”，并非从头全新训练，也不是旧u0/u10链的精确续训；+850及其全部前序数据和训练成本单列。

旧B0-03 Actor、旧两支u10、+850/+990全恢复包及pending保留原身份。新链不能把旧Actor的1000次更新计作自己的Actor更新，也不能隐去WM已经使用过的数据与成本。

## 5. 核心保留、必要映射、项目额外配方的完整处置

| 分类 | 项目 | 现状与后续明确处置 |
| --- | --- | --- |
| 官方核心 | Dynamics、MultiEncoderAE、GenCoord、原WM分组损失、H32 Actor/Critic | 保留固定官方类和更新机制；不加新loss/风险头/phase-TD/BC |
| 官方核心 | 真实采集、统计flush、Ratio、10个H7、Actor1＋Critic20 | 恢复该顺序；不在中间插入开发误差资格阶段 |
| 必要机器人映射 | M1 ZGWS＋Piper＋真实双指＋被动门 | 保留真实资产和原task定义，输入/预测维度变化逐项列出，不伪装为G1同benchmark |
| 必要机器人映射 | 23混合动作、轮速度/关节目标/夹口全宽 | 保留基础物理映射和真实/想象一致性；动作率继续固定基础effort单位 |
| 必要机器人映射 | 0.25ms训练物理、2ms外部servo、20ms策略、C20系数.50625 | 保留已核定数值身份和实际缓存时钟；原2msWarp/native3.3正式成绩身份另列 |
| 必要机器人映射 | 被动门context、独立裁判、完整任务参考 | 按实际语义绑定；真实未来状态/裁判答案不进入Actor |
| 项目额外配方 | 8个H7＋2个H1 | 新官方流程取消该混合，恢复10个horizon8窗口；首失败H1历史数据保留但不挤入默认联合批次 |
| 项目额外配方 | 75%online＋固定native/grip/multimode/response配额 | 新官方主环恢复当前在线replay；已有离线源仅保留初始化的历史来源，不能继续偷偷混入训练 |
| 项目额外配方 | 每十批整块交替两个cohort | 不继承；使用新链官方在线replay，不再追加对交替方式的独立训练支线 |
| 项目额外配方 | 固定WM输入统计、额外首层重标 | 新链恢复每次真实采集后的官方统计更新；不能在归一化flush时暗加首层重标或保留冻结开关 |
| 项目额外配方 | gain32 | 新链附加gain设为1，采用官方基础物理映射；不把改变优化参数化称为单纯不变的单位换算 |
| 项目额外配方 | 25%双块门、50mm自动拦Actor | 移除其学习前置/额外阶段身份；误差继续报告，不能据这些工程线追认历史通过 |
| 项目额外配方 | B0-03 Actor热启动和新增独立覆盖预训练路线 | 新official-flow链不隐式继承旧Actor；撤销未发布覆盖预训练支线。覆盖仅为接口诊断/必要参考资产完善，不另建学习课程 |
| 项目运行工程 | 完整恢复包、预算、视频、日志与GitHub回读 | 保留，明确它们是可复现运行支持，不改官方学习规则 |

### 动作坐标必须避免的错误

官方 `MultiEncoderAE.forward()` 只对latent做tanh，最后decoder为线性输出，没有将最终动作一律限制到[-1,1]。项目 `RobotActor` 的旧clamp位于动作转成canonical坐标之后。新链不能误把基础effort输出先clamp到±1，再做物理映射：以当前J2基础单位为例，这会把命令错误限制到home附近约±0.025rad，改变完整姿态的可达范围。

正确做法是明确官方Actor输出、固定基础effort、处理后的伺服目标以及原模型物理边界分别在哪一层应用，并使真实采集、replay、Dynamics.proc、上一动作与想象环境一致。gain32=1不等于修改原机器人关节限位、PD、力限或6N裁判。相关比例须同时给出分子/分母和实际物理单位，不能只报无量纲数掩盖坐标变化。

## 6. 成绩与视频的地位

65c121b按原计划未过连续两块资格，新Actor更新为0，正式共同u0为0/10；这些原事实不改。新官方流程解除额外工程门，不会让旧模型自动成为合格最终候选。

完整任务视频记录同一冻结学习策略从原起点连续执行、每20ms依据真实后继出动作；参考尾段、教师接管、阶段重置或不同节点拼接均不能当该策略完整成功。视频可在开发中及时生成，但标准迁移仍须达到既定物理任务、独立结果和0.90参照／0.88接近带要求。0.90是论文SONIC参照，机器人与任务不同不能写成同benchmark复现；缺完整任务实测仍记NA。

标准迁移未完成时继续报告实际限制，不自行换任务、增新算法或把“能录视频”替代原目标。本文件的恢复官方流程是下一轮实施要求，不是已执行成果。
