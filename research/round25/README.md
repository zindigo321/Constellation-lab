# R25：仅输入 N 的构型生成器

这是 `R25-balanced-1.1.0` 的七文件原字节快照。支持整数 `2 <= N <= 100`，只使用 Python 标准库；验收环境为 Windows / Python 3.11。覆盖与重访性能仍为 **UNVALIDATED**，程序不启动 STK。

在仓库根目录运行：

```powershell
python -B research/round25/program/generate.py 28 --out work/generated/N28
```

输出目录必须全新。输出为 `orbits.csv`、`config.json`、`COMPLETE.json`，后两者绑定轨道表及源码。退出0且完成回执绑定有效才表示参数输出成功；非法输入退出2，输出冲突或I/O错误退出3。重复运行请选择新目录。

卫星高度固定600 km，倾角按伴随配置中的一阶J2太阳同步关系计算；所有地球常数、UTCG和根数映射仍有明确的临时假设。不能将代数残差或合法输出视为原生传播和性能已验证。

自动面数取最近整数 `sqrt(2*N)`，限制于 `[2,N]`；各面数量最多相差1。RAAN均匀分布，面内均匀分布，跨面相位采用源码/策略文件记录的奇偶规则。等星数族称Walker-Delta，不等星数称custom-balanced-Delta；该策略没有证明性能最优或长期碰撞安全。

这是新的独立入口。仓库早期 `src.cli` 保留其原行为；请使用本目录入口进行通用N输出。源文件身份见 [SOURCE_MAP.json](../SOURCE_MAP.json)，阶段状态见 [说明](../../docs/r25-r28-status.md)。
