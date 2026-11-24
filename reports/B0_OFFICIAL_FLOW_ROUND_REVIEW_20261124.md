# official_flow_s0_v1：u1000 实验审查与下一段决定

审查日期：2026-11-24，北京时间。证据固定于 [51a0133802983b65602949000099e7d18fa8e835](https://github.com/kaiwen123-yang/dog-and-arm/commit/51a0133802983b65602949000099e7d18fa8e835)。本次做源码对照、已提交结果复算和下一计划发布；新增训练、仿真、优化器更新、现场权重重载均为零。AutoDL 大数组和完整权重未在本次重新读取，不声称读取了不可访问的其他会话或所有远端字节。

**结论：官方在线学习主环已真实运行到 1,000 次 Actor 更新；标准任务尚未学会。下一轮从 u1000 完整恢复同一主链，先累计到 u3000，有真实物理依据再至 u5000。** 当前 B0-04、最终候选 null、合格完整双侧物理归一化回报 NA，V0 完整成功视频仍为零。此次不以失败为由重新随机初始化，不增加 WM 误差放行阶段。

[原实验报告](B0_OFFICIAL_FLOW_RESULTS_20261124.md) · [原 manifest](../results/b0/standard_official_flow_20261124/baseline_manifest.json) · [逐案与预算复算](../results/b0/official_flow_review_20261124/evidence_audit.json) · [源码审查](../results/b0/official_flow_review_20261124/wm_code_audit.json) · [下一执行计划](../docs/B0_OFFICIAL_FLOW_CONTINUATION_PLAN_20261124.md)

## 1. 这次已经做到了什么

实际入口是项目的 M1/Piper 环境适配器与固定官方学习器，真实调用链为：采集当前策略物理转移、保存 replay、更新 WM/Actor 统计、按有效样本 Ratio 调度、十批 H7 WM、一次 H32 Actor 和二十批 Critic。首更新发生于第 19 个采集 tick，已有 22,678 个有效转移；十个 WM 批、Actor 与 Critic 的索引和优化步骤都有实测回执。新链使用 4096 环境、WM batch 2048、Actor batch 4096。

逐行检查 1,000 条更新日志，得到以下守恒关系。collection.jsonl 只有抽样记录的 1,192 行，不是全部 2,772 拍，不能直接逐行相加当总预算。

| 本轮实际量 | 复算结果 |
| --- | ---: |
| H32 Actor / H7 WM / Critic 优化步 | 1,000 / 10,000 / 20,000 |
| 有效策略转移 | 10,255,490 |
| 真实前缀区间 | 1,098,622 |
| 全部训练物理区间 | 11,354,112，等于前两项之和 |
| 0.25 ms 物理微步 | 908,328,960 |
| WM 窗口 / 被评分后继 | 20,480,000 / 143,360,000 |
| Actor 想象步 | 131,072,000 |
| 完整数值有效的 terminal 区间 | 99,507 |
| 直接继承的 WM 祖先 minibatch | 14,850，独立于本轮新增 10,000 |

来源：[updates.jsonl](../results/b0/standard_official_flow_20261124/updates.jsonl)、[coverage](../results/b0/standard_official_flow_20261124/coverage_u001000.json)、[首更新](../results/b0/standard_official_flow_20261124/first_update.json)、[manifest](../results/b0/standard_official_flow_20261124/baseline_manifest.json)。首批 Actor 起点包含 1,483/4,096 条完整 terminal 行；当前代码始终积分完整 80 微步，再将物理首次失败与数值区间有效性分开处理。没有证据支持“失败样本全部被删除”这个解释。

末点 Ratio pending=0，上一记账时钟为 10,250,240；当前已越过该时钟 5,250 个有效转移，距下一个 10,240 阈值尚差 4,990。恢复时以完整包为准，不能清零时钟再重算额度。[恢复回执](../results/b0/standard_official_flow_20261124/restored_u001000.json)

## 2. 任务能力：有驶近和停车进展，接触与完整成功仍为零

复核了 134 份原 result、配套 return、逐案表及完整回报分母，未发现逐案汇总不一致。必须分别报告两类分母：

| 实际评测 | 数量与结果 | 可以说明什么 |
| --- | --- | --- |
| 接触名义片段 | 110 案，Warp 80 / native 30；0 通过、0 接触阶段事件；60 案首个 2 ms 超 6 N | 同一标准 Actor 尚未通过原十项 |
| frame0 完整任务开发尝试 | 24 案、0 完整成功；15 个驶近事件、11 个停车事件 | 最远完成前两个阶段，尚未完成预抓取；不能写成整轮零事件 |
| 新 Actor 的原无接触任务 | u0/u200/u500/u1000，各 60 案，共 0/240 | 全部跑完 7 s，全部因 TCP 精度不达标；另 81 案同时不达根位置要求 |
| V0 完整成功视频 | 0 | 失败视频或拼接片段不能补足 |

240 个无接触案例的 solver_first_failure 均为空，不等于“全部摔倒或跑不完”。u1000 支撑／运动臂／驻车 TCP RMSE 中位数分别为 77.17/72.31/82.04 mm。旧 B0-03 的通过记录保持，但新初始化 Actor 不能继承其验收资格。[无接触逐案](../results/b0/standard_official_flow_20261124/free) · [逐案汇总](../results/b0/standard_official_flow_20261124/physical_cases.csv)

u200、u500 的两侧、两后端均完成驶近和停车；u1000 的 Warp 则退回停车阶段失败。原十项首 2 ms 超力数从每组 6 降到 3，也没有变成握持通过：前拉三案改为 Warp 10 ms / native 16 ms 的握持几何失败，背推三案仍在首微步约 33.1 N 超力。

| u1000 完整任务 | 真实完成 | 首次失败 |
| --- | --- | --- |
| Warp 前拉 | 驶近 | 11.744 s，停车超时；工位 XY 误差 35.291 mm |
| Warp 背推 | 驶近 | 11.224 s，停车时夹指碰到把手非抓取部位；XY 20.075 mm |
| native 前拉 | 驶近、停车 | 9.596 s，预抓取工位约束失败；XY 18.803 mm |
| native 背推 | 驶近、停车 | 9.174 s，预抓取工位约束失败；XY 20.009 mm |

native 前拉的 XY 尚小于 20 mm；由现有裁判分支可推断航向超过 2°，但紧凑表没有保存确切航向原值，本次不填写未经测量的角度。24 次完整尝试的最大末门角约 0.0000417°，尚无有意义的开门进展。[完整时钟表](../results/b0/standard_official_flow_20261124/full_clocks.csv) · [完整任务清单](../results/b0/standard_official_flow_20261124/video_manifest.json)

这 24 案复用训练时已给定的两条完整参考，属于开发评测。前拉 75.736 s、背推 56.056 s 的整段分母保持；存续前缀的局部高 tracking、失败吸收分或更长失败时间都不等于任务完成度，也不能拿来减去 0.88/0.90。

## 3. 同链继续有依据，不能把 u1000 当成官方收敛上限

同一真实握持验证起点的 J2 首命令持续变化，不是只在日志中得到更高想象回报。

| 节点 | 前拉 J2 首命令，rad | 背推 J2 首命令，rad | 背推距非饱和区 / 采集 σ |
| ---: | ---: | ---: | ---: |
| u0 | 0.80839 | 0.81404 | 194.91 |
| u200 | 1.00041 | 0.89030 | 164.41 |
| u500 | 1.17914 | 0.96770 | 133.45 |
| u1000 | 1.49640 | 1.14450 | 62.73 |

在线带噪 J2 命令上端也从 u200 的 1.00795、u500 的 1.19302 增至 u1000 的 1.52572 rad。[首解记录](../results/b0/standard_official_flow_20261124/servo) · [分节点覆盖](../results/b0/standard_official_flow_20261124/coverage_u001000.json)

限制同样明确：参考命令上端为 2.59618 rad，上端缺口 1.07046 rad，占参考跨度 59.60%；实际 q 曾达到该姿态，不等于策略已能输出保持它的动作。夹口命令仅覆盖 30.34–47.83 mm，参考为 10–90 mm。u1000 握持首拍 J2 仍两侧饱和，前拉／背推未裁矩 -390.29/-89.89 Nm，实际均为 -35 Nm。夹指未裁力 20.10/12.53 N，实际上限 10 N。命令改善与真实接触能力应分别判断。

固定官方 runner 的 max_iterations 默认 1,000,000，是外层采集循环次数，既不是本项目的 Actor update 数，也不是应该照搬的训练承诺。此次 u1000 是项目登记段的终点，不能据此宣布官方算法已训练到收敛、迁移方法无效或必须重启。[官方 runner](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/runners/supermimic_runner.py)

基于这些实际趋势，下一段先同链到 u3000，而不是重新开始一条观测或 WM 初始化不同的链。u3000 后是否再至 u5000，依据新的阶段／接触进展，或严格同钟的双侧物理跟踪改善与整段行为检查；不能仅靠命令更近、WM loss 更低或失败更晚延长。

## 4. WM 退化需要拆解，不能重新变成 Actor 放行门

旧独立双指集的四项 H32 TCP P95，从 u0 的 20.7/14.5/21.9/18.5 mm，到 u1 的 498.6/815.7/668.8/704.6 mm，u1000 为 597.5/859.7/892.4/861.7 mm。该退化真实存在；这些是固定旧开发分布上的指标，不能直接当成当前所有在线状态的误差。[WM 分节点](../results/b0/standard_official_flow_20261124/wm_nodes.csv)

目前没有分离首 19 拍在线统计更新与十批 H7 权重更新的影响。下一轮在冻结 u0/u1 上做权重×统计四格前向诊断：u0/u0、u0/u1、u1/u0、u1/u1。只交换 WM 的 state_normalizer 与 action_normalizer 完整 buffer，保持物理 action scale/offset、75 维表示、context、积分器和 FK；不改 Actor 统计。stats1 是累计 22,678 行后 count=73,157 的统计，不是第一拍的统计。

混配模型没有实际接受对应训练，权重与统计也有交互。四格只用于判断条件敏感性和下一项应查的位置，不当作两个可相加的独立因果效应，不把混配包直接选成候选。原官方在线统计继续更新。需要确认当前分布时，另作有界、独立的冻结策略开发采集，不能拿训练 replay 当独立验证，也不能又加一千批预适配才准 Actor 更新。

## 5. 已排除的解释、仍有差异的地方

| 项目 | 本次确认 | 下一段处置 |
| --- | --- | --- |
| 首次失败数据 | 完整数值有效的 terminal 状态/动作起点已进入 replay/Actor | 不再以此为假定 bug 重写采样 |
| 基础 effort 输出 | 无界 decoder 先做物理映射，再按实际边界夹取 | 不把 J2 覆盖窄当成 ±1 结构上限，不改 gain |
| 连续轮限位 | 实际模型为 ±99,999 rad，并非 [0,0] | 不凭猜测取消限位罚 |
| 参考覆盖 | 八参考、十三相位均有实采；两条完整参考贡献 3,621,747 条有效记录 | 不再用旧 B0-03 小姿态范围解释本轮全部数据 |
| 实际接触分布 | open/hold 参考时钟样本 17,887，占 0.1744%；它不是物理接触证明 | 另报原裁判前的真实持续双指 |
| 参考／实际阶段 | u200/u500 的八个完整案例均在同钟 pregrasp 失败；u1000 Warp 是事件落后 | 不平移或暂停参考时钟掩盖落后 |
| 训练／正式裁判 | 训练用参考 phase 和逐 lane 物理终止；正式另有 station XY/heading 与独立事件判定 | 如实登记任务适配差异，不自动增加新奖励或课程 |
| Warp 数值警告 | 134 条保存轨迹有限，96 条 Warp 容量位为零；警告出处未定位 | 捕获原 warning 位置与调用栈；不能追认其必然无害 |

依据：[源码审查](../results/b0/official_flow_review_20261124/wm_code_audit.json)、[物理审查](../results/b0/official_flow_review_20261124/physics_code_audit.json)、[数值回查](../results/b0/standard_official_flow_20261124/physical_trace_recheck.json)。现有完整 qpos/qvel/raw action 记录是 20 ms，2 ms 事件表不含全部 q/v/heading。先定位有物理意义的 20 ms 分歧区间，再补必要 2 ms 原值；float32 Warp 与 float64 native 的首个非零差不等于接口错误。

## 6. “按官方流程”应怎样准确表述

本轮已证实主要在线调度和学习步骤落实；这不等于逐字使用官方机器人环境，也不等于达到论文结果。方法仍是固定官方核心加明确的平台映射，并使用有祖先成本的 WM-only warm-start。

官方同时支持 rep_state 与 proprio；固定 runner 的默认是 rep_state/history1，本项目和既有 O1 选择的是 proprio/history10。此为明确配置选择，不是遗漏输入的已证 bug。即使切到官方 rep_state，Actor 目标仍为 540 维，30 列参考相对平移仍只在 WM/Critic 的 570 维目标内。rep58 可以直接提供高度/根线速度，但不含 base XY；不能声称换模式会自动解决停车，也不能悄悄给 Actor 75 维含门几何状态或 570 维目标。[官方表示](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/representations.py) · [官方 motion task](https://github.com/HybridRobotics/supermimic/blob/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/tasks/task_spec.py)

官方 G1 资产采用 0.9 的 soft joint range 因子，项目当前罚项边界直接取 M1/Piper 编译 joint range；这是应披露的资产映射差异，尚未证实为本轮失败原因。下一段保持相同范围，不在续训时混入额外调参。完整优化器/replay/solver/RNG 恢复也是项目运行保障扩展，不能称为固定官方 runner 原生恢复功能。[官方与平台映射清单](../docs/B0_OFFICIAL_FLOW_ALIGNMENT_20261124.md)

## 7. 与最终目标的距离

当前已经完成环境、参考、真实采集、模型和 Actor/Critic 主环的运行与计数验证，并出现完整任务前两个阶段的真实成功。尚未建立原门槛内的持续抓持，尚未完成预抓取，更未完成开门、保持、释放、撤臂及离开整段任务。不能用“已做十三阶段中的两个”计算项目完成百分比。

需要继续取得：同一候选原接触十项、每项 D≥18/20、双侧 frame0 完整 Warp 与 C 每侧≥18/20、同包 native3.3 双侧完整名义、新链无接触资格、独立 seed1/2、三 seed 冻结后每 seed/侧 H≥40/50、合格完整回报和 V0 视频。当前 D、C、独立 seed 和 H 均未开启。0.90 是论文 SONIC 参照，0.88 是项目预登记接近带；跨机器人任务有比较限制，现阶段差值仍为 NA。[正式协议](../docs/B0_PAPER_BASELINE_PROTOCOL.md) · [目标差距](../docs/GOAL_GAP_20261124.md)

下一轮把主预算用于真实连续学习，同时有限核查后端首分歧、统计/权重影响与当前分布，按固定节点评测并交付。首次一侧完整成功就立即出原速连续视频，后续资格在同轮继续；不以诊断报告代替可执行训练，也不预先承诺下一轮一定成功。
