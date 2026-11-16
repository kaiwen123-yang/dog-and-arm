# 本轮源码快照

- `h0_operator_motion_attempt1.py`：第一次关节未运动时的动作入口。
- `h0_operator_motion_retry.py`：第二次实际成功动作的入口；`h0_operator_motion.py` 是当次结束后的同版本副本。
- 其余文件是本轮结束时的采集/启动源码快照，并非声称每次早期诊断均用了最终 QoS/DDS 配置；具体采用配置见对应运行的 summary、启动日志和 H0 报告。最终相机记录器新增的 DDS 环境元数据字段未用于此前已开始的采集，实际进程环境另见 `../logs/final_process_environment.json`。

整理报告时，项目 `scripts/h0_operator_motion.py` 修正了一处纯日志标记：夹爪发送前设置其 phase。未改变发送序列或再次运行硬件动作。保留的第二次 `motion_sdk_tx.csv` 在夹爪阶段仍沿用前一保持段 phase；用事件、命令类型、CAN ID 和原始时间关联，不能仅依赖这个旧 phase 标签。

离线统计器后来将通用时间字段从 `first/last_monotonic_ns` 改成 `first/last_timestamp_ns` 并增加 clock 标签，避免把 ROS header 误标成单调时间。交付的 timing_summary 由相同原始数据重算；历史控制台日志保留原输出，测量数值不变。
