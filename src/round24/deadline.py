"""Absolute UTC/QPC deadline supervision; only own suspended Job descendants."""
import ctypes
from ctypes import wintypes
import datetime
import json
import os
from pathlib import Path
import subprocess
import time
from src.round16.supervise import (CREATE_SUSPENDED, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, JOBOBJECT_EXTENDED_LIMIT_INFORMATION)
from src.round13.common import write


class DeadlineExpired(subprocess.TimeoutExpired):
    def __init__(self, argv, timeout, observation):
        super().__init__(argv, timeout)
        self.observation = observation
        self.returncode = observation['actual_process_exit_code']


def wait_absolute(proc, life, compute, timeout, start_utc, start_mono, heartbeat=lambda x:None,
                  utc=time.time, mono=time.perf_counter):
    """Testable wait logic. Late exit 0 remains a deadline failure."""
    waits = 0
    kind = 'NOT_WAITED'
    maximum_local_elapsed = 0.0
    def sample():
        nonlocal maximum_local_elapsed
        u,m=utc(),mono()
        elapsed=life.elapsed()
        maximum_local_elapsed=max(maximum_local_elapsed,u-start_utc,m-start_mono)
        is_compute=compute() if callable(compute) else compute
        limit=life.data['compute_limit_seconds' if is_compute else 'total_limit_seconds']
        deadline=elapsed>=limit or maximum_local_elapsed>=timeout or life.fatal_clock_anomaly
        return dict(utc_epoch=u,monotonic_seconds=m,utc_wall_s=u-start_utc,
            monotonic_wall_s=m-start_mono,elapsed_s=elapsed,configured_timeout_s=timeout,
            deadline_exceeded=deadline,deadline_kind='COMPUTE' if is_compute else 'TOTAL',
            overrun_s=max(0.0,elapsed-limit,maximum_local_elapsed-timeout),
            clock_anomalies=list(life.anomalies),wait_return_type=kind,wait_calls=waits)
    while True:
        state=sample();heartbeat(state)
        if state['deadline_exceeded']:
            return state
        remaining=min(timeout-maximum_local_elapsed,life.remaining(compute() if callable(compute) else compute))
        try:
            proc.wait(timeout=max(.001,min(1.0,remaining)))
            kind='PROCESS_EXIT'
        except subprocess.TimeoutExpired:
            kind='SHORT_WAIT_TIMEOUT'
        waits+=1
        state=sample();heartbeat(state)
        if state['deadline_exceeded'] or kind=='PROCESS_EXIT':
            return state


def run(argv, *, cwd, env, stdout, stderr, timeout, life, compute=True, evidence=None, progress=None):
    if os.name!='nt':raise RuntimeError('ROUND24_WINDOWS_JOB_REQUIRED')
    start_u,start_m=time.time(),time.perf_counter()
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    ntdll=ctypes.WinDLL('ntdll',use_last_error=True)
    kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype=wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    kernel.SetInformationJobObject.restype=wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype=wintypes.BOOL
    kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
    ntdll.NtResumeProcess.argtypes=[wintypes.HANDLE];ntdll.NtResumeProcess.restype=ctypes.c_long
    job=kernel.CreateJobObjectW(None,None)
    if not job:raise ctypes.WinError(ctypes.get_last_error())
    proc=None;assigned=False;closed=False;observation={};forced=False
    evidence=Path(evidence) if evidence else None
    last_heartbeat=[-100.0]
    def beat(state):
        if not evidence:return
        # Independent parent progress sampling does not rely on the worker checking.
        if state['deadline_exceeded'] or state['wait_return_type']=='PROCESS_EXIT' or state['monotonic_seconds']-last_heartbeat[0]>=1:
            last_heartbeat[0]=state['monotonic_seconds']
            item=dict(state,pid=proc.pid if proc else None,last_worker_progress=None)
            if progress and Path(progress).exists():
                try:item['last_worker_progress']=json.loads(Path(progress).read_text(encoding='utf8'))
                except (ValueError,OSError):item['progress_read_state']='CONCURRENT_OR_PARTIAL_WRITE'
            evidence.parent.mkdir(parents=True,exist_ok=True)
            with evidence.with_suffix('.heartbeat.jsonl').open('a',encoding='utf8') as stream:
                stream.write(json.dumps(item,ensure_ascii=False)+'\n')
    def close():
        nonlocal closed
        if not closed:
            if not kernel.CloseHandle(job):raise ctypes.WinError(ctypes.get_last_error())
            closed=True
    try:
        life.check(compute() if callable(compute) else compute)
        limits=JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(job,JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,ctypes.byref(limits),ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        proc=subprocess.Popen(argv,cwd=cwd,env=env,stdout=stdout,stderr=stderr,creationflags=CREATE_SUSPENDED)
        if not kernel.AssignProcessToJobObject(job,wintypes.HANDLE(int(proc._handle))):
            raise ctypes.WinError(ctypes.get_last_error())
        assigned=True
        life.check(compute() if callable(compute) else compute)
        status=ntdll.NtResumeProcess(wintypes.HANDLE(int(proc._handle)))
        if status<0:raise OSError('ROUND24_NT_RESUME_FAILED:'+hex(status&0xffffffff))
        observation=wait_absolute(proc,life,compute,timeout,start_u,start_m,beat)
        # Always close this job, including successful parent exits with live descendants.
        forced=observation['deadline_exceeded'] and proc.poll() is None
        close()
        for _ in range(5):
            if proc.poll() is not None:break
            try:proc.wait(timeout=1)
            except subprocess.TimeoutExpired:pass
        observation.update(actual_process_exit_code=proc.poll(),real_exit_observed=proc.returncode is not None,
            forced_termination=forced,job_closed=True,pid=proc.pid,argv=list(argv),cwd=str(cwd),
            final_utc_epoch=time.time(),final_monotonic_seconds=time.perf_counter(),
            start_utc_epoch=start_u,start_monotonic_seconds=start_m,
            scope='Only own suspended child and inherited Job descendants',host_sleep_reproduced=False)
        if evidence:write(evidence,observation)
        if observation['deadline_exceeded']:raise DeadlineExpired(argv,timeout,observation)
        # Check again after cleanup; its time is part of this operation.
        try:life.check(compute() if callable(compute) else compute)
        except Exception:
            observation['deadline_exceeded']=True
            observation['overrun_s']=max(observation['overrun_s'] , -life.remaining(compute() if callable(compute) else compute),0)
            if evidence:write(evidence,observation)
            raise DeadlineExpired(argv,timeout,observation)
        return subprocess.CompletedProcess(argv,proc.returncode)
    finally:
        try:
            if proc is not None and not assigned and proc.poll() is None:proc.kill()
            close()
        finally:
            if proc is not None:
                for _ in range(5):
                    if proc.poll() is not None:break
                    try:proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:pass
                proc._handle.Close()
