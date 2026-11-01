"""R20 immutable history and full original-asset input binding; no origin I/O."""
import hashlib
import json
from pathlib import Path
import zipfile
from src.round13.common import read,write,record,require,sha,fingerprint
from src.round13.archive import safe_inventory,safe_name
from src.round16 import inputs as decoder
from .space import B0,S,ANCHORS,summary

ROOT=Path(__file__).resolve().parents[2]
DIGESTS=dict(sealed='a100ed04e0182f7844d2566340522609c93a0f529109e1a42d8b7e3ab4a2d515',
    transport='542cc72b5dc22d8a013082d967829fa6142da6b0ab679bf53545768bdc341bff',
    delivery='08233d0684e56e91440d143b529d3e3956dbd6991c30714d34ac9bdeb6b46014',
    code='21c658774d956499d1bf68c8ef655ac1bf09664efe8f729cc3d36390ee573501',
    contract='1d4bd672bc0086c54b65feb54f6cd0158ea16293d1db84f2c61958339be8297c')

def prior_binding(cfg,check=lambda:None):
    base=Path(cfg['r19_delivery']); sealed=base/'sealed'
    for key,path in [('sealed',sealed/'artifact_manifest.json'),('transport',base/'transport_manifest.json'),
                     ('delivery',base/'delivery_manifest.json'),('code',sealed/'frozen/consumer_code.zip'),
                     ('contract',sealed/'frozen/contract.json')]:
        require(sha(path,check)==DIGESTS[key],'R20_PRIOR_ANCHOR:'+key)
    # Read-only archival verifier, never the R19 science entry or evaluator.
    from src.round19.export import verify_delivery
    layers=verify_delivery(base,check)
    rows=read(sealed/'frozen/consumer_code.json'); require(len(rows)==292,'R20_OLD292')
    from .binding import verify_sources
    verify_sources(rows,check)
    used={}
    for row in read(sealed/'artifact_manifest.json')['files']:
        name=safe_name(row['path'])
        if (name.startswith(('frozen/','science/','attempt_history/')) or name in
                {'report.md','final_status.json','consumer_version_binding.json','historical_attempts_index.json'}):
            p=sealed/name
            if p.suffix in {'.json','.md'}:p.read_text(encoding='utf8')
            used[name]=dict(bytes=row['bytes'],sha256=row['sha256'])
    # Historical failed attempts remain bound to original work, with full logs.
    history=[]
    for item in read(sealed/'historical_attempts_index.json')['histories']:
        folder=Path(item['path'])
        for row in item.get('files',[]):
            check();p=folder/safe_name(row['relative_path'])
            require(p.resolve().is_relative_to(folder.resolve()) and not p.is_symlink(), 'R20_HISTORY_PATH')
            require(p.stat().st_size==row['bytes'] and sha(p,check)==row['sha256'],'R20_HISTORY_BYTES')
        history.append(dict(path=str(folder),files=len(item.get('files',[])),disposition='REUSED_HISTORICAL_EVIDENCE'))
    plan=Path(cfg['r20_plan']); planning={}
    for p in sorted(plan.rglob('*')):
        if p.is_file():
            check();planning[p.relative_to(plan).as_posix()]=record(p,check)
            if p.suffix in {'.md','.json','.jsonl'}:p.read_text(encoding='utf8')
    audit=Path(cfg['r19_audit']);audit_rows=[]
    for p in sorted(audit.rglob('*')):
        if p.is_file():audit_rows.append(record(p,check))
    checkpoints=read(plan/'evidence/r19_postcommit_immutable_recheck.json')['checkpoint6']
    for row in checkpoints:require(record(row['path'],check)==row,'R20_CHECKPOINT_ANCHOR')
    return dict(status='PASS',layers=layers,old292_bytes_verified=True,checkpoint6=checkpoints,
        planning=planning,prior_audit=audit_rows,used_evidence=used,historical_attempts=history,
        prior_runtime_science_disposition='REUSED; not new R20 tests or candidates',candidate_REUSED=0)

def metadata(cfg,work=None,check=lambda:None):
    prior=prior_binding(cfg,check)
    require(record(cfg['archive'],check)['sha256']==cfg['archive_sha256'],'R20_ARCHIVE_DIGEST')
    with zipfile.ZipFile(cfg['archive']) as z:
        safe_inventory(z.infolist());require(len(z.infolist())==cfg['archive_members'],'R20_ZIP_MEMBERS')
        cat=z.read(cfg['archive_root']+'/'+decoder.CATALOG);pro=z.read(cfg['archive_root']+'/'+decoder.PROMOTION)
    require(hashlib.sha256(cat).hexdigest()==cfg['catalog_sha256'] and hashlib.sha256(pro).hexdigest()==cfg['promotion_sha256'],'R20_CATALOG_PROMOTION')
    meta=decoder.metadata_from(json.loads(cat),json.loads(pro),check)
    center=sorted((set(meta['baseline_indices'])-{1217,1284})|{2021,2023});donors=sorted(set(meta['pool_indices'])-set(center))
    states={int(i):s for i,s in meta['states'].items()}
    plan=read(Path(cfg['r20_plan'])/'evidence/strategy_summary.json')
    require([(a['anchor_id'],a['remove'],a['add']) for a in plan['anchors']]==list(ANCHORS),'R20_ANCHOR_OPERATION')
    for a in plan['anchors']:
        ids=sorted((set(center)-{a['remove']})|{a['add']})
        require(fingerprint(sorted(states[i] for i in ids))==a['identity'],'R20_ANCHOR_IDENTITY')
    meta.update(center_indices=center,donor_indices20=donors,original_constraint_reference=B0,
        search_center=S,improvement_reference=S,space_summary=summary(center,donors,states,check),
        r19_prior_binding=prior,anchor_assertions=plan['anchors'])
    b=read(Path(cfg['r19_delivery'])/'sealed/science/baseline.json')
    meta['original_reference_thresholds']=dict(tau100=b['effective_grid']['T100_s']+1e-6,
        tau90=b['effective_grid']['T90_s']+1e-6,n=43070,k90=38763,reference_identity=B0)
    return meta

def load(cfg,work,check=lambda:None):
    lib=decoder.load(cfg,work,check)
    try:
        meta=read(Path(work)/'frozen/contract.json')['metadata']
        require(lib.baseline_indices==meta['baseline_indices'] and {str(i):s for i,s in lib.states.items()}==meta['states'],'R20_FROZEN_POOL')
        lib.center_indices=meta['center_indices'];lib.donor_indices20=meta['donor_indices20']
        lib.evidence['round20_adapter']='Fresh full catalog verification via immutable R16 schema decoder'
        lib.evidence['candidate_REUSED']=0
        return lib
    except BaseException:lib.close();raise

pool_diagnostic=decoder.pool_diagnostic
