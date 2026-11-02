"""Self-contained synthetic checks for the published R28 offline core.

No STK, native orbit data, archived work directories or third-party packages.
All generated points, events and query identities are FIXTURE_ONLY.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture():
    points = [dict(point_id=name, layer=layer, latitude_geodetic_deg=0.0,
                   longitude_deg=0.0, height_m=0.0, fixture_only=True)
              for name, layer in [('GAP', 'DIAGNOSTIC_GLOBAL'),
                                  ('ZERO', 'DIAGNOSTIC_GLOBAL'),
                                  ('CAL', 'CALIBRATION_ONLY')]]
    satellites = ['SyntheticA', 'SyntheticB']
    specs = []
    for point in points:
        for satellite in satellites:
            specs.append(dict(point_id=point['point_id'], sat_id=satellite,
                              window_epsec=[1000.0, 1100.0],
                              sensor_object_path=f'Satellite/{satellite}/Sensor/Camera',
                              protocol_sha256='FIXTURE_PROTOCOL', source_sha256='FIXTURE_SOURCE',
                              point_table_sha256='FIXTURE_POINTS'))
    intervals = {
        ('GAP', 'SyntheticA'): [(1010.0, 1020.0), (1040.0, 1045.0)],
        ('GAP', 'SyntheticB'): [(1015.0, 1025.0), (1070.0, 1075.0)],
        ('CAL', 'SyntheticA'): [(1002.0, 1003.0)],
        ('CAL', 'SyntheticB'): [(1004.0, 1006.0)],
    }
    return points, satellites, specs, intervals


def payload(store, spec, intervals):
    query_id = store.query_id(spec)
    events = [dict(**{k: v for k, v in spec.items() if k != 'window_epsec'},
                   query_id=query_id, sensor_id='Camera',
                   query_window_epsec=[1000.0, 1100.0],
                   start_epsec=left, stop_epsec=right,
                   event_solver_config_sha256='FIXTURE_SOLVER', fixture_only=True)
              for left, right in intervals.get((spec['point_id'], spec['sat_id']), [])]
    status = dict(point_id=spec['point_id'], sat_id=spec['sat_id'], query_id=query_id,
                  sensor_object_path=spec['sensor_object_path'],
                  query_window_epsec=[1000.0, 1100.0],
                  computation_status='COMPLETED_WITH_ACCESS' if events else 'COMPLETED_NO_ACCESS',
                  raw_interval_count=len(events), solver_sha256='FIXTURE_SOLVER')
    return events, status


def normalize(result):
    return {key: value for key, value in result.items() if key != 'implementation'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core-dir', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'src')
    parser.add_argument('--out', required=True, type=Path, help='new directory; never overwritten')
    args = parser.parse_args()
    output = args.out.resolve()
    if output.exists():
        parser.error('--out must not already exist')
    output.mkdir(parents=True)
    core = args.core_dir.resolve()
    modules = {name: load_module(name, core / (name + '.py'))
               for name in ['incremental_store', 'stats_production', 'stats_independent']}
    Store = modules['incremental_store'].Store
    points, satellites, specs, intervals = fixture()
    baseline = Store(output / 'complete_store', {'scope': 'FIXTURE_ONLY'}, specs, batch_size=4)
    for spec in specs:
        baseline.commit(spec, *payload(baseline, spec, intervals))
    baseline.close()
    snapshot = baseline.snapshot()
    inputs = dict(points=points, events=snapshot['events'], statuses=snapshot['query_statuses'])
    tests = []
    commands = []

    def check(name, callback):
        start = time.perf_counter()
        try:
            callback()
        except Exception:
            tests.append(dict(name=name, status='FAIL', wall_s=time.perf_counter()-start,
                              traceback=traceback.format_exc()))
        else:
            tests.append(dict(name=name, status='PASS', wall_s=time.perf_counter()-start))

    def both(data):
        before = copy.deepcopy(data)
        results = [modules[name].summarize(data['points'], data['events'], data['statuses'],
                                           duration_s=100.0, merge_tolerance_s=1e-6,
                                           window_start_s=1000.0, required_sat_ids=satellites)
                   for name in ['stats_production', 'stats_independent']]
        assert data == before, 'statistics mutated input'
        assert normalize(results[0]) == normalize(results[1]), 'independent implementations disagree'
        return results[0]

    def rejects(mutator):
        data = copy.deepcopy(inputs)
        mutator(data)
        for name in ['stats_production', 'stats_independent']:
            try:
                modules[name].summarize(data['points'], data['events'], data['statuses'],
                                       100.0, 1e-6, 1000.0, satellites)
            except (ValueError, TypeError, KeyError):
                pass
            else:
                raise AssertionError(name + ' accepted malformed fixture')

    def expected_nonzero_gaps():
        result = both(inputs)
        gap, zero, cal = result['points']
        assert gap['internal_gaps_s'] == [15.0, 25.0]
        assert gap['merged_visit_count'] == 3 and gap['mean_internal_gap_s'] == 20.0
        assert gap['contributing_satellite_ids'] == satellites
        assert gap['first_wait_s'] == 10.0 and gap['tail_wait_s'] == 25.0
        assert result['summary']['internal_gap_count'] == 2
        assert result['summary']['mean_internal_gap_s'] == 20.0
        assert zero['merged_visit_count'] == 0 and zero['first_hit_s'] is None
        assert zero['no_access_duration_s'] == 100.0
        assert cal['internal_gaps_s'] == [1.0]
        assert result['calibration_summary']['internal_gap_count'] == 1
        assert result['official_score'] is None
    check('explicit_multisatellite_union_nonzero_gaps_and_layer_separation', expected_nonzero_gaps)

    def partial_error_preserves_events():
        data = copy.deepcopy(inputs)
        data['statuses'][1]['computation_status'] = 'COMPUTATION_ERROR'
        result = both(data)
        row = result['points'][0]
        assert row['statistics_complete'] is False and row['internal_gap_count'] is None
        assert row['observed_statistics']['internal_gap_count'] == 2
        assert len(row['raw_intervals']) == 4 and result['statistics_status'] != 'COMPLETE'
    check('partial_failed_query_retains_observed_events_but_nulls_primary_metrics', partial_error_preserves_events)

    def not_run_is_not_no_access():
        data = copy.deepcopy(inputs)
        query = data['statuses'][1]
        query['computation_status'] = 'NOT_RUN'
        query['raw_interval_count'] = None
        data['events'] = [e for e in data['events'] if e['query_id'] != query['query_id']]
        row = both(data)['points'][0]
        assert row['merged_visit_count'] is None and len(row['raw_intervals']) == 2
        assert row['computation_status'] == 'NOT_COMPUTED_BUDGET'
    check('unrun_query_is_not_completed_zero_access', not_run_is_not_no_access)
    check('boolean_endpoint_rejected', lambda: rejects(lambda d: d['events'][0].update(start_epsec=True)))
    check('boolean_interval_count_rejected', lambda: rejects(lambda d: d['statuses'][0].update(raw_interval_count=True)))
    check('unknown_query_id_rejected', lambda: rejects(lambda d: d['events'][0].update(query_id='UNKNOWN')))
    check('event_query_identity_mismatch_rejected', lambda: rejects(lambda d: d['events'][0].update(sat_id='SyntheticB')))
    check('sensor_binding_mismatch_rejected', lambda: rejects(lambda d: d['events'][0].update(sensor_id='WrongCamera')))
    check('solver_binding_mismatch_rejected', lambda: rejects(lambda d: d['events'][0].update(event_solver_config_sha256='WRONG')))
    check('missing_required_query_rejected', lambda: rejects(lambda d: d['statuses'].pop()))
    check('duplicate_event_rejected', lambda: rejects(lambda d: d['events'].append(copy.deepcopy(d['events'][0]))))

    def checkpoint_resume():
        cut = Store(output / 'resumed_store', {'scope': 'FIXTURE_ONLY'}, specs, batch_size=4)
        for spec in specs[:4]:
            cut.commit(spec, *payload(cut, spec, intervals))
        cut.close()
        before = {p.relative_to(cut.folder).as_posix(): p.read_bytes()
                  for p in cut.folder.rglob('*') if p.is_file()}
        resumed = Store(cut.folder)
        assert len(resumed.records) == 4
        for spec in specs:
            if not resumed.committed(spec):
                resumed.commit(spec, *payload(resumed, spec, intervals))
        resumed.close()
        assert resumed.snapshot() == snapshot
        assert len(resumed.receipts) == 2 and resumed.receipts[-1]['batch_query_count'] == 2
        assert resumed.metrics()['actual_store_file_count'] == 8
        assert all((resumed.folder/path).read_bytes() == data for path, data in before.items())
        assert normalize(both(dict(points=points, events=resumed.snapshot()['events'],
                                   statuses=resumed.snapshot()['query_statuses']))) == normalize(both(inputs))
    check('store_checkpoint_resume_short_tail_and_statistics_end_to_end', checkpoint_resume)

    def source_binding_rejected():
        store = Store(output/'source_conflict_store', {'scope':'FIXTURE_ONLY'}, specs, batch_size=4)
        events, status = payload(store, specs[0], intervals)
        events[0]['source_sha256'] = 'UNDECLARED_SOURCE'
        try:
            store.commit(specs[0], events, status)
        except modules['incremental_store'].StoreError:
            return
        raise AssertionError('Store accepted undeclared event source identity')
    check('store_source_identity_binding_rejected', source_binding_rejected)

    def cli_agreement():
        source = output / 'synthetic_input.json'
        source.write_text(json.dumps(inputs, allow_nan=False), encoding='utf-8')
        results = []
        for name in ['stats_production', 'stats_independent']:
            target = output / (name + '_cli.json')
            command = [sys.executable, '-I', '-S', '-B', str(core/(name+'.py')),
                       '--input', str(source), '--out', str(target), '--duration', '100',
                       '--merge-tolerance', '0.000001', '--window-start', '1000',
                       '--sat-ids', *satellites]
            run = subprocess.run(command, cwd=output, capture_output=True, timeout=30)
            commands.append(dict(argv=command, actual_process_exit=run.returncode,
                                 shell_used=False, shell_exit=None,
                                 stdout=run.stdout.decode('utf-8', errors='replace'),
                                 stderr=run.stderr.decode('utf-8', errors='replace')))
            assert run.returncode == 0, run.stderr
            results.append(json.loads(target.read_text(encoding='utf-8')))
        assert normalize(results[0]) == normalize(results[1]) == normalize(both(inputs))
    check('both_standalone_cli_match_public_api', cli_agreement)

    failed = [test for test in tests if test['status'] != 'PASS']
    report = dict(status='FAIL' if failed else 'PASS', scope='FIXTURE_ONLY_NO_NATIVE_EVIDENCE',
                  check_count=len(tests), failed_count=len(failed), checks=tests, commands=commands,
                  sources={name+'.py':hashlib.sha256((core/(name+'.py')).read_bytes()).hexdigest()
                           for name in modules},
                  limitations=['Synthetic API/CLI/storage validation only; no STK activation or performance claim.'])
    (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({key:report[key] for key in ['status','scope','check_count','failed_count']}))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
