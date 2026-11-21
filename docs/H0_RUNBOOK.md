# H0 本机复跑入口

本机项目：`/home/kaiwen/research/dog-and-arm`。臂环境继续使用
`/home/kaiwen/research/OSCBF-research/envs/piper-sdk/bin/python`，其中安装的是
**pyAgxArm 1.0.0**。不需要安装旧 piper_sdk、重装 ROS 或升级固件。

## 驱动与接收

相机源码固定为 `orbbec/ros2_astra_camera@f7e71d9ce806e788cb48d8580aac2c778fba4214`。
本机缺少的系统依赖已由操作者执行 `sudo bash scripts/h0_host_prepare.sh` 补齐。
该脚本还设置两个 DC1 USB 功能的访问权限，核对 Piper USB-CAN 序列号，并在
接口 DOWN 时启用 1 Mbps CAN；它不发送电机指令。不要为正常复跑重复安装环境。

`bash scripts/h0_build_camera.sh` 可重建被忽略的相机 workspace。首次构建额外发现
缺少 nlohmann JSON 头文件，脚本在 `hardware/deps/` 解包 Ubuntu 3.10.5-2 的
头文件包，不写系统 include 路径。实际驱动没有源代码补丁。

相机进程在单独终端：

```bash
cd /home/kaiwen/research/dog-and-arm
bash scripts/h0_camera.sh
```

使用 ROS domain 88、localhost only。RGB `2bc5:0557`、深度 `2bc5:0657`。
RGB 640×480 MJPEG→rgb8，深度 640×400 16UC1，均请求 30 FPS；关闭 IR、点云和
深度到彩色注册。仅保留相机自身 TF，没有发布臂到相机的标定变换。

为每次试验选一个**新的**目录（下面的 `RUN` 是示例，不是固定复用目录），然后在
两个独立终端启动接收器。默认持续到 Ctrl+C；`--seconds 65` 是可选的明确采样时长。

```bash
RUN=results/hardware/h0/新会话名
RAW=results/raw_large/hardware/h0/新会话名
bash scripts/h0_ros_env.sh /usr/bin/python3 \
  scripts/h0_record_camera.py "$RUN" --raw-directory "$RAW" --bag-seconds 10
```

```bash
RUN=results/hardware/h0/新会话名
RAW=results/raw_large/hardware/h0/新会话名
env -u LD_LIBRARY_PATH /home/kaiwen/research/OSCBF-research/envs/piper-sdk/bin/python -I \
  scripts/h0_record_arm.py "$RUN" --raw-directory "$RAW"
```

相机接收 QoS 使用 **RELIABLE / KEEP_LAST 10 / VOLATILE**，匹配实测发布者。
本机首次 BEST_EFFORT 订阅曾出现 RGB 严重空洞，不能把 SensorData QoS 无条件套用到这里。
长时间 RELIABLE 记录仍曾出现大图像成批到达，因此相机和记录器统一经
`h0_ros_env.sh` 加载 `config/h0_fastdds.xml`：64 MiB SHM 段、4 MiB 最大消息，
另保留本机 UDP 发现。默认约 512 KiB SHM 段小于一帧 RGB 数据。
这只影响 H0 的进程，不改变系统或其他 ROS 项目。官方依据见
[Fast DDS 2.6 SHM](https://fast-dds.docs.eprosima.com/en/2.6.x/fastdds/transport/shared_memory/shared_memory.html)。
图像解码、视频写盘在图像记录进程内，臂状态进程只接收；两者不发送使能或运动命令。

## 有限动作

先静止记录，检查 `camera_live.json` 和 `arm_live.json`，再检查当前姿态、故障和现场
空间/线缆。`h0_operator_motion.py` 是唯一动作入口，复用旧工程 `PiperDevice` 的
状态检查和使能握手，MOVE_J 使用原成功入口的自动模式帧发送顺序。**必须由现场操作者运行**。

先用新的预览目录运行不带 `--execute` 的命令；`--start-deg` 必须依据本次实时反馈
明确填写，不能自动复制旧姿态或本报告数字。当前 SDK 会夹紧超出限位的目标，封装会
拒绝非法目标以避免静默改变；第一轮实测 J3 +1.611°，当次已明确告知操作者目标为 0°。

```bash
# 把六个角度替换为已审阅的本次明确目标，单位为度。
env -u LD_LIBRARY_PATH /home/kaiwen/research/OSCBF-research/envs/piper-sdk/bin/python -I \
  scripts/h0_operator_motion.py results/hardware/h0/新预览目录 \
  --start-deg J1 J2 J3 J4 J5 J6
```

预览通过且现场就绪后，操作者选择新的动作结果目录，指定正在运行的
`--recording-directory "$RUN"`，再加 `--execute`。
动作是 MOVE_J 10%、J6 在 4 s 内 +2°、停 3 s、4 s 返回、停 3 s，夹爪
40→15→40 mm、1 N。正常结束保持使能；Ctrl+C/SIGTERM 请求与旧入口一致的阻尼
急停，可能下沉，现场保留物理急停。没有 reset、归零、CPV、保护参数或固件写入。

锁文件只能防止本入口的重复实例，不能阻止外部脚本；现场必须关闭其他运动发送端。
命令循环完成与实际运动成功分开判断：检查关节、夹爪反馈和现场观察，保留失败包。

## Q12 标定的单次定位

同一个 `scripts/h0_operator_motion.py` 使用 `--calibration-target-deg J1 J2 J3 J4 J5 J6` 接收一个以度为单位的六轴绝对目标。它与原 H0 的 `--start-deg` 互斥，共享同一把发送锁。默认只读预览会记录当前关节、控制器状态及所有已发现的就绪问题。该模式跳过使能、回零、往返动作和夹爪操作。控制器须已在 CAN 控制模式，六轴已使能且无故障，起始位姿已停稳，实测起点和目标均在 SDK 限位内。示教模式下可做只读预览与静止采图。

单次定位沿用 H0 的小幅速度尺度，每关节每次最多 2°，参考角速度至多 0.5°/s，MOVE_J 速度档为 10%。操作者在可见的本机终端保有 Ctrl+C 和物理急停。实际运动需先看现场空间、线缆和预览目标，在新的结果目录用同一组角度加 `--execute` 及既有独立记录器的 `--recording-directory`。活动的 H0 记录器保留移动过程。若使用 π 的逐姿态采集，则在本次定位记录器退出后运行一次 `capture_pose.sh`。每次定位结束停在目标，不自动换下一个姿态。

定位过程逐帧记录主机 CAN 提交结果，另存一次高层目标序列与实测到位结果。到位要求 MOVE_J 到位反馈、各轴目标误差不超过 0.5°，并在连续 0.5 秒内各轴实测范围不超过 0.1°。正式标定另用每次拍摄的静止窗核对。发生跟踪偏差、故障、执行中断或反馈中断时沿用原入口的阻尼急停，现场留意机械臂可能下沉。

操作者另行明确要求六轴物理回零时，用互斥的 `--handoff-near-zero` 显式选择本次返回。它只处理已在各轴 5° 内的近零位，经现场确认示教灯已熄灭、全臂空间已清空后，按 [Piper H 手册 §3.1.3](https://agilexsupport.yuque.com/staff-hso6mo/alxgtf/ay1awrn2hrhn1krg) 处理已结束示教的交接。它逐步等待待机和 CAN 模式及六轴仍已使能的反馈，再返回全零目标。对于略超 SDK 边界且超出量在 1° 内的轴，首个参考直接采用已指定的 0°；其余轴从实测角度插值。使能、复位、编码器写零均未接入该模式。正常单姿态定位不调用这个返回流程。

## 停止、重启和证据

机械臂停稳后，正常 Ctrl+C 停止相机进程，再执行 `bash scripts/h0_camera.sh`，确认
两路图像及 CameraInfo 恢复。记录器可以保持运行以记录这段**有意停流**，再正常退出。
重启窗口与稳定采集窗口的间隔统计分开解释。

```bash
/usr/bin/python3 scripts/h0_analyze.py "$RUN"
```

- `stream_timing.csv`：全部图像/参数消息原始 ROS header 与本机回调接收时间。
- `joints.csv`：三报文形成的真实六关节接收组，rad；保留 CAN 首/末时间和 SDK 时间。
- `gripper.csv`：0x2A8 的真实宽度/力反馈，m/N；不是命令值。
- `arm_snapshots.jsonl`：约 10 Hz 缓存快照，包含各消息自身更新时间；不能当作反馈频率。
- `motion_events.jsonl`、`motion_sdk_tx.csv`：动作事件和 SDK 发送调用；不能单凭发送成功宣称运动成功。
- `samples/`：原始 RGB PNG、未经缩放/裁剪/伪彩替代的 uint16 深度 NPY；深度 1 count=1 mm，0 无效。
- `preview.avi`：RGB＋最近深度预览、固定 30 FPS。右侧只有显示色图，并非几何配准。
  精确时序看 `video_frames.csv` 和源时间表；诊断掉帧阶段的定帧率视频不可当作实时长度。
- `$RAW/camera_bag/`：本次开头指定时长的原始 ROS 消息；`$RAW/raw_can.csv`：整个窗口的原始 CAN。

完整 AVI、周期样本、bag 和原始 CAN 留本地。Git 提交可复核的精选样帧、原始深度小样本、
短视频、状态/时间表与报告。软件接收关联不是硬件同步；相机内参来自设备/驱动，未重新标定。
RGB CameraInfo 的 D 全零与设备非零 r_k 的差异仍须在后续视觉测量前处理。

### 重连后在失能状态核对 CAN 指令模式

2026-11-21 Q12 现场由操作者明确要求用 SDK 接通 CAN。H0 同一独占入口新增互斥的 `--select-can-disabled`。该操作只在新鲜反馈显示控制器正常、静止且六个驱动均失能时选择 CAN 的关节位置控制模式。执行时检查独立接收器并只发一次模式请求，回读两项模式、使能与六轴角。窗口或现场 STOP 不会因此启动定位或采集。

本次切换独立接收 1,200 组六轴姿态，接口 TX 增量 1，模式请求获得响应，关节实测角无变化，驱动保持失能。随后用 SDK 只读查询，控制器返回 J2 的 0°～180° 和 J3 的 −170°～0°。当时 J2=−3.221°，J3=+1.530°，未上力。此模式不能作为故障复位或开机回零入口。
