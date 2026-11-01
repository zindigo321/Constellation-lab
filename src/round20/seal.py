"""Immutable R20 scientific closure with exact file manifests and one-way receipt."""
import hashlib
import json
from pathlib import Path
import shutil
import time
import zipfile
from src.round13.archive import safe_name, safe_inventory
from src.round13.common import read, write, require, sha, fingerprint
from .binding import verify_sources, verify_attempt, artifacts
from .control import Lifecycle

PROFILE = 'ROUND20_V1'
DECLARED = 173473
FLAGS = dict(active_protocol_change_authorized=False, official_readiness='UNRESOLVED', official_score=None,
    next_scientific_run_gate='BLOCKED_PENDING_RULE_CONFIRMATION', native_activation_count=0,
    git_write_operations=0, new_native_validation_performed=False,
    whole_constellation_STK_verified=False, source='archived_component_composition')
COUNT_KEYS = ['declared_candidates', 'fully_evaluated', 'fully_independently_verified',
    'T100_certificate_rejected', 'T100_certificate_verified', 'T90_certificate_rejected',
    'T90_certificate_verified', 'unprocessed', 'unknown', 'qualified_count', 'qualified_for_round20', 'retained_R18_R19_incumbent', 'candidate_REUSED']


def durable_records(path):
    """An interrupted final line is the only recoverable JSONL damage."""
    path = Path(path)
    if not path.exists():
        return
    with path.open(encoding='utf8') as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                if line.endswith('\n') or stream.read(1):
                    raise


def prefix_counts(science):
    science = Path(science)
    seen, checked, qualified = {}, {}, set()
    ledger_ids = set()
    for ordinal, row in enumerate(durable_records(science/'ledger.jsonl')):
        require(row['identity'] not in ledger_ids, 'PREFIX_DUPLICATE_LEDGER_IDENTITY')
        require(row.get('ordinal') == ordinal, 'PREFIX_LEDGER_NOT_CONTIGUOUS')
        ledger_ids.add(row['identity'])
    for name, kind in [('candidates', 'FULL'), ('t100_certificates', 'T100'), ('t90_certificates', 'T90')]:
        for row in durable_records(science/(name+'.jsonl')):
            identity = row['identity']
            require(identity not in seen, 'PREFIX_DUPLICATE_PROCESSED_IDENTITY')
            seen[identity] = kind
            if row.get('qualified_for_round20'):
                qualified.add(identity)
    for name, kind in [('checker', 'FULL'), ('t100_certificate_checker', 'T100'), ('t90_certificate_checker', 'T90')]:
        for row in durable_records(science/(name+'.jsonl')):
            identity = row['identity']
            require(identity not in checked, 'PREFIX_DUPLICATE_CHECKED_IDENTITY')
            if row.get('status') == 'PASS' and not row.get('differences'):
                checked[identity] = kind
    require(len(seen) <= DECLARED, 'PREFIX_EXCESS_RECORDS')
    verified = {i for i in seen if checked.get(i) == seen[i] and i in ledger_ids}
    return dict(declared_candidates=DECLARED,
        fully_evaluated=sum(k == 'FULL' for k in seen.values()),
        fully_independently_verified=sum(seen[i] == 'FULL' for i in verified),
        T100_certificate_rejected=sum(k == 'T100' for k in seen.values()),
        T100_certificate_verified=sum(seen[i] == 'T100' for i in verified),
        T90_certificate_rejected=sum(k == 'T90' for k in seen.values()),
        T90_certificate_verified=sum(seen[i] == 'T90' for i in verified),
        unprocessed=DECLARED-len(seen), unknown=len(seen)-len(verified),
        qualified_count=len(qualified & verified), qualified_for_round20=len(qualified & verified), retained_R18_R19_incumbent=True, candidate_REUSED=0)


def terminal(folder, check=lambda: None, prefix=False):
    from .checker import terminal_verification
    meta=read(folder/'frozen/contract.json')['metadata']
    result=terminal_verification(meta,folder/'science',check,prefix)
    result['qualified_count']=result['qualified_for_round20']
    return result


def report_text(final, folder):
    lines=['# 第二十轮：三个固定 R19 锚点的完整第二换修复并集', '',
        f"状态 {final['status']}；研究 Python 退出码 {final['exit_code']}。",
        f"结论：{final['optimization_outcome']}。", '',
        '| 分区 | 本轮处理 | 逐项独立核验 |','|---|---:|---:|',
        f"| T100 | {final['T100_certificate_rejected']} | {final['T100_certificate_verified']} |",
        f"| T90 | {final['T90_certificate_rejected']} | {final['T90_certificate_verified']} |",
        f"| FULL | {final['fully_evaluated']} | {final['fully_independently_verified']} |", '',
        f"声明173473；未处理{final['unprocessed']}；unknown {final['unknown']}；合格改善{final['qualified_for_round20']}；candidate_REUSED=0。",
        f"保留R18/R19中心S：{final['retained_R18_R19_incumbent']}。B0、S与三个不可行锚点重放另计。", '',
        '中心与改善参考固定S，可行门相对B0。三个第二换族的精确去重并集173473，按规范删除对/加入对遍历；排名为Tmax/Tavg/T100/T90/identity。',
        'T100→T90→FULL，无GAP证书层。负证书known_infeasible=true、full_feasibility_evaluation_performed=false；其它未计算指标保持null。通过两必要门者全部精算。']
    science=folder/'science'
    if all((science/(n+'.json')).exists() for n in ['baseline','center','selected']):
        reports=[read(science/(n+'.json')) for n in ['baseline','center','selected']]
        lines+=['','| 指标秒 | B0 | 固定S | 最终选择 |','|---|---:|---:|---:|']
        getters=[('mask T90',lambda r:r['effective_grid']['T90_s']),('mask T100',lambda r:r['effective_grid']['T100_s']),
            ('内部Tavg',lambda r:r['regional']['pooled_internal']['mean_s']),('内部Tmax',lambda r:r['regional']['pooled_internal']['max_s']),
            ('内部gap分母',lambda r:r['regional']['pooled_internal']['gap_count']),('原域T90',lambda r:r['full_grid']['T90_s']),
            ('原域T100',lambda r:r['full_grid']['T100_s']),('含边界Tmax',lambda r:r['regional']['pooled_boundary_inclusive']['max_s'])]
        for name,get in getters:lines.append('| '+name+' | '+' | '.join(str(get(r)) for r in reports)+' |')
        chosen=reports[-1]
        lines+=['',f"mask覆盖{chosen['effective_grid']['covered']}/{chosen['effective_grid']['points']}，原域覆盖{chosen['full_grid']['covered']}/{chosen['full_grid']['points']}。",
            f"最终identity `{chosen['identity']}`。",'','| 对象 | B0首尾秒 | S首尾秒 | 最终首尾秒 |','|---|---|---|---|']
        for target in chosen['regional']['targets']:
            vals=[[b-a for a,b in r['regional']['targets'][target]['boundary_segments']] for r in reports]
            lines.append('| '+target+' | '+' | '.join(str(v) for v in vals)+' |')
        lines+=['','全部原始/合并区间、内部gap与首尾端点保存在对应报告；metric_comparison.json列明相对B0与S变化。',
            '无进一步合格改善时原样复制R18轨道CSV并校验原SHA；操作、差集、各星高度与研究元数据另存selection_protocol.json。']
    lines+=['', '540项历史回归与26项历史绑定使用版本一致隔离子集，R20新增测试单列。原292消费文件和6个检查点原字节保全。',
        'Python审计保护在协调器、各worker、导出启动器/子进程及finalizer拒绝所有socket.*事件、原生导入、vendor执行、越界写与非白名单子进程；这是Python审计范围，不是操作系统级隔离。',
        '条件范围：保存高度500–700km的组件组合；半角0.81°、直接AreaTarget、暂定mask与混合高度正式可采纳性未确认；EOP止2019而场景2027。',
        'active_protocol_change_authorized=false；official_readiness=UNRESOLVED；official_score=null；next_scientific_run_gate=BLOCKED_PENDING_RULE_CONFIRMATION。',
        'source=archived_component_composition；new_native_validation_performed=false；whole_constellation_STK_verified=false；原生激活与Git写操作均0。',
        '原域缺点按本轮实测列示，不推断物理不可达。保存组件不证明连续几何完备性。本结论仅覆盖声明的三锚第二换并集，不推及其它中心、完整双换或全局最优。',
        'K12保持BLOCKED/2、0单元、成本NOT_RUN；R14–R19历史结果不改写。',
        '历史失败/预检完整日志保留原work，historical_attempts_index.json明确区分完整导出日志与原work摘要索引。', '',
        f"封存边界累计墙钟{final['lifecycle_elapsed_at_seal_s']:.3f}秒。研究/外层Shell/导出进程/启动器退出与计时在transport及completion单向绑定。",
        'receipt创建与随后最终读回是不同计时边界；最终读回观察记录位于原work/final_readback_observation.json，单向绑定最终manifest/receipt，不回写已封存对象。']
    return '\n'.join(lines)+'\n'


def independent_readback(folder, check=lambda: None):
    folder = Path(folder).resolve()
    receipt, manifest = read(folder/'receipt.json'), read(folder/'artifact_manifest.json')
    require(receipt['profile'] == manifest['profile'] == PROFILE and
            receipt['manifest_sha256'] == sha(folder/'artifact_manifest.json', check), 'SEAL_RECEIPT_BINDING')
    names = set()
    for row in manifest['files']:
        check()
        name = safe_name(row['path'])
        lexical, path = folder/name, (folder/name).resolve()
        require(name.casefold() not in names and path.is_relative_to(folder) and not lexical.is_symlink(), 'SEAL_MEMBER_SCOPE')
        require(all(not p.is_symlink() for p in lexical.parents if p.is_relative_to(folder)), 'SEAL_PARENT_LINK')
        names.add(name.casefold())
        require(path.is_file() and path.stat().st_size == row['bytes'] and sha(path, check) == row['sha256'], 'SEAL_MEMBER_BYTES')
    require({p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()} ==
            {r['path'] for r in manifest['files']} | {'artifact_manifest.json', 'receipt.json'}, 'SEAL_EXACT_SET')
    final = read(folder/'final_status.json')
    require(final['status'] == receipt['status'] and final['exit_code'] == receipt['exit_code'] ==
            {'PASS': 0, 'FAIL': 1, 'BLOCKED': 2}[final['status']], 'SEAL_STATUS_EXIT')
    require(all(final.get(k) == v for k, v in FLAGS.items()), 'SEAL_SCOPE_FLAGS')
    require(final['declared_candidates'] == DECLARED, 'SEAL_DECLARED')
    if final['status'] == 'PASS':
        completed = terminal(folder, check)
        require(completed['status'] == 'PASS' and all(completed[k] == final[k] for k in COUNT_KEYS), 'SEAL_EXACT_SPACE')
        require(final['unprocessed'] == final['unknown'] == 0, 'SEAL_INCOMPLETE')
        rows = read(folder/'frozen/consumer_code.json')
        require(fingerprint(rows) == read(folder/'frozen/contract.json')['source_manifest_identity'], 'SEAL_SOURCE_IDENTITY')
        with zipfile.ZipFile(folder/'frozen/consumer_code.zip') as snapshot:
            safe_inventory(snapshot.infolist())
            require(set(snapshot.namelist()) == {r['relative_path'] for r in rows}, 'SEAL_SOURCE_SET')
            for row in rows:
                blob = snapshot.read(row['relative_path'])
                require(len(blob) == row['bytes'] and hashlib.sha256(blob).hexdigest() == row['sha256'], 'SEAL_SOURCE_ZIP')
        bindings = read(folder/'consumer_version_binding.json')['selected']
        require(set(bindings) == {'science', 'tests', 'legacy', 'guards'}, 'SEAL_JOB_SET')
        for job, binding in bindings.items():
            history = folder/'attempt_history'/binding['attempt_id']
            command = read(history/'command_result.json')
            result = read(folder/job/'job_result.json')
            require(read(history/'consumer_code.json') == command['code_manifest'] == rows, 'SEAL_ATTEMPT_SOURCE')
            require(result == read(history/'supervised_result.json') and result['status'] == 'PASS' and result['exit_code'] == 0
                and result['job'] == job and result['attempt_id'] == history.name and result['consumer_identity'] == fingerprint(rows), 'SEAL_WORKER_BINDING')
            from .binding import ROOT
            require(command['command'] == binding['command'] and command['python_exit_code'] == 0 and not command['timeout']
                and Path(command['cwd']).resolve() == ROOT and result['argv'] == command['command']
                and Path(result['cwd']).resolve() == ROOT, 'SEAL_COMMAND_BINDING')
            contract_digest=sha(folder/'frozen/contract.json',check)
            require(sha(history/'consumer_contract.json',check)==contract_digest==binding['contract_sha256']
                ==command['contract_sha256']==result['contract_sha256'],'SEAL_ATTEMPT_CONTRACT_BINDING')
            require(artifacts(folder/job, check) == command['output_artifacts'] and
                fingerprint(command['output_artifacts']) == binding['output_artifacts_identity'] and
                sha(history/'consumer_code.zip', check) == binding['code_snapshot_sha256'], 'SEAL_OUTPUT_BINDING')
            require(read(folder/job/'guard_audit.json')['status'] == 'PASS' and
                    read(folder/job/'guard_audit.json')['unexpected_denials'] == 0, 'SEAL_WORKER_GUARD_AUDIT')
        tests, legacy = read(folder/'tests/job_result.json'), read(folder/'legacy/job_result.json')
        require(tests['tests'] > 0 and tests['failures'] == tests['errors'] == tests['skipped'] == 0, 'SEAL_TESTS')
        require(legacy['regression_tests'] == 202 and legacy['round14_tests'] == 89 and
            legacy['round15_tests'] == 66 and legacy['round16_tests'] == 30 and legacy['round17_tests'] == 31 and legacy['round18_tests'] == 46 and legacy['round19_tests'] == 76 and legacy['original_test_total'] == 540 and
            legacy['binding_counterexamples'] == 26, 'SEAL_HISTORICAL_TESTS')
        require(read(folder/'supervision/process_tree_verification.json')['status'] == 'PASS', 'SEAL_SUPERVISION')
        coordinator_events = list(durable_records(folder/'coordinator_guard.jsonl'))
        require(any(r.get('kind') == 'guard_installed' for r in coordinator_events)
                and not any(r.get('kind') in {'unexpected_denial','denied'} for r in coordinator_events),
                'SEAL_COORDINATOR_GUARD')
        for name in ['asset_context_verification', 'baseline_checker', 'baseline_whole_readback', 'baseline_r19_readback', 'center_checker', 'center_r19_readback',
                     'source_preservation', 'independent_terminal_verification', 'independent_necessary_gate_context', 'anchor_replays','independent_space_definition',
                     'selected_checker', 'independent_selection']:
            require(read(folder/('science/'+name+'.json'))['status'] == 'PASS', 'SEAL_SCIENCE_GATE:'+name)
    return dict(status=final['status'], exit_code=final['exit_code'], verified_members=len(manifest['files']),
        manifest_sha256=receipt['manifest_sha256'], delivery=str(folder), reexecuted=False)


def seal(work, selected, status, reasons):
    work = Path(work)
    life = Lifecycle(work/'lifecycle.json')
    check = lambda: life.check(False)
    check()
    folder = work/('sealed' if not (work/'sealed').exists() else 'sealed_'+str(time.time_ns()))
    folder.mkdir()
    for name in ['frozen', 'supervision']:
        if (work/name).exists():
            shutil.copytree(work/name, folder/name)
    for path in work.glob('starting_*'):
        if path.is_file():
            shutil.copyfile(path, folder/path.name)
    if (work/'coordinator_guard.jsonl').exists():
        shutil.copyfile(work/'coordinator_guard.jsonl', folder/'coordinator_guard.jsonl')
    historical = []
    selected_paths = {Path(p).resolve() for p in selected.values()}
    for attempt in sorted((work/'attempts').glob('*')):
        if attempt.resolve() not in selected_paths:
            command = read(attempt/'command_result.json') if (attempt/'command_result.json').exists() else {}
            result = read(attempt/'supervised_result.json') if (attempt/'supervised_result.json').exists() else {}
            historical.append(dict(path=str(attempt), attempt_id=attempt.name, job=command.get('job'),
                status=result.get('status'), exit_code=result.get('exit_code'), selected=False, full_exported=False,
                disposition='RETAINED_ONLY_IN_ORIGINAL_WORK',
                files=artifacts(attempt, check), summary_is_not_complete_exported_log=True))
    for preparation in sorted(p for p in work.iterdir() if p.is_dir() and
            (p.name == 'preparation' or p.name.startswith('precheck_') or p.name.startswith('preflight_'))):
        historical.append(dict(path=str(preparation), disposition='RETAINED_ONLY_IN_ORIGINAL_WORK',
            files=artifacts(preparation, check), summary_is_not_complete_exported_log=True))
    supplemental_preflight=work.parent/'checker_preflight'
    if supplemental_preflight.is_dir():
        historical.append(dict(path=str(supplemental_preflight),disposition='RETAINED_ONLY_IN_ORIGINAL_WORK',
            files=artifacts(supplemental_preflight,check),summary_is_not_complete_exported_log=True))
    write(folder/'historical_attempts_index.json', dict(status='PASS', histories=historical,
        selected_attempts_exported_in_full=True, prior_failures_not_erased=True))
    shutil.copyfile(work/'lifecycle.json', folder/'lifecycle.json')
    rows = read(work/'frozen/consumer_code.json') if (work/'frozen/consumer_code.json').exists() else []
    bound = {}
    for job, attempt in selected.items():
        check()
        if status == 'PASS':
            bound[job] = verify_attempt(attempt, rows, check)
        shutil.copytree(attempt/'output', folder/job)
        history = folder/'attempt_history'/attempt.name
        history.mkdir(parents=True)
        for name in ['consumer_code.json', 'consumer_code.zip', 'consumer_contract.json', 'command_result.json', 'supervised_result.json', 'stdout.log', 'stderr.log']:
            if (attempt/name).exists():
                shutil.copyfile(attempt/name, history/name)
    write(folder/'consumer_version_binding.json', dict(status='PASS' if status == 'PASS' else status, selected=bound))
    count = prefix_counts(folder/'science')
    if status != 'PASS' and (folder/'science/ledger.jsonl').exists() and (folder/'frozen/contract.json').exists():
        prefix_audit = terminal(folder, check, prefix=True)
        write(folder/'prefix_verification.json', prefix_audit)
        # Preserve generated-but-unverified tail records as unknown, not PASS.
        for key in ['fully_independently_verified','T100_certificate_verified','T90_certificate_verified']:
            require(count[key]==prefix_audit[key],'R20_PREFIX_VERIFIED_COUNT')
        if prefix_audit['status'] == 'FAIL':
            status = 'FAIL'
            reasons = list(reasons)+['Independent prefix verification failed']
    if status == 'PASS':
        completed = terminal(folder, check)
        require(completed['status'] == 'PASS', 'TERMINAL_VERIFICATION_FAILED')
        count = {k: completed[k] for k in COUNT_KEYS}
        verify_sources(rows, check)
    outcome = ('QUALIFIED_FURTHER_IMPROVEMENT_FOUND' if count['qualified_count'] else
        'NO_FURTHER_QUALIFIED_IMPROVEMENT_IN_DECLARED_THREE_ANCHOR_SECOND_SWAP_UNION') if status == 'PASS' else 'PARTIAL_NOT_CONCLUDED'
    final = dict(FLAGS, **count, profile=PROFILE, status=status,
        exit_code={'PASS': 0, 'FAIL': 1, 'BLOCKED': 2}[status], reasons=reasons,
        optimization_outcome=outcome, lifecycle_elapsed_at_seal_s=life.elapsed(),
        K12=dict(status='BLOCKED', exit_code=2, units=0, cost='NOT_RUN'),
        historical_rounds=dict(R14='PASS, 0 improvement', R15='PASS, 0 improvement', R16='PASS, 0 improvement', R17='PASS, 0 improvement',R18='PASS, 2 qualified improvements; retained as history'))
    final['declared'] = DECLARED
    final['retained_original_baseline'] = False
    final['conditional_offline_scope'] = 'Complete three fixed R19 anchor second-swap family union only'
    replay_file=folder/'science/enumeration_completion.json'
    if not replay_file.exists():replay_file=folder/'science/progress.json'
    replay_counts=read(replay_file) if replay_file.exists() else {}
    final['B0_replayed'] = replay_counts.get('B0_replayed',0)
    final['S_replayed'] = replay_counts.get('S_replayed',0)
    final['anchors_replayed'] = replay_counts.get('anchors_replayed',0)
    for name in ['baseline', 'center', 'selected']:
        if (folder/('science/'+name+'.json')).exists():
            report = read(folder/('science/'+name+'.json'))
            final[name+'_identity'] = report['identity']
            final[name+'_metrics'] = dict(mask=report['effective_grid'], raw=report['full_grid'],
                pooled_internal=report['regional']['pooled_internal'],
                pooled_boundary_inclusive=report['regional']['pooled_boundary_inclusive'])
    write(folder/'timings.json', dict(worker_wall_s={job: read(attempt/'output/job_result.json').get('worker_wall_s')
        for job, attempt in selected.items() if (attempt/'output/job_result.json').exists()},
        lifecycle_elapsed_upper_bound_s=life.elapsed(), overlapping_worker_walls_added=False,
        boundary='Seal timing; actual entry, research Shell, export child and final transport recorded outside seal'))
    write(folder/'final_status.json', final)
    report = report_text(final, folder)
    (folder/'report.md').write_text(report, encoding='utf8')
    require((folder/'report.md').read_text(encoding='utf8') == report, 'REPORT_UTF8_READBACK')
    entries = [dict(path=p.relative_to(folder).as_posix(), bytes=p.stat().st_size, sha256=sha(p, check))
               for p in sorted(folder.rglob('*')) if p.is_file()]
    write(folder/'artifact_manifest.json', dict(profile=PROFILE, files=entries))
    write(folder/'receipt.json', dict(profile=PROFILE, status=status, exit_code=final['exit_code'],
        manifest_sha256=sha(folder/'artifact_manifest.json', check), receipt_self_hashed=False))
    audit = independent_readback(folder, check)
    write(work/'latest_delivery.json', dict(path=str(folder), **audit))
    return audit
