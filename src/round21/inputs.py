"""R21 archival inputs, immutable R20 continuation and planning provenance."""
import hashlib
import json
from pathlib import Path
import zipfile
from src.round13.common import read, record, require, sha, fingerprint
from src.round13.archive import safe_inventory, safe_name
from src.round16 import inputs as decoder
from .space import B0, S, INTERMEDIATES, summary

ROOT = Path(__file__).resolve().parents[2]
DIGESTS = dict(sealed='50030f2c722ee700cd741a6c2f0d791126a93c28a8551c5ffd9b644c0b84056b',
               transport='c7f6c4529740513cde4e1b307d076e96496e3fceb5b6552780185b88779a008a',
               delivery='3aa4222ca14e0cc5c9e47a776802cfd59705ac62cec2ce451e306b60f48c0a4c',
               code='0a9264d6dcef6c64de8739cd9226528bb2054a499666b663ea4bb0b66c0f010c',
               contract='5f6c8e4c96fb3b7f9ad2313bf2b3574fcbd65b5701fe052aa368eaf8612dbc2b')


def _text_inventory(folder, check):
    result = {}
    for path in sorted(Path(folder).rglob('*')):
        if path.is_file():
            check()
            require(not path.is_symlink() and path.resolve().is_relative_to(Path(folder).resolve()), 'R21_EVIDENCE_PATH')
            result[path.relative_to(folder).as_posix()] = record(path, check)
            if path.suffix.lower() in {'.md', '.json', '.jsonl', '.log', '.txt'}:
                encoding = 'utf8'
                # Windows PowerShell historically emitted redirected raw logs as
                # UTF-16. Decode archival log text without changing its bytes.
                # Scientific JSON/JSONL and document evidence stay strict UTF-8.
                if path.suffix.lower() in {'.log', '.txt'}:
                    with path.open('rb') as stream:
                        prefix = stream.read(4)
                    if prefix.startswith((b'\xff\xfe', b'\xfe\xff')):
                        encoding = 'utf-16'
                    elif prefix.startswith(b'\xef\xbb\xbf'):
                        encoding = 'utf-8-sig'
                result[path.relative_to(folder).as_posix()]['text_encoding'] = encoding
                with path.open(encoding=encoding) as stream:
                    for line in stream:
                        check()
    return result


def prior_binding(cfg, check=lambda: None):
    base = Path(cfg['r20_delivery'])
    sealed = base/'sealed'
    for key, path in [('sealed', sealed/'artifact_manifest.json'), ('transport', base/'transport_manifest.json'),
                      ('delivery', base/'delivery_manifest.json'), ('code', sealed/'frozen/consumer_code.zip'),
                      ('contract', sealed/'frozen/contract.json')]:
        require(sha(path, check) == DIGESTS[key], 'R21_PRIOR_ANCHOR:'+key)
    from src.round20.export import verify_delivery
    layers = verify_delivery(base, check)
    rows = read(sealed/'frozen/consumer_code.json')
    require(len(rows) == 319, 'R21_OLD319')
    from .binding import verify_sources
    verify_sources(rows, check)
    used = {}
    for row in read(sealed/'artifact_manifest.json')['files']:
        name = safe_name(row['path'])
        if name.startswith(('frozen/', 'science/', 'attempt_history/')) or name in {
                'report.md', 'final_status.json', 'consumer_version_binding.json', 'historical_attempts_index.json'}:
            path = sealed/name
            if path.suffix in {'.json', '.md'}:
                path.read_text(encoding='utf8')
            used[name] = dict(bytes=row['bytes'], sha256=row['sha256'])
    wanted = {identity for label, donor, identity in INTERMEDIATES}
    intermediate_evidence = {identity: {} for identity in wanted}
    scanned = {}
    # These are real R20 FULL records, their independent audits and their exact ledger entries.
    for name in ['candidates', 'checker', 'ledger']:
        count = 0
        with (sealed/'science'/(name+'.jsonl')).open(encoding='utf8') as stream:
            for line in stream:
                if count % 1024 == 0:
                    check()
                value = json.loads(line)
                if value['identity'] in wanted:
                    require(name not in intermediate_evidence[value['identity']], 'R21_PRIOR_DUPLICATE_FULL')
                    intermediate_evidence[value['identity']][name] = value
                count += 1
        scanned[name] = count
    for identity, evidence in intermediate_evidence.items():
        require(set(evidence) == {'candidates', 'checker', 'ledger'}, 'R21_PRIOR_INTERMEDIATE_MISSING')
        report, audit, ledger = (evidence[name] for name in ['candidates', 'checker', 'ledger'])
        require(audit['status'] == 'PASS' and not audit['differences'] and ledger['partition'] == 'FULL', 'R21_PRIOR_INTERMEDIATE_NOT_VERIFIED')
        require(ledger['record_sha256'] == fingerprint(report) and ledger['checker_sha256'] == fingerprint(audit), 'R21_PRIOR_LEDGER_BINDING')
        require(report['feasibility']['feasible'] is True and report['qualified_for_round20'] is False, 'R21_PRIOR_INTERMEDIATE_ROLE')
        evidence['first_hits'] = record(sealed/'science/full_first_hits'/(identity+'.npy'), check)
    history = []
    for item in read(sealed/'historical_attempts_index.json')['histories']:
        folder = Path(item['path'])
        for row in item.get('files', []):
            check()
            path = folder/safe_name(row['relative_path'])
            require(path.resolve().is_relative_to(folder.resolve()) and not path.is_symlink(), 'R21_HISTORY_PATH')
            require(path.stat().st_size == row['bytes'] and sha(path, check) == row['sha256'], 'R21_HISTORY_BYTES')
        history.append(dict(path=str(folder), files=len(item.get('files', [])), disposition='REUSED_HISTORICAL_EVIDENCE'))
    planning = _text_inventory(Path(cfg['r21_plan']), check)
    audit = _text_inventory(Path(cfg['r20_audit']), check)
    transport = _text_inventory(base/'transport', check)
    completion = _text_inventory(base/'completion', check)
    observation = Path(cfg.get('r20_original_work', str(ROOT/'work/round20'/base.name)))/'observations/after_all_exits_full_readback.json'
    observation_value = read(observation)
    checkpoints = read(sealed/'frozen/contract.json')['checkpoint_inputs']
    require(len(checkpoints) == 6, 'R21_PRIOR_CHECKPOINT_COUNT')
    for row in checkpoints:
        require(record(row['path'], check) == row, 'R21_CHECKPOINT_ANCHOR')
    return dict(status='PASS', layers=layers, old319_bytes_verified=True, checkpoint6=checkpoints,
                planning=planning, prior_audit=audit, used_evidence=used, historical_attempts=history,
                transport=transport, completion=completion, previous_final_observation=dict(record(observation, check), value=observation_value),
                intermediate_evidence=intermediate_evidence, R20_jsonl_rows_read=scanned,
                prior_runtime_science_disposition='REUSED_EVIDENCE; no R21 candidate reuse', candidate_REUSED=0)


def metadata(cfg, work=None, check=lambda: None):
    prior = prior_binding(cfg, check)
    require(record(cfg['archive'], check)['sha256'] == cfg['archive_sha256'], 'R21_ARCHIVE_DIGEST')
    with zipfile.ZipFile(cfg['archive']) as archive:
        safe_inventory(archive.infolist())
        require(len(archive.infolist()) == cfg['archive_members'], 'R21_ZIP_MEMBERS')
        cat = archive.read(cfg['archive_root']+'/'+decoder.CATALOG)
        pro = archive.read(cfg['archive_root']+'/'+decoder.PROMOTION)
    require(hashlib.sha256(cat).hexdigest() == cfg['catalog_sha256'] and hashlib.sha256(pro).hexdigest() == cfg['promotion_sha256'], 'R21_CATALOG_PROMOTION')
    meta = decoder.metadata_from(json.loads(cat), json.loads(pro), check)
    center = sorted((set(meta['baseline_indices'])-{1217, 1284}) | {2021, 2023})
    donors = sorted(set(meta['pool_indices'])-set(center))
    states = {int(i): value for i, value in meta['states'].items()}
    plan = read(Path(cfg['r21_plan'])/'evidence/strategy_summary.json')
    assertions = plan['existing_R20_feasible_intermediates']
    require([(row['label'], row['identity']) for row in assertions] == [(label, identity) for label, donor, identity in INTERMEDIATES], 'R21_INTERMEDIATE_PLAN')
    for assertion, (label, donor, identity) in zip(assertions, INTERMEDIATES):
        ids = sorted((set(center)-{676, 2021}) | {1440, donor})
        require(assertion['indices'] == ids and fingerprint(sorted(states[i] for i in ids)) == identity, 'R21_INTERMEDIATE_IDENTITY')
        require(assertion['R20_original_ledger'] == prior['intermediate_evidence'][identity]['ledger'], 'R21_PLAN_ORIGINAL_LEDGER')
    require(plan['declared_universe']['declared_unique_count'] == 111306 and all(value == 0 for value in plan['planning_execution_counts'].values()), 'R21_PLAN_NOT_EXECUTION')
    baseline = read(Path(cfg['r20_delivery'])/'sealed/science/baseline.json')
    meta.update(center_indices=center, donor_indices21=donors, original_constraint_reference=B0,
                search_center=S, improvement_reference=S, intermediate_assertions=assertions,
                space_summary=summary(center, donors, states, check), r20_prior_binding=prior,
                original_reference_thresholds=dict(tau100=baseline['effective_grid']['T100_s']+1e-6,
                                                   tau90=baseline['effective_grid']['T90_s']+1e-6,
                                                   n=43070, k90=38763, reference_identity=B0))
    return meta


def load(cfg, work, check=lambda: None):
    lib = decoder.load(cfg, work, check)
    try:
        meta = read(Path(work)/'frozen/contract.json')['metadata']
        require(lib.baseline_indices == meta['baseline_indices'] and {str(i): state for i, state in lib.states.items()} == meta['states'], 'R21_FROZEN_POOL')
        lib.center_indices = meta['center_indices']
        lib.donor_indices21 = meta['donor_indices21']
        lib.evidence['round21_adapter'] = 'Fresh full catalog verification via immutable R16 schema decoder'
        lib.evidence['candidate_REUSED'] = 0
        return lib
    except BaseException:
        lib.close()
        raise


pool_diagnostic = decoder.pool_diagnostic
