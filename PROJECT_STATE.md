# 项目状态

更新日期：2026-11-16（Asia/Shanghai）。

## 当前阶段

**H0：Piper H＋DaBai DC1 实机联调已完成，保留明确的测量限制。** 本机工作目录为 `/home/kaiwen/research/dog-and-arm`。本轮完成目录/现有环境检查、相机驱动构建、真实静止与动作联合采集、正常停止/重启及证据保存；没有进行 P1–P3 模型装配，不能把 H0 或开工包标成 P3 完成。

- 机械臂本体验机：**用户此前已完成**，本轮复用现有 OSCBF-learn / pyAgxArm。
- H0 相机＋机械臂联调：**本轮实机完成**；[报告](reports/H0_HARDWARE_REPORT.md)、[会话清单](results/hardware/h0/20261116_2051/manifest.json)、[操作说明](docs/H0_RUNBOOK.md)。
- 手眼标定、标定板采购、相机/支架称重及惯量：**继续后置**。
- 下一轮：按 [prompts/NEXT_RUN.txt](prompts/NEXT_RUN.txt) 完成尚未执行的 P0 仿真环境与 P1–P3 官方模型转换/装配，不自行启动真实机器人。

## 本轮实际环境、命令和文件

- 从 `7bb3c1b` 克隆本仓库。原工程 `/home/kaiwen/research/OSCBF-research` 对应 OSCBF-learn `2ea3f1f`；解释器 `envs/piper-sdk/bin/python` 中实际是 pyAgxArm 1.0.0 / python-can 4.6.1，SDK 源提交 `d90e234b`，PIPER_H/V189 配置。未重装机械臂环境或升级固件。
- 实际 `can0` 初始 DOWN；确认 USB-CAN `1d50:606f`、序列号 `004F00374548570120353731` 后，用户执行 `sudo bash scripts/h0_host_prepare.sh` 补齐缺失相机依赖、USB 权限并启用 1 Mbps CAN。准备脚本及接收器不发电机指令。
- 相机为 DC1，RGB `2bc5:0557`、深度 `2bc5:0657`，序列号 `CC16762023M`，USB 480 Mbps。`bash scripts/h0_build_camera.sh` 构建 Astra `f7e71d9c`；首次缺 `nlohmann/json.hpp` 的失败和解包头文件后的成功均保留。驱动源/编译产物在忽略目录 `hardware/camera_ws/`，未修改上游。
- 相机入口 `bash scripts/h0_camera.sh`；最终相机/接收器经 `scripts/h0_ros_env.sh` 使用 domain 88、localhost、Fast DDS 64 MiB SHM。ROS 与机械臂解释器分开，未使用仿真 `.venv`。
- `h0_record_camera.py` 保存 RGB/原始深度/CameraInfo/视频/时间；`h0_record_arm.py` 只接收 SDK/CAN 状态。两者独立进程；`h0_operator_motion.py` 是现场唯一运动入口，复用原 `PiperDevice`，记录实际 MOVE_J/夹爪发送调用。
- 成功现场命令使用原解释器、`--execute --recording-directory .../continuous --start-deg 83.551 2.821 0 -1.132 24.567 5.556`，输出到 `.../continuous/retry`。完整命令和事件见报告及证据；这些绝对角度仅属于当次现场，不能盲目重放。
- 离线用 `/usr/bin/python3 scripts/h0_analyze.py <run>` 计算接收间隔和关联，用 `h0_export_window.py` 导出事件窗口。真实配置已填入 [config/hardware_session.yaml](config/hardware_session.yaml)。

## H0 实测结果

| 项目 | 结果 |
| --- | --- |
| RGB / 原始深度 | 640×480 rgb8 / 640×400 16UC1；1 count = 1 mm，0 无效；未对齐、未缩放保存数组 |
| 两路 CameraInfo | 完整保存 D/K/R/P、尺寸、frame、ROI、binning；各自匹配图像，K 可与设备服务核对；RGB D 的已知差异见下 |
| 静止联合记录 | 65 s RELIABLE 窗口完成；最终 240 s：RGB 7179、深度 7204、关节 48006 行 |
| 最终接收性能 | RGB 29.912 Hz、深度 30.017 Hz、关节 200.025 Hz；最大间隔分别 40.023/39.860/8.104 ms；无 >100 ms 间隔、倒退、队列丢帧或 CAN 错误 |
| 小幅动作 / 正常停止 | 第二次 J6 实测范围 1.962°，慢转、保持、返回；初始明确调整 J3 +1.611°→0°，没有全零回位 |
| 夹爪 / 现场观察 | 约 39.5→15.1→39.5 mm；用户确认“这次动作、停止、支架和线缆都正常” |
| 相机正常重启 | 成功退出并恢复两路流/参数；新传输配置下完成 90 s＋240 s 静止复核 |

最终 RGB–depth 最近接收时间差中位数/P95/最大值 8.399/16.305/17.915 ms；RGB–joint 为 1.219/2.374/3.681 ms。相机 header 来自驱动回调 `node->now()`，不是已证明的曝光时刻。CAN 保留内核时间、SDK 更新时间和主机单调接收时间；约 10 Hz 缓存快照不用于反馈率。实际相机/记录节点 `use_sim_time=false`。这些结果仅是同一主机的软件接收关联，未验证硬件同步。

## 失败记录与剩余限制

- 首次 BEST_EFFORT 接收 RGB 仅约 6.52 Hz；匹配发布者改为 RELIABLE 后短窗口恢复。约 720 s 连续记录又在约 182 s 后出现 RGB 成批到达；最终改项目独立 SHM 配置，90 s＋240 s 静止复核恢复到约 40 ms 最大间隔。成功运动段仍属于修改前的传输配置，**未在最终配置下再次做动作复核**，不得给旧运动数据套用最终时序指标。
- 首次动作六轴不动、夹爪开合；保留用户反馈和失败包。修正原封装关闭自动模式帧发送与 MOVE_J 入口不一致的问题后，现场第二次运动成功。未提高速度/幅度或关闭保护。返回斜坡结束时短暂未到位，随后保持段到位，没有持续控制器故障。
- RGB CameraInfo 发布的 D 为零，但设备服务返回非零 `r_k`；需在几何视觉使用前核实，不能声称内参精度已验证。`RD1001` 是驱动返回的 sensor platform string，不是已验证完整固件版本。
- 本轮只验证正常目标保持停止，未实测急停、断流看门狗、全工作空间线缆或视觉闭环。Astra 退出时有参数清理提示，进程正常结束并已成功重启；原日志保留。
- 结束时记录显示机械臂仍为 MOVE_J、六轴使能、无故障，约 `[83.551,2.737,0,-1.132,24.567,5.557]°`，夹爪约 39.5 mm；没有自动失能/reset/回零。相机及本轮接收进程已正常结束。后续硬件任务仍须读当时实时状态。

## 证据位置

- [H0 报告](reports/H0_HARDWARE_REPORT.md)、[成功动作短片](results/hardware/h0/20261116_2051/evidence/motion_success/clip.mp4)、[动作与接收时序图](results/hardware/h0/20261116_2051/evidence/motion_success/motion_and_timing.png)。
- `results/hardware/h0/20261116_2051/evidence/` 包含真实 RGB、uint16 深度小样本、两路内参、静止/失败/成功/重启短片、真实关节/夹爪及全部接收时间；最终 240 s 验证在 `evidence/final_validation/`。为提交体积抽取的 SDK 缓存快照明确标为约 1 Hz，原始时间不变。
- 完整本地运行目录及全部周期样本/AVI 保留但不提交；大 CAN/rosbag 在 `results/raw_large/hardware/h0/20261116_2051/`。bag 只覆盖若干运行开头的 10 s，不能称作较晚运动的全量 bag。没有删除唯一原件或另建压缩归档。

## 模型路线的既有成果与未完成项

开工包已有环境隔离/源下载脚本、来源锁定清单、门生成器、配置/查看器、支架 OBJ/预览/来源说明、四张用户安装照片和装配规则。既有单/双门 XML 曾在独立准备环境用 MuJoCo 3.3.0 编译并静止步进 2 s；[开工验证](reports/KICKOFF_VALIDATION.md) 不含机器人控制，也不是本轮 Linux 的整机验证。

仍待下一轮完成：项目仿真 `.venv` 和图形显示、完整官方 M1 ZGWS/Piper H 网格获取与转换、M1 衍生 URDF、背部名义安装与腕部附件对齐、组合 URDF/MJCF、关节/执行器映射、少量合法姿态的 FK 与夹爪检查及装配图。随后才进入 P4 以后的接触/轮足动力学和单/双门任务。

遵守 `accessory_payload_mode=omitted` 和 `synthetic_aligned_rgbd`：附件显式零质量，仿真理想对齐 RGB-D 不冒充本次实物标定。手眼及称重不阻塞名义装配。

下一轮阅读续接提示后可执行的第一条环境命令：`bash scripts/setup_env.sh`。仅需相机复跑时使用 `bash scripts/h0_camera.sh`，它不会启动机械臂动作。
