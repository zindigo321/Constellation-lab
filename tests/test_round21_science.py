import copy
import hashlib
import math
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np
from src.round13.common import read,fingerprint
from src.round14.science import regional
from src.round21 import space,science,checker,inputs

class SpaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg=read(Path(__file__).resolve().parents[1]/'configs/round21.json')
        meta=read(Path(cfg['r20_delivery'])/'sealed/frozen/contract.json')['metadata']
        cls.c=meta['center_indices'];cls.d=meta['donor_indices20'];cls.states={int(i):s for i,s in meta['states'].items()}
        cls.main=list(space.iter_candidates(cls.c,cls.d,cls.states))
        cls.other=list(checker.iter_candidates(cls.c,cls.d,cls.states))
        cls.sets=checker.family_operations(cls.c,cls.d)
    def test_complete_union_operations_indices_identity_and_order(self):
        self.assertEqual(self.main,self.other);self.assertEqual(len(self.main),111306)
        self.assertEqual(len({r['identity'] for r in self.main}),111306)
    def test_two_family_intersection_and_sizes(self):
        first,second=self.sets
        self.assertEqual([len(first),len(second),len(first&second)],[55666,55666,26])
        self.assertTrue(all(add==(218,1440,1876) for remove,add in first&second))
    def test_owner_and_per_r_counts(self):
        from collections import Counter
        self.assertEqual(Counter(row['family_owner'] for row in self.main),dict(G1=55666,G2=55640))
        self.assertEqual(set(Counter(tuple(row['remove']) for row in self.main).values()),{4281})
    def test_pair_order_and_special_pair_deduplication(self):
        keys=[(next(r for r in row['remove'] if r not in (676,2021)),tuple(a for a in row['add'] if a!=1440)) for row in self.main]
        self.assertEqual(keys,sorted(keys))
        self.assertEqual(sum(row['add']==[218,1440,1876] for row in self.main),26)
    def test_fixed_deletions_donor_and_family_are_coupled(self):
        self.assertEqual(space.families([38,676,2021],[218,1440,1876]),['G1','G2'])
        self.assertEqual(space.families([38,676,2021],[13,1440,214]),[])
        self.assertEqual(space.families([38,676,1440],[218,1440,1876]),[])
        self.assertEqual(space.families([38,676,2021],[218,1440,2021]),[])
    def test_exact_three_swap_and_historical_difference(self):
        for row in self.main:
            self.assertEqual(len(row['indices']),28)
            self.assertTrue(set(row['remove'])<=set(self.c));self.assertTrue(set(row['add'])<=set(self.d))
            self.assertTrue({676,2021}<=set(row['remove']));self.assertIn(1440,row['add'])
            self.assertFalse(set(row['remove'])&set(row['add']))
            self.assertEqual(len(set(row['indices'])^set(self.c)),6)
            self.assertNotIn(len(set(row['indices'])^set(self.c)),[2,4])

class GateTests(unittest.TestCase):
    def setUp(self):
        self.center=sorted(list(range(26))+[676,2021]);self.donors=[218,386,1440,1876]
        rows={i:np.zeros(43070) for i in self.center+self.donors}
        for a in rows.values():a[0]=np.inf;a[1]=np.inf
        rows[676][0]=0.;rows[2021][0]=0.;rows[0][0]=0.;rows[676][1]=0.;rows[1440][1]=0.
        rows[386][1]=597566. # fixed1440 repairs this point; donor386 cannot
        rows[218][1]=597566.;rows[1876][1]=597566.
        self.lib=SimpleNamespace(center_indices=self.center,donor_indices21=self.donors,rows=rows,
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
    def item(self,remove=(0,676,2021),add=(218,386,1440)):
        fs=space.families(remove,add);ids=sorted((set(self.center)-set(remove))|set(add))
        return dict(ordinal=0,remove=list(remove),add=list(add),indices=ids,identity=fingerprint(sorted(self.lib.states[i] for i in ids)),families=fs,family_owner=fs[0])
    def test_joint_three_owner_point_lost_only_after_all_three_removed(self):
        self.assertEqual(self.gate.failed100[(0,676,2021)].tolist(),[0])
        for removed in [(676,2021),(0,676),(0,2021)]:
            self.assertLessEqual(min(self.lib.rows[i][0] for i in self.center if i not in removed),self.gate.tau100)
    def test_fixed1440_is_in_cache_and_25_plus3_equals_26_plus2(self):
        remove=(0,676,2021);retained=[i for i in self.center if i not in remove]
        full=checker.boolean_on_time(self.lib.rows,retained+[218,386,1440],self.lib.keep,self.gate.tau100)
        accelerated=checker.boolean_on_time(self.lib.rows,retained+[1440],self.lib.keep,self.gate.tau100)
        accelerated|=self.lib.rows[218]<=self.gate.tau100;accelerated|=self.lib.rows[386]<=self.gate.tau100
        self.assertTrue(np.array_equal(full,accelerated));self.assertTrue(full[1]);self.assertFalse(full[0])
        self.assertEqual(len(retained),25)
    def test_triple_swap_certificate_from_original28_values(self):
        item=self.item();part,cert=self.gate.classify(item)
        self.assertEqual(part,'T100');self.assertEqual(cert['point_id'],0);self.assertEqual(len(cert['source_values']),28)
        self.assertEqual(self.audit.verify_certificate(item,cert)['status'],'PASS')
    def test_missing_fixed_donor_is_rejected(self):
        item=self.item();item['add']=[218,386,1876]
        with self.assertRaisesRegex(ValueError,'OPERATION'):self.gate.classify(item)
    def test_raw28_value_tampering_rejected(self):
        item=self.item();_,cert=self.gate.classify(item);cert['source_values'][0]['first_hit_s']=1.
        self.assertEqual(self.audit.verify_certificate(item,cert)['status'],'FAIL')
    def test_cache_removal_threshold_or_owner_tampering_rejected(self):
        item=self.item();_,cert=self.gate.classify(item)
        for key,value in [('cache_binding_sha256','wrong'),('tau100',0.),('family_owner','G2'),('candidate_binding_sha256','wrong')]:
            tampered=copy.deepcopy(cert);tampered[key]=value
            self.assertEqual(self.audit.verify_certificate(item,tampered)['status'],'FAIL')
    def test_certificate_protocol_flags_and_nested_index_types_exact(self):
        item=self.item();_,cert=self.gate.classify(item)
        for key,value in [('source','native'),('new_native_validation_performed',0),('whole_constellation_STK_verified',0)]:
            tampered=copy.deepcopy(cert);tampered[key]=value
            self.assertEqual(self.audit.verify_certificate(item,tampered)['status'],'FAIL')
        tampered=copy.deepcopy(cert)
        position=tampered['indices'].index(1);tampered['indices'][position]=True
        self.assertEqual(self.audit.verify_certificate(item,tampered)['status'],'FAIL')
    def test_T90_certificate_and_padding_flag_verified_independently(self):
        for row in self.lib.rows.values():row[:5000]=500000.
        base={'effective_grid':{'T100_s':595089.,'T90_s':283728.}}
        self.gate=science.Gate(self.lib,base,{'identity':space.S})
        self.audit.row_digests=self.gate.row_digests;self.audit.source_binding=self.gate.source_binding
        self.audit.boolean_cache={};self.audit.donor_boolean_cache={};self.audit.cache_binding_cache={}
        item=self.item();part,cert=self.gate.classify(item)
        self.assertEqual(part,'T90');self.assertEqual(cert['c90'],38070)
        self.assertEqual(self.audit.verify_certificate(item,cert)['status'],'PASS')
        for value in [False,1]:
            tampered=copy.deepcopy(cert);tampered['bitset_padding_zero']=value
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
        science.annotate(r,s);self.assertFalse(r['qualified_for_round21'])
        r['regional']['pooled_internal']['max_s']=98.;science.annotate(r,s);self.assertTrue(r['qualified_for_round21'])
        r['feasibility']['feasible']=False;science.annotate(r,s);self.assertFalse(r['qualified_for_round21'])
    def test_numeric_tolerance_does_not_relax_identity_or_boolean(self):
        self.assertEqual(checker._differences([10.,'x',True],[10.+1e-7,'x',True],1e-6),[])
        for val in [[10.+2e-6,'x',True],[10.,'y',True],[10.,'x',1]]:
            self.assertTrue(checker._differences([10.,'x',True],val,1e-6))
    def test_ranking_uses_exact_floats(self):
        reports=[dict(qualified_for_round21=True,ranking_key=[1.,2.,3.,4.,'a']),
            dict(qualified_for_round21=True,ranking_key=[1.-1e-8,2.,3.,4.,'b'])]
        self.assertIs(science.select(reports),reports[1])
    def test_feasible_F1_F2_cannot_be_improvement_or_fallback(self):
        center={'identity':space.S,'regional':{'pooled_internal':{'max_s':132051.28738869302}}}
        intermediates=[]
        for identity,maximum in [('F1',146674.743179584),('F2',172730.31608610202)]:
            report=dict(identity=identity,feasibility=dict(feasible=True,rejection_reasons=[]),
                improvement={'substantive_improvement':True},regional={'pooled_internal':{'max_s':maximum,'mean_s':9300.}},
                effective_grid={'T100_s':595089.,'T90_s':283000.})
            science.annotate(report,center);self.assertIs(report['qualified_for_round21'],False)
            intermediates.append(report)
        self.assertIsNone(science.select(intermediates))
    def test_independent_T90_boolean_count_and_exact_boundary(self):
        values=np.full(43070,np.inf);values[:38762]=123.
        rows={0:values};keep=np.ones(43070,dtype=bool)
        digest=checker.classification_digest(values<=123.)
        self.assertEqual(checker.verify_t90_count(rows,[0],keep,123.,38763,38762,digest)['status'],'PASS')
        values[38762]=123.
        digest=checker.classification_digest(values<=123.)
        self.assertEqual(checker.verify_t90_count(rows,[0],keep,123.,38763,38763,digest)['status'],'FAIL')
    def test_raw_source_change_invalidates_T100_witness(self):
        rows={0:np.array([597566.]),1:np.array([np.inf])}
        witness=checker.verify_t100_witness(rows,[0,1],0,595089.)['source_values']
        rows[0][0]=595089.
        self.assertEqual(checker.verify_t100_witness(rows,[0,1],0,595089.,witness)['status'],'FAIL')


class EvidenceEncodingTests(unittest.TestCase):
    def test_archival_log_BOM_decoding_preserves_exact_raw_bytes(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('ROUND21_TEST_ROOT')) as name:
            folder=Path(name)
            payloads={'powershell.log':'原始输出\n'.encode('utf-16'),
                'big_endian.txt':b'\xfe\xff'+'原始输出\n'.encode('utf-16-be'),
                'utf8_bom.log':b'\xef\xbb\xbf'+'原始输出\n'.encode('utf8'),
                'utf8.json':'{"状态":"保留"}\n'.encode('utf8')}
            for filename,payload in payloads.items():(folder/filename).write_bytes(payload)
            inventory=inputs._text_inventory(folder,lambda:None)
            self.assertEqual(inventory['powershell.log']['text_encoding'],'utf-16')
            self.assertEqual(inventory['big_endian.txt']['text_encoding'],'utf-16')
            self.assertEqual(inventory['utf8_bom.log']['text_encoding'],'utf-8-sig')
            self.assertEqual(inventory['utf8.json']['text_encoding'],'utf8')
            for filename,payload in payloads.items():
                self.assertEqual((folder/filename).read_bytes(),payload)
                self.assertEqual(inventory[filename]['bytes'],len(payload))
                self.assertEqual(inventory[filename]['sha256'],hashlib.sha256(payload).hexdigest())
    def test_scientific_JSON_cannot_use_archival_log_encoding_exception(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('ROUND21_TEST_ROOT')) as name:
            folder=Path(name);(folder/'scientific.json').write_bytes('{"a":1}'.encode('utf-16'))
            with self.assertRaises(UnicodeDecodeError):inputs._text_inventory(folder,lambda:None)

if __name__=='__main__':unittest.main()
