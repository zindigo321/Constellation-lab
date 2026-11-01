import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess

from src.round13.common import write, sha
from src.round23 import export, seal, binding


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ROUND23_TEST_ROOT'))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def fixture(self):
        folder = self.root/'copy'
        folder.mkdir()
        p = folder/'text.txt'
        p.write_text('第21轮原始字节', encoding='utf8')
        write(folder/'transport_manifest.json', dict(files=[dict(path='text.txt', bytes=p.stat().st_size, sha256=sha(p))]))
        write(folder/'transfer_receipt.json', dict(manifest_sha256=sha(folder/'transport_manifest.json')))
        return folder

    def test_transport_byte_and_exact_set_validation(self):
        folder = self.fixture()
        self.assertEqual(export.verify_transport(folder)['status'], 'PASS')
        (folder/'extra').write_text('unlisted', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'TRANSPORT_ORIGINAL_EXACT_SET'):
            export.verify_transport(folder)

    def test_transport_payload_and_manifest_tampering(self):
        folder = self.fixture()
        (folder/'text.txt').write_text('different', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'TRANSPORT_ORIGINAL_MEMBER_BYTES'):
            export.verify_transport(folder)
        write(folder/'transport_manifest.json', dict(files=[]))
        with self.assertRaisesRegex(ValueError, 'TRANSPORT_RECEIPT_BINDING'):
            export.verify_transport(folder)

    def test_original_work_binding_even_when_bytes_match(self):
        folder = self.fixture()
        work = export.ROOT/'work/round23/one'
        with self.assertRaisesRegex(ValueError, 'TRANSPORT_RECEIPT_WORK_BINDING'):
            export.verify_work_mapping(folder, dict(source_work=str(work), files=[]),
                dict(source_work=str(work.parent/'two'), destination=str(folder)), lambda: None)

    def test_exact_destination_and_finite_export_child_command(self):
        work = export.ROOT/'work/round23/test_run'
        destination = self.root/'approved'/work.name
        self.assertEqual(export.validate_destination(work, destination, destination.parent), destination)
        with self.assertRaisesRegex(ValueError, 'EXPORT_DESTINATION_BINDING'):
            export.validate_destination(work, self.root/'wrong'/work.name, destination.parent)
        calls = []
        with patch('src.round23.guard.install', lambda *a, **kw: calls.append(kw)):
            export.install_export_guard(self.root, destination, allow_export_child=True)
            export.install_export_guard(self.root, destination)
            export.install_export_guard(self.root, destination, role='finalizer')
        self.assertEqual([r['role'] for r in calls], ['export_launcher','export_child','finalizer'])
        command = calls[0]['commands'][0]
        self.assertEqual(command['argv'][5], 'src.round23.export')
        self.assertEqual(command['argv'][-4:], ['--work',str(self.root),'--destination',str(destination)])
        self.assertEqual(calls[1]['commands'], [])
        self.assertEqual(calls[2]['commands'], [])

    def test_attempt_and_contract_binding_reject_wrong_source_or_digest(self):
        work = self.root/'work'
        attempt = work/'attempts/a'
        attempt.mkdir(parents=True)
        write(attempt/'consumer_code.json', [{'wrong':'version'}])
        write(attempt/'command_result.json', dict(code_manifest=[]))
        with self.assertRaisesRegex(ValueError, 'ATTEMPT_CONSUMER'):
            binding.verify_attempt(attempt, [])
        write(work/'frozen/contract.json', {'profile':'ROUND23_V1'})
        (attempt/'consumer_contract.json').write_bytes((work/'frozen/contract.json').read_bytes())
        digest = binding.verify_contract(work, attempt)
        with self.assertRaisesRegex(ValueError, 'DIGEST_MISMATCH'):
            binding.verify_contract(work, attempt, 'bad')
        write(attempt/'consumer_contract.json', {'profile':'ROUND20_V1'})
        with self.assertRaisesRegex(ValueError, 'COPY_MISMATCH'):
            binding.verify_contract(work, attempt, digest)

    def test_interrupted_final_jsonl_and_corrupt_middle(self):
        p = self.root/'records.jsonl'
        p.write_text('{"ok":1}\n{"tail":', encoding='utf8')
        self.assertEqual(list(seal.durable_records(p)), [{'ok':1}])
        p.write_text('{broken}\n{}\n', encoding='utf8')
        with self.assertRaises(json.JSONDecodeError):
            list(seal.durable_records(p))

    def test_scope_booleans_and_exit_integers_are_exact_types(self):
        folder = self.root/'sealed'
        folder.mkdir()
        base = dict(seal.FLAGS, status='FAIL', exit_code=1, declared_candidates=166970)
        for changes in [dict(active_protocol_change_authorized=0), dict(native_activation_count=False),
                        dict(exit_code=True), dict(declared_candidates=True)]:
            write(folder/'final_status.json', dict(base, **changes))
            p = folder/'final_status.json'
            write(folder/'artifact_manifest.json', dict(profile=seal.PROFILE,
                files=[dict(path=p.name, bytes=p.stat().st_size, sha256=sha(p))]))
            write(folder/'receipt.json', dict(profile=seal.PROFILE, status='FAIL', exit_code=1,
                manifest_sha256=sha(folder/'artifact_manifest.json')))
            with self.assertRaises(ValueError):
                seal.independent_readback(folder)

    def invoke_fixture(self):
        from src.round23 import run
        work = self.root/'attempt_work'
        work.mkdir()
        snapshot = work/'snapshot.zip'
        snapshot.write_bytes(b'preparation fixture snapshot')
        clock = unittest.mock.Mock()
        clock.timeout.return_value = 60
        clock.elapsed.return_value = 1
        patches = [patch.object(run, 'Lifecycle', return_value=clock),
                   patch.object(run, 'verify_sources'), patch.object(run, 'verify_runtime')]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        return run, work, snapshot

    def test_supervisor_failure_preserves_attempt_without_claiming_python_exit(self):
        run, work, snapshot = self.invoke_fixture()
        with patch('src.round23.supervise.run', side_effect=OSError('synthetic supervisor setup failure')):
            attempt, result = run.invoke(work, 'tests', [], snapshot)
        from src.round13.common import read
        command = read(attempt/'command_result.json')
        self.assertEqual(result['status'], 'FAIL')
        self.assertIsNone(command['python_exit_code'])
        self.assertEqual(command['launch_status'], 'SUPERVISOR_EXCEPTION_START_STATE_UNKNOWN')
        self.assertTrue((attempt/'supervisor_exception.json').is_file())
        self.assertEqual((attempt/'consumer_code.zip').read_bytes(), snapshot.read_bytes())

    def test_actual_child_exit_mismatch_cannot_keep_reported_blocked_status(self):
        run, work, snapshot = self.invoke_fixture()
        def child(argv, **kwargs):
            out = Path(argv[argv.index('--out')+1])
            out.mkdir()
            write(out/'job_result.json', dict(status='BLOCKED', exit_code=2))
            return subprocess.CompletedProcess(argv, 1)
        with patch('src.round23.supervise.run', side_effect=child):
            attempt, result = run.invoke(work, 'tests', [], snapshot)
        self.assertEqual((result['status'], result['exit_code']), ('FAIL', 1))
        self.assertEqual(result['error'], 'CHILD_EXIT_MISMATCH')
        self.assertEqual(result['prior_reported_exit_code'], 2)

    def test_shell_capture_uses_global_native_exit_in_invoked_scriptblock(self):
        from src.round23 import shell
        repo = self.root/'repo'
        work = repo/'work/round23/capture_test'
        work.mkdir(parents=True)
        (work/'observations').mkdir()
        write(repo/'configs/round23.json', dict(preferred_output=str(self.root/'delivery')))
        with patch.object(shell, 'ROOT', repo), patch.object(shell, 'install'):
            script = shell.prepare(work, 'research', label='capture')
        body = script.read_text(encoding='utf8')
        self.assertIn('$global:LASTEXITCODE = $null', body)
        self.assertIn('$round23PythonExit = $global:LASTEXITCODE', body)
        self.assertNotIn('$LASTEXITCODE = $null', body)
        from src.round23.run import THREAD_ENV
        for key,value in THREAD_ENV.items():
            self.assertIn(f"$env:{key} = '{value}'", body)


if __name__ == '__main__':
    unittest.main()
