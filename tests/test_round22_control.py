"""ROUND22 preparation-inclusive cutoffs and fail-dominant results."""
import os
from pathlib import Path
import subprocess
import tempfile
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.round13.common import EvidenceError, read, write, record, sha
from src.round22 import control
from src.round22 import reference_adapter
from src.round22.regression import (source_subset, SUBSET_COUNTS, BOOTSTRAP,
    suite_adapter, fixture_temp_root, verify_ids, test_ids as actual_ids)


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ROUND22_TEST_ROOT'))
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def clock(self,offset=6590.):
        record_epoch = 10000.
        path = self.root/'lifecycle.json'
        effective = record_epoch-offset
        write(path,dict(record_epoch=record_epoch,preparation_offset_seconds=offset,
            effective_start_epoch=effective,start_epoch=effective,start_epoch_already_includes_preparation=True,
            compute_limit_seconds=6600,total_limit_seconds=7200))
        return path

    def test_offset_consumes_real_parent_timeout_and_is_not_charged_twice(self):
        path = self.clock()
        with patch.object(control.time,'time',return_value=10000.), patch.object(control.time,'monotonic',return_value=500.):
            life = control.Lifecycle(path)
            self.assertEqual((life.elapsed(),life.remaining(),life.timeout()),(6590.,610.,10.))
        with patch.object(control.time,'time',return_value=20000.), patch.object(control.time,'monotonic',return_value=501.):
            self.assertEqual(life.elapsed(),6591.)
            self.assertEqual(life.timeout(),9.)

    def test_compute_and_total_deadlines_share_one_start_with_600s_reserve(self):
        path = self.clock(6600.)
        with patch.object(control.time,'time',return_value=10000.), patch.object(control.time,'monotonic',return_value=500.):
            life = control.Lifecycle(path)
            self.assertEqual(life.remaining(),600.)
            life.check(False)
            with self.assertRaisesRegex(control.BudgetExceeded,'ROUND22_COMPUTE_DEADLINE'):
                life.timeout()
        with patch.object(control.time,'monotonic',return_value=1100.):
            with self.assertRaisesRegex(control.BudgetExceeded,'ROUND22_TOTAL_DEADLINE'):
                life.check(False)

    def test_ambiguous_clock_metadata_and_altered_limits_rejected(self):
        path = self.clock(); original = read(path)
        for changes in [dict(start_epoch=10000.),dict(effective_start_epoch=3400.),
            dict(preparation_offset_seconds=-1.),dict(start_epoch_already_includes_preparation=False),
            dict(compute_limit_seconds=6599),dict(total_limit_seconds=7201)]:
            write(path,dict(original,**changes))
            with self.assertRaises(EvidenceError):
                control.Lifecycle(path)

    def test_fail_cannot_be_downgraded_by_later_timeout(self):
        state = control.Status()
        for level in ['BLOCKED','FAIL','PASS','BLOCKED']:
            state.add(level,'case')
        self.assertEqual((state.value,state.exit_code),('FAIL',1))
        self.assertEqual(control.classify(PermissionError('ROUND22_GUARD_NETWORK')),'FAIL')
        self.assertEqual(control.classify(subprocess.TimeoutExpired(['python'],1)),'BLOCKED')

    def test_all_nine_subsets_keep_exact_historical_source_members(self):
        root = Path(__file__).resolve().parents[1]
        rows = read(Path('G:/gpt-file/Codex/outputs/bd-fmb/round21/20261031T070246_offline')/
                    'sealed/frozen/consumer_code.json')
        self.assertEqual(SUBSET_COUNTS,(168,185,203,223,245,268,292,319,346))
        self.assertEqual(len(rows),346)
        previous = set()
        for count in SUBSET_COUNTS:
            subset = source_subset(rows,count,root)
            names = {row['relative_path'] for row in subset}
            self.assertEqual(len(subset),count)
            self.assertEqual(len(names),count)
            self.assertTrue(previous.issubset(names))
            self.assertFalse(any(name.startswith('src/round22/') for name in names))
            previous = names
        self.assertIn('src/round21/science.py',previous)

    def test_r21_selection_bootstraps_before_guard_without_third_root_exception(self):
        adapter = suite_adapter('test_round21*.py')
        self.assertTrue(adapter.startswith(BOOTSTRAP))
        self.assertIn('ctypes.wintypes',BOOTSTRAP)
        self.assertIn('importlib.abc',BOOTSTRAP)
        self.assertIn("selected_pattern='test_round21*.py'",adapter)
        self.assertNotIn('install_reference()',adapter)
        self.assertEqual(set(reference_adapter.WHITELIST),{
            'test_round19_binding.BindingTests.test_old268_preserved_and_subsets_have_exact_members',
            'test_round20_binding.BindingTests.test_old292_and_exact_historical_subsets'})
        for bad in ['test*.py','test_round22*.py','test_round21_science.py']:
            with self.assertRaisesRegex(ValueError,'SELECTION_PATTERN'):
                suite_adapter(bad)

    def reference_fixture(self, test_id):
        base = self.root/test_id.split('.')[0]
        original, repo = base/'original',base/'repo'
        original.mkdir(parents=True);repo.mkdir()
        rows=[]
        for number in range(reference_adapter.WHITELIST[test_id]['count']):
            path=original/(str(number)+'.py')
            path.write_text(str(number),encoding='utf8')
            rows.append(dict(record(path),relative_path=path.name))
        source=original/'test.py';copy=repo/'test.py'
        source.write_text('unchanged historical assertion',encoding='utf8')
        copy.write_bytes(source.read_bytes())
        return SimpleNamespace(ROOT=repo),repo,original,source,copy,sha(source),rows,base/'events.jsonl'

    def test_exact_two_root_scopes_restore_on_normal_and_exceptional_exit(self):
        for test_id in reference_adapter.WHITELIST:
            args=self.reference_fixture(test_id)
            with reference_adapter.reference_scope(test_id,*args):
                self.assertEqual(args[0].ROOT,args[2])
            self.assertEqual(args[0].ROOT,args[1])
            with self.assertRaisesRegex(RuntimeError,'known fixture failure'):
                with reference_adapter.reference_scope(test_id,*args):
                    self.assertEqual(args[0].ROOT,args[2])
                    raise RuntimeError('known fixture failure')
            self.assertEqual(args[0].ROOT,args[1])
            events=[json.loads(line) for line in args[-1].read_text(encoding='utf8').splitlines()]
            self.assertEqual(len(events),2)
            self.assertTrue(all(e['restored'] and e['test_bytes_preserved'] for e in events))
            self.assertTrue(all(e['original_before']==e['original_after'] for e in events))

    def test_non_whitelist_and_tampered_test_never_receive_original_root(self):
        test_id=next(iter(reference_adapter.WHITELIST));args=self.reference_fixture(test_id)
        for other in [test_id+'.extra','test_round21_binding.BindingTests.test_old319_and_eight_exact_historical_subsets']:
            with reference_adapter.reference_scope(other,*args):
                self.assertEqual(args[0].ROOT,args[1])
        self.assertFalse(args[-1].exists())
        args[4].write_text('changed assertions',encoding='utf8')
        with self.assertRaisesRegex(ValueError,'REFERENCE_TEST_BYTES'):
            with reference_adapter.reference_scope(test_id,*args):
                self.fail('tampered test must not enter')
        self.assertEqual(args[0].ROOT,args[1])

    def test_r20_temp_is_in_copy_and_exact_ids_reject_duplicates_or_missing(self):
        repo=self.root/'repo'
        self.assertEqual(fixture_temp_root(self.root,repo,'test_round20*.py'),repo/'work/round20/tmp')
        self.assertEqual(fixture_temp_root(self.root,repo,'test_round21*.py'),self.root/'tmp')
        actual,expected=self.root/'actual.log',self.root/'expected.log'
        text='test_a (fixture.Case.test_a) ... ok\ntest_b (fixture.Case.test_b) ... ok\n'
        actual.write_text(text,encoding='utf8');expected.write_text(text,encoding='utf8')
        self.assertEqual(verify_ids(actual,expected,2)['count'],2)
        expected.write_text(text.splitlines()[0]+'\n',encoding='utf8')
        with self.assertRaisesRegex(ValueError,'ID_SET_MISMATCH'):
            verify_ids(actual,expected,2)
        actual.write_text(text+text,encoding='utf8')
        with self.assertRaisesRegex(ValueError,'DUPLICATED_ACTUAL_TEST_IDS'):
            actual_ids(actual)


if __name__ == '__main__':
    unittest.main()
