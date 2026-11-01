"""External actual-Shell observations and final readback, without receipt edits."""
import argparse
import datetime
import json
from pathlib import Path
import sys
from src.round13.common import read,write,require,sha,record
from .binding import ROOT,verify_sources,verify_runtime
from .control import Lifecycle
from .guard import install

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()

def main():
    p=argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('--work',required=True)
    p.add_argument('--kind',required=True,choices=['research','export','finalizer','final-readback'])
    p.add_argument('--actual-shell-exit',type=int)
    p.add_argument('--label',default='a1')
    args=p.parse_args();work=Path(args.work).resolve()
    require(work.parent==ROOT/'work/round20','R20_OBSERVER_WORK')
    install(work,work/'observations'/(args.kind+'_guard.jsonl'),role='finalizer')
    life=Lifecycle(work/'lifecycle.json');check=lambda:life.check(False);check()
    if args.kind!='final-readback':
        require(args.actual_shell_exit is not None,'R20_MISSING_ACTUAL_SHELL_EXIT')
        pending=read(work/'observations'/(args.kind+'_'+args.label+'_pending.json'))
        require(pending['kind']==args.kind and pending['python_exit_code']==args.actual_shell_exit,'R20_SHELL_PYTHON_EXIT_BINDING')
        result=dict(pending,actual_shell_exit_code=args.actual_shell_exit,observed_after_process_exit=True,
            observed_utc=now(),lifecycle_elapsed_s=life.elapsed(),observer_argv=list(sys.orig_argv),observer_cwd=str(Path.cwd()),
            observation_source='Actual exec_command/write_stdin process completion supplied by outer tool observer')
        if args.kind=='research':
            result['shell_exit_code']=args.actual_shell_exit
            write(work/'transport/shell_default.json',result)
        elif args.kind=='export':
            command=read(work/'export_process/export_command_result.json')
            result.update(export_launcher_python_exit_code=pending['python_exit_code'],export_shell_exit_code=args.actual_shell_exit,
                export_process_exit_code=command['export_process_exit_code'])
            write(work/'observations/export_shell_result.json',result)
        else:
            result.update(finalizer_python_exit_code=pending['python_exit_code'],finalizer_shell_exit_code=args.actual_shell_exit)
        write(work/'observations'/(args.kind+'_actual_exit.json'),result)
        write(work/'observations'/(args.kind+'_'+args.label+'_actual_exit.json'),result)
        print(json.dumps(result,ensure_ascii=False));return 0
    from .export import verify_delivery
    cfg=read(ROOT/'configs/round20.json');destination=Path(cfg['preferred_output'])/work.name
    for kind in ['research','export','finalizer']:
        obs=read(work/'observations'/(kind+'_actual_exit.json'))
        require(obs['observed_after_process_exit'] is True and obs['actual_shell_exit_code']==obs['python_exit_code']==0,'R20_REQUIRED_ACTUAL_EXIT')
    audit=verify_delivery(destination,check)
    verify_sources(read(work/'frozen/consumer_code.json'),check);verify_runtime(work,check)
    finalizer=read(work/'observations/finalizer_actual_exit.json')
    result=dict(audit,recorded_utc=now(),lifecycle_elapsed_s=life.elapsed(),
        delivery_manifest_sha256=sha(destination/'delivery_manifest.json',check),
        delivery_receipt_sha256=sha(destination/'delivery_receipt.json',check),
        transport_manifest_sha256=sha(destination/'transport_manifest.json',check),
        transfer_receipt_sha256=sha(destination/'transfer_receipt.json',check),
        sealed_manifest_sha256=sha(destination/'sealed/artifact_manifest.json',check),
        all_actual_outer_exits_observed_before_readback=True,finalizer_exit_observation=record(work/'observations/finalizer_actual_exit.json'),
        receipt_creation_elapsed_s=read(destination/'delivery_receipt.json')['lifecycle_elapsed_s'],
        finalizer_readback_elapsed_s=read(work/'final_readback_observation.json')['final_readback_completed_elapsed_s'],
        finalizer_actual_outer_exit_observed_elapsed_s=finalizer['lifecycle_elapsed_s'],
        scope='All three exact layers, original-work bytes, full candidate terminal audit, sources and checkpoint/HEAD preservation after real outer exit',
        immutable_receipts_modified=False,native_activation_count=0,git_write_operations=0)
    write(work/'observations/after_all_exits_full_readback.json',result)
    print(json.dumps(result,ensure_ascii=False));return 0

if __name__=='__main__':raise SystemExit(main())
