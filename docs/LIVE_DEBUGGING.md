# 本地 Linux 实时查看装配变化

本轮在用户桌面逐个打开 **M1 单体、Piper H 单体、M1＋Piper H 整机**，边检查几何与关节关系，边修正模型。默认入口是 [live_assembly.py](../scripts/live_assembly.py)：窗口标题带 `KINEMATIC_PREVIEW`，只调用 `mj_forward`，不推进物理时间。

当前真实工作目录为 `/home/kaiwen/research/dog-and-arm`。H0 已完成，记录以 [PROJECT_STATE.md](../PROJECT_STATE.md) 和 [H0 报告](../reports/H0_HARDWARE_REPORT.md) 为准；本流程不重新验机、不启动相机驱动或真实机械臂/M1，也不把实机反馈实时映射到模型。手眼标定、标定板采购、附件称重和惯量仍后置。

本次入口交付时，三种预览场景已在准备环境用 MuJoCo 3.3.0 成功编译，记录见 [assembly_build_all.json](../reports/assembly_build_all.json)。实时入口的同一加载函数也已核对三场景的 `MjSpec` 标题、`home` 恢复和关节列表，以及 Piper/整机的双指位置关系、相机字段和碰撞组；全程只 `mj_forward`，物理时间保持 0。准备环境没有可用桌面，尚未完成用户 Linux 桌面上的开窗、按键和重载验证。离线渲染图即使生成，也只属于离线图像证据；用户本机的实时显示须按下面步骤实际执行并单独记录。

## 1. 先准备两个桌面终端

**终端 A** 保持 MuJoCo 窗口运行，接收键盘操作；**终端 B** 供 Codex 修改配置、生成模型、查看真实报错和提交代码。两者都在用户当前 Linux 图形桌面中打开，并进入同一仓库：

```bash
cd /home/kaiwen/research/dog-and-arm
git status --short
```

已有仓库无需再次克隆。先保留和识别本地修改，再正常拉取需要的上游更新；不要覆盖用户尚未提交的工作。

[project_env.sh](../scripts/project_env.sh) 的接口是 `bash scripts/project_env.sh COMMAND [ARGUMENTS...]`。它会进入项目根目录，把 `.venv/bin` 放到 PATH 首位，隔离 Conda/ROS 的 Python 和动态库路径，并原样保留显示、代理等必要变量。因此下文的 `python` 都通过该脚本调用，不需要先激活环境。

**仅在首次没有仿真 `.venv` 或确实缺少项目依赖时运行：**

```bash
bash scripts/setup_env.sh
```

已有环境只需确认正在使用的解释器和版本：

```bash
bash scripts/project_env.sh python -c "import sys, mujoco; print(sys.executable); print(mujoco.__version__)"
```

本入口要求 MuJoCo `3.3.0`。依赖问题按实际错误处理，不重装已有 ROS/CUDA、不写 Conda base、不改 shell 启动文件。环境脚本不是 ROS 启动器，后面的可选 RViz 应使用单独的 ROS 终端。

## 2. 获取官方资产

首次准备源模型时，在终端 B 执行：

```bash
bash scripts/project_env.sh python scripts/fetch_sources.py
bash scripts/project_env.sh python scripts/inspect_sources.py
```

来源版本由 `config/sources.lock.json` 指定。保留 `vendor/` 中已有修改，不修改官方源文件；转换、前缀和名义安装由项目生成器处理。之后调整安装参数通常只需重新构建，不必每次重新下载。

本流程使用 `scripts/build_assembly.py --stage m1|piper|combined|all`。该命令的阶段值、输出 XML 与实时查看入口如下：

| 阶段 | 构建参数 | 打开的场景 | 这一步主要观察 |
| --- | --- | --- | --- |
| M1 单体 | `--stage m1` | `sim/scenes/m1_preview.xml` | 四个轮子、腿部层级、初始姿态、关节正方向和地面相对高度 |
| Piper H 单体 | `--stage piper` | `sim/scenes/piper_preview.xml` | 六轴链、官方夹爪、双指对称开合、各关节方向 |
| 整机 | `--stage combined` | `sim/scenes/assembly_preview.xml` | 背部安装、腕部支架/相机固定关系、外形和碰撞几何 |

## 3. 逐个打开，完成一层就能看到一层

### M1 单体

终端 B：

```bash
bash scripts/project_env.sh python scripts/build_assembly.py --stage m1
```

构建成功后，终端 A：

```bash
bash scripts/project_env.sh python scripts/live_assembly.py --model sim/scenes/m1_preview.xml --watch
```

确认窗口标题含 `KINEMATIC_PREVIEW`，可看见完整轮足结构。按左右箭头选择关节、上下箭头小步调整，观察对应腿/轮的轴线与方向；按 F11 回到 `home`。此时 M1 的姿态来自预览位置，不代表已经会站立、行走或保持平衡。

M1 单体没有机械臂夹爪和腕相机时，程序会提示，Space/F8 不会凭空生成这些部件。检查完成后按 **F12** 退出当前窗口，再切换下一场景。

### Piper H 单体

终端 B：

```bash
bash scripts/project_env.sh python scripts/build_assembly.py --stage piper
```

终端 A：

```bash
bash scripts/project_env.sh python scripts/live_assembly.py --model sim/scenes/piper_preview.xml --watch
```

观察六轴连接是否完整、夹爪是否只有一套，选择若干机械臂关节做小步变化，再用 Space 开闭夹爪。两个真实夹指应同步反向运动；程序按 `q1=+w/2、q2=-w/2` 更新位置，不依赖 `mj_forward` 自动满足 mimic/equality。

单体是否包含腕相机由该场景实际内容决定。没有 `wrist_rgbd` 时保留自由视角并提示，不把缺少相机的单体报成相机显示成功。检查后 F12 关闭，再打开整机。

### 整机装配

终端 B：

```bash
bash scripts/project_env.sh python scripts/build_assembly.py --stage combined
```

终端 A：

```bash
bash scripts/project_env.sh python scripts/live_assembly.py --watch
```

默认场景就是 `sim/scenes/assembly_preview.xml`。依次看整机正面、侧面和腕部局部；检查安装座与背部是否相接、机械臂有无明显插进机身、相机/支架是否跟随固定末端主体而非活动夹指。开闭夹爪时，相机相对固定主体的位置应保持不变。

F8 切换 `wrist_rgbd` 与外部自由视角，查看腕相机朝向及夹爪遮挡；这只是虚拟相机画面，不等于取得真实 DC1 标定或深度测量。已有照片及 H0 视野可以用于外形对照，精确外参继续标为名义值。

需要一次重建全部模型时，可在终端 B 使用：

```bash
bash scripts/project_env.sh python scripts/build_assembly.py --stage all
```

`all` 不替代逐个打开查看。当前阶段完成依据仍按 [BUILD_PLAN.md](BUILD_PLAN.md) 和实际报告记录。

## 4. 键位与实际行为

先让 MuJoCo 窗口获得键盘焦点。选中的关节名称与每次位置变化在终端 A 输出。

| 按键 | 实际行为 |
| --- | --- |
| 左 / 右箭头 | 选择上一个 / 下一个标量关节；机械臂优先，然后是 M1；不选择自由基座和夹爪双指 |
| 下 / 上箭头 | 选中关节减小 / 增加；默认 hinge 每次 2°，slide 每次 2 mm；有有限位的关节会截到限位 |
| Space | 在夹爪有效开口两端切换，两个手指共同更新；属于运动学位置切换 |
| F6 | 概览 / 侧面 / 正面 / 腕部局部；只轮换当前模型已有的相机 |
| F8 | 腕相机 `wrist_rgbd` / 外部自由视角 |
| F9 | 外观 / 碰撞专用视图：显示 group 3 与 mesh 凸包，隐藏重合视觉组 1/2；不改变物理参数 |
| F10 | 请求重新编译当前 XML；成功后关闭旧窗、打开新窗，恢复新模型的 `home` |
| F11 | 恢复当前模型的 `home` |
| F12 | 退出程序并关闭窗口 |
| Esc | MuJoCo 原生自由视角 |

鼠标拖动/滚轮采用 MuJoCo 原生的旋转、平移和缩放。不要把鼠标施力/拖动、写自由基座轨迹或真实关节映射加入本轮预览流程。F9 是几何显示，不证明接触有效；本机曾发现碰撞与外观完全重合引发闪白，现通过隐藏视觉组并显示凸包解决。

需要更细的手动步长时：

```bash
bash scripts/project_env.sh python scripts/live_assembly.py --watch --step-deg 0.5 --step-m 0.001
```

只有明确希望自动播放运动学动画时，才使用：

```bash
bash scripts/project_env.sh python scripts/live_assembly.py --watch --scripted-demo
```

该选项以 16 秒为周期缓慢改变前两个 Piper hinge joint 和夹爪；机械臂偏移上限分别为 6°、3°，同时服从关节限位。它不带控制器、不施加真实或虚拟外力。手动调关节、开闭夹爪或恢复 home 会停止本次动画；要再次自动演示，关闭后明确带该选项重启。M1 单体没有 Piper 关节时，不会演示轮足行走。

## 5. 让配置修改真实出现在窗口里

终端 A 保持 `--watch`，终端 B 修改有依据的安装参数，例如 `config/assembly.yaml` 中的名义位姿，然后重新运行对应构建命令：

```bash
bash scripts/project_env.sh python scripts/build_assembly.py --stage combined
```

查看器监控场景及递归引用的 XML，等待文件变化稳定后尝试编译。**它不直接监控 YAML，也不重跑生成器；改配置后必须构建。** 只改 OBJ/STL 等网格而 XML 未变化时，用 F10 明确重载。

新模型编译成功后，终端显示“先关闭旧窗口，再打开新窗口并恢复 home”；旧窗口完全清理后才创建新窗口，因此重载时会有短暂的窗口关闭/重开。它不是同一窗口内的无缝热切换，也不会保留旧的关节编辑姿态。新模型编译失败则保留旧模型和旧窗口，终端及事件日志写明错误；仍看见旧画面不代表新修改已经生效。

Codex 每次有意义的修改应说明：改了哪个参数、为什么改、预计哪处几何会变化；重载后根据实际画面报告结果。无需为了展示 watch 而制造无用修改。默认一条查看会话只维持一个 viewer，切换场景先关闭旧会话，避免多个窗口混淆版本。

## 6. 证据与完成口径

实际事件自动追加到 `results/assembly/live_events.jsonl`，带会话号、UTC 时间和主机单调时间。日志包括 load/reload、按键、位置赋值、相机/碰撞组切换和窗口关闭；它记录程序行为，**不会自动证明用户亲眼看到了画面**。

阶段报告应分开写：

| 实际取得的证据 | 可以记录的结果 |
| --- | --- |
| XML 编译成功 | 模型可以被 MuJoCo 解析 |
| viewer 已创建并能正常操作、获得桌面画面证据 | 本机 GUI 已显示对应模型；注明所见场景和操作 |
| 用户明确反馈看到了具体变化 | 用户确认看到该次变化；保留反馈对应的阶段 |
| 开合、相机切换和少量 FK 对照 | 对应几何/运动学关系已检查 |
| 本入口的动画、按键或截图 | 不能作为动力学稳定、控制闭环或开门成功的证据 |

可按需保存当前桌面截图或短视频，说明是哪个模型和模式；不要把旧截图称作本次实时显示。没有用户确认时继续推进已授权的构建与检查，只不填写“用户已确认看到”。门的接触动力学和自由基座轮足控制仍属于 P4 以后。

## 7. 图形环境不可用时

没有 `DISPLAY`/`WAYLAND_DISPLAY` 时，脚本明确退出；显示变量存在但连接失败时也会报告 GLFW 错误。不要仅凭远程进程在运行就说用户已看到窗口，不随意把 `DISPLAY=:0` 写死，不改为 EGL/截图后把“实时桌面可视化”标成完成。

在这种情况下，继续完成不依赖 GUI 的模型转换、编译和文件修正，记录本轮尚未验证桌面显示，并给用户这一条在本机桌面终端执行的命令：

```bash
cd /home/kaiwen/research/dog-and-arm
bash scripts/project_env.sh python scripts/live_assembly.py --watch
```

如果当前是远程会话，先确认用户实际使用的桌面显示环境；不要为一个显示错误重装驱动、CUDA 或 ROS。没有 `home` keyframe、网格路径不正确等模型错误，应修复生成器后重建，不通过隐藏错误或删除几何来完成显示。

## 8. RViz 的位置

本轮实时修改反馈以 MuJoCo 桌面为主。RViz 可用于组合 URDF、TF 和关节方向的额外对照，当前仓库不提供已验证的 RViz 启动脚本或 MuJoCo↔ROS 同步桥。

确实需要 RViz 时，另开只加载已有 ROS 2 Humble 的终端，核实 `robot_state_publisher`、`joint_state_publisher_gui` 和 `rviz2` 是否可用；使用生成的组合 URDF，处理好 mesh URI，并让 Fixed Frame 与真实根 link 一致。不要经 `project_env.sh` 启动 ROS 节点，不复用真实机械臂命令话题。单独打开空 RViz 不算机器人已经显示；RViz 中手动变化也不会自动同步到 MuJoCo。

这部分未在用户桌面执行前保持“可选、未验证”，不阻塞当前 MuJoCo 可视化和 P0–P3 装配。

## 9. 在有意义的里程碑及时推送

建议在“M1 单体可用”“Piper/夹爪可用”“整机安装与腕相机检查完成”等自然节点提交，必要时先提交明确标为准备完成的代码，随后补上真实本机验证结果。每次提交前检查实际 diff，把模型、生成脚本、配置、必要小结果与进度说明放在一起；普通提交并推送到用户已授权的 `kaiwen123-yang/dog-and-arm`，不等整个开门任务结束才推送。

提交说明要区分“代码已准备”“编译通过”“桌面已验证”。推送后报告实际提交和推送状态；失败保留本地提交并说明原因。不要每一帧或每次按键自动提交，不提交 `.venv`、`vendor`、下载/编译目录、临时大数据或密钥，不强推，不另外制作压缩归档。

每个里程碑更新 `PROJECT_STATE.md`、`reports/assembly_report.md` 和 `prompts/NEXT_RUN.txt`，留下实际命令、所见变化、当前问题和下一步。交付完整模型时，仍需完成 [模型首轮](../prompts/FIRST_RUN.txt) 的 URDF/MJCF、映射和少量 FK 检查；能打开 viewer 只是其中一项。

本机执行更新（2026-11-16）：M1 已有桌面截图、18 s 屏幕录像与实际按键记录，详见 PROJECT_STATE.md 的本机节点；上文准备环境描述保留为历史来源。
