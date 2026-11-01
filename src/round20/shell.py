"""Generate exact UTF-8 PowerShell launch records; external tool observes its exit."""
import argparse
from pathlib import Path
import sys
from src.round13.common import read,require
from .binding import ROOT
from .guard import install

def quote(value):return "'"+str(value).replace("'","''")+"'"

def prepare(work,kind,label='a1',retry=False):
    work=Path(work).resolve();require(work.parent==ROOT/'work/round20','R20_SHELL_WORK')
    require(label.isalnum(),'R20_SHELL_LABEL')
    install(work,work/'observations'/('shell_prepare_'+kind+'_'+label+'.jsonl'),role='finalizer')
    destination=Path(read(ROOT/'configs/round20.json')['preferred_output'])/work.name
    script='tools/run_round20.py' if kind=='research' else 'tools/export_round20.py'
    argv=[sys.executable,'-X','utf8','-B',script,'--work',str(work)]
    if kind=='research':
        if retry:argv+=['--new-attempt']
    else:
        argv+=['--destination',str(destination)]
        if kind=='finalizer':argv+=['--finalize-shell-record',str(work/'observations/export_shell_result.json')]
    folder=work/'transport' if kind=='research' else work/'observations'
    folder.mkdir(parents=True,exist_ok=True)
    prefix=kind+'_'+label;path=work/'observations'/(prefix+'.ps1')
    require(not path.exists(),'R20_SHELL_ALREADY_EXISTS')
    rawout=folder/(prefix+'_stdout_raw.log');rawerr=folder/(prefix+'_stderr_raw.log')
    stdout=folder/(prefix+'_stdout.log');stderr=folder/(prefix+'_stderr.log')
    pending=work/'observations'/(prefix+'_pending.json')
    body=f"""$ErrorActionPreference = 'Continue'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:GIT_OPTIONAL_LOCKS = '0'
Set-Location -LiteralPath {quote(ROOT)}
$round20Started = [DateTime]::UtcNow.ToString('o')
$round20Watch = [Diagnostics.Stopwatch]::StartNew()
& {' '.join(quote(a) for a in argv)} 1> {quote(rawout)} 2> {quote(rawerr)}
$round20PythonExit = $LASTEXITCODE
$round20Utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText({quote(stdout)}, [IO.File]::ReadAllText({quote(rawout)}), $round20Utf8)
[IO.File]::WriteAllText({quote(stderr)}, [IO.File]::ReadAllText({quote(rawerr)}), $round20Utf8)
$round20Observation = [ordered]@{{
    kind = {quote(kind)}
    label = {quote(label)}
    python_exit_code = $round20PythonExit
    shell_exit_code = $null
    observed_after_process_exit = $false
    actual_argv = @({','.join(quote(a) for a in argv)})
    cwd = {quote(ROOT)}
    shell_pid = $PID
    shell_source = {quote(path)}
    start_utc = $round20Started
    end_utc = [DateTime]::UtcNow.ToString('o')
    shell_wall_s = $round20Watch.Elapsed.TotalSeconds
    stdout = {quote(stdout)}
    stderr = {quote(stderr)}
}}
[IO.File]::WriteAllText({quote(pending)}, ($round20Observation | ConvertTo-Json -Depth 6), $round20Utf8)
Write-Output ($round20Observation | ConvertTo-Json -Depth 6 -Compress)
exit $round20PythonExit
"""
    path.write_text(body,encoding='utf8');require(path.read_text(encoding='utf8')==body,'R20_SHELL_UTF8')
    return path

if __name__=='__main__':
    p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--work',required=True)
    p.add_argument('--kind',required=True,choices=['research','export','finalizer']);p.add_argument('--label',default='a1')
    p.add_argument('--retry',action='store_true');args=p.parse_args()
    print(prepare(args.work,args.kind,args.label,args.retry))
