"""R22 original-asset decoder and immutable R21/R19/planning provenance.

Historical candidates are evidence only. Every declared R22 candidate is fresh.
"""
import hashlib
import json
from pathlib import Path
import zipfile

from src.round13.common import read, record, require, sha, fingerprint
from src.round13.archive import safe_inventory, safe_name
from src.round16 import inputs as decoder
from .space import B0, S, ANCHORS, summary

ROOT = Path(__file__).resolve().parents[2]
DIGESTS = dict(sealed='5a6eda3f5cca9bdc9cd9a0cbd26b098e0b500296e1da58c6afc0b22d9f32679b',
    transport='75b9f9e931f51790a0e82074a64ee6d773799667b0e34813d6b70d8ba4ee6aa7',
    delivery='e1a8a60aa4f8a9da6541c220afa2fbdd6981ae4af2eeb2ef3daf4bc8b2b89cc8',
    code='076a3136908e05e58af7c0d68b7ab1e94c5b4bec9517ad7dfef05899579fecff',
    contract='ceeaabb765872af900c371311dd08aac0f8a43493ac6349239ac4d397525c748')
R19_MANIFEST = 'a100ed04e0182f7844d2566340522609c93a0f529109e1a42d8b7e3ab4a2d515'
S_CSV_SHA = '7b9480f8a1aef119b73cd2e1732ce45845b1634886492a8c5857636ad8654365'


def evidence_text(path, check=lambda: None):
    """Read archival logs by explicit BOM; JSON keeps common.read's UTF8sig policy.

    JSONL remains strict UTF-8 with no BOM and every line is parsed. UTF16 or
    invalid UTF8 science is never accepted and no replacement decoding is used.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == '.json':
        read(path)
        return 'utf-8-sig'
    encoding = 'utf8'
    if suffix in {'.log', '.txt'}:
        with path.open('rb') as stream:
            prefix = stream.read(4)
        if prefix.startswith((b'\xff\xfe', b'\xfe\xff')):
            encoding = 'utf-16'
        elif prefix.startswith(b'\xef\xbb\xbf'):
            encoding = 'utf-8-sig'
    with path.open(encoding=encoding) as stream:
        for line in stream:
            check()
            if suffix == '.jsonl':
                json.loads(line)
    return encoding


def _text_inventory(folder, check=lambda: None):
    folder = Path(folder)
    result = {}
    for path in sorted(folder.rglob('*')):
        if path.is_file():
            check()
            require(not path.is_symlink() and path.resolve().is_relative_to(folder.resolve()), 'R22_EVIDENCE_PATH')
            name = path.relative_to(folder).as_posix()
            result[name] = record(path, check)
            if path.suffix.lower() in {'.md','.json','.jsonl','.log','.txt'}:
                result[name]['text_encoding'] = evidence_text(path, check)
    return result


def _used_manifest_evidence(sealed, check):
    result = {}
    for row in read(sealed/'artifact_manifest.json')['files']:
        name = safe_name(row['path'])
        if name.startswith(('frozen/','science/','attempt_history/')) or name in {
                'report.md','final_status.json','consumer_version_binding.json','historical_attempts_index.json'}:
            path = sealed/name
            check()
            require(path.resolve().is_relative_to(sealed.resolve()) and not path.is_symlink(), 'R22_PRIOR_EVIDENCE_PATH')
            require(path.stat().st_size == row['bytes'] and sha(path, check) == row['sha256'], 'R22_PRIOR_EVIDENCE_BYTES')
            result[name] = dict(bytes=row['bytes'], sha256=row['sha256'])
            if path.suffix.lower() in {'.json','.jsonl','.md','.log','.txt'}:
                result[name]['text_encoding'] = evidence_text(path, check)
    return result


def _r19_anchor_binding(cfg, assertions, check):
    sealed = Path(cfg['r19_delivery'])/'sealed'
    require(sha(sealed/'artifact_manifest.json', check) == R19_MANIFEST, 'R22_R19_MANIFEST_ANCHOR')
    manifest = {safe_name(row['path']):row for row in read(sealed/'artifact_manifest.json')['files']}
    wanted = {anchor['identity'] for anchor in assertions}
    found = {identity:{} for identity in wanted}
    scanned = {}
    for name in ['science/ledger.jsonl','science/t100_certificates.jsonl','science/t100_certificate_checker.jsonl']:
        path = sealed/name
        row = manifest[name]
        require(path.stat().st_size == row['bytes'] and sha(path, check) == row['sha256'], 'R22_R19_EVIDENCE_BYTES')
        count = 0
        with path.open(encoding='utf8') as stream:
            for line in stream:
                if count % 1024 == 0:
                    check()
                value = json.loads(line)
                identity = value.get('identity')
                if identity in wanted:
                    require(name not in found[identity], 'R22_R19_ANCHOR_DUPLICATE')
                    found[identity][name] = value
                count += 1
        scanned[name] = dict(rows=count, bytes=row['bytes'], sha256=row['sha256'])
    for anchor in assertions:
        proof = found[anchor['identity']]
        require(set(proof) == set(scanned), 'R22_R19_ANCHOR_MISSING')
        ledger = proof['science/ledger.jsonl']
        cert = proof['science/t100_certificates.jsonl']
        audit = proof['science/t100_certificate_checker.jsonl']
        require(ledger == anchor['existing_R19_ledger'], 'R22_R19_LEDGER_IDENTITY')
        require(ledger['partition'] == 'T100' and audit['status'] == 'PASS', 'R22_R19_ANCHOR_ROLE')
        require(ledger['certificate_sha256'] == fingerprint(cert)
            and ledger['checker_output_sha256'] == fingerprint(audit), 'R22_R19_CERTIFICATE_BINDING')
    return dict(status='PASS',manifest_sha256=R19_MANIFEST, evidence=found, scanned=scanned,
        disposition='EXISTING_R19_ANCHORS_REPLAY_ASSERTIONS_ONLY; not R22 candidate results')


def prior_binding(cfg, check=lambda: None):
    base = Path(cfg['r21_delivery'])
    sealed = base/'sealed'
    for key, path in [('sealed',sealed/'artifact_manifest.json'),('transport',base/'transport_manifest.json'),
            ('delivery',base/'delivery_manifest.json'),('code',sealed/'frozen/consumer_code.zip'),
            ('contract',sealed/'frozen/contract.json')]:
        require(sha(path, check) == DIGESTS[key], 'R22_PRIOR_ANCHOR:'+key)
    from src.round21.export import verify_delivery
    layers = verify_delivery(base, check)
    rows = read(sealed/'frozen/consumer_code.json')
    require(len(rows) == 346, 'R22_OLD346')
    from .binding import verify_sources
    verify_sources(rows, check)
    with zipfile.ZipFile(sealed/'frozen/consumer_code.zip') as snapshot:
        safe_inventory(snapshot.infolist())
        require(set(snapshot.namelist()) == {row['relative_path'] for row in rows}, 'R22_PRIOR_SOURCE_SET')
        for row in rows:
            check()
            blob = snapshot.read(row['relative_path'])
            require(len(blob) == row['bytes'] and hashlib.sha256(blob).hexdigest() == row['sha256'], 'R22_PRIOR_SOURCE_BYTES')
    used = _used_manifest_evidence(sealed, check)
    history = []
    for item in read(sealed/'historical_attempts_index.json')['histories']:
        folder = Path(item['path'])
        for row in item.get('files', []):
            check()
            path = folder/safe_name(row['relative_path'])
            require(path.resolve().is_relative_to(folder.resolve()) and not path.is_symlink(), 'R22_HISTORY_PATH')
            require(path.stat().st_size == row['bytes'] and sha(path, check) == row['sha256'], 'R22_HISTORY_BYTES')
            if path.suffix.lower() in {'.json','.jsonl','.log','.txt','.md'}:
                evidence_text(path, check)
        history.append(dict(path=str(folder),files=len(item.get('files',[])),disposition='HISTORICAL_EVIDENCE_ONLY'))
    planning = _text_inventory(Path(cfg['r22_plan']), check)
    audit = _text_inventory(Path(cfg['r21_audit']), check)
    transport = _text_inventory(base/'transport', check)
    completion = _text_inventory(base/'completion', check)
    observation = Path(cfg.get('r21_original_work',str(ROOT/'work/round21'/base.name)))/'observations/after_all_exits_full_readback.json'
    observation_value = read(observation)
    checkpoints = read(sealed/'frozen/contract.json')['checkpoint_inputs']
    require(len(checkpoints) == 6, 'R22_PRIOR_CHECKPOINT_COUNT')
    for row in checkpoints:
        require(record(row['path'],check) == {key:row[key] for key in ['path','bytes','sha256']}, 'R22_CHECKPOINT_ANCHOR')
    csv = sealed/'science/selected_orbits.csv'
    blob = csv.read_bytes()
    require(len(blob) == 5199 and blob.count(b'\r\n') == 29 and hashlib.sha256(blob).hexdigest() == S_CSV_SHA, 'R22_S_CSV_ANCHOR')
    assertions = read(Path(cfg['r22_plan'])/'evidence/existing_anchor_diagnostics.json')['anchors']
    r19 = _r19_anchor_binding(cfg, assertions, check)
    return dict(status='PASS',layers=layers,old346_bytes_verified=True,checkpoint6=checkpoints,
        planning=planning,prior_audit=audit,used_evidence=used,historical_attempts=history,
        transport=transport,completion=completion,previous_final_observation=dict(record(observation,check),value=observation_value),
        r19_anchor_binding=r19, prior_runtime_science_disposition='HISTORICAL_EVIDENCE_ONLY; all R22 candidates fresh',
        candidate_REUSED=0)


def metadata(cfg, work=None, check=lambda: None):
    prior = prior_binding(cfg, check)
    archive_record = record(cfg['archive'], check)
    require(archive_record['sha256'] == cfg['archive_sha256'] and archive_record['bytes'] == cfg['archive_bytes'], 'R22_ARCHIVE_DIGEST')
    with zipfile.ZipFile(cfg['archive']) as archive:
        safe_inventory(archive.infolist())
        require(len(archive.infolist()) == cfg['archive_members'], 'R22_ZIP_MEMBERS')
        cat = archive.read(cfg['archive_root']+'/'+decoder.CATALOG)
        pro = archive.read(cfg['archive_root']+'/'+decoder.PROMOTION)
    require(hashlib.sha256(cat).hexdigest() == cfg['catalog_sha256'] and hashlib.sha256(pro).hexdigest() == cfg['promotion_sha256'], 'R22_CATALOG_PROMOTION')
    meta = decoder.metadata_from(json.loads(cat),json.loads(pro),check)
    center = sorted((set(meta['baseline_indices'])-{1217,1284})|{2021,2023})
    donors = sorted(set(meta['pool_indices'])-set(center))
    states = {int(index):value for index,value in meta['states'].items()}
    require(fingerprint(sorted(states[index] for index in center)) == S, 'R22_CENTER_IDENTITY')
    plan = read(Path(cfg['r22_plan'])/'evidence/strategy_summary.json')
    diagnostics = read(Path(cfg['r22_plan'])/'evidence/existing_anchor_diagnostics.json')
    require(plan['status'] == 'PLANNING_ONLY' and plan['declared_space']['declared_candidates'] == 173499, 'R22_PLAN_SCOPE')
    for key in ['new_R22_states_generated','new_R22_double_swap_metrics_evaluated','new_donor_pairs_generated','project_writes','Git_writes','native_activations']:
        require(plan['planning_execution_counts'][key] == 0, 'R22_PLAN_NOT_EXECUTION')
    assertions = diagnostics['anchors']
    require(assertions == plan['anchors'], 'R22_PLAN_DIAGNOSTICS_BINDING')
    require([(a['label'],a['remove'],a['add'],a['identity']) for a in assertions] == list(ANCHORS), 'R22_FIXED_ANCHORS')
    for anchor in assertions:
        ids = sorted((set(center)-{anchor['remove']})|{anchor['add']})
        require(ids == anchor['existing_R19_ledger']['indices'] and fingerprint(sorted(states[index] for index in ids)) == anchor['identity'], 'R22_ANCHOR_IDENTITY')
        anchor['indices'] = ids
        anchor['role'] = 'INFEASIBLE_ANCHOR_DIAGNOSTIC_ONLY'
    baseline = read(Path(cfg['r21_delivery'])/'sealed/science/baseline.json')
    meta.update(center_indices=center,donor_indices22=donors,original_constraint_reference=B0,
        search_center=S,improvement_reference=S,anchor_assertions=assertions,
        space_summary=summary(center,donors,states,check),r21_prior_binding=prior,
        original_reference_thresholds=dict(tau100=baseline['effective_grid']['T100_s']+1e-6,
            tau90=baseline['effective_grid']['T90_s']+1e-6,n=43070,k90=38763,reference_identity=B0))
    return meta


def load(cfg, work, check=lambda: None):
    lib = decoder.load(cfg,work,check)
    try:
        meta = read(Path(work)/'frozen/contract.json')['metadata']
        require(lib.baseline_indices == meta['baseline_indices'] and {str(index):state for index,state in lib.states.items()} == meta['states'], 'R22_FROZEN_POOL')
        lib.center_indices = meta['center_indices']
        lib.donor_indices22 = meta['donor_indices22']
        lib.evidence['round22_adapter'] = 'Fresh complete 2171-asset verification using immutable R16 schema decoder; no origin path I/O'
        lib.evidence['candidate_REUSED'] = 0
        return lib
    except BaseException:
        lib.close()
        raise


pool_diagnostic = decoder.pool_diagnostic
