"""Single explicitly authorized R19 reference-only ROOT adaptation.

Copied unchanged beside sitecustomize; it never changes test source/assertions.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sys

WHITELIST='test_round19_binding.BindingTests.test_old268_preserved_and_subsets_have_exact_members'

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def validate_reference_rows(rows,original):
    original=Path(original).resolve();names=set();result=[]
    if len(rows)!=268:raise ValueError('R20_REFERENCE_COUNT')
    for row in rows:
        name=row['relative_path'];p=original/name
        if name.casefold() in names or not p.resolve().is_relative_to(original) or p.is_symlink() or any(
            q.is_symlink() for q in p.parents if q.is_relative_to(original)) or p.resolve()!=Path(row['path']).resolve():
            raise ValueError('R20_REFERENCE_PATH')
        names.add(name.casefold())
        if p.stat().st_size!=row['bytes'] or digest(p)!=row['sha256']:raise ValueError('R20_REFERENCE_BYTES')
        result.append(dict(path=str(p),bytes=row['bytes'],sha256=row['sha256']))
    return result

@contextmanager
def reference_scope(test_id,module,repo,original,source_test,copy_test,expected_sha,rows,log):
    if test_id!=WHITELIST:
        yield
        return
    repo,original=Path(repo).resolve(),Path(original).resolve();before=module.ROOT
    if Path(before).resolve()!=repo:raise ValueError('R20_REFERENCE_INITIAL_ROOT')
    if digest(source_test)!=expected_sha or digest(copy_test)!=expected_sha:raise ValueError('R20_REFERENCE_TEST_BYTES')
    mapping=validate_reference_rows(rows,original)
    event=dict(test_id=test_id,executed_copy_root=str(repo),historical_reference_root=str(original),
        before_ROOT=str(before),test_source_sha256=expected_sha,original268_before=mapping,
        temp=os.environ.get('TEMP'),tmp=os.environ.get('TMP'))
    try:
        module.ROOT=original
        yield
    finally:
        module.ROOT=before
        event['after_ROOT']=str(module.ROOT);event['restored']=module.ROOT==before
        event['original268_after']=validate_reference_rows(rows,original)
        event['test_bytes_preserved']=digest(source_test)==digest(copy_test)==expected_sha
        with Path(log).open('a',encoding='utf8') as stream:stream.write(json.dumps(event,ensure_ascii=False)+'\n')
        if not event['restored'] or not event['test_bytes_preserved']:raise ValueError('R20_REFERENCE_RESTORE_OR_BYTES')

def install():
    import unittest
    original_run=unittest.TestCase.run
    def run(test,result=None):
        if test.id()!=WHITELIST:return original_run(test,result)
        repo=Path(os.environ['ROUND20_LEGACY_REPO']);original=Path(os.environ['ROUND20_ORIGINAL_ROOT'])
        cfg=json.loads((repo/'configs/round19.json').read_text(encoding='utf8'))
        rows=json.loads((Path(cfg['r18_delivery'])/'sealed/frozen/consumer_code.json').read_text(encoding='utf8'))
        module=sys.modules['src.round19.binding']
        with reference_scope(test.id(),module,repo,original,original/'tests/test_round19_binding.py',
                repo/'tests/test_round19_binding.py',os.environ['ROUND20_REFERENCE_TEST_SHA'],rows,
                os.environ['ROUND20_REFERENCE_LOG']):
            return original_run(test,result)
    unittest.TestCase.run=run
