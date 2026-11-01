"""Early evidence readback and four existing-asset probes, no new candidates."""
import argparse
import datetime
import json
from pathlib import Path
import time
import numpy as np
from src.round13.common import read,write,sha,record,require,fingerprint
from .binding import ROOT,verify_runtime,artifacts
from .control import Lifecycle
from .guard import install

def main(mode):
    p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--work',required=True)
    args=p.parse_args();work=Path(args.work).resolve()
    install(work,work/'preparation'/(mode+'_guard.jsonl'),role='preparation')
    life=Lifecycle(work/'lifecycle.json');check=lambda:life.check(True)
    cfg=read(ROOT/'configs/round24.json')
    start_u,start_m,start_c=time.time(),time.monotonic(),time.process_time()
    if mode=='initialize':
        from .inputs import preserve_prior_sources,prior_binding
        prior=prior_binding(cfg,check,work)
        old=preserve_prior_sources(check=check)
        require(sha(Path(cfg['r22_delivery'])/'sealed/frozen/contract.json',check)=='2f98e4bea0a3c6e17bc0c9df86e9a0bfafcac22de0c9fdefa5a353b3b625a2b7','R24_NEW_R22_CONTRACT')
        observation=ROOT/'work/round22/20261101T074830_offline/observations/after_all_exits_full_readback.json'
        require(sha(observation,check)=='00370dbd6fe39003325fcef1d6f136c7309fbec31de1861b37805a59139291c8','R24_R22_AFTER_EXITS_SHA')
        write(work/'starting_prior_sources.json',old)
        verify_runtime(work,check)
        prior_work=Path(cfg['r23_work'])
        write(work/'starting_r23_work_manifest.json',dict(root=str(prior_work),files=artifacts(prior_work,check)))
        write(work/'preparation/prerequisite_verification.json',prior)
        # Exact longest historical fixture source basename + actual deepest isolated destination.
        base=work/'attempts/20261101T000000_123456_legacy/output/old202/regression/repo/tests'
        paths=[str(base/p.relative_to(ROOT/'tests')) for p in (ROOT/'tests').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
        longest=max(paths,key=len)
        require(len(longest)<260,'R24_HISTORICAL_PATH_TOO_LONG')
        write(work/'preparation/deepest_fixture_path.json',dict(status='PASS',longest_destination=longest,
            characters=len(longest),max_path_exclusive=260,source_fixture_count=len(paths)))
        result=dict(status='PASS',old_consumers=400,checkpoints=6,r22_three_layers_and_actual_exits=True,r23_preserved_files=len(read(work/'starting_r23_work_manifest.json')['files']))
    elif mode=='pretests':
        import zipfile
        from .binding import manifest,source_files
        from .worker import tests_job
        out=work/('precheck_'+str(time.time_ns()));out.mkdir()
        rows=manifest(source_files(work),check)
        write(out/'consumer_code.json',rows)
        with zipfile.ZipFile(out/'consumer_code.zip','w',zipfile.ZIP_DEFLATED) as z:
            for row in rows:z.write(row['path'],row['relative_path'])
        result=tests_job(work,out)
    else:
        from .resolver import FrozenArchive
        from .asset_decoder import CATALOG,MATRIX,BASE,PROTOCOL_SHA,validate_npz_row,validate_state
        from src.round14.inputs import validate_entry,validate_intervals
        from src.round13.inputs import Inputs
        arc=FrozenArchive(cfg,work/'preparation/four_assets',check)
        results=[]
        try:
            catalog=arc.json(CATALOG);inputs=Inputs(arc,cfg)
            matrix=np.load(arc.path(MATRIX),mmap_mode='r',allow_pickle=False)
            for index in [0,60,1085,2170]:
                u,m,c=time.time(),time.monotonic(),time.process_time()
                asset=catalog['assets'][index];validate_state(asset['row']);arc.progress.asset=index
                for kind,filename in [('global','hits.npz'),('regional','intervals.json')]:
                    folder=BASE+'runs/access_library/'+kind+'/'+asset[kind+'_key']
                    entry=arc.json(folder+'/entry.json')
                    validate_entry(asset,entry,catalog[kind+'_context'],asset[kind+'_key'],PROTOCOL_SHA)
                    path=arc.path(folder+'/'+filename)
                    require(arc.used[folder+'/'+filename]['sha256']==entry['data_sha256']==asset[kind+'_data_sha256'],'R24_PREFLIGHT_DATA_SHA')
                    if kind=='global':validate_npz_row(path,matrix[index],43424,604800.)
                    else:validate_intervals(arc.json(folder+'/'+filename),inputs.targets,604800.)
                results.append(dict(index=index,status='PASS',utc_start=u,utc_end=time.time(),
                    monotonic_wall_s=time.monotonic()-m,cpu_s=time.process_time()-c,remaining_compute_s=life.remaining(True)))
            del matrix
            preserved=arc.preserve()
        finally:arc.close()
        result=dict(status='PASS',fixed_existing_asset_probes=results,used_members=preserved,
            complete_2171_input_gate=False,new_candidate_evaluations=0)
    result.update(start_utc_epoch=start_u,end_utc_epoch=time.time(),utc_wall_s=time.time()-start_u,
        monotonic_wall_s=time.monotonic()-start_m,cpu_s=time.process_time()-start_c,remaining_compute_s=life.remaining(True),
        new_scientific_candidates=0)
    write(work/'preparation'/(mode+'_result.json'),result)
    print(json.dumps({k:v for k,v in result.items() if k not in {'used_members'}},ensure_ascii=False))
    return 0
