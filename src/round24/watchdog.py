"""Independent total-deadline parent around preparation, coordinator and delivery."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from src.round13.common import read,write,require
from .control import Lifecycle
from .deadline import run,DeadlineExpired
from .guard import install,register_command
from .binding import ROOT


def cli(default_mode=None):
    p=argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('--mode',default=default_mode,choices=['initialize','preflight','pretests','research','export','finalizer','observer'])
    p.add_argument('--work',required=True)
    args,rest=p.parse_known_args()
    require(args.mode is not None,'R24_WATCHDOG_MODE')
    work=Path(args.work).resolve();require(work.parent==ROOT/'work/round24','R24_WATCHDOG_WORK')
    life=Lifecycle(work/'lifecycle.json');compute=args.mode in {'initialize','preflight','pretests'}
    if args.mode=='research':
        def compute():
            try:return read(work/'coordinator_phase.json').get('phase')!='CLOSURE'
            except (OSError,ValueError):return True
    folder=work/'outer_supervision'/(args.mode+'_'+str(time.time_ns()));folder.mkdir(parents=True)
    argv=[sys.executable,'-X','utf8','-B','-m','src.round24.entry','--mode',args.mode,'--work',str(work),*rest]
    destination=Path(read(ROOT/'configs/round24.json')['preferred_output'])/work.name
    commands=[];register_command(commands,argv,ROOT,work,destination)
    install(work,folder/'guard.jsonl',role='supervisor',commands=commands)
    code=None;status='FAIL';error=None
    try:
        with (folder/'stdout.log').open('wb') as out,(folder/'stderr.log').open('wb') as err:
            proc=run(argv,cwd=ROOT,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),stdout=out,stderr=err,
                timeout=max(.001,life.remaining(False if callable(compute) else compute)),life=life,compute=compute,
                evidence=folder/'deadline.json',progress=work/'input_progress/latest.json')
        code=proc.returncode;status={0:'PASS',1:'FAIL',2:'BLOCKED'}.get(code,'FAIL')
    except DeadlineExpired as e:
        code=e.returncode;status='BLOCKED';error=str(e)
        if args.mode=='research' and life.remaining(False)>0 and not life.fatal_clock_anomaly:
            # An unresponsive coordinator cannot consume the entire closure reserve.
            closure=[sys.executable,'-X','utf8','-B','-m','src.round24.entry','--mode','closure','--work',str(work)]
            register_command(commands,closure,ROOT,work)
            try:
                with (folder/'closure.stdout.log').open('wb') as out,(folder/'closure.stderr.log').open('wb') as err:
                    recovered=run(closure,cwd=ROOT,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),stdout=out,stderr=err,
                        timeout=life.remaining(False),life=life,compute=False,evidence=folder/'closure.deadline.json')
                write(folder/'closure.result.json',dict(actual_child_python_exit_code=recovered.returncode,
                    original_coordinator_exit_code=code,original_deadline_preserved=True))
                if recovered.returncode==1:status='FAIL'
            except Exception as ce:
                write(folder/'closure.error.json',dict(error=type(ce).__name__+': '+str(ce),
                    actual_child_exit_code=getattr(ce,'returncode',None),original_deadline_preserved=True))
    except Exception as e:
        error=type(e).__name__+': '+str(e)
        from .control import classify
        status=classify(e)
    if (work/'execution_failure.json').exists() and read(work/'execution_failure.json').get('status')=='FAIL':status='FAIL'
    result=dict(status=status,actual_child_python_exit_code=code,supervisor_return_code={'PASS':0,'FAIL':1,'BLOCKED':2}[status],
        actual_supervisor_exit_observed=False,mode=args.mode,argv=argv,error=error,
        elapsed_s=life.elapsed(),budget_compliance=life.elapsed()<=7200,overrun_s=max(0,life.elapsed()-7200),
        observation=str(folder/'deadline.json'),stdout=str(folder/'stdout.log'),stderr=str(folder/'stderr.log'))
    write(folder/'result.json',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result['supervisor_return_code']


if __name__=='__main__':raise SystemExit(cli())
