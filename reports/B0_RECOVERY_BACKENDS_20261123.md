# B0 同包三后端闭环与接触差异实测

2026-11-23，北京时间，第二平台 RTX 3060 Laptop。使用同一冻结 seed0 Warp 权重 `full_s0_joint_warp_prior_r1/checkpoint_000000.pt`，以及 `full_warp_hold_park_r1` 的固定双侧参考。该包有历史教师动作监督，完整任务 H32 更新为 0。本节新增的都是物理诊断与冻结策略闭环。

## 三套未经修改的后端

| 后端及实际评分 | 前拉，末步门角与物理步 | 背推，末步门角与物理步 |
| --- | --- | --- |
| native MuJoCo 3.3.0 | 60.1671°，31,310 步，退臂超时 | 6.2455°，10,611 步，打开阶段抓持几何失败 |
| CPU MuJoCo 3.16.0 | 59.9479°，37,373 步，通过 | 25.0274°，27,513 步，通过 |
| MuJoCo-Warp 3.16.0 | 59.9506°，37,373 步，通过 | 25.0262°，27,512 步，通过 |

每条名义任务从原停车初态启动，前缀 0 步，Actor 每 20 ms 读取本后端的历史状态并执行同一动作参数化，裁判每 2 ms 检查一次。CPU 两端使用 CPU Actor，Warp 端使用 CUDA Actor。成功均记录完整 13 阶段与两个各 1,500 步保持。CPU3.16 和 Warp 的同包结果为两侧各 1/1 名义。原生 3.3 的同包跨端门槛仍未通过。本工作包未追加任何完整 C 或 H 的任务评测。

原始逐例、完整名义视频和步数：[native3.3](../results/b0/recovery_c_anchor_native33_r1)、[CPU3.16](../results/b0/recovery_c_anchor_cpu316_r1)、[Warp3.16](../results/b0/recovery_c_anchor_warp316_r1)。对应完整状态、未限幅与已限幅动作位于专用树 `results/raw_large/b0/` 下的同名目录。

## 第一次力学分歧出现在轮胎首次着地

两侧各有三个开环定位窗口。起步从真实参考初态做 320 个物理步。预抓取和稳定开门分别从冻结参考同一个 q/v 出发，先执行 100 个物理步的共用前缀，再比较 320 步。输入 q/v 向 float32 仅量化一次，两套 CPU 引擎读取相同量化值。23 路目标按原时钟每十步更新，每个物理步的偏置补偿使用所在后端自身的实时动力学。每次窗口均使用新 MjData，重置后按照该后端的标准 forward 初始化，后续连续积分。表中差值包括前缀，窗口属于局部动力学诊断。

从停车起点开始，零基区间 8，即 16–18 ms 的首次着地，3.3 产生 4 个约束接触点，CPU3.16 与 Warp 均产生 10 个。3.3 与 CPU3.16 在该步的单轮载荷差已超过 0.1 N，积分后的根位置差在区间 17 首次超过 0.1 mm，TCP 区间起始位置差在区间 21 首次超过 0.1 mm。双侧起点均有这一顺序。

预抓取从源区间 5,520 开始时，双方 TCP 已由相同姿态确定。3.3 每轮有 1 个承重点，另两端每轮有 4 个，两个版本的四轮合计为 4 对 16。3.3 与 CPU3.16 的最大单轮载荷差为 9.848/8.505 N（前拉/背推），相同目标驱动 420 个物理步内，最大 TCP 差为 0.819/1.444 mm。相同窗口 CPU3.16 与 Warp 的最大 TCP 差仅为 0.00238/0.00384 mm。逐窗分母、首次越限和全部实测：[逐窗对照表](../results/b0/recovery_c_probe_r1/pair_windows.csv)。

## 单变量定位与反事实闭环

三端共用原模型生成器；质量、摩擦、阻尼、执行器增益/偏置、约束与接触掩码均已逐项比较。3.3 与 CPU3.16 的最大惯量数值差为 2.11×10⁻¹⁴ kg·m²，几何四元数分量最大差 3.51×10⁻⁵。选取的公共 solver 字段中，CCD 迭代默认 50 对 35；在 3.3 将其单独设为 35，六个短窗口的轨迹没有测得变化。仅改变 MULTICCD 开关也未改变起步和预抓取轮地差异。已保存每个源模型、版本、实际选项、起始状态、代表帧的逐个接触点及力；Warp host 模型对照与实际 GPU 轨迹分别记录。[编译字段比较](../results/b0/recovery_c_probe_r1/compiled_fields.json)

3.3 的平面–网格碰撞从最深支撑点出发，按邻接顶点和距离阈值补点。3.16 用与平面最相对的相邻凸多边形面，最多保留四个支撑点。试验只将 3.16 诊断模型的四个轮胎网格 `mesh_polynum` 设为 0，调用其原有最深支撑点分支，保留网格顶点、三角面、质量、摩擦、控制器、迭代器和完整评分标准。此改变仅存在于该次内存中的模型。具体实现见 [3.3.0 的 mjc_PlaneConvex](https://github.com/google-deepmind/mujoco/blob/3.3.0/src/engine/engine_collision_convex.c) 与 [3.16.0 的 mjc_PlaneConvex](https://github.com/google-deepmind/mujoco/blob/3.16.0/src/engine/engine_collision_convex.c)。

只改轮胎之后，CPU3.16 预抓取对 3.3 的最大 TCP 差从 0.819/1.444 mm 降至 0.00000274/0.00000190 mm，最大单轮载荷差均低于 0.000022 N。该项解释了早期差异。稳定开门还有第二项差异：固定起点的首次求解，CPU3.16 两个夹指对把手各 2 个承重点，3.3、Warp、关闭 MULTICCD 的 CPU3.16 都是各 1 个。只关 MULTICCD 将 CPU3.16 与 Warp 在稳定前拉/背推中最大 TCP 差从 0.2692/0.0276 mm 降到 0.0283/0.0014 mm。

在 CPU3.16 上使用同一个监督 Actor 做 2×2 实验，每条均闭环执行，均为 nominal 两条。

| 轮地支撑 | CPU3.16 MULTICCD | 前拉 / 背推 | 前拉首失败 / 背推首失败 |
| --- | --- | --- | --- |
| 原面接触 | 默认开启 | 通过 / 通过 | 两侧走完整流程 |
| 原面接触 | 关闭 | 通过 / 通过 | 37,373 / 27,515 步 |
| 仅最深点 | 默认开启 | 失败 / 失败 | 均在 open 阶段 TCP–把手距离超过 5 mm，分别 13,301 / 11,739 步 |
| 仅最深点 | 关闭 | 失败 / 失败 | 31,310 步退臂超时 / 10,619 步抓持几何失败 |

仅改轮地支撑就能改变这两条闭环任务的成败。对上述单点条件再关闭 MULTICCD，前拉与原生 3.3 在同一物理步退臂超时。背推在同一阶段触发同一抓持几何事件，相差 8 个物理步（16 ms）。两项干预后 CPU3.16 对原生 3.3 的稳定开门短窗最大 TCP 差降至 0.00409/0.00000138 mm。该结论限定于这组权重、条件与窗口。[仅关闭 MULTICCD](../results/b0/recovery_c_anchor_cpu316_multiccd_off_r1) · [仅改变轮地支撑](../results/b0/recovery_c_anchor_cpu316_wheel_deepest_r1) · [两项条件合并](../results/b0/recovery_c_anchor_cpu316_wheel_deepest_and_multiccd_off_r1)

## 命令、文件与范围

在 `/home/kaiwen/research/dog-and-arm-b0-contact` 中运行。原名义评测用以下命令；native3.3 使用 `.venv/bin/python`，CPU3.16 使用 `bash scripts/b0/env.sh python`，两者取 `--backend native --device cpu`。Warp 使用隔离 B0 环境和 CUDA。重新测量时另起 run 名；原输出保留。

```bash
export MUJOCO_GL=egl OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
bash scripts/b0/env.sh python -u -m scripts.b0.eval_contact_segments \
  --full-task --side pull push --backend warp --device cuda:0 \
  --checkpoint results/b0/full_s0_joint_warp_prior_r1/checkpoint_000000.pt \
  --references results/raw_large/b0/full_warp_hold_park_r1 --run recovery_c_anchor_warp316_r1 --video
bash scripts/b0/env.sh python -m scripts.b0.recovery_backend_probe \
  --engine cpu316 --variant wheel_deepest_only --output results/b0/recovery_c_probe_r1
bash scripts/b0/env.sh python -u -m scripts.b0.recovery_backend_ablation \
  --checkpoint results/b0/full_s0_joint_warp_prior_r1/checkpoint_000000.pt \
  --engine cpu316 --variant wheel_deepest_and_multiccd_off \
  --run recovery_c_anchor_cpu316_wheel_deepest_and_multiccd_off_r1 --video
.venv/bin/python -m scripts.b0.recovery_backend_compare results/b0/recovery_c_probe_r1
```

原生和 Warp 默认物理仍各自用于正式评分。这些对照为后端迁移提供了有针对性的采样条件；是否能由新策略同时容忍两种接触分布，要由该策略在两个原始后端上的独立闭环决定。

### 在 Warp 重现原生侧的失败

Warp 的胶囊–网格夹指碰撞在此场景每指生成一个接触点。仅对四个轮胎启用最深支撑点分支，真实反馈闭环即重现原生两个失败事件。前拉在第 31,310 步退臂超时，背推在第 10,620 步越过 5 mm 抓持门槛，两者与原生分别相差 0 与 9 步。其短窗根/TCP 差和力差见前述逐窗表。Warp 此次背推加载时出现一次 float 转换 overflow 警告，两侧物理记录有限，接触缓冲 overflow 位均为 0。已保留未改设置的正式 Warp 结果。[Warp 单点轮地诊断的两条闭环与视频](../results/b0/recovery_c_anchor_warp316_wheel_deepest_r1)

## 同一参考下直接换包与六臂读出试验

在两条固定 Warp 参考下，历史 native 成功包也无法直接迁移。native3.3 前拉/背推分别在 12.680°/5.284° 出现抓持几何失败。该权重在 CPU3.16 只完成背推，前拉耗尽参考。native/Warp 两套实际训练教师的 `open` 起点相差 13 帧，操作期间的同钟 TCP 教师目标中位差为 5.94 mm（前拉）、6.17 mm（背推）。[native3.3](../results/b0/recovery_c_native_anchor_on_warp_refs_native33_r1) · [CPU3.16](../results/b0/recovery_c_native_anchor_on_warp_refs_cpu316_r1)

选取两个实际 native 训练教师中与固定 Warp 时钟同阶段且 TCP 目标差≤2 mm、姿态差≤1°的动作标签，前拉 450 帧、背推 436 帧。两个 nominal 评测回放均未提供教师标签。第一个试验冻结 Warp Actor 主体，最小二乘调整末层出端的六个臂关节，原 Warp 两个训练教师的 3,786/2,802 帧用于约束原动作，系数见 `protocol.json`。实测训练 RMSE 从 0.02102/0.01257 rad 减到 0.00262/0.00231 rad。原生复测两侧都超过 6 N，Warp 前拉超过 6 N、背推抓持超时。默认两端均 0/2，保留此负结果。[拟合](../results/b0/recovery_c_s0_arm_readout_r1) · [原生回归](../results/b0/recovery_c_arm_readout_native33_r1) · [Warp 回归](../results/b0/recovery_c_arm_readout_warp316_r1)

## 将实测根位移偏差映射为六臂角度修正

在固定 Warp 参考第 753 个策略时刻，原冻结 Actor 在原生上的所在根位置与给定参考的差约 3.5 mm，两个方向的 TCP–把手误差为 3.17/3.42 mm；在原 Warp 环境上为 0.13/0.17 mm。背推约在第 1,061 帧触及 5 mm。继承 Warp u0 主体与 23 个输出通道，利用仿真真值当前根位置和给定参考的根位置得到世界系平移误差。在公共参考姿态预计算抓取点对六臂的位姿雅可比，将平移误差映射到六个臂参考动作残差。角速度行的长度尺度为 0.12 m，阻尼 0.01，每个关节修正限幅为 ±0.05 rad，近收臂参考按距初始姿态幅度平滑衰减。此处采用仿真特权根平移和模型运动学。整个运动学表只取决于提供的公共参考，两端共用；部署不读取接触力、未来真实状态、后端 ID 或教师动作。

冻结全部原网络参数，在上述 450/436 个对齐训练帧上，两侧等权拟合一个共享系数。无约束解为 1.339，按事前区间 [0,1] 取 1.0。两组训练残差变为 0.01193/0.00276 rad。先用独立实现验证闭环，原生 3.3 前拉/背推 37,059/27,955 步均通过，约 59.9772°/24.9942°。CPU3.16 两侧 37,373/27,512 步均通过。Warp 两侧 37,376/27,514 步均通过。这是带几何前馈的监督初始化，新增 H32=0。[标定](../results/b0/recovery_c_s0_stance_r1) · [native3.3](../results/b0/recovery_c_stance_native33_r1) · [CPU3.16](../results/b0/recovery_c_stance_cpu316_r1) · [Warp](../results/b0/recovery_c_stance_warp316_r1)

### 标准 Actor、物理采集和想象入口

将独立实现迁入标准 Actor。保留原 540 个参考分量，末尾追加六个弧度单位的修正。六个新编码器列初始化为零，新归一化列均值 0、标准差 0.05 rad；原编码器和归一化器逐列复制。Actor 直接将六臂修正加到原六臂物理输出。相同入口还可叠加 A3 的 570 维和 A4 的 571 维输入，分别得到 576/577 维。WM 与 Critic 输入维度保持既有定义。实际物理采集与 `DoorImagination._update_goal` 都经 `DoorMotions.goals` 从当时根位置重算修正，想象中根位置来自预测，梯度可通过位移回到模型动作链。额外的六个神经输入列可在随后的联训中更新。

两侧共 71 个扰根观测，标准物理 Actor 与独立实现的最大归一化动作差为 5.96×10⁻⁸。六个新分量对当前根 XYZ 的偏导与中心差分最大差为 4.63×10⁻⁷ rad/m。核对工具初次因 PyTorch 编译图不允许复用捐赠缓冲区而中断；关闭该核对工具的编译优化后，逐列偏导和数值比对均通过。第二平台和 AutoDL 标准测试使用同一完整文件，SHA-256 为 `7f86370f47d549ce6a1570a8d66f3996abb80708f50162ba42a5927cb5dff61f`。原生 3.3 标准入口再次双侧通过，37,056/27,948 步，59.9774°/24.9950°。接触处的数值微差会使长轨迹的终点步数小幅改变。[标准包与验算](../results/b0/recovery_c_s0_stance_integrated_r1) · [标准加载的原生逐案](../results/b0/recovery_c_integrated_native33_r1)

```bash
bash scripts/b0/env.sh python -m scripts.b0.recovery_backend_fit --checkpoint results/b0/full_s0_joint_warp_prior_r1/checkpoint_000000.pt --run recovery_c_s0_arm_readout_r1
bash scripts/b0/env.sh python -m scripts.b0.recovery_backend_stance fit --checkpoint results/b0/full_s0_joint_warp_prior_r1/checkpoint_000000.pt --run recovery_c_s0_stance_r1
bash scripts/b0/env.sh python -m scripts.b0.recovery_backend_package --source results/b0/full_s0_joint_warp_prior_r1/checkpoint_000000.pt --fit results/b0/recovery_c_s0_stance_r1/fit.json --references results/raw_large/b0/full_warp_hold_park_r1 --run recovery_c_s0_stance_integrated_r1
```

同一台第二平台的标准 Warp 入口随后完成前拉 37,373 步、59.96510°与背推 27,514 步、25.02920°，两侧均通过。两套 CPU/GPU 运行时的原始差异保留在对应的 `warp_capacity`、实际步数和审计数组中。采用 A3/A4 权重作为底座时，也已分别核对 576/577 维的字段迁移与根位置梯度；装包不计作它们的物理通过。[标准 Warp 双侧复测](../results/b0/recovery_c_integrated_warp316_laptop_r1) · [A3 装包](../results/b0/recovery_c_s0_A3_stance_r1/package.json) · [A4 装包](../results/b0/recovery_c_s0_A4_stance_r1/package.json)

真实训练材料现已分别在第二平台和云端 `torch.load` 实载。两端的固定参考数组形状、完整可读与有限性检查，三个本地监督试验及云端独立/A3/A4 组合包的路径、权重字节数、SHA、Actor/WM/Critic 张量数与能否接续在线优化器见[复核清单](../results/b0/recovery_c_s0_stance_integrated_r1/recovery_inventory.json)。这些离线几何拟合只产生新的 Actor 包，不生成在线 replay、优化器或 RNG 状态；后续真实 H32 在各自 run 单独保存恢复边界。
