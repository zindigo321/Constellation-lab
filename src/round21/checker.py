"""Independent R21 source-array numerics, certificates and exact stream audit.

Only the validated decoder, producer state-token format and the frozen R14
checker numerical primitives are shared.  This module never imports R21's
main science, bitset, interval merge, decision, ranking or selection code.
"""
import hashlib
import itertools
import math

import numpy as np

from src.round13.common import fingerprint, require
from src.round14.checker import (_coverage, _regional, _decision, _differences,
                                 _digest, verify_baseline_whole)

DECLARED = 111306
B0 = 'c1fbd71e9dfca4e0a7d0d603d496fff8a71e2bc406d12eee113ab2bc4207b71d'
TARGET = 'YangtzeRiverDelta_Island_1'
PARTS = ('T100', 'T90', 'FULL')
META = {'ordinal', 'remove', 'add', 'partition', 'processing_state', 'family_owner', 'families'}
ROUND21_FIELDS = {'improvement_vs_original_baseline', 'improvement_vs_S',
                  'qualified_for_round21', 'ranking_key',
                  'round21_selection_rejection_reasons'}


def _pool(center, donors, states):
    c, d = sorted(center), sorted(donors)
    require(len(c) == len(set(c)) == 28 and len(d) == len(set(d)) == 2143,
            'CHECKER_R21_POOL_CARDINALITY')
    require(not set(c) & set(d) and sorted(c+d) == list(range(2171)),
            'CHECKER_R21_EXACT_DONOR_SET')
    require(all(type(i) is int and i in states for i in c+d)
            and len({states[i] for i in c+d}) == 2171, 'CHECKER_R21_STATE_POOL')
    return c, d


def classification_digest(values):
    return hashlib.sha256(np.asarray(values, dtype=np.uint8).tobytes(order='C')).hexdigest()


def boolean_on_time(rows, indices, keep, tau):
    keep = np.asarray(keep)
    require(keep.dtype == np.bool_ and keep.ndim == 1 and math.isfinite(float(tau)),
            'CHECKER_BOOLEAN_SCHEMA')
    result = np.zeros(int(keep.sum()), dtype=np.bool_)
    for index in indices:
        source = np.asarray(rows[index])
        finite = source[np.isfinite(source)]
        require(source.shape == keep.shape and not np.isnan(source).any()
                and not np.isneginf(source).any() and not (finite < 0).any()
                and not (finite > 604800).any(), 'CHECKER_BOOLEAN_SOURCE')
        result = np.logical_or(result, source[keep] <= tau)
    return result


def verify_t100_witness(rows, indices, point_id, tau, source_values=None, states=None):
    differences, expected = [], []
    if (type(point_id) is not int or point_id < 0 or not indices
            or any(point_id >= len(rows[i]) for i in indices)):
        return dict(status='FAIL', differences=[dict(path='point_id', reason='INVALID_POINT_ID')],
                    source_values=[])
    for index in indices:
        value = float(rows[index][point_id])
        if math.isnan(value) or value == -math.inf or value <= tau or (math.isfinite(value) and value > 604800):
            differences.append(dict(path='source_values/'+str(index), reason='SOURCE_NOT_VALID_LATE_VALUE'))
        row = dict(index=index, first_hit_s=value if math.isfinite(value) else None,
                   classification='FINITE_LATE' if math.isfinite(value) else 'NO_FIRST_HIT')
        if states is not None:
            row['state'] = states[index]
        expected.append(row)
    if source_values is not None:
        differences += _differences(expected, source_values, 0, 'source_values')
    return dict(status='FAIL' if differences else 'PASS', differences=differences,
                source_values=expected, point_id=point_id, tau100=tau)


def verify_t90_count(rows, indices, keep, tau, k90, c90, digest):
    values = boolean_on_time(rows, indices, keep, tau)
    count, actual_digest = int(np.count_nonzero(values)), classification_digest(values)
    differences = []
    if type(c90) is not int or count != c90:
        differences.append(dict(path='c90', reason='EXACT_COUNT_MISMATCH', expected=count, reported=c90))
    if actual_digest != digest:
        differences.append(dict(path='classification_sha256', reason='CLASSIFICATION_DIGEST_MISMATCH'))
    if count >= k90:
        differences.append(dict(path='c90', reason='NO_T90_VIOLATION'))
    return dict(status='FAIL' if differences else 'PASS', differences=differences,
                c90=count, k90=k90, classification_sha256=actual_digest)


def _scientific(report):
    return {key: value for key, value in report.items() if key not in META}


def _rank(report):
    return [report['regional']['pooled_internal']['max_s'],
            report['regional']['pooled_internal']['mean_s'],
            report['effective_grid']['T100_s'], report['effective_grid']['T90_s'], report['identity']]


def _annotate(report, center):
    old, new = center['regional']['pooled_internal']['max_s'], report['regional']['pooled_internal']['max_s']
    reduction = old-new if old is not None and new is not None else None
    lower = reduction-1e-6 if reduction is not None else None
    substantive = lower is not None and lower >= 1.
    report['improvement_vs_original_baseline'] = dict(report['improvement'])
    report['improvement_vs_S'] = dict(Tmax_reduction_s=reduction, minimum_required_s=1.,
        uncertainty_margin_s=1e-6, substantive_improvement=substantive, conservative_lower_bound_s=lower)
    report['qualified_for_round21'] = bool(report['feasibility']['feasible'] and substantive)
    report['ranking_key'] = _rank(report)
    reasons = list(report['feasibility']['rejection_reasons'])
    if not substantive:
        reasons.append('Tmax_REDUCTION_VS_S_BELOW_CONSERVATIVE_ONE_SECOND_GATE')
    report['round21_selection_rejection_reasons'] = reasons
    return report


def compact_report(report):
    if report.get('_compact') is True:
        return report
    result = {key: report[key] for key in META | {'identity', 'indices', 'source',
        'new_native_validation_performed', 'whole_constellation_STK_verified', 'native_verified',
        'first_hits_sha256'} if key in report}
    result.update(_compact=True, qualified_for_round21=report['qualified_for_round21'],
                  rank=_rank(report), main_output_sha256=fingerprint(_scientific(report)))
    return result


class IndependentChecker:
    def __init__(self, lib, baseline_report=None, center_report=None, check=lambda: None,
                 duration=604800, tolerance=1e-6, required_count=28):
        self.lib, self.check = lib, check
        self.rows, self.intervals, self.states = lib.rows, lib.intervals, lib.states
        self.targets, self.keep = list(lib.targets), np.asarray(lib.keep)
        self.duration, self.tolerance, self.required_count = duration, tolerance, required_count
        self.original_indices = sorted(lib.baseline_indices)
        inferred = sorted((set(self.original_indices)-{1217, 1284}) | {2021, 2023})
        self.center_indices = sorted(center_report['indices'] if center_report is not None
                                     else getattr(lib, 'center_indices', inferred))
        self.donors = sorted(set(self.rows)-set(self.center_indices))
        _pool(self.center_indices, self.donors, self.states)
        shape = np.asarray(self.rows[self.original_indices[0]]).shape
        require(len(shape) == 1 and self.keep.dtype == np.bool_ and self.keep.shape == shape,
                'CHECKER_R21_ROW_MASK_SHAPE')
        require(set(self.rows) == set(self.intervals) == set(self.states), 'CHECKER_R21_SOURCE_POOL')
        self.row_digests = {}
        for index, source in self.rows.items():
            check()
            values = np.asarray(source); finite = values[np.isfinite(values)]
            require(values.shape == shape and not np.isnan(values).any() and not np.isneginf(values).any()
                    and not (finite < 0).any() and not (finite > duration).any(), 'CHECKER_INVALID_SOURCE_ROW')
            require(set(self.intervals[index]) == set(self.targets), 'CHECKER_REGIONAL_TARGET_SET')
            self.row_digests[index] = _digest(values)
        self.expected, self.certified, self.independent_partitions = {}, {}, {}
        self.boolean_cache, self.donor_boolean_cache, self.minimum_cache = {}, {}, {}
        self.cache_binding_cache = {}
        self.baseline_reference = None
        self.center_reference = None
        self.baseline_reference = self.recompute(self.original_indices)[0]
        self.center_reference = self.recompute(self.center_indices, self.baseline_reference)[0]
        self.mask_ids = np.flatnonzero(self.keep)
        self.tau100 = self.baseline_reference['effective_grid']['T100_s']+tolerance
        self.tau90 = self.baseline_reference['effective_grid']['T90_s']+tolerance
        self.k90 = math.ceil(9*len(self.mask_ids)/10)
        self.mask_sha256 = classification_digest(self.keep)
        self.coordinate_sha256 = hashlib.sha256(np.asarray(lib.coords, dtype='<f8').tobytes()).hexdigest()
        self.matrix_sha256 = getattr(lib, 'matrix_sha256', None)
        if self.matrix_sha256 is None:
            self.matrix_sha256 = getattr(lib, 'evidence', {}).get('matrix', {}).get('sha256')
        self.center_identity = self.center_reference['identity']
        self.source_binding = fingerprint(dict(matrix_sha256=self.matrix_sha256,
            mask_sha256=self.mask_sha256, coordinate_sha256=self.coordinate_sha256,
            center_identity=self.center_identity,original_constraint_reference=B0,tau100=self.tau100,tau90=self.tau90,
            rows=[[i,self.states[i],self.row_digests[i],lib.assets[i]['regional_data_sha256']] for i in sorted(self.rows)]))
        if baseline_report is not None or center_report is not None:
            self.set_references(baseline_report or self.baseline_reference,
                                center_report or self.center_reference)

    def set_references(self, baseline_report, center_report):
        for name, expected, reported in [('B0', self.baseline_reference, baseline_report),
                                         ('S', self.center_reference, center_report)]:
            for key in ('identity', 'indices', 'full_grid', 'effective_grid', 'regional', 'first_hits_sha256'):
                require(not _differences(expected[key], reported[key], self.tolerance),
                        'CHECKER_R21_REFERENCE_MISMATCH:'+name+'/'+key)
        return dict(status='PASS', original_constraint_reference=self.baseline_reference['identity'],
                    search_center=self.center_identity, improvement_reference=self.center_identity)

    def enumerate_space(self, check=lambda: None):
        return iter_candidates(self.center_indices, self.donors, self.states, check)

    def _hits(self, indices, remove_pair=None, add_pair=None):
        require(len(indices)==len(set(indices))==28,'CHECKER_R21_UNIQUE28')
        removed=sorted(set(self.center_indices)-set(indices));added=sorted(set(indices)-set(self.center_indices))
        if remove_pair is not None or add_pair is not None:
            require(removed==remove_pair and added==add_pair and len(removed)==len(added)==3,'CHECKER_R21_SWAP_LABEL')
        require(set(indices)==set(self.original_indices) or not removed and not added or
            removed==[676,2021] and set(added) in ({218,1440},{1440,1876}) or
            len(removed)==len(added)==3 and {676,2021}<=set(removed) and 1440 in added and bool({218,1876}&set(added)),
            'CHECKER_R21_OUT_OF_SCOPE')
        key=tuple(i for i in self.center_indices if i in indices)
        if key not in self.minimum_cache:
            vector=np.full(len(self.keep),np.inf)
            for i in key: vector=np.where(np.asarray(self.rows[i])<vector,self.rows[i],vector)
            self.minimum_cache[key]=vector
        vector=self.minimum_cache[key].copy()
        for i in sorted(set(indices)-set(key)):vector=np.where(np.asarray(self.rows[i])<vector,self.rows[i],vector)
        return vector

    def recompute(self, indices, baseline_report=None, remove_pair=None, add_pair=None):
        indices = list(indices)
        require(all(type(i) is int and i in self.rows for i in indices), 'CHECKER_UNAVAILABLE_COMPONENT')
        require(len({self.states[i] for i in indices}) == len(indices), 'CHECKER_DUPLICATE_STATE')
        hits = self._hits(indices, remove_pair, add_pair)
        raw = {target: [] for target in self.targets}
        for index in indices:
            for target in self.targets:
                raw[target] += self.intervals[index][target]
        report = dict(indices=indices, identity=fingerprint(sorted(self.states[i] for i in indices)),
            unique_state_count=len({self.states[i] for i in indices}),
            full_grid=_coverage(hits, self.duration), effective_grid=_coverage(hits[self.keep], self.duration),
            regional=_regional(raw, self.targets, self.duration, self.tolerance), first_hits_sha256=_digest(hits),
            input_state_identity=fingerprint([[i, self.states[i]] for i in sorted(indices)]),
            source='archived_component_composition', new_native_validation_performed=False,
            whole_constellation_STK_verified=False, native_verified=False)
        reference = self.baseline_reference if baseline_report is not None else None
        report['feasibility'] = _decision(report, reference, self.required_count, self.duration, self.tolerance)
        old = reference['regional']['pooled_internal']['max_s'] if reference else None
        new = report['regional']['pooled_internal']['max_s']
        change = old-new if old is not None and new is not None else None
        lower = change-self.tolerance if change is not None else None
        substantive = lower is not None and lower >= 1.
        report['improvement'] = dict(Tmax_reduction_s=change, minimum_required_s=1.,
            uncertainty_margin_s=self.tolerance, substantive_improvement=substantive, conservative_lower_bound_s=lower)
        report['qualified_improvement'] = bool(report['feasibility']['feasible'] and substantive)
        report['selection_rejection_reasons'] = list(report['feasibility']['rejection_reasons'])
        if not substantive:
            report['selection_rejection_reasons'].append('Tmax_REDUCTION_BELOW_CONSERVATIVE_ONE_SECOND_GATE')
        return report, hits

    def verify(self, indices, reported, reported_hits, baseline_report=None, remove_pair=None, add_pair=None):
        expected, hits = self.recompute(indices, baseline_report, remove_pair, add_pair)
        if ROUND21_FIELDS & set(reported):
            _annotate(expected, self.center_reference)
        scientific = _scientific(reported)
        differences = _differences(expected, scientific, self.tolerance)
        actual = np.asarray(reported_hits)
        classification = maximum = None
        if actual.shape != hits.shape:
            differences.append(dict(path='first_hits', reason='SHAPE_MISMATCH'))
        else:
            classification = int(np.count_nonzero(np.isfinite(actual) != np.isfinite(hits)))
            finite = np.isfinite(actual) & np.isfinite(hits)
            maximum = float(np.max(np.abs(actual[finite]-hits[finite]), initial=0.))
            if classification or maximum > self.tolerance or np.isnan(actual).any() or np.isneginf(actual).any():
                differences.append(dict(path='first_hits', reason='POINTWISE_MISMATCH'))
            if _digest(actual) != scientific.get('first_hits_sha256'):
                differences.append(dict(path='first_hits_sha256', reason='REPORTED_ARRAY_DIGEST_MISMATCH'))
        comparisons = {}
        for target in self.targets:
            spans = expected['regional']['targets'][target]['merged_intervals']
            claimed = reported.get('regional', {}).get('targets', {}).get(target, {}).get('merged_intervals')
            comparisons[target] = dict(expected_merged_count=len(spans), checker_intervals_sha256=fingerprint(spans),
                main_intervals_sha256=fingerprint(claimed), differences=_differences(spans, claimed, self.tolerance, target))
        qualified = expected.get('qualified_for_round21', False)
        result = dict(identity=expected['identity'], status='FAIL' if differences else 'PASS', differences=differences,
            points_compared=len(hits), classification_difference_count=classification,
            max_absolute_first_hit_error_s=maximum, absolute_tolerance_s=self.tolerance, relative_tolerance=0,
            input_sha256=fingerprint([[i, self.states[i], self.row_digests[i]] for i in sorted(indices)]),
            main_first_hits_sha256=scientific.get('first_hits_sha256'), checker_first_hits_sha256=_digest(hits),
            main_output_sha256=fingerprint(scientific), checker_output_sha256=fingerprint(expected),
            interval_comparisons=comparisons, qualified_for_round21=qualified, rank=_rank(expected),
            shared_schema='Validated decoder/coordinates/mask/producer state-token format; frozen R14 checker primitives',
            independent_methods='Pairwise retained minima; sorted order statistic; cumulative-frontier intervals; B0 gates/S improvement')
        if not differences and ROUND21_FIELDS <= set(reported):
            self.expected[expected['identity']] = dict(identity=expected['identity'], indices=list(indices),
                qualified_for_round21=qualified, rank=_rank(expected), main_output_sha256=result['main_output_sha256'],
                checker_output_sha256=result['checker_output_sha256'])
        return result

    def _boolean(self, candidate, tau):
        removed=tuple(candidate['remove']);key=(removed,float(tau))
        if key not in self.boolean_cache:
            selected=[i for i in self.center_indices if i not in removed]
            self.boolean_cache[key]=boolean_on_time(self.rows,selected,self.keep,tau)
        result=self.boolean_cache[key].copy()
        for donor in candidate['add']:
            dkey=(donor,float(tau))
            if dkey not in self.donor_boolean_cache:
                self.donor_boolean_cache[dkey]=np.asarray(self.rows[donor])[self.keep]<=tau
            result=np.logical_or(result,self.donor_boolean_cache[dkey])
        return result

    def partition(self, candidate):
        if not self._boolean(candidate,self.tau100).all():return 'T100'
        if int(np.count_nonzero(self._boolean(candidate,self.tau90)))<self.k90:return 'T90'
        return 'FULL'

    def cache_binding(self, remove):
        key=tuple(remove)
        if key not in self.cache_binding_cache:
            self.cache_binding_cache[key]=fingerprint(dict(source_binding=self.source_binding,
                center_identity=self.center_identity,original_constraint_reference=B0,remove=list(remove),tau100=self.tau100,tau90=self.tau90,
                tolerance_s=1e-6,retained_original_indices=[i for i in self.center_indices if i not in remove],
                fixed_new_donor=1440,accelerated_retained_indices=sorted([i for i in self.center_indices if i not in remove]+[1440])))
        return self.cache_binding_cache[key]

    def verify_certificate(self,candidate,cert):
        differences=[];part=self.partition(candidate)
        ids=sorted([i for i in self.center_indices if i not in candidate['remove']]+candidate['add'])
        members=[label for label,donor in [('G1',218),('G2',1876)] if donor in candidate['add']]
        if (len(set(candidate['remove']))!=3 or len(set(candidate['add']))!=3 or len(set(ids))!=28
                or not {676,2021}<=set(candidate['remove']) or 1440 not in candidate['add']
                or not set(candidate['remove'])<=set(self.center_indices)
                or not set(candidate['add'])<=set(self.rows)-set(self.center_indices)
                or candidate['indices']!=ids or candidate['identity']!=fingerprint(sorted(self.states[i] for i in ids))
                or not members or candidate['families']!=members or candidate['family_owner']!=members[0]):
            differences.append('CANDIDATE_IDENTITY_OR_OPERATION')
        if part not in ('T100','T90') or part!=cert.get('partition'):differences.append('PARTITION')
        for k,v in candidate.items():
            if _differences(v,cert.get(k),0):differences.append(k)
        binding=fingerprint(dict(cache_binding=self.cache_binding(candidate['remove']),
            add=candidate['add'],family_owner=candidate['family_owner'],families=candidate['families']))
        expected=dict(known_infeasible=True,full_feasibility_evaluation_performed=False,
            feasibility='NOT_EVALUATED',full_grid=None,effective_grid=None,regional=None,
            T90_s=None,T100_s=None,Tavg_s=None,Tmax_s=None,qualified_for_round21=False,
            source_binding_sha256=self.source_binding,cache_binding_sha256=self.cache_binding(candidate['remove']),
            candidate_binding_sha256=binding,mask_sha256=self.mask_sha256,coordinate_sha256=self.coordinate_sha256,
            tau100=self.tau100,tau90=self.tau90,k90=self.k90,
            source='archived_component_composition',new_native_validation_performed=False,whole_constellation_STK_verified=False)
        for k,v in expected.items():
            if type(cert.get(k)) is not type(v) or cert.get(k)!=v:differences.append(k)
        source_rows=[[i,self.states[i],self.row_digests[i],self.lib.assets[i]['regional_data_sha256']] for i in candidate['indices']]
        if cert.get('input_binding_sha256')!=fingerprint(source_rows):differences.append('INPUT_BINDING')
        if part=='T100':
            if cert.get('in_mask') is not True:differences.append('IN_MASK_FLAG')
            point=cert.get('point_id')
            if type(point) is not int or point not in self.mask_ids:differences.append('POINT_MASK')
            else:
                detail=verify_t100_witness(self.rows,candidate['indices'],point,self.tau100,cert.get('source_values'),self.states)
                if detail['status']!='PASS':differences.append(detail)
                if cert.get('coordinates')!=np.asarray(self.lib.coords[point]).tolist():differences.append('COORDINATES')
                if cert.get('source_values_sha256')!=fingerprint(detail['source_values']):differences.append('VALUES_DIGEST')
        elif part=='T90':
            if cert.get('bitset_padding_zero') is not True:differences.append('BITSET_PADDING_FLAG')
            classes=self._boolean(candidate,self.tau90);c90=int(np.count_nonzero(classes))
            if type(cert.get('c90')) is not int or cert['c90']!=c90 or c90>=self.k90:differences.append('C90')
            if cert.get('classification_sha256')!=classification_digest(classes):differences.append('BOOLEAN_DIGEST')
        return dict(status='FAIL' if differences else 'PASS',identity=candidate['identity'],ordinal=candidate['ordinal'],
            partition=part,differences=differences,certificate_sha256=fingerprint(cert),
            method='Raw 28 source values for T100; independent Boolean OR/count for priority and T90',
            source_binding_sha256=self.source_binding)

    def selection(self):
        eligible=[v for v in self.expected.values() if v['qualified_for_round21']]
        eligible.sort(key=lambda v:tuple(v['rank']))
        return dict(status='PASS',qualified_count=len(eligible),ranking=[v['identity'] for v in eligible],
            selected_identity=eligible[0]['identity'] if eligible else None)


def family_operations(center,donors):
    families=[]
    for special in [218,1876]:
        family=set()
        for r in center:
            if r in (676,2021):continue
            for b in donors:
                if b in (1440,special):continue
                family.add((tuple(sorted([676,2021,r])),tuple(sorted([1440,special,b]))))
        families.append(family)
    return families

def iter_candidates(center,donors,states,check=lambda:None):
    c,d=_pool(center,donors,states);sets=family_operations(c,d)
    require([len(f) for f in sets]==[55666,55666],'CHECKER_R21_FAMILIES')
    intersection=sets[0]&sets[1]
    require(len(intersection)==26 and all(added==(218,1440,1876) for removed,added in intersection),'CHECKER_R21_INTERSECTIONS')
    all_ops=set.union(*sets);require(len(all_ops)==111306,'CHECKER_R21_UNION_COUNT')
    def order_key(operation):
        removed,added=operation
        return (next(r for r in removed if r not in (676,2021)),tuple(a for a in added if a!=1440))
    for ordinal,(removed,added) in enumerate(sorted(all_ops,key=order_key)):
        if ordinal%512==0:check()
        ids=[i for i in c if i not in removed]+list(added);ids.sort()
        members=['G'+str(n+1) for n,f in enumerate(sets) if (removed,added) in f]
        yield dict(ordinal=ordinal,remove=list(removed),add=list(added),indices=ids,
            identity=fingerprint(sorted(states[i] for i in ids)),family_owner=members[0],families=members)


def terminal_verification(meta,folder,check=lambda:None,prefix=False):
    """Verify durable order and return only the contiguous independently valid prefix."""
    import json
    from pathlib import Path
    from collections import Counter
    folder=Path(folder);truncated=[]
    def records(name):
        path=folder/(name+'.jsonl')
        if not path.exists():return
        with path.open(encoding='utf8') as stream:
            for line in stream:
                if not line.endswith('\n'):
                    require(prefix,'R21_PARTIAL_LINE');truncated.append(name);break
                yield json.loads(line)
    ledger=records('ledger')
    main={p:iter(records(p.lower()+'_certificates' if p!='FULL' else 'candidates')) for p in PARTS}
    checked={p:iter(records(p.lower()+'_certificate_checker' if p!='FULL' else 'checker')) for p in PARTS}
    states={int(i):s for i,s in meta['states'].items()};counts=Counter();verified=Counter();qualified=[];owners=Counter()
    ids=set();order=hashlib.sha256();total=0;prefix_error=None;prefix_failed=False
    iterator=iter_candidates(meta['center_indices'],meta['donor_indices21'],states,check)
    try:
        for spec in iterator:
            row=next(ledger,None)
            if row is None:
                require(prefix,'R21_MISSING_LEDGER');break
            require(not _differences(spec,{k:row.get(k) for k in spec},0),'R21_LEDGER_OPERATION')
            identity=row['identity'];require(identity not in ids,'R21_DUPLICATE_LEDGER')
            part=row['partition'];require(part in PARTS,'R21_PARTITION')
            value=next(main[part],None);audit=next(checked[part],None)
            require(value is not None and audit is not None,'R21_MISSING_EVIDENCE')
            require(not _differences(spec,{k:value.get(k) for k in spec},0),'R21_RECORD_ORDER')
            require(audit['status']=='PASS' and audit['differences']==[] and audit['identity']==identity,'R21_CHECKER_NOT_PASS')
            require(row['record_sha256']==fingerprint(value) and row['checker_sha256']==fingerprint(audit),'R21_LEDGER_HASH')
            if part!='FULL':
                require(audit['partition']==part and audit['certificate_sha256']==fingerprint(value),'R21_CERTIFICATE_BINDING')
                require(value['known_infeasible'] is True and value['full_feasibility_evaluation_performed'] is False,'R21_CERTIFICATE_SEMANTICS')
            else:
                require(audit['main_output_sha256']==fingerprint(_scientific(value)),'R21_FULL_BINDING')
                require(not _differences(_rank(value),audit['rank'],1e-6),'R21_FULL_RANK_TOLERANCE')
                require(type(value['qualified_for_round21']) is bool and value['qualified_for_round21'] is audit['qualified_for_round21'],'R21_FULL_QUALIFICATION')
                hits=np.load(folder/'full_first_hits'/(identity+'.npy'),allow_pickle=False)
                require(hits.shape==(43424,) and _digest(hits)==value['first_hits_sha256'],'R21_FULL_VECTOR')
            ids.add(identity);counts[part]+=1;verified[part]+=1;owners[spec['family_owner']]+=1;total+=1
            if part=='FULL' and value['qualified_for_round21']:qualified.append((tuple(_rank(value)),identity))
            order.update((identity+'\n').encode())
        if not prefix:
            require(next(ledger,None) is None,'R21_EXTRA_LEDGER')
            for stream in list(main.values())+list(checked.values()):require(next(stream,None) is None,'R21_EXTRA_RECORD')
            require(total==111306 and order.hexdigest()==meta['space_summary']['identity_order_sha256'],'R21_COMPLETE_UNION')
    except (ValueError,KeyError,TypeError,OSError) as exc:
        if not prefix:raise
        prefix_error=dict(type=type(exc).__name__,message=str(exc),first_unverified_ordinal=total)
        prefix_failed=str(exc) not in {'R21_MISSING_EVIDENCE','R21_MISSING_LEDGER'}
    qualified.sort()
    return dict(status='FAIL' if prefix_failed else 'PASS',declared_candidates=111306,declared=111306,
        T100_certificate_rejected=counts['T100'],T100_certificate_verified=verified['T100'],
        T90_certificate_rejected=counts['T90'],T90_certificate_verified=verified['T90'],
        fully_evaluated=counts['FULL'],fully_independently_verified=verified['FULL'],
        unprocessed=111306-total,unknown=0,candidate_REUSED=0,qualified_for_round21=len(qualified),
        retained_S=not qualified,selected_identity=qualified[0][1] if qualified else None,
        owner_counts=dict(owners),verified_candidates=total,identity_order_sha256=order.hexdigest(),
        exact_mutually_exclusive_partition_union=not prefix and total==111306,
        prefix_only=prefix,prefix_incomplete=prefix and total!=111306,prefix_error=prefix_error,truncated_final_streams=truncated)
