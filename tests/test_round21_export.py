import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.round13.common import write, sha
from src.round21 import export, seal, binding


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ROUND21_TEST_ROOT'))
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
        work = export.ROOT/'work/round21/one'
        with self.assertRaisesRegex(ValueError, 'TRANSPORT_RECEIPT_WORK_BINDING'):
            export.verify_work_mapping(folder, dict(source_work=str(work), files=[]),
                dict(source_work=str(work.parent/'two'), destination=str(folder)), lambda: None)

    def test_exact_destination_and_finite_export_child_command(self):
        work = export.ROOT/'work/round21/test_run'
        destination = self.root/'approved'/work.name
        self.assertEqual(export.validate_destination(work, destination, destination.parent), destination)
        with self.assertRaisesRegex(ValueError, 'EXPORT_DESTINATION_BINDING'):
            export.validate_destination(work, self.root/'wrong'/work.name, destination.parent)
        calls = []
        with patch('src.round21.guard.install', lambda *a, **kw: calls.append(kw)):
            export.install_export_guard(self.root, destination, allow_export_child=True)
            export.install_export_guard(self.root, destination)
            export.install_export_guard(self.root, destination, role='finalizer')
        self.assertEqual([r['role'] for r in calls], ['export_launcher','export_child','finalizer'])
        command = calls[0]['commands'][0]
        self.assertEqual(command['argv'][5], 'src.round21.export')
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
        write(work/'frozen/contract.json', {'profile':'ROUND21_V1'})
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
        base = dict(seal.FLAGS, status='FAIL', exit_code=1, declared_candidates=111306)
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


if __name__ == '__main__':
    unittest.main()
