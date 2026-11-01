"""Generate exact UTF-8 PowerShell launch records; external tool observes its exit."""
import argparse
from pathlib import Path
import sys
from src.round13.common import read,require
from .binding import ROOT
from .guard import install

def quote(value):return "'"+str(value).replace("'","''")+"'"

def prepare(work,kind,label='a1',retry=False):
    work=Path(work).resolve();require(work.parent==ROOT/'work/round21','R21_SHELL_WORK')
    require(label.isalnum(),'R21_SHELL_LABEL')
    install(work,work/'observations'/('shell_prepare_'+kind+'_'+label+'.jsonl'),role='finalizer')
    destination=Path(read(ROOT/'configs/round21.json')['preferred_output'])/work.name
    script='tools/run_round21.py' if kind=='research' else 'tools/export_round21.py'
    argv=[sys.executable,'-X','utf8','-B',script,'--work',str(work)]
    if kind=='research':
        if retry:argv+=['--new-attempt']
    else:
        argv+=['--destination',str(destination)]
        if kind=='finalizer':argv+=['--finalize-shell-record',str(work/'observations/export_shell_result.json')]
    folder=work/'transport' if kind=='research' else work/'observations'
    folder.mkdir(parents=True,exist_ok=True)
    prefix=kind+'_'+label;path=work/'observations'/(prefix+'.ps1')
    require(not path.exists(),'R21_SHELL_ALREADY_EXISTS')
    rawout=folder/(prefix+'_stdout_raw.log');rawerr=folder/(prefix+'_stderr_raw.log')
    stdout=folder/(prefix+'_stdout.log');stderr=folder/(prefix+'_stderr.log')
    pending=work/'observations'/(prefix+'_pending.json')
    body=f"""$ErrorActionPreference = 'Continue'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:GIT_OPTIONAL_LOCKS = '0'
Set-Location -LiteralPath {quote(ROOT)}
$round21Started = [DateTime]::UtcNow.ToString('o')
$round21Watch = [Diagnostics.Stopwatch]::StartNew()
$LASTEXITCODE = $null
& {' '.join(quote(a) for a in argv)} 1> {quote(rawout)} 2> {quote(rawerr)}
$round21PythonExit = $LASTEXITCODE
$round21LaunchStatus = if ($null -eq $round21PythonExit) {{ 'PRE_START_FAILURE' }} else {{ 'STARTED' }}
$round21Utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText({quote(stdout)}, [IO.File]::ReadAllText({quote(rawout)}), $round21Utf8)
[IO.File]::WriteAllText({quote(stderr)}, [IO.File]::ReadAllText({quote(rawerr)}), $round21Utf8)
$round21Observation = [ordered]@{{
    kind = {quote(kind)}
    label = {quote(label)}
    python_exit_code = $round21PythonExit
    launch_status = $round21LaunchStatus
    shell_exit_code = $null
    observed_after_process_exit = $false
    actual_argv = @({','.join(quote(a) for a in argv)})
    cwd = {quote(ROOT)}
    shell_pid = $PID
    shell_source = {quote(path)}
    start_utc = $round21Started
    end_utc = [DateTime]::UtcNow.ToString('o')
    shell_wall_s = $round21Watch.Elapsed.TotalSeconds
    stdout = {quote(stdout)}
    stderr = {quote(stderr)}
}}
[IO.File]::WriteAllText({quote(pending)}, ($round21Observation | ConvertTo-Json -Depth 6), $round21Utf8)
Write-Output ($round21Observation | ConvertTo-Json -Depth 6 -Compress)
if ($null -eq $round21PythonExit) {{ exit 1 }}
exit $round21PythonExit
"""
    path.write_text(body,encoding='utf8');require(path.read_text(encoding='utf8')==body,'R21_SHELL_UTF8')
    return path

if __name__=='__main__':
    p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--work',required=True)
    p.add_argument('--kind',required=True,choices=['research','export','finalizer']);p.add_argument('--label',default='a1')
    p.add_argument('--retry',action='store_true');args=p.parse_args()
    print(prepare(args.work,args.kind,args.label,args.retry))
