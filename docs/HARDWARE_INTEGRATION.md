# H0：Piper H 与 DaBai DC1 实机联调

## 2026-11-25 新一期入口

H0仍是已完成的小幅联调与采集记录。用户现在要求固定桌面Piper策略迁移和真实完整开门动作，按[新一期计划](DESKTOP_PIPER_TRANSFER_PLAN_20261125.md)与[启动词](../prompts/PIPER_DESKTOP_START.txt)执行，复用本页现有SDK/记录器；不重做H0来代替新任务。H0的有限动作、手眼/时序和停止验证边界保持，新的部署结果另行登记。

更新：2026-11-16。用户已完成机械臂本体验机；本轮增加腕部相机与机械臂的联合运行和数据采集。本文保留执行方案；已完成的本轮结果见 [H0 实测报告](../reports/H0_HARDWARE_REPORT.md)，本机复跑见 [H0_RUNBOOK](H0_RUNBOOK.md)。

## 1. 本轮位置与目标

P0 检查现有工程环境后即可执行 H0，不需要先把机械臂装到 M1 上。沿用已经验机通过的固定安装状态。P1/P2 的资产与模型工作可以交错进行，H0 的视角、遮挡和接口记录供 P3 使用。

本轮要得到一段实际记录：机械臂静止、少量低速小幅运动、停止，以及夹爪开合期间，RGB、深度和真实机械臂状态持续存在，可以按已说明的时间域进行软件时间关联。

手眼外参、标定板、附件质量/惯量、视觉闭环控制与实机开门留在后续。本轮不要求彩色点云、精确基座到光心 TF，也不重新进行整套机械臂验机。M1 实机不参与运动。

硬件暂时不在本机时，H0 保持 pending，继续不依赖硬件的模型工作；不能把准备文件或历史机械臂日志写成本轮通过。H0 不阻塞使用名义参数的 MuJoCo 装配和接触仿真。

## 2. 先复用已经成功的机械臂环境

用户已有 [OSCBF-learn](https://github.com/kaiwen123-yang/OSCBF-learn) 工程。本次核对提交 `2ea3f1f48d10591b2bcb770af704011b381910b7` 的 README 和相关入口：机械臂使用 **pyAgxArm、PIPER_H、V189 配置**，`envs/piper-sdk` 是环境目录名，不能据此改装旧 `piper_sdk`。固件配置是历史成功环境的依据，当前实机仍以本机记录和状态为准，不为 H0 升级固件。[1]

已存在 `scripts/read_joint_state.py` 和 `scripts/read_feedback_sources.py` 的接收入口。前者含本机 CAN 通道、USB-CAN 身份以及固定 5 s 采样配置，应先阅读再复用接收逻辑；不能原样复制旧硬件标识、将 5 s 采样冒充整轮联调，或顺手改变 CAN 配置。[1]

旧 `cpv_axes_demo.py --execute` 不只是取流动作，它还包含使能、MOVE_J 准备姿态、模式切换和返回。旧项目另外保留 CPV 段末 CAN 错误的待处理项；H0 不默认重跑它或完整抓放，也不为了接相机重开整个控制课题。使用本机当前已验证的控制方式，由现场操作者启动明确的小范围慢动作，记录所用入口。[1]

状态采集只接收反馈。若现有系统没有 ROS JointState 话题，可以沿用 SDK 接收日志，并给数据补充同一主机的接收时间；无需为了相机另启动一套会自动使能的机械臂驱动。若必须增加状态桥接，代码中不能发送运动/使能指令。同一时刻只保留一个运动命令发送端。

## 3. 环境分开运行

仿真继续使用 `.venv` 和 `scripts/project_env.sh`。机械臂继续使用原来的已验证环境。相机使用独立 ROS2 Humble 终端或相机工作空间，不把 ROS Python 包强行装进 MuJoCo 的 `.venv`，也不重装现有 ROS/CUDA/驱动。

仓库新增 `scripts/hardware_env.sh`：在最小环境中加载已有 ROS 和显式指定的 overlay，保留显示、代理和 ROS 通信配置；不安装软件、不启动设备、不发送控制。

```bash
# 只读取当前 ROS 图；相机/状态节点需要已经在另一个终端启动。
bash scripts/hardware_env.sh -- ros2 topic list -t

# 相机 workspace 存在后，显式指定它的 setup 文件。
bash scripts/hardware_env.sh --overlay /实际相机工作空间/install/setup.bash -- ros2 node list
```

选择一个物理主机做本轮联合记录，避免先引入跨机时钟问题。优先沿用已验机的 Ubuntu 环境；如果在 WSL，先确认相机 USB 透传和实际枚举，机械臂 CAN 在 WSL 可用不自动代表相机可用。

需要新建相机 workspace 时可使用 `hardware/camera_ws`，上游和编译产物不提交；实际修改、依赖版本及启动命令写入项目配置和报告。先核对缺少的依赖，再处理具体缺项，不照抄旧 README 的 Galactic 环境或全局安装命令。

## 4. H0-A：相机独立接入，再和机械臂状态一起运行

### 4.1 设备身份与驱动

先查看 `lsusb`、`lsusb -t`；有 V4L2 工具时查看 `v4l2-ctl --list-devices`，再对实际 RGB 节点查询支持模式。记录协商速度、设备身份、驱动版本及启动参数；不硬编码 `/dev/video0`，也不要求 OpenNI 深度设备必须出现为 V4L2 节点。

只选一套相机驱动，同一相机不要同时被 Astra、OrbbecSDK 和另一个 RGB 抓流程序占用。

| 官方候选 | 本次核对结果 | 使用方式 |
| --- | --- | --- |
| ros2_astra_camera / master | 有准确的 `dabai_dc1.launch.xml`，使用 OpenNI 与 UVC | 现有环境可用时优先复用；新环境根据实际 Humble 构建情况选择 |
| OrbbecSDK_ROS2 / main | SDK v1 路线，存在 `dabai.launch.py`，明确包含 DC1 OpenNI 设备 | 核对设备和当前安装；不能编造 `dabai_dc1.launch.py` |
| OrbbecSDK_ROS2 / v2-main | 本次所读支持表未明确列 DC1 | 不能仅因更新就默认采用或要求升级固件 |

核对依据见文末 [2]–[4]。固定版本 Astra 的 udev 规则列 DC1 深度为 `2bc5:0657`、RGB 为 `2bc5:0557`，但 DC1 启动文件默认 UVC PID 是 `0x050e`。因此必须按本机枚举选 PID。[2]

下面仅是**选择了该 Astra 驱动、已经构建且本机确认 RGB PID 为 0557 后**的启动模板：

```bash
ros2 launch astra_camera dabai_dc1.launch.xml \
  camera_name:=wrist_camera uvc_product_id:=0x0557 \
  enable_ir:=false enable_point_cloud:=false enable_colored_point_cloud:=false
```

这一版本默认 RGB 为 640×480、深度为 640×400，均配置 30 FPS；原生分辨率不同不是故障。实际使用支持的模式，先保存原始流，不为了画面一样大而裁剪或缩放成伪对齐。[2]

### 4.2 应实际读取的数据

启动后先用 `ros2 topic list -t`、`ros2 node list` 和 `ros2 topic info -v` 确认实际名字、类型和 QoS。采用上述命名时，候选话题是：

```text
/wrist_camera/color/image_raw
/wrist_camera/color/camera_info
/wrist_camera/depth/image_raw
/wrist_camera/depth/camera_info
```

分别保存两路 CameraInfo 的 K、D、R、P、distortion_model、ROI、binning、尺寸及 frame_id。对于不裁剪、不 binning 的初始模式，检查每路图像与本路 CameraInfo 的对应关系；不能要求 RGB 与 depth 内参、尺寸相同。[5]

Astra 的 `get_camera_info` 服务只取彩色参数，不能替代两路 CameraInfo。其 `get_device_info` 回调没有填写消息中的固件字段，固件信息在 `get_sdk_version` 返回 JSON 中；具体服务类型先用 `ros2 service list -t` 查看，不能混用 `astra_camera_msgs` 与 `orbbec_camera_msgs`。[3]

CameraInfo 发布成功不等于已重新标定。记录参数来自设备、已有标定文件还是驱动默认回退；`K[0]==0` 按 ROS 约定表示未标定。缺失或回退参数应记录为问题，不能编造内参，也不因此要求现在购买标定板。[3][5]

同时记录深度编码、比例/单位和无效值定义，保留原始数值数组或原始编码图像，不能只保存彩色深度伪彩图。使用普通纸盒/书本等漫反射目标检查可用深度区域即可，无需专用标定板。整体图像中背景、夹爪或反光区域的无效深度不等于整机故障。

## 5. H0-B：联合运行和有限动作

先让机械臂保持当前稳定状态，相机和真实关节反馈同时记录。建议静止观察约 60–120 s，然后在一个连续记录中完成少量已验证的低速小幅动作、停住及夹爪开合。这里的时长是采样方案，可按现场修改，不是后台任务的强制截止时间。

动作由现场操作者沿用已有控制入口启动，并确认当前安装和活动空间可用。新增相机录制进程不应自动归零、使能或执行历史绝对姿态。相机解码/显示/存盘与机械臂控制分进程，避免把图像处理塞进控制循环。

覆盖以下观察即可，不做全工作空间扫描：

- 相机画面随腕部动作变化，目标在选定的几个姿态下仍有可用视野；夹爪开、闭时遮挡变化可解释。
- 支架相对固定主体稳定，线缆在本次小范围动作中没有绷紧、卷入或拉扯接口；以现场观察和短片记录。
- 相机运行时六关节真实反馈、夹爪反馈/实际状态仍持续更新；无法读取的量写明，不能用命令值替代反馈。
- 记录实际图像/状态接收率、间隔、无数据长间隔、重连和 CPU/队列积压现象。已知控制故障若在本轮出现，保留日志并处理当前问题，不报告通过。
- 停住后正常停止并重新启动相机采集，再确认数据能恢复。无需进行带电拔插、固件更新或重置整个系统。

## 6. 时间关联的正确口径

每路保留原始设备/消息时间戳及其来源，同时在**同一主机、同一次系统启动**的采集端记录 `host_monotonic_ns`；可同时保存 ROS/Unix 接收时间。图像、关节状态和事件均采用这一主机时间基准进行初步关联。

先读取实际相机、状态桥接和记录节点的 `use_sim_time`，H0 期望使用真实主机时钟，但不能把模板中的期望值当作已读取结果。若 SDK getter 只是返回缓存，循环打点应标为 poll/snapshot 时间，不能当成新 CAN 反馈的接收时刻或据此计算真实反馈频率。优先保留 SDK 的反馈更新时间/序号，区分接收事件、反馈更新与缓存轮询；拿不到这些信息时写明限制，不为了统计强制重写底层接收器。

本次核对的 Astra 实现对 RGB 和深度在回调中写 `node_->now()`。SDK v1 ROS2 路线对包括 DC1 的 OpenNI 设备选择 system 时间域。这些不是已经证明的曝光时刻，不应照搬其他设备的硬同步或设备时钟参数。[3][4]

统计每路接收间隔的中位数、P95、最大值，以及时间戳倒退/跳变、明显空洞。可以报告 RGB–depth、RGB–最近关节状态的接收时间差；只有确认原始时间戳来自同一时钟域后，才另外比较原始时间戳。不要直接相减不同设备纪元，也不要把 rosbag 写盘时间当曝光时刻。

这里得到的是软件时间关联与当前采集链的观测结果，不是硬件同步误差或精确端到端延迟。采集端接收率也不自动等于传感器内部帧率。不要求逐帧时间戳相等或任意亚毫秒指标。

可以用短段 rosbag 保留实际话题，同时保存 SDK 状态 CSV；若已有记录器满足要求就复用。需要新增记录器时，由本机 Codex 根据真实接口实现只读采集，不创建另一个运动控制器。

## 7. 最小交付与通过依据

填写 `config/hardware_session.yaml` 的实际接口、驱动和数据语义；本轮已按实测回填。后续复跑先核对当时设备，不能把上次记录直接当作本次实测，也不要求用户逐项人工测量。

本轮输出到 `results/hardware/h0/<session>/`，建议包括：

| 内容 | 最小要求 |
| --- | --- |
| manifest / 启动记录 | 系统、已有臂工程、SDK/驱动提交、实际启动命令、话题与 QoS、时间域 |
| color_camera_info、depth_camera_info | 两路完整参数与来源、是否回退、是否启用对齐 |
| RGB 与原始深度样帧 | 静止、运动/停止、夹爪开闭的代表帧；深度含单位说明 |
| joints / events | 六关节名称、顺序、单位、真实反馈；夹爪状态；动作开始/停止事件时间 |
| stream_timing | 原始 header/设备时间、主机单调接收时间、frame_id、图像编码/尺寸 |
| summary / 短视频 | 实际接收率与间隔摘要、掉流/重连/资源问题、可辨认的联合运行过程 |

完整原始录制放 `results/raw_large/hardware/h0/`，不自动提交大包。GitHub 至少保留可以复核的短片、样帧、原始深度小样本、状态/时间数据与报告；只留视频不够。无需额外制作本机压缩归档，也不自动删除唯一原始记录。

报告写入 `reports/H0_HARDWARE_REPORT.md`，逐项给出证据：

1. 真实 RGB、深度及两路参数均可读取，机械臂实际状态可同时记录。
2. 单位、原始/对齐状态、frame 和时间戳语义已说明；回退或缺失有明确记录。
3. 一段记录覆盖静止、有限动作、停止与夹爪变化，数据能关联到事件。
4. 联合运行没有未处理的持续掉流、重连、状态停止更新或控制异常；接收性能有数据依据。
5. 保存的命令可以再次启动该组合，正常重启采集后能够恢复。

存在的子项分别标明完成、部分完成或未完成；例如 RGB 正常但深度缺失，应写 H0 部分完成。相机参数为回退值时不能宣称内参已验证。总体 H0 完成只说明联合运行与采集可用，不说明手眼、视觉闭环或实机开门已经完成。

## 8. 回填 P3 和下一步

真实流配置和视角检查进入独立硬件配置；仿真里的 `synthetic_aligned_rgbd` 仍是理想相机。不要把真实 RGB/深度天然当成同一光心或已对齐，也不要把名义安装变换标成标定结果。

可以保留相机自身 TF 子树。未知臂到光心变换暂不发布为真实标定 TF；若展示需要名义关系，明确标注 assumption。手眼以后再做，现阶段无需购买板。

H0 后继续尚未完成的 P0–P3；已完成 P3 则进入 P4 **MuJoCo 固定基座接触开门**。更新 PROJECT_STATE.md、下一轮提示词，并正常提交推送。

## 已读取的依据

1. [用户既有实机 README](https://github.com/kaiwen123-yang/OSCBF-learn/blob/2ea3f1f48d10591b2bcb770af704011b381910b7/README.md)、[只接收关节反馈入口](https://github.com/kaiwen123-yang/OSCBF-learn/blob/2ea3f1f48d10591b2bcb770af704011b381910b7/scripts/read_joint_state.py)、[CPV 动作入口](https://github.com/kaiwen123-yang/OSCBF-learn/blob/2ea3f1f48d10591b2bcb770af704011b381910b7/scripts/cpv_axes_demo.py)。它们是可复用依据，不是本次 H0 的运行记录。
2. Astra 固定提交 `f7e71d9ce806e788cb48d8580aac2c778fba4214`：[DC1 启动文件](https://github.com/orbbec/ros2_astra_camera/blob/f7e71d9ce806e788cb48d8580aac2c778fba4214/astra_camera/launch/dabai_dc1.launch.xml)、[USB 规则](https://github.com/orbbec/ros2_astra_camera/blob/f7e71d9ce806e788cb48d8580aac2c778fba4214/astra_camera/scripts/56-orbbec-usb.rules)。
3. 同版本 Astra：[UVC 设备选择与 RGB 时间戳](https://github.com/orbbec/ros2_astra_camera/blob/f7e71d9ce806e788cb48d8580aac2c778fba4214/astra_camera/src/uvc_camera_driver.cpp)、[深度与 CameraInfo](https://github.com/orbbec/ros2_astra_camera/blob/f7e71d9ce806e788cb48d8580aac2c778fba4214/astra_camera/src/ob_camera_node.cpp)、[服务实现](https://github.com/orbbec/ros2_astra_camera/blob/f7e71d9ce806e788cb48d8580aac2c778fba4214/astra_camera/src/ros_service.cpp)。
4. OrbbecSDK_ROS2/main 固定提交 `0ea4ab68f5b8ddf22998b7c45d251dc58ea2779e`：[启动入口](https://github.com/orbbec/OrbbecSDK_ROS2/blob/0ea4ab68f5b8ddf22998b7c45d251dc58ea2779e/orbbec_camera/launch/dabai.launch.py)、[OpenNI 判断](https://github.com/orbbec/OrbbecSDK_ROS2/blob/0ea4ab68f5b8ddf22998b7c45d251dc58ea2779e/orbbec_camera/src/utils.cpp)、[时间域及发布逻辑](https://github.com/orbbec/OrbbecSDK_ROS2/blob/0ea4ab68f5b8ddf22998b7c45d251dc58ea2779e/orbbec_camera/src/ob_camera_node.cpp)。当前 v2 支持表核对版本为 `ffba347cadc96d0457a91af59fc06cdf86052728`，不据此推断未列设备必然兼容。
5. [ROS 官方 CameraInfo 定义](https://github.com/ros2/common_interfaces/blob/humble/sensor_msgs/msg/CameraInfo.msg)。
