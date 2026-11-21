# B0 来源与运行环境

B0 以 O1 的发布源码、实际运行配置和依赖解析结果为起点。两份上游源码分别在 `vendor/b0/supermimic` 和 `vendor/b0/mjlab_research`。用户仓库的 `vendor/b0/o1` 仅提供历史配置与结果。三个固定提交、资产清单、工程控制版本、O1 runner 全部参数及实际结果已列入[来源锁](../config/b0/source_lock.json)。

| 读取材料 | 实际核对内容 |
| --- | --- |
| [O1 配置](https://github.com/kaiwen123-yang/Supermimic/blob/00e45d400e6bbe5f35d549f7fe08e5d014cb41a5/results/20261111-o1-official-lafan40-s0/actual_config.json) | seed 0，4096 环境，GenCoord，proprio/history10，motion/velocity slot 比例 1/0，latent32，replay_ratio16，return sampler，WM 和 Actor/Critic 的层宽、更新数与学习率 |
| [O1 来源](https://github.com/kaiwen123-yang/Supermimic/blob/00e45d400e6bbe5f35d549f7fe08e5d014cb41a5/results/20261111-o1-official-lafan40-s0/source_resolution.json) | 官方 `abc124c` 和研究版 `dd51a9f` 配对，旧算法锁中的 mjlab 1.5.0 已由 O1 实际解析的研究版 1.6.0 替代 |
| [O1 解析锁](https://github.com/kaiwen123-yang/Supermimic/blob/00e45d400e6bbe5f35d549f7fe08e5d014cb41a5/configs/o1_official_resolved.uv.lock)及[环境记录](https://github.com/kaiwen123-yang/Supermimic/blob/00e45d400e6bbe5f35d549f7fe08e5d014cb41a5/results/20261111-o1-official-lafan40-s0/environment.json) | 历史 CPython 3.13.18、Torch 2.14.0、Warp 1.18.0、MuJoCo/MuJoCo-Warp 3.16.0、rsl-rl-lib 5.5.2 |
| [O1 最终汇总](https://github.com/kaiwen123-yang/Supermimic/blob/00e45d400e6bbe5f35d549f7fe08e5d014cb41a5/results/20261111-o1-official-lafan40-s0/summary.json)和[复核](https://github.com/kaiwen123-yang/Supermimic/blob/00e45d400e6bbe5f35d549f7fe08e5d014cb41a5/results/20261111-o1-official-lafan40-s0/review_20261111.json) | G1 LAFAN40，最终 40/40，平均归一化回报 0.8744398924149845，32,294 次 Actor 更新 |
| [复现项目收尾](https://github.com/kaiwen123-yang/Supermimic/blob/00e45d400e6bbe5f35d549f7fe08e5d014cb41a5/docs/REPRODUCTION_CLOSEOUT_AND_DYNAMICS_STUDY_20261117.md) | O7 完成后 G1 复现已关闭。本轮在 dog-and-arm 创建新实验 |

源码中的 `WorldModelLearner.update` 从长度 8 的状态窗计算前 7 个动作的连续预测损失。 `ActorCriticPolicyLearner.update()` 自采起点，冻结动力学及表示参数，沿 `MultiTaskWorldModelEnv.step(actions)` 的四项返回做 BPTT，并拟合 GAE 价值目标。优化器按每个 Sequential 内部各 Linear 的权重使用 Muon，其余参数使用 fused Adam。O1 的三网络从零起步，B0 无需任何 G1 权重。[学习器源码](https://github.com/HybridRobotics/supermimic/tree/abc124c1bd5976341034668af3d12c087f2f1f55/src/supermimic/learners)

## 重建命令

在带有 Python 3.13 的工作站执行以下命令。脚本使用 `B0_PYTHON` 指定解释器，默认查找 `python3.13`。在本机创建环境时复用现有的解释器可执行文件。

```bash
B0_PYTHON="$HOME/miniconda3/bin/python3.13" bash scripts/b0/setup_env.sh
bash scripts/b0/env.sh python scripts/b0/runtime.py
```

安装脚本以固定 O1 lock 导出 Linux 运行依赖，使用 PyPI 下载所列版本，并以 editable 方式安装两个固定源码。首次创建的 Python 环境位于 `.venv-b0`，安装元数据和临时解析文件位于 `vendor/b0/o1-resolved`。训练入口应由 `scripts/b0/env.sh` 启动，以清除其他 Python 或动态库环境的路径影响。

## 本机执行结果

已在 Ubuntu 22.04 本机实际执行安装和 `python -m pip check`，129 个 B0 运行包解析、安装成功，依赖一致性检查通过。CPython 实际为 3.13.13，复用已有解释器创建独立 venv。当前硬件为 RTX 5080 Laptop、16,303 MiB 显存、580.159.03 驱动。历史 O1 的 96 GB 显存和 Python 3.13.18 仅用于来源对照。

本机的 `Simulation`、`MultiTaskWorldModelEnv`、`WorldModelLearner` 与 `ActorCriticPolicyLearner` 均从两个指定 checkout 成功导入。`bash scripts/b0/env.sh python scripts/b0/runtime.py --output config/b0/runtime_local.json` 已在真实 CUDA 设备上用官方 optimizer builder 完成一次参数更新，内部权重的最大绝对变化可在[运行记录](../config/b0/runtime_local.json)中核对。该记录列出完整已装包版本。学习策略的环境交互和任务成绩由 B0 训练及评估报告单独记录。
