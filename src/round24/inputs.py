"""Bind the unchanged R22 science, authorized complete rerun, and raw assets."""
import hashlib
import json
from pathlib import Path
import zipfile

from src.round13.common import read,record,require,sha,fingerprint
from src.round13.archive import safe_inventory,safe_name
from . import asset_decoder as decoder
from src.round22.inputs import evidence_text
from .space import B0,S,ANCHORS,planned_summary

ROOT=Path(__file__).resolve().parents[2]
ORIGINAL_SEAL=ROOT/'work/round22/20261031T074900_offline/sealed_1793435727870243100'
ORIGINAL_MANIFEST='90ef50c2c05f715e0c97dbd71366b4658601e2666055eeefb00360ee66f9dfab'
ORIGINAL_ZIP='fbce7175c778d27dc511a9905333ff657889ed2f2e78f0793e569aa755cf30d5'
ORIGINAL_CONTRACT='57a2cbe7e8006d645e3efdb05f035f9fda9177f69091707ef306ecb5814f57b7'
ORIGINAL_SOURCE_IDENTITY='ba4320a840bf5fd3f6cf46c8c217554204e306970828e69e6246f25503eaaf49'
S_CSV_SHA='7b9480f8a1aef119b73cd2e1732ce45845b1634886492a8c5857636ad8654365'
ANCHOR_EXPECTED=(
    dict(T90_s=284546.9452871524,T100_s=595089.2108747589,Tavg_s=9251.17226018343,
         Tmax_s=130560.50163224502,gap_count=172,c90=38720,deficit=43,capable_donors=2137),
    dict(T90_s=285492.0745635856,T100_s=595089.2108747589,Tavg_s=9416.175186922259,
         Tmax_s=130560.50163224502,gap_count=169,c90=38672,deficit=91,capable_donors=2125),
    dict(T90_s=285200.6890520235,T100_s=595089.2108747589,Tavg_s=9415.614151292679,
         Tmax_s=130560.50163224502,gap_count=169,c90=38682,deficit=81,capable_donors=2129),
)


def _records(path,check):
    with Path(path).open(encoding='utf8') as stream:
        for ordinal,line in enumerate(stream):
            if ordinal%1024==0:check()
            yield json.loads(line)


def preserve_prior_sources(sealed=None,check=lambda:None):
    from src.round23.inputs import preserve_prior_sources as preserve373
    old=preserve373(check=check)
    prior=ROOT/'work/round23/20261101T082559_offline'
    require(sha(prior/'frozen/consumer_code.zip',check)=='58282d008bbb7a9555fdd4c5c3abccfd42e9aa701f07f47e7861601689974260','R24_OLD400_ZIP')
    require(sha(prior/'frozen/contract.json',check)=='bb0223491b73b18d40b6adecbd04df9f547ccc154bb0e0b2a195d339a335e33f','R24_OLD400_CONTRACT')
    require(sha(prior/'execution_completion.json',check)=='c1ff9404d05bd1f5c8eca3e6900e109a722c168b29fb69816c616f803fbe962a','R24_R23_FAILURE_CHANGED')
    rows=read(prior/'frozen/consumer_code.json')
    require(len(rows)==400 and fingerprint(rows)=='4db7b29cf96b28d2991658a499d8f53fce02a8fdc6cb77ee65e8cb9dd85eb24b','R24_OLD400_IDENTITY')
    for row in rows:
        require(record(row['path'],check)=={k:row[k] for k in ['path','bytes','sha256']},'R24_OLD400_CHANGED')
    with zipfile.ZipFile(prior/'frozen/consumer_code.zip') as z:
        safe_inventory(z.infolist())
        require(set(z.namelist())=={r['relative_path'] for r in rows},'R24_OLD400_ZIP_SET')
        for row in rows:
            blob=z.read(row['relative_path']);require(len(blob)==row['bytes'] and hashlib.sha256(blob).hexdigest()==row['sha256'],'R24_OLD400_ZIP_BYTES')
    return dict(status='PASS',old_consumers=400,checkpoint_count=6,source_rows=rows,checkpoints=old['checkpoints'],old373=old)


def _anchor_provenance(sealed,check):
    wanted={identity for _,_,_,identity in ANCHORS};found={identity:{} for identity in wanted};scanned={}
    for name in ('ledger','t90_certificates','t90_certificate_checker'):
        path=Path(sealed)/'science'/(name+'.jsonl');count=0
        for value in _records(path,check):
            count+=1
            if value.get('identity') in wanted:
                require(name not in found[value['identity']],'R24_DUPLICATE_EXISTING_ANCHOR')
                found[value['identity']][name]=value
        scanned[name]=dict(record(path,check),rows=count)
    for _,remove,add,identity in ANCHORS:
        values=found[identity]
        require(set(values)=={'ledger','t90_certificates','t90_certificate_checker'},'R24_EXISTING_R22_ANCHOR_MISSING')
        ledger,cert,audit=[values[n] for n in ('ledger','t90_certificates','t90_certificate_checker')]
        require(ledger['partition']=='T90' and cert['partition']=='T90' and audit['status']=='PASS'
            and audit['differences']==[] and ledger['remove']==list(remove) and ledger['add']==list(add),
            'R24_EXISTING_ANCHOR_OPERATION')
        require(ledger['record_sha256']==fingerprint(cert) and ledger['checker_sha256']==fingerprint(audit)
            and audit['certificate_sha256']==fingerprint(cert),'R24_EXISTING_ANCHOR_HASH')
    return dict(status='PASS',scanned=scanned,anchors=found,
        disposition='Existing R22 T90 certificate identities only; all R24 candidates are freshly evaluated')


def prior_binding(cfg,check=lambda:None,work=None):
    original=Path(cfg.get('r22_original_seal',ORIGINAL_SEAL)).resolve()
    require(original==ORIGINAL_SEAL.resolve(),'R24_ORIGINAL_R22_SEAL_PATH')
    for relative,digest in [('artifact_manifest.json',ORIGINAL_MANIFEST),('frozen/consumer_code.zip',ORIGINAL_ZIP),
            ('frozen/contract.json',ORIGINAL_CONTRACT)]:
        require(sha(original/relative,check)==digest,'R24_ORIGINAL_R22_ANCHOR:'+relative)
    from src.round22.seal import independent_readback
    original_audit=independent_readback(original,check)
    require(original_audit['status']=='PASS' and original_audit['exit_code']==0,'R24_ORIGINAL_SCIENCE_NOT_PASS')
    from src.round23.inputs import preserve_prior_sources as preserve373
    preserved=preserve373(original,check)
    rows=preserved['source_rows']
    require(read(original/'frozen/contract.json')['source_manifest_identity']==ORIGINAL_SOURCE_IDENTITY,'R24_SOURCE_CONTRACT_IDENTITY')
    with zipfile.ZipFile(original/'frozen/consumer_code.zip') as snapshot:
        safe_inventory(snapshot.infolist())
        require(set(snapshot.namelist())=={r['relative_path'] for r in rows},'R24_OLD373_ZIP_SET')
        for row in rows:
            check();blob=snapshot.read(row['relative_path'])
            require(len(blob)==row['bytes'] and hashlib.sha256(blob).hexdigest()==row['sha256'],'R24_OLD373_ZIP_BYTES')
    old_completion=read(original.parent/'execution_completion.json')
    require(old_completion['status']=='BLOCKED' and old_completion['exit_code']==2
        and old_completion['actual_export_launcher_python_exit_code'] is None
        and old_completion['actual_finalizer_python_exit_code'] is None,'R24_ORIGINAL_BLOCKED_RECORD_CHANGED')
    work=Path(work or ROOT/cfg['prepared_work'])
    prerequisite=read(work/'r22_prerequisite.json')
    require(prerequisite['status']=='PASS' and prerequisite['old373_preserved']==373
        and prerequisite['checkpoint6_preserved']==6 and prerequisite['r22_rerun_actual_exit_codes_all_zero'] is True,
        'R24_R22_PREREQUISITE')
    rerun=Path(cfg['r22_delivery']).resolve()
    require(rerun==Path(prerequisite['r22_rerun_delivery']).resolve(),'R24_RERUN_PATH_BINDING')
    for name,key in [('sealed/artifact_manifest.json','r22_rerun_sealed_manifest_sha256'),
            ('transport_manifest.json','r22_rerun_transport_manifest_sha256'),('delivery_manifest.json','r22_rerun_delivery_manifest_sha256')]:
        require(sha(rerun/name,check)==prerequisite[key],'R24_RERUN_MANIFEST_ANCHOR:'+name)
    from src.round22.export import verify_delivery
    rerun_audit=verify_delivery(rerun,check)
    require(rerun_audit['status']=='PASS' and read(rerun/'sealed/final_status.json')['status']=='PASS','R24_RERUN_NOT_PASS')
    require(read(rerun/'sealed/frozen/consumer_code.json')==rows,'R24_RERUN373_VERSION_MISMATCH')
    observation_path=Path(prerequisite['r22_after_all_exits_observation_path'])
    require(sha(observation_path,check)==prerequisite['r22_after_all_exits_observation_sha256'],'R24_R22_FINAL_OBSERVATION_SHA')
    observation=read(observation_path)
    require(observation['status']=='PASS' and observation['all_actual_outer_exits_observed_before_readback'] is True,
        'R24_R22_FINAL_OBSERVATION')
    for role in ('research','export','finalizer'):
        actual=observation['actual_outer_exits'][role]
        require(type(actual['python_exit_code']) is int and type(actual['actual_shell_exit_code']) is int
            and actual['python_exit_code']==actual['actual_shell_exit_code']==0,'R24_R22_ACTUAL_EXITS')
    require(read(rerun/'completion/export_command_result.json')['export_process_exit_code']==0,'R24_R22_DIRECT_EXPORT_EXIT')
    for key,name in [('delivery_manifest_sha256','delivery_manifest.json'),('delivery_receipt_sha256','delivery_receipt.json'),
            ('transport_manifest_sha256','transport_manifest.json'),('transfer_receipt_sha256','transfer_receipt.json'),
            ('sealed_manifest_sha256','sealed/artifact_manifest.json')]:
        require(observation[key]==sha(rerun/name,check),'R24_FINAL_OBSERVATION_LAYER_BINDING:'+key)
    require(observation['finalizer_actual_outer_exit_observed_elapsed_s']<=observation['lifecycle_elapsed_s'],
        'R24_OBSERVATION_MUST_FOLLOW_FINALIZER_EXIT')
    return dict(status='PASS',original_r22_scientific_seal=record(original/'artifact_manifest.json',check),
        original_r22_scientific_readback=original_audit,original_r22_overall_completion=record(original.parent/'execution_completion.json',check),
        original_r22_overall_status='BLOCKED/2; preserved',original_r22_code_zip=record(original/'frozen/consumer_code.zip',check),
        original_r22_contract=record(original/'frozen/contract.json',check),old373_and_checkpoint6=preserved,
        rerun_three_layer_audit=rerun_audit,rerun_delivery=str(rerun),
        rerun_observation=dict(record(observation_path,check),value=observation),prerequisite=record(work/'r22_prerequisite.json',check),
        authorization=prerequisite['authorization'],anchor_provenance=_anchor_provenance(original,check),
        candidate_results_reused=False)


def metadata(cfg,work=None,check=lambda:None):
    prior=prior_binding(cfg,check,work)
    prior['R23_old400_preservation']=preserve_prior_sources(check=check)
    archive=record(cfg['archive'],check)
    require(archive['sha256']==cfg['archive_sha256'] and archive['bytes']==cfg['archive_bytes'],'R24_ARCHIVE_DIGEST')
    with zipfile.ZipFile(cfg['archive']) as source:
        safe_inventory(source.infolist())
        require(len(source.infolist())==cfg['archive_members'],'R24_ARCHIVE_MEMBERS')
        catalog=source.read(cfg['archive_root']+'/'+decoder.CATALOG)
        promotion=source.read(cfg['archive_root']+'/'+decoder.PROMOTION)
    require(hashlib.sha256(catalog).hexdigest()==cfg['catalog_sha256']
        and hashlib.sha256(promotion).hexdigest()==cfg['promotion_sha256'],'R24_CATALOG_PROMOTION_SHA')
    meta=decoder.metadata_from(json.loads(catalog),json.loads(promotion),check)
    center=sorted((set(meta['baseline_indices'])-{1217,1284})|{2021,2023})
    donors=sorted(set(meta['pool_indices'])-set(center));states={int(i):v for i,v in meta['states'].items()}
    require(fingerprint(sorted(states[i] for i in center))==S,'R24_CENTER_IDENTITY')
    anchors=[]
    for (label,remove,add,identity),expected in zip(ANCHORS,ANCHOR_EXPECTED):
        ids=sorted((set(center)-set(remove))|set(add))
        require(fingerprint(sorted(states[i] for i in ids))==identity,'R24_EXISTING_ANCHOR_IDENTITY')
        existing=prior['anchor_provenance']['anchors'][identity]
        require(existing['ledger']['indices']==ids,'R24_EXISTING_ANCHOR_INDEX_BINDING')
        anchors.append(dict(label=label,remove=list(remove),add=list(add),identity=identity,indices=ids,
            role='INFEASIBLE_ANCHOR_DIAGNOSTIC_ONLY',replay_expected=expected,existing_R22_ledger=existing['ledger'],
            existing_R22_certificate_sha256=fingerprint(existing['t90_certificates']),
            existing_R22_checker_sha256=fingerprint(existing['t90_certificate_checker'])))
    baseline=read(Path(cfg['r22_delivery'])/'sealed/science/baseline.json')
    meta.update(center_indices=center,donor_indices23=donors,original_constraint_reference=B0,
        search_center=S,improvement_reference=S,anchor_assertions=anchors,
        space_summary=planned_summary(center),r22_prior_binding=prior,
        original_reference_thresholds=dict(tau100=baseline['effective_grid']['T100_s']+1e-6,
            tau90=baseline['effective_grid']['T90_s']+1e-6,n=43070,k90=38763,reference_identity=B0))
    return meta


def load(cfg,work,check=lambda:None):
    lib=decoder.load(cfg,work,check)
    try:
        meta=read(Path(work)/'frozen/contract.json')['metadata']
        require(lib.baseline_indices==meta['baseline_indices']
            and {str(i):v for i,v in lib.states.items()}==meta['states'],'R24_FROZEN_POOL')
        lib.center_indices=meta['center_indices'];lib.donor_indices23=meta['donor_indices23']
        lib.evidence['round24_adapter']='R24 equivalent R16 full validation with fresh cache hashes, per-phase progress and unchanged schema/numerical checks'
        lib.evidence['candidate_REUSED']=0
        lib.evidence['old373_checkpoint6_preservation']=preserve_prior_sources(check=check)
        return lib
    except BaseException:
        lib.close();raise


pool_diagnostic=decoder.pool_diagnostic
