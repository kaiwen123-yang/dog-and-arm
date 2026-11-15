# 开工包准备验证

日期：2026-11-15。验证环境是本次准备工作使用的独立 Linux Python 3.12.14 虚拟环境，MuJoCo **3.3.0**；不是用户 Linux 主机。

## 实际完成的检查

1. 阅读固定版本的 M1 ZGWS MJCF、Piper H/夹爪描述及 MuJoCo 3.3.0 相关解析代码；模型入口、转换规则和已知限制写入 docs/。
2. 检查来源脚本的配置、资源解析、版本记录及已有 checkout 保留行为；盘点器对读取到的源 XML/Xacro 进行过解析检查。本次没有在此开工目录下载完整 vendor 网格。
3. 运行 scripts/init_workspace.py，确认目录初始化成功并保留现有文件。
4. 检查 Python 脚本语法和两个 shell 脚本语法；通过 scripts/project_env.sh 调用验证用 Python/MuJoCo，确认没有继承 PYTHONPATH、PYTHONHOME、CONDA_PREFIX、LD_LIBRARY_PATH。
5. 实际运行 scripts/build_doors.py，生成单扇和双扇组件与场景。
6. 用 MuJoCo 3.3.0 实际编译这两个场景，检查门在 0°、30°、60°、90°、110° 静态姿态下的碰撞；这些采样没有门/框/地面初始穿透接触。
7. 两个场景分别从静止执行 1,000 次 mj_step，步长 0.002 s、共 2 s 仿真时间，状态有限且门保持静止。
8. 用 EGL 实际调用 view_model.py 的静态截图模式，生成并查看 `results/doors/double_closed.png`，确认双扇门、门框与两侧固定把手几何可见。

上述静态角度采样直接设置 qpos，仅用于几何检查，不作为开门任务成绩。2 s 步进没有机器人、施力或控制器，也不证明推拉成功。

## 场景结果

| 场景 | nq / nv | nu / neq | 名义门扇总质量 | 静止步进终点 |
| --- | --- | --- | --- | --- |
| 单门 | 1 / 1 | 0 / 0 | 12 kg | 门角 0、角速度 0 |
| 双门 | 2 / 2 | 0 / 0 | 24 kg | 两门角 0、角速度 0 |

可读的检查数据位于 `reports/door_preparation_check.json`。

编译时发现并修正了一项实际问题：门框若是只有零质量 geoms 的空 body，会触发自动质心计算错误。现在门框静态 geoms 直接放入 worldbody，门扇保留显式惯性。这一经验也已写入附件建模规则，避免将“暂不计附件载荷”变成虚构质量来绕过报错。

## 本次未验证或未完成

- 用户 Ubuntu 上的依赖安装、桌面查看器与 GPU 渲染。
- 在本开工目录完整执行官方模型下载、全部 DAE 转换和所有网格编译。
- M1＋Piper H＋附件的组合 URDF/MJCF、FK 对照及腕部 RGB-D。
- 固定基座接触控制、自由基座运控或机器人推拉门。
- 手眼标定、真实相机驱动、附件实测质量与惯量。

下一步按 prompts/FIRST_RUN.txt 执行 P0–P3。没有把以上未完成项写成已成功复现。
