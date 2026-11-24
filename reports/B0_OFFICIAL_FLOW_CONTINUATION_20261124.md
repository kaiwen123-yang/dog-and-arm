# official_flow_s0_v1 同链续训

## 11 月 24 日 23:31 北京时间的恢复与诊断

目标为固定 SuperMimic 的 M1＋Piper 标准迁移。实际已保留 u1001。主段目标 u3000。发布此节点时仍处 B0-04，候选为空，合格双侧完整回报 NA。

| 账目 | Actor | WM | Critic | 有效策略转移 |
| --- | ---: | ---: | ---: | ---: |
| 直接 WM 祖先 | — | 14,850 | — | 见上轮谱系 |
| 父主链 u0–1000 | 1,000 | 10,000 | 20,000 | 10,255,490 |
| 本轮已保留至 u1001 | 1 | 10 | 20 | 11,047 |
| 四次中断后未保留 | 6 | 90 | 120 | 92,028 |

父包完整加载了三网络、六优化器、四组统计、replay、ReturnSampler、Ratio、RNG 和连续物理状态。实际首个新更新在 tick 2775，累计有效转移 10,266,537。u1001 另进程完整回读，136 个 solver 数组、162 个优化器张量、采样器/RNG 和全部 lane 对照通过。已完成但回滚的 102,400 个完整 lane 区间独立计费。失败的部分更新按实际优化器计数记账。[父包](../results/b0/standard_official_flow_continuation_20261124/parent.json) · [首个新更新](../results/b0/standard_official_flow_continuation_20261124/first_resumed_update.json) · [u1001 回读](../results/b0/standard_official_flow_continuation_20261124/restored_u001001.json)

### 冻结 WM 的权重与统计

相同历史前拉与背推双指开发窗的 H32 TCP 误差 P95 如下，单位 mm，分母为 386 和 446 个窗。

| WM 权重 | WM 统计 | 前拉 | 背推 |
| --- | --- | ---: | ---: |
| u0 | u0 | 20.72 | 14.49 |
| u0 | u1 | 246.76 | 287.79 |
| u1 | u0 | 52.84 | 59.40 |
| u1 | u1 | 498.58 | 815.74 |

原配对重现。在线统计从 50,479 增至 73,157 的影响取决于使用哪组权重。四格均保留原动作映射、context、FK 与积分器，新增优化步为零。首批的 2,048 个 H7 起点使用实际抽样索引，分别保存真实输入与自回归输入的逐通道 z 分位数、首层响应和配对误差。该首批所在的回放只有 19 tick，表中 H32 来自历史长开发窗。[四格和逐层数据](../results/b0/standard_official_flow_continuation_20261124/wm_factorial/factorial.json)

u1000 另用预先写入开发程序的种子 821001 运行 256×64 个区间。其中 7,851 为前缀，8,533 为有效策略区间，含 558 个完整 terminal。合法 H32 前拉 1,126 窗、背推 880 窗，TCP P95 分别为 14.85、64.36 mm。实际持续双指的有效区间为零，该分层记 NA。该块独立采集，未回灌训练。[开发块](../results/b0/standard_official_flow_continuation_20261124/current_policy/u001000/scores.json)

### u1000 物理分歧

四个原 2 ms 同包重测均复现原失败阶段与步数。两侧在第 206 个 20 ms 参考帧首次出现至少一个采集噪声标准差的原始命令差，均是第 12 号轮通道。当时前拉 Warp/native 轮速目标为 0.50245/0.45149 rad/s，实测为 0.49805/0.48826 rad/s。重放保存的相同历史，Actor 命令与原记录最大差为浮点量级。前拉 native 在原裁判首失败时 XY 18.80315 mm，航向 2.00118973°；背推 native 为 20.00872 mm 和 0.672856°。前者航向、后者 XY 越过原工位约束。两侧正式 Warp 位于不同失败状态。

完整训练时钟诊断保持 80 微步/20 ms、8 微步/2 ms、已登记 bias 刷新和原事件秒数。前拉在 11.7355 s 驻车超时，背推在 11.24625 s 发生非抓握部位夹指接触。两案独立于正式计数。另用四案定位溢出告警，前拉转背推时，原评测器在构造 Warp 世界的 `put_data` 过程中把 `efm_fluid` 从 float64 转成 float32；字段追踪捕获长度 241 的数组中索引 65 超出 float32 范围。本场景两模型风、密度、黏度均为零，安装版本中的流体导数读路径受 `has_fluid` 控制。历史日志只保留了转换行号。[对齐与求解量](../results/b0/standard_official_flow_continuation_20261124/backend/comparison.json) · [字段与调用栈](../results/b0/standard_official_flow_continuation_20261124/backend/warnings_warning_fields.jsonl)

续训在独立 AutoDL 目录运行。共享显存时保留了原 dtype 的回放历史和 autograd 暂存试验回执；官方 CUDA Graph 捕获仍遇到内存分配失败。后续从已核对的 u1001 恢复，使用原 GPU 常驻缓冲和官方图。正式节点锁定后顺序启动 Warp/native 完整任务、接触、free 及纯 Actor 验证。跟踪窗登记发生在首次 u1001 后、任何 u1500 及以后物理结果产生前；全部分母只由 u500/u1000 的原始帧交集确定。[固定窗](../results/b0/standard_official_flow_continuation_20261124/tracking_windows.json)
