# M1＋Piper 标准迁移同链续训结果

2026-11-25，北京时间。固定官方 SuperMimic 迁移链 `official_flow_s0_v1` 从 u1000 完整恢复，完成 u3000 主段，并依据双侧物理实测延长到 **u4991**。同一末点 Actor 在 Warp 和 native MuJoCo 3.3.0 上均通过背推侧的 5° 开门保持和稳定握持，两端均为 **2/10**。20 次从 frame 0 开始的双侧完整尝试中，20 次完成驶近、9 次完成停车、0 次完成全任务。阶段为 B0-04，最终候选为空，合格双侧完整回报 NA，V0 成功视频为 0。0.90 为论文 SONIC 参照，0.88 为项目登记的接近带。[独立 manifest](../results/b0/standard_official_flow_continuation_20261124/baseline_manifest.json) · [原判定逐案表](../results/b0/standard_official_flow_continuation_20261124/physical_cases.csv) · [视频登记](../results/b0/standard_official_flow_continuation_20261124/video_manifest.json)

## 各节点的原物理任务

接触列为同包原十项的通过数，完整列为 Warp 与 native 合计四案。每个节点的 free 包含支撑、运动臂、驻车各 20 案。

| 累计 Actor 更新 | Warp 接触 | native 接触 | 完整任务 | free | 观察结果 |
| --- | ---: | ---: | ---: | ---: | --- |
| u1500 | 0/10 | 未排期 | 0/4 | 0/60 | 四案均完成驶近。前拉驻车超时，背推碰到框架。 |
| u2000 | 0/10 | 未排期 | 0/4 | 0/60 | Warp 背推恢复停车，随后碰到门板。纯 Actor 背推保持入口仅有 2 ms 双指。 |
| u3000 | 0/10 | 0/10 | 0/4 | 0/60 | 两侧两端均完成驶近和停车。前拉在预抓取时后腿关节持续饱和，背推工位漂移。 |
| u4000 | **2/10** | 未排期 | 0/4 | 0/60 | 背推 `open_5` 完成 open、hold，`stable_grip` 完成 hold。六个纯 Actor 入口按反向顺序复测。 |
| u4991 | **2/10** | **2/10** | 0/4 | 0/60 | 两后端通过同两项。两端的前拉接触片段均未通过。 |

u4000 的背推抓、持、放三个验证入口各进行了 32 次 20 ms 策略查询。最长连续双指载荷依次为 458、618、618 ms，同包复测得到相同数值。u4991 三入口为 472、640、640 ms。该末点的四个完整回合分别停在 Warp 前拉预抓取阶段过早接触门、Warp 背推预抓取阶段触发轮支撑/倾斜判定、native 前拉预抓取超时、native 背推驻车超时。[纯 Actor 逐入口](../results/b0/standard_official_flow_continuation_20261124/pure_actor_entries.csv) · [u4000 复测](../results/b0/standard_official_flow_continuation_20261124/repeat_u004000.json) · [完整任务的失败与时钟](../results/b0/standard_official_flow_continuation_20261124/full_clocks.csv)

五个节点共评 70 个正式接触 nominal，含 Warp 50 案、native 20 案，6 份通过记录均对应表中的两个背推片段。24 案在首个 2 ms 因适用的 6 N 门力限制结束。free 的 300 案均实际运行 7 s，全部未达 TCP 精度要求，80 案还未达根位置精度，20 案还未达关节范围归一化精度。u4991 的支撑、运动臂、驻车 TCP 位置 RMSE 中位数为 80.42、78.57、89.18 mm。该 Actor 尚未取得自己的无接触资格。[free 汇总](../results/b0/standard_official_flow_continuation_20261124/free_summary.csv) · [末点 free 逐案](../results/b0/standard_official_flow_continuation_20261124/free/u004991/)

## u3000 的延长依据

全长固定窗内，native 前拉原失败对应的预抓取航向 RMSE 从 u1000 的 0.5024° 降到 0.1499°，共 101 个同钟端点。native 背推原失败对应的 XY RMSE 从 9.960 降到 3.779 mm，共 121 个端点。Warp 的 77 个驻车端点在两侧的 XY 与航向均改善，四个完整案又达到历史最佳的驶近＋停车。前拉预抓取 XY 在两端均变差，Warp 背推预抓取航向也略升。两个 Warp 回合在比 u1000 更早的物理时刻结束，实际阶段更晚；u3000 四案的首失败均发生在预抓取。由这些双侧事实决定延长。u4000 的原片段通过与持续双指是延长后取得的新结果。固定窗的选取规则见启动前登记，具体端点清单在首次 u1001 尝试后、所有新节点评测之前，仅由 u500/u1000 原轨迹生成。[固定窗](../results/b0/standard_official_flow_continuation_20261124/tracking_windows.json) · [延长决定及各项正反变化](../results/b0/standard_official_flow_continuation_20261124/decision_u003000.json)

## 预算、恢复与下一节点

| 账目 | H32 Actor | H7 WM | Critic | 有效策略转移 |
| --- | ---: | ---: | ---: | ---: |
| 直接 WM 祖先 | 见历史谱系 | 14,850 | 见历史谱系 | 见历史谱系 |
| 父主链 u0–1000 | 1,000 | 10,000 | 20,000 | 10,255,490 |
| 本轮保留增量 | 3,991 | 39,910 | 79,820 | 40,869,225 |
| 四次中断后回滚 | 6 | 90 | 120 | 92,028 |
| 本轮实际支出 | **3,997** | **40,000** | **79,940** | **40,961,253** |
| u4991 包内主链累计 | 4,991 | 49,910 | 99,820 | 51,124,715 |

本轮新增保留了 44,564,480 个 20 ms 物理区间，含 3,695,255 个前缀区间和 332,255 个完整有效 terminal。实际执行并保留 3,565,158,400 个 0.25 ms 微步。按真实有效转移计的 WM stored positions 比率为 15.99946，目标为 16。分段恢复后至各段最后保留更新的墙钟合计 6,759.08 s，包含段内保存开销；另行评测与回滚耗时单列。这些物理转移、模型窗口和想象步采用独立分母。[逐更新日志](../results/b0/standard_official_flow_continuation_20261124/updates.jsonl) · [恢复与增量细账](../results/b0/standard_official_flow_continuation_20261124/baseline_manifest.json)

启动基线为 GitHub main `bdb72d8f7019688b6e51ba0cd2d083a5bef90532`。固定源码为 SuperMimic `abc124c1` 与 mjlab_research `dd51a9fc`。恢复时逐项核对学习 cfg，继承 WM、已训练 Actor/Critic、全部优化器和统计、ReturnSampler、Ratio、RNG、连续 lane、历史动作及 solver/servo。原链保留 4,096 环境、H7 每轮 10 批、H32 Actor 一步、Critic 20 批、在线统计和原奖励。训练使用 0.25/2/20 ms 物理、伺服、策略时钟，正式 Warp/native 使用原 2 ms 物理身份。[父节点回读](../results/b0/standard_official_flow_continuation_20261124/restored_u001000.json) · [首个新更新](../results/b0/standard_official_flow_continuation_20261124/first_resumed_update.json)

共享 GPU 上四次尝试分别遇到显存或 CUDA Graph 捕获错误。为取得 u1001，一度将 40 页历史按原 dtype 映射到主存，并对 autograd 暂存作等精度传输。u1001 独立恢复通过。后续保留的 u1002–u4991 使用原 GPU 存储和官方图，未修改学习 cfg。每个失败尝试回滚到它自己的有效恢复点，并计入上述实际支出。轻量留档有 29 个绝对 tick 边界，最大间隔 500，小于 1,000 tick 的环容量。核对了相邻留档的 70,123,520 条重叠 lane 记录，episode 和四组计数字段吻合，保留增量的有效数与包内总量差一致。[覆盖留档](../results/b0/standard_official_flow_continuation_20261124/coverage_archive.json) · [不可变节点与文件字节数](../results/b0/standard_official_flow_continuation_20261124/milestones.json)

u4991 由另一进程从约 15.7 GB 的状态文件、权重及 solver 快照恢复，通过 4,096 条 lane、136 个 solver 数组、162 个优化器状态张量和全部 RNG/采样器核对。该节点已用尽本轮登记的 40,000 批 WM。运行至 u5000 还需 9 Actor / 90 WM / 180 Critic，届时本轮实付会超过原上限 6 Actor / 90 WM / 120 Critic。当前标准候选为空；十项 nominal、D、完整双侧 C/native、独立 seed1/2、三 seed 冻结 H 及论文回报资格仍未取得。D、C、seed1/2 和 H 均未启动。[末点回读](../results/b0/standard_official_flow_continuation_20261124/restored_u004991.json) · [预算收束](../results/b0/standard_official_flow_continuation_20261124/budget_decision.json)

## 物理量及其比例

训练新段中 J2 最大实际命令为 2.57766 rad，参考上界 2.59618 rad，相差 0.01852 rad，占参考跨度 1.79618 rad 的 1.03%。u4991 保持入口首个求解时，前拉和背推的 J2 执行力矩分别为 −16.736 和 +0.839 Nm，对应 35 Nm 限值的 47.8% 和 2.4%。同一时刻主动夹指执行力为 −3.778 和 −3.764 N，对应 10 N 限值的 37.8% 和 37.6%。背推 `open_5` 在适用相位的峰值合力在 Warp/native 为 4.946/4.967 N，各为 6 N 限值的 82.4%/82.8%。逐案表另列实际/参考相位、XY 与航向原值及阈值、轮目标/轮速、六臂关节和夹口的目标及实测、裁剪前及已执行驱动力。[实际命令覆盖](../results/b0/standard_official_flow_continuation_20261124/coverage_u004991.json) · [最终求解区间](../results/b0/standard_official_flow_continuation_20261124/last_physical_intervals.csv) · [逐轴物理单位与限幅](../results/b0/standard_official_flow_continuation_20261124/wheel_arm_jaw.csv)

## 两项有限诊断

WM 四格使用同一旧开发窗，新增优化步为零。下表为原双指窗口的 H32 TCP P95，前拉 386 窗、背推 446 窗。原配对复现。仅交换完整 state/action normalizer 的 mean/var/std/count；u1 统计来自首 19 tick，计数 73,157。改变统计与改变权重有明显交互。首批实际 H7 索引、真实输入 z、首层响应和自回归输入分别留档。[四格结果](../results/b0/standard_official_flow_continuation_20261124/wm_factorial/factorial.json)

| 权重 | 统计 | 前拉 mm | 背推 mm |
| --- | --- | ---: | ---: |
| u0 | u0 | 20.72 | 14.49 |
| u0 | u1 | 246.76 | 287.79 |
| u1 | u0 | 52.84 | 59.40 |
| u1 | u1 | 498.58 | 815.74 |

u1000 与 u3000 各独立采集 256×64 tick，均未回灌训练。前者 8,533 个有效策略区间、0 个双指区间，后者 10,690 个有效、143 个双指。u3000 全程双指 H7 有前拉 5 窗、背推 0 窗；双侧全程双指 H32 均为 0 窗。两节点开发种子不同，独立块不取代原物理裁判。u5000 未到达，该节点登记的第三个开发块未采集。[u1000 开发块](../results/b0/standard_official_flow_continuation_20261124/current_policy/u001000/scores.json) · [u3000 开发块](../results/b0/standard_official_flow_continuation_20261124/current_policy/u003000/scores.json)

u1000 原身份的 Warp/native 双侧四案复现原失败阶段和步数。两侧首次达到一个探索噪声标准差的原始命令差均在参考第 206 帧，即 4.12 s 的轮通道 12。前拉 native 首失败时 XY 18.80315 mm、航向 2.00118973°，确认触发航向线。完整训练细步两案保持每 Actor 80 微步、每伺服 8 微步和原 bias 刷新；前拉 11.7355 s 驻车超时，背推 11.24625 s 发生非抓握部位接触。四个额外告警复测案捕获前拉转背推时 `put_data` 对 `efm_fluid` 的 float64→float32 转换，长度 241 的数组中索引 65 超出 float32 范围。现场两侧的风、密度、黏度均为零，当前版本的流体求解读路径受 `has_fluid` 控制。历史日志只能确认转换行号。[对齐与后端对照](../results/b0/standard_official_flow_continuation_20261124/backend/comparison.json) · [字段和调用栈](../results/b0/standard_official_flow_continuation_20261124/backend/warnings_warning_fields.jsonl)
