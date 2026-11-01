"""R22 version-exact offline regressions in immutable historical subsets."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from src.round13.common import read, write, record, require, sha, fingerprint
from .binding import ROOT, starting

R21_MANIFEST_SHA = '5a6eda3f5cca9bdc9cd9a0cbd26b098e0b500296e1da58c6afc0b22d9f32679b'
DEFAULT_R21 = Path('G:/gpt-file/Codex/outputs/bd-fmb/round21/20261031T070246_offline')
SUBSET_COUNTS = (168, 185, 203, 223, 245, 268, 292, 319, 346)
# Executed before any historical guard: ctypes initializes only Python's normal
# Windows standard-library support. No scientific native modules are imported.
BOOTSTRAP = 'import ctypes, ctypes.wintypes, datetime, hashlib, importlib.abc, io, json, os, pathlib, platform, subprocess, tempfile, time, unittest\n'


def relative(row, root=None):
    return row.get('relative_path') or Path(row['path']).relative_to(root or ROOT).as_posix()


def source_subset(rows, count, root=None):
    """Select historical source versions without editing their copied bytes."""
    excluded = {168:(14,15,16,17,18,19,20,21),185:(15,16,17,18,19,20,21),203:(16,17,18,19,20,21),223:(17,18,19,20,21),245:(18,19,20,21),268:(19,20,21),292:(20,21),319:(21,),346:()}[count]
    result = []
    for row in rows:
        name = relative(row, root)
        if any(name.startswith(f'src/round{n}/') or name.startswith(f'tests/test_round{n}') or
               name in {f'tools/run_round{n}.py', f'tools/export_round{n}.py', f'configs/round{n}.json', f'docs/round{n}.md'}
               for n in excluded):
            continue
        result.append(dict(row))
    require(len(result) == count, f'REGRESSION_SUBSET{count}_COUNT')
    return result


def verify_mapping(root, repo, subset, check=lambda: None):
    root, repo = Path(root).resolve(), Path(repo).resolve()
    mapping = []
    for source in subset:
        check()
        name = relative(source, root)
        current = record(source['path'], check)
        require((current['bytes'], current['sha256']) == (source['bytes'], source['sha256']),
                'REGRESSION_SOURCE_VERSION_MISMATCH')
        target = repo/name
        require(target.resolve().is_relative_to(repo) and not target.is_symlink(), 'REGRESSION_COPY_PATH')
        copied = record(target, check)
        require((copied['bytes'], copied['sha256']) == (source['bytes'], source['sha256']),
                'REGRESSION_COPY_VERSION_MISMATCH')
        mapping.append(dict(relative_path=name, source=current, executed_copy=copied))
    return mapping


def test_ids(log):
    rows = []
    for line in Path(log).read_text(encoding='utf8').splitlines():
        match = re.match(r'^\w+ \(([^)]+)\) \.\.\.', line)
        if match:
            rows.append(match.group(1))
    require(len(rows) == len(set(rows)), 'DUPLICATED_ACTUAL_TEST_IDS')
    return rows


def bound_historical_log(relative_name):
    cfg = read(ROOT/'configs/round22.json')
    sealed = Path(cfg.get('r21_delivery', DEFAULT_R21))/'sealed'
    manifest = sealed/'artifact_manifest.json'
    require(sha(manifest) == R21_MANIFEST_SHA, 'REGRESSION_R21_MANIFEST_ANCHOR')
    members = {row['path']: row for row in read(manifest)['files']}
    require(relative_name in members, 'REGRESSION_HISTORICAL_LOG_NOT_BOUND')
    expected, path = members[relative_name], sealed/relative_name
    require(path.stat().st_size == expected['bytes'] and sha(path) == expected['sha256'],
            'REGRESSION_HISTORICAL_LOG_BYTES')
    return path


def verify_ids(log, expected_log, count):
    actual, expected = test_ids(log), test_ids(expected_log)
    require(len(actual) == len(expected) == count and set(actual) == set(expected),
            'HISTORICAL_TEST_ID_SET_MISMATCH')
    return dict(status='PASS', count=count, ids=actual, identity=fingerprint(sorted(actual)),
                expected_log=record(expected_log))


def suite_adapter(pattern):
    require(pattern in {'test_round14*.py', 'test_round15*.py', 'test_round16*.py', 'test_round17*.py',
                        'test_round18*.py', 'test_round19*.py', 'test_round20*.py', 'test_round21*.py'}, 'REGRESSION_SELECTION_PATTERN')
    return BOOTSTRAP + '''from guard_impl import install
install()
import json, os, unittest
_discover = unittest.defaultTestLoader.discover
_calls = []
def _round22_discover(start_dir, pattern='test*.py', top_level_dir=None):
    if str(start_dir) == 'tests' and pattern == 'test*.py' and top_level_dir is None and not _calls:
        _calls.append(1)
        with open(os.environ['ROUND22_SELECTION_LOG'], 'w', encoding='utf8') as stream:
            json.dump(dict(source='unchanged src.round9.regression.worker', start_dir='tests',
                requested_pattern='test*.py', selected_pattern=SELECTED, test_files_modified=False), stream)
        return _discover(start_dir, pattern=SELECTED, top_level_dir=top_level_dir)
    return _discover(start_dir, pattern=pattern, top_level_dir=top_level_dir)
unittest.defaultTestLoader.discover = _round22_discover
'''.replace('SELECTED', repr(pattern)) + network_adapter() + ('\nfrom round22_reference_adapter import install as install_reference\ninstall_reference()\n' if pattern in {'test_round19*.py','test_round20*.py'} else '')


def network_adapter():
    """Supplement unchanged historical guards in every inherited Python child.

    Historical mechanism tests retain their original detector fixture and
    subprocess policy; this added audit hook closes all socket event gaps.
    """
    return '\nfrom round22_legacy_guard import install as _round22_install\n_round22_install()\n'


def verify_helper_mapping(folder,expected=None):
    """Bind the added standalone guard's executed copy just like old sources."""
    source=record(ROOT/'src/round22/legacy_guard.py')
    copied=record(Path(folder)/'round22_legacy_guard.py')
    expected=source if expected is None else expected
    require(source==expected,'REGRESSION_HELPER_SOURCE_CHANGED')
    require((copied['bytes'],copied['sha256'])==(expected['bytes'],expected['sha256']),
            'REGRESSION_HELPER_COPY_CHANGED')
    return dict(relative_path='src/round22/legacy_guard.py',source=expected,executed_copy=copied)


def verify_bootstrap_mapping(folder, expected=None):
    """Bind both the unchanged historical guard copy and generated bootstrap."""
    folder = Path(folder)
    actual = dict(source=record(ROOT/'src/round9/guard.py'),
        guard_copy=record(folder/'guard_impl.py'), bootstrap=record(folder/'sitecustomize.py'))
    require((actual['source']['bytes'],actual['source']['sha256']) ==
        (actual['guard_copy']['bytes'],actual['guard_copy']['sha256']), 'REGRESSION_BOOTSTRAP_GUARD_BYTES')
    if expected is not None:
        require(actual == expected, 'REGRESSION_BOOTSTRAP_CHANGED')
    return actual


def fixture_temp_root(out, repo, pattern):
    out, repo = Path(out).resolve(), Path(repo).resolve()
    require(repo.is_relative_to(out), 'REGRESSION_FIXTURE_REPO_SCOPE')
    result = repo/'work/round20/tmp' if pattern == 'test_round20*.py' else out/'tmp'
    require(result.is_relative_to(out), 'REGRESSION_FIXTURE_TEMP_SCOPE')
    return result


def run_old202(work, out, life, commands):
    from src.round9 import regression as old
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    subset = source_subset(starting(work), 168)
    # The old runner expects precisely path/bytes/sha256 source records.
    old_rows = [{k: row[k] for k in ['path', 'bytes', 'sha256']} for row in subset]
    write(out/'subset168.json', subset)
    original = old.subprocess.run
    check = lambda: life.check(True)

    def observed_run(argv, **kwargs):
        if '--regression-worker' not in argv:
            return original(argv, **kwargs)
        from .guard import register_command
        from .supervise import run
        repo = out/'regression/repo'
        adapter_path = out/'regression/guard/sitecustomize.py'
        shutil.copyfile(ROOT/'src/round22/legacy_guard.py',adapter_path.parent/'round22_legacy_guard.py')
        adapter_path.write_text(BOOTSTRAP+adapter_path.read_text(encoding='utf8')+network_adapter(), encoding='utf8')
        kwargs['env']['ROUND22_LEGACY_REPO']=str(repo)
        # The historical fixture explicitly supports preserving every nested
        # mechanism run. Keep its actual child logs and results on failures;
        # neither test source, assertions nor process policy are changed.
        mechanism_root = out/'regression/mechanism_evidence'
        previous_mechanism_root = kwargs['env'].get('R2_MECHANISM_EVIDENCE')
        kwargs['env']['R2_MECHANISM_EVIDENCE'] = str(mechanism_root)
        write(out/'mechanism_evidence_policy.json',dict(
            source='Unchanged test_round2_mechanisms.EvidenceTests.setUp environment hook',
            destination=str(mechanism_root),previous_environment_value=previous_mechanism_root,
            original_test_source_modified=False,original_assertions_modified=False,
            nested_commands_modified=False,results_reused=False,
            thread_related_environment={key:value for key,value in kwargs['env'].items()
                if key.upper().startswith(('OMP_','MKL_','OPENBLAS_','NUMEXPR_','VECLIB_','BLIS_','NUMBA_')) or 'NUM_THREADS' in key.upper()}))
        helper=verify_helper_mapping(adapter_path.parent)
        bootstrap=verify_bootstrap_mapping(adapter_path.parent)
        write(out/'bootstrap_mapping_before.json',bootstrap)
        write(out/'helper_mapping_before.json',helper)
        write(out/'supplemental_network_adapter.json', dict(status='PASS',
            adapter=record(adapter_path),source=record(Path(__file__)),helper_mapping=helper,
            copied_historical_source_changed=False))
        write(out/'mapping_before.json', verify_mapping(ROOT, repo, subset, check))
        kwargs['timeout'] = min(kwargs.get('timeout', 170), life.timeout())
        command = dict(argv=argv, cwd=str(kwargs.get('cwd')), enforced_timeout_s=kwargs['timeout'],
                       profile='ROUND22_ISOLATED_168_V1', timeout=False)
        start = time.perf_counter()
        try:
            register_command(commands, argv, kwargs['cwd'], work)
            proc = run(argv, **kwargs)
            command['exit_code'] = proc.returncode
            return proc
        except subprocess.TimeoutExpired:
            command['timeout'] = True
            raise
        finally:
            command['wall_s'] = time.perf_counter()-start
            write(out/'supervised_command.json', command)
            write(out/'mapping_after.json', verify_mapping(ROOT, repo, subset, check))
            write(out/'helper_mapping_after.json',verify_helper_mapping(adapter_path.parent,helper['source']))
            write(out/'bootstrap_mapping_after.json',verify_bootstrap_mapping(adapter_path.parent,bootstrap))

    old.subprocess.run = observed_run
    try:
        result = old.run_regression(ROOT, out, old_rows)
    finally:
        old.subprocess.run = original
    require(result['status'] == 'PASS' and result['tests'] == 202 and
            not any(result[key] for key in ['failures', 'errors', 'skipped']), 'ORIGINAL_202_TEST_FAILURE')
    write(out/'test_id_verification.json', verify_ids(out/'regression/stderr.log',
          bound_historical_log('legacy/old202/regression/stderr.log'), 202))
    return result


def run_selected(work, out, life, subset_count, pattern, expected_count, historical_log, commands):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    repo, guard = out/'repo', out/'guard'
    tmp = fixture_temp_root(out, repo, pattern)
    for directory in [repo, guard, tmp, repo/'work']:
        directory.mkdir(parents=True, exist_ok=True)
    subset = source_subset(starting(work), subset_count)
    check = lambda: life.check(True)
    for row in subset:
        check(); name = relative(row); dest = repo/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        require(record(row['path'], check) == {key: row[key] for key in ['path', 'bytes', 'sha256']},
                'HISTORICAL_SUBSET_SOURCE_CHANGED')
        shutil.copyfile(row['path'], dest)
    write(out/f'subset{subset_count}.json', subset)
    write(out/'mapping_before.json', verify_mapping(ROOT, repo, subset, check))
    shutil.copyfile(ROOT/'src/round9/guard.py', guard/'guard_impl.py')
    shutil.copyfile(ROOT/'src/round22/legacy_guard.py', guard/'round22_legacy_guard.py')
    shutil.copyfile(ROOT/'src/round22/reference_adapter.py', guard/'round22_reference_adapter.py')
    adapter = suite_adapter(pattern)
    (guard/'sitecustomize.py').write_text(adapter, encoding='utf8')
    require((guard/'sitecustomize.py').read_text(encoding='utf8') == adapter, 'ADAPTER_UTF8_READBACK')
    helper=verify_helper_mapping(guard)
    bootstrap=verify_bootstrap_mapping(guard)
    write(out/'bootstrap_mapping_before.json',bootstrap)
    ref_source=record(ROOT/'src/round22/reference_adapter.py');ref_copy=record(guard/'round22_reference_adapter.py')
    require((ref_source['bytes'],ref_source['sha256'])==(ref_copy['bytes'],ref_copy['sha256']),'R22_REFERENCE_HELPER_BYTES')
    write(out/'reference_helper_mapping.json',dict(source=ref_source,executed_copy=ref_copy))
    write(out/'helper_mapping_before.json',helper)
    write(out/'suite_selection_adapter.json', dict(profile='ROUND22_ISOLATED_SELECTION_V1',
        content=adapter, sitecustomize=record(guard/'sitecustomize.py'), guard=record(guard/'guard_impl.py'),
        consumer_adapter=record(Path(__file__)),helper_mapping=helper,modifications_to_copied_files=False))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8',
        PYTHONPATH=str(guard)+os.pathsep+str(repo), TMP=str(tmp), TEMP=str(tmp), MPLCONFIGDIR=str(out/'mpl'),
        ROUND9_REGRESSION='1', ROUND9_WRITE_ROOTS=json.dumps([str(out)]), ROUND9_GUARD_LOG=str(out/'guard.jsonl'),
        ROUND21_TEST_ROOT=str(tmp), ROUND20_TEST_ROOT=str(tmp), ROUND19_TEST_ROOT=str(tmp), ROUND18_TEST_ROOT=str(tmp), ROUND17_TEST_ROOT=str(tmp), ROUND16_TEST_ROOT=str(tmp), ROUND15_TEST_ROOT=str(tmp), ROUND14_TEST_ROOT=str(tmp), ROUND13_TEST_ROOT=str(tmp),
        ROUND22_SELECTION_LOG=str(out/'suite_selection.json'),ROUND22_LEGACY_REPO=str(repo),
        ROUND22_ORIGINAL_ROOT=str(ROOT),ROUND22_REFERENCE_TEST_SHAS=json.dumps({
            'test_round19_binding':sha(ROOT/'tests/test_round19_binding.py'),
            'test_round20_binding':sha(ROOT/'tests/test_round20_binding.py')}),
        ROUND22_REFERENCE_LOG=str(out/'reference_adapter.jsonl'))
    argv = [sys.executable, '-B', str(repo/'tools/run_round9.py'), '--regression-worker', '--result', str(out/'tests.json')]
    from .guard import register_command
    from .supervise import run
    register_command(commands, argv, repo, work)
    start, timeout = time.perf_counter(), life.timeout()
    command = dict(argv=argv, cwd=str(repo), enforced_timeout_s=timeout, timeout=False)
    try:
        with (out/'stdout.log').open('wb') as stdout, (out/'stderr.log').open('wb') as stderr:
            proc = run(argv, cwd=repo, env=env, stdout=stdout, stderr=stderr, timeout=timeout)
        command['exit_code'] = proc.returncode
    except subprocess.TimeoutExpired:
        command['timeout'] = True
        raise
    finally:
        command['wall_s'] = time.perf_counter()-start
        write(out/'supervised_command.json', command)
        write(out/'mapping_after.json', verify_mapping(ROOT, repo, subset, check))
        write(out/'helper_mapping_after.json',verify_helper_mapping(guard,helper['source']))
        write(out/'bootstrap_mapping_after.json',verify_bootstrap_mapping(guard,bootstrap))
        require(record(ROOT/'src/round22/reference_adapter.py')==ref_source and record(guard/'round22_reference_adapter.py')==ref_copy,'R22_REFERENCE_HELPER_CHANGED')
    result = read(out/'tests.json') if (out/'tests.json').exists() else dict(successful=False, tests=0)
    events = [json.loads(line) for line in (out/'guard.jsonl').read_text(encoding='utf8').splitlines()]
    denied = [event for event in events if event['kind'] == 'denied']
    result.update(status='PASS' if proc.returncode == 0 and result['successful'] and not denied else 'FAIL',
        argv=argv, exit_code=proc.returncode, elapsed_s=time.perf_counter()-start, enforced_timeout_s=timeout,
        guard_denials=denied, guard_installations=sum(event['kind'] == 'guard_installed' for event in events),
        stdout=record(out/'stdout.log'), stderr=record(out/'stderr.log'), guard=record(out/'guard.jsonl'),
        subset_files=subset_count, source_files_modified=False, selected_test_pattern=pattern)
    write(out/'result.json', result)
    require(result['status'] == 'PASS' and result['tests'] == expected_count and
            not any(result[key] for key in ['failures', 'errors', 'skipped']),
            'ROUND'+str({185:14,203:15,223:16,245:17,268:18,292:19,319:20,346:21}[subset_count])+f'_{expected_count}_TEST_FAILURE')
    require(read(out/'suite_selection.json')['selected_pattern'] == pattern, 'TEST_SELECTION_NOT_BOUND')
    if pattern in {'test_round19*.py','test_round20*.py'}:
        adapted=[json.loads(line) for line in (out/'reference_adapter.jsonl').read_text(encoding='utf8').splitlines()]
        expected_id = ('test_round19_binding.BindingTests.test_old268_preserved_and_subsets_have_exact_members'
            if pattern=='test_round19*.py' else 'test_round20_binding.BindingTests.test_old292_and_exact_historical_subsets')
        require(len(adapted)==1 and adapted[0]['test_id']==expected_id and adapted[0]['restored']
            and adapted[0]['test_bytes_preserved'] and adapted[0]['original_before']==adapted[0]['original_after'],
            'R22_REFERENCE_ADAPTATION_RECORD')
    write(out/'test_id_verification.json', verify_ids(out/'stderr.log', bound_historical_log(historical_log), expected_count))
    return result


def run_binding26(work, out, life):
    from src.round10.binding import bind
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    cfg = read(ROOT/'configs/round18.json'); prior = Path(cfg['prior'])/'executed_closure'
    frozen = read(prior/'starting_code_manifest.json')['files']
    require(len(frozen) == 142, 'FROZEN142_COUNT')
    mapping = []
    for row in frozen:
        life.check(True)
        require(record(row['path']) == row, 'FROZEN142_CHANGED')
        mapping.append(dict(relative_path=Path(row['path']).relative_to(ROOT).as_posix(),
            source=row, actual_read_path=row['path'], isolation='read-only fixed historical binder; no source copy'))
    write(out/'subset142.json', frozen); write(out/'source_mapping.json', mapping)
    binding, cases = bind(Path(read(ROOT/'configs/round12.json')['k9']), ROOT, frozen, out, out)
    require(binding['status'] == cases['status'] == 'PASS' and len(cases['cases']) == 26,
            'HISTORICAL_BINDING_COUNTEREXAMPLES')
    for row in frozen:
        require(record(row['path']) == row, 'FROZEN142_CHANGED_AFTER_BINDING')
    write(out/'mapping_after.json', mapping)
    return dict(status='PASS', cases=26, binding=binding, historical_stage_map=binding['historical_stage_map'])


def run_regressions(work, out, life, commands=None):
    out = Path(out)
    commands = [] if commands is None else commands
    from .guard import install
    install(work, out/'parent_guard.jsonl', role='regression', commands=commands)
    old = run_old202(work, out/'old202', life, commands)
    r14 = run_selected(work, out/'round14_89', life, 185, 'test_round14*.py', 89,
                       'legacy/round14_89/stderr.log', commands)
    r15 = run_selected(work, out/'round15_66', life, 203, 'test_round15*.py', 66, 'legacy/round15_66/stderr.log', commands)
    r16 = run_selected(work, out/'round16_30', life, 223, 'test_round16*.py', 30, 'legacy/round16_30/stderr.log', commands)
    r17 = run_selected(work, out/'round17_31', life, 245, 'test_round17*.py', 31, 'legacy/round17_31/stderr.log', commands)
    r18 = run_selected(work, out/'round18_46', life, 268, 'test_round18*.py', 46, 'legacy/round18_46/stderr.log', commands)
    r19 = run_selected(work,out/'round19_76',life,292,'test_round19*.py',76,'legacy/round19_76/stderr.log',commands)
    r20 = run_selected(work,out/'round20_49',life,319,'test_round20*.py',49,'legacy/round20_49/stderr.log',commands)
    r21 = run_selected(work,out/'round21_63',life,346,'test_round21*.py',63,'tests/tests.log',commands)
    historical = run_binding26(work, out/'binding26', life)
    result = dict(status='PASS', regression_tests=202, old_tests=202, round14_tests=89, round15_tests=66,
        round16_tests=30, round17_tests=31, round18_tests=46, round19_tests=76, round20_tests=49, round21_tests=63, original_test_total=652, binding_counterexamples=26, regression=old,
        round14_regression=r14, round15_regression=r15, round16_regression=r16, round17_regression=r17, round18_regression=r18, round19_regression=r19, round20_regression=r20, round21_regression=r21, historical_binding=historical,
        untouched_source_files=346, generated_adapter_changes_test_selection_and_adds_socket_guard=True,
        historical_mechanism_child_policy='Unchanged fixture source plus complete finite argv/interpreter/cwd/output schema checks and inherited socket.* denial',
        historical_platform_exception='Exact System32/cmd.exe /c ver used by platform.platform only; no native scientific activation',
        historical_node_discovery='New adapter reads COMPUTERNAME for platform._node; socket.gethostname remains forbidden',
        source_subset_counts=list(SUBSET_COUNTS), historical_binding_subset_count=142,
        standard_library_bootstrap=BOOTSTRAP, bootstrap_before_historical_guards=True)
    write(out/'regression_summary.json', result)
    return result
