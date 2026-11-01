"""R23 real combinatorial space and synthetic failure-boundary regressions."""
import copy
import itertools
import math
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np
from src.round13.common import read, fingerprint
from src.round14.science import regional
from src.round23 import space, science, checker


class SpaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = read(Path(__file__).resolve().parents[1]/'configs/round23.json')
        meta = read(Path(cfg['r22_delivery'])/'sealed/frozen/contract.json')['metadata']
        cls.c = meta['center_indices']
        cls.d = sorted(set(meta['pool_indices'])-set(cls.c))
        cls.states = {int(i):s for i,s in meta['states'].items()}
        cls.main = list(space.iter_candidates(cls.c,cls.d,cls.states))
        cls.sets = checker.family_operations(cls.c,cls.d)

    def test_complete_independent_union_operations_indices_identity_and_order(self):
        count = 0
        for actual, expected in itertools.zip_longest(self.main,checker.iter_candidates(self.c,self.d,self.states)):
            self.assertEqual(actual,expected)
            count += 1
        self.assertEqual(count,166970)
        self.assertEqual(len({v['identity'] for v in self.main}),166970)

    def test_exact_family_intersections_and_no_triple(self):
        self.assertEqual([len(s) for s in self.sets],[55666]*3)
        r = (676,1412,1941)
        self.assertEqual(self.sets[0]&self.sets[1],{(r,(2,196,1118))})
        self.assertEqual(self.sets[0]&self.sets[2],{(r,(196,640,1118))})
        expected = {(tuple(sorted([1412,1941,i])),(2,640,1118)) for i in self.c if i not in {1412,1941}}
        self.assertEqual(self.sets[1]&self.sets[2],expected)
        self.assertEqual(set.intersection(*self.sets),set())

    def test_51_deletion_triples_combinatorial_types_and_exact_owner(self):
        triples = Counter(tuple(v['remove']) for v in self.main)
        self.assertEqual(len(triples),51)
        self.assertEqual(Counter(triples.values()),{2141:25,4281:25,6420:1})
        self.assertEqual(Counter(v['family_owner'] for v in self.main),dict(p1=55666,p2=55665,p3=55639))
        self.assertEqual(sum(len(v['families'])==2 for v in self.main),28)

    def test_canonical_numeric_order_and_first_last_operations(self):
        keys = [(tuple(v['remove']),tuple(v['add'])) for v in self.main]
        self.assertEqual(keys,sorted(keys))
        self.assertEqual(keys[0],((38,676,1412),(0,196,1118)))
        self.assertEqual(keys[-1],((1412,1941,2092),(640,1118,2170)))

    def test_same_anchor_removal_and_addition_must_be_coupled(self):
        self.assertEqual(space.families([38,676,1412],[2,640,1118]),[])
        self.assertEqual(space.families([676,1412,1941],[2,196,1118]),['p1','p2'])
        self.assertEqual(space.families([38,1412,1941],[2,640,1118]),['p2','p3'])

    def test_final_sets_are_three_swap_no_history_exclusion_and_no_r21_overlap(self):
        for v in self.main:
            self.assertEqual(len(v['indices']),28)
            self.assertEqual(len(set(v['indices'])^set(self.c)),6)
            self.assertTrue(set(v['remove'])<=set(self.c))
            self.assertTrue(set(v['add'])<=set(self.d))
            self.assertFalse(1440 in v['add'] and (218 in v['add'] or 1876 in v['add']))
        summary = space.summary(self.c,self.d,self.states)
        self.assertIs(summary['history_filter_applied'],False)
        self.assertEqual(summary['candidate_REUSED'],0)
        self.assertIs(summary['earlier_identity_disjointness_claimed'],False)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.center = list(range(100,125))+[676,1412,1941]
        self.donors = [2,196,640,1118]
        rows = {i:np.zeros(43070) for i in self.center+self.donors}
        for values in rows.values():
            values[:2] = np.inf
        # No single removal loses point 0, but removal of all three owners does.
        for owner in [100,676,1412]:
            rows[owner][0] = 0.
        rows[1412][1] = 0.
        rows[1118][1] = 0.
        self.lib = SimpleNamespace(center_indices=self.center,donor_indices23=self.donors,rows=rows,
            keep=np.ones(43070,dtype=bool),coords=np.zeros((43070,2)),states={i:str(i) for i in rows},
            assets={i:dict(regional_data_sha256='regional-'+str(i)) for i in rows},evidence={'matrix':{'sha256':'matrix'}})
        self.base = {'effective_grid':{'T100_s':595089.,'T90_s':283728.}}
        self.rebuild()

    def rebuild(self):
        self.gate = science.Gate(self.lib,self.base,{'identity':space.S})
        self.audit = object.__new__(checker.IndependentChecker)
        for key,value in dict(lib=self.lib,rows=self.lib.rows,states=self.lib.states,keep=self.lib.keep,
            center_indices=self.center,tau100=self.gate.tau100,tau90=self.gate.tau90,k90=38763,
            mask_ids=np.arange(43070),source_binding=self.gate.source_binding,center_identity=space.S,
            mask_sha256=self.gate.mask_sha256,coordinate_sha256=self.gate.coordinate_sha256,
            row_digests=self.gate.row_digests,boolean_cache={},donor_boolean_cache={},
            cache_binding_cache={},minimum_cache={}).items():
            setattr(self.audit,key,value)

    def item(self,remove=(100,676,1412),add=(196,640,1118)):
        fs = space.families(remove,add)
        ids = sorted((set(self.center)-set(remove))|set(add))
        return dict(ordinal=0,remove=list(remove),add=list(add),indices=ids,
            identity=fingerprint(sorted(self.lib.states[i] for i in ids)),families=fs,family_owner=fs[0])

    def test_joint_three_owner_loss_is_rebuilt_from_retained25(self):
        self.assertEqual(self.gate.failed100[(100,676,1412)].tolist(),[0,1])
        for owner in [100,676,1412]:
            self.assertEqual(min(self.lib.rows[i][0] for i in self.center if i!=owner),0.)
        part, cert = self.gate.classify(self.item())
        self.assertEqual(part,'T100')
        self.assertEqual(cert['point_id'],0)

    def test_retained25_cache_and_original28_independent_witness_agree(self):
        item = self.item()
        part,cert = self.gate.classify(item)
        self.assertEqual(part,'T100')
        self.assertEqual(len(cert['source_values']),28)
        self.assertEqual(self.audit.verify_certificate(item,cert)['status'],'PASS')
        self.assertEqual(self.gate.cache_bindings[tuple(item['remove'])],self.audit.cache_binding(item['remove']))

    def test_wrong_triple_owner_threshold_and_original_value_are_rejected(self):
        item = self.item()
        _,cert = self.gate.classify(item)
        for key,value in [('cache_binding_sha256',self.gate.cache_bindings[(101,676,1412)]),
                ('family_owner','p2'),('candidate_binding_sha256','bad'),('tau100',0.)]:
            bad = copy.deepcopy(cert)
            bad[key] = value
            self.assertEqual(self.audit.verify_certificate(item,bad)['status'],'FAIL')
        bad = copy.deepcopy(cert)
        bad['source_values'][0]['first_hit_s'] = 0.
        self.assertEqual(self.audit.verify_certificate(item,bad)['status'],'FAIL')

    def test_mismatched_anchor_operations_cannot_be_classified(self):
        item = self.item()
        item['add'] = [2,640,1118]
        item['indices'] = sorted((set(self.center)-set(item['remove']))|set(item['add']))
        item['identity'] = fingerprint(sorted(self.lib.states[i] for i in item['indices']))
        with self.assertRaisesRegex(ValueError,'FAMILY_BINDING'):
            self.gate.classify(item)

    def test_certificate_flags_and_index_types_are_exact(self):
        item = self.item()
        _,cert = self.gate.classify(item)
        for key,value in [('new_native_validation_performed',0),('whole_constellation_STK_verified',0),('known_infeasible',1)]:
            bad = copy.deepcopy(cert)
            bad[key] = value
            self.assertEqual(self.audit.verify_certificate(item,bad)['status'],'FAIL')
        bad = copy.deepcopy(cert)
        bad['indices'][0] = True
        self.assertEqual(self.audit.verify_certificate(item,bad)['status'],'FAIL')

    def test_T90_original28_count_and_padding_are_independently_verified(self):
        for values in self.lib.rows.values():
            values[:5000] = 500000.
        self.rebuild()
        item = self.item()
        part,cert = self.gate.classify(item)
        self.assertEqual(part,'T90')
        self.assertEqual(cert['c90'],38070)
        self.assertEqual(self.audit.verify_certificate(item,cert)['status'],'PASS')
        for value in [False,1]:
            bad = copy.deepcopy(cert)
            bad['bitset_padding_zero'] = value
            self.assertEqual(self.audit.verify_certificate(item,bad)['status'],'FAIL')

    def test_negative_certificate_never_claims_uncomputed_FULL_metrics(self):
        _,cert = self.gate.classify(self.item())
        self.assertIs(cert['known_infeasible'],True)
        self.assertIs(cert['full_feasibility_evaluation_performed'],False)
        for key in ['T90_s','T100_s','Tavg_s','Tmax_s','regional','full_grid','effective_grid']:
            self.assertIsNone(cert[key])

    def test_finite_late_and_no_first_hit_have_distinct_classification(self):
        result = checker.verify_t100_witness({0:[595920.2685995891],1:[np.inf]},[0,1],0,595089.)
        self.assertEqual([v['classification'] for v in result['source_values']],['FINITE_LATE','NO_FIRST_HIT'])
        self.assertIsNone(result['source_values'][1]['first_hit_s'])

    def test_cutoff_equality_ceil_and_all_padding_bits(self):
        tau = 123.
        self.assertEqual(science.pack_on_time(np.array([tau,np.nextafter(tau,np.inf),np.inf]),tau),1)
        self.assertEqual(math.ceil(.9*43070),38763)
        self.assertEqual(science.count_bits((1<<38762)-1,0,0,0,43070),38762)
        self.assertEqual(science.count_bits((1<<38762)-1,1<<38762,0,0,43070),38763)
        with self.assertRaisesRegex(ValueError,'PADDING'):
            science.count_bits(1<<43070,0,0,0,43070)

    def test_invalid_source_sentinels_and_out_of_window_times_rejected(self):
        for value in [math.nan,-math.inf,-1.,604801.]:
            with self.assertRaises(ValueError):
                science.pack_on_time(np.array([value]),10.)

    def test_T90_negative_certificate_rejects_exactly_k90_covered(self):
        values = np.full(43070,np.inf)
        values[:38762] = 123.
        keep = np.ones(43070,dtype=bool)
        digest = checker.classification_digest(values<=123.)
        self.assertEqual(checker.verify_t90_count({0:values},[0],keep,123.,38763,38762,digest)['status'],'PASS')
        values[38762] = 123.
        digest = checker.classification_digest(values<=123.)
        self.assertEqual(checker.verify_t90_count({0:values},[0],keep,123.,38763,38763,digest)['status'],'FAIL')


class MetricTests(unittest.TestCase):
    def test_actual_gap_denominator_pools_gaps_across_targets(self):
        result = regional({'a':[[0.,1.],[3.,4.],[7.,8.]],'b':[[0.,1.],[10.,11.]]},['a','b'])
        self.assertEqual(result['pooled_internal']['gap_count'],3)
        self.assertEqual(result['pooled_internal']['mean_s'],14/3)

    def test_B0_feasibility_and_conservative_one_second_S_gate_are_separate(self):
        report = dict(feasibility=dict(feasible=True,rejection_reasons=[]),improvement={'substantive_improvement':True},
            regional={'pooled_internal':{'max_s':99.,'mean_s':10.}},effective_grid={'T100_s':100.,'T90_s':90.},identity='x')
        center = {'identity':space.S,'regional':{'pooled_internal':{'max_s':100.}}}
        science.annotate(report,center)
        self.assertFalse(report['qualified_for_round23'])
        report['regional']['pooled_internal']['max_s'] = 98.999998
        science.annotate(report,center)
        self.assertTrue(report['qualified_for_round23'])
        report['feasibility']['feasible'] = False
        science.annotate(report,center)
        self.assertFalse(report['qualified_for_round23'])

    def test_exact_rank_and_unqualified_fallback(self):
        reports = [dict(qualified_for_round23=True,ranking_key=[1.,2.,3.,4.,'a']),
            dict(qualified_for_round23=True,ranking_key=[1.-1e-8,2.,3.,4.,'b'])]
        self.assertIs(science.select(reports),reports[1])
        self.assertIsNone(science.select([dict(qualified_for_round23=False,ranking_key=[0.,0.,0.,0.,'x'])]))

    def test_identity_boolean_integer_and_floating_tolerance_are_separate(self):
        self.assertEqual(checker._differences([10.,'x',True],[10.+1e-7,'x',True],1e-6),[])
        for value in [[10.+2e-6,'x',True],[10.,'y',True],[10.,'x',1]]:
            self.assertTrue(checker._differences([10.,'x',True],value,1e-6))

    def test_all_three_infeasible_anchors_are_excluded_from_selection(self):
        center = {'identity':space.S,'regional':{'pooled_internal':{'max_s':132051.28738869302}}}
        reports = []
        for label,_,_,identity in space.ANCHORS:
            report = dict(identity=identity,feasibility=dict(feasible=False,rejection_reasons=['T90_EXCEEDS_B0']),
                improvement={'substantive_improvement':True},regional={'pooled_internal':{'max_s':130560.,'mean_s':9250.}},
                effective_grid={'T100_s':595089.,'T90_s':285000.})
            science.annotate(report,center)
            self.assertIs(report['qualified_for_round23'],False)
            reports.append(report)
        self.assertIsNone(science.select(reports))


if __name__ == '__main__':
    unittest.main()
