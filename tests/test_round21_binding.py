import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest

from src.round13.common import read, record, sha
from src.round21 import reference_adapter
from src.round21.regression import (BOOTSTRAP, ROOT, source_subset, suite_adapter,
    test_ids as parse_test_ids, verify_ids, verify_mapping, verify_helper_mapping,
    fixture_temp_root, verify_bootstrap_mapping)


class BindingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=os.environ.get('ROUND21_TEST_ROOT'))
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.serial = 0

    def fixture(self, test_id):
        self.serial += 1
        base = self.root/str(self.serial)
        original, repo = base/'original', base/'repo'
        original.mkdir(parents=True)
        repo.mkdir()
        rows = []
        for number in range(reference_adapter.WHITELIST[test_id]['count']):
            path = original/(str(number)+'.py')
            path.write_text(str(number), encoding='utf8')
            rows.append(dict(record(path), relative_path=path.name))
        source_test, copied_test = original/'test.py', repo/'test.py'
        source_test.write_text('unchanged test source', encoding='utf8')
        copied_test.write_bytes(source_test.read_bytes())
        return (SimpleNamespace(ROOT=repo), repo, original, source_test, copied_test,
            sha(source_test), rows, base/'events.jsonl')

    def test_exact_two_id_whitelist_and_counts(self):
        self.assertEqual({name: item['count'] for name, item in reference_adapter.WHITELIST.items()}, {
            'test_round19_binding.BindingTests.test_old268_preserved_and_subsets_have_exact_members':268,
            'test_round20_binding.BindingTests.test_old292_and_exact_historical_subsets':292})

    def test_both_roots_restore_after_normal_scope(self):
        for test_id in reference_adapter.WHITELIST:
            args = self.fixture(test_id)
            with reference_adapter.reference_scope(test_id, *args):
                self.assertEqual(args[0].ROOT, args[2])
            self.assertEqual(args[0].ROOT, args[1])
            event = read(args[-1])
            self.assertTrue(event['restored'])
            self.assertEqual(event['original_before'], event['original_after'])
            self.assertTrue(event['test_bytes_preserved'])

    def test_both_roots_restore_after_exception(self):
        for test_id in reference_adapter.WHITELIST:
            args = self.fixture(test_id)
            with self.assertRaisesRegex(RuntimeError, 'fixture failure'):
                with reference_adapter.reference_scope(test_id, *args):
                    raise RuntimeError('fixture failure')
            self.assertEqual(args[0].ROOT, args[1])
            self.assertTrue(read(args[-1])['restored'])

    def test_non_whitelisted_id_never_adapts(self):
        test_id = next(iter(reference_adapter.WHITELIST))
        args = self.fixture(test_id)
        for other in [test_id+'.extra', test_id.replace('BindingTests', 'OtherTests'), 'unapproved.test']:
            with reference_adapter.reference_scope(other, *args):
                self.assertEqual(args[0].ROOT, args[1])
        self.assertFalse(args[-1].exists())

    def test_wrong_initial_root_rejected(self):
        test_id = next(iter(reference_adapter.WHITELIST))
        args = self.fixture(test_id)
        args[0].ROOT = args[2]
        with self.assertRaisesRegex(ValueError, 'INITIAL_ROOT'):
            with reference_adapter.reference_scope(test_id, *args):
                self.fail('scope must not enter')

    def test_source_and_copy_test_tamper_rejected(self):
        test_id = next(iter(reference_adapter.WHITELIST))
        for index in [3, 4]:
            args = self.fixture(test_id)
            args[index].write_text('tampered', encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'TEST_BYTES'):
                with reference_adapter.reference_scope(test_id, *args):
                    self.fail('scope must not enter')
            self.assertEqual(args[0].ROOT, args[1])

    def test_reference_source_tamper_rejected(self):
        test_id = next(iter(reference_adapter.WHITELIST))
        args = self.fixture(test_id)
        Path(args[6][0]['path']).write_text('changed', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'REFERENCE_BYTES'):
            with reference_adapter.reference_scope(test_id, *args):
                self.fail('scope must not enter')
        self.assertEqual(args[0].ROOT, args[1])

    def test_scope_late_tamper_restores_and_records_failure(self):
        test_id = next(iter(reference_adapter.WHITELIST))
        args = self.fixture(test_id)
        with self.assertRaisesRegex(ValueError, 'RESTORE_OR_BYTES'):
            with reference_adapter.reference_scope(test_id, *args):
                args[4].write_text('changed during test', encoding='utf8')
        self.assertEqual(args[0].ROOT, args[1])
        event = read(args[-1])
        self.assertTrue(event['restored'])
        self.assertFalse(event['test_bytes_preserved'])

    def test_manifest_count_duplicate_escape_absolute_rejected(self):
        test_id = next(iter(reference_adapter.WHITELIST))
        args = self.fixture(test_id)
        rows, original = args[6], args[2]
        cases = [rows[:-1], rows+[rows[0]], [rows[0]]*268,
            [dict(rows[0], relative_path='../escape')]+rows[1:],
            [dict(rows[0], relative_path=str(original/'0.py'))]+rows[1:],
            [dict(rows[0], path=str(original/'other.py'))]+rows[1:]]
        for bad in cases:
            with self.assertRaises(ValueError):
                reference_adapter.validate_reference_rows(bad, original)

    def test_old319_and_eight_exact_historical_subsets(self):
        cfg = read(ROOT/'configs/round21.json')
        rows = read(Path(cfg['r20_delivery'])/'sealed/frozen/consumer_code.json')
        self.assertEqual(len(rows), 319)
        for count in [168,185,203,223,245,268,292,319]:
            subset = source_subset(rows, count)
            self.assertEqual(len(subset), count)
            self.assertEqual(len({row['relative_path'] for row in subset}), count)
        for row in rows:
            self.assertEqual(record(row['path']), {key:row[key] for key in ['path','bytes','sha256']})

    def test_original_and_execution_copy_tamper_rejected(self):
        original, repo = self.root/'original', self.root/'repo'
        original.mkdir()
        repo.mkdir()
        source, copied = original/'a.py', repo/'a.py'
        source.write_text('same', encoding='utf8')
        copied.write_bytes(source.read_bytes())
        rows = [dict(record(source), relative_path='a.py')]
        self.assertEqual(len(verify_mapping(original, repo, rows)), 1)
        copied.write_text('different', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'COPY_VERSION'):
            verify_mapping(original, repo, rows)
        source.write_text('changed', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'SOURCE_VERSION'):
            verify_mapping(original, repo, rows)

    def test_helper_copy_bytes_tamper_rejected(self):
        helper = self.root/'round21_legacy_guard.py'
        shutil.copyfile(ROOT/'src/round21/legacy_guard.py', helper)
        self.assertEqual(verify_helper_mapping(self.root)['source']['sha256'], sha(helper))
        helper.write_text('tampered helper', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'HELPER_COPY_CHANGED'):
            verify_helper_mapping(self.root)

    def test_standard_library_bootstrap_precedes_all_guards(self):
        self.assertIn('ctypes.wintypes', BOOTSTRAP)
        for pattern in ['test_round14*.py','test_round19*.py','test_round20*.py']:
            adapter = suite_adapter(pattern)
            self.assertTrue(adapter.startswith(BOOTSTRAP))
            self.assertLess(adapter.index('import ctypes'), adapter.index('from guard_impl import install'))
            if pattern in {'test_round19*.py','test_round20*.py'}:
                self.assertIn('from round21_reference_adapter import install', adapter)
        with self.assertRaisesRegex(ValueError, 'SELECTION_PATTERN'):
            suite_adapter('test*.py')

    def test_r20_fixture_temp_inside_copied_root_and_foreign_repo_rejected(self):
        repo = self.root/'repo'
        self.assertEqual(fixture_temp_root(self.root,repo,'test_round20*.py'), repo/'work/round20/tmp')
        self.assertEqual(fixture_temp_root(self.root,repo,'test_round19*.py'), self.root/'tmp')
        with self.assertRaisesRegex(ValueError, 'FIXTURE_REPO_SCOPE'):
            fixture_temp_root(self.root,self.root.parent/'foreign','test_round20*.py')

    def test_executed_historical_guard_and_bootstrap_tamper_rejected(self):
        copied = self.root/'guard_impl.py'
        bootstrap = self.root/'sitecustomize.py'
        shutil.copyfile(ROOT/'src/round9/guard.py',copied)
        bootstrap.write_text(BOOTSTRAP,encoding='utf8')
        before = verify_bootstrap_mapping(self.root)
        bootstrap.write_text('changed',encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'BOOTSTRAP_CHANGED'):
            verify_bootstrap_mapping(self.root,before)
        copied.write_text('changed',encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'BOOTSTRAP_GUARD_BYTES'):
            verify_bootstrap_mapping(self.root)

    def test_exact_test_id_sets_and_duplicates(self):
        actual, expected = self.root/'actual.log', self.root/'expected.log'
        actual.write_text('test_a (module.Case.test_a) ... ok\ntest_b (module.Case.test_b) ... ok\n', encoding='utf8')
        expected.write_text('test_b (module.Case.test_b) ... ok\ntest_a (module.Case.test_a) ... ok\n', encoding='utf8')
        self.assertEqual(verify_ids(actual, expected, 2)['count'], 2)
        expected.write_text('test_c (module.Case.test_c) ... ok\n', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'ID_SET_MISMATCH'):
            verify_ids(actual, expected, 2)
        actual.write_text('test_a (module.Case.test_a) ... ok\ntest_a (module.Case.test_a) ... ok\n', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'DUPLICATED_ACTUAL_TEST_IDS'):
            parse_test_ids(actual)


if __name__ == '__main__':
    unittest.main()
