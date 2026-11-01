"""R21 T100 -> T90 -> full independent frozen-family research."""
from contextlib import ExitStack
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import shutil
import time
import numpy as np
from src.round13.common import fingerprint,read,record,require,sha,write
from src.round14.science import evaluate
from .space import DECLARED,INTERMEDIATES,B0,S,iter_candidates,operations
ROOT=Path(__file__).resolve().parents[2]
CENTER_IDENTITY=S
BASELINE_IDENTITY=B0
PARTITIONS=('T100','T90','FULL')

def pack_on_time(values,tau):
    a=np.asarray(values)
    require(a.ndim==1 and not np.isnan(a).any() and not np.isneginf(a).any(),'R21_INVALID_SENTINEL')
    finite=a[np.isfinite(a)]
    require(not (finite<0).any() and not (finite>604800).any() and math.isfinite(tau),'R21_INVALID_TIME')
    return int.from_bytes(np.packbits(a<=tau,bitorder='little').tobytes(),'little')

def count_bits(retained,first,second,n):
    require(all(type(v) is int and v>=0 and v>>n==0 for v in [retained,first,second]),'R21_PADDING')
    return (retained|first|second).bit_count()

class Gate:
    def __init__(self,lib,baseline,center,check=lambda:None):
        self.lib=lib;self.center=lib.center_indices;self.donors=lib.donor_indices21
        self.tau100=baseline['effective_grid']['T100_s']+1e-6;self.tau90=baseline['effective_grid']['T90_s']+1e-6
        self.mask_ids=np.flatnonzero(lib.keep);self.n=len(self.mask_ids);self.k90=(9*self.n+9)//10
        require(self.n==43070 and self.k90==38763,'R21_MASK_COUNT')
        self.mask_sha256=hashlib.sha256(np.asarray(lib.keep,dtype=np.uint8).tobytes()).hexdigest()
        self.coordinate_sha256=hashlib.sha256(np.asarray(lib.coords,dtype='<f8').tobytes()).hexdigest()
        self.row_digests={};self.bits90={}
        for i in sorted(lib.rows):
            check();self.row_digests[i]=hashlib.sha256(np.asarray(lib.rows[i],dtype='<f8').tobytes()).hexdigest()
            self.bits90[i]=pack_on_time(np.asarray(lib.rows[i])[lib.keep],self.tau90)
        self.source_binding=fingerprint(dict(matrix_sha256=lib.evidence['matrix']['sha256'],
            mask_sha256=self.mask_sha256,coordinate_sha256=self.coordinate_sha256,center_identity=S,original_constraint_reference=B0,
            tau100=self.tau100,tau90=self.tau90,
            rows=[[i,lib.states[i],self.row_digests[i],lib.assets[i]['regional_data_sha256']] for i in sorted(lib.rows)]))
        self.failed100={};self.retained90={};self.cache_bindings={}
        for r in sorted(set(self.center)-{676,2021}):
            remove=tuple(sorted((676,2021,r)))
            check();retained=[i for i in self.center if i not in remove]
            require(len(retained)==25,'R21_RETAINED_ORIGINAL25')
            accelerated=sorted(retained+[1440])
            minima=np.min(np.stack([lib.rows[i] for i in accelerated]),axis=0)
            self.failed100[remove]=self.mask_ids[minima[lib.keep]>self.tau100]
            bits=0
            for i in accelerated:bits|=self.bits90[i]
            self.retained90[remove]=bits
            self.cache_bindings[remove]=fingerprint(dict(source_binding=self.source_binding,center_identity=S,original_constraint_reference=B0,
                remove=list(remove),tau100=self.tau100,tau90=self.tau90,tolerance_s=1e-6,
                retained_original_indices=retained,fixed_new_donor=1440,accelerated_retained_indices=accelerated))

    def evidence(self):
        return dict(status='PASS',priority=list(PARTITIONS),source_binding_sha256=self.source_binding,
            mask_sha256=self.mask_sha256,coordinate_sha256=self.coordinate_sha256,
            tau100=self.tau100,tau90=self.tau90,n=self.n,k90=self.k90,center_identity=S,
            original_constraint_reference=B0,cache_bindings={','.join(map(str,k)):v for k,v in self.cache_bindings.items()},
            triple_deletion_plus_fixed1440_deficits={','.join(map(str,k)):v.tolist() for k,v in self.failed100.items()},
            source_rows=[[i,self.lib.states[i],self.row_digests[i],self.lib.assets[i]['regional_data_sha256']] for i in sorted(self.lib.rows)],
            bitset_padding_zero=True,gap_certificate_layer=False,candidate_REUSED=0)

    def classify(self,item):
        remove=tuple(item['remove']);add=item['add'];lib=self.lib
        require(remove in self.failed100 and len(add)==len(set(add))==3 and 1440 in add
            and all(i in self.donors for i in add),'R21_OPERATION')
        require(item['indices']==sorted((set(self.center)-set(remove))|set(add)),'R21_CANDIDATE_INDICES')
        require(item['identity']==fingerprint(sorted(lib.states[i] for i in item['indices'])),'R21_CANDIDATE_IDENTITY')
        from .space import families
        fs=families(remove,add)
        require(fs and item['family_owner']==fs[0] and item['families']==fs,'R21_FAMILY_BINDING')
        variable=[i for i in add if i!=1440]
        pts=self.failed100[remove]
        failures=pts[(np.asarray(lib.rows[variable[0]])[pts]>self.tau100)&(np.asarray(lib.rows[variable[1]])[pts]>self.tau100)]
        c90=None
        if len(failures):part='T100'
        else:
            c90=count_bits(self.retained90[remove],self.bits90[variable[0]],self.bits90[variable[1]],self.n)
            if c90>=self.k90:return 'FULL',None
            part='T90'
        cert=dict(item,partition=part,known_infeasible=True,full_feasibility_evaluation_performed=False,
            feasibility='NOT_EVALUATED',full_grid=None,effective_grid=None,regional=None,
            T90_s=None,T100_s=None,Tavg_s=None,Tmax_s=None,qualified_for_round21=False,
            source='archived_component_composition',new_native_validation_performed=False,whole_constellation_STK_verified=False,
            source_binding_sha256=self.source_binding,cache_binding_sha256=self.cache_bindings[remove],
            candidate_binding_sha256=fingerprint(dict(cache_binding=self.cache_bindings[remove],add=add,
                family_owner=item['family_owner'],families=item['families'])),
            input_binding_sha256=fingerprint([[i,lib.states[i],self.row_digests[i],lib.assets[i]['regional_data_sha256']] for i in item['indices']]),
            mask_sha256=self.mask_sha256,coordinate_sha256=self.coordinate_sha256,tau100=self.tau100,tau90=self.tau90,k90=self.k90)
        if part=='T100':
            p=int(failures[0]);values=[]
            for i in item['indices']:
                v=float(lib.rows[i][p]);require(v>self.tau100,'R21_T100_SOURCE')
                values.append(dict(index=i,state=lib.states[i],first_hit_s=v if math.isfinite(v) else None,
                    classification='FINITE_LATE' if math.isfinite(v) else 'NO_FIRST_HIT'))
            cert.update(point_id=p,in_mask=True,coordinates=np.asarray(lib.coords[p]).tolist(),source_values=values,source_values_sha256=fingerprint(values))
        else:
            bits=self.retained90[remove]|self.bits90[variable[0]]|self.bits90[variable[1]]
            classes=np.unpackbits(np.frombuffer(bits.to_bytes((self.n+7)//8,'little'),dtype=np.uint8),bitorder='little',count=self.n)
            cert.update(c90=c90,classification_sha256=hashlib.sha256(classes.tobytes()).hexdigest(),bitset_padding_zero=True)
        return part,cert

def annotate(report, center_report):
    """Keep the old B0 result explicit and apply the fixed-S improvement gate."""
    require(center_report['identity'] == CENTER_IDENTITY, 'ROUND21_WRONG_IMPROVEMENT_REFERENCE')
    reduction = center_report['regional']['pooled_internal']['max_s']-report['regional']['pooled_internal']['max_s']
    improvement = dict(Tmax_reduction_s=reduction, minimum_required_s=1., uncertainty_margin_s=1e-6,
        substantive_improvement=reduction-1e-6 >= 1., conservative_lower_bound_s=reduction-1e-6)
    report['improvement_vs_original_baseline'] = dict(report['improvement'])
    report['improvement_vs_S'] = improvement
    report['qualified_for_round21'] = bool(report['feasibility']['feasible'] and improvement['substantive_improvement'])
    report['ranking_key'] = [report['regional']['pooled_internal']['max_s'],
        report['regional']['pooled_internal']['mean_s'], report['effective_grid']['T100_s'],
        report['effective_grid']['T90_s'], report['identity']]
    report['round21_selection_rejection_reasons'] = list(report['feasibility']['rejection_reasons'])
    if not improvement['substantive_improvement']:
        report['round21_selection_rejection_reasons'].append('Tmax_REDUCTION_VS_S_BELOW_CONSERVATIVE_ONE_SECOND_GATE')
    return report


def science_job(work,out,life,lock=lambda:None):
    from .inputs import load,pool_diagnostic
    from .checker import IndependentChecker,iter_candidates as independent_candidates,terminal_verification
    from src.round14.checker import _differences,verify_baseline_whole
    from src.round14.worker import save_details,baseline_assertions
    work,out=Path(work),Path(out);cfg=read(ROOT/'configs/round21.json');meta=read(work/'frozen/contract.json')['metadata']
    check=lambda:life.check(True);begin=time.perf_counter();events=[]
    counts=dict(declared_candidates=DECLARED,T100_generated=0,T100_verified=0,T90_generated=0,T90_verified=0,
        FULL_evaluated=0,FULL_verified=0,unprocessed=DECLARED,unknown=0,qualified_for_round21=0,candidate_REUSED=0,
        B0_replayed=0,S_replayed=0,intermediates_replayed=0,retained_S=True)
    def phase(name):
        events.append(dict(phase=name,science_elapsed_s=time.perf_counter()-begin,lifecycle_elapsed_s=life.elapsed()))
        write(out/'phase_timings.json',dict(events=events,overlapping_worker_walls_added=False))
    lib=load(cfg,work,check)
    try:
        lock();phase('2171_original_assets_revalidated')
        write(out/'asset_context_verification.json',lib.evidence)
        write(out/'input_identity.json',dict(status='PASS',archive=record(cfg['archive'],check),used_members=lib.arc.used))
        baseline,bhits=evaluate(lib.baseline_indices,lib.rows,lib.intervals,lib.keep,lib.targets,lib.states)
        center,chits=evaluate(lib.center_indices,lib.rows,lib.intervals,lib.keep,lib.targets,lib.states,baseline)
        checker=IndependentChecker(lib,baseline,center,check)
        for name,rep,hits in [('baseline',baseline,bhits),('center',center,chits)]:
            audit=checker.verify(rep['indices'],rep,hits,baseline if name=='center' else None)
            write(out/(name+'_checker.json'),audit);require(audit['status']=='PASS','R21_REFERENCE_CHECK:'+name)
            old=read(Path(cfg['r20_delivery'])/('sealed/science/'+name+'.json'))
            for k in ['identity','indices','full_grid','effective_grid','regional']:
                require(not _differences(old[k],rep[k],1e-6),'R21_PRIOR_REFERENCE:'+name+'/'+k)
            pointwise=_pointwise(np.load(Path(cfg['r20_delivery'])/('sealed/science/'+name+'_first_hits.npy'),allow_pickle=False),hits)
            write(out/(name+'_r20_readback.json'),pointwise);save_details(out,name,rep,hits,lib)
        baseline_assertions(baseline,lib.k13_baseline)
        whole=verify_baseline_whole(baseline,bhits,lib.baseline_whole['hits'],lib.baseline_whole['intervals'],lib.targets)
        write(out/'baseline_whole_readback.json',whole);require(whole['status']=='PASS','R21_B0_WHOLE')
        counts.update(B0_replayed=1,S_replayed=1)
        tau100=baseline['effective_grid']['T100_s']+1e-6;tau90=baseline['effective_grid']['T90_s']+1e-6
        intermediate_results=[]
        for assertion in meta['intermediate_assertions']:
            label=assertion['label'];ids=assertion['indices']
            rep,hits=evaluate(ids,lib.rows,lib.intervals,lib.keep,lib.targets,lib.states,baseline)
            annotate(rep,center)
            audit=checker.verify(ids,rep,hits,baseline)
            write(out/(label+'_checker.json'),audit)
            require(audit['status']=='PASS','R21_INTERMEDIATE_INDEPENDENT:'+label)
            require(rep['identity']==assertion['identity'] and rep['feasibility']['feasible'] is True
                and rep['qualified_for_round21'] is False,'R21_INTERMEDIATE_ROLE:'+label)
            old_evidence=meta['r20_prior_binding']['intermediate_evidence'][rep['identity']]
            old=old_evidence['candidates']
            for key in ['identity','indices','full_grid','effective_grid','regional','first_hits_sha256']:
                require(not _differences(old[key],rep[key],1e-6),'R21_INTERMEDIATE_PRIOR_FULL:'+label+'/'+key)
            for key in ['full_grid','effective_grid']:
                require(not _differences(assertion[key],rep[key],1e-6),'R21_INTERMEDIATE_PLAN_ASSERTION:'+label+'/'+key)
            require(not _differences(assertion['pooled_internal'],rep['regional']['pooled_internal'],1e-6),'R21_INTERMEDIATE_PLAN_GAPS:'+label)
            old_hits_path=Path(cfg['r20_delivery'])/'sealed/science/full_first_hits'/(rep['identity']+'.npy')
            pointwise=_pointwise(np.load(old_hits_path,allow_pickle=False),hits)
            pointwise.update(R20_FULL_record_sha256=fingerprint(old),R20_checker_record_sha256=fingerprint(old_evidence['checker']),
                R20_original_ledger=old_evidence['ledger'],R20_first_hits=old_evidence['first_hits'])
            require(old_evidence['checker']['main_first_hits_sha256']==rep['first_hits_sha256'],'R21_INTERMEDIATE_PRIOR_CHECKER_VECTOR')
            write(out/(label+'_r20_readback.json'),pointwise)
            save_details(out,label,rep,hits,lib)
            intermediate_results.append(dict(label=label,identity=rep['identity'],status='B0_FEASIBLE_INTERMEDIATE_NOT_INCUMBENT',
                feasible_vs_B0=True,qualified_vs_S=False,new_R21_candidate=False,R20_ordinal=old_evidence['ledger']['ordinal'],
                r20_first_hits_sha256=old_evidence['first_hits']['sha256'],independent_checker_status=audit['status']))
            counts['intermediates_replayed']+=1
        write(out/'intermediate_replays.json',dict(status='PASS',intermediates=intermediate_results))
        phase('B0_S_F1_F2_independently_replayed_and_bound_to_R20')
        write(out/'expanded_pool_raw_domain_diagnostic.json',pool_diagnostic(lib,bhits))
        write(out/'reference_roles.json',dict(original_constraint_reference=B0,search_center=S,improvement_reference=S,
            intermediates='B0_FEASIBLE_INTERMEDIATE_NOT_INCUMBENT',fallback=S,fixed_throughout=True))
        # Exact per-item comparison, not only cardinalities or summed families.
        compared=0
        for a,b in itertools.zip_longest(iter_candidates(lib.center_indices,lib.donor_indices21,lib.states,check),
                independent_candidates(lib.center_indices,lib.donor_indices21,lib.states,check)):
            require(a==b and a is not None,'R21_INDEPENDENT_ENUMERATION');compared+=1
        require(compared==DECLARED,'R21_ENUM_COUNT')
        write(out/'independent_space_definition.json',dict(status='PASS',items_compared=compared,
            exact_operations_indices_identity_order_owner=True,family_sizes=[55666,55666],intersection=26,
            owner_counts=meta['space_summary']['owner_counts']))
        gate=Gate(lib,baseline,center,check);write(out/'necessary_gate_context.json',gate.evidence())
        require(gate.source_binding==checker.source_binding,'R21_GATE_SOURCE_BINDING')
        for remove in gate.failed100:
            require(gate.cache_bindings[remove]==checker.cache_binding(list(remove)),'R21_TRIPLE_DELETION_CACHE')
            vals=np.zeros(len(gate.mask_ids),dtype=bool)
            for i in lib.center_indices:
                if i not in remove:vals|=np.asarray(lib.rows[i])[lib.keep]<=checker.tau100
            vals|=np.asarray(lib.rows[1440])[lib.keep]<=checker.tau100
            require(gate.failed100[remove].tolist()==gate.mask_ids[~vals].tolist(),'R21_TRIPLE_DELETION_PLUS_FIXED1440_POINTS')
        write(out/'independent_necessary_gate_context.json',dict(status='PASS',source_binding_sha256=checker.source_binding,
            triple_deletion_caches=len(gate.failed100),retained_original25_plus_fixed1440=True,independent_raw_boolean_reconstruction=True))
        phase('independent_union_and_triple_deletion_gates_ready')
        names=['ledger','candidates','checker','t100_certificates','t100_certificate_checker','t90_certificates','t90_certificate_checker']
        (out/'full_first_hits').mkdir();best=best_hits=None;candidate_start=time.perf_counter()
        with ExitStack() as stack:
            streams={n:stack.enter_context((out/(n+'.jsonl')).open('w',encoding='utf8')) for n in names}
            def emit(n,obj):streams[n].write(json.dumps(obj,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n')
            for item in iter_candidates(lib.center_indices,lib.donor_indices21,lib.states,check):
                part,cert=gate.classify(item)
                if part!='FULL':
                    counts[part+'_generated']+=1;emit(part.lower()+'_certificates',cert)
                    audit=checker.verify_certificate(item,cert);emit(part.lower()+'_certificate_checker',audit)
                    require(audit['status']=='PASS','R21_CERTIFICATE:'+part)
                    counts[part+'_verified']+=1;value=cert
                else:
                    check();require(checker.partition(item)=='FULL','R21_INDEPENDENT_FULL_PRIORITY')
                    rep,hits=evaluate(item['indices'],lib.rows,lib.intervals,lib.keep,lib.targets,lib.states,baseline)
                    annotate(rep,center);rep.update(item,partition='FULL');counts['FULL_evaluated']+=1
                    emit('candidates',rep);np.save(out/'full_first_hits'/(rep['identity']+'.npy'),hits,allow_pickle=False)
                    audit=checker.verify(item['indices'],rep,hits,baseline,item['remove'],item['add']);emit('checker',audit)
                    require(audit['status']=='PASS','R21_FULL_NUMERICAL_CHECK');counts['FULL_verified']+=1;value=rep
                    if rep['qualified_for_round21']:
                        counts['qualified_for_round21']+=1
                        if best is None or tuple(rep['ranking_key'])<tuple(best['ranking_key']):best,best_hits=rep,hits.copy()
                emit('ledger',dict(item,partition=part,record_sha256=fingerprint(value),checker_sha256=fingerprint(audit)))
                counts['unprocessed']=DECLARED-counts['T100_generated']-counts['T90_generated']-counts['FULL_evaluated']
                if item['ordinal']==1023:
                    elapsed=time.perf_counter()-candidate_start
                    write(out/'first_batch_throughput.json',dict(candidates=1024,wall_s=elapsed,candidates_per_s=1024/elapsed,
                        counts=counts.copy(),disposition='FORMAL_FROZEN_LEDGER_PREFIX',lifecycle_elapsed_s=life.elapsed()))
                if item['ordinal']%512==0:
                    check()
                    for st in streams.values():st.flush()
                    write(out/'progress.json',dict(counts,completed=False,lifecycle_elapsed_s=life.elapsed()))
        phase('all_candidates_processed_and_independently_verified')
        selection=checker.selection();require(selection['selected_identity']==(best['identity'] if best else None),'R21_SELECTION')
        write(out/'independent_selection.json',selection)
        terminal=terminal_verification(meta,out,check);write(out/'independent_terminal_verification.json',terminal)
        require(terminal['qualified_for_round21']==counts['qualified_for_round21'] and terminal['selected_identity']==selection['selected_identity'],'R21_TERMINAL_SELECTION')
        selected,hits=(best,best_hits) if best is not None else (center,chits)
        counts['retained_S']=best is None
        save_details(out,'selected',selected,hits,lib)
        audit=checker.verify(selected['indices'],selected,hits,baseline,
            best['remove'] if best else None,best['add'] if best else None)
        write(out/'selected_checker.json',audit);require(audit['status']=='PASS','R21_SELECTED')
        _export_orbits(out,selected,lib,cfg,best is None)
        write(out/'boundary_tradeoffs.json',dict(baseline=baseline['regional'],center=center['regional'],selected=selected['regional'],boundary_is_primary_constraint=False))
        def delta(ref):
            return dict(T90_s=selected['effective_grid']['T90_s']-ref['effective_grid']['T90_s'],
                T100_s=selected['effective_grid']['T100_s']-ref['effective_grid']['T100_s'],
                Tavg_s=selected['regional']['pooled_internal']['mean_s']-ref['regional']['pooled_internal']['mean_s'],
                Tmax_s=selected['regional']['pooled_internal']['max_s']-ref['regional']['pooled_internal']['max_s'],
                gap_count=selected['regional']['pooled_internal']['gap_count']-ref['regional']['pooled_internal']['gap_count'],
                boundary_Tmax_s=selected['regional']['pooled_boundary_inclusive']['max_s']-ref['regional']['pooled_boundary_inclusive']['max_s'])
        write(out/'metric_comparison.json',dict(relative_to_B0=delta(baseline),relative_to_S=delta(center),
            full_grid=selected['full_grid'],effective_grid=selected['effective_grid'],actual_gap_denominator=selected['regional']['pooled_internal']['gap_count']))
        missing=np.flatnonzero(~np.isfinite(hits)).tolist()
        write(out/'research_scope.json',dict(status='PASS',scope='Complete limited third-swap union of the two fixed feasible R20 intermediates',
            source='archived_component_composition',new_native_validation_performed=False,whole_constellation_STK_verified=False,
            active_protocol_change_authorized=False,official_readiness='UNRESOLVED',official_score=None,
            next_scientific_run_gate='BLOCKED_PENDING_RULE_CONFIRMATION',missing_raw_domain_point_ids=missing,
            physical_unreachability_inferred=False,continuous_geometry_completeness_claim=False,
            conditions=['Saved mixed altitudes 500..700 km','0.81 degree half angles/direct AreaTarget/provisional mask conditional','EOP ends 2019; scenario 2027']))
        write(out/'source_preservation.json',lib.preserve())
        for name in ['asset_verification.jsonl','input_asset_verification.jsonl']:
            if (work/name).is_file():shutil.copyfile(work/name,out/name)
        outcome='QUALIFIED_FURTHER_IMPROVEMENT_FOUND' if best else 'NO_FURTHER_QUALIFIED_IMPROVEMENT_IN_DECLARED_TWO_INTERMEDIATE_THIRD_SWAP_UNION'
        completion=dict(counts,status='PASS',completed=True,optimization_outcome=outcome,selected_identity=selected['identity'],
            verified_candidates=sum(counts[p+'_verified'] for p in PARTITIONS),scientific_wall_s=time.perf_counter()-begin)
        write(out/'enumeration_completion.json',completion);write(out/'progress.json',completion)
        phase('selected_artifacts_source_preservation_and_durable_readback')
        return completion
    except BaseException:
        counts['unknown']=counts['T100_generated']-counts['T100_verified']+counts['T90_generated']-counts['T90_verified']+counts['FULL_evaluated']-counts['FULL_verified']
        counts['unprocessed']=DECLARED-counts['T100_generated']-counts['T90_generated']-counts['FULL_evaluated']
        write(out/'progress.json',dict(counts,completed=False,optimization_outcome='PARTIAL_NOT_CONCLUDED'))
        raise
    finally:lib.close()


def select(reports):
    eligible = [r for r in reports if r['qualified_for_round21']]
    return min(eligible, key=lambda r: tuple(r['ranking_key'])) if eligible else None



def _pointwise(old_hits, hits):
    require(old_hits.shape == hits.shape == (43424,), 'ROUND21_REPLAY_POINT_SHAPE')
    require(not np.isnan(old_hits).any() and not np.isneginf(old_hits).any(), 'ROUND21_REPLAY_INVALID_SENTINEL')
    classes = int(np.count_nonzero(np.isfinite(old_hits) != np.isfinite(hits)))
    finite = np.isfinite(old_hits) & np.isfinite(hits)
    error = float(np.max(np.abs(old_hits[finite]-hits[finite]),initial=0.))
    require(classes == 0 and error <= 1e-6, 'ROUND21_R20_POINTWISE_MISMATCH')
    return dict(status='PASS',points_compared=43424,classification_difference_count=classes,max_absolute_error_s=error)


def _export_orbits(out, selected, lib, cfg, retained):
    from src.round13.inputs import state_key, ORBIT_FIELDS
    path = out/'selected_orbits.csv'
    prior = Path(cfg['r20_delivery'])/'sealed/science/selected_orbits.csv'
    if retained:
        shutil.copyfile(prior,path)
        require(sha(path) == sha(prior) == '7b9480f8a1aef119b73cd2e1732ce45845b1634886492a8c5857636ad8654365'
                and path.stat().st_size == 5199, 'ROUND21_RETAINED_CSV_BYTES')
    else:
        rows = [dict(sat_id=f'Sat{n:03d}',catalog_index=i,
            **{k:repr(float(lib.assets[i]['row'][k])) for k in ORBIT_FIELDS})
            for n,i in enumerate(selected['indices'],1)]
        with path.open('w',encoding='utf8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    with path.open(encoding='utf8',newline='') as stream:
        restored = list(csv.DictReader(stream))
    require(len(restored) == 28,'ROUND21_ORBIT_CSV_COUNT')
    for i,row in zip(selected['indices'],restored):
        require(state_key(row)==lib.states[i] and all(float(row[k]).hex()==float(lib.assets[i]['row'][k]).hex()
            for k in ORBIT_FIELDS),'ROUND21_ORBIT_CSV_ROUNDTRIP')
    write(out/'selection_protocol.json',dict(status='PASS',identity=selected['identity'],indices=selected['indices'],
        original_constraint_reference=BASELINE_IDENTITY,search_center=CENTER_IDENTITY,improvement_reference=CENTER_IDENTITY,
        retained_S=retained,relative_to_S=dict(removed=sorted(set(lib.center_indices)-set(selected['indices'])),
            added=sorted(set(selected['indices'])-set(lib.center_indices))),
        relative_to_B0=dict(removed=sorted(set(lib.baseline_indices)-set(selected['indices'])),
            added=sorted(set(selected['indices'])-set(lib.baseline_indices))),
        saved_altitudes_km={str(i):float(lib.assets[i]['row']['altitude_km']) for i in selected['indices']},
        source='archived_component_composition',new_native_validation_performed=False,
        whole_constellation_STK_verified=False,float_roundtrip_verified=True,csv=record(path)))


