# 第22轮条件离线研究

本轮完整重新处理三个既有R19单换锚点的第二换并集173499个28星组合。q1=(1412,1118)、q2=(2021,1123)、q3=(1941,1200)，均为INFEASIBLE_ANCHOR_DIAGNOSTIC_ONLY，不能作为参考或保留结果。

固定S、D=catalog\S；每候选恰从S删2加2。按无序删除对、再加入对数字字典序，要求存在同一锚的首删和首加同时出现。78个删除对；每族57834，两两交1且无三重交；首属q1/q2/q3为57834/57833/57832。全部重新处理，不排除历史99个identity；candidate_REUSED=0。

执行顺序T100→T90→FULL。完整双删保留26行重新构造，不以单删独占点并集替代。负证书直接绑定原28值或Boolean OR/count；FULL用不同最小值、次序统计、区间合并和门算法逐项核验。可共享已验证输入schema、坐标/mask和状态identity格式。B0定义可行门；S定义保守1秒进一步改善门和fallback。全部通过必要门者完整评价，不取前N。

保留原346消费文件字节及六checkpoint；所有新消费源码、配置、测试、文档、入口及引导适配封存。每正式job独立attempt，源码JSON/ZIP、同一contract、日志、实际argv/cwd/退出/timeout及精确输出集绑定。历史九组652测试、26绑定及新增测试在本轮实际重跑；仅原两个精确ROOT用例允许只读引用原项目，try/finally恢复；其余执行副本隔离。

单一7200秒墙钟包含全部准备，6600秒停止科学/回归、600秒收尾；父子重叠不相加。初始精确epoch未在首工具记录，lifecycle明确采用保守更早UTC界，不伪称精确测量。FAIL不被后续超时降级。

纯Python审计防护覆盖所有socket.*、原生导入、vendor执行、越界写与非白名单子进程，不声称操作系统隔离。研究、导出、finalizer与观察器分别记录实际退出。三层sealed/transport/delivery精确集合、大小/SHA及原work映射完整读回；最终退出后观察单向绑定manifest/receipt，不改旧回执。

第二次尝试遇到宿主分页资源不足，Shapely DLL加载失败；原单测诊断随后通过，原FAIL完整保留。后续新启动进程统一将OPENBLAS_NUM_THREADS、OMP_NUM_THREADS、MKL_NUM_THREADS、NUMEXPR_NUM_THREADS设为1并绑定实际环境，以降低数值库线程内存开销。此设置不修改系统分页文件、依赖版本、原测试断言或科学门。

入口：D:/conda_envs/fmb/python.exe -X utf8 -B tools/run_round22.py --work <新work>。导出入口tools/export_round22.py；外层shell/observe记录实际退出。仅在全部验收通过时PASS/0；缺证或截止BLOCKED/2；数值/测试/版本/越权/封存错误FAIL/1。

active_protocol_change_authorized=false，official_readiness=UNRESOLVED，official_score=null，next_scientific_run_gate=BLOCKED_PENDING_RULE_CONFIRMATION。source=archived_component_composition；new_native_validation_performed=false；whole_constellation_STK_verified=false。混合保存高度、0.81度半角、直接AreaTarget与暂定mask仍有条件；EOP止2019而场景2027。原域缺点不证明物理不可达或连续几何完备性；历史状态不改写。原生激活和Git写均0。完成后停止，不开启R23。
