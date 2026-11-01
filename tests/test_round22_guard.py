"""ROUND22 per-role network closure and exact process/write boundaries."""
import json
import os
from pathlib import Path
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch

from src.round22 import guard
from src.round22 import legacy_guard


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ROUND22_TEST_ROOT'))
        self.work = Path(self.tmp.name).resolve()
        self.destination = self.work/'destination'

    def tearDown(self):
        self.tmp.cleanup()

    def capture(self, role='science', commands=None, destination=None):
        callbacks = []
        with patch.object(sys, 'addaudithook', side_effect=callbacks.append), \
             patch.object(sys, 'meta_path', list(sys.meta_path)):
            lock = guard.install(self.work,self.work/(role+'_guard.jsonl'),controlled=True,
                role=role,commands=commands,destination=destination)
        self.assertEqual(len(callbacks),1)
        return callbacks[0], lock

    def worker(self, job='science'):
        return [sys.executable,'-X','utf8','-B','-m','src.round22.worker',
            '--work',str(self.work),'--out',str(self.work/'attempts/one/output'),'--job',job]

    def test_every_role_rejects_every_socket_audit_event(self):
        events = ['socket.__new__','socket.connect','socket.bind','socket.sendto','socket.sendmsg','socket.getaddrinfo',
                  'socket.gethostname','socket.gethostbyname','socket.gethostbyaddr','socket.getnameinfo','socket.unknown_future_event']
        for role in guard.ROLES:
            audit, _ = self.capture(role)
            for event in events:
                with self.subTest(role=role,event=event), self.assertRaisesRegex(PermissionError,'ROUND22_GUARD_NETWORK'):
                    audit(event,(None,('example.invalid',9)))

    def test_registered_argv_interpreter_cwd_work_and_destination_are_all_exact(self):
        commands = []
        argv = [sys.executable,'-X','utf8','-B','-m','src.round22.export',
            '--work',str(self.work),'--destination',str(self.destination)]
        guard.register_command(commands,argv,guard.ROOT,self.work,self.destination)
        self.assertTrue(guard.command_allowed(argv,guard.ROOT,commands,self.work,self.destination))
        for changed in [argv+['--extra'],['other_python.exe']+argv[1:],argv[:-1]+[str(self.destination/'other')]]:
            self.assertFalse(guard.command_allowed(changed,guard.ROOT,commands,self.work,self.destination))
        self.assertFalse(guard.command_allowed(argv,self.work,commands,self.work,self.destination))
        self.assertFalse(guard.command_allowed(argv,guard.ROOT,commands,self.work/'other',self.destination))
        self.assertFalse(guard.command_allowed(argv,guard.ROOT,commands,self.work,self.destination/'other'))
        audit, _ = self.capture('export_launcher',commands,self.destination)
        audit('subprocess.Popen',(sys.executable,argv,str(guard.ROOT),{}))
        audit('subprocess.Popen',(None,argv,str(guard.ROOT),{}))
        with self.assertRaisesRegex(PermissionError,'ROUND22_GUARD_UNAPPROVED_SUBPROCESS'):
            audit('subprocess.Popen',('other_python.exe',argv,str(guard.ROOT),{}))

    def test_coordinator_workers_and_supervisor_probes_have_exact_scope(self):
        from src.round22.supervise import PROBE_CODE, PROBE_MODES
        for job in guard.COORDINATOR_JOBS:
            self.assertTrue(guard.coordinator_command_allowed(self.worker(job),self.work,guard.ROOT))
        self.assertFalse(guard.coordinator_command_allowed(self.worker()+['extra'],self.work,guard.ROOT))
        self.assertFalse(guard.coordinator_command_allowed(self.worker('other'),self.work,guard.ROOT))
        self.assertFalse(guard.coordinator_command_allowed(self.worker(),self.work,self.work))
        wrong = self.worker(); wrong[9] = str(self.work.parent/'unrelated/attempts/one/output')
        self.assertFalse(guard.coordinator_command_allowed(wrong,self.work,guard.ROOT))
        for mode in PROBE_MODES:
            folder = self.work/'supervision'/mode
            argv = [sys.executable,'-X','utf8','-B','-c',PROBE_CODE,str(folder/'created_pid.json'),mode]
            self.assertTrue(guard.coordinator_command_allowed(argv,self.work,folder))
            argv[5] += ';print(1)'
            self.assertFalse(guard.coordinator_command_allowed(argv,self.work,folder))

    def test_export_child_and_finalizer_cannot_create_any_child(self):
        argv = self.worker('tests')
        commands = []
        guard.register_command(commands,argv,guard.ROOT,self.work)
        for role in guard.TERMINAL_ROLES:
            with self.assertRaisesRegex(ValueError,'ROUND22_TERMINAL_ROLE_HAS_CHILDREN'):
                self.capture(role,commands)
            empty = []
            audit, _ = self.capture(role,empty)
            guard.register_command(empty,argv,guard.ROOT,self.work)
            with self.assertRaisesRegex(PermissionError,'ROUND22_GUARD_UNAPPROVED_SUBPROCESS'):
                audit('subprocess.Popen',(sys.executable,argv,str(guard.ROOT),{}))

    def test_native_vendor_and_outside_mutations_denied_but_export_write_allowed(self):
        audit, lock = self.capture('export_child',destination=self.destination)
        audit('open',(str(self.destination/'legal.json'),'w',os.O_WRONLY|os.O_CREAT))
        audit('open',(str(self.work.parent/'read_evidence'),'r',0))
        for event,args,reason in [
            ('import',('comtypes.client',None,None,None,None),'NATIVE_IMPORT'),
            ('exec',(compile('pass',str(guard.ROOT/'work/round18/old/materialized/vendor.py'),'exec'),),'VENDOR_EXECUTION'),
            ('open',(str(self.work.parent/'forbidden'),'w',os.O_WRONLY|os.O_CREAT),'WRITE_SCOPE'),
            ('os.replace',(str(self.work/'source'),str(self.work.parent/'forbidden')),'MUTATION_SCOPE')]:
            with self.assertRaisesRegex(PermissionError,'ROUND22_GUARD_'+reason):
                audit(event,args)
        lock()
        with self.assertRaisesRegex(PermissionError,'ROUND22_GUARD_WRITE_SCOPE'):
            audit('open',(str(self.work/'materialized/input.json'),'w',os.O_WRONLY|os.O_CREAT))

    def test_command_registration_rejects_foreign_interpreter_or_output(self):
        for argv,cwd,destination in [
            (['foreign.exe','-c','pass'],guard.ROOT,None),
            (self.worker(),self.work.parent,None),
            ([sys.executable,'--out',str(self.work.parent/'outside')],guard.ROOT,None),
            ([sys.executable,'--destination',str(self.destination)],guard.ROOT,None)]:
            with self.assertRaises(ValueError):
                guard.register_command([],argv,cwd,self.work,destination)

    def test_original_project_is_read_only_for_every_role(self):
        for role in guard.ROLES:
            audit, _ = self.capture(role)
            original = guard.ROOT/'docs/round20.md'
            audit('open',(str(original),'r',0))
            with self.subTest(role=role), self.assertRaisesRegex(PermissionError,'ROUND22_GUARD_WRITE_SCOPE'):
                audit('open',(str(original),'w',os.O_WRONLY|os.O_TRUNC))

    def test_legal_destination_and_native_package_aliases(self):
        audit, _ = self.capture('export_child',destination=self.destination)
        audit('open',(str(self.destination/'report.json'),'w',os.O_WRONLY|os.O_CREAT))
        for module in ['agi.stk12.stkobjects','ansys.stk.core','win32com.client','stk_adapter']:
            with self.subTest(module=module), self.assertRaisesRegex(PermissionError,'ROUND22_GUARD_NATIVE_IMPORT'):
                audit('import',(module,None,None,None,None))

    def test_saved_stage_evidence_reader_requires_exact_module_path_and_frozen_bytes(self):
        repo=self.work/'isolated_repo'
        source=guard.ROOT/'src/round8/native.py'
        copied=repo/'src/round8/native.py'
        copied.parent.mkdir(parents=True)
        shutil.copyfile(source,copied)
        self.assertTrue(legacy_guard.saved_evidence_import(repo,'src.round8.native'))
        self.assertTrue(legacy_guard.saved_evidence_file(repo,copied))
        for module in ['native','src.round8.native.extra','src.other.native','win32com.client','agi.stk12']:
            self.assertFalse(legacy_guard.saved_evidence_import(repo,module))
        duplicate=repo/'native.py';shutil.copyfile(source,duplicate)
        self.assertFalse(legacy_guard.saved_evidence_file(repo,duplicate))
        copied.write_bytes(copied.read_bytes()+b'\n')
        self.assertFalse(legacy_guard.saved_evidence_import(repo,'src.round8.native'))
        self.assertFalse(legacy_guard.saved_evidence_file(repo,copied))


if __name__ == '__main__':
    unittest.main()
