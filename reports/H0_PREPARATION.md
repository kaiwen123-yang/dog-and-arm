# H0 回合准备记录

日期：2026-11-16（Asia/Shanghai）。本文件记录方案准备，不是实机验收报告。

## 已完成

- 在 dog-and-arm 当前开工版本上加入 H0，并同步 AGENTS、README、阶段计划、状态和首轮/续接提示词。
- 核对用户 OSCBF-learn 的既有 pyAgxArm 连接、纯接收反馈入口、历史验机结果与动作脚本范围。沿用用户已完成的本体验机，不重开整套验机。
- 核对官方 DC1 启动入口、USB PID 差异、两路 CameraInfo、原生流模式和时间戳来源；链接固定在 docs/HARDWARE_INTEGRATION.md。
- 增加硬件会话配置模板、H0 提示词和独立 ROS 环境入口，仿真环境继续分开。
- 完成新增 shell 脚本的 bash 语法检查与帮助入口调用，解析硬件 YAML 与目录初始化 Python。检查未将 H0、手眼或称重设为名义仿真硬门槛。

## 尚未执行

准备环境没有用户的 ROS2 Humble 安装、Piper H 或 DC1。本次未安装驱动、未连接 CAN、未取真实图像、未运动机械臂，也未在真实 ROS workspace 下验证 hardware_env.sh 的加载结果。

H0 的真实接入、联合采集、有限动作、数据分析和相机重启验证由 Linux 中的 Codex 按 prompts/HARDWARE_INTEGRATION.txt 执行。实测完成后另写 reports/H0_HARDWARE_REPORT.md，状态依据本次真实数据更新。
