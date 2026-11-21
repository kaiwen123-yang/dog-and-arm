# B0 教师、参考与交互记录

2026-11-21 在用户 Linux 工作区用 native MuJoCo 3.3.0、2 ms 步长运行。整机使用 `rail_bridge_front60_v2`，保留一个自由根、双真实手指、夹指联动和被动铰链。[参考索引](../data/b0/reference_manifest.json) · [完整 episode 清单与用途](../data/b0/episode_index.jsonl) · [逐条物理核对](../data/b0/native_teacher_checks.json)

## 历史原始数据核对

读取最终清单中 40 条记录对应的真实文件头。每条均有 182 列的 25 Hz `timeseries.csv`、20 列的接触点 CSV、8 列的 500 Hz 六臂余量 CSV，以及配置和工程结果。读取根目录为 `results/raw_large/p6/rail_bridge_front60_v2_20261120T133724Z/`。P5 的 50 Hz 记录另按其实际列审阅。[P6 条件与原始路径映射](../results/p6/rail_bridge_front60_v2_20261120T133724Z/conditions.csv) · [P5 原始采样代码](../scripts/p5_free_base.py)

| 来源 | 直接可用 | 可按明确几何计算 | 进入 B0 所缺的字段或时序 |
| --- | --- | --- | --- |
| P5 50 Hz | 23 个被驱动关节位置/速度/力，根位置、欧拉角、线速度和 yaw rate，轮载和离散滑动 | 欧拉姿态转根四元数 | 完整根角速度、第二指实际位置/速度、每步执行的混合物理目标、控制与逐子步变化 |
| P6 25 Hz | 根姿态和世界系双速度、23 通道实际关节/速度/ctrl/effort、夹口、门角速、实际 TCP/把手位姿、接触点和力 | 主动指与开口可还原同采样点的从动指位置。根刚体旋转可换算角速度坐标系 | 只得到每隔 20 个物理步的瞬时命令。第二指真实速度和其余子步命令缺失。P6 任务环与 B0 的 20 ms 恒定动作时序不同 |
| P6 500 Hz | 控制阶段和六轴有符号限位余量 | 已知角度与边界时可复核余量 | 表中未存完整关节状态、门状态、动作或下一状态 |
| 汇总/影像 | 条件、物理事件、工程成功及可见动作 | 从时序定位训练应覆盖的接触阶段 | 无逐步控制输入和全身速度 |

因此只用往期文件定位教师、条件与原始证据。三个运动参考在被动门场景中重新产生。两条门轨迹均为新目录中的 C01，历史 C02–C20 保持原有记录。

## 实际采集

运动教师复用冻结 P5 的目标臂姿增量 `[8,10,8,0,0,0]°`、五次平滑曲线、四轮轮速分配及 0.07 m/s 直行速度。为同时覆盖移动变臂姿和停车收臂，新的 7 s 轨迹安排了重叠的动作时段，夹口从 40 mm 开至 60 mm 再收回。被动门全程保留在场景内。每个真实 20 ms 转移持有同一个 23 维物理目标。每个 2 ms 子步按非轮伺服的上一求解偏置 `qfrc_bias/kp` 写入 ctrl，主动指目标为开口的一半，再执行 `mj_step`。保存实际 ctrl/force、混合物理目标及其在 B0 裁剪后坐标中的编码。教师没有网络原始输出。独立 WM 验证轨迹在整个 episode 加入 seed 13097 的分块动作扰动，每 200 ms 更换一次。[采集入口](../scripts/b0/collect_reference.py) · [训练与评测共用的具名映射](../learning/b0/physics.py)

| 本轮 native 教师 episode | 时长 | 物理结果 |
| --- | ---: | --- |
| 支撑伸收臂 | 7 s | J1/J2/J3 最大实际运动 8.000° / 10.000° / 8.000°，根水平净位移 0.024 mm，终速 0.256 mm/s |
| 移动变臂姿 | 7 s | 前进 0.27650 m，最大水平速度 72.90 mm/s，终速 0.869 mm/s |
| 减速停车并收臂 | 7 s | 前进 0.16604 m，最大水平速度 72.58 mm/s，终速 0.520 mm/s |
| WM 独立验证，移动变臂姿并扰动 | 7 s | 前进 0.27768 m，终速 2.074 mm/s。排除在训练和参考库外 |
| 前拉 C01 | 74.276 s / 37,138 步 | 门终角 60.05158°，实际完成两个 3 s 停车窗口 |
| 背推 C01，95° | 54.244 s / 27,122 步 | 门终角 25.081°，实际完成两个 3 s 停车窗口 |

门参考由冻结版本 `86ade863de712dd6cd402714229b12b1bdae5b13` 的 P6 控制逻辑产生。给已有循环增加可选读数回调，仅在 B0 采集时读取物理步起止状态、实际指令和已求解接触。预偏置物理目标由实际发出的 ctrl 与同一步使用的偏置精确反算，双指开口按完整宽度存储。每个 2 ms 目标均有记录。P6 的六轴目标 10 ms 更新，腿轮命令 2 ms 更新，因此这两条门参考仅作为动态参考和接触段来源，不进入 20 ms 恒定动作 WM replay。门角和机器人取自同一 episode。末段前拉剩 8 个子步，背推剩 2 个子步；两段都保留精确终态，并在数组 `valid_full_interval` 标记。[冻结教师与采样位置](../scripts/p6_single_door.py) · [门阶段、终角和连续窗口](../data/b0/native_teacher_checks.json)

## 回放和数据使用

全量未压缩 NumPy 数组按每条 episode 单独保存在 `results/raw_large/b0/native_teacher_20261121_r1/<episode>/`。每条含逐步元数据、原始状态、世界系根速度、TCP/把手/铰链坐标、夹口和两指约束残差；`substeps/` 保存 500 Hz 前后完整状态、实际 ctrl/力、轮载、滑动、指载、门反力、非预期接触、臂限位及执行器饱和标记。四元数为 wxyz，根原始 qvel 前三项为世界系线速度，接着三项为机体系角速度。训练时从前置 `qpos[k], qvel[k]`、已执行 `action_clipped[k]` 指向 `qpos[k+1], qvel[k+1]`。最后一次转移的 terminated 标记保留，窗口限定在同一 episode 内。大数组留在本机，索引和物理核对表提交仓库。[读取函数](../learning/b0/reference.py) · [数据约定](../docs/B0_DATA_MODEL_CONTRACT.md)

逐条检查了 50 Hz 状态与 500 Hz 准确步号一致、终态保留且仅一个终止边界。三个训练候选各有 350 个真实转移，独立扰动验证另有 350 个。用学习物理入口的 NativePlant 重新执行四条轨迹的全部编码动作，逐个 20 ms 边界与原采样比较，测得误差见逐条核对表。这验证采集与具名动作映射；策略物理表现和研究后端结果单独记录。[逐条核对](../data/b0/native_teacher_checks.json)

实际命令（在项目根路径运行，同一名字已存在时入口会拒绝覆盖）。

```bash
bash scripts/project_env.sh python scripts/b0/collect_reference.py support moving_arm park moving_arm_wm_validation --output results/raw_large/b0/native_teacher_20261121_r1
bash scripts/project_env.sh env OPENBLAS_NUM_THREADS=1 python scripts/b0/collect_reference.py pull --output results/raw_large/b0/native_teacher_20261121_r1
bash scripts/project_env.sh env OPENBLAS_NUM_THREADS=1 python scripts/b0/collect_reference.py push --output results/raw_large/b0/native_teacher_20261121_r1
bash scripts/project_env.sh python scripts/b0/collect_reference.py --output results/raw_large/b0/native_teacher_20261121_r1 --index-dir data/b0
```

## 同一真实命令在两种物理后端的响应

独立训练环境已用 `bash scripts/b0/env.sh python -u -m scripts.b0.compare_reference --output results/b0/backend_r1/native33_teacher_vs_mjlab.json` 执行三个 7 s 回合。每个研究后端世界从对应 native 3.3.0 参考的初始完整状态开始，连续重放 350 个实测动作，使用相同的 2 ms 固定伺服。下表比较研究后端的 MuJoCo 3.16.0/Warp 与原 native 3.3.0。每个世界完成 3,500 个物理步，三个被动门均维持 0°。[完整逐案数据](../results/b0/backend_r1/native33_teacher_vs_mjlab.json)

| native 教师目标 | 根位置 RMSE（mm） | 根姿态 RMSE（°） | TCP RMSE（mm） | 腿角/臂角 RMSE（rad） | 轮速 RMSE（rad/s） |
| --- | ---: | ---: | ---: | ---: | ---: |
| 支撑伸收臂 | 0.746 | 0.00425 | 0.779 | 0.001974 / 0.000012 | 0.02349 |
| 移动变臂姿 | 3.993 | 0.00557 | 3.990 | 0.001321 / 0.000040 | 0.03437 |
| 减速停车并收臂 | 2.383 | 0.00501 | 2.387 | 0.001307 / 0.000036 | 0.02965 |

根、关节和 TCP 按全部 351 个 50 Hz 状态边界对齐。另按 5 Hz 从研究后端导出已求解接触，在同一子步按 FAR/FBL/RAR/RBL 对照真实轮载。三条各 35 次采样，按 1 N 分类的四轮支撑均与 native 一致，逐轮法向力 RMSE 为 0.966–1.587 N，非预期接触采样力峰均为 0 N。3.16/Warp 的步进检查没有报告臂限位、持续饱和或失稳。这些数值覆盖自由运动教师回合，双侧操作使用下节的完整事件与子步数据。[对照入口](../scripts/b0/compare_reference.py)

## 训练后端完整门任务的教师可行性

在同一固定 mjlab/Warp 后端，用 C01 前拉和 95° 背推分别连续执行一次冻结 P6 控制。每个回合只在初态设置自由根和门角。随后唯一积分入口为 `Simulation.step`，主机用 `get_data_into` 读回每个求解步的状态、真实接触和执行力，供原 P6 事件判据与下一步教师反馈读取。此处保留 P6 500 Hz 基座命令和 100 Hz / 新阶段六轴命令，记录在新目录的 `substeps/`。从始至终由教师控制，只确认训练物理后端可以完成两种接触任务。[训练后端教师入口](../scripts/b0/check_door_teacher.py) · [前拉事件与物理核对](../results/b0/backend_r1/pull_teacher.json) · [背推事件与物理核对](../results/b0/backend_r1/push_teacher.json)

| 指标 | 前拉 C01 | 背推 C01 |
| --- | ---: | ---: |
| 物理步数 × 2 ms | 36,863 × 2 ms | 27,043 × 2 ms |
| 终态门角 | 60.04931° | 25.07761° |
| 六轴逐步最小限位余量 | 1.504° | 16.880° |
| 抓持最大偏移 | 2.693 mm | 2.611 mm |
| 门对机器人的合力峰 | 2.698 N | 1.561 N |
| 退臂后 / 终点独立连续保持步数 | 1,500 / 1,500 | 1,500 / 1,500 |
| 两窗口最大平速（mm/s） | 0.269 / 4.992 | 0.178 / 4.911 |
| 两窗口最大偏航速率（°/s） | 0.035 / 0.105 | 0.019 / 0.070 |

用保存的 500 Hz 子步独立复读两个保持窗口。两侧四个窗口的指载均为 0 N，最小单轮载荷分别高于 100 N（前拉）与 89 N（背推）。全程无超过 P6 判据的非预期接触。Warp 的 float32 时钟分别累加到 73.70875 s 和 54.07954 s，步数乘 2 ms 分别为 73.726 s 和 54.086 s。物理步号对齐和保持窗口按实际步数计。主机 MjData 的 warning 向量没有覆盖所有 GPU 运行时警告。启动时 Warp 提示 CAPSULE–MESH 的 MULTICCD 最多生成一个接触点，此约束保留在运行记录中。[前拉核对](../results/b0/backend_r1/pull_teacher.json) · [背推核对](../results/b0/backend_r1/push_teacher.json)

实际命令如下。两次完整数据及其配置与逐步记录保存在 `results/raw_large/b0/research_teacher_20261121_r1/`。

```bash
bash scripts/b0/env.sh python -u -m scripts.b0.check_door_teacher pull --output results/raw_large/b0/research_teacher_20261121_r1/pull --evidence results/b0/backend_r1/pull_teacher.json
bash scripts/b0/env.sh python -u -m scripts.b0.check_door_teacher push --output results/raw_large/b0/research_teacher_20261121_r1/push --evidence results/b0/backend_r1/push_teacher.json
```

## 完美末速度下的 20 ms 位置积分误差

用已记录的每个真实起点执行一次固定 B0 GenCoord 积分，`dt=0.020`、`c=0.55`。离线把真实末速度转换到起点机体系，构造精确速度增量，再调用正式的 `RobotRepresentation.apply_prediction`。末端机身四元数只用于把原始末端角速度换算到世界系；计算得到的下一姿态只由起点姿态和速度积分产生。TCP 从两个姿态分别做 MuJoCo FK。每步独立重新取真实起点，未改模型、未更新权重，真实末速度未进入实际策略或 WM 的训练输入。[可复现入口](../scripts/b0/integration_oracle.py) · [完整逐块误差与条件分组](../results/b0/native_replay_audit_r1/gencoord_velocity_oracle.json)

| 来源 | 转移数 | 根位置 RMS（mm） | 根姿态 RMS（°） | 六臂角 RMS（°） | 两指位置 RMS（mm） | TCP 距离 RMS（mm） |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 教师支撑伸收 | 350 | 0.024 | 0.00088 | 0.00383 | 0.060 / 0.078 | 0.044 |
| 教师移动变姿 | 350 | 0.024 | 0.00087 | 0.00382 | 0.060 / 0.078 | 0.045 |
| 教师停车收臂 | 350 | 0.024 | 0.00090 | 0.00440 | 0.075 / 0.097 | 0.049 |
| 独立扰动验证 | 350 | 0.026 | 0.00410 | 0.01589 | 0.153 / 0.245 | 0.104 |
| 初轮策略触发失败的转移 | 31 | 0.604 | 0.431 | 6.136 | 7.272 / 8.994 | 9.619 |
| 初轮策略其余转移 | 289 | 0.795 | 0.384 | 7.555 | 9.558 / 10.380 | 10.471 |

初轮策略数据取自 seed0 两个真实在线采集块；两个截断标记与失败标记分开保留。31 个失败步中有 29 个步的六臂最大初速至少为 5 rad/s，单步最大臂命令与真实初始关节角之差的 RMS 为 1.163 rad。独立扰动教师的相应两项 RMS 为 0.111 rad/s 和 0.0109 rad。可见固定积分式在这两类实际动作分布上的精度差异很大。此实验给出“末速度已知”这一特定条件下的位置误差；模型可在位置和末速度两类误差之间权衡。逐步诊断无法单独归因完整轨迹的漂移。[分组与末速度数值残差](../results/b0/native_replay_audit_r1/gencoord_velocity_oracle.json)

```bash
bash scripts/b0/env.sh python -m scripts.b0.integration_oracle --output results/b0/native_replay_audit_r1/gencoord_velocity_oracle.json
```
