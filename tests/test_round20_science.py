import copy
import hashlib
import math
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np
from src.round13.common import read,fingerprint
from src.round14.science import regional
from src.round20 import space,science,checker

class SpaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg=read(Path(__file__).resolve().parents[1]/'configs/round20.json')
        meta=read(Path(cfg['r19_delivery'])/'sealed/frozen/contract.json')['metadata']
        cls.c=meta['center_indices'];cls.d=meta['donor_indices19'];cls.states={int(i):s for i,s in meta['states'].items()}
        cls.main=list(space.iter_candidates(cls.c,cls.d,cls.states))
        cls.other=list(checker.iter_candidates(cls.c,cls.d,cls.states))
        cls.sets=checker.family_operations(cls.c,cls.d)
    def test_complete_union_operations_indices_identity_and_order(self):
        self.assertEqual(self.main,self.other);self.assertEqual(len(self.main),173473)
        self.assertEqual(len({r['identity'] for r in self.main}),173473)
    def test_pairwise_and_triple_intersections(self):
        a,b,c=self.sets
        self.assertEqual([len(a&b),len(a&c),len(b&c),len(a&b&c)],[1,27,1,0])
        self.assertEqual([len(a),len(b),len(c)],[57834]*3)
    def test_owner_and_decomposition_counts(self):
        from collections import Counter
        self.assertEqual(Counter(r['family_owner'] for r in self.main),dict(q1=57834,q2=57833,q3=57806))
        self.assertEqual(Counter(Counter(tuple(r['remove']) for r in self.main).values()),{4283:26,2142:26,6423:1})
    def test_deletion_and_corresponding_donor_cannot_be_decoupled(self):
        self.assertEqual(space.families([38,676],[214,2126]),[])
        self.assertEqual(space.families([38,911],[13,1440]),[])
        self.assertEqual(space.families([676,911],[214,1440]),['q1','q2'])
    def test_no_anchor_donor_removal_or_first_removal_reinsertion(self):
        for r in self.main:
            self.assertEqual(len(r['indices']),28)
            self.assertTrue(set(r['remove'])<=set(self.c));self.assertTrue(set(r['add'])<=set(self.d))
            self.assertFalse(set(r['remove'])&set(r['add']))

class GateTests(unittest.TestCase):
    def setUp(self):
        self.center=sorted(list(range(26))+[676,911]);self.donors=[214,386,1440,2126]
        rows={i:np.zeros(43070) for i in self.center+self.donors}
        for a in rows.values():a[0]=np.inf;a[1]=np.inf
        rows[676][0]=0.;rows[911][0]=0.;rows[911][1]=0.
        rows[386][1]=0. # repairs the anchor's point, but not the jointly owned point
        rows[214][1]=597566.;rows[2126][1]=597566.
        self.lib=SimpleNamespace(center_indices=self.center,donor_indices20=self.donors,rows=rows,
            keep=np.ones(43070,dtype=bool),coords=np.zeros((43070,2)),states={i:str(i) for i in rows},
            assets={i:dict(regional_data_sha256='regional-'+str(i)) for i in rows},evidence={'matrix':{'sha256':'matrix'}})
        base={'effective_grid':{'T100_s':595089.,'T90_s':283728.}}
        self.gate=science.Gate(self.lib,base,{'identity':space.S})
        self.audit=object.__new__(checker.IndependentChecker)
        for k,v in dict(lib=self.lib,rows=rows,states=self.lib.states,keep=self.lib.keep,center_indices=self.center,
            tau100=self.gate.tau100,tau90=self.gate.tau90,k90=38763,mask_ids=np.arange(43070),
            source_binding=self.gate.source_binding,center_identity=space.S,mask_sha256=self.gate.mask_sha256,
            coordinate_sha256=self.gate.coordinate_sha256,row_digests=self.gate.row_digests,
            boolean_cache={},donor_boolean_cache={},cache_binding_cache={}).items():setattr(self.audit,k,v)
    def item(self,remove=(676,911),add=(214,386)):
        fs=space.families(remove,add);ids=sorted((set(self.center)-set(remove))|set(add))
        return dict(ordinal=0,remove=list(remove),add=list(add),indices=ids,identity=fingerprint(sorted(self.lib.states[i] for i in ids)),families=fs,family_owner=fs[0])
    def test_joint_owner_point_lost_only_after_double_removal(self):
        self.assertEqual(self.gate.failed100[(676,911)].tolist(),[0,1])
        for removed in [676,911]:
            self.assertLessEqual(min(self.lib.rows[i][0] for i in self.center if i!=removed),self.gate.tau100)
    def test_anchor_repair_does_not_imply_double_swap_pass(self):
        item=self.item();part,cert=self.gate.classify(item)
        self.assertEqual(part,'T100');self.assertEqual(cert['point_id'],0)
        self.assertEqual(self.audit.verify_certificate(item,cert)['status'],'PASS')
    def test_raw28_value_tampering_rejected(self):
        item=self.item();_,cert=self.gate.classify(item);cert['source_values'][0]['first_hit_s']=1.
        self.assertEqual(self.audit.verify_certificate(item,cert)['status'],'FAIL')
    def test_cache_removal_threshold_or_owner_tampering_rejected(self):
        item=self.item();_,cert=self.gate.classify(item)
        for key,value in [('cache_binding_sha256','wrong'),('tau100',0.),('family_owner','q3'),('candidate_binding_sha256','wrong')]:
            tampered=copy.deepcopy(cert);tampered[key]=value
            self.assertEqual(self.audit.verify_certificate(item,tampered)['status'],'FAIL')
    def test_certificate_not_full_and_metrics_stay_unknown(self):
        _,cert=self.gate.classify(self.item())
        self.assertIs(cert['known_infeasible'],True);self.assertIs(cert['full_feasibility_evaluation_performed'],False)
        self.assertIsNone(cert['T100_s']);self.assertIsNone(cert['regional'])
    def test_finite_late_and_no_first_hit_distinct(self):
        result=checker.verify_t100_witness({0:[597566.],1:[np.inf]},[0,1],0,595089.)
        self.assertEqual([r['classification'] for r in result['source_values']],['FINITE_LATE','NO_FIRST_HIT'])
        self.assertEqual(result['source_values'][0]['first_hit_s'],597566.);self.assertIsNone(result['source_values'][1]['first_hit_s'])
    def test_cutoff_equality_is_included(self):
        tau=123.;bits=science.pack_on_time(np.array([tau,np.nextafter(tau,np.inf),np.inf]),tau)
        self.assertEqual(bits,1)
    def test_t90_38762_38763_boundary_and_padding(self):
        self.assertEqual(science.count_bits((1<<38762)-1,0,0,43070),38762)
        self.assertEqual(science.count_bits((1<<38762)-1,1<<38762,0,43070),38763)
        with self.assertRaisesRegex(ValueError,'PADDING'):science.count_bits(1<<43070,0,0,43070)
    def test_bad_hit_values_rejected(self):
        for v in [float('nan'),-math.inf,-1.,604801.]:
            with self.assertRaises(ValueError):science.pack_on_time(np.array([v]),10.)

class MetricTests(unittest.TestCase):
    def test_actual_gap_denominator(self):
        result=regional({'a':[[0.,1.],[3.,4.],[7.,8.]],'b':[[0.,1.],[10.,11.]]},['a','b'])
        self.assertEqual(result['pooled_internal']['gap_count'],3)
        self.assertEqual(result['pooled_internal']['mean_s'],14/3)
    def test_B0_feasibility_and_S_improvement_are_separate(self):
        r=dict(feasibility=dict(feasible=True,rejection_reasons=[]),improvement={'substantive_improvement':True},
            regional={'pooled_internal':{'max_s':99.5,'mean_s':10.}},effective_grid={'T100_s':100.,'T90_s':90.},identity='x')
        s={'identity':space.S,'regional':{'pooled_internal':{'max_s':100.}}}
        science.annotate(r,s);self.assertFalse(r['qualified_for_round20'])
        r['regional']['pooled_internal']['max_s']=98.;science.annotate(r,s);self.assertTrue(r['qualified_for_round20'])
        r['feasibility']['feasible']=False;science.annotate(r,s);self.assertFalse(r['qualified_for_round20'])
    def test_numeric_tolerance_does_not_relax_identity_or_boolean(self):
        self.assertEqual(checker._differences([10.,'x',True],[10.+1e-7,'x',True],1e-6),[])
        for val in [[10.+2e-6,'x',True],[10.,'y',True],[10.,'x',1]]:
            self.assertTrue(checker._differences([10.,'x',True],val,1e-6))
    def test_ranking_uses_exact_floats(self):
        reports=[dict(qualified_for_round20=True,ranking_key=[1.,2.,3.,4.,'a']),
            dict(qualified_for_round20=True,ranking_key=[1.-1e-8,2.,3.,4.,'b'])]
        self.assertIs(science.select(reports),reports[1])

if __name__=='__main__':unittest.main()
