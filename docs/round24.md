# 第24轮：修复绝对截止监督并重试原R23空间

本轮仅执行保存组件的条件离线研究。固定B0为可行门参考、固定S为至少再改善1秒的参考与无改善回退；三个既有R22不可行锚点p1/p2/p3仅定义邻域。新增全部最终候选相对S删3加3，不把不可行锚点更新成参考。

完整空间为三族各26×2141，按删除三元组、加入三元组的数字字典序去重。必须存在同一锚的删除对和加入对都包含于操作中；并集166970，交集1/1/26，无三重交。首属p1/p2/p3分别55666/55665/55639；51种删除类型独立核验为25×2141+25×4281+6420。所有候选均重新处理并逐项独立核验，不设历史排除名单。

固定分区优先级T100→T90→FULL。T100证书保存原mask点及最终28行实际source值；T90由独立原28行Boolean OR/count重建。两类证书都声明known_infeasible=true、full_feasibility_evaluation_performed=false，未算指标null；通过两门者全部完整精算。Tavg使用真实内部gap总和除真实数量。浮点核验atol=1e-6、rtol=0，整数/身份/集合/bool精确。首尾与含边界结果实测单列。

原400源和六checkpoint保全，全部R24消费者及精确工作目录/命令/环境/空间/门/排序冻结后才枚举科学候选。实际重跑788历史测试、26绑定及本轮新增测试；仅原R19/R20两项ROOT白名单，用try/finally恢复。历史副本逐文件核验；R21/R22/R23保全测试读取真实旧冻结源，不扩白名单。科学JSON和JSONL保持原严格编码规则。

Python审计防护覆盖协调器、worker、回归、导出launcher/child、finalizer与observer，拒绝全部socket.*、原生接口/vendor执行、越界写和未登记子进程。终端角色无子进程权限；Windows Job Object只清理本次自建后代。保护不等于OS隔离。

总墙钟7200秒，6600秒停止科学/回归，末600秒专用于收尾。初始附件读取早于精确配对采样，因此保留更早的保守起点和采样限制；不冒称严格满足先采样后读取。QPC初始值与Python perf_counter同源；当前解释器monotonic使用另一个原点的GetTickCount64，不能混用。准备、失败、等待、导出、实际退出和最终读回均计入，不重设预算或相加父子重叠耗时。非零工程FAIL不因后来超时变BLOCKED。

监督每次读取UTC和QPC，以二者累计较大值和已观测最大值计时；UTC倒退不续期，前跳或单调异常保守停止。等待最长1秒，等待前后和真实退出后均复核。最外层总截止监督覆盖准备、协调、封存、导出、finalizer和observer；内部科学/回归子树受compute截止监督。超时实际退出、强制终止、wall/overrun分列，迟到0不能通过。受控等待/时钟测试不声称复现宿主休眠，不修改电源策略。

最终复核为运行中QPC异常前跳增加明确拒绝：UTC仍前进但QPC增量超过UTC增量容差时立即停止，不仅扣减剩余预算。初版完整科学与交付证据保留，新增受控反例曾实际失败；修正后在原始UTC/QPC预算内另建短路径，四作业全量重新冻结、重跑，不复用初版候选结果。same_budget_lineage.json绑定旧封存、失败测试及源码快照，两个lifecycle.json的原始字节一致。缓存路径检查同时覆盖命名根的全部上层目录重解析点。

新resolver只读命中R22 materialized或K13 vendor，每个成员当前完整哈希后才使用；缺失才向新work安全提取。保留2171资产完整state/NPZ每点/矩阵/区间/坐标检查和结束preserve，增加每资产和每阶段进度，父级独立采样心跳。未完成输入的前缀不重载全部科学输入，仅按已落盘核验记录收尾，qualified/selected为null。已超过total时只留外置晚到取证。

运行入口为`D:/conda_envs/fmb/python.exe -X utf8 -B tools/run_round24.py --work <新work>`；导出入口`tools/export_round24.py`。使用`src.round24.shell`生成research/export/finalizer脚本，外层显式`exit $global:LASTEXITCODE`；每步真实Shell退出由`src.round24.observe`记录。finalizer退出后另运行`--kind final-readback`，全量核三层精确集合/字节/原work映射、源码/合同/全空间/真实退出；观察只写原work，单向绑定receipt，不造哈希循环。目的目录须早期验证权限且导出前不存在。

R22原科学PASS/0、原整体BLOCKED/2与过期时钟均不改写；用户授权的新R22重跑整体PASS/0及退出后读回作为独立前置输入。无合格改善时原样复制R18 CSV原字节并保留SHA，操作与本轮元数据另存。

保持active_protocol_change_authorized=false、official_readiness=UNRESOLVED、official_score=null、next_scientific_run_gate=BLOCKED_PENDING_RULE_CONFIRMATION。source=archived_component_composition，无新原生/整星座STK验证；500–700km混合保存高度、0.81度半角、直接AreaTarget和暂定mask正式可采纳性未确认；EOP止2019、场景2027。K12仍BLOCKED/2、0单元、成本NOT_RUN；原生激活0、Git写0。结论只覆盖本轮声明的限定三换并集，不声称完整catalog三换或全局最优。原R23未处理，空间与本轮相同，原BLOCKED/2证据不改写。完成后停止，不开启R25。
