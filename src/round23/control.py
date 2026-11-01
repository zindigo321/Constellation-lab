"""One effective preparation-inclusive clock for every R23 parent and child."""
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
        'ROUND23_DELIVERY_PREFLIGHT_NOT_PASS')
    require(Path(data['root']).resolve()==preferred and
        Path(data['destination']).resolve()==preferred/work.name,
        'ROUND23_DELIVERY_PREFLIGHT_DESTINATION')
    require(data.get('destination_absent_before_export') is True,
        'ROUND23_DELIVERY_PREFLIGHT_ABSENCE_BOOL')
    stamp=datetime.datetime.fromisoformat(data['observed_utc'].replace('Z','+00:00'))
    require(stamp.tzinfo is not None and stamp.utcoffset()==datetime.timedelta(0),
        'ROUND23_DELIVERY_PREFLIGHT_UTC')
    require(stamp.timestamp()<=(time.time() if now_epoch is None else now_epoch),
        'ROUND23_DELIVERY_PREFLIGHT_IN_FUTURE')
    require(not (preferred/work.name).exists(),'ROUND23_DELIVERY_DESTINATION_ALREADY_EXISTS')
    return data


def verify_shell_probes(work):
    """Bind fresh actual Python/script/outer exits and pre-start-null evidence."""
    folder=Path(work)/'preparation'
    data=read(folder/'shell_probe_observations.json')
    require(data.get('status')=='PASS' and data.get('observed_after_actual_tool_process_exits') is True and
        data.get('outer_wrapper_explicit_exit_global_LASTEXITCODE') is True,
        'ROUND23_SHELL_PROBE_NOT_OBSERVED')
    seven,prestart=data['seven'],data['prestart']
    require(all(type(seven.get(key)) is int and seven[key]==7 for key in
        ['python_exit_code','script_exit_code','actual_outer_shell_exit_code']),
        'ROUND23_SHELL7_PROPAGATION')
    require(prestart.get('python_exit_code') is None and prestart.get('python_started') is False and
        prestart.get('launch_status')=='PRE_START_FAILURE' and
        type(prestart.get('actual_outer_shell_exit_code')) is int and prestart['actual_outer_shell_exit_code']==1,
        'ROUND23_PRESTART_NULL_EXIT')
    for item,stem in [(seven,'shell7'),(prestart,'shell_null')]:
        require(sha(folder/(stem+'.ps1'))==item['source_sha256'] and
            sha(folder/(stem+'_pending.json'))==item['pending_sha256'],'ROUND23_SHELL_PROBE_BYTES')
        pending=read(folder/(stem+'_pending.json'))
        if stem=='shell7':
            require(type(pending.get('python_exit_code')) is int and pending['python_exit_code']==7 and
                type(pending.get('script_exit_code')) is int and pending['script_exit_code']==7 and
                pending.get('python_started') is True,'ROUND23_SHELL7_PENDING_MISMATCH')
        else:
            require(pending.get('python_exit_code') is None and pending.get('python_started') is False and
                pending.get('launch_status')=='PRE_START_FAILURE','ROUND23_NULL_PENDING_MISMATCH')
    require(type(data.get('science_candidates_evaluated')) is int and data['science_candidates_evaluated']==0,
        'ROUND23_PROBE_CANDIDATE_BOUNDARY')
    return data


class Lifecycle:
    def __init__(self, path):
        self.path = Path(path)
        self.data = read(path)
        d = self.data
        record = float(d.get('record_epoch', d['start_epoch']))
        offset = float(d.get('preparation_offset_seconds', 0))
        effective = float(d['effective_start_epoch'])
        require(all(math.isfinite(v) for v in [record, offset, effective]) and offset >= 0,
                'ROUND23_INVALID_CLOCK')
        require(abs(record-offset-effective) <= 1e-6, 'ROUND23_PREPARATION_OFFSET_MISMATCH')
        require(d['start_epoch'] == effective and d.get('start_epoch_already_includes_preparation') is True,
                'ROUND23_START_MUST_INCLUDE_PREPARATION')
        require(d['compute_limit_seconds'] == 6600 and d['total_limit_seconds'] == 7200,
                'ROUND23_CLOCK_LIMITS')
        self.effective_start_epoch = effective
        self._start = time.monotonic() - (time.time()-effective)

    def elapsed(self):
        return time.monotonic()-self._start

    def remaining(self, compute=False):
        return self.data['compute_limit_seconds' if compute else 'total_limit_seconds']-self.elapsed()

    def check(self, compute=False):
        if self.remaining(compute) <= 0:
            raise BudgetExceeded('ROUND23_COMPUTE_DEADLINE' if compute else 'ROUND23_TOTAL_DEADLINE')

    def timeout(self):
        self.check(True)
        return max(.001, min(self.remaining(), self.remaining(True)))


def classify(exc):
    if str(exc).startswith('ROUND23_GUARD_'):
        return 'FAIL'
    if isinstance(exc, subprocess.TimeoutExpired):
        return 'BLOCKED'
    return archived_classify(exc)
