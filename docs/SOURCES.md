# 已核对的来源与使用边界

本文件保留可追溯入口。固定提交定义首版来源；并不宣称它们是最新版本。下载脚本不会安装厂商 SDK 或执行硬件控制。

## 1. M1 四轮轮足

- 官方仓库：[zsibot/MATRiX_Python_SDK](https://github.com/zsibot/MATRiX_Python_SDK)。
- 固定提交：`7c63590c21beba2f633c344b96bc29a695d7a807`。
- 模型：[model/zgws/zgws.xml](https://github.com/zsibot/MATRiX_Python_SDK/blob/7c63590c21beba2f633c344b96bc29a695d7a807/model/zgws/zgws.xml)，网格在同级 `assets/`。
- 本任务的官方型号入口是 **ZGWS**，不使用 ZSL/xgw 小型机器人替代。
- 已读模型包含自由基座、12 个腿关节、4 个轮关节、16 个 motor。该目录没有 M1 URDF；本项目将针对这棵 MJCF 树衍生 URDF。
- 模型中的力矩范围、质量等只视为官方模型参数，不自动等于实物连续性能或用户称重结果。

只获取 `model/zgws`；使用原生 MuJoCo，不依赖厂商仿真 UI 或兼容加载器。原 MJCF 不包含完整地面场景，注释里的姿态不是生效 keyframe。

### 官方运控的准确结论

[GENISOM-AI/MATRiX_Robot_MC](https://github.com/GENISOM-AI/MATRiX_Robot_MC) 的公开说明存在 `zsm-1w → ZGWS` 和 `zgwsarm → ZGWS_ARM` 对应关系，因此不是“没有 M1 官方运控入口”。但这里没有将大体积 release 下载解包，也没有验证其二进制/策略能在本项目的 MuJoCo、状态排列、载荷和 Piper H 组合下直接运行。

不能将 `ZGWS_ARM` 名字当作本项目已经适配的证据。P0–P3 不依赖它；进入 P5 时再逐项核对模型、状态/action、频率、策略输入与机械臂接口。上游 release 是否含可用 M1 URDF、确切内部路径和运控可用性，需实际解包后才能确认。

## 2. Piper H 和官方夹爪

- 官方仓库：[agilexrobotics/agx_arm_urdf](https://github.com/agilexrobotics/agx_arm_urdf)。
- 固定提交：`680fa925cd00db7e2628563d2edc5540963045de`。
- [Piper H 本体 URDF](https://github.com/agilexrobotics/agx_arm_urdf/blob/680fa925cd00db7e2628563d2edc5540963045de/piper_h/urdf/piper_h_description.urdf)。
- [Piper H 带夹爪 Xacro](https://github.com/agilexrobotics/agx_arm_urdf/blob/680fa925cd00db7e2628563d2edc5540963045de/piper_h/urdf/piper_h_with_gripper_description.xacro)。
- [独立夹爪 URDF](https://github.com/agilexrobotics/agx_arm_urdf/blob/680fa925cd00db7e2628563d2edc5540963045de/agx_gripper/urdf/agx_gripper_description.urdf)，用于核对，不重复叠加。
- 用户给出的 [Piper 官方语雀入口](https://agilexsupport.yuque.com/staff-hso6mo/alxgtf/ay1awrn2hrhn1krg) 保留为硬件文档入口；工程中具体 link、joint、mimic 与 mesh 的结论以以上实际源码为依据。

本体与夹爪资源共用 `package://agx_arm_description/agx_arm_urdf/` 前缀。首版下载 `piper_h` 和 `agx_gripper`，不以普通 Piper 或其他手爪替代 Piper H。

## 3. 支架、相机与用户照片

- 用户支架链接：[JD SKU 100392215766](https://item.jd.com/100392215766.html)。
- 用户相机链接：[JD SKU 100301597275](https://item.jd.com/100301597275.html)，本项目按 DaBai DC1 记录。
- 支架候选来源：[piper_ros/camera_v3.dae](https://github.com/agilexrobotics/piper_ros/blob/ac41fcbcdda598f01b51cf6175ed9a24d0dacadc/src/piper_description/meshes/dae/camera_v3.dae)。
- 提取的是单独 `binary_stl_file_039-mesh`，已应用场景节点矩阵；保留米单位和原场景坐标，不包含相机或夹爪。
- 文件、许可与处理细节见 `assets/accessories/`，照片见 `materials/photos/` 和 `docs/PHOTO_REFERENCE.md`。

照片与支架结构吻合，可以开始名义装配；尚未确认零售工程修订与实测安装外参。当前不因此暂停，也不把假设写成实物标定。

后续实机相机参考：[orbbec/ros2_astra_camera](https://github.com/orbbec/ros2_astra_camera) 中的 `dabai_dc1.launch.xml`，以及 [OrbbecSDK_ROS2/main](https://github.com/orbbec/OrbbecSDK_ROS2/tree/main) 的旧设备支持路径。届时按实际设备标识和固件核对，不能拿其他 DaBai 型号的 CAD、内参或支持分支直接代用。本阶段不安装这些驱动，也不以真实驱动作为 MuJoCo 图像输出条件。

## 4. MuJoCo 与项目执行

- [MuJoCo 3.3.0 XML 参考](https://mujoco.readthedocs.io/en/3.3.0/XMLreference.html)。
- [MuJoCo 3.3.0 URDF 解析器源码](https://github.com/google-deepmind/mujoco/blob/3.3.0/src/xml/xml_urdf.cc)：已核对本项目关心的 mesh basename、mimic、effort 与坐标处理。
- [MuJoCo 3.3.0 建模说明](https://mujoco.readthedocs.io/en/3.3.0/modeling.html)。
- [Codex AGENTS.md 指南](https://developers.openai.com/codex/guides/agents-md)。`PROJECT_STATE.md` 和 `prompts/` 是本项目的接续约定，不是额外产品功能。

## 5. 来源盘点和实际验证的区别

`scripts/fetch_sources.py` 按 lock 获取首次使用的源模型。现有有效 checkout 会保留，其实际 HEAD 和修改状态写入 `reports/source_versions.json`；重跑不会自动覆盖它使之符合 lock。

`scripts/inspect_sources.py` 盘点 XML/Xacro 结构和本地资源是否存在，输出 `reports/source_inventory.json`。它没有展开所有 Xacro，也不证明 MuJoCo 编译、几何正确、控制稳定或开门成功。P2/P3 由后续实际加载、FK 和图像检查补齐。

本仓库不会仅凭期刊分区或论文标题选择研究路线。论文模块复现可以在基础任务可运行后单独记录；当前没有把尚未逐篇核实的论文方法写成已经复现。
