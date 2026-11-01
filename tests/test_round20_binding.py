import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from src.round13.common import read,write,record,sha
from src.round20 import binding,reference_adapter,seal
from src.round20.regression import source_subset

class BindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ.get('ROUND20_TEST_ROOT'));self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
    def test_old292_and_exact_historical_subsets(self):
        cfg=read(binding.ROOT/'configs/round20.json');rows=read(Path(cfg['r19_delivery'])/'sealed/frozen/consumer_code.json')
        binding.verify_sources(rows);self.assertEqual(len(rows),292)
        for count in [168,185,203,223,245,268,292]:self.assertEqual(len(source_subset(rows,count)),count)
    def test_original_and_copy_source_tampering(self):
        from src.round20.regression import verify_mapping
        original=self.root/'original';repo=self.root/'repo';original.mkdir();repo.mkdir()
        p=original/'a.py';q=repo/'a.py';p.write_text('a',encoding='utf8');q.write_bytes(p.read_bytes())
        rows=[dict(record(p),relative_path='a.py')]
        verify_mapping(original,repo,rows)
        q.write_text('bad',encoding='utf8')
        with self.assertRaisesRegex(ValueError,'COPY_VERSION'):verify_mapping(original,repo,rows)
        p.write_text('bad',encoding='utf8')
        with self.assertRaisesRegex(ValueError,'SOURCE_VERSION'):verify_mapping(original,repo,rows)
    def test_source_duplicate_escape_absolute_and_tamper(self):
        p=self.root/'a.py';p.write_text('a',encoding='utf8');row=dict(record(p),relative_path='a.py')
        with patch.object(binding,'ROOT',self.root):
            for bad in [[row,dict(row,relative_path='A.py')],[dict(row,relative_path='../a.py')],[dict(row,path=str(self.root/'other'))]]:
                with self.assertRaises(ValueError):binding.verify_sources(bad)
            p.write_text('changed',encoding='utf8')
            with self.assertRaisesRegex(ValueError,'FROZEN_SOURCE_CHANGED'):binding.verify_sources([row])
    def test_attempt_source_mismatch(self):
        a=self.root/'attempts'/'a';a.mkdir(parents=True)
        write(a/'consumer_code.json',[{'bad':1}]);write(a/'command_result.json',dict(code_manifest=[]))
        with self.assertRaisesRegex(ValueError,'ATTEMPT_CONSUMER'):binding.verify_attempt(a,[])
    def test_contract_copy_and_recorded_digest_must_match(self):
        work=self.root/'work';attempt=work/'attempt';(work/'frozen').mkdir(parents=True);attempt.mkdir()
        write(work/'frozen/contract.json',{'profile':'ROUND20_V1'})
        (attempt/'consumer_contract.json').write_bytes((work/'frozen/contract.json').read_bytes())
        digest=binding.verify_contract(work,attempt)
        with self.assertRaisesRegex(ValueError,'DIGEST_MISMATCH'):binding.verify_contract(work,attempt,'wrong')
        write(attempt/'consumer_contract.json',{'profile':'wrong'})
        with self.assertRaisesRegex(ValueError,'COPY_MISMATCH'):binding.verify_contract(work,attempt,digest)
    def test_scope_excludes_old_files_and_checkpoints(self):
        self.assertTrue(binding.allowed_new('src/round20/a.py'))
        for p in ['src/round19/a.py','checkpoints/round19/evidence.json','tests/nested/test_round20.py']:
            self.assertFalse(binding.allowed_new(p))
    def fixture(self):
        original=self.root/'original';repo=self.root/'repo';original.mkdir();repo.mkdir()
        rows=[]
        for n in range(268):
            p=original/(str(n)+'.py');p.write_text(str(n),encoding='utf8');rows.append(dict(record(p),relative_path=p.name))
        src=original/'test.py';cp=repo/'test.py';src.write_text('test',encoding='utf8');cp.write_bytes(src.read_bytes())
        return SimpleNamespace(ROOT=repo),repo,original,src,cp,sha(src),rows,self.root/'log.jsonl'
    def test_whitelisted_reference_root_normal_restore_and_fixture_isolation(self):
        args=self.fixture();module,repo,original,*_=args
        with reference_adapter.reference_scope(reference_adapter.WHITELIST,*args):
            self.assertEqual(module.ROOT,original)
        self.assertEqual(module.ROOT,repo)
        self.assertTrue(read(args[-1])['restored'])
        self.assertTrue(Path(os.environ['TEMP']).resolve().is_relative_to(binding.ROOT/'work/round20'))
    def test_whitelisted_reference_root_exception_restore(self):
        args=self.fixture();module,repo,*_=args
        with self.assertRaisesRegex(RuntimeError,'expected'):
            with reference_adapter.reference_scope(reference_adapter.WHITELIST,*args):raise RuntimeError('expected')
        self.assertEqual(module.ROOT,repo);self.assertTrue(read(args[-1])['restored'])
    def test_non_whitelist_does_not_adapt(self):
        args=self.fixture();module,repo,*_=args
        with reference_adapter.reference_scope('unapproved.test',*args):self.assertEqual(module.ROOT,repo)
        self.assertFalse(args[-1].exists())
    def test_reference_test_and_source_bytes_tamper_rejected(self):
        args=self.fixture()
        args[4].write_text('tamper',encoding='utf8')
        with self.assertRaisesRegex(ValueError,'TEST_BYTES'):
            with reference_adapter.reference_scope(reference_adapter.WHITELIST,*args):pass
        args[4].write_bytes(args[3].read_bytes());Path(args[6][0]['path']).write_text('tamper',encoding='utf8')
        with self.assertRaisesRegex(ValueError,'REFERENCE_BYTES'):
            with reference_adapter.reference_scope(reference_adapter.WHITELIST,*args):pass
    def test_reference_manifest_count_duplicate_and_path_rejected(self):
        args=self.fixture();rows=args[6];original=args[2]
        for bad in [rows[:-1],rows+[rows[0]],[rows[0]]*268,[dict(rows[0],relative_path='../escape')]+rows[1:]]:
            with self.assertRaises(ValueError):reference_adapter.validate_reference_rows(bad,original)
    def test_partial_final_line_not_counted_middle_damage_rejected(self):
        p=self.root/'rows.jsonl';p.write_text('{"a":1}\n{"b":',encoding='utf8')
        self.assertEqual(list(seal.durable_records(p)),[{'a':1}])
        p.write_text('{bad}\n{}\n',encoding='utf8')
        with self.assertRaises(json.JSONDecodeError):list(seal.durable_records(p))

if __name__=='__main__':unittest.main()
