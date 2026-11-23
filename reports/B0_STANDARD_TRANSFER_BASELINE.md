# SuperMimic 标准迁移独立结果：M1＋Piper H

## 11 月 24 日标准接触迁移

固定 effort 与 canonical 的 seed0 配对已实际完成 u50。每支训练 50 H32、500 WM 和 1,000 Critic，Warp 正式接触均为 0/10。两个 run 的 u0/1/5/10/50 共 100 个正式片段结果已回收。相同基础 effort 评分下，u50 十片段等权均值为 canonical −0.03413、effort −0.04738。完整双侧任务回报仍为 NA，最终候选为空。

相同物理记录的六个 tracking 分项与限位一致，Piper J2 的同位移罚比为 3947.84。u50 背推稳定握持的首步门力在固定 effort 分支为 22.20 N；仅额外接入官方 ReturnSampler 后为 6.697 N，仍超出 6 N。ReturnSampler、Ratio 和尾帧三组均已实训到 u50，各 0/10。详见[逐案实测](../results/b0/pair_units_v1/nominal_segments.csv)、[奖励复算](../results/b0/pair_units_v1/measured.json)和[采样调度账本](../results/b0/pair_sampling_audit_v1/completed_training.json)。配对 u200、补接触数据和统计处理的实验另行回收。

## 11 月 23 日历史快照

结果快照：`b0-standard-s0-638fddc`。日期：2026-11-23，北京时间。实验截止提交：[638fddc](https://github.com/kaiwen123-yang/dog-and-arm/commit/638fddcb2f025006595f79f27a977a8fba41cbc2)。

**状态：标准迁移进行中，B0-04 接触尚未通过；这是一份独立、可追溯的中间结果，不是已达论文指标的最终基线。** 用户要求先详细研究已开源的 SuperMimic，迁移结果达到或接近论文指标后单独保留，供后续方法比较。本文件是该结果的固定入口；每轮以新提交保留快照，最终冻结三 seed 的唯一候选及协议后再标为正式基线。当前没有合格的最终 checkpoint。

目标方法 ID 为 `SuperMimic-M1Piper-standard-v1`，完整指标定义见 [论文对照协议](../docs/B0_PAPER_BASELINE_PROTOCOL.md)。原始实验报告、逐案结果不覆盖：[本轮完整审查](B0_STANDARD_ROUND_REVIEW_20261123.md)、[原执行报告](B0_STANDARD_TRANSFER_RESULTS.md)、[机器可读结果清单](../results/b0/standard_baseline_20261123/baseline_manifest.json)。

## 1. 方法身份与成本来源

| 项目 | 当前实际记录 |
| --- | --- |
| 平台 | M1 四轮轮足＋Piper H＋双指夹爪，被动铰链门；front60_v2；当前只有仿真结果 |
| 官方来源 | SuperMimic `abc124c1bd5976341034668af3d12c087f2f1f55`；mjlab_research `dd51a9fcc98791a2f0b018b3c7f71a3eefd5ecdd` |
| 标准核心 | EffortScaledActor / MultiEncoderAE、GenCoord、原 tracking / softdone、H32 Actor–Critic；Actor 反传时冻结 WM 参数并保留导数 |
| 额外控制与监督 | 本轮五条链额外动作 BC 为 0，无参考臂/夹口动作直通、无解析站位补偿、无新增任务 reward/风险头 |
| Actor 继承 | B0-03 `free_s0_cloud_servo_r2/checkpoint_001000.pt`；1,000 H32、10,000 WM、20,000 Critic、1,088,000 有效在线转移 |
| 门 WM 继承 | `contact_s0_wm_held_r2/wm_002000.pt`；2,000 教师 minibatch；不是零成本初始化 |
| 接触初始化 | 新门 Critic 第一层重新初始化，兼容层迁移；新链从 seed0 建立优化器、RNG 和 replay；续训目录恢复完整 cohort_state |
| 当前训练规模 | 128 lanes×40 个 20 ms；Actor/WM batch256；每轮 8 个 H7＋2 个 H1 WM minibatch、1 次 H32、20 个 Critic minibatch |
| 物理与计算 | AutoDL RTX PRO 6000、Warp 3.16 主后端；原 native3.3 独立评分；20 ms 由10×2 ms组成 |
| 仍需对齐的实现 | action-rate 的动作坐标、ReturnSampler、实际 replay 调度、参考尾帧规则；详见[官方实现审查](../docs/B0_OFFICIAL_IMPLEMENTATION_AUDIT_20261123.md) |

保留核心并不代表已经完整复现论文配方。当前官方动作正则经过平台动作坐标后物理权重变化，接触采集尚未调用官方 ReturnSampler，YAML 中 replay_ratio=16 没有实际驱动固定 cohort 调度。它们是本次已查明的适配差异；下一轮分别对齐并记录协议版本，不追溯性修改本页历史成绩。

## 2. 最新标准迁移的实际成绩

下表是五条配对配置链的最终节点，全部为 seed0。更新和转移是该条接触链累计，未把继承无接触/门 WM 成本混入；这些继承成本见上表。完整恢复目录均以 `results/b0/` 为前缀。

| 配置链与 checkpoint | 接触 H32 | 有效在线转移 | Warp 正式接触 | native 正式接触 |
| --- | ---: | ---: | --- | --- |
| `standard_s0_control40_to50_r1/checkpoint_000050.pt` | 50 | 69,480 | 0/10 | 未执行 |
| `standard_s0_gain32_to200_r1/checkpoint_000200.pt` | 200 | 345,268 | 0/10 | 0/10 |
| `standard_s0_gripdata_r1/checkpoint_000050.pt` | 50 | 73,163 | 0/10 | 未执行 |
| `standard_s0_padding_r1/checkpoint_000050.pt` | 50 | 82,748 | 0/10 | 未执行 |
| `standard_s0_wmcoords_r1/checkpoint_000050.pt` | 50 | 86,911 | 0/10 | 未执行 |

正式十项是既有五个 v1＋五个 hold-margin v2，不混成重新放宽的统一裁判。gain32-u50 另有原 v1 native 0/10，其中仅五项属于正式组合，另五项正式 hold-margin 未评；不写成该节点正式 0/10，也不用 u200 填补。

本轮 415 条原始 nominal 记录来自 55 个评测 run，全部失败；其中 275 条正式组合记录、140 条额外 v1 对照。27 套完整 checkpoint×backend 十项加一套仅五项。303 条在首个2 ms发生门受力超限。它们有相同任务、不同节点和版本的重复，不是415个独立泛化试验。[逐案索引](../results/b0/standard_handoff_20261123/case_index.csv)

去除两个续训目录的前缀重复后，五条配置共新增 **400 H32、4,000 WM、8,000 Critic、657,570 有效转移、2,048,000 模拟 lane 控制区间**。该总数仅用于本轮探索成本，不代表一个模型的学习量，不代表五个独立 seed。

## 3. 对照论文的结果表：哪些已测，哪些仍缺

| 结果维度 | 论文参照或本项目目标 | 当前结果 | 判定 |
| --- | --- | --- | --- |
| 完整回合归一化 tracking | 论文 BONES-SEED 的 SONIC 参考线0.90；本项目目标≥0.90，预登记接近数值带≥0.88 | NA：尚无本协议完整实测回报 | 不能判断数值距离，不能用单步/想象 reward 代填 |
| 状态 WM 预测误差 | 论文图3(c) 0.007–0.011；需匹配状态、nominal error、时域和平均方式 | 尚未形成可比的独立表 | 不能把 H32 TCP 毫米值与它相减 |
| 接触 nominal | 同一标准候选10/10 | 最终各组0/10；gain200双端均0/10 | 十项均仍未过 |
| 接触开发 D | 每项≥18/20 | 未执行 | 不是0/20 |
| 完整前拉/背推 | 同包从头连续执行，Warp nominal及C每侧≥18/20，native双侧nominal | 标准本轮未执行 | 不能继承R/J混合策略成绩 |
| 独立seed1/2与保留H | 三条独立训练链，冻结后每seed/侧H≥40/50 | 未执行，H未打开 | 未形成多seed最终基线 |
| 数据/计算效率 | 到同一目标的转移数、imagined steps、总训练GPU-hours | 当前有更新和转移；可靠完整GPU小时账本NA | 不宣称复现3小时或>1000倍加速 |

0.88 是本项目为后续实验事先规定的绝对0.02容差，不是论文作者定义；数值带只描述迁移任务的回报，并且必须同时满足原物理门槛。论文的25/129,514和0/129,514来自G1训练动作覆盖，不能由几条门任务分数推出相同失败率。论文原数据与硬件信息见[原文v3](https://arxiv.org/pdf/2610.28480v3)与[作者说明](https://supermimic.github.io/)。

## 4. 世界模型和真实接触的解释证据

双指接触起点、相同真实记录动作开环H32预测的TCP P95如下，单位mm；前拉412窗来自51 lanes，背推450窗来自56 lanes，窗口相互重叠。

| 预测器 | 前拉 | 背推 |
| --- | ---: | ---: |
| 常速外推 | 13.95 | 11.86 |
| held_r2初始WM | 50.53 | 40.36 |
| control-u50 | 688.06 | 166.67 |
| gripdata-u50 | 106.62 | 145.39 |
| wmcoords-u50 | 100.66 | 82.60 |
| gain32-u200 | 551.98 | 278.53 |

补握持数据、输入坐标变换缓解了部分退化，但仍未达到该验证集上的简单外推或初始WM精度；不能将此表解读为Actor–WM闭环梯度已可靠。独立标准策略验证集的背推只有27窗/3 lanes，覆盖另有不足。详细全部节点及文件见[本轮审查§6](B0_STANDARD_ROUND_REVIEW_20261123.md#6-wm-的自由运动改善和抓持退化必须分开报告)。

同一抓持起点，gain200前拉真实20 ms后继tracking由0.05278提高至0.09080，背推由0.05609提高至0.08287；首2 ms门力却为30.64/51.98 N，均超过6 N。该诊断在失败后继续积分到20 ms，所以这些值不能计为合格评测回报，更不是论文式完整0.908回报。[原始诊断](../results/b0/standard_handoff_20261123/gain200_entry.json)

## 5. 与其他已有结果的分工

P6工程教师、旧接触ReferenceResidualActor、540参考前馈＋累计15,000动作BC、546额外解析补偿仍单独保留。546-u1的三后端双侧nominal和Warp C各9/20是有效混合能力证据；它们不能并入本页标准方法结果，也不能把三个后端当三个训练seed。

后续方法应复用本页最终冻结的物理任务、数据资格、case身份、评分代码和选模规则，报告同seed/同case配对差值，同时说明新增视觉、教师数据、BC、解析控制和计算预算。当前快照保留为未完成迁移的中间对照；正式成功基线尚待训练和验证。

下一实际执行顺序见[标准迁移计划](../docs/B0_STANDARD_TRANSFER_PLAN_20261123.md)，完整启动词见[B0_START.txt](../prompts/B0_START.txt)。本次研究与文档发布没有新训练、新物理评测或硬件动作。
