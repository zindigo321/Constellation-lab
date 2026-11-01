"""One effective preparation-inclusive clock for every R24 parent and child."""
import math
import datetime
import subprocess
import time
from pathlib import Path

from src.round13.common import read, require, sha
from src.round13.control import Status, BudgetExceeded
from src.round16.control import classify as archived_classify


def verify_delivery_preflight(work, preferred_output, now_epoch=None):
    """Require the real early writable-path observation before freezing."""
    work, preferred = Path(work).resolve(), Path(preferred_output).resolve()
    data = read(work/'preparation/delivery_writable_preflight.json')
    require(type(data.get('status')) is str and data['status']=='PASS',
        'ROUND24_DELIVERY_PREFLIGHT_NOT_PASS')
    require(Path(data['root']).resolve()==preferred and
        Path(data['destination']).resolve()==preferred/work.name,
        'ROUND24_DELIVERY_PREFLIGHT_DESTINATION')
    require(data.get('destination_absent_before_export') is True,
        'ROUND24_DELIVERY_PREFLIGHT_ABSENCE_BOOL')
    stamp=datetime.datetime.fromisoformat(data['observed_utc'].replace('Z','+00:00'))
    require(stamp.tzinfo is not None and stamp.utcoffset()==datetime.timedelta(0),
        'ROUND24_DELIVERY_PREFLIGHT_UTC')
    require(stamp.timestamp()<=(time.time() if now_epoch is None else now_epoch),
        'ROUND24_DELIVERY_PREFLIGHT_IN_FUTURE')
    require(not (preferred/work.name).exists(),'ROUND24_DELIVERY_DESTINATION_ALREADY_EXISTS')
    return data


def verify_shell_probes(work):
    """Bind fresh actual Python/script/outer exits and pre-start-null evidence."""
    folder=Path(work)/'preparation'
    data=read(folder/'shell_probe_observations.json')
    require(data.get('status')=='PASS' and data.get('observed_after_actual_tool_process_exits') is True and
        data.get('outer_wrapper_explicit_exit_global_LASTEXITCODE') is True,
        'ROUND24_SHELL_PROBE_NOT_OBSERVED')
    seven,prestart=data['seven'],data['prestart']
    require(all(type(seven.get(key)) is int and seven[key]==7 for key in
        ['python_exit_code','script_exit_code','actual_outer_shell_exit_code']),
        'ROUND24_SHELL7_PROPAGATION')
    require(prestart.get('python_exit_code') is None and prestart.get('python_started') is False and
        prestart.get('launch_status')=='PRE_START_FAILURE' and
        type(prestart.get('actual_outer_shell_exit_code')) is int and prestart['actual_outer_shell_exit_code']==1,
        'ROUND24_PRESTART_NULL_EXIT')
    for item,stem in [(seven,'shell7'),(prestart,'shell_null')]:
        require(sha(folder/(stem+'.ps1'))==item['source_sha256'] and
            sha(folder/(stem+'_pending.json'))==item['pending_sha256'],'ROUND24_SHELL_PROBE_BYTES')
        pending=read(folder/(stem+'_pending.json'))
        if stem=='shell7':
            require(type(pending.get('python_exit_code')) is int and pending['python_exit_code']==7 and
                type(pending.get('script_exit_code')) is int and pending['script_exit_code']==7 and
                pending.get('python_started') is True,'ROUND24_SHELL7_PENDING_MISMATCH')
        else:
            require(pending.get('python_exit_code') is None and pending.get('python_started') is False and
                pending.get('launch_status')=='PRE_START_FAILURE','ROUND24_NULL_PENDING_MISMATCH')
    require(type(data.get('science_candidates_evaluated')) is int and data['science_candidates_evaluated']==0,
        'ROUND24_PROBE_CANDIDATE_BOUNDARY')
    return data


class Lifecycle:
    def __init__(self, path, utc=time.time, monotonic=time.perf_counter):
        self.path = Path(path)
        self.data = read(path)
        d = self.data
        record = float(d.get('record_epoch', d['start_epoch']))
        offset = float(d.get('preparation_offset_seconds', 0))
        effective = float(d['effective_start_epoch'])
        require(all(math.isfinite(v) for v in [record, offset, effective]) and offset >= 0,
                'ROUND24_INVALID_CLOCK')
        require(abs(record-offset-effective) <= 1e-6, 'ROUND24_PREPARATION_OFFSET_MISMATCH')
        require(d['start_epoch'] == effective and d.get('start_epoch_already_includes_preparation') is True,
                'ROUND24_START_MUST_INCLUDE_PREPARATION')
        require(d['compute_limit_seconds'] == 6600 and d['total_limit_seconds'] == 7200,
                'ROUND24_CLOCK_LIMITS')
        self.effective_start_epoch = effective
        self.utc, self.monotonic = utc, monotonic
        self._start = float(d['start_monotonic_seconds'])
        require(math.isfinite(self._start), 'ROUND24_INVALID_MONOTONIC_ORIGIN')
        self._max_elapsed = 0.0
        self._previous = None
        self.anomalies = []
        self.fatal_clock_anomaly = False
        self.last_sample = None

    def elapsed(self):
        u, m = self.utc(), self.monotonic()
        ue, me = u-self.effective_start_epoch, m-self._start
        tolerance = self.data.get('clock_skew_tolerance_s', 2.0)
        if self._previous is not None:
            pu, pm = self._previous
            du, dm = u-pu, m-pm
            if dm < 0 or du-dm > tolerance or (du >= 0 and dm-du > tolerance):
                self.fatal_clock_anomaly = True
                self.anomalies.append(dict(kind='CLOCK_DISCONTINUITY', utc_delta=du, monotonic_delta=dm))
            elif du < 0:
                self.anomalies.append(dict(kind='UTC_BACKWARD_NO_BUDGET_EXTENSION', utc_delta=du, monotonic_delta=dm))
        elif abs(ue-me) > tolerance:
            self.fatal_clock_anomaly = True
            self.anomalies.append(dict(kind='CROSS_PROCESS_CLOCK_SKEW', utc_elapsed=ue, monotonic_elapsed=me))
        if not all(math.isfinite(v) for v in (u,m,ue,me)) or me < -tolerance:
            self.fatal_clock_anomaly = True
        self._previous = (u,m)
        self._max_elapsed = max(self._max_elapsed, ue, me)
        self.last_sample = dict(utc_epoch=u,monotonic_seconds=m,utc_elapsed_s=ue,
            monotonic_elapsed_s=me,effective_elapsed_s=self._max_elapsed,
            anomaly=self.fatal_clock_anomaly)
        return self._max_elapsed

    def remaining(self, compute=False):
        return self.data['compute_limit_seconds' if compute else 'total_limit_seconds']-self.elapsed()

    def check(self, compute=False):
        remaining = self.remaining(compute)
        if self.fatal_clock_anomaly:
            raise BudgetExceeded('ROUND24_CLOCK_ANOMALY')
        if remaining <= 0:
            raise BudgetExceeded('ROUND24_COMPUTE_DEADLINE' if compute else 'ROUND24_TOTAL_DEADLINE')

    def timeout(self):
        self.check(True)
        return max(.001, min(self.remaining(), self.remaining(True)))


def classify(exc):
    if str(exc).startswith('ROUND24_GUARD_'):
        return 'FAIL'
    if isinstance(exc, subprocess.TimeoutExpired):
        return 'BLOCKED'
    return archived_classify(exc)
