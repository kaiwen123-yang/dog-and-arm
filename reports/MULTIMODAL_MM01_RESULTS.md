# MM-01 多模态全身开门实验结果

2026 年 11 月 25 日，北京时间。方法为 `M1Piper-Multimodal-v1`。在原生 MuJoCo 3.3.0 自由底盘 M1、Piper H、官方平行夹爪、腕相机和被动铰链门上，监督策略和加入 H32 世界模型优化的策略分别 **0/12**。24 案均未接触门。模型式分支在一个验证回合完成底盘驶近，随后因自碰终止。新增学生完整成功视频为 0。桌面实机部署继续由用户择时，本轮真实运动命令为 0。[逐案判定](../results/multimodal/mm01_20261125/physics/physics_cases.json) · [运行清单、权重及原始数据位置](../results/multimodal/mm01_20261125/manifest.json)

## 完整物理评测

每格 4 案，来自前拉、背推两侧各执行 15° 和 25°。同一门侧的两种指令使用相同初始状态、首帧 RGB、深度和本体信号。两个分支也在同初态下配对。两支检查点均冻结后读取保留测试场景结果。数据划分为三个训练场景、一个验证场景和一个独立测试场景。本轮使用一个共同训练种子，表中报告实际次数。[场景清单](../config/multimodal/scenes.json) · [分组结果与初态核对](../results/multimodal/mm01_20261125/physics/physics_summary.json)

| 冻结学生 | 已见名义场景 | 验证场景 | 保留测试场景 | 完整成功 | 驶近完成 | 接触门 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 多模态监督续训 | 0/4 | 0/4 | 0/4 | **0/12** | 0/12 | 0/12 |
| 同一父策略＋H32 世界模型优化 | 0/4 | 0/4 | 0/4 | **0/12** | 1/12 | 0/12 |

每个回合从原始停车点起步。策略每 20 ms 在自己产生的后继状态上重新决策。独立裁判每 2 ms 核对底盘驶近和停稳、到达把手、双指抓持、目标角、持稳、释放、撤臂、释放后保持、收臂、底盘退出和最终停稳，共 12 个顺序事件。到角容差 ±2°，持门稳定要求连续 0.5 s，最终停稳要求连续 3 s。裁判使用真实接触、位姿和门角，学生只收到传感输入。四个名义教师复核回合均通过全部 12 项。[评分规则](../config/multimodal/evaluation.json) · [教师对新裁判的物理复核](../results/multimodal/mm01_20261125/data/independent_judge_teacher_checks.json)

监督分支的 12 案全部在驶近阶段终止，原因是 6 次自碰、3 次 J2 越限、3 次 J5 越限。H32 分支 11 次在驶近、1 次在停稳终止，共 6 次自碰、2 次 J2 越限、4 次 J5 越限。H32 验证前拉 25° 在 9.056 s 到站，9.330 s 自碰。视频从该回合第 0 子步连续渲染至第 4,665 子步。教师对照视频来自本轮名义前拉 15° 的完整 51.174 s 物理轨迹。两段均为 1080p、25 fps，已核验全帧解码和显示时间戳。[H32 学生失败回合](../results/multimodal/mm01_20261125/videos/wm_validation_pull_25_failure_1080p.mp4) · [P6 教师完整成功回合](../results/multimodal/mm01_20261125/videos/teacher_pull_15_1080p.mp4)

## 数据、目标与信息来源

教师可行性筛选先于正式采集。在同一前拉初态上，P6 对 15° 和 25° 指令分别达到 14.811° 和 24.849°。同一背推初态分别达到 15.084° 和 25.090°。四案均完成释放、收臂和退出。另行复核的前拉 60° 为旧能力参照。随后冻结两个目标、容差、五个场景和 24 条正式采集清单。场景变化包括停车偏移、初始航向、门初角、摩擦/阻尼和面板外观。[可行性和采集前登记](../results/multimodal/mm01_20261125/data/teacher_registration.json)

| 正式 P6 数据 | 回合 | 完整成功 | 有效 20 ms 转移 | 同时刻腕部 RGB-D 帧 |
| --- | ---: | ---: | ---: | ---: |
| 训练 | 16 | 12 | 38,256 | 7,661 |
| 验证 | 4 | 4 | 10,781 | 2,159 |
| 测试 | 4 | 4 | 10,661 | 2,134 |
| 合计 | 24 | 20 | 59,698 | 11,954 |

20 条常规轨迹全部完成。其余 4 条为预先登记的训练扰动，2 条持续打开夹爪导致失握，2 条瞬时打开后重新闭合触及门受力上限。失败动作保留给世界模型。独立补采的四条较缓卸载均先失去双指同时接触 60–88 ms，恢复名义控制后首个 20 ms 区间全程重获双指接触，最终均完成开门。该补采集独立于本轮正式配对。[逐回合数据](../results/multimodal/mm01_20261125/data/teacher_dataset.json) · [分割、初态和指令配对](../results/multimodal/mm01_20261125/data/teacher_data_summary.json) · [恢复逐拍证据](../results/multimodal/mm01_20261125/data/recovery_evidence.json)

旧 546 维混合 u1 单独贡献一条原生背推 25° 成功示范。其控制来源含未来参考前馈、继承的 15,000 次动作 BC 和解析站姿补偿。按原归档清单核验六组数组后，从已积分状态合成重渲 544 张腕部帧，沿用原始请求与执行动作，提供 2,719 个合格标签。历史单步伺服量缺失的位置保留缺失标记。该回合与 P6 的 32,307 个训练标签合计 35,026 个，共 17 个训练来源。[混合回合原数组及来源摘要](../results/multimodal/mm01_20261125/data/mixed_source.json) · [重复转换入口](../scripts/multimodal/import_mixed.py)

学生使用 64×64 腕部 RGB、米制深度和有效掩码、10 拍关节编码器/夹口/重力方向/角速度历史、前次实际执行动作、任务文本、因果图像年龄和从本次复位起算的传感时间。图像按 10 Hz 同步仿真曝光，在 50 Hz 决策时取最近可用帧，复位时重复首个实测状态。动作输出为 12 路腿位置、4 路轮速、6 路臂位置和夹口全宽。归一化、逐通道本体到动作的线性项及剩余动作预测均从训练集学习。真值门角、TCP 系把手、接触和阶段用于监督、教师或裁判。学生前向与 H32 想象均通过专用传感接口，部署时没有教师接管。RGB、深度和文本编码器均从头训练，参数共 448,264。[实际腕部图](../results/multimodal/mm01_20261125/data/wrist_rgbd_p6.png) · [学生实现](../learning/multimodal/actor.py) · [数据读取](../learning/multimodal/dataset.py)

## 对照预算与世界模型

共同学生完成 12,000 次、每批 256 个样本的监督更新。两支恢复相同的模型、AdamW 状态和数据归一化参数，冻结相同的视觉和文本编码器，再各做 512 次、每批 256 的 Actor 更新。两支用相同顺序抽取 131,072 条示范动作，比较的共同父及批序列摘要一致。[训练登记](../config/multimodal/actor_run.json) · [实际配对预算和权重核对](../results/multimodal/mm01_20261125/actor/comparison.json)

| 计算项目 | 监督续训 | 加入 H32 优化 |
| --- | ---: | ---: |
| 续训 Actor 更新 / 每步 BC 样本 | 512 / 256 | 512 / 256 |
| 额外想象动作查询 | 0 | 524,288（512 × 32 个起点 × 32 拍） |
| 实测 Actor 更新耗时 | 4.53 s | 127.13 s |
| Actor 更新峰值已分配 GPU 显存 | 408.19 MiB | 409.40 MiB |

模型支另有 2,400 次教师世界模型更新、400 次加入混合和学生交互的更新，以及 600 次视觉特征投影更新。共用父策略在四个训练场景任务中产生 3,255 个有效转移，动作无 BC 标签。世界模型最终使用 21 条训练回合、44,230 个有效转移、44,104 个合法 H7 起点。两支共享示范数据和动作监督预算，世界模型使用的无标签交互与额外计算单列。本轮新增 Critic 更新为 0。[世界模型配方](../config/multimodal/wm.json) · [交互数据、训练与验证](../results/multimodal/mm01_20261125/wm/interaction_update.json)

想象中用固定来源的 GenCoord 转移更新本体，用学习到的局部状态推进门角、门速、TCP 系把手、接触和腕部特征。每拍重新查询 Actor，每五拍向 Actor 更新一次预测的视觉特征。模型以起点的真实传感观测初始化，后续轨迹由模型产生。H32 一次方向导数为 0.00039505，三种步长的中心差分在 0.00039453–0.00039628。四条独立验证轨迹的 768 个 H32 窗口中，门角 MAE 为 0.771°，把手位置误差为 31.65 mm，夹口 MAE 为 0.905 mm。腕部池化特征 RMSE 为 0.05081，同一组保持起帧的参照为 0.03953。24 对局部原生动作扰动的轮速、J2 和夹口响应方向均相符，模型相对物理响应幅值的中位比约为 0.56、0.28 和 0.36。这些诊断的覆盖范围为三个动作通道和登记的局部状态。[短时优化和数值核验](../results/multimodal/mm01_20261125/wm/calibration.json) · [物理扰动逐案对照](../results/multimodal/mm01_20261125/wm/action_response.json)

在 RTX PRO 6000 Blackwell 上，代表回合的腕部采集达到 104.7 次决策/s，单个 EGL 工人峰值约 201 MiB。正式采集使用六个进程，采样到合计峰值 1,206 MiB，24 案耗时 119.25 s。共同 BC 更新期间峰值 500.60 MiB。保留的实际预算和单独丢弃的测速更新均已记账。运行使用现有的 25 核、120 GiB 内存配额，训练与渲染依吞吐交错，后台任务没有强制墙钟退出器。[资源实测](../results/multimodal/mm01_20261125/data/teacher_resources.json) · [预算总表](../results/multimodal/mm01_20261125/manifest.json)

## 换指令、失败诊断与独立补训

验证场景中，教师前拉两目标的首个可测动作差异出现在 27.30 s，背推出现在 26.68 s。当拍的腕部图像、深度和本体历史仍相同。冻结相同观测只换指令时，监督学生最大动作变化分别为 0.000123 和 0.0000586（归一化动作）。在 4,096 个验证状态上，监督分支屏蔽 RGB、屏蔽深度、替换同侧目标、重复最近本体帧四种操作产生的平均绝对动作变化分别为 0.000084、0.000451、0.0000164 和 0.000412。两支的六对物理指令对照各自末态门角差均为 0°。测到的输入响应尚不足以产生不同的开门结果。[监督策略输入干预](../results/multimodal/mm01_20261125/actor/supervised_evaluation.json) · [同初态、同观测的动作分歧](../results/multimodal/mm01_20261125/actor/supervised_export.json) · [物理指令对照](../results/multimodal/mm01_20261125/physics/physics_summary.json)

共同父策略在四次训练场景闭环中都在驶近阶段触及 J2 下限。前拉 15° 在第 5 秒的 J2 实测/命令为 0.654/0.644 rad，同阶段 P6 的两个值均约为 0.800 rad。固定第 3 秒其余输入，只改变 J2 本体历史，输出物理目标的局部斜率约为 0.998 rad/rad。该状态上，目标随已经偏离的实测关节一同变化。正式失败还涉及其他关节与自碰。[共同父四案](../results/multimodal/mm01_20261125/physics/development_cases.json) · [回放及局部响应](../results/multimodal/mm01_20261125/actor/feedback_diagnosis.json)

为验证这一个现象，另从共同父训练一个候选。在 3,255 个已访问训练状态上增加 P6 驶近阶段六臂绝对归位目标，原 17 源动作监督继续使用。新增 2,400 次更新，没有使用测试场景。在原四条记录上，J2 命令的 P95 绝对误差从 0.769–0.800 rad 降至 0.00375–0.00678 rad。重新闭环后，同钟且两策略都仍在驶近的时段内，四案该误差均升高。该候选完整成功 **0/8**，其中一案到站后停稳超时，其余 7 案在驶近终止。一次与门框发生意外接触，双指抓持 0/8。这个实验说明对已采状态的局部纠正未能稳定策略之后访问的状态。[补训登记与原始权重位置](../results/multimodal/mm01_20261125/approach/registration.json) · [逐案同钟与固定观测对照](../results/multimodal/mm01_20261125/approach/comparison.json)

## 复测与接续

第二平台独立树为 `/home/kaiwen/research/dog-and-arm-mm01`，AutoDL 代码目录为 `/root/autodl-tmp/dog-and-arm-mm01`，完整训练检查点、优化器状态和原始数组在 AutoDL 的 `/root/autodl-tmp/mm01-20261125`。两份学生部署包分别在 384 个验证状态和 72 拍连续在线控制上与原训练包的 CPU 输出逐值一致。第二平台从 GitHub 取回监督部署包，实际重跑名义前拉 15°，第 4,421 子步触及 J2 下限，AutoDL 对应回合在第 4,439 子步触及同一下限。这是单独的跨主机复测。[第二平台逐案记录](../results/multimodal/mm01_20261125/physics/dev2_supervised_recheck.json) · [监督部署包](../results/multimodal/mm01_20261125/actor/supervised.pt) · [H32 部署包](../results/multimodal/mm01_20261125/actor/model_optimized.pt) · [校准后的世界模型](../results/multimodal/mm01_20261125/wm/wm_objective.pt)

在第二平台独立树中，以下命令会将新的单案物理复测写入单独目录。原生 3.3.0 负责积分，冻结策略在现有 PyTorch 环境内前向。

```bash
cd /home/kaiwen/research/dog-and-arm-mm01
export MUJOCO_GL=egl PYTHONPATH=. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
mkdir -p results/raw_large
OUT=$(mktemp -d "$PWD/results/raw_large/mm01_recheck_XXXXXX")
.venv/bin/python -m scripts.multimodal.evaluate \
  --checkpoint results/multimodal/mm01_20261125/actor/supervised.pt \
  --branch supervised_recheck --scene tr_nominal --side pull --goal 15 \
  --output "$OUT"
```

共同 BC 的实际配方为 `train_actor --stage initial --steps 12000 --batch-size 256 --seed 701 --lr 0.0005 --membership config/multimodal/actor_run.json`。四次回灌使用 `evaluate_suite --branch common_12000 --feedback`。监督和 H32 两支使用 `train_actor --stage paired --steps 512 --batch-size 256 --seed 1701 --lr 0.0001`，只在 H32 分支加载校准的世界模型。两支完整物理评分使用 `evaluate_suite`。精确路径、世界模型两段的逐回合成员参数和额外补训恢复命令均已保存。[配对初始化与采样](../config/multimodal/actor_run.json) · [世界模型训练、恢复与 H32 命令](../results/multimodal/mm01_20261125/wm/package_and_recovery.json) · [补训恢复入口](../results/multimodal/mm01_20261125/approach/comparison.json)

早期 13 个开发、共同父或监督回合所存公开请求已经过策略内部限幅。现已用逐拍真实传感输入和同一冻结 CPU 检查点恢复底层限幅前输出，重新限幅后与原物理命令逐值相同。后续 24 个 AutoDL 学生回合在线保存底层请求。两个阶段都保留真实执行动作及物理目标。[正式回合动作核对](../results/multimodal/mm01_20261125/physics/formal_requests.json) · [早期开发与回灌](../results/multimodal/mm01_20261125/physics/parent_requests.json) · [补训回合](../results/multimodal/mm01_20261125/physics/repair_requests.json)

下一集中轮从底盘驶近与驻臂保持的闭环偏离入手。在训练场景中随新学生的实际访问轨迹连续查询全身教师，记录当拍纠正目标、执行动作与物理后继。用相同观测和预算检验关节与轮速直连对回正的影响，再从原始初态复测停稳、接触和两目标分化。MM-01 的保留测试场景已经揭晓，后续对新方法的盲测另留场景。桌面部署保留独立入口。[接续启动词](../prompts/NEXT_RUN.txt)
