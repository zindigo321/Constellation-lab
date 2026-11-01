"""Clock and wait injection exercises the production absolute-deadline loop."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from src.round13.common import write
from src.round13.control import BudgetExceeded,Status
from src.round24.control import Lifecycle
from src.round24.deadline import wait_absolute


class DeadlineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ.get('ROUND24_TEST_ROOT'))
        self.path=Path(self.tmp.name)/'clock.json';self.clock=[10000.,1000.]
        write(self.path,dict(start_epoch=10000.,record_epoch=10000.,effective_start_epoch=10000.,
            preparation_offset_seconds=0.,start_epoch_already_includes_preparation=True,
            start_monotonic_seconds=1000.,compute_limit_seconds=6600,total_limit_seconds=7200))
        self.life=Lifecycle(self.path,utc=lambda:self.clock[0],monotonic=lambda:self.clock[1])
    def tearDown(self):self.tmp.cleanup()
    def advance(self,s):self.clock[0]+=s;self.clock[1]+=s
    def test_preparation_included_from_immutable_origin(self):
        self.advance(125);self.assertEqual(self.life.elapsed(),125)
        other=Lifecycle(self.path,utc=lambda:self.clock[0],monotonic=lambda:self.clock[1])
        self.assertEqual(other.elapsed(),125)
    def test_6601_compute_denied_total_closure_available(self):
        self.advance(6601)
        with self.assertRaises(BudgetExceeded):self.life.check(True)
        self.life.check(False);self.assertEqual(self.life.remaining(False),599)
    def test_7201_total_denied_real_overrun_retained(self):
        self.advance(7201)
        with self.assertRaises(BudgetExceeded):self.life.check(False)
        self.assertEqual(self.life.elapsed(),7201)
    def test_backward_utc_does_not_extend_remaining(self):
        self.advance(60);self.life.check(True)
        self.clock[0]-=500;self.clock[1]+=20
        self.assertEqual(self.life.elapsed(),80)
        self.assertFalse(self.life.fatal_clock_anomaly)
    def test_forward_utc_jump_conservatively_stops(self):
        self.life.elapsed();self.clock[0]+=30;self.clock[1]+=1
        with self.assertRaisesRegex(BudgetExceeded,'CLOCK_ANOMALY'):self.life.check(True)
        self.assertEqual(self.life.elapsed(),30)
    def test_monotonic_backward_is_fatal_no_decreasing_elapsed(self):
        self.advance(60);self.life.elapsed();self.clock[1]-=2
        with self.assertRaisesRegex(BudgetExceeded,'CLOCK_ANOMALY'):self.life.check(True)
        self.assertGreaterEqual(self.life.elapsed(),60)
    def test_monotonic_forward_discontinuity_stops_before_global_deadline(self):
        self.life.elapsed();self.clock[0]+=1;self.clock[1]+=30
        with self.assertRaisesRegex(BudgetExceeded,'CLOCK_ANOMALY'):self.life.check(True)
        self.assertEqual(self.life.elapsed(),30)
    def test_first_sample_rejects_cross_process_basis_mismatch(self):
        self.clock[1]-=5
        with self.assertRaisesRegex(BudgetExceeded,'CLOCK_ANOMALY'):self.life.check(True)
    def test_wait_late_zero_exit_is_blocked_and_not_clamped(self):
        outer=self
        class Child:
            def wait(self,timeout):outer.assertLessEqual(timeout,1);outer.advance(7000);return 0
        result=wait_absolute(Child(),self.life,True,6600,10000,1000,
            utc=lambda:self.clock[0],mono=lambda:self.clock[1])
        self.assertTrue(result['deadline_exceeded']);self.assertEqual(result['overrun_s'],400)
        self.assertEqual(result['utc_wall_s'],7000);self.assertEqual(result['wait_return_type'],'PROCESS_EXIT')
    def test_normal_child_zero_after_short_wait(self):
        outer=self
        class Child:
            def wait(self,timeout):outer.advance(.1);return 0
        result=wait_absolute(Child(),self.life,True,6600,10000,1000,
            utc=lambda:self.clock[0],mono=lambda:self.clock[1])
        self.assertFalse(result['deadline_exceeded']);self.assertEqual(result['wait_calls'],1)
    def test_blocked_child_short_polling_never_waits_remaining_budget(self):
        waits=[];outer=self
        class Child:
            def wait(self,timeout):
                waits.append(timeout);outer.advance(timeout)
                raise subprocess.TimeoutExpired('own-child',timeout)
        result=wait_absolute(Child(),self.life,True,3,10000,1000,
            utc=lambda:self.clock[0],mono=lambda:self.clock[1])
        self.assertEqual(waits,[1,1,1]);self.assertTrue(result['deadline_exceeded'])
    def test_fail_not_downgraded_by_following_timeout(self):
        state=Status();state.add('FAIL','input corrupt');state.add('BLOCKED','timeout')
        self.assertEqual(state.value,'FAIL')
    def test_initial_origin_limits_cannot_be_redefined(self):
        data=json.loads(self.path.read_text(encoding='utf8'));data['compute_limit_seconds']=7200;write(self.path,data)
        with self.assertRaises(ValueError):Lifecycle(self.path)
    def test_parent_switches_from_compute_to_total_only_for_closure(self):
        outer=self;closing=[False]
        class Child:
            def wait(self,timeout):closing[0]=True;outer.advance(6601);return 0
        result=wait_absolute(Child(),self.life,lambda:not closing[0],7200,10000,1000,
            utc=lambda:self.clock[0],mono=lambda:self.clock[1])
        self.assertFalse(result['deadline_exceeded']);self.assertEqual(result['deadline_kind'],'TOTAL')
    def test_blocked_coordinator_still_stops_at_compute_under_total_parent_window(self):
        outer=self
        class Child:
            def wait(self,timeout):outer.advance(6601);return 0
        result=wait_absolute(Child(),self.life,lambda:True,7200,10000,1000,
            utc=lambda:self.clock[0],mono=lambda:self.clock[1])
        self.assertTrue(result['deadline_exceeded']);self.assertEqual(result['deadline_kind'],'COMPUTE')
