"""R28 targeted Store counterexamples, all FIXTURE_ONLY."""
import copy
import json
import shutil
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from incremental_store import Store, StoreError, StoreCorruption, StoreConflict, encode


def specs(n=8):
    return [dict(point_id=f'P{i//4}',sat_id=f'Sat{i%4+1:03}',window_epsec=[0,100],
                 sensor_object_path=f'Satellite/Sat{i%4+1:03}/Sensor/Camera',protocol_sha256='fixture_protocol',
                 source_sha256='fixture_source',point_table_sha256='fixture_points') for i in range(n)]


def values(store, spec, state='COMPLETED_WITH_ACCESS'):
    qid=store.query_id(spec)
    events=[] if state=='COMPLETED_NO_ACCESS' else [dict(**{k:v for k,v in spec.items() if k!='window_epsec'},
            query_id=qid,sensor_id='Camera',start_epsec=1.123456789012345,stop_epsec=2.123456789012345)]
    return events,dict(point_id=spec['point_id'],sat_id=spec['sat_id'],query_id=qid,
                      computation_status=state,raw_interval_count=len(events),query_window_epsec=[0,100])


def run(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);results=[]
    def check(name, fn):
        start=time.perf_counter()
        try: fn()
        except Exception as exc:results.append(dict(name=name,status='FAIL',error=repr(exc),wall_s=time.perf_counter()-start))
        else:results.append(dict(name=name,status='PASS',wall_s=time.perf_counter()-start))
        print(name,results[-1]['status'],flush=True)
    def require(condition):
        if not condition:raise AssertionError('condition false')
    def rejects(fn, expected=StoreError):
        try:fn()
        except expected:return
        raise AssertionError('expected '+expected.__name__)
    ss=specs();base=Store(out/'base',{'scope':'FIXTURE_ONLY'},ss,batch_size=4)
    vv=[values(base,s) for s in ss]
    def buffering():
        base.commit(ss[0],*vv[0]);require(not base.committed(ss[0]));require(len(base.pending)==1)
        require(base.snapshot()['query_statuses'][0]['computation_status']=='NOT_RUN')
        require(len(Store(out/'base').records)==0)
    check('unpublished_tail_is_not_success_and_reopen_ignores_it',buffering)
    def commit_batch():
        for s,v in zip(ss[1:4],vv[1:4]):base.commit(s,*v)
        require(len(base.records)==4 and len(base.receipts)==1 and not base.pending)
        require(base.metrics()['actual_store_file_count']==5)
    check('full_batch_atomic_three_files',commit_batch)
    check('duplicate_committed_is_idempotent',lambda:(base.commit(ss[0],*vv[0]),require(base.idempotent_commits==1),require(len(base.records)==4)))
    bad=copy.deepcopy(vv[0]);bad[1]['elapsed_s']=99
    check('conflicting_committed_result_rejected',lambda:rejects(lambda:base.commit(ss[0],*bad),StoreConflict))
    def tail():
        base.commit(ss[4],*vv[4]);base.flush();require(len(base.records)==5 and base.receipts[-1]['batch_query_count']==1)
    check('short_tail_explicit_flush',tail)
    def immutable():
        snapshot=base.snapshot();snapshot['events'][0]['start_epsec']=99
        require(base.records[base.query_id(ss[0])]['events'][0]['start_epsec']==vv[0][0][0]['start_epsec'])
    check('snapshot_isolation_and_double_precision_roundtrip',immutable)
    def bytes_intact():
        before={p.relative_to(base.folder).as_posix():p.read_bytes() for p in base.folder.rglob('*') if p.is_file()}
        reopened=Store(base.folder)
        for s,v in zip(ss[:5],vv[:5]):reopened.commit(s,*v)
        after={p.relative_to(base.folder).as_posix():p.read_bytes() for p in base.folder.rglob('*') if p.is_file()}
        require(before==after and len(reopened.records)==5 and reopened.idempotent_commits==5)
    check('recovery_skips_duplicate_and_preserves_original_bytes',bytes_intact)
    def tamper_case(name, op):
        folder=out/name;shutil.copytree(base.folder,folder);op(folder)
        rejects(lambda:Store(folder))
    check('missing_committed_event_block_rejected',lambda:tamper_case('missing',lambda d:next((d/'events').glob('*.json')).unlink()))
    check('corrupt_committed_status_block_rejected',lambda:tamper_case('corrupt',lambda d:next((d/'statuses').glob('*.json')).write_bytes(b'{bad')))
    def duplicate_receipt(d):
        receipt=next((d/'batches').glob('*.json'));shutil.copy2(receipt,d/'batches'/'99999999-duplicate.json')
    check('duplicate_receipt_rejected',lambda:tamper_case('duplicate_receipt',duplicate_receipt))
    def boolean_receipt(d):
        p=next((d/'batches').glob('*.json'));data=json.loads(p.read_bytes());data['batch_query_count']=True;p.write_bytes(encode(data))
    check('boolean_receipt_count_rejected',lambda:tamper_case('boolean_receipt',boolean_receipt))
    class CrashStore(Store):
        def _publish(self,path,data):
            if path.parent.name=='batches':raise RuntimeError('SIMULATED_RECEIPT_CUT')
            return super()._publish(path,data)
    def unpublished_blocks():
        crashed=CrashStore(out/'orphan',{'scope':'FIXTURE_ONLY'},ss,batch_size=4)
        for s in ss[:3]:crashed.commit(s,*values(crashed,s))
        rejects(lambda:crashed.commit(ss[3],*values(crashed,ss[3])),RuntimeError)
        reopened=Store(crashed.folder);require(not reopened.records and len(reopened.metrics()['incomplete_blocks'])==2)
        for s in ss[:4]:reopened.commit(s,*values(reopened,s))
        require(len(reopened.records)==4 and not reopened.metrics()['incomplete_blocks'])
    check('written_blocks_without_receipt_not_success_and_recoverable',unpublished_blocks)
    def partial():
        st=Store(out/'partial',{'scope':'FIXTURE_ONLY'},ss,batch_size=4)
        st.commit(ss[0],*values(st,ss[0]));st.commit(ss[1],*values(st,ss[1],'COMPUTATION_ERROR'))
        st.commit(ss[2],*values(st,ss[2],'COMPLETED_NO_ACCESS'));st.flush()
        snap=Store(st.folder).snapshot();states=[x['computation_status'] for x in snap['query_statuses'][:4]]
        require(states==['COMPLETED_WITH_ACCESS','COMPUTATION_ERROR','COMPLETED_NO_ACCESS','NOT_RUN'])
        require(len(snap['events'])==2 and st.metrics()['completed_query_count']==2 and st.metrics()['failed_query_count']==1)
    check('partial_success_failed_events_no_access_not_run_distinct',partial)
    def mutation(name, mutate):
        st=Store(out/name,{'scope':'FIXTURE_ONLY'},ss,batch_size=4);e,s=values(st,ss[0]);mutate(e,s)
        rejects(lambda:st.commit(ss[0],e,s))
    check('bool_event_endpoint_rejected',lambda:mutation('bool_endpoint',lambda e,s:e[0].update(start_epsec=True)))
    check('nan_event_endpoint_rejected',lambda:mutation('nan_endpoint',lambda e,s:e[0].update(start_epsec=float('nan'))))
    check('reversed_interval_rejected',lambda:mutation('reverse',lambda e,s:e[0].update(start_epsec=3)))
    check('bool_status_count_rejected',lambda:mutation('bool_count',lambda e,s:s.update(raw_interval_count=True)))
    check('bool_status_window_rejected',lambda:mutation('bool_window',lambda e,s:s.update(query_window_epsec=[False,100])))
    check('event_source_mismatch_rejected',lambda:mutation('source_mismatch',lambda e,s:e[0].update(source_sha256='wrong')))
    check('status_camera_mismatch_rejected',lambda:mutation('status_camera',lambda e,s:s.update(sensor_object_path='WRONG')))
    check('status_source_mismatch_rejected',lambda:mutation('status_source',lambda e,s:s.update(source_sha256='WRONG')))
    check('event_missing_query_id_rejected',lambda:mutation('event_no_qid',lambda e,s:e[0].pop('query_id')))
    check('event_camera_id_mismatch_rejected',lambda:mutation('event_camera',lambda e,s:e[0].update(sensor_id='WRONG')))
    check('event_bool_window_rejected',lambda:mutation('event_bool_window',lambda e,s:e[0].update(query_window_epsec=[False,100])))
    check('event_solver_mismatch_rejected',lambda:mutation('event_solver',lambda e,s:s.update(solver_sha256='DIFFERENT')))
    check('event_unknown_identity_rejected',lambda:mutation('unknown_event',lambda e,s:e[0].update(point_id='UNKNOWN')))
    check('duplicate_event_rejected',lambda:mutation('duplicate_event',lambda e,s:(e.append(copy.deepcopy(e[0])),s.update(raw_interval_count=2))))
    check('unknown_query_rejected',lambda:rejects(lambda:base.commit('UNKNOWN',[],{})))
    check('duplicate_plan_rejected',lambda:rejects(lambda:Store(out/'duplicate_plan',{},[ss[0],ss[0]],batch_size=4)))
    check('batch_size_frozen_on_reopen',lambda:rejects(lambda:Store(base.folder,batch_size=8)))
    def pending_duplicate():
        st=Store(out/'pending_duplicate',{},ss,batch_size=4);v=values(st,ss[0]);st.commit(ss[0],*v);st.commit(ss[0],*v)
        require(len(st.pending)==1 and st.idempotent_commits==1);v[1]['elapsed_s']=1
        rejects(lambda:st.commit(ss[0],*v),StoreConflict)
    check('pending_duplicate_and_conflict',pending_duplicate)
    def close():
        st=Store(out/'close',{},ss,batch_size=4);st.commit(ss[0],*values(st,ss[0]));st.close();st.close()
        require(len(Store(st.folder).records)==1);rejects(lambda:st.commit(ss[1],*values(st,ss[1])))
    check('close_flushes_tail_and_rejects_further_write',close)
    report=dict(scope='FIXTURE_ONLY',status='PASS' if all(x['status']=='PASS' for x in results) else 'FAIL',
                check_count=len(results),checks=results)
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(run(sys.argv[1]))
