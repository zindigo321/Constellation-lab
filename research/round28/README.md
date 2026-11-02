# R28：离线批次与统计核心

这里公开 `r28_v01` 中三个标准库模块的原字节快照：

- `src/incremental_store.py`：不可变批次事件/状态块，以原子完成回执为提交点，支持恢复、幂等与冲突拒绝。
- `src/stats_production.py`：分组后排序并集及逐点间隔统计。
- `src/stats_independent.py`：独立端点扫描实现及统计CLI。

这三个文件是十文件原生运行集合的离线子集。完整STK采集器、监督器、实际任务/点表/事件、系统资源和本机工程不在本次发布内；本目录不提供整套原生实验复现。聚合结果见 [阶段说明](../../docs/r25-r28-status.md)。

## 独立合成检查

在仓库根目录运行，输出目录均须全新：

```powershell
python -B research/round28/checks/store_counterexamples.py work/r28-store-checks
python -B research/round28/checks/synthetic_smoke.py --out work/r28-synthetic-checks
```

第一项为原R28的32项Store反例，第二项为本次发布新增的14项合成API/CLI/恢复检查。全部数据标为 `FIXTURE_ONLY`，只用标准库，无需STK或第三方包。合成检查不替代真实原生证据。

## 使用边界

Store为单写者设计；批大小在创建时冻结，尾批需要 `flush()` 或 `close()` 提交。未发布回执的尾部不是完成，恢复时不重复计入已提交查询。普通本地文件系统的同目录原子替换及fsync语义不等于任意硬件断电保证。

统计调用应显式传 `duration_s`、`window_start_s`、`merge_tolerance_s` 和 `required_sat_ids`。部分卫星失败/未算时保留已得事件，主统计保持不完整；原始访问信息不因分组而丢失。两种并集实现保持分离。

批量布局减少文件数，仍有查询计划与snapshot物化成本。R28中D的Store从6242降为101文件，**不是整体运行速度提升61.8倍**；完整N28准入仍关闭。原源码身份和父运行集合SHA见 [SOURCE_MAP.json](../SOURCE_MAP.json)。
