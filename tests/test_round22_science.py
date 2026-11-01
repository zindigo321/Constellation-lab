import copy
import hashlib
import itertools
import math
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np
from src.round13.common import read, fingerprint
from src.round14.science import regional
from src.round22 import space, science, checker


class SpaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]
        cfg=read(root/'configs/round21.json')
        meta=read(Path(cfg['preferred_output'])/Path(cfg['prepared_work']).name/'sealed/frozen/contract.json')['metadata']
        cls.c=meta['center_indices'];cls.d=meta['donor_indices21']
        cls.states={int(i):s for i,s in meta['states'].items()}
        cls.main=list(space.iter_candidates(cls.c,cls.d,cls.states))
        cls.sets=checker.family_operations(cls.c,cls.d)

    def test_complete_independent_union_operations_indices_identity_and_order(self):
        count=0
        for actual,expected in itertools.zip_longest(self.main,checker.iter_candidates(self.c,self.d,self.states)):
            self.assertEqual(actual,expected);count+=1
        self.assertEqual(count,173499)
        self.assertEqual(len({v['identity'] for v in self.main}),173499)

    def test_three_families_pairwise_singletons_and_no_triple(self):
        self.assertEqual([len(s) for s in self.sets],[57834]*3)
        for i,j in itertools.combinations(range(3),2):
            expected={(tuple(sorted([space.ANCHORS[i][1],space.ANCHORS[j][1]])),tuple(sorted([space.ANCHORS[i][2],space.ANCHORS[j][2]])))}
            self.assertEqual(self.sets[i]&self.sets[j],expected)
        self.assertEqual(set.intersection(*self.sets),set())

    def test_exact_78_deletion_pairs_and_owner_counts(self):
        pairs=Counter(tuple(v['remove']) for v in self.main)
        self.assertEqual(len(pairs),78);self.assertEqual(Counter(pairs.values()),{2142:75,4283:3})
        self.assertEqual(Counter(v['family_owner'] for v in self.main),dict(q1=57834,q2=57833,q3=57832))

    def test_global_numeric_pair_order_and_two_anchor_deduplication(self):
        keys=[(tuple(v['remove']),tuple(v['add'])) for v in self.main]
        self.assertEqual(keys,sorted(keys))
        self.assertEqual(sum(len(v['families'])==2 for v in self.main),3)

    def test_removal_and_its_corresponding_donor_must_be_coupled(self):
        self.assertEqual(space.families([1412,2021],[1118,1123]),['q1','q2'])
        self.assertEqual(space.families([0,1412],[1123,1200]),[])
        self.assertEqual(space.families([1941,2021],[1118,1200]),['q3'])

    def test_exact_two_swap_and_no_historical_filter(self):
        for v in self.main:
            self.assertEqual(len(v['indices']),28);self.assertEqual(len(set(v['indices'])^set(self.c)),4)
            self.assertTrue(set(v['remove'])<=set(self.c));self.assertTrue(set(v['add'])<=set(self.d))
        self.assertEqual(len(self.main),173499)
        summary=space.summary(self.c,self.d,self.states)
        self.assertIs(summary['history_filter_applied'],False)
        self.assertEqual(summary['candidate_REUSED'],0)
        self.assertIs(summary['earlier_identity_disjointness_claimed'],False)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.center=sorted(list(range(25))+[1412,1941,2021]);self.donors=[386,1118,1123,1200]
        rows={i:np.zeros(43070) for i in self.center+self.donors}
        for a in rows.values():a[:2]=np.inf
        # Point zero is jointly owned by both deleted S assets, never singly exclusive.
        rows[1412][0]=0.;rows[0][0]=0.
        # Point one is repaired by the fixed anchor donor, unlike point zero.
        rows[1412][1]=0.;rows[1118][1]=0.;rows[386][1]=597566.
        self.lib=SimpleNamespace(center_indices=self.center,donor_indices22=self.donors,rows=rows,
            keep=np.ones(43070,dtype=bool),coords=np.zeros((43070,2)),states={i:str(i) for i in rows},
            assets={i:dict(regional_data_sha256='regional-'+str(i)) for i in rows},evidence={'matrix':{'sha256':'matrix'}})
        self.base={'effective_grid':{'T100_s':595089.,'T90_s':283728.}}
        self.rebuild()

    def rebuild(self):
        self.gate=science.Gate(self.lib,self.base,{'identity':space.S})
        self.audit=object.__new__(checker.IndependentChecker)
        for k,v in dict(lib=self.lib,rows=self.lib.rows,states=self.lib.states,keep=self.lib.keep,center_indices=self.center,
            tau100=self.gate.tau100,tau90=self.gate.tau90,k90=38763,mask_ids=np.arange(43070),
            source_binding=self.gate.source_binding,center_identity=space.S,mask_sha256=self.gate.mask_sha256,
            coordinate_sha256=self.gate.coordinate_sha256,row_digests=self.gate.row_digests,
            boolean_cache={},donor_boolean_cache={},cache_binding_cache={}).items():setattr(self.audit,k,v)

    def item(self,remove=(0,1412),add=(386,1118)):
        fs=space.families(remove,add);ids=sorted((set(self.center)-set(remove))|set(add))
        return dict(ordinal=0,remove=list(remove),add=list(add),indices=ids,identity=fingerprint(sorted(self.lib.states[i] for i in ids)),
            families=fs,family_owner=fs[0])

    def test_joint_owner_point_creates_new_hole_after_second_deletion(self):
        self.assertEqual(self.gate.failed100[(0,1412)].tolist(),[0,1])
        for removed in [(1412,),(0,)]:
            self.assertLessEqual(min(self.lib.rows[i][0] for i in self.center if i not in removed),self.gate.tau100)
        part,cert=self.gate.classify(self.item())
        self.assertEqual(part,'T100');self.assertEqual(cert['point_id'],0)
        self.assertEqual(self.lib.rows[1118][1],0.)

    def test_complete_26_row_cache_and_source28_certificate(self):
        item=self.item();part,cert=self.gate.classify(item)
        self.assertEqual(part,'T100');self.assertEqual(len(cert['source_values']),28)
        self.assertEqual(self.audit.verify_certificate(item,cert)['status'],'PASS')
        self.assertEqual(self.gate.cache_bindings[tuple(item['remove'])],self.audit.cache_binding(item['remove']))

    def test_wrong_cache_pair_owner_and_original28_tampering_rejected(self):
        item=self.item();_,cert=self.gate.classify(item)
        for key,value in [('cache_binding_sha256',self.gate.cache_bindings[(1,1412)]),('family_owner','q2'),
                ('candidate_binding_sha256','bad'),('tau100',0.)]:
            bad=copy.deepcopy(cert);bad[key]=value
            self.assertEqual(self.audit.verify_certificate(item,bad)['status'],'FAIL')
        bad=copy.deepcopy(cert);bad['source_values'][0]['first_hit_s']=0.
        self.assertEqual(self.audit.verify_certificate(item,bad)['status'],'FAIL')

    def test_mismatched_anchor_operations_rejected(self):
        item=self.item();item.update(add=[1123,1200])
        item['indices']=sorted((set(self.center)-set(item['remove']))|set(item['add']))
        item['identity']=fingerprint(sorted(self.lib.states[i] for i in item['indices']))
        with self.assertRaisesRegex(ValueError,'FAMILY_BINDING'):self.gate.classify(item)

    def test_certificate_protocol_and_integer_boolean_types_are_exact(self):
        item=self.item();_,cert=self.gate.classify(item)
        for key,value in [('new_native_validation_performed',0),('whole_constellation_STK_verified',0),('known_infeasible',1)]:
            bad=copy.deepcopy(cert);bad[key]=value
            self.assertEqual(self.audit.verify_certificate(item,bad)['status'],'FAIL')
        bad=copy.deepcopy(cert);bad['indices'][bad['indices'].index(1)]=True
        self.assertEqual(self.audit.verify_certificate(item,bad)['status'],'FAIL')

    def test_T90_actual_candidate_count_and_padding_flag(self):
        for row in self.lib.rows.values():row[:5000]=500000.
        self.rebuild();item=self.item();part,cert=self.gate.classify(item)
        self.assertEqual(part,'T90');self.assertEqual(cert['c90'],38070)
        self.assertEqual(self.audit.verify_certificate(item,cert)['status'],'PASS')
        for value in [False,1]:
            bad=copy.deepcopy(cert);bad['bitset_padding_zero']=value
            self.assertEqual(self.audit.verify_certificate(item,bad)['status'],'FAIL')

    def test_negative_certificate_does_not_claim_full_metrics(self):
        _,cert=self.gate.classify(self.item())
        self.assertIs(cert['known_infeasible'],True);self.assertIs(cert['full_feasibility_evaluation_performed'],False)
        for key in ['T90_s','T100_s','Tavg_s','Tmax_s','regional','full_grid','effective_grid']:
            self.assertIsNone(cert[key])

    def test_finite_late_is_distinct_from_no_first_hit(self):
        result=checker.verify_t100_witness({0:[595920.2685995891],1:[np.inf]},[0,1],0,595089.)
        self.assertEqual([v['classification'] for v in result['source_values']],['FINITE_LATE','NO_FIRST_HIT'])
        self.assertIsNone(result['source_values'][1]['first_hit_s'])

    def test_T90_cutoff_equality_and_38762_38763_padding(self):
        tau=123.;self.assertEqual(science.pack_on_time(np.array([tau,np.nextafter(tau,np.inf),np.inf]),tau),1)
        self.assertEqual(science.count_bits((1<<38762)-1,0,0,43070),38762)
        self.assertEqual(science.count_bits((1<<38762)-1,1<<38762,0,43070),38763)
        with self.assertRaisesRegex(ValueError,'PADDING'):science.count_bits(1<<43070,0,0,43070)

    def test_invalid_sentinels_and_window_are_rejected(self):
        for v in [math.nan,-math.inf,-1.,604801.]:
            with self.assertRaises(ValueError):science.pack_on_time(np.array([v]),10.)

    def test_T90_checker_counts_original_arrays_and_rejects_at_threshold(self):
        values=np.full(43070,np.inf);values[:38762]=123.;keep=np.ones(43070,dtype=bool)
        digest=checker.classification_digest(values<=123.)
        self.assertEqual(checker.verify_t90_count({0:values},[0],keep,123.,38763,38762,digest)['status'],'PASS')
        values[38762]=123.;digest=checker.classification_digest(values<=123.)
        self.assertEqual(checker.verify_t90_count({0:values},[0],keep,123.,38763,38763,digest)['status'],'FAIL')


class MetricTests(unittest.TestCase):
    def test_candidate_actual_gap_denominator(self):
        result=regional({'a':[[0.,1.],[3.,4.],[7.,8.]],'b':[[0.,1.],[10.,11.]]},['a','b'])
        self.assertEqual(result['pooled_internal']['gap_count'],3)
        self.assertEqual(result['pooled_internal']['mean_s'],14/3)

    def test_B0_feasibility_and_S_improvement_are_separate(self):
        r=dict(feasibility=dict(feasible=True,rejection_reasons=[]),improvement={'substantive_improvement':True},
            regional={'pooled_internal':{'max_s':99.5,'mean_s':10.}},effective_grid={'T100_s':100.,'T90_s':90.},identity='x')
        s={'identity':space.S,'regional':{'pooled_internal':{'max_s':100.}}}
        science.annotate(r,s);self.assertFalse(r['qualified_for_round22'])
        r['regional']['pooled_internal']['max_s']=98.;science.annotate(r,s);self.assertTrue(r['qualified_for_round22'])
        r['feasibility']['feasible']=False;science.annotate(r,s);self.assertFalse(r['qualified_for_round22'])

    def test_ranking_preserves_sub_tolerance_float_order(self):
        reports=[dict(qualified_for_round22=True,ranking_key=[1.,2.,3.,4.,'a']),
            dict(qualified_for_round22=True,ranking_key=[1.-1e-8,2.,3.,4.,'b'])]
        self.assertIs(science.select(reports),reports[1])

    def test_identity_boolean_and_numeric_tolerance_are_separate(self):
        self.assertEqual(checker._differences([10.,'x',True],[10.+1e-7,'x',True],1e-6),[])
        for val in [[10.+2e-6,'x',True],[10.,'y',True],[10.,'x',1]]:
            self.assertTrue(checker._differences([10.,'x',True],val,1e-6))

    def test_three_infeasible_anchors_can_never_be_selected(self):
        center={'identity':space.S,'regional':{'pooled_internal':{'max_s':132051.28738869302}}}
        reports=[]
        for label,_,_,identity in space.ANCHORS:
            r=dict(identity=identity,feasibility=dict(feasible=False,rejection_reasons=['MASK_NOT_EXACT_FULL_COVERAGE']),
                improvement={'substantive_improvement':True},regional={'pooled_internal':{'max_s':86000.,'mean_s':9200.}},
                effective_grid={'T100_s':None,'T90_s':280000.})
            science.annotate(r,center);self.assertIs(r['qualified_for_round22'],False);reports.append(r)
        self.assertIsNone(science.select(reports))

    def test_q3_planning_failure_and_true_113_deficit_are_diagnostic_only(self):
        cfg=read(Path(__file__).resolve().parents[1]/'configs/round22.json')
        q=read(Path(cfg['r22_plan'])/'evidence/existing_anchor_diagnostics.json')['anchors'][2]
        self.assertIsNone(q['existing_mask_metrics']['T100_s'])
        self.assertGreater(q['existing_mask_metrics']['T90_s'],283728.33914436615+1e-6)
        self.assertEqual(q['existing_T90_hit_count'],38650);self.assertEqual(q['existing_T90_deficit'],113)


if __name__=='__main__':unittest.main()
