"""Two exact read-only historical ROOT scopes; copied tests stay unchanged."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sys

WHITELIST = {
    'test_round19_binding.BindingTests.test_old268_preserved_and_subsets_have_exact_members':
        dict(module='src.round19.binding', count=268, config='round19', prior='r18_delivery'),
    'test_round20_binding.BindingTests.test_old292_and_exact_historical_subsets':
        dict(module='src.round20.binding', count=292, config='round20', prior='r19_delivery'),
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_reference_rows(rows, original, expected_count=268):
    original = Path(original).resolve()
    names, result = set(), []
    if len(rows) != expected_count:
        raise ValueError('R22_REFERENCE_COUNT')
    for row in rows:
        name = row['relative_path']
        path = original/name
        if (not name or '\\' in name or Path(name).is_absolute() or '..' in Path(name).parts
                or name.casefold() in names or not path.resolve().is_relative_to(original)
                or path.is_symlink() or any(p.is_symlink() for p in path.parents if p.is_relative_to(original))
                or path.resolve() != Path(row['path']).resolve()):
            raise ValueError('R22_REFERENCE_PATH')
        names.add(name.casefold())
        if path.stat().st_size != row['bytes'] or digest(path) != row['sha256']:
            raise ValueError('R22_REFERENCE_BYTES')
        result.append(dict(path=str(path), bytes=row['bytes'], sha256=row['sha256']))
    return result


@contextmanager
def reference_scope(test_id, module, repo, original, source_test, copy_test, expected_sha, rows, log):
    """Only these two IDs adapt; restoration runs for normal and exceptional exits."""
    if test_id not in WHITELIST:
        yield
        return
    repo, original = Path(repo).resolve(), Path(original).resolve()
    before = module.ROOT
    if Path(before).resolve() != repo:
        raise ValueError('R22_REFERENCE_INITIAL_ROOT')
    if digest(source_test) != expected_sha or digest(copy_test) != expected_sha:
        raise ValueError('R22_REFERENCE_TEST_BYTES')
    count = WHITELIST[test_id]['count']
    mapping = validate_reference_rows(rows, original, count)
    event = dict(test_id=test_id, executed_copy_root=str(repo), historical_reference_root=str(original),
        before_ROOT=str(before), test_source_sha256=expected_sha, original_before=mapping,
        temp=os.environ.get('TEMP'), tmp=os.environ.get('TMP'), reference_only=True,
        copied_source_modified=False, original_project_writes_allowed=False)
    try:
        module.ROOT = original
        yield
    finally:
        module.ROOT = before
        event.update(after_ROOT=str(module.ROOT), restored=module.ROOT == before)
        validation_error = None
        try:
            event['original_after'] = validate_reference_rows(rows, original, count)
            event['test_bytes_preserved'] = digest(source_test) == digest(copy_test) == expected_sha
            if not event['restored'] or not event['test_bytes_preserved']:
                raise ValueError('R22_REFERENCE_RESTORE_OR_BYTES')
        except Exception as exc:
            validation_error = exc
            event.update(validation_error=repr(exc), test_bytes_preserved=False)
        with Path(log).open('a', encoding='utf8') as stream:
            stream.write(json.dumps(event, ensure_ascii=False)+'\n')
        if validation_error is not None:
            raise validation_error


def install():
    import unittest
    original_run = unittest.TestCase.run

    def run(test, result=None):
        test_id = test.id()
        if test_id not in WHITELIST:
            return original_run(test, result)
        spec = WHITELIST[test_id]
        repo = Path(os.environ['ROUND22_LEGACY_REPO'])
        original = Path(os.environ['ROUND22_ORIGINAL_ROOT'])
        cfg = json.loads((repo/('configs/'+spec['config']+'.json')).read_text(encoding='utf8'))
        rows = json.loads((Path(cfg[spec['prior']])/'sealed/frozen/consumer_code.json').read_text(encoding='utf8'))
        test_module = test_id.split('.')[0]
        expected_sha = json.loads(os.environ['ROUND22_REFERENCE_TEST_SHAS'])[test_module]
        with reference_scope(test_id, sys.modules[spec['module']], repo, original,
                original/('tests/'+test_module+'.py'), repo/('tests/'+test_module+'.py'),
                expected_sha, rows, os.environ['ROUND22_REFERENCE_LOG']):
            return original_run(test, result)

    unittest.TestCase.run = run
