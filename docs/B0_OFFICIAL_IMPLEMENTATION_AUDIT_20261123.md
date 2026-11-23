# 固定官方 SuperMimic 实现与 M1＋Piper H 迁移审查

> 历史快照提示（2026-11-24）：以下保留11月23日当时的实现状态和判断。动作率/ReturnSampler/Ratio/clip末帧等现已完成对齐与实训；当前入口为[11月24日审查](../reports/B0_STANDARD_ROUND_REVIEW_20261124.md)，不按旧待办重复启动。

日期：2026-11-23，北京时间。审查目标代码为 `638fddcb2f025006595f79f27a977a8fba41cbc2`，新增代码范围为 `5e6db44..638fddc`。本文件为源码与已归档证据的审查，没有执行新的训练或物理评测。阶段仍是标准迁移；下列建议须在下一执行轮形成实际配对结果，不能提前记为已修复。

固定 SuperMimic 来源为 `abc124c1bd5976341034668af3d12c087f2f1f55`，mjlab_research 来源为 `dd51a9fcc98791a2f0b018b3c7f71a3eefd5ecdd`。论文、固定代码、项目实际适配分别登记；最新上游 main 只作为候选来源，不能静默替换已验证版本。本次检查的官方模块如下。

## 1. 官方实现到项目调用的映射

| 官方固定源码 | 项目对应入口 | 核对结论 |
| --- | --- | --- |
| [models.py][O1]：Dynamics、MultiEncoderAE | [contact_model.py](../learning/b0/contact_model.py)、[contact_policy.py](../learning/b0/contact_policy.py) | 同一官方 MLP/LN/GELU 与 latent32 组织。标准五组实际类为 EffortScaledActor；没有参考臂/夹口动作直通、解析反馈或额外动作 BC。 |
| [representations.py][O2]：GenCoord、前瞻、观测 | [model.py](../learning/b0/model.py)、DoorMotions | 机器人 24 个实际关节含两指；23 路控制含一个逻辑夹口。历史10、77维本体、540维Actor目标是本平台映射；官方尾窗采用当前 clip 最后有效帧夹紧，项目另加零槽规则，见 §4。 |
| [gencoord_helpers.py][O3] | ContactRepresentation.represent | 根角速度先转世界系，再按官方规则转本体系；门角/角速度与几何量单独扩展。无需将机械臂和被动门伪装成人形关节。 |
| [tracking_reward.py][O4] | ContactRun.collect、DoorImagination、继承的 representation reward | 原六项 tracking 与关节软限位公式仍在，但动作率项的动作坐标已不同；见 §2。不能只凭函数名相同就说完整奖励语义一致。 |
| [wm_learner.py][O5] | ContactRun.learners、ContactWindows、OnlineContactReplay | 官方8行窗口计7个预测转移；项目H7与此相符，另加2个H1批接纳完整终止转移。不是全部原论文配方照搬；见 §3。 |
| [policy_learner.py][O6] | ContactRun.policy | 调用原 ActorCriticPolicyLearner：H32、gamma .99、lambda .95、Actor一次/20次Critic，WM参数冻结而状态/动作梯度不断。新门Critic第一层重建、兼容隐藏/输出层迁移属于暖启动，不是原Critic完整续训。 |
| [learner_utils.py][O7] | 上述官方 learners 自动构造 | 实际是内部Linear权重Muon、其余capturable Adam，Actor beta2=.95；本轮标准配置未替换成纯AdamW。论文表与固定代码若表述不同，分别登记，不擅自替换。 |
| [world_model_env.py][O8] | DoorImagination | 同一 softdone 根高/倾斜、survival、bootstrap；项目在物理与想象中统一按 successor t+1 打分。softdone不含接触力/握持丢失/阶段时限，已知能力边界需保留。 |
| [multi_task_world_model_env.py][O9] | DoorImagination、build_actor_obs_td | motion slot=1，velocity slot=0；Critic可见完整门WM状态与目标，Actor不读未来真实接触或裁判标签。 |
| [replay_buffer.py][O10] | OnlineContactReplay、ContactWindows | 为实际失败/20 ms完整后继重写了窗口组织，禁止跨terminal；128 lane同步cohort及32cohort回放容量是项目配方。 |
| [supermimic_runner.py][O11] | train_contact.py、ContactRun.collect/update | 项目未调用原runner的训练比例调度，继承配置中的replay_ratio=16实际不控制接触循环；见 §3。 |
| [reset_sampling.py][O12] | ContactRun.collect的eligible抽样 | 官方默认return-based RSI；项目当前等额六条参考、各条内部均匀抽合法帧，未接入ReturnSampler。应明确登记并安排原机制适配。 |
| [task_spec.py][O13] | build_actor、sensor | 使用原TaskSpec与历史TensorDict构造，实际动作/参考信息权限保持一致。 |

当前标准核心确实已经运行，但“使用官方 learners”与“所有论文/官方训练语义已对齐”是两个不同的审查项目。已通过的 B0-03 不应因此整段推翻；接触迁移中发现的差异应在对应边界补齐证据。

## 2. 优先修正候选：动作率惩罚所用的单位

### 2.1 已证实的数学差异

固定官方 Dynamics 的输入是缩放前动作，内部执行 `physical = action * scale + offset`；tracking reward 对同一缩放前动作使用 `-dt * 0.1 * sum((action-last_action)^2)`。[Dynamics 源码][O1]与[奖励源码][O4]

项目为了统一腿、轮、臂、夹口与回放，使用固定物理范围归一化命令 `a`，随后通过 ActionMap 转成真实伺服目标。EffortScaledActor 已在输出端计算：

- `a = home_action + standard_action * decoder_output`；
- `standard_action = (0.25 * effort_limit / servo_gain) / action_map_scale`，夹口从单指换成全开度；
- ContactRun.collect 和 DoorImagination 给原奖励函数的仍是 `a` 和上一条同坐标命令。

因此物理目标正确，不代表动作率正则坐标也正确对齐。令 `u` 为固定基础 effort/gain 动作单位，则同一物理命令差满足 `delta_a = standard_action * delta_u`；项目当前每通道惩罚相对 effort单位的系数变成 `standard_action²`。直接从[动作核对JSON](../results/b0/standard_transfer_action_audit/action_units.json)可复算：

| 通道 | 固定effort单位 | ActionMap范围尺度 | 当前动作率惩罚相对effort单位 | 同跳变惩罚弱化倍数 |
| --- | ---: | ---: | ---: | ---: |
| Piper J1 | .0291667 rad | 2.6179938 rad | .00012412 | 8,056.82 |
| Piper J2 | .025 rad | 1.5707963 rad | .00025330 | 3,947.84 |
| Piper J4 | .0375 rad | 2.3561944 rad | .00025330 | 3,947.84 |
| 单轮速度 | .5 rad/s | 6 rad/s | .00694444 | 144.00 |
| 逻辑夹口全宽 | .00333333 m | .05 m | .00444444 | 225.00 |

这些倍数是坐标推导，**不是实验测得的性能收益，也不能单独证明首步超力的唯一根因**。同一迁移平台可以登记必要动作单位，但应把物理命令、网络参数化、探索幅度、上一动作输入和奖励动作率单位逐项分开，不能让其中一项的更改隐式影响其余项目。

### 2.2 gain32不能消除这个差异

本轮 `rescale_standard_arm_jaw` 只对臂/夹口末层权重与bias除32，同时输出单位乘32。初始物理行为与既有探索尺度保持；同一未来物理动作在当前奖励中仍按固定ActionMap坐标计罚。因此gain32是优化参数化试验，没有对上述官方正则语义作修复。

下一轮若恢复固定effort单位正则，不能直接用已经乘32的 `actor.standard_action` 当奖励单位。应单独冻结奖励动作单位；否则同一物理动作又会因训练参数化不同而相差32²，破坏配对解释。

### 2.3 最小可执行验证

先用已有真实记录，将六项tracking、动作率、软限位三个部分在相同状态/动作上展开，报告原坐标与固定effort坐标的分项值及导数；这一步只是定位和版本登记。随后实际训练一对同初始化、同参考、同normalizer来源、同数据与H32预算的标准Actor：

- 对照沿用旧动作率坐标；
- 修复组仅将奖励中的当前/上一动作一致换回登记的基础effort坐标，物理执行、Actor输入与回放文件继续沿既有规范；如果决定采用其他平台归一化，必须明示理由并另命名；
- 两组共用的尾槽/基础接口修复要在启动前固定，不临时给某组追加优势；
- 保留原tracking系数、softdone、H32、网络、任务时限和6 N阈值，不引入force reward、BC或参考前馈。

同一物理前缀比较首20 ms命令跳变、首2 ms力、连续握持、全片段回报和失败时刻；训练到既定有意义节点后继续真实物理验收。只有完成这一步，才能说明单位修复对学习是否有效。

完整任务的首步另须处理无历史动作：`eval_contact_segments.continuous_initial` 使用canonical零值作为Actor历史哨兵，并明确reset前没有动作。奖励转换不能将其当成实际执行的零命令，再换算成 `(-home_action)/base_scale` 而凭空制造大跳变。保存上一动作是否有效，按固定官方reset约定定义奖励首步的上一动作；Actor历史若仍保留原哨兵，应明确与奖励坐标分开。带真实教师前缀的接触片段则始终使用实际上一条clipped命令。

## 3. WM窗口和实际学习强度

### 3.1 八行窗口和七个预测转移

官方 `WorldModelLearnerCfg.horizon=8`；其 `_rollout` 使用 `range(actions.shape[1]-1)`，对应8个状态位置、7个实际预测转移。项目H7提供8行并含真实末后继，末行动作未积分，符合固定代码的这项语义。项目增加2个H1 minibatch属于终止数据适配；不能将“40步物理cohort”称为40步或H32 WM监督，也不能将“paper k=8”的表述不加定义地覆盖实际H7实现。

本轮每个joint更新：

- H7：8批×256窗×7个转移 = 14,336个WM预测目标；
- H1：2批×256窗×1个转移 = 512个目标；
- 合计14,848个目标，17,408个采样窗口位置；
- H7每批192在线＋64离线，H1全在线：其中在线预测目标11,264、在线窗口位置13,312；其余来自教师/登记握持数据；
- Actor：256×32 = 8,192个想象步，随后20个Critic minibatch。

这些是可重复/重叠的训练使用次数，不是14,848条新增独立物理转移。

### 3.2 replay_ratio=16没有在当前接触循环中生效

官方runner以 `num_envs / (wm_batches * wm_batch * wm_horizon) * replay_ratio` 调度joint更新。接触脚本则每调用一次40步cohort，固定执行一次joint更新，未读取replay_ratio。现有128×40=5,120个模拟lane intervals/轮，尚不含每lane100个2 ms教师前缀子步；失败lane仍同步步进，不可全部算有效交互。

| 当前独立链末节点 | H32累计 | 有效在线转移 | WM预测目标累计 | 目标/有效转移 | 窗口位置/有效转移 |
| --- | ---: | ---: | ---: | ---: | ---: |
| control u50 | 50 | 69,480 | 742,400 | 10.6851 | 12.5273 |
| gain32 u200 | 200 | 345,268 | 2,969,600 | 8.6009 | 10.0838 |
| gripdata u50 | 50 | 73,163 | 742,400 | 10.1472 | 11.8967 |
| padding u50 | 50 | 82,748 | 742,400 | 8.9718 | 10.5187 |
| wmcoords u50 | 50 | 86,911 | 742,400 | 8.5421 | 10.0148 |

表中WM目标包含离线样本，分母为新增在线数据；这是训练使用强度，不能误写成纯在线 replay ratio。相对5,120个attempted intervals，两个口径固定为2.9和3.4。官方配置的16采用8行窗口口径；换成7个预测转移是14，尚需说明warmup、终止过滤等条件。**不能用本表8.6009与官方16直接相减。**续跑u10→u50、u50→u200已经包含父run，不重复累计。

下一执行轮应显式选择并记录接触数据计数与调度单位，调用或对应实现固定官方调度机制，考虑有效新转移和终止窗；每轮同时报告真实新数据、attempted物理工作量、WM样本使用、Actor/Critic步数和GPU时间。批量可适应现场显存，不能只留下一个不起作用的配置字段声称原配方已经恢复。

### 3.3 官方ReturnSampler的移植

当前每条参考约分配相同数量的lane，并在各自eligible中均匀随机；官方默认对低真实回报时间bin增加重采样，同时保留explore/keep份额。[runner 源码][O11]与[ReturnSampler 源码][O12]

分箱还存在论文与固定实现的差别：论文所述1 s时间段不能直接写成固定代码默认。固定mjlab_research的[MotionCommand源码][O14]第181行采用 `bin_count=int(total_frames//(0.2/env.step_dt))+1`，在20 ms控制率下约为每10帧一箱；固定ReturnSampler按 `frame*bin_count//frame_count` 映射全拼接timeline，并非逐reference独立的1 s bins。由于取整与额外加1，每箱不保证恰好10帧。论文口径和本次实际0.2 s左右分箱分别登记。

下一轮把官方ReturnSampler作为来源明确的采集机制适配。需要处理ragged MotionID、有效帧bin、失败lane、cohort截断及真实episode终止：当前失败lane在cohort余下时间仍积分，不能把失效后数据喂给sampler；教师前缀不计策略得分；clip_end与cohort timeout不得当成物理失败。先与原均匀采样固定其他项做有意义的实际学习比较。此机制调整使用原tracking，不需要自定义接触奖励。

具体边界限定为：保持整数frame/bin映射，给不足历史/后继的起点、无合法起点的bin显式mask后重新归一化；全局bin可跨MotionID边界，但每次抽到的真实起点及后续窗口必须留在其自身clip。排除数量和实际bin定义入结果。resume保存value/count/effort以及尚未凑齐20步的record缓冲，不能仅存cfg。采样/坐标配对沿用相同物理探索与本体噪声设置；gain32不顺带放大探索，冻结评测关闭训练统计与sampler更新。这里只处理现有collector的具体语义，不建立新测试框架。

## 4. 本轮具体修改的正确性和限制

### gain32

实现位于 `contact_training.py:154–162,177–185`。首次B0-03迁移才变换，完整resume重新装载保存过的尺度，不再次乘32；探索尺度在载入/变换前保存，因此与原物理噪声匹配。已归档9,705个真实历史的初始动作与重载比较；这不能证明优化轨迹等价，末层有效物理更新幅度就是试验的改变。

### goal_padding

`contact_policy.py:262–271,303–306` 用原始rotation6D全零哨兵识别无效槽，在官方normalizer输出后遮罩；有效rotation两列不可能全零。已登记1,350无效槽修复、96,300有效槽逐值不变。检查点须通过cfg重建hook，不能只拿state_dict当完整行为定义。

固定官方本来在单条clip末尾夹紧到最后有效参考；项目在其后自行置零。本轮修复解决了“raw零被normalizer变成116.852”的伪信号，但仍保留项目零槽策略。恢复官方尾窗夹紧只影响观测目标，**不授权延长实际任务参考、增加保持时间或跨clip取未来帧**。正式裁判时限继续固定。优先在需读到尾窗的片段做匹配检验，不将它解释成六个首步超力的原因。

此外有效新目标本身存在迁移分布偏移：参考核对中的Piper J4新目标约1.825 rad，而B0-03对应均值近0、std约1.29e-5、epsilon .01，归一化幅度可达182.26。尾槽修复没有解决这一有效目标问题。应核对目标/本体normalizer分布及latent饱和；尚不能据此断言必须重建网络或增加BC。

### wmcoords

`contact_training.py:135–151` 的首层代数正确。设旧均值/分母为 `m0,s0`，新为 `m1,s1`，则 `W1=W0*s1/s0`、`b1=b0+W0*(m1-m0)/s0` 保留归一化输入的首层预激活；context列未改。当前代码先更新bias后缩放weight，与推导一致，使用std＋epsilon的真实分母。

实测1,725个输入在零优化时，单换统计造成TCP单坐标最大偏移12.412 mm，首层变换后约0.000358 mm。Adam动量数值保留，**后续优化轨迹不等价**，不得将wmcoords结果视为纯粹无效果的坐标替换。WM转移的统计分布和参数来源必须共同冻结；若改变优化器处理方式，另列配置与配对预算。

### gripdata和验证隔离

训练脚本核对预登记train种子71200–71207，再构造ContactWindows；该类拒收validation。H7原64离线改32原教师＋32握持挑战，Actor初始状态和参考没有增加标签监督。额外数据来自既有策略行为，应保留behavior lineage；“无额外动作BC”不等于“无教师/混合策略产生的WM数据”。

验证collector使用training=False，禁止normalizer更新与replay写入；载入checkpoint后只采真实控制数据，评分使用相同open-loop动作窗。新增侧别读取从路径对应metadata取得，正确支持六条参考，不再错误把motion索引直接当pull/push二值。

## 5. 结果解读和下一执行轮优先级

同一双指窗口的H32 TCP P95：held_r2为50.53/40.36 mm，wmcoords-u50为100.66/82.60 mm，gain32-u200为551.98/278.53 mm；常速对照为13.95/11.86 mm。这是同记录动作的开环预测误差，不是闭环策略成功率。冻结control-u10采出的自由运动背推H32仅3条lane、27个重叠窗，不能代表背推整体模型质量。详见[本轮审查](../reports/B0_STANDARD_ROUND_REVIEW_20261123.md)。

[同起点动作扫描](../results/b0/standard_handoff_20261123/gain200_entry.json)证明标准Actor出现真实跟踪方向改善：前拉首20 ms successor tracking从.05278到.09080，背推从.05609到.08287；对应u200首2 ms力仍30.64/51.98 N，超过原6 N。**.09080/.1不是整回合normalized return**；动作扫描在首步已违反裁判后仍积分足20 ms作诊断，不是成功回合。

下一执行轮建议按以下顺序落实，完成实际学习与验收，不再只增加静态核查材料：

1. 冻结可比较的独立标准基线身份与论文式/任务式两套指标；已有五条seed0链保持历史身份，旧R/J继续旁列。
2. 以动作率单位语义为第一项最小配对修复。保留B0-03和held_r2来源，或明确说明为何选择某个完整状态作暖启动；同一对照两组必须来源一致，勿直接把失败u200认作已成功标准底座。
3. 同步给训练循环增加必要的分项得分与实际预算记录；这些是观测，不改变学习目标。仅在读取尾段目标时落实官方夹紧/已登记零槽的必要对照。
4. 再恢复固定官方ReturnSampler与有明确分母的学习强度；按已证WM接触遗忘情况安排同split、同预算的真实数据覆盖和normalizer处理。WM预热若使用，冻结Actor并单列全部更新数；不能把预热包装成joint训练，也不默认叠加H32监督或自研力损失。
5. 每个有意义节点实际计分十项接触与连续任务；先完成同一标准候选的既定出口，再做独立seed1/2和冻结H。若仍失败，继续交付受限标准结果与证据，不替换为BC/解析成绩，也不自动推进VLA。

代码和现存证据支持以上问题定位；哪个改动能使完整接触成功仍需下一轮实验。保持完整分母、失败、同包身份和实际训练预算，才能让这个单独迁移结果成为后续方法对比的可信基线。

[O1]: https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/models.py
[O2]: https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/representations.py
[O3]: https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/utils/gencoord_helpers.py
[O4]: https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/utils/tracking_reward.py
[O5]: https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/learners/wm_learner.py
[O6]: https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/learners/policy_learner.py
[O7]: https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/learners/learner_utils.py
[O8]: https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/envs/world_model_env.py
[O9]: https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/envs/multi_task_world_model_env.py
[O10]: https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/replay_buffer.py
[O11]: https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/runners/supermimic_runner.py
[O12]: https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/runners/reset_sampling.py
[O13]: https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/tasks/task_spec.py
[O14]: https://github.com/HybridRobotics/mjlab_research/blob/dd51a9fcc98791a2f0b018b3c7f71a3eefd5ecdd/src/mjlab/tasks/tracking/mdp/commands.py

