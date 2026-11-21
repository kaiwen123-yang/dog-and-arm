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
