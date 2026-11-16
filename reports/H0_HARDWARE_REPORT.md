# H0：Piper H＋DaBai DC1 腕部相机实机联调

日期：2026-11-16，Asia/Shanghai。会话：`20261116_2051`。

**本轮完成了真实相机接入、静止联合采集、现场启动的小幅腕部动作/停止及夹爪开合、相机正常重启和结果归档。** 机械臂本体验机是用户此前已完成的前置成果；本报告只把本轮新采集的数据作为 H0 证据。首次动作未运动和两次图像传输问题均保留，没有把脚本退出、平均帧率或历史日志当作通过依据。

限定结论：联合运行和数据采集可用。运动记录使用了修正前的 DDS 传输配置，其中存在 RGB 成批到达；后续通过项目独立传输配置解决，并完成 90 s＋240 s **静止**复核，未再次要求操作者重复运动。不能把最后静止窗口的时序性能套用到先前的运动视频。手眼、几何标定精度、硬件同步、视觉闭环和实机开门均不在本轮完成范围。

## 1. 逐项结果

| 子项 | 本轮结果 | 主要证据 |
| --- | --- | --- |
| 工作目录与仓库 | 已创建并克隆到 `/home/kaiwen/research/dog-and-arm`；从 `7bb3c1b` 开始 | [会话清单](../results/hardware/h0/20261116_2051/manifest.json) |
| 复用原机械臂环境 | 已完成；pyAgxArm 1.0.0、PIPER_H/V189；未重装旧环境 | [配置](../config/hardware_session.yaml)、环境日志 |
| 相机识别、驱动接入 | 已完成；DC1 RGB `2bc5:0557`，深度 `2bc5:0657`，USB 480 Mbps | [USB记录](../results/hardware/h0/20261116_2051/logs/usb.txt)、驱动启动日志 |
| RGB、原始深度 | 已完成；640×480 rgb8、640×400 16UC1，原始深度为 uint16 毫米 | [真实 RGB](../results/hardware/h0/20261116_2051/evidence/static_color_000000.png)、[原始深度](../results/hardware/h0/20261116_2051/evidence/static_depth_000000.npy) |
| 两路 CameraInfo | 均已完整保存，尺寸/frame 各自匹配；不是新标定，RGB D 有已记录差异 | [RGB 参数](../results/hardware/h0/20261116_2051/evidence/color_camera_info.json)、[深度参数](../results/hardware/h0/20261116_2051/evidence/depth_camera_info.json) |
| 静止联合采集 | 已完成；65 s 修正 QoS 窗口及最终 240 s 窗口 | [最终统计](../results/hardware/h0/20261116_2051/evidence/final_validation/timing_summary.json) |
| 慢动作、正常停止 | 第二次完成；J6 实测变化范围 1.962°，返回约 5.557°，现场确认正常 | [动作数据](../results/hardware/h0/20261116_2051/evidence/motion_success/)、[时序图](../results/hardware/h0/20261116_2051/evidence/motion_success/motion_and_timing.png) |
| 夹爪开合 | 两次均有真实反馈；成功段约 39.5→15.1→39.5 mm | [夹爪记录](../results/hardware/h0/20261116_2051/evidence/motion_success/gripper.csv) |
| 支架、线缆与视野 | 用户确认第二次动作、停止、支架和线缆均正常；画面可见夹爪及前方地面/家具 | [现场确认](../results/hardware/h0/20261116_2051/evidence/motion_success/motion_observation.json)、[短视频](../results/hardware/h0/20261116_2051/evidence/motion_success/clip.mp4) |
| 相机正常停止/重启 | 已完成；干净退出后同一设备恢复 RGB/深度/参数；新传输配置验证 90 s＋240 s | [重启短片](../results/hardware/h0/20261116_2051/evidence/restart_12s.mp4)、[重启统计](../results/hardware/h0/20261116_2051/evidence/restart_validation/timing_summary.json) |

## 2. 实际环境与接入方式

主机是 Ubuntu 22.04.5 x86_64，已有 ROS2 Humble。本轮只完成 H0 所需的目录/环境检查，没有安装仿真 `.venv`，没有启动 M1、MoveIt 或额外的机械臂 ROS 控制器。

机械臂工程为 `/home/kaiwen/research/OSCBF-research`，对应 OSCBF-learn 提交 `2ea3f1f48d10591b2bcb770af704011b381910b7`；SDK 来源 `d90e234ba8e408cfa964b38aa9120b3131fc9f85`。解释器是 `envs/piper-sdk/bin/python`，库实际为 pyAgxArm 1.0.0、python-can 4.6.1。状态记录复用原 `read_joint_state.py` 的接收/解码路径；动作复用原 `PiperDevice` 和已验证 MOVE_J、夹爪接口。

`can0` 初始为 DOWN，核对 USB-CAN 序列号 `004F00374548570120353731` 后，由用户在本机终端执行 `sudo bash scripts/h0_host_prepare.sh` 启用 1 Mbps。脚本没有发送电机命令。静止记录器的 TX 增量为 0。最初开接口后无接收 socket 时系统计数已有 RX dropped；5 s 探测边界另增 67。后续完整 65 s、连续动作窗口及最终 240 s 的接口 dropped/error 增量均为 0，不能把初始累计值误当作这些窗口丢帧。

相机只使用 `orbbec/ros2_astra_camera@f7e71d9ce806e788cb48d8580aac2c778fba4214`，位于被 Git 忽略的 `hardware/camera_ws/`，没有修改上游源文件。用户安装了检查发现缺失的 libuvc、glog、gflags、camera-info-manager、image-publisher 及其依赖；首次编译又发现 `nlohmann/json.hpp` 缺失，在 `hardware/deps/` 解包 Ubuntu 3.10.5-2 头文件包后构建成功。原编译失败日志保留，没有重装 ROS/CUDA、改 shell 启动文件或刷写固件。

当前启动命令为 `bash scripts/h0_camera.sh`。它调用 `h0_ros_env.sh`，限定 domain 88、localhost、Fast DDS 和项目 XML；RGB PID 显式设为 `0x0557`，关闭 IR、点云和 D2C 注册，深度缩放因子保持 1。两个记录进程与唯一现场动作进程独立，图像处理/存盘不进入机械臂控制循环。

驱动发现序列号 `CC16762023M`；`get_device_info` 的通用设备名为 Astra，其固件字段为空。`get_sdk_version` 返回 `RD1001`、ROS SDK 1.1.0、OpenNI Standard 2.3.0 Build 85。源码表明 `RD1001` 来自 sensor platform string，不能当作已验证的完整固件构建版本。原始返回见 [服务记录](../results/hardware/h0/20261116_2051/logs/camera_services.txt)。

## 3. 内参、深度与时间语义

| 参数 | RGB | 深度 |
| --- | --- | --- |
| 图像尺寸 | 640×480 | 640×400 |
| 编码 | rgb8（USB MJPEG 解码后） | 16UC1，1 count = 1 mm，0 无效 |
| fx / fy | 488.788452 / 488.788452 | 476.290222 / 476.290222 |
| cx / cy | 318.621857 / 211.099976 | 320.553589 / 197.625702 |
| frame | wrist_camera_color_optical_frame | wrist_camera_depth_optical_frame |
| distortion_model / D | plumb_bob / 5 个零 | plumb_bob / 5 个零 |

两路 K 与设备参数服务的右/左相机参数一致，没有使用外部标定 URL。完整 D/K/R/P、ROI、binning、尺寸和 header 都已保存。原生尺寸不同是正常配置；没有裁剪、缩放原始数组来制造对齐。深度预览只做显示色映射，原始 NPY 保留毫米数值和零值。夹爪附近、背景/反光或超出可用区域的零深度被保留，未将其填充成虚假测量。

**RGB 参数限制**：设备返回非零 `r_k`，但该版本 `getColorCameraInfo()` 发布的 D 全零。K 来源可核对不等于畸变参数或几何精度已经验证；本轮未擅自改成另一套标定。使用深度投影/几何视觉前需要处理此差异。手眼、标定板采购、附件称重及惯量测量继续后置。只发布相机自身 TF，没有发布未知的臂到光心标定 TF。

实际读取相机节点和记录节点的 `use_sim_time=false`。Astra 为 RGB/深度消息填入驱动回调中的 `node->now()`，不是已经证明的曝光时刻；原始设备时间戳未由此接口暴露。记录器保存原 ROS header、同一主机 `monotonic_ns` 回调时刻及 Unix 接收时刻。CAN 另保留内核帧时间、SDK 更新时间和接收后的单调时间；六关节统计来自 0x2A5/0x2A6/0x2A7 接收组，夹爪来自 0x2A8。约 10 Hz SDK 快照明确标为缓存轮询，未用其计算真实反馈率。

最终 240 s 窗口的最近接收时间差：RGB–depth 中位数/P95/最大值为 **8.399/16.305/17.915 ms**；RGB–joint 为 **1.219/2.374/3.681 ms**。这是同一主机的软件接收关联，不是硬件同步误差、曝光对齐或端到端延迟。

## 4. 实测性能与已处理问题

| 窗口 | RGB Hz | 深度 Hz | 关节 Hz | RGB 最大接收间隔 | 结果解释 |
| --- | ---: | ---: | ---: | ---: | --- |
| 首次 BEST_EFFORT，70 s | 6.52 | 29.93 | 200.02 | 2139.52 ms | 明显漏收大图像；保留诊断记录 |
| 改 RELIABLE，65 s | 29.91 | 30.02 | 200.03 | 78.82 ms | 此短窗口恢复；不能推断长期稳定 |
| 连续记录，约 720 s | 29.76 | 30.02 | 200.03 | 389.56 ms | 约 182 s 后 RGB 成批到达，785 个 >100 ms 间隔 |
| 成功动作导出，33.72 s | 29.84 | 30.02 | 200.02 | 367.25 ms | 动作/夹爪连续有记录，但 RGB 时序仍受旧传输影响 |
| 最终 RELIABLE＋64 MiB SHM，240 s | **29.91** | **30.02** | **200.03** | **40.02 ms** | 两路图像均无 >100 ms 间隔，无时间戳倒退 |

最终 RGB 间隔中位数/P95/最大值为 32.161/36.220/40.023 ms，深度为 34.758/35.369/39.860 ms；关节为 4.999/5.143/8.104 ms。实际样本数为 RGB 7179、深度 7204、关节 48006。CameraInfo 各自也持续更新；数量边界不要求逐帧相等。记录队列丢帧为 0，最终最大队列长度 4，CAN 错误帧及完整窗口接口错误增量均为 0。接收率不等同于传感器内部帧率。

长窗口问题的处理依据是本机观察到约 537 KiB 的默认 Fast DDS 段，而一帧 RGB 裸数据为 921600 字节。官方说明默认 SHM 段为 512 KiB，段过小可能丢数据；本项目设置 64 MiB 段和 4 MiB 最大消息，并保留本机 UDP 发现。[官方传输说明](https://fast-dds.docs.eprosima.com/en/2.6.x/fastdds/transport/shared_memory/shared_memory.html)。相机正常重启后，90 s＋240 s 静止记录恢复到上述时序；这支持传输配置是问题因素，但不声称已穷尽所有负载和故障条件。

退出时 Astra 上游会打印静态参数不能 undeclare 的清理错误，并有 class_loader/USB 优先级提示；日志最后确认进程 cleanly finished，后续设备成功重启。本轮没有为这些提示修改上游驱动，没有隐去日志。CPU 没有完整的连续监测曲线；已保存队列、进程配置和峰值 RSS，不能由本轮记录宣称实时调度保证。

## 5. 动作、失败与停止结果

第一遍使用的封装继承了 `PiperDevice` 为 CPV 关闭自动模式发送的设置。六轴新鲜反馈一直不变，用户确认“机械臂未动，只有夹爪开合；支架线缆正常”。原 `motion_summary.completed=true` 只代表命令循环结束，**不是运动通过**；[首次记录及现场解释](../results/hardware/h0/20261116_2051/evidence/attempt1/motion_observation.json) 完整保留。

第二遍恢复原成功 MOVE_J 入口在每组关节目标前发送模式帧的方式，并记录实际 SDK 发送调用。动作范围、速度、停止逻辑、保护参数均未扩大；仍由用户现场启动，采集器只接收。起始实测为 `[83.551,2.821,1.611,-1.132,24.567,5.556]°`，已明确告知 J3 目标改为合法的 0°，没有静默夹紧目标或回到全零位。原 SDK TX 文件在夹爪阶段的 phase 标签沿用前一保持段，应按事件时间、CAN ID 和 commands 文件解释；整理时已修正后续入口的日志标记，未重跑硬件，见 [源码快照说明](../results/hardware/h0/20261116_2051/sources/README.md)。

J6 目标在 4 s 内 +2°、保持 3 s、4 s 返回、保持 3 s；实测范围 1.962°，偏转保持段约 7.502°，最后约 5.557°。返回斜坡结束时尚未到位（SDK motion_status=1），后续保持段转为 0；没有持续控制器故障。启动/调整期间 J2/J3/J5 也有反馈变化，导出窗口各轴范围为 `[0,0.667,2.044,0,0.495,1.962]°`，不能描述为其他五轴绝对无位移。

夹爪使用既有 `move_gripper_m`，目标 40→15→40 mm、1 N，实测约 39.5→15.1→39.5 mm。第一遍还保留了从初始近闭合到打开的记录。用户明确确认第二次动作、停止、支架、线缆均正常。只有本次小范围的现场观察依据，没有做全工作空间线缆验证。

本轮验证的是目标保持下的**正常停止**，没有现场测试 Ctrl+C/急停或断流看门狗，不把旧停止接口当成本轮新验证。末次机械臂保持 MOVE_J、六轴使能、无故障，角度约 `[83.551,2.737,0,-1.132,24.567,5.557]°`；没有自动失能、reset 或回零。相机和本轮接收进程已正常结束。

## 6. 文件与复跑

- [静止短片](../results/hardware/h0/20261116_2051/evidence/static_12s.mp4)、[成功动作/夹爪短片](../results/hardware/h0/20261116_2051/evidence/motion_success/clip.mp4)、[首次未运动短片](../results/hardware/h0/20261116_2051/evidence/attempt1/clip.mp4)、[重启短片](../results/hardware/h0/20261116_2051/evidence/restart_12s.mp4)。
- [成功窗口](../results/hardware/h0/20261116_2051/evidence/motion_success/) 含关节、夹爪、全部图像接收时间、原始深度小样本、动作事件、发送调用、实际样本与事件的时间差。周期原始样本不一定正好落在事件瞬间；视频逐帧索引另行保留。
- [最终 240 s 数据](../results/hardware/h0/20261116_2051/evidence/final_validation/) 保留全部接收时间和关节/夹爪行；[完整连续窗口统计](../results/hardware/h0/20261116_2051/evidence/continuous_timing_summary.json) 保留约 720 s 的整体情况。SDK 缓存快照为提交体积抽取约 1 Hz，文件名和 scope 明示；全量原件未删。
- 完整本地运行在 `results/hardware/h0/20261116_2051/{static,static_reliable,continuous,restart_shm64,final_validation}/`；完整 CAN/短段 rosbag 在 `results/raw_large/hardware/h0/20261116_2051/`。这些大录制和完整 AVI 不进 Git，没有另做压缩归档。bag 是各次开始的 10 s，不能把它称为覆盖较晚动作的全量 bag。
- [操作入口与复跑说明](../docs/H0_RUNBOOK.md)。只启动相机的下一条命令：`bash scripts/h0_camera.sh`。重做动作前必须重新读取现场状态，不盲目复用本次绝对角度。

后续主任务回到尚未完成的 P0–P3 仿真环境、官方资产和模型装配；继续保留 `synthetic_aligned_rgbd` 与本次未对齐真实 DC1 配置的区别。手眼、板采购、称重/惯量均后置。
