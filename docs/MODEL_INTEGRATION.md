# 模型组装与转换任务

目标是把 **铜锤 M1 四轮轮足、Piper H、官方夹爪、腕部支架和 DaBai DC1** 组合成可检查、可控制的 MuJoCo 模型。官方文件保留在 `vendor/`；修改、转换和安装参数放在工程自己的目录。第一版允许使用明确记录的仿真假设，实物称重、标定板和手眼标定后置。

## 1. M1：保留原生 MJCF 的动力学

采用官方 `model/zgws/zgws.xml` 及其引用的 17 个 STL。该目录没有 M1 URDF；需要的 URDF 应标为“基于官方 ZGWS MJCF 衍生”，原生 MJCF 继续作为动力学来源。[1]

针对这棵模型树转换，保留各腿实际参数，不为了外观对称修改小偏移。根 `base_link` 的原始高度 `0.5 m` 是场景放置，不是机器人内部安装关系。转换规则：

| 内容 | 必须保留的含义 |
|---|---|
| 父子变换 | MJCF `quat` 为 **wxyz**；转换到 URDF `origin` 时保留完整旋转 |
| 关节 | 保留轴、原点和限位；轮关节改为 `continuous` 属于显式建模选择 |
| 惯性 | `inertial pos` 是质心；惯性四元数定义主轴，不能丢弃 |
| 盒体 | MJCF `box size` 是半尺寸，URDF 是全尺寸，转换时乘 2 |
| 速度上限 | 原 MJCF 未提供的值单独标为项目假设，不称作官方规格 |

惯性可保持主轴朝向与对角值，也可旋转为完整张量：

\[
I=R\,\mathrm{diag}(I_1,I_2,I_3)R^T.
\]

执行器、传感器和接触参数保留在 MJCF 层。原模型的 16 个 `motor` 接收力矩语义的输入，不能直接向 `ctrl` 填目标角度。

## 2. Piper H：正确接入本体和夹爪

`piper_h_with_gripper_description.xacro` 直接包含完整本体 URDF，**不是带 parent/prefix 参数的宏**。在派生副本中去掉 Piper 自带的 `world` 和 `world_to_base_link`，用固定安装关节把 `piper_base_link` 接到 M1 安装座。[2][3]

带夹爪 Xacro 已含夹爪，不再叠加独立夹爪文件。确定的固定连接为：

- `link6 → flange_link`：零平移、零旋转。
- `flange_link → gripper_base`：平移 `[0,0,0.0045] m`。

建立 link/joint 名称映射，逐项更新 `parent`、`child`、`mimic` 等引用。不要用全局字符串替换破坏资源路径。

## 3. 夹爪：宽度命令与物理坐标分开

官方描述的 `gripper` 是连接空 link 的宽度 master，范围 `0–0.1 m`；两指分别为 `+0.5` 和 `−0.5` mimic。[3] MuJoCo **3.3.0** 的 URDF 解析器不处理 mimic，物理模型应去掉空 moving master，保留两指及其惯性，并加入耦合约束：[4]

\[
q_1=w/2,\qquad q_2=-w/2,\qquad 0\leq w\leq0.1\ \mathrm{m}.
\]

当两指参考位置均为零时，可采用：

```xml
<equality>
  <joint name="piper_finger_coupling"
         joint1="piper_gripper_joint2"
         joint2="piper_gripper_joint1"
         polycoef="0 -1 0 0 0"/>
</equality>
```

使用一个夹爪控制输入，上层开口宽度不能直接当单指位移。保留官方两指各自的轴和安装旋转，实际显示检查开合方向。

可设 `tcp_nominal = gripper_base + [0,0,0.138] m` 作为初始接口；它来自夹指关节原点，后续根据接触面调整，不能称为实机已标定 TCP。

## 4. 几何、坐标与质量

MuJoCo 3.3.0 支持 OBJ、二进制 STL 等网格，不直接加载 DAE。转换 DAE 时应用场景节点变换和单位，不只提取裸顶点；已提供的支架 OBJ 已是米单位，不再乘 `0.001`。[5]

**所有导入网格使用唯一文件 basename。**3.3.0 URDF 解析器按去路径、去扩展名的名字建立 mesh，单靠 `strippath=false` 不能解决重名。采用 `m1_base_link_collision.stl`、`piper_base_link_visual.obj` 等名字，并更新引用。[4]

初始导入保留 `discardvisual=false`、`fusestatic=false`、`strippath=false`，明确解析 `package://` 路径。手写 MJCF 时优先使用四元数；URDF 的固定轴 `rpy` 对应 MJCF `eulerseq="XYZ"`，同时设置 `angle="radian"`。[5]

保留官方本体惯性。不要默认打开 `balanceinertia=true` 掩盖参数问题。视觉与碰撞不能重复贡献质量；夹指间隙和门把手孔洞应使用合适的组合碰撞体，避免整体凸包把空隙填实。[5]

URDF 的 `effort` 在该版本中用于关节执行器合力限幅，但导入过程不会自动生成完整控制器，`velocity` 也没有变成硬速度约束。[4] 仿真执行器、控制频率和速度限制另列配置。官方模型字段只作为模型来源记录，不能据此宣称已确认实机电机的连续输出能力。

## 5. 腕部附件：按照片先完成名义装配

四张实物照片已足够核对支架结构和朝向。将照片中的固定壳体与 Piper H 的实际零件划分对应，再确定附件父 link；支架不接活动夹指。独立 OBJ 保留旧场景坐标，旧完整组合模型的 `link6` 偏移不能直接当作 Piper H 安装变换。

本阶段统一采用：

```yaml
accessory_payload_mode: omitted
mount_parameter_status: simulation_assumption
camera_mode: synthetic_aligned_rgbd
hardware_calibrated: false
```

`omitted` 表示暂不计相机与支架的额外载荷。**附件 MJCF geoms 显式设 `mass="0"` 或 `density="0"`**，并保持既有本体惯性，避免缺少附件惯性时被默认密度自动补入质量。附件仍保留视觉与碰撞，并用固定连接安装。质量缺失不作为当前开工报错或等待条件。

在 MJCF 中，优先把零质量附件 geoms 和 camera 直接放进具有官方显式 inertial 的固定末端主体，用局部位姿与 sites 表示各安装坐标；URDF 可继续保留 fixed link 结构。不要创建只有零质量 geoms、没有 inertial 的新 body 后让编译器自动算质心——MuJoCo 3.3.0 可能报 `body mass is too small`。这是表示方法问题，不需要为了绕过报错虚构附件实测质量。

第一版从同一个 MuJoCo camera 输出 RGB 与深度，作为理想对齐图像观察门把手和夹爪遮挡。FOV、外壳简化尺寸、安装位姿均标为 `simulation_assumption`。这只是初始仿真，不代表 DaBai DC1 的实物光学标定、噪声或有效测距范围；模型装配不要求测量、购买标定板或先运行实机驱动。

用户另加 H0 实机联调回合，见 docs/HARDWARE_INTEGRATION.md。H0 可以读取真实 RGB/深度、CameraInfo、实际机械臂状态并观察运动中的遮挡；这不自动提供手眼外参。真实流参数保存在独立硬件配置，不把真实未对齐 RGB/深度套用成仿真的同一理想光心。

保留“支架安装基准、相机外壳、光学坐标”各自的含义，外壳中心不自动等于光心。MuJoCo 相机沿自身负 Z 轴观察、Y 轴向上；建立虚拟光学坐标后检查画面实际方向。[5] 先让夹爪前方目标出现在画面中，再调整视角参数，不从手机照片推算精确焦距。

## 6. 装配完成的判断

只保留一个整机自由基座。无门、浮动基座、两真实夹指且一个耦合约束时，结构预期为 `nq=31, nv=30, nu=23, neq=1`；其中输入为 `16+6+1`。固定基座和加门场景另算，附件不增加自由度。

在几组合法姿态下对照 URDF/MJCF 的轮心、法兰、夹指及 TCP 位姿，检查单位、旋转、开合与碰撞几何即可。随后通过真实 `mj_step` 进入动力学；`mj_forward` 展示只说明运动学。固定底盘下的臂动作与释放基座后的稳定移动操控分别记录。

输出至少包括组合描述、可独立修改的安装配置、关节与执行器映射、正面和侧面装配图，以及腕部相机观察图。夹爪开口变化应保持相机相对固定主体不动；轮足原始接触体仍应存在。出现实际网格加载错误时修正对应文件，不通过删除零件获得表面上的“加载成功”。

## 官方参考

1. [M1/ZGWS 原生 MJCF](https://github.com/zsibot/MATRiX_Python_SDK/blob/7c63590c21beba2f633c344b96bc29a695d7a807/model/zgws/zgws.xml)
2. [Piper H 本体 URDF](https://github.com/agilexrobotics/agx_arm_urdf/blob/680fa925cd00db7e2628563d2edc5540963045de/piper_h/urdf/piper_h_description.urdf)
3. [Piper H 官方夹爪 Xacro](https://github.com/agilexrobotics/agx_arm_urdf/blob/680fa925cd00db7e2628563d2edc5540963045de/piper_h/urdf/piper_h_with_gripper_description.xacro)
4. [MuJoCo 3.3.0 URDF 解析器](https://github.com/google-deepmind/mujoco/blob/3.3.0/src/xml/xml_urdf.cc)
5. [MuJoCo 3.3.0 XML 参考](https://mujoco.readthedocs.io/en/3.3.0/XMLreference.html)
