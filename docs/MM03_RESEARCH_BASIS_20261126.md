# MM03 文献依据：稳定低层、完整任务与可微优化

调研截至 2026-11-26。只用原始论文、正式出版记录、作者项目页和官方代码。以下是针对 M1＋Piper 当前失败的设计依据；不把其他机器人的成功率、软约束或局部稳定性证明直接外推到本平台。每篇阅读范围为主要方法、实验与相关附录，代码核查为可用性和关键实现，不声称外部仓库逐字节审计。

## 1. 立即用于 MM03 的主依据

| 工作 | 已核实身份与原文 | 机制及本项目用法 | 边界 |
| --- | --- | --- | --- |
| SLIM / Learning Multi-Stage Pick-and-Place with a Legged Mobile Manipulator | IEEE RA-L 2025；[期刊版本](https://arxiv.org/abs/2509.03859)、[完整技术报告](https://arxiv.org/html/2501.09905v4)、[作者项目](https://horizonrobotics.github.io/gail/SLIM/) | 带臂训练并冻结低层，视觉/语言高层发送前进、转向及臂爪命令；学习零速静站，完整教师与学生数据并用。支持本项目 9 维任务层＋16 维轮腿层。 | Go1＋WidowX 单腕 RGB，主要抓取搬运；附录低层 10 种子选 3 个继续，不能忽略选择过程。高低层异步经验不表示本项目已发生实时延迟故障。 |
| UMI-on-Legs: Making Manipulation Policies Mobile with Manipulation-Centric Whole-body Controllers | CoRL 2024，PMLR 270 于 2025 出版；[正式页](https://proceedings.mlr.press/v270/ha25a.html)、[全文](https://arxiv.org/html/2407.10353v1)、[官方代码](https://github.com/real-stanford/umi-on-legs) | 任务坐标系末端轨迹接全身跟踪器，近时参考与预览支持身体预先协调。借鉴可跟踪的中间接口，后续比较任务系与身体系参考。 | 依赖位姿估计，缺通用碰撞/力反馈；不是 M1 轮地控制器。当前不重建 UMI 采集链。 |
| First Order Model-Based RL through Decoupled Backpropagation（DMO） | CoRL 2025，PMLR 305；[正式页](https://proceedings.mlr.press/v305/amigo25a.html)、[全文](https://arxiv.org/html/2509.00215)、[代码](https://github.com/machines-in-motion/DMO_code) | 模拟器负责前向，学习模型负责局部反向导数。无 critic 的 DMO-BPTT 适合密集短程目标。MM03 保持教师轨迹损失与 BC，隔离前向累积误差。 | 真实仿真成本增加，模型 Jacobian 仍近似；本项目改造称 DMO-style trajectory imitation，不冒称完整复现。 |
| PWM: Policy Learning with Multi-Task World Models | ICLR 2025；[正式页](https://proceedings.iclr.cc/paper_files/paper/2025/hash/240ea1741b205ea295721d55184ac43b-Abstract-Conference.html)、[全文](https://arxiv.org/html/2407.02466v3)、[代码](https://github.com/imgeorgiev/PWM) | 讨论模型平滑性与一阶优化质量；提示不能仅按状态预测 MSE 判断模型是否适合优化。MM03 加入真实方向响应和梯度尺度诊断。 | 旧稿名称 Large World Models 与正式 Multi-Task 不同；并非门任务成功依据。 |
| Stable-BC: Controlling Covariate Shift with Stable Behavior Cloning | IEEE RA-L 2025；[全文](https://arxiv.org/html/2408.06246v1)、[作者页](https://collab.me.vt.edu/Stable-BC/)、[代码](https://github.com/VT-Collab/Stable-BC) | 关注偏离示范后的闭环误差能否收缩。MM03 用扰动恢复和零速停止检验稳定低层，而非只优化动作 MSE。 | 连续局部 Jacobian 条件不能直接当离散接触系统的全局保证；本轮先不叠加全身特征值正则。 |

## 2. 2025–2026 补充：可借什么、不直接搬什么

### Coupled Local and Global World Models for Efficient First Order RL

[2026-10-11 v3 全文](https://arxiv.org/html/2602.06219v3) · [作者项目](https://coupled-global-local-wm-rl.pages.dev/)。作者项目标 CoRL 2026。大视觉模型作前向，小模型作梯度近似；Go2 高层给既有运动策略发送 5 Hz 身体速度，G1 也使用已有全身跟踪器。其 H16/5 Hz 为 3.2 s，不等于本项目 H32/50 Hz 的 0.64 s。它支持控制分层和前向/反向分工的方向，当前不把大型视频模型设为 MM03 前置。项目仍标 code release soon，未确认可运行官方整套代码。

### Rambo: RL-Augmented Model-Based Whole-Body Control for Loco-Manipulation

IEEE RA-L 2025；[全文](https://arxiv.org/html/2504.06662v4) · [正式页](https://ieeexplore.ieee.org/document/11106746/) · [官方代码](https://github.com/catachiii/rambo)。接触力 QP 提供前馈，RL 学反馈修正。可借鉴稳定基准＋残差的分开比较；单有模型前馈也不自动成功。机器人主要用腿操作，无独立 Piper 和轮子；当前不移植其整个单刚体/点足接触求解器。代码许可 CC BY-NC 4.0，复用时保留来源与许可。

### Safe Whole-Body Loco-Manipulation via Combined Model and Learning-based Control

ICRA 2026，MERL TR2026-072，2026-06-04；[官方全文](https://www.merl.com/publications/docs/TR2026-072.pdf)。臂导纳控制器进入腿策略的训练闭环，参考治理器调整不可执行请求，并使用速度估计。可借鉴任务请求与身体能力之间的接口。论文使用腕部六维 F/T，主要结果含约 25 s 跟踪轨迹；不能据此增加当前传感器采购前置或宣称本平台获得同样安全保证。

### Compliant Residual DAgger: Improving Real-World Contact-Rich Manipulation with Human Corrections

NeurIPS 2025；[完整论文](https://arxiv.org/html/2506.16685v5) · [作者项目](https://compliant-residual-dagger.github.io/) · [代码](https://github.com/yifan-hou/cr-dagger)。纠正以连续残差、柔顺接口和力反馈接入，并保留无需纠正的数据。MM02 已有真正的学生在轨补标，“再加入 DAgger”不构成新方案；可借的是纠正方式、零残差区域和前后段数据覆盖。其接触/力传感条件不同，不用来解释当前接触前支撑首败。

### Whole-body Motion Control of an Omnidirectional Wheel-Legged Mobile Manipulator via Contact-Aware Dynamic Optimization

[2025-09-17 预印本全文](https://arxiv.org/html/2509.14010v1)。可借鉴显式轮地滚动与接触建模；其平台有四个独立转向关节，M1 当前是固定轴滑移转向。软摩擦惩罚不是硬安全保证，所示真实旋转/下蹲不能替代开门验证。当前不重写完整 DDP 控制系统。

### FT-WBC: Learning Fault-Tolerant Whole-Body Control for Legged Loco-Manipulation

[2026 年论文](https://arxiv.org/abs/2606.24466) · [作者项目](https://ft-wbc.github.io/)。作者页确认 CoRL 2026 录用；官方仓仍为 code coming soon。可借姿态请求适配思想，但其核心是执行器故障，真实任务仍主要先走后操作。没有证据把 MM02 归为硬件故障，不列入当前主实现。

## 3. 与 SuperMimic 的真实关系

[SuperMimic: Scaling Humanoid Whole-Body Control with One Differentiable World Model](https://arxiv.org/abs/2610.28480)，CoRL 2026；[官方代码](https://github.com/HybridRobotics/supermimic)。其参考条件动作跟踪、Actor/Critic、在线模型数据和训练动作集，与本项目 RGB-D/语言门操作不同；论文未覆盖任意物体接触交互。MM02 的无 critic 教师轨迹匹配是自研配方。不能把未达到其效果归为一个已证明的“缺 critic”错误，也不继续把标准迁移当 MM03 的前置资格。

仍沿用可微模型策略优化的核心思想，但以真实物理成功和梯度用途为标准。DMO 提供了当前可实现的不同用法；未来若密集目标无法表达长期事件，可以单独研究 value bootstrap，首组对照不同时更换目标和 critic。

## 4. 本项目的设计推论与创新边界

直接采用：带臂零速稳定控制、部署可得状态估计、全程与分段数据并行、同父配对、模型前向/反向分离和物理方向核验。保留：未来任务坐标系短轨迹、接触感知残差、稳定性相关可行请求。暂缓：大型视频生成模型、完整 DDP/QP 重写、新硬件采购与实机运动。

分层、残差、DAgger、短 BPTT 和 DMO 都已有公开先例。可研究的项目贡献候选是：在轮腿臂接触任务中，依据支撑与感知置信度形成可执行任务接口，并使模型梯度优化稳定改善实际恢复和完整任务。它仍是假设，须由共同控制骨干、共同数据、多个种子和未见场景的对照支撑。

必要经典：[DAgger，AISTATS 2011](https://proceedings.mlr.press/v15/ross11a.html)；[SHAC，ICLR 2022](https://research.nvidia.com/publication/2022-05_accelerated-policy-learning-parallel-differentiable-simulation)。它们帮助解释数据分布与短视野价值估计，不替代当前平台实验。
