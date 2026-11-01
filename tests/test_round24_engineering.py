"""Preservation, cache integrity and interrupted-input semantics."""
import ast
import hashlib
import inspect
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from src.round13.common import read,write,sha
from src.round24 import asset_decoder,binding,regression,seal
from src.round24.resolver import FrozenArchive,Progress,safe_path

def current_work():
    return binding.ROOT/read(binding.ROOT/'configs/round24.json')['prepared_work']


class EngineeringTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ.get('ROUND24_TEST_ROOT'))
        self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_old400_exact_subsets_and_checkpoint6(self):
        old=read(binding.ROOT/'work/round23/20261101T082559_offline/frozen/consumer_code.json')
        for n in [168,185,203,223,245,268,292,319,346,373,400]:
            self.assertEqual(len(regression.source_subset(old,n)),n)
        self.assertEqual(len(read(binding.ROOT/'work/round23/20261101T082559_offline/starting_checkpoints.json')),6)
        for row in old:self.assertEqual(sha(row['path']),row['sha256'])
    def test_only_round24_additions_allowed(self):
        self.assertTrue(binding.allowed_new('src/round24/deadline.py'))
        for name in ['src/round23/control.py','src/round16/supervise.py','tests/test_round23_science.py','../bad.py']:
            self.assertFalse(binding.allowed_new(name))
    def test_npz_validator_is_ast_identical_to_immutable_full_validator(self):
        from src.round16.inputs import validate_npz_row
        self.assertEqual(ast.dump(ast.parse(inspect.getsource(asset_decoder.validate_npz_row))),
            ast.dump(ast.parse(inspect.getsource(validate_npz_row))))
    def test_npz_entire_row_late_point_mismatch_rejected(self):
        values=np.zeros(43424);path=self.root/'values.npz';np.savez(path,first_hits=values)
        changed=values.copy();changed[-1]=1
        with self.assertRaisesRegex(ValueError,'MISMATCH'):
            asset_decoder.validate_npz_row(path,changed,43424,604800.)
        self.assertEqual(asset_decoder.validate_npz_row(path,values,43424,604800.)['points_verified'],43424)
    def fake_archive(self,blob=b'current'):
        arc=object.__new__(FrozenArchive);arc.check=lambda:None;arc.roots=[self.root/'old'];arc.vendor=self.root/'new'
        arc.locations={};arc.used={};arc.progress=Progress(self.root,lambda:None)
        (self.root/'old').mkdir(exist_ok=True);(self.root/'old/a').write_bytes(blob)
        arc.manifest={'files':{'a':{'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()}}}
        return arc
    def test_cache_full_current_hash_and_source_binding(self):
        arc=self.fake_archive();p=arc.path('a')
        self.assertEqual(p,self.root/'old/a');self.assertEqual(arc.used['a']['sha256'],sha(p))
        self.assertFalse(arc.vendor.exists())
    def test_cache_tamper_before_first_use_is_rejected(self):
        arc=self.fake_archive();(self.root/'old/a').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'CACHE_BYTES_CHANGED'):arc.path('a')
    def test_end_preserve_detects_post_validation_cache_change(self):
        arc=self.fake_archive();arc.path('a');(self.root/'old/a').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'MEMBER_CHANGED_AFTER_READ'):arc.preserve()
    def test_unsafe_cache_paths_rejected(self):
        for name in ['../a','a/../../bad','C:/a','a\\b','x:stream','CON','A/../b']:
            with self.assertRaises(ValueError):safe_path(self.root,name)
    def test_reparse_point_is_rejected_even_when_not_symlink(self):
        p=self.root/'x';p.write_bytes(b'x')
        original=Path.lstat
        def mocked(path):
            actual=original(path)
            return SimpleNamespace(st_file_attributes=0x400,st_mode=actual.st_mode) if path==p else actual
        with patch.object(Path,'lstat',mocked):
            with self.assertRaisesRegex(ValueError,'REPARSE'):safe_path(self.root,'x')
    def test_reparse_ancestor_of_cache_root_is_rejected(self):
        cache=self.root/'cache';cache.mkdir();(cache/'x').write_bytes(b'x')
        original=Path.lstat
        def mocked(path):
            actual=original(path)
            return SimpleNamespace(st_file_attributes=0x400,st_mode=actual.st_mode) if path==self.root else actual
        with patch.object(Path,'lstat',mocked):
            with self.assertRaisesRegex(ValueError,'REPARSE'):safe_path(cache,'x')
    def test_progress_is_diagnostic_not_full_input_pass(self):
        progress=Progress(self.root,lambda:None);progress.asset=60
        with progress.phase('NPZ_matrix_all_values'):pass
        data=read(self.root/'input_progress/latest.json')
        self.assertEqual(data['asset'],60);self.assertEqual(data['completed_assets'],0)
        self.assertNotIn('status',data)
    def test_zero_input_prefix_has_null_qualification_and_selection(self):
        data=seal.prefix_counts(self.root)
        self.assertIsNone(data['qualified_for_round24']);self.assertIsNone(data['qualified_count'])
        self.assertIsNone(data['retained_S']);self.assertEqual(data['unprocessed'],166970)
        self.assertEqual(data['unknown'],0)
    def test_partial_final_record_never_counts_as_complete(self):
        (self.root/'ledger.jsonl').write_text('{"ordinal":0',encoding='utf8')
        self.assertEqual(list(seal.durable_records(self.root/'ledger.jsonl')),[])
    def test_middle_corrupt_record_fails(self):
        (self.root/'ledger.jsonl').write_text('bad\n{}\n',encoding='utf8')
        with self.assertRaises(ValueError):list(seal.durable_records(self.root/'ledger.jsonl'))
    def test_empty_input_closure_after_compute_uses_only_total_budget(self):
        calls=[]
        write(self.root/'lifecycle.json',dict(controlled_test=True,compute_limit_seconds=6600,total_limit_seconds=7200))
        class Clock:
            def __init__(self,path):pass
            def check(self,compute=False):
                calls.append(compute)
                if compute:raise AssertionError('Closure crossed compute gate')
            def elapsed(self):return 6601.
        with patch.object(seal,'Lifecycle',Clock):
            result=seal.seal(self.root,{},'BLOCKED',['controlled compute deadline'])
        final=read(self.root/'sealed/final_status.json')
        self.assertEqual(result['exit_code'],2);self.assertTrue(calls);self.assertFalse(any(calls))
        self.assertIsNone(final['qualified_for_round24']);self.assertIsNone(final['selected'])
        self.assertEqual(final['B0_replayed'],0);self.assertEqual(final['S_replayed'],0)
        self.assertEqual(final['anchors_replayed'],0);self.assertFalse((self.root/'sealed/science/selected_orbits.csv').exists())
    def test_actual_shell_seven_and_prestart_null_are_bound(self):
        from src.round24.control import verify_shell_probes
        value=verify_shell_probes(current_work())
        self.assertEqual(value['seven']['actual_outer_shell_exit_code'],7)
        self.assertIsNone(value['prestart']['python_exit_code'])
    def test_short_work_name_keeps_fixture_below_windows_path_limit(self):
        data=read(current_work()/'preparation/deepest_fixture_path.json')
        self.assertLess(data['characters'],260)
