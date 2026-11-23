# M1＋Piper H 标准 SuperMimic 接触迁移实测

> 本轮已于2026-11-23 22:50:39北京时间回收，实验端点638fddc。下文“运行中/待回收”是执行时原始记录。最终独立成绩见[B0_STANDARD_TRANSFER_BASELINE.md](B0_STANDARD_TRANSFER_BASELINE.md)，全部分母和后回收WM结果见[最新审查](B0_STANDARD_ROUND_REVIEW_20261123.md)，下一步以[标准计划](../docs/B0_STANDARD_TRANSFER_PLAN_20261123.md)为准。原实验正文保留。

2026-11-23，北京时间。承接 main@5e6db44。当前在 B0-04 双侧接触阶段。原尺度、六臂/夹口 ×32、补充握持 WM 数据三组在 u50 均实际完成 Warp 接触名义计分，三组分别为 0/10。后三者分别保持各自权重。当前尚无可以推进 B0-05 完整单门的标准候选。运行中的末节点与机器回收结果见本报告后续回收段、[快照](../results/b0/standard_handoff_20261123/snapshot.json)及[逐案索引](../results/b0/standard_handoff_20261123/case_index.csv)。

## 恢复的官方机制与实际配置

| 项目 | 本次实际调用与证据 |
| --- | --- |
| 来源与物理 | SuperMimic abc124c1bd5976341034668af3d12c087f2f1f55，mjlab_research dd51a9fcc98791a2f0b018b3c7f71a3eefd5ecdd。AutoDL RTX PRO 6000，MuJoCo-Warp 3.16；独立 native MuJoCo 3.3.0。每个目标在物理后端持有 10×2 ms。 |
| Actor | B0-03 free_s0_cloud_servo_r2/checkpoint_001000.pt 的 EffortScaledActor，严格载入含统计的 state_dict。官方 MultiEncoderAE；77 维本体、10 帧历史，motion goal 540，velocity slot 占比 0。继承无接触 H32 1,000、WM 10,000、Critic 20,000、在线转移 1,088,000。此次所有 S 配置的额外动作 BC 为 0。 |
| WM | contact_s0_wm_held_r2/wm_002000.pt 的完整门 WM，继承 2,000 次教师 minibatch。75 维表示、23 路 post-clamp 动作、5 维仿真上下文和 GenCoord 积分，状态/物理动作统计各继承 10,808 个样本。 |
| Critic 和学习 | 新门输入第一层重新初始化，兼容隐藏及输出层沿用。新迁移优化器、RNG 和在线 replay 从 seed0 建立。H32 调用固定 ActorCriticPolicyLearner，Actor 更新时冻结 WM 参数，保留动作和状态导数；使用原 tracking、根高/倾斜软终止、可微 bootstrap 与 GAE。每轮 10 WM、1 Actor、20 Critic 更新，单步回报上界 0.1，价值上界约 10。 |
| 数据和时钟 | 6 条成功接触训练参考、另 4 条教师回合、在线 128 lanes×40 个 20 ms，Actor/WM batch 各 256。WM 每轮 2 个 H1、8 个 H7 minibatch。教师在 RSI 前缀重建物理历史；正式片段只在规定起点前重建，评分全程由冻结策略控制。 |
| 节点 | u0/1/5/10/50 分别保存，×32 从完整 u50 状态另起 run 向 u200 接续；包含 Actor/WM/Critic、统计、优化器、RNG 与 replay。训练证据见各 run 的 actual_config.json、updates.jsonl、outcome.json。大权重与逐步数组保存在云端原路径。 |

原先 contact_s0_tracking_r3 的接触 u1000、572,118 条有效转移及 v1 Warp/native 各 0/10 保留在原报告；本轮从 B0-03 和 held_r2 双锚点重新移入接触。540 参考前馈/BC 对照在原接触监督包两端十项每项 20/20；对应全程 R 包继承五段共 15,000 BC，tracking-u1 Warp 双侧 nominal、C 前拉/背推 9/20、9/20，native nominal 0/2。546 J 在相同 BC 链上加解析补偿，u1 同包三端双侧 nominal，Warp C 9/20、9/20，native C 9/20、10/20；u0 已具该名义能力。详情见[历史审查](B0_RECOVERY_REVIEW_20261123.md)。

## 已定位的问题与配对结果

- **动作映射与首步受力。** 对 9,759 个教师 20 ms 目标、97,590 个 2 ms 子步核对 12 腿 rad、4 轮 rad/s、6 臂 rad、1 路夹口全宽 m 的顺序、offset、scale、双指开度及单电机 0.5 倍映射。未检出命令裁剪。六臂教师最大偏移为原网络尺度的 29.26–71.85 倍；保持探索幅度（臂 0.0025–0.005 rad、夹口 0.333 mm），只将末层臂/夹口行除 32、解码单位乘 32。在 9,705 个真实十帧历史上初始动作和严格重载后输出最大差为 0。此项属于优化尺度比较。[动作依据](../results/b0/standard_transfer_action_audit/action_units.json)
- **实际物理限制。** 原尺度与 ×32 第 1 队列同为 1,725 条有效转移。在第 50 队列，两组分别有 937 和 1,713 条有效转移；有效控制区间内计到首失败子步，J2 接近力限（≥98%）分别 3,630/8,582 和 1,364/16,522；23 路命令均无裁剪。后续状态分布已分开。×32-u50 的前拉接近走到 2,683 子步耗尽参考，末端 TCP 仍距把手 307.7 mm，抓持入口首个 2 ms 前拉约 50.87 N、背推约 33.32 N，均超过 6 N。该包 native 原 v1 也为 0/10。[在线动作统计](../results/b0/standard_transfer_action_audit/online_cohorts.json)
- **参考、前动作与后继。** 20 个回合中的 13,640 条训练、13,541 条验证完整转移核对通过，末个 2 ms 对应下一状态、前动作对应前一 clipped 命令，六条参考保留独立 MotionID 和长度。十个起点用批内 Warp 与正式逐侧 Warp 做同前缀对照。六个抓持/开角入口在固定裁判下首步越限，连续采集的教师源 phase 仍有 3 个子步处于 grasp。两侧相同动作首子步实测力差最大约 0.0135 N；保存两种时钟与失败原因。[参考记录](../results/b0/standard_transfer_interface_r1/reference_boundaries.json) · [物理前缀](../results/b0/standard_transfer_interface_r1/matched_warp_prefix.json)
- **参考尾部的非零伪信号。** 原先在 raw goal 将无效未来槽置 0，经过继承的 motion normalizer 后，最大绝对值达到 116.852。修复仅在标准 motion encoder 的归一化输出上遮掉无效槽，覆盖全部 1,350 个无效槽；96,300 个有效槽逐值相同，同样本统计更新逐值相同。control u1–10 的 17,736 条有效输入中仅 24 条有尾槽，原 r3 十个失败入口均具完整前瞻。因此该缺陷无法解释首步超力。padding 组独立配同预算计分。[修复复测](../results/b0/standard_transfer_interface_r1/goal_padding_regression.json)
- **验证覆盖与 WM 遗忘。** 冻结 control-u10 另采独立 seed 81101–81103，192 lanes、2,321 条有效转移、142 次物理终止，有连续 H32 的 50 lanes 共 450 窗，其中背推仅 3 lanes 的 27 窗。采集禁止更新 normalizer 和追加 replay。再复用独立抓持挑战 3 cohorts、4,761 条转移，双指起始 H32 前拉 412 窗/51 lanes，背推 450 窗/56 lanes。控制组对自己的自由运动预测改善，抓持精度却恶化。下表为相同双指 H32 窗的 TCP P95，单位 mm，均按记录命令开环预测。[H1/H7/H32 原表索引及对照](../results/b0/standard_transfer_wm_validation_control10_r1/h32_comparison.csv)

| 抓持挑战，同窗预测器 | 前拉 | 背推 |
| --- | ---: | ---: |
| 保持当前状态 | 15.64 | 15.26 |
| 常速外推 | 13.95 | 11.86 |
| 载入 held_r2 | 50.53 | 40.36 |
| 原尺度 u50 | 688.06 | 166.67 |
| ×32 u50 | 467.18 | 271.87 |
| 补握持物理数据 u50 | 106.62 | 145.39 |

补数据只用已登记训练种子 71200–71207 的 512 lanes，14,396 条完整转移及 11,644 个 H7 窗；原 H7 每批 192 在线＋64 教师，改为 192 在线＋32 原教师＋32 抓持挑战。只向 WM 提供真实 s/a/s_next，Actor 仍由同一起点、同参考和官方 H32 学习。验证集、校准集均未进入优化。自由运动 H32 TCP P95 的前拉/背推从同预算 54.88/257.80 mm 降至 36.92/235.92 mm，但背推仅 27 个重叠窗。物理接触仍未过。

保持 held_r2 的 MLP，仅替换为 control-u10 输入统计，抓持 TCP P95 变为 464.67/544.43 mm；反向替换为 358.03/130.48 mm。另设 wmcoords 配对组，保留全部真实统计更新，将 75 状态、23 物理动作列及 bias 换到新坐标，保留 5 个 context 列和原优化器动量数值，优化轨迹需单独评价。首批 1,725 个同物理输入，未做优化时，仅换统计造成的 TCP 单步最大单坐标偏移 12.412 mm，等价变换后约 0.000358 mm。[复测](../results/b0/standard_transfer_wm_rebase_audit/function_check.json)

## 运行与剩余门槛

云端工作树 /root/autodl-tmp/dog-and-arm-b0-standard。配置命令为 `bash scripts/b0/env.sh python scripts/b0/train_contact.py --config config/b0/standard_contact_40.yaml --run <新名称> --updates 50`。其他配置与实际运行参数随各 run 登记。云端 b0-standard-finish 收齐冻结物理评测；第二平台 b0-standard-receive 只收小型结果及证据视频，并从隔离交付树发普通提交。查看命令见 prompts/NEXT_RUN.txt。

正式接触协议仍按登记的五个 v1 加五个 hold-margin。另跑全十项 v1 以供原 r3 同版比较；各组按包、后端、版本、case 分别计数。D 开发每项要求 ≥18/20，完整门同包主后端两侧 C 各 ≥18/20，native 两侧 nominal 及持续真实 H32 能力。此轮未进入完整任务评测、独立 seed1/2 或 H。旧混合结果、物理阶段时间用完、梯度和 WM 改善均保留各自含义。截止本次交接，没有标准包通过接触。

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
