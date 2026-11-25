# 官方 SuperMimic 在 M1＋Piper 上的预抓兼容性实测

2026-11-25，北京时间。固定父包为 `79fd3cf/official_flow_s0_v1/u10000`，执行登记为 `2f75c349`。**原预抓平台四案均因位置精度不足错过就绪窗口。四案在参考钟继续推进后也未建立双指接触。** 原方法停在 B0-04，候选为空，合格双侧回报 NA，V0 为 0。

[机制决定](../results/b0/standard_pregrasp_compatibility_20261125/mechanism_decision.json) · [实际成本与恢复](../results/b0/standard_pregrasp_compatibility_20261125/budget_and_recovery.json) · [原登记](../docs/B0_PREGRASP_COMPATIBILITY_PLAN_20261125.md)

## 原端点与参考时钟

离线复算 u4991、u7500、u10000 各四条轨迹，共 85,404 个 2 ms 区间。四个 u4991 输入来自已登记的父诊断回放。逐拍区分实际事件阶段与参考阶段，记录实际 TCP、当前 20 ms bank FK、密集 2 ms 参考 FK、记录的 Cartesian goal、冻结端点。每条轨迹的五组坐标、三维分量、符号投影及残差均保存在原数组索引列出的位置。

下表为 u10000 的原参考平台。每案 ramp 已满足，姿态误差 ≤0.02 rad 的最长连续段均为 76 拍，位置误差 ≤3 mm 和最终 ready 均为 0 拍。表中后四列为平台平均、沿当拍端点总误差方向的有符号投影，单位 mm。它们允许相互抵消。

| 后端 | 方向 | 实际进入预抓 s | 原 ramp 完成 s | 平台最近距离 mm | 根平移 | 根旋转 | 臂 FK | 参考进展 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| warp | 前拉 | 7.278 | 11.744 | 9.629 | +2.497 | +0.751 | +7.231 | +0.026 |
| warp | 背推 | 7.272 | 11.740 | 13.826 | +5.134 | +0.201 | +9.010 | +0.047 |
| native | 前拉 | 6.726 | 11.744 | 7.933 | -0.979 | -0.150 | +10.041 | +0.025 |
| native | 背推 | 6.732 | 11.740 | 11.180 | +1.550 | +0.234 | +9.784 | +0.046 |

前拉参考平台止于 11.896 s，背推止于 11.892 s（右端开区间）。各案最近位置仍超过门槛 4.933–10.826 mm。沿参考钟进入 grasp 后，到冻结端点的距离与到当前参考 TCP 的距离开始分离。扩大到实际预抓阶段的全部 ramp 后样本，四案最近距离依上表次序为 6.962、12.618、4.683、10.587 mm，仍无位置合格拍。

物理区间起点 k 对应就绪表 step=k+1，Actor 在绝对边界取 k//10 帧，学习目标取下一策略帧。按区间起点 FK 重算原端点距离，所有可比样本最大差 0.000355 mm；误用积分后位置会达 0.502 mm。两层三维向量恒等式最大闭合残差 0.000317 mm。用原 FK 重算对 ready 的判定与原记录逐拍一致。u4991/u7500/u10000 的原实际事件窗分别完整 4/4、0/4、0/4，原参考跟踪窗分别完整 8/8、6/8、8/8。12 案有 8 案实际覆盖平台，其余 4 案缺少可评平台。详细区间含最小值时刻和连续拍数。[端点分解](../results/b0/standard_pregrasp_compatibility_20261125/endpoint_decomposition.csv) · [就绪逐案](../results/b0/standard_pregrasp_compatibility_20261125/readiness_predicates.json) · [时钟](../results/b0/standard_pregrasp_compatibility_20261125/clock_alignment.json) · [原窗复算](../results/b0/standard_pregrasp_compatibility_20261125/registered_windows_recheck.json) · [原数组与向量表](../results/b0/standard_pregrasp_compatibility_20261125/source_array_inventory.json)

## 冻结 Actor 能区分什么

前拉选取 11.76、11.88 s，背推选取 11.74、11.88 s，均在首个扰动前登记。四锚各重建完整 10 帧历史。对机器人整体作 ±50 mm 水平平移后，同一稳态计算下，Actor 的历史与 540 维目标相同，固定端点误差的对应坐标可改变符号，Critic 输入最大分量差为 0.04982–0.05000。四锚的 yaw +0.5° 和 J2 +0.001 rad 共八个正控均改变可见输入。该实验辨识了信息丢失，尚未辨识两种状态各自的最优电机命令。

28 个登记变体实际直接调用冻结 Actor 27 次。首锚冷启动与稳态原始命令差 5.96×10⁻⁸，零平移也复现该输入舍入效应；三个完全同输入的冗余平移变体共用已直接求得的命令。固定官方 motion Actor 省略未来根相对平移 30 维，当前 77×10 本体历史不含根 XY。原六项 tracking、effort 动作率、joint_limit 分项、软终止及 H32 末端 Critic 按固定源码核对。四个实测后继的八项有符号标量与原 reward 最大差 7.45×10⁻⁹。身体目标随预测根 XY/yaw 重锚，绝对根目标项另行计入。0.3 m 高斯核尺度与 3 mm 判据衡量不同的量。[锚点](../results/b0/standard_pregrasp_compatibility_20261125/states.json) · [冻结输入与命令](../results/b0/standard_pregrasp_compatibility_20261125/input_alias.json) · [原目标项和源码](../results/b0/standard_pregrasp_compatibility_20261125/original_objective_terms.json)

## 原目标方向在真实物理中的响应

两侧各从 frame 0 积分 47,600 个 0.25 ms 微步，四个查询前锚点均可达。快照包含 136 个 solver 数组、伺服缓存、连续物理监测计数、历史、上拍动作、参考时钟、上下文和 RNG。每锚用原无扰动身份读回一拍，共 320 微步。四个起点的 solver、历史与上拍动作均逐值一致；两个后继逐位复现，其余两个后继最大 q 差 3.73×10⁻⁹、速度差 2.51×10⁻⁶，离散计数与首败状态均一致。

真实响应从这些同身份初态出发，只在首拍施加原 H32 目标梯度、J2 或四轮同向扰动。J2 为 0.025 rad/effort，轮速为 0.5 (rad/s)/effort。随后 WM 和物理各自按后继重新查询冻结 Actor，使用登记的共同本体噪声。每锚 19 条，共 76 条，均走完 32 拍，无物理首败。H1/H7 为原折扣回报前缀，H32 含软生存权重和原终端 Critic。12 组正向干预来自 4 个锚点 × 3 个幅值，共用相邻状态，不能当作 12 个独立试验。

| 时域 | 同一 WM 的 AD 与中心割线，同号/反号/低分辨 | WM 与真实回报中心割线，同号/反号/低分辨 | 正向梯度同时降低真实同钟和端点误差 |
|---|---:|---:|---:|
| H1，20 ms | 36 / 0 / 0 | 33 / 3 / 0 | 0/12 |
| H7，140 ms | 36 / 0 / 0 | 36 / 0 / 0 | 6/12 |
| H32，640 ms | 25 / 9 / 2 | 20 / 8 / 8 | 3/12 |

H32 正向首动作使实际端点距离变化 −0.0144 至 +0.0635 mm，真实 J32 在 3/12 档高于原动作。九个 WM 长时 AD/割线反号均在背推。已记录的接触、限幅、轮滑及 Critic 裁剪开关在 108 个同锚对照中均未发生相对基线的切换。单边和中心割线各自保留。有限幅非线性、浮点分辨率及后续策略反馈仍影响长时比较，现有证据不足以定位特定动力学导数或训练映射错误。[响应登记](../results/b0/standard_pregrasp_compatibility_20261125/response_registration.json) · [76条响应与目标分项](../results/b0/standard_pregrasp_compatibility_20261125/response_branches.csv) · [108组分时域比较](../results/b0/standard_pregrasp_compatibility_20261125/response_differences.csv) · [梯度与物理汇总](../results/b0/standard_pregrasp_compatibility_20261125/gradient_physics_comparison.json)

## 正式首败之后的原参考钟

同一冻结 u10000 分别从 frame 0 跑原 2 ms Warp 和 native MuJoCo 3.3.0。四案均封存原预抓超时、事件和吸收失败评分，之后保持在途动作至下一绝对 20 ms 边界；物理监测从 frame 0 连续维护。下表的下一查询以绝对 2 ms 步计数。

| 后端 | 方向 | 正式首败 s | 首败后下次查询步 | 继续 s | 参考阶段物理终止 | 同回合视频 |
|---|---|---:|---:|---:|---|---|
| warp | 前拉 | 16.278 | 8140 | 0.972 | grip_handle_error | [原速视频](../results/b0/standard_pregrasp_compatibility_20261125/continuation/warp_pull/reference_clock_1x.mp4) |
| warp | 背推 | 16.274 | 8140 | 0.972 | grip_handle_error | [原速视频](../results/b0/standard_pregrasp_compatibility_20261125/continuation/warp_push/reference_clock_1x.mp4) |
| native | 前拉 | 15.728 | 7870 | 1.670 | lost_grip | [原速视频](../results/b0/standard_pregrasp_compatibility_20261125/continuation/native_pull/reference_clock_1x.mp4) |
| native | 背推 | 15.734 | 7870 | 1.512 | grip_handle_error | [原速视频](../results/b0/standard_pregrasp_compatibility_20261125/continuation/native_push/reference_clock_1x.mp4) |

到终止的四个诊断段中，双指同时接触为 0 拍，门角和门合力均为 0。三案在参考进入 open 时夹爪距把手超限，native 前拉因连续缺载 150 ms 停止。保持、释放及以后的阶段未到达。native 的正式前段状态、动作、时刻和分数与归档逐值一致；Warp 背推首败步相同，前拉提前 1 个 2 ms 步，归档和本次吸收分分别为 0.2145990、0.2145726。四条连续原速视频全部解码并核对逐帧时间戳。原 u10000 首败记录保持封存。[逐案及首败回执](../results/b0/standard_pregrasp_compatibility_20261125/reference_clock_continuation_cases.csv) · [视频清单](../results/b0/standard_pregrasp_compatibility_20261125/diagnostic_video_manifest.json)

## 恢复、成本和资格差距

本轮真实重载父包的三个网络、在线统计、优化器、replay、sampler、RNG、4,096 条 lane、solver 与伺服。40 页 replay 的 480 个字段张量、136 个 solver 数组及 162 个优化器状态张量均通过逐值核对。父时钟 26,988，有效转移 102,414,758，Ratio pending=0，距下次阈值 5,722。大资产见 AutoDL 的 `/root/autodl-tmp/dog-and-arm-b0-temporal-v1/.pregrasp-2f75c349/results/raw_large/b0/pregrasp_compatibility_20261125`，逐案入口见成本回执。轻结果可随仓库直接读取。[父包实载](../results/b0/standard_pregrasp_compatibility_20261125/parent_recovery.json) · [边界核验](../results/b0/standard_pregrasp_compatibility_20261125/restored_u010000.json) · [实际成本](../results/b0/standard_pregrasp_compatibility_20261125/budget_and_recovery.json)

实际新增 4 条正式物理身份诊断、2 条细步重建、4 条单拍重载与 76 条响应，共 86 条。诊断物理步总量为 34,570 个 2 ms 步与 290,080 个 0.25 ms 微步。Actor/WM/Critic 优化和回滚实付均为 0/0/0。旧轮 5,009/50,090/100,180 次增量、父主链累计 10,000/100,000/200,000 次和祖先 WM 14,850 批分列。

距首个 V0 尚缺同一冻结 Actor 从原 frame 0 依次完成 3 mm、0.02 rad、150 ms 预抓就绪、抓持、开门（前拉 60° 或背推 25°）、保持、释放、撤臂、收臂、退离及停稳。距独立标准结果尚缺同包原 Warp 接触 10/10、D 十项各 ≥18/20、双侧完整 C 各 ≥18/20、同包 native 双侧完整名义、每个 free 参考 ≥18/20，继而独立 seed1/2、冻结 H 每 seed 每侧 ≥40/50 及合格双侧回报。父包目前 Warp/native 接触均 0/10、full 0/4、free 0/60。合格回报 NA，距 0.88 接近带和 0.90 参照的数值差仍不可计算。

## 机制决定与独立适配提案

本轮确认了水平位置输入别名，也确认原 H32 目标方向在登记物理状态上缺乏一致的端点纠偏效果。两者对完整任务失败的因果份额尚未分离。未取得违反既定单位、时刻、字段、历史或样本映射契约的反例。唯一运行时代码调整为诊断单世界在原物理首败微步返回，默认训练路径沿用父实现；配对修复训练未触发。

提出独立方法 **SuperMimic-M1Piper-RefXY2-v1**。只给 Actor 增加当前参考根相对机器人根的机体系水平偏移两维；仿真用根位姿给出自定位的理想上界。等宽对照的两维恒零，两支都从 u10000 恢复，新列零初始化，按原目标和物理协议比较。提案预算为每支 200 Actor / 2,000 WM / 4,000 Critic，整对一次回滚预留 20/200/400，本轮支出为零。该试验可检验额外水平位置信息能否使臂/底盘补偿达到原就绪精度，仍须独立实训验证。[提案、信息差异与预算](../results/b0/standard_pregrasp_compatibility_20261125/adaptation_proposal.json)
