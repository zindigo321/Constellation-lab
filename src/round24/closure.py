"""Total-only recovery after the coordinator's own compute Job was closed."""
import argparse
from pathlib import Path
from src.round13.common import read,write,sha,require
from .control import Lifecycle
from .guard import install
from .binding import ROOT
from .seal import seal

def main():
    p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--work',required=True)
    work=Path(p.parse_args().work).resolve();require(work.parent==ROOT/'work/round24','R24_CLOSURE_WORK')
    install(work,work/'closure_guard.jsonl',role='finalizer')
    life=Lifecycle(work/'lifecycle.json');life.check(False)
    status='FAIL' if (work/'execution_failure.json').exists() else 'BLOCKED'
    selected={}
    contract=work/'frozen/contract.json'
    if contract.exists():
        digest=sha(contract)
        for attempt in sorted((work/'attempts').glob('*')):
            if ((attempt/'consumer_contract.json').exists() and sha(attempt/'consumer_contract.json')==digest
                    and (attempt/'output').exists()):
                job=attempt.name.rsplit('_',1)[-1]
                if job in {'tests','guards','legacy','science'}:selected[job]=attempt
    write(work/'closure_recovery.json',dict(status=status,mode='TOTAL_ONLY_PREFIX',
        reason='Independent parent observed coordinator compute deadline and closed its own Job',
        selected_attempts={k:str(v) for k,v in selected.items()},
        unobserved_grandchild_exit_codes=None,science_input_reloaded=False,new_candidates_evaluated=0))
    result=seal(work,selected,status,['Independent coordinator compute-deadline recovery'])
    return result['exit_code']
