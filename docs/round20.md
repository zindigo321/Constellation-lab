# 第二十轮条件离线研究

入口 `tools/run_round20.py`，独立配置 `configs/round20.json` 和 profile `ROUND20_V1`。
只处理固定 S 与三个 R19 不可行锚点 q1=(911,214)、q2=(676,1440)、q3=(911,2126) 的第二换族并集。
主枚举按删除无序对、加入无序对数字字典序；独立枚举逐族生成集合再求并集。
声明 173473 个唯一组合，三个原族各 57834，交集 1/27/1，无三重交；归属 q1/q2/q3 为 57834/57833/57806。

必要门顺序 T100 单点负证书、T90 精确计数负证书、全部剩余组合完整精算。没有 GAP 层。
双删缓存使用真实保留26星；共同覆盖的点可在双删后缺失。缓存绑定源数据、S、完整删除对、阈值与容差；证书再绑定加入对和归属。
T100 checker 从28个原源值核验，T90 checker 从原数组 Boolean OR/count 重建，主路径使用 bitset/popcount。
主完整计算使用 stack/min、partition 和逐段合并；独立完整核验使用 pairwise where、排序和累计前沿聚类。
共享边界仅为已校验的解码/schema、坐标、mask、状态身份格式和原R14独立数值原语。
原域43424首访逐点核验，内部gap使用实际数量作分母；可行门相对B0，保守至少1秒改善相对S。
数值比对 atol=1e-6、rtol=0；集合、identity、整数、布尔类型和值精确；排序不使用近似等价。

原292消费文件和六检查点只读。全部新增消费文件在候选处理前冻结为JSON/ZIP，同一contract副本绑定每个attempt。
原540历史测试按168/185/203/223/245/268/292原字节子集实际重跑，26绑定反例单列。
仅R19指定只读测试可临时指回原ROOT，使用try/finally恢复，所有夹具仍在新work。
安全保护覆盖所有角色的socket.*、原生导入、vendor执行、越界写与精确子进程白名单；仅为Python审计范围。
Windows Job Object监督正常与超时进程树；所有实际退出由外层观察，直接子进程无Shell时为null。

单一effective_start_epoch包含读取、准备、失败、执行和导出。科学/回归6600秒截止，总墙钟7200秒。
未终止JSONL末行只可作中断前缀诊断，不计PASS；中间损坏、重复、遗漏或错绑失败。
FAIL优先于BLOCKED；失败attempt、源码和完整日志永久保留，新版本需重新冻结并重跑受影响全部正式任务。
三层sealed/transport/delivery manifest精确集合及单向receipt；封存内容不回写；外层结束后的最终全量读回另存observation。

active_protocol_change_authorized=false；official_readiness=UNRESOLVED；official_score=null；next_scientific_run_gate=BLOCKED_PENDING_RULE_CONFIRMATION。
source=archived_component_composition；new_native_validation_performed=false；whole_constellation_STK_verified=false。
混合保存高度500–700km、0.81度半角、直接AreaTarget与暂定mask仍为条件口径；EOP止2019而场景2027。
原生激活与Git写预算均0。无进一步合格改善时原样保留S的5199字节CSV。结论不外推完整catalog双换或全局最优。

## 验证清单

- 三族交集、完整集合/身份/顺序/归属、禁止错误耦合删除条件与donor条件。
- 双删共同覆盖点、修复旧缺点后新增缺点、28原值篡改、迟访/未访区别。
- T90等于截止计入、38762/38763边界、padding为零、缓存/归属/阈值错绑。
- B0可行门与S改善门分离、实际gap分母、数值容差与身份/布尔严格、精确排序。
- 历史七组ID/字节/退出、指定ROOT适配正常及异常恢复、非白名单不适配、原件/副本篡改。
- 各角色完整socket事件和写/子进程边界、真实进程树正常及超时回收。
- 源码/合同/attempt/导出绑定、FAIL优先、统一时钟、末行中断与中间损坏。
- 正式完整科学计算、全部独立核验、三层文件集合/摘要/原work映射、实际退出后的最后读回。

此命令行研究不含Web/API/浏览器界面；测试技能的相关阶段裁剪为CLI、文件协议与受监督进程流。
