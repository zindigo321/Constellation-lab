"""ROUND23 source policy and exact executed-attempt version binding."""
import hashlib
from pathlib import Path
import shutil
import sys
import time
import zipfile

from src.round13.archive import safe_name, safe_inventory
from src.round13.common import read, write, record, require, sha, fingerprint

ROOT = Path(__file__).resolve().parents[2]
JOBS = {'science', 'tests', 'legacy', 'regression', 'r14regression', 'guards', 'checker', 'certificate'}

def current_head():
    head=(ROOT/'.git/HEAD').read_text(encoding='ascii').strip()
    if not head.startswith('ref: '):return head
    name=head[5:];p=ROOT/'.git'/name
    if p.is_file():return p.read_text(encoding='ascii').strip()
    for line in (ROOT/'.git/packed-refs').read_text(encoding='ascii').splitlines():
        if line.endswith(' '+name):return line.split()[0]
    raise ValueError('R23_HEAD_UNAVAILABLE')

def verify_runtime(work,check=lambda:None):
    require(current_head()==read(Path(work)/'starting_git.json')['HEAD']['stdout'].strip(),'R23_HEAD_CHANGED')
    for row in read(Path(work)/'starting_checkpoints.json'):
        require(record(row['path'],check)=={key:row[key] for key in ['path','bytes','sha256']},'R23_CHECKPOINT_CHANGED')

def verify_contract(work,attempt,expected=None,check=lambda:None):
    actual=sha(Path(attempt)/'consumer_contract.json',check)
    require(actual==sha(Path(work)/'frozen/contract.json',check),'R23_CONTRACT_COPY_MISMATCH')
    if expected is not None:require(actual==expected,'R23_CONTRACT_DIGEST_MISMATCH')
    return actual


def allowed_new(name):
    try:
        name = safe_name(name)
    except ValueError:
        return False
    return (name.startswith('src/round23/') and name.endswith('.py')
            or name.startswith('tests/test_round23') and name.endswith('.py') and Path(name).parent.as_posix() == 'tests'
            or name in {'tools/run_round23.py', 'configs/round23.json', 'docs/round23.md', 'tools/export_round23.py'})


def starting(work):
    work = Path(work)
    for name in ['starting_code_manifest.json', 'starting_tracked_manifest.json', 'r14_code_before.json']:
        if (work/name).exists():
            data = read(work/name)
            return data['files'] if isinstance(data, dict) else data
    raise FileNotFoundError('ROUND23_STARTING_SOURCE_MANIFEST_MISSING')


def source_files(work):
    old = starting(work)
    old_names = {row.get('relative_path', Path(row['path']).relative_to(ROOT).as_posix()) for row in old}
    names = set(old_names)
    names.update(p.relative_to(ROOT).as_posix() for p in (ROOT/'src/round23').rglob('*.py'))
    names.update(p.relative_to(ROOT).as_posix() for p in (ROOT/'tests').glob('test_round23*.py'))
    names.update(['tools/run_round23.py', 'tools/export_round23.py', 'configs/round23.json', 'docs/round23.md'])
    actual = {p.relative_to(ROOT).as_posix() for folder in ['src', 'tools', 'tests', 'configs', 'docs']
              for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    require(all(allowed_new(n) for n in actual-old_names), 'ADDITION_OUTSIDE_ROUND23')
    require(old_names.issubset(actual | {n for n in old_names if '/' not in n}), 'STARTING_SOURCE_MISSING')
    return [ROOT/name for name in sorted(names)]


def manifest(paths, check=lambda: None):
    return [dict(record(path, check), relative_path=Path(path).relative_to(ROOT).as_posix()) for path in paths]


def verify_sources(rows, check=lambda: None):
    require(bool(rows), 'EMPTY_CONSUMER_SOURCE_MANIFEST')
    names = [safe_name(row['relative_path']) for row in rows]
    require(len({name.casefold() for name in names}) == len(rows), 'DUPLICATE_SOURCE_PATH')
    resolved = set()
    for row, name in zip(rows, names):
        check()
        path = ROOT/name
        target = path.resolve()
        require(target.is_relative_to(ROOT.resolve()), 'SOURCE_PATH_ESCAPE')
        require(not path.is_symlink() and all(not p.is_symlink() for p in path.parents if p.is_relative_to(ROOT)), 'SOURCE_LINK_REJECTED')
        require(target == Path(row['path']).resolve(), 'SOURCE_ABSOLUTE_PATH')
        require(str(target).casefold() not in resolved, 'DUPLICATE_RESOLVED_SOURCE_PATH')
        resolved.add(str(target).casefold())
        require(record(row['path'], check) == {k: row[k] for k in ['path', 'bytes', 'sha256']}, 'FROZEN_SOURCE_CHANGED: '+name)


def build_contract(work, cfg, metadata, rows, checkpoints):
    """Freeze all three matched third-swap families before candidate evaluation."""
    life = read(Path(work)/'lifecycle.json')
    return dict(profile='ROUND23_V1', config=cfg, metadata=metadata,execution_work=str(Path(work).resolve()),
        anchor_assertions=metadata['anchor_assertions'], frozen_anchor_order=['p1','p2','p3'],
        anchor_role='INFEASIBLE_ANCHOR_DIAGNOSTIC_ONLY',
        effective_start_epoch=life['effective_start_epoch'],
        preparation_elapsed_at_freeze_s=time.time()-life['effective_start_epoch'],
        starting_head=read(Path(work)/'starting_git.json')['HEAD']['stdout'].strip(),
        source_manifest_identity=fingerprint(rows), frozen_before_new_candidate=True,
        declared_candidates=166970, original_constraint_reference=metadata['original_constraint_reference'],
        search_center=metadata['search_center'], improvement_reference=metadata['improvement_reference'],
        immutable_search_center_indices=metadata['center_indices'], donors=metadata['donor_indices23'],
        enumeration='Numeric lexicographic unordered removal triple R then unordered donor triple A; exists the SAME i with R_i subset R and A_i subset A; each candidate once',
        candidate_definition='sorted((S minus (R_i union {r})) union (A_i union {b})); r in S minus R_i; b in D minus A_i',
        canonical_operations=dict(remove_count=3,add_count=3,symmetric_difference_from_S=6),
        family_order=['p1','p2','p3'],family_raw_counts=[55666,55666,55666],
        family_pairwise_intersections={'p1_p2':1,'p1_p3':1,'p2_p3':26},family_triple_intersection=0,
        family_first_owner_counts=dict(p1=55666,p2=55665,p3=55639),
        effective_removal_triples=51, independent_count_formula='25*2141+25*4281+6420=166970',
        removal_activation_classes=[dict(count=25,anchors=['p1'],additions_each=2141),
            dict(count=25,anchors=['p2','p3'],additions_each=4281),
            dict(count=1,anchors=['p1','p2','p3'],additions_each=6420)],
        retained_cache_definition='25 original S rows excluding the complete removal triple; rebuild threshold minima and Boolean union; bind complete R/S/source rows/threshold; add all three donors with matched family membership and first owner',
        certificate_priority=['T100_INFEASIBLE','T90_INFEASIBLE','FULL'],
        thresholds=metadata['original_reference_thresholds'],
        numerical_policy=dict(absolute_tolerance_s=1e-6,relative_tolerance=0,interval_merge_s=1e-6,
            substantive_improvement='S.Tmax - candidate.Tmax - 1e-6 >= 1',
            T90='ceil(9*n/10) order statistic; equality at cutoff included',
            Tavg='sum all internal gaps / candidate actual gap count',
            qualification_booleans_and_integer_identity_values='exact types and values',
            ranking='Exact Tmax/Tavg/T100/T90/identity order; no approximate ranking'),
        constraints=['28 unique legal states at own saved heights','each target at least 2 merged visits',
            'exact mask coverage','T100 finite <=604800','mask T90/T100 and pooled internal Tavg <= B0 +1e-6'],
        ranking=['Tmax','Tavg','T100','T90','identity'],
        certificate_semantics='T100/T90 known_infeasible=true, full_feasibility_evaluation_performed=false; all other uncomputed full metrics null/NOT_EVALUATED; c90 is a count, never T90 seconds',
        shared_boundary='Validated archive decoder/schema, coordinates/mask and original state tokens. Independent enumeration, numeric minima/order/union/gates, Boolean certificates and selection',
        conditional_offline_scope='Complete third-swap union of three fixed existing R22 infeasible double-swap anchors; no native runs or official protocol approval',
        physical_protocol_identity=cfg['native_protocol_hash'],
        checkpoint_inputs=checkpoints,checkpoint_inputs_in_old373=False,
        required_prior_stage='Completed R22 rerun including actual finalizer/Shell exits and subsequent full readback; original R22 BLOCKED/2 preserved',
        execution_interfaces=dict(interpreter=sys.executable,cwd=str(ROOT),
            worker_argv_prefix=[sys.executable,'-X','utf8','-B','-m','src.round23.worker','--work',str(Path(work).resolve())],
            export_child_argv=[sys.executable,'-X','utf8','-B','-m','src.round23.export','--work',str(Path(work).resolve()),
                '--destination',str(Path(cfg.get('preferred_output',ROOT/'work/round23'))/Path(work).name)],
            numerical_environment=cfg.get('numerical_thread_environment',{}),
            child_environment=dict(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8',GIT_OPTIONAL_LOCKS='0'),
            terminal_roles=['export_child','finalizer','observer'],shell_generator='src/round23/shell.py',
            actual_shell_exit_observed_outside_process=True,external_wrapper_exit='exit $global:LASTEXITCODE'),
        input_anchors={key:cfg[key] for key in ['archive_sha256','matrix_sha256','catalog_sha256','promotion_sha256']},
        history_identity_exclusion_enabled=False,candidate_REUSED=0,
        identity_novelty_claim=False,
        partial_jsonl_policy='Only a malformed unterminated final JSON line may be ignored for interrupted-prefix diagnostics and is never counted; PASS requires all 166970 complete records; middle damage or duplicate records fail')


def freeze(work, cfg, metadata, check=lambda: None):
    work = Path(work)
    old = starting(work)
    require(len(old) == 373, 'STARTING_R22_SOURCE_COUNT')
    for row in old:
        require(record(row['path'], check) == {k: row[k] for k in ['path', 'bytes', 'sha256']}, 'R22_SOURCE_BYTES_CHANGED')
    rows = manifest(source_files(work), check)
    verify_sources(rows, check)
    old_names = {row.get('relative_path', Path(row['path']).relative_to(ROOT).as_posix()) for row in old}
    additions = sorted(row['relative_path'] for row in rows if row['relative_path'] not in old_names)
    require(all(allowed_new(name) for name in additions), 'ADDITION_OUTSIDE_ROUND23')
    frozen = work/'frozen'
    require(not frozen.exists(), 'FROZEN_CONTRACT_ALREADY_EXISTS')
    frozen.mkdir()
    write(frozen/'change_policy.json', dict(profile='ROUND23_V1', unchanged_prior_files=len(old),
        allowed_modified=[], additions=additions, historical_profiles_modified=False))
    checkpoints = read(work/'starting_checkpoints.json')
    require(len(checkpoints) == 6, 'R23_CHECKPOINT_COUNT')
    for row in checkpoints:
        require(record(row['path'],check) == {k:row[k] for k in ['path','bytes','sha256']}, 'R23_CHECKPOINT_CHANGED')
    contract = build_contract(work, cfg, metadata, rows, checkpoints)
    prerequisite=read(work/'r22_prerequisite.json')
    require(prerequisite['status']=='PASS' and prerequisite['old373_preserved']==373 and
        prerequisite['checkpoint6_preserved']==6 and prerequisite['r22_rerun_actual_exit_codes_all_zero'] is True,
        'ROUND23_R22_PREREQUISITE_NOT_COMPLETED')
    require(sha(prerequisite['r22_after_all_exits_observation_path'],check)==
        prerequisite['r22_after_all_exits_observation_sha256'],'ROUND23_R22_EXIT_READBACK_CHANGED')
    require(sha(Path(prerequisite['original_r22_seal'])/'artifact_manifest.json',check)==
        prerequisite['original_r22_manifest_sha256']=='90ef50c2c05f715e0c97dbd71366b4658601e2666055eeefb00360ee66f9dfab',
        'ROUND23_ORIGINAL_R22_SEAL_CHANGED')
    contract['r22_prerequisite']=dict(input_record=record(work/'r22_prerequisite.json',check),evidence=prerequisite)
    from .control import verify_delivery_preflight,verify_shell_probes
    contract['early_delivery_preflight']=verify_delivery_preflight(work,cfg['preferred_output'])
    contract['actual_shell_probe_binding']=verify_shell_probes(work)
    preparation_paths=sorted(p for p in (work/'preparation').rglob('*') if p.is_file())
    preparation_paths+=sorted((work/'observations').glob('*.ps1'))
    evidence=[]
    for path in preparation_paths:
        check()
        require(not path.is_symlink() and path.resolve().is_relative_to(work.resolve()) and
            all(not parent.is_symlink() for parent in path.parents if parent.is_relative_to(work.resolve())),
            'ROUND23_PREPARATION_SOURCE_SCOPE')
        relative=path.relative_to(work).as_posix()
        snapshot=frozen/'preparation_evidence'/relative
        snapshot.parent.mkdir(parents=True,exist_ok=True)
        before=record(path,check)
        shutil.copyfile(path,snapshot)
        require((snapshot.stat().st_size,sha(snapshot,check))==(before['bytes'],before['sha256']),
            'ROUND23_PREPARATION_COPY_BYTES')
        evidence.append(dict(source_path=str(path.resolve()),source_relative_path=relative,
            snapshot_relative_path=snapshot.relative_to(frozen).as_posix(),bytes=before['bytes'],sha256=before['sha256']))
    contract['preparation_boundary_evidence']=evidence
    contract['preparation_failures_preserved']=True
    write(frozen/'consumer_code.json', rows)
    write(frozen/'contract.json', contract)
    with zipfile.ZipFile(frozen/'consumer_code.zip', 'w', zipfile.ZIP_DEFLATED) as snapshot:
        for row in rows:
            snapshot.write(row['path'], row['relative_path'])
    return rows


def verify_preparation_evidence(contract,frozen,check=lambda:None):
    """Read immutable auxiliary snapshots and their actual original work bytes."""
    frozen=Path(frozen).resolve()
    work=Path(contract['execution_work']).resolve()
    require(bool(contract.get('preparation_boundary_evidence')),'ROUND23_PREPARATION_EVIDENCE_EMPTY')
    seen=set()
    for row in contract.get('preparation_boundary_evidence',[]):
        check()
        name=safe_name(row['source_relative_path'])
        copied=safe_name(row['snapshot_relative_path'])
        source, snapshot=work/name,frozen/copied
        require(name.casefold() not in seen and source.resolve()==Path(row['source_path']).resolve() and
            source.resolve().is_relative_to(work) and snapshot.resolve().is_relative_to(frozen) and
            not source.is_symlink() and not snapshot.is_symlink() and
            all(not parent.is_symlink() for parent in source.parents if parent.is_relative_to(work)) and
            all(not parent.is_symlink() for parent in snapshot.parents if parent.is_relative_to(frozen)),
            'ROUND23_PREPARATION_EVIDENCE_SCOPE')
        seen.add(name.casefold())
        for path in [source,snapshot]:
            require(path.stat().st_size==row['bytes'] and sha(path,check)==row['sha256'],
                'ROUND23_PREPARATION_EVIDENCE_CHANGED')
    require({'preparation/delivery_writable_preflight.json','preparation/shell_probe_observations.json',
        'preparation/shell7.ps1','preparation/shell_null.ps1'}.issubset(seen),
        'ROUND23_PREPARATION_REQUIRED_HELPER_MISSING')
    return dict(status='PASS',files=len(seen))


def artifacts(out, check=lambda: None):
    out = Path(out)
    result = []
    for path in sorted(out.rglob('*')):
        if path.is_file():
            check()
            require(not path.is_symlink(), 'OUTPUT_LINK_REJECTED')
            result.append(dict(relative_path=path.relative_to(out).as_posix(), bytes=path.stat().st_size, sha256=sha(path, check)))
    return result


def verify_attempt(attempt, final_rows, check=lambda: None):
    attempt = Path(attempt).resolve()
    require(attempt.parent.name == 'attempts', 'ATTEMPT_SCOPE')
    consumer = read(attempt/'consumer_code.json')
    command = read(attempt/'command_result.json')
    require(consumer == final_rows == command['code_manifest'], 'ATTEMPT_CONSUMER_VERSION_MISMATCH')
    verify_sources(final_rows, check)
    out = attempt/'output'
    require(command['attempt_id'] == attempt.name and Path(command['output']).resolve() == out, 'ATTEMPT_PATH_MISMATCH')
    job = command['job']
    require(job in JOBS, 'ATTEMPT_UNKNOWN_JOB')
    expected = [sys.executable, '-X', 'utf8', '-B', '-m', 'src.round23.worker',
        '--work', str(attempt.parent.parent), '--out', str(out), '--job', job]
    require(command['command'] == expected, 'ATTEMPT_COMMAND_MISMATCH')
    require(Path(command['cwd']).resolve() == ROOT, 'ATTEMPT_CWD_MISMATCH')
    contract_digest=sha(attempt/'consumer_contract.json',check)
    require(contract_digest==sha(attempt.parent.parent/'frozen/contract.json',check)
            and command['contract_sha256']==contract_digest,'ATTEMPT_CONTRACT_BINDING')
    require(command['output_artifacts'] == artifacts(out, check), 'ATTEMPT_OUTPUT_ARTIFACT_MISMATCH')
    result = read(out/'job_result.json')
    require(result['attempt_id'] == attempt.name and result['job'] == job and
            result['consumer_identity'] == fingerprint(final_rows), 'WORKER_ATTEMPT_BINDING')
    require(result['argv'] == expected and Path(result['cwd']).resolve() == ROOT,
            'WORKER_ACTUAL_COMMAND_BINDING')
    require(result['contract_sha256']==contract_digest,'WORKER_CONTRACT_BINDING')
    for row in read(attempt.parent.parent/'frozen/contract.json')['checkpoint_inputs']:
        require(record(row['path'], check) == {k:row[k] for k in ['path','bytes','sha256']},
                'R23_CHECKPOINT_CHANGED_AFTER_RUN')
    require(result['status'] == 'PASS' and result['exit_code'] == 0 and
            command['python_exit_code'] == 0 and command.get('timeout') is False, 'ATTEMPT_NOT_COMPLETED_PASS')
    require(read(attempt/'supervised_result.json') == result and command['supervised_result_exit_code'] == 0,
            'ATTEMPT_SUPERVISED_RESULT_BINDING')
    with zipfile.ZipFile(attempt/'consumer_code.zip') as snapshot:
        safe_inventory(snapshot.infolist())
        require(set(snapshot.namelist()) == {row['relative_path'] for row in final_rows}, 'ATTEMPT_SNAPSHOT_SET')
        for row in final_rows:
            check()
            blob = snapshot.read(row['relative_path'])
            require(len(blob) == row['bytes'] and hashlib.sha256(blob).hexdigest() == row['sha256'], 'ATTEMPT_SNAPSHOT_BYTES')
    return dict(status='PASS', profile='ROUND23_V1', attempt_id=attempt.name, job=job,
        command=command['command'], consumer_identity=fingerprint(final_rows),
        output_artifacts_identity=fingerprint(command['output_artifacts']),
        contract_sha256=contract_digest,
        code_snapshot_sha256=sha(attempt/'consumer_code.zip', check))
