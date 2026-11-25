# RefXY2 配对迁移实测

两支各保留 +200 Actor / +2,000 WM / +4,000 Critic，配对实付 400 / 4,000 / 8,000，回滚为零。主段 252 案，延长复测 12 案。native/pull 的处理支最小 P95 为 10.255 mm，超过 shared_0 最大 P95 9.910 mm，差 0.345 mm。登记的 native 非退化条件未满足。本轮于 +200 结案，RefXY2 完整成功 0/12，V0=0，合格双侧回报 NA。这界定了 u10000 父点、固定配方和本轮预算内的独立适配结果。原 standard-v1 继续封存于 u10000，B0-04、候选 null、合格回报 NA。旧 546 维混合方法的双侧成功视频另见[原视频与策略来源](SUCCESS_VIDEOS_AND_SCOPE_20261125.md)。

## 原物理裁判

| 冻结包 | Warp 接触 | native 接触 | frame0 full | free |
| --- | ---: | ---: | ---: | ---: |
| shared_0 | 0/10 | 0/10 | 0/4 | 0/60 |
| zero_200 | 1/10 | 2/10 | 0/4 | 0/60 |
| measured_200 | 1/10 | 2/10 | 0/4 | 0/60 |

- shared_0 通过的接触入口为 0 项。
- zero_200 通过的接触入口为 warp/push/stable_grip、native/push/open_5、native/push/stable_grip。
- measured_200 通过的接触入口为 warp/push/stable_grip、native/push/open_5、native/push/stable_grip。

measured +200 的 Warp 前拉首次通过 pregrasp，首遍在第 6,121 个物理区间结束时（12.242 s）达到原 75 拍连续 ready，进入 approach_arm 后超时。该事件发生在固定 76 拍平台之后，固定平台本身的位置合格拍仍为 0。处理支 Warp 背推记录到 put_data 的 efm_fluid 溢出警告，原始记录随包保留。

完整任务均从 frame0 开始，到原首败结束。下表采用每侧固定的 76 个 2 ms 区间。位置要求 3 mm，原 pregrasp 阶段要求同时 ready 连续 75 拍（150 ms）。每案的全阶段窗口、各误差分位、参考进展与根平移／根旋转／臂 FK 投影均在逐案包内。

| 包 | 后端 | 侧 | 固定窗拍数 | 最小 mm | P50 mm | P95 mm | 最大 mm | P95 / 3 mm | 位置合格拍 | 原最长同时 ready 拍 | 已完成事件 | 首败 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| shared_0 | warp | pull | 76 | 9.628 | 10.478 | 11.378 | 11.490 | 3.793 | 0 | 0 | approach_base → settle | timeout:pregrasp |
| shared_0 | warp | push | 76 | 13.826 | 14.373 | 14.954 | 15.025 | 4.985 | 0 | 0 | approach_base → settle | timeout:pregrasp |
| shared_0 | native | pull | 76 | 7.933 | 8.919 | 9.910 | 10.030 | 3.303 | 0 | 0 | approach_base → settle | timeout:pregrasp |
| shared_0 | native | push | 76 | 11.180 | 11.591 | 12.075 | 12.139 | 4.025 | 0 | 0 | approach_base → settle | timeout:pregrasp |
| zero_200 | warp | pull | 76 | 10.887 | 12.205 | 13.464 | 13.611 | 4.488 | 0 | 0 | approach_base → settle | timeout:pregrasp |
| zero_200 | warp | push | 76 | 15.760 | 16.291 | 16.895 | 16.972 | 5.632 | 0 | 0 | approach_base → settle | door_contact_outside_manipulation |
| zero_200 | native | pull | 76 | 11.336 | 12.567 | 13.840 | 13.988 | 4.613 | 0 | 0 | approach_base → settle | timeout:pregrasp |
| zero_200 | native | push | 76 | 14.894 | 15.507 | 16.174 | 16.257 | 5.391 | 0 | 0 | approach_base → settle | door_contact_outside_manipulation |
| measured_200 | warp | pull | 76 | 5.191 | 6.125 | 7.035 | 7.142 | 2.345 | 0 | 75 | approach_base → settle → pregrasp | timeout:approach_arm |
| measured_200 | warp | push | 76 | 12.744 | 13.120 | 13.568 | 13.627 | 4.523 | 0 | 0 | approach_base → settle | timeout:pregrasp |
| measured_200 | native | pull | 76 | 8.676 | 9.502 | 10.255 | 10.343 | 3.418 | 0 | 0 | approach_base → settle | timeout:pregrasp |
| measured_200 | native | push | 76 | 11.148 | 11.461 | 11.853 | 11.906 | 3.951 | 0 | 0 | approach_base → settle | timeout:pregrasp |

## 延长决定

| 原裁判 | 共同 +0 P95 mm | zero +200 P95 mm | measured +200 P95 mm | 本侧登记条件 |
| --- | ---: | ---: | ---: | --- |
| warp/pull | 11.378/11.377 | 13.464/13.464 | 7.035/7.035 | 满足 |
| warp/push | 14.954/14.958 | 16.895/16.898 | 13.568/13.567 | 满足 |
| native/pull | 9.910/9.910 | 13.840/13.840 | 10.255/10.255 | 未满足 |
| native/push | 12.075/12.075 | 16.174/16.174 | 11.853/11.853 | 满足 |

native/pull 的处理支最小 P95 为 10.255 mm，超过 shared_0 最大 P95 9.910 mm，差 0.345 mm。登记的 native 非退化条件未满足。共享回滚预留依然是 20 / 200 / 400。本轮新增 D/C 资格案为 0。+500、+1000、独立种子、H、原 u15000、算法/VLA 和实机执行均未开展。[判定与对照效果量](../results/b0/refxy2_pair_20261125/extension_decision.json) · [物理逐包清单](../results/b0/refxy2_pair_20261125/assessment/physics_manifest.json) · [视频清单](../results/b0/refxy2_pair_20261125/video_manifest.json)

## 从同一完整状态分叉

父状态的 replay.clock 为 26,988，有效转移 102,414,758，Ratio.pending 为 0，距下次阈值还有 5,722 个有效转移。两支保留 official_flow_s0_v1、4096 个环境、原 H32、WM/Critic、八参考、时钟、原奖励及在线统计。measured 仅向已归一化的 540 维目标追加当前参考根减自身根的水平差，按自身 yaw 转到机体系并除以 0.05 m。zero 同宽，两维恒零。FreeRun.actor_obs、接触与完整任务、真实采样、replay 与各想象步均走对应路径。

首层旧 540 列及 Adam 两种矩逐张量复制，新增 4,096 个权重及对应矩全零。现场共享 step 为 10,000，实际 betas=(0.9,0.95)，lr=0.00019999999494757503，eps=1e−8。两支 +0 的 68 个 Actor、24 个 WM、10 个 Critic 状态张量全部相同。33 个归档真实查询在 CPU 稳定推理下，与父包的首层、raw、clipped 与物理命令最大差均为零。[+0 对照及坐标导数](../results/b0/refxy2_pair_20261125/frozen_inputs_000000.json) · [measured 迁移](../results/b0/refxy2_pair_20261125/measured/migration.json) · [zero 迁移](../results/b0/refxy2_pair_20261125/zero/migration.json)

两支首真实拍命令相同，首个更新的 11 组抽样索引、统计计数相同。4,096 个 Actor 起点中，4,083 个来自继承 replay 且输入逐值相同，新采的 13 个中有 7 个状态／历史出现浮点差异。measured 的 32 个想象步均重算 XY，31 个后继 aux 带梯度。首更新后 measured 新列权重变化 L2 为 0.00194152，zero 新列与矩仍全零。原全 Actor 裁剪前范数分别为 0.0408307 和 0.0406325。对 33 个冻结历史只将 XY 置零，measured 在 +50、+100、+200 的 raw 命令最大分量变化依次约为 0.0000803、0.000140、0.000302，zero 全为零。[实际首更新比较](../results/b0/refxy2_pair_20261125/first_update_paired_comparison.json) · [两支 +200 冻结输入](../results/b0/refxy2_pair_20261125/frozen_inputs_000200.json)

zero 和 measured 分别新增 2,048,963 和 2,049,102 个有效真实采集转移。具名可恢复节点含 +0、+1、+10、+50、+100、+200，中间每至多 10 个更新也保存。恢复时由不可变父 ring 与逐 tick 无损增量还原全部 replay，在线 lanes、历史、上拍命令、servo/solver、RNG、采样器、时钟和 Ratio 一并恢复。两支终点均实际再载并逐项核对。同一轮首个 zero 进程在初始恢复期间停止，将 Adam 学习率张量迁移到原设备后重启，当时未采集、未优化。[实付与失败记录](../results/b0/refxy2_pair_20261125/budget.json) · [逐次优化](../results/b0/refxy2_pair_20261125/optimizer_cost.jsonl) · [zero 终点恢复](../results/b0/refxy2_pair_20261125/zero/verification/complete_000200.json) · [measured 终点恢复](../results/b0/refxy2_pair_20261125/measured/verification/complete_000200.json)

## 独立冻结 FP64 检查

原 540/u10000、四个旧锚点共完成 264 次有符号扰动、4 次预热、8 次 baseline、12 次方向 JVP、4 次反向 AD，新增物理与优化均为零。12/12 个方向的 J32 中心差分在至少三档连续尺度上趋向反向梯度投影，最细尺度同号 12/12，相对误差为 0.00000685% 至 0.2393%。八个奖励分项的值重构最大残差为 1.33×10⁻¹⁵。诊断前向 JVP 在 TorchScript 单位四元数旋转中丢失切向量。修正入口通过该算子反例检查，整条 H32 的修正后 JVP 与分项导数一致性仍为 unresolved。现有证据不足以判定训练核心违约。[FP64 结论、逐尺度残差与反例](../results/b0/refxy2_pair_20261125/fp64/README.md)

## 执行与资产

训练源码从登记提交 2bbb9fec 单独部署，执行目录为 AutoDL 的 `/root/autodl-tmp/dog-and-arm-b0-temporal-v1/.refxy2-2bbb9fec`。物理数组、权重与恢复增量按各包 manifest 的相对路径从该目录解析。常规评测用原 2 ms Warp 与 native MuJoCo 3.3.0，free 用原三参考各 20 案。精确恢复命令为 `bash scripts/b0/env.sh python -m scripts.b0.refxy2_verify measured 200`，zero 同理。原始训练支出承袭父主链 10,000 / 100,000 / 200,000，另列 WM 祖先 14,850 批。A–D 历史实验未重做。默认项目入口保留 de0a4d6c 的已有视频交付与停止自动续训决定。[zero 清单](../results/b0/refxy2_pair_20261125/zero/manifest.json) · [measured 清单](../results/b0/refxy2_pair_20261125/measured/manifest.json)
