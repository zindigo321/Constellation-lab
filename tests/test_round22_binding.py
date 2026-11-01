import codecs
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
import sys
import zipfile
from unittest.mock import patch

from src.round13.common import read, write, record, sha, fingerprint
from src.round22 import binding, inputs


class BindingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=os.environ.get('ROUND22_TEST_ROOT'))
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.serial = 0

    def attempt_fixture(self):
        self.serial += 1
        repo = self.root/('repo'+str(self.serial))
        repo.mkdir()
        source = repo/'a.py'
        source.write_text('preserved source',encoding='utf8')
        rows = [dict(record(source),relative_path='a.py')]
        work = repo/'work'
        attempt = work/'attempts'/'a1_science'
        out = attempt/'output'
        out.mkdir(parents=True)
        (work/'frozen').mkdir()
        write(work/'frozen/contract.json',dict(profile='ROUND22_V1',checkpoint_inputs=[]))
        (attempt/'consumer_contract.json').write_bytes((work/'frozen/contract.json').read_bytes())
        digest = sha(attempt/'consumer_contract.json')
        write(attempt/'consumer_code.json',rows)
        argv = [sys.executable,'-X','utf8','-B','-m','src.round22.worker',
            '--work',str(work),'--out',str(out),'--job','science']
        result = dict(status='PASS',exit_code=0,attempt_id=attempt.name,job='science',
            consumer_identity=fingerprint(rows),argv=argv,cwd=str(repo),contract_sha256=digest)
        write(out/'job_result.json',result)
        write(attempt/'supervised_result.json',result)
        command = dict(code_manifest=rows,attempt_id=attempt.name,output=str(out),job='science',
            command=argv,cwd=str(repo),contract_sha256=digest,output_artifacts=binding.artifacts(out),
            python_exit_code=0,timeout=False,supervised_result_exit_code=0)
        write(attempt/'command_result.json',command)
        with zipfile.ZipFile(attempt/'consumer_code.zip','w') as snapshot:
            snapshot.write(source,'a.py')
        return repo,work,attempt,out,rows,command,result

    def test_new_source_policy_is_only_authorized_round22_paths(self):
        for name in ['src/round22/science.py','src/round22/nested/helper.py',
                'tests/test_round22_science.py','tools/run_round22.py','tools/export_round22.py',
                'configs/round22.json','docs/round22.md']:
            self.assertTrue(binding.allowed_new(name), name)
        for name in ['src/round21/science.py','tests/nested/test_round22.py','tools/other.py',
                'configs/round22.extra.json','../src/round22/a.py','/src/round22/a.py',
                'src/round22/data.npz','docs/round21.md']:
            self.assertFalse(binding.allowed_new(name), name)

    def test_log_bom_variants_are_decoded_without_byte_changes(self):
        for index, (blob, encoding) in enumerate([
                ('中文\n'.encode('utf8'),'utf8'),
                ('中文\n'.encode('utf-8-sig'),'utf-8-sig'),
                ('中文\n'.encode('utf-16'),'utf-16'),
                (codecs.BOM_UTF16_BE+'中文\n'.encode('utf-16-be'),'utf-16')]):
            path = self.root/(str(index)+'.log')
            path.write_bytes(blob)
            before = record(path)
            self.assertEqual(inputs.evidence_text(path),encoding)
            self.assertEqual(record(path),before)
            self.assertEqual(path.read_bytes(),blob)

    def test_scientific_json_keeps_existing_utf8_bom_policy(self):
        path = self.root/'science.json'
        path.write_bytes(codecs.BOM_UTF8+b'{"value":1}')
        self.assertEqual(inputs.evidence_text(path),'utf-8-sig')
        self.assertEqual(read(path),{'value':1})

    def test_scientific_json_rejects_utf16_and_invalid_utf8(self):
        path = self.root/'science.json'
        for blob in ['{"value":1}'.encode('utf-16'),b'{"value":"\xff"}']:
            path.write_bytes(blob)
            with self.assertRaises(UnicodeError):
                inputs.evidence_text(path)

    def test_scientific_jsonl_rejects_bom_utf16_and_malformed_middle(self):
        path = self.root/'science.jsonl'
        for blob in [codecs.BOM_UTF8+b'{"value":1}\n',
                '{"value":1}\n'.encode('utf-16'),
                b'{"value":1}\nBROKEN\n{"value":2}\n']:
            path.write_bytes(blob)
            with self.assertRaises((UnicodeError,ValueError)):
                inputs.evidence_text(path)
        path.write_bytes(b'{"value":1}\n{"value":2}\n')
        self.assertEqual(inputs.evidence_text(path),'utf8')

    def test_invalid_archival_log_is_not_replacement_decoded(self):
        path = self.root/'broken.log'
        path.write_bytes(b'not utf8\xff')
        with self.assertRaises(UnicodeDecodeError):
            inputs.evidence_text(path)

    def test_contract_binds_complete_matched_anchor_union(self):
        work = self.root/'work'
        work.mkdir()
        write(work/'lifecycle.json',dict(effective_start_epoch=1000))
        write(work/'starting_git.json',dict(HEAD=dict(stdout='head\n')))
        metadata = dict(anchor_assertions=[dict(label='q1')],original_constraint_reference='B0',
            search_center='S',improvement_reference='S',center_indices=list(range(28)),
            donor_indices22=list(range(28,2171)),original_reference_thresholds={'tau100':2,'tau90':1})
        cfg = dict(native_protocol_hash='protocol',archive_sha256='archive',matrix_sha256='matrix',
            catalog_sha256='catalog',promotion_sha256='promotion')
        rows, checkpoints = [dict(path='a',sha256='x')], [dict(path='c')]
        contract = binding.build_contract(work,cfg,metadata,rows,checkpoints)
        self.assertEqual(contract['profile'],'ROUND22_V1')
        self.assertEqual(contract['declared_candidates'],173499)
        self.assertEqual(contract['canonical_operations'],dict(remove_count=2,add_count=2,symmetric_difference_from_S=4))
        self.assertEqual(contract['family_pairwise_intersections'],dict(q1_q2=1,q1_q3=1,q2_q3=1))
        self.assertEqual(contract['family_triple_intersection'],0)
        self.assertEqual(contract['family_first_owner_counts'],dict(q1=57834,q2=57833,q3=57832))
        self.assertEqual(contract['effective_removal_pairs'],78)
        self.assertFalse(contract['history_identity_exclusion_enabled'])
        self.assertEqual(contract['candidate_REUSED'],0)
        self.assertEqual(contract['anchor_role'],'INFEASIBLE_ANCHOR_DIAGNOSTIC_ONLY')
        self.assertEqual(contract['source_manifest_identity'],fingerprint(rows))
        self.assertEqual(contract['starting_head'],'head')

    def test_attempt_contract_copy_and_expected_sha_are_both_required(self):
        work, attempt = self.root/'work',self.root/'attempt'
        (work/'frozen').mkdir(parents=True)
        attempt.mkdir()
        contract = dict(profile='ROUND22_V1',declared_candidates=173499)
        write(work/'frozen/contract.json',contract)
        write(attempt/'consumer_contract.json',contract)
        digest = sha(work/'frozen/contract.json')
        self.assertEqual(binding.verify_contract(work,attempt,digest),digest)
        with self.assertRaisesRegex(ValueError,'DIGEST_MISMATCH'):
            binding.verify_contract(work,attempt,'wrong')
        write(attempt/'consumer_contract.json',dict(contract,declared_candidates=173490))
        with self.assertRaisesRegex(ValueError,'COPY_MISMATCH'):
            binding.verify_contract(work,attempt)

    def test_attempt_exact_version_and_actual_command_binding(self):
        repo,work,attempt,out,rows,command,result = self.attempt_fixture()
        with patch.object(binding,'ROOT',repo):
            self.assertEqual(binding.verify_attempt(attempt,rows)['status'],'PASS')
            command['command'] = list(command['command'])+['--unexpected']
            write(attempt/'command_result.json',command)
            with self.assertRaisesRegex(ValueError,'COMMAND_MISMATCH'):
                binding.verify_attempt(attempt,rows)

    def test_attempt_fails_closed_on_source_snapshot_or_output_tamper(self):
        for kind in ['source_manifest','snapshot','output']:
            repo,work,attempt,out,rows,command,result = self.attempt_fixture()
            if kind == 'source_manifest':
                write(attempt/'consumer_code.json',[dict(rows[0],sha256='wrong')])
                reason = 'CONSUMER_VERSION_MISMATCH'
            elif kind == 'snapshot':
                with zipfile.ZipFile(attempt/'consumer_code.zip','w') as snapshot:
                    snapshot.writestr('a.py','different source')
                reason = 'SNAPSHOT_BYTES'
            else:
                (out/'unbound.json').write_text('{}',encoding='utf8')
                reason = 'OUTPUT_ARTIFACT_MISMATCH'
            with patch.object(binding,'ROOT',repo):
                with self.assertRaisesRegex(ValueError,reason):
                    binding.verify_attempt(attempt,rows)

    def test_attempt_requires_real_successful_child_exit_and_no_timeout(self):
        for key,value in [('python_exit_code',None),('python_exit_code',1),('timeout',True)]:
            repo,work,attempt,out,rows,command,result = self.attempt_fixture()
            command[key] = value
            write(attempt/'command_result.json',command)
            with patch.object(binding,'ROOT',repo):
                with self.assertRaisesRegex(ValueError,'NOT_COMPLETED_PASS'):
                    binding.verify_attempt(attempt,rows)

    def test_source_identity_absolute_path_and_bytes_are_verified(self):
        path = self.root/'a.py'
        path.write_text('original',encoding='utf8')
        row = dict(record(path),relative_path='a.py')
        with patch.object(binding,'ROOT',self.root):
            binding.verify_sources([row])
            with self.assertRaisesRegex(ValueError,'DUPLICATE_SOURCE_PATH'):
                binding.verify_sources([row,row])
            bad = dict(row,path=str(self.root/'other.py'))
            with self.assertRaisesRegex(ValueError,'SOURCE_ABSOLUTE_PATH'):
                binding.verify_sources([bad])
            path.write_text('changed',encoding='utf8')
            with self.assertRaisesRegex(ValueError,'FROZEN_SOURCE_CHANGED'):
                binding.verify_sources([row])

    def test_starting_source_is_old346_not_new_round22(self):
        cfg = read(binding.ROOT/'configs/round22.json')
        old = read(Path(cfg['r21_delivery'])/'sealed/frozen/consumer_code.json')
        self.assertEqual(len(old),346)
        self.assertEqual(len({row['relative_path'] for row in old}),346)
        self.assertFalse(any('/round22/' in row['relative_path'] for row in old))
        for row in old:
            self.assertEqual(record(row['path']),{key:row[key] for key in ['path','bytes','sha256']})
        write(self.root/'starting_code_manifest.json',old)
        self.assertEqual(binding.starting(self.root),old)

    def test_runtime_uses_actual_starting_head_and_separate_checkpoint_bytes(self):
        path = self.root/'checkpoint.csv'
        path.write_bytes(b'preserved\r\n')
        row = dict(record(path),relative_path='checkpoints/round18/selected_orbits.csv')
        write(self.root/'starting_git.json',dict(HEAD=dict(stdout='current\n')))
        write(self.root/'starting_checkpoints.json',[row])
        with patch.object(binding,'current_head',return_value='current'):
            binding.verify_runtime(self.root)
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'CHECKPOINT_CHANGED'):
                binding.verify_runtime(self.root)
        with patch.object(binding,'current_head',return_value='other'):
            with self.assertRaisesRegex(ValueError,'HEAD_CHANGED'):
                binding.verify_runtime(self.root)

    def test_real_planning_anchor_records_are_existing_infeasible_r19(self):
        cfg = read(binding.ROOT/'configs/round22.json')
        plan = read(Path(cfg['r22_plan'])/'evidence/existing_anchor_diagnostics.json')
        anchors = plan['anchors']
        self.assertEqual([(a['label'],a['remove'],a['add']) for a in anchors],
            [('q1',1412,1118),('q2',2021,1123),('q3',1941,1200)])
        self.assertEqual([a['existing_R19_ledger']['ordinal'] for a in anchors],[39676,52539,46187])
        self.assertTrue(all(a['existing_R19_ledger']['partition']=='T100' for a in anchors))
        self.assertEqual(anchors[2]['existing_T90_deficit'],113)
        points = {p['point_id']:p for p in anchors[1]['T100_gate_missing_points']}
        self.assertEqual(points[23148]['classification'],'NO_FIRST_HIT')
        self.assertEqual(points[30898]['classification'],'FINITE_LATE')
        self.assertAlmostEqual(points[30898]['existing_first_hit_s'],595920.2685995891)


if __name__ == '__main__':
    unittest.main()
