# M1＋Piper H 基础联合模型：装配与可视调试交付

日期：2026-11-16。起点为仓库 H0 提交 `284c1f3f1bb9d5096003433f6153a9c5e95d6189`。

## 1. 当前完成到哪一层

已实际生成并编译：M1 单体、带官方夹爪和名义腕部附件的 Piper H 单体、联合 URDF、联合原生 MJCF，以及联合机器人＋被动单门场景。已经完成三组姿态的独立 FK 对照、真实 MuJoCo 离线渲染、原始虚拟 RGB/深度输出和 8 秒运动学短片。

**当前模式为 KINEMATIC_PREVIEW。没有执行整机 `mj_step`，没有实现轮足站立保持，也没有执行接触开门。** 此轮没有启动相机驱动、CAN、SDK 或任何实机动作，没有修改 H0 的证据与实测结论。

桌面实时入口 `scripts/live_assembly.py` 已实现，并用同一 MuJoCo 版本验证其实际加载、home、关节与相机数据接口；准备环境没有 DISPLAY/WAYLAND，**用户 Linux 桌面的开窗、按键与重载仍待本机验证**。下一轮首先完成这一项，不能用本报告中的离线图片代替。

## 2. 实际准备环境与执行

- 独立 Linux 准备环境，Python 3.12.14、MuJoCo 3.3.0；依赖位于独立虚拟环境，没有使用或修改用户的 OSCBF／ROS 环境。
- 官方源通过 `scripts/fetch_sources.py` 实际下载；`reports/source_versions.json` 记录固定提交与实际 HEAD 一致、上游工作树没有本地修改。
- `scripts/inspect_sources.py` 完成源文件及网格清单，无缺失资源。
- `scripts/build_assembly.py --stage all` 完成实际编译。生成器先在同目录临时 XML 中编译、加入 home、再次编译，然后替换正式场景，避免 `--watch` 读取半成品。
- `scripts/check_assembly.py` 完成三组合法姿态的独立 URDF FK 与 MJCF 对照。
- 仅对离线渲染命令选择 `MUJOCO_GL=egl`，执行 `scripts/capture_assembly.py --video` 和带门场景的非视频导出；没有设置全局 EGL。
- 本机入口保持 `bash scripts/setup_env.sh` 和 `bash scripts/project_env.sh python ...`。上述准备环境结果不代表用户本机已创建 `.venv` 或打开桌面窗口。

## 3. 官方来源与模型组成

| 部分 | 固定来源 | 处理方式 |
| --- | --- | --- |
| M1 四轮轮足 | [MATRiX_Python_SDK 7c63590](https://github.com/zsibot/MATRiX_Python_SDK/tree/7c63590c21beba2f633c344b96bc29a695d7a807/model/zgws) | 使用 ZGWS 原生 body/joint/inertial/motor/sensor 树，不替换成小狗模型 |
| Piper H＋官方夹爪 | [agx_arm_urdf 680fa92](https://github.com/agilexrobotics/agx_arm_urdf/tree/680fa925cd00db7e2628563d2edc5540963045de/piper_h) | 展开 with-gripper Xacro 的明确 include，移除自带 world／固定根，不重复附加夹爪 |
| 支架候选几何 | [piper_ros ac41fcb](https://github.com/agilexrobotics/piper_ros/tree/ac41fcbcdda598f01b51cf6175ed9a24d0dacadc) | 使用已有独立 OBJ；原 DAE 节点变换已在提取时处理，不再乘毫米缩放或重置网格原点 |
| 相机外壳、安装座 | 本工程名义几何 | 简化盒体，尺寸及安装参数在 config/assembly.yaml，不作为实测 CAD |

Piper 首版 visual 明确复用官方 collision STL，并使用统一颜色；**没有转换其 DAE 精细外观或材质**。官方质量、质心和惯量独立保留，外观简化不用于反推质量。M1 源 STL 中 12 个二进制文件的头部以 `solid` 开始，生成器依据其真实字节布局只重写 80 字节头，避免被误读为 ASCII；没有缩放或删除三角形。

派生网格在 `assets/converted/`，按固定源可重建，不重复上传全部大网格；新拉取工程后必须先获取源并构建。URDF 网格引用相对 `description/`，MJCF 相对 `sim/robots/` 或 `sim/scenes/`。RViz 的 ROS 包／资源 URI 启动整合尚未提供或验证；当前可见调试使用 MuJoCo MJCF。

## 4. 整机树与夹爪关系

- M1 根 body 为 `m1_base_link`，整机保留唯一的 `m1_floating_base`。
- 背部固定安装 frame 为 `m1_arm_mount`，Piper 根 `piper_base_link` 固定连接到该 frame。
- M1 保留 12 个腿关节＋4 个轮关节和 16 个 motor。
- Piper 有 6 个臂关节、2 个实际夹指 slide joint；一个指间 equality 约束和一个夹爪 motor。
- `piper_camera_bracket`、`piper_camera_shell`、`piper_wrist_optical_frame` 均固定在 `piper_gripper_base`，不连接活动夹指。
- URDF 保留官方虚拟宽度主关节 `piper_gripper` 及 mimic；MJCF 移除无实际机构的主关节，显式实现 `q2=-q1`。开口宽度 `w=2*q1`，因此 `q1=w/2`、`q2=-w/2`。
- MuJoCo 3.3.0 的模型入口使用生成的 MJCF，不能依赖直接导入 URDF 自动实现 mimic。

M1 的衍生 URDF 用等价的完整惯量张量表达源主轴惯量，惯性原点 rpy 为零；原生 MJCF 保留源惯性姿态。源质量与物理惯量没有调整。M1 URDF 的 `velocity=1 rad/s` 是源文件未提供速度上限时的描述占位值，不是实物参数。

## 5. 当前名义安装参数

长度单位 m、角度单位 rad；RPY 是固定轴 `Rz(yaw) Ry(pitch) Rx(roll)`。

| 关系 | xyz | rpy | 状态 |
| --- | --- | --- | --- |
| M1 base → Piper base | `[0.05, 0, 0.18]` | `[0, 0, 0]` | 名义背部安装，非实测 |
| gripper_base → 支架 mesh frame | `[0, 0, 0]` | `[-π/2, 0, +π/2]` | 参照形状／照片的初始对齐 |
| gripper_base → 相机壳体 | `[-0.092, 0, 0.026]` | `[0, -π/2, 0]` | 名义外形中心 |
| gripper_base → optical frame | `[-0.092, 0, 0.042]` | `[0, 0, -π/2]` | 非手眼标定结果 |
| gripper_base → TCP | `[0, 0, 0.138]` | `[0, 0, 0]` | 名义 TCP，可在配置修改 |

M1 base 网格局部最高点约 `z=0.08208936`；安装座上表面为 `z=0.18`，首版用 150×150 mm 的名义安装座连接二者。这个网格最高点不能替代实际安装面测量。相机外壳全边长采用 `[0.03, 0.09, 0.026]`，不是 DC1 规格声明。

`accessory_payload_mode=omitted`：支架、相机以及名义安装座额外载荷暂不计。MJCF 附件 geoms 显式 `mass=0`／`density=0`，并关闭根据几何推导惯量；没有用默认密度偷偷增加质量。当前生成器只支持这个载荷模式，真实载荷需后续明确加入惯性数据。

## 6. 初始姿态与碰撞表达

M1 源 `home` 是 XML 注释，不是活动 keyframe。此处只复用其中的关节姿态候选：前腿 hip/knee 为 `+0.6/-1.2`，后腿为 `-0.6/+1.2`，外展和轮角为 0。源根高 0.52 m 会造成轮网格穿地约 21.659 mm；同一姿态的几何接地根高约 0.54165915 m，所以预览设为 **0.54266 m**，留约 1 mm 初始几何间隙。

Piper home 为 `[0, 0.8, -1.4, 0, 0.6, 0] rad`，夹爪开口 40 mm。这是独立选取的仿真装配姿态，不来自 H0 绝对角度，也不会下发到实机。

碰撞几何统一放在 group 3，默认隐藏显示，F9 可显示；显示开关不会禁用物理碰撞。Piper 基座与 link1 的源 STL 在相邻关节壳体处重叠约 6 mm，固定根预览显式排除此邻接对，与浮动整机已有父子过滤的意图一致，不修改网格。支架用两个板状碰撞代理，避免单一凸包填满弧形空腔；指爪 mesh 仍使用 MuJoCo 凸包接触近似。

最终 home 在单体／整机预览中没有生成接触点。这个结果只描述当前姿态和所用碰撞过滤，不能证明所有工作空间无自碰撞，更不能证明浮动机器人能够保持站姿。

## 7. 实际编译与 FK 结果

| 模型 | nq | nv | nu | neq | 模型质量 kg |
| --- | ---: | ---: | ---: | ---: | ---: |
| M1 单体 | 23 | 22 | 16 | 0 | 38.820510000 |
| Piper H＋夹爪＋名义附件 | 8 | 8 | 7 | 1 | 4.716554081 |
| 联合机器人 | 31 | 30 | 23 | 1 | 43.537064081 |
| 联合机器人＋被动单门 | 32 | 31 | 23 | 1 | 55.537064081 |

`nq` 是位置坐标数；浮动根含四元数，所以不能把 nq 直接称作独立自由度数。夹指 equality 也会进一步约束运动。质量是源模型参数之和，不是整机称重结果；门的 12 kg 也只是已有场景设计值。

独立检查脚本用 SciPy 的旋转和 URDF 树计算，不导入生成器的坐标变换函数。三组姿态包含 home 臂／底盘＋0 mm 夹爪，以及少量关节正反向变化配合 40／80 mm 开口。

- 对照 34 个 body/site 目标，包括轮足链、法兰、TCP、安装座与腕部附件。
- 仅跳过 MuJoCo 中有意删除的虚拟 `piper_gripper_link`。
- 最大位置误差：约 **3.044×10⁻¹⁶ m**。
- 最大旋转矩阵元素差：约 **9.806×10⁻¹⁶**。
- 两指 mimic 坐标误差为 0，并核对实际 equality 系数与残差。

这些误差表示两种数字描述之间的数值一致性，不是实物毫米级或更高精度的标定结果。原始逐帧数据见 [assembly_kinematics.json](assembly_kinematics.json)，编译／资产／名义参数见 [assembly_build_all.json](assembly_build_all.json)。

## 8. 图像、深度与视频

- [M1 单体](../results/assembly/m1_single.png)、[Piper H 单体](../results/assembly/piper_single.png)：用实际 home 静态渲染，未推进物理时间。
- [整机概览](../results/assembly/overview.png)、[侧面](../results/assembly/side.png)、[正面](../results/assembly/front.png)。
- [腕部结构局部](../results/assembly/with_door/wrist_detail.png)：能分辨官方夹爪、支架候选和简化相机壳体。
- [腕部相机看门](../results/assembly/with_door/wrist_rgb.png)、[深度预览](../results/assembly/with_door/wrist_depth_preview.png)。
- 原始虚拟深度为 `float32[480,640]`，单位 m，保存 MuJoCo Renderer 的线性光轴深度；同目录 `wrist_rgb_uint8.npy` 与其逐像素配对。PNG 标题／色标是展示层，不写入原始数组。
- 同一外参在空场景主要看到背景与远处地面；加入被动门后看到门板和 U 形把手。未通过修改手眼参数来制造可见结果。该 home 没有保证夹指处于腕相机视野内，后续视角覆盖需继续检查。
- [8 秒短片](../results/assembly/kinematic_preview.mp4)：已实际解码核对 240 帧／30 fps／8 s。只改变 joint2 约 5°并返回，夹爪 40→80→20→40 mm；画面标注 KINEMATIC_PREVIEW。它是离线运动学演示，不是实时桌面录像。

相机保持 `synthetic_aligned_rgbd`，fovy 60°、640×480 是当前虚拟设定。真实 H0 的 RGB 与深度分辨率不同、未对齐、RGB 畸变参数存在差异，这些实测事实没有被此理想相机覆盖。手眼、标定板、附件净重／惯量均继续后置。

## 9. 实时调试交付与下一步

本机按 [LIVE_DEBUGGING.md](../docs/LIVE_DEBUGGING.md) 打开窗口，或把 [LIVE_ASSEMBLY.txt](../prompts/LIVE_ASSEMBLY.txt) 交给 Linux Codex。窗口支持选择／微调关节、夹爪开闭、腕相机、碰撞显示、重载和恢复 home；配置修改后先重建 XML，`--watch` 成功编译后重开窗口。

第一项是让用户真正看到 M1、Piper 和整机，并在调整时看到变化。桌面确认和修正按有意义节点及时普通提交／推送，不自动按帧提交。之后再进入固定基座单门接触，逐步接入轮足保持／慢行和自由基座任务。

官方确有 [MATRiX_Robot_MC](https://github.com/GENISOM-AI/MATRiX_Robot_MC) 外部运控运行包，支持表包含 `zsm-1w→ZGWS`、`zgwsarm→ZGWS_ARM`；但本项目没有下载／接入该包，也未验证其与独立 MuJoCo＋Piper H 的兼容性。[v0.6.6 发布记录](https://github.com/GENISOM-AI/MATRiX_Robot_MC/releases/tag/v0.6.6) 明确其打包检查未包含实机或仿真运动试验。因此当前模型中的 16 个 M1 motor 仍是控制接口，不代表已经有站立控制器。

## 10. 本机桌面节点：M1（2026-11-16）

本机 Python 3.10.12 / MuJoCo 3.3.0，X11 :1。已恢复固定官方源、构建 M1 并实际打开 native viewer；与准备侧离线结果分开记录。[home 桌面截图](../results/assembly/live_local/m1_home.png)、[髋关节 +6°](../results/assembly/live_local/m1_hip_plus6.png)、[碰撞凸包视图](../results/assembly/live_local/m1_collision_hulls.png)、[18 秒桌面录像](../results/assembly/live_local/m1_desktop.mp4)。

实际操作 FAR hip +6°、knee −4°、wheel +6°，home 与退出正常；事件见 `m1_events.jsonl`。碰撞显示发现重叠闪白，F9 已改为碰撞专用视图；F6 切换已有检查相机，并清除原生 F6 的坐标轴副作用。没有修改 M1 物理模型或安装参数。GUI 和操作已由桌面捕获核对，未收到用户明确观看反馈。Piper/整机的本机检查继续进行。

## 11. 本机桌面节点：Piper H

实际 `--stage piper` 构建、桌面开窗，J1/J2 各 +4°、J3 −4°，双指 100→0 mm，F6 腕部近景、F9 凸包/附件代理、F8 虚拟相机、F10 重载与 home 恢复。用户对腕部近景及夹爪开合明确回复“能看到，继续”。

[六轴概览](../results/assembly/live_local/piper_home.png)、[张开](../results/assembly/live_local/piper_gripper_open.png)、[闭合](../results/assembly/live_local/piper_gripper_closed.png)、[碰撞几何](../results/assembly/live_local/piper_collision.png)、[24 s 桌面录像](../results/assembly/live_local/piper_desktop.mp4)。空场景腕相机实测只有背景与远地面；联合带门场景再核对目标，未调整外参来伪造视野。事件见 `piper_events.jsonl`，没有 `mj_step` 或硬件访问。

## 12. 本机联合预览与暂停点

用户于 2026-11-16 要求“今天就这样吧，先暂停”。已正常关闭本轮 viewer；没有启动硬件或 `mj_step`。

暂停前实际执行 `build_assembly.py --stage combined`、默认 `live_assembly.py --watch` 和 `check_assembly.py`。联合模型 31/30/23/1、43.537064081 kg 未变；三姿态 FK 最大位置差 3.044e-16 m、旋转矩阵差 9.806e-16。保留 [侧面](../results/assembly/live_local/combined_side.png)、[正面](../results/assembly/live_local/combined_front.png)、[腕部局部](../results/assembly/live_local/combined_wrist_detail.png)、[开口 100 mm](../results/assembly/live_local/combined_gripper_open.png)、[闭合时碰撞代理](../results/assembly/live_local/combined_wrist_collision.png)。证据来自本次 X11 屏幕捕获；事件为 `combined_events.jsonl`，不是动力学数据。

名义安装参数未改变，不为了演示重载制造安装修改。Piper 单体已验证 F10，且在 combined 构建重写其 XML 时实际完成 watch 重载。联合场景的带门腕视角、相机固定关系量化与重载收尾尚未完成；初始自由视角曾裁掉腕部上缘，F6 命名视角正常，默认取景仍待修正。不能把整个本机装配检查或后续动力学标为完成。

M1/Piper 节点 `f8786a8`、`728fc8a` 已普通推送。HTTPS 首次 TLS 中断，随后缺少 credential helper；最终命令 `git -c http.version=HTTP/1.1 -c credential.helper= -c 'credential.helper=!gh auth git-credential' push origin main` 复用本机已有登录成功。

## 13. 2026-11-20：本机可见检查收尾

`mjv_defaultFreeCamera` 修正初始取景，[默认窗口](../results/assembly/live_20261120/default_view.png) 包含腕部与四轮。保持窗口时由另一桌面终端运行 `build_assembly.py --stage combined`，实际 watch 重载成功，[重载画面](../results/assembly/live_20261120/reloaded_view.png) 和事件日志对应。安装参数没有改变。

[本机腕相机看门](../results/assembly/live_20261120/wrist_door.png) 实际显示门板和 U 形把手，未改变外参。`check_assembly.py` 新增 9 个开合/腕姿态检查：手指运动引起相机世界位姿变化 0；相对 gripper_base 位姿误差不超过 5.93e-17 m、5.55e-16。三组 FK 继续通过。全部是名义运动学结果，非手眼标定或开门成功。下一步是独立 P4 固定基座真实接触场景。
