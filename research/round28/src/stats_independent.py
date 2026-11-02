"""Independent R28 grouped endpoint-sweep checker, with no production imports.

At each unique event endpoint, an occupancy counter changes. Exact connected
components are formed by that sweep, then tiny empty components are joined
under the separately implemented diagnostic tolerance rule. This module also
independently validates the fixed point/status set and computes gaps and waits.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path


def _finite(x, name):
    if type(x) not in (int, float) or not math.isfinite(x):
        raise ValueError(name + ": invalid finite numeric input")
    return float(x)


def _validate(points, events, statuses, duration_s, tolerance_s):
    duration = _finite(duration_s, "duration")
    tolerance = _finite(tolerance_s, "tolerance")
    if not duration > 0 or tolerance < 0:
        raise ValueError("invalid duration/tolerance")
    if type(points) is not list or type(events) is not list or type(statuses) is not list:
        raise ValueError("three input collections must be lists")
    point_map = {}
    for point in points:
        if type(point) is not dict:
            raise ValueError("invalid point object")
        point_id = point.get("point_id")
        if type(point_id) is not str or point_id == "" or point_id in point_map:
            raise ValueError("invalid or repeated point identity")
        layer = point.get("layer")
        if type(layer) is not str or layer == "":
            raise ValueError("invalid layer")
        coordinate_rules = {"latitude_geodetic_deg": (-90, 90, True),
                            "longitude_deg": (-180, 180, False),
                            "height_m": None}
        for name, bounds in coordinate_rules.items():
            if name in point:
                value = _finite(point[name], name)
                if bounds is not None:
                    lo, hi, inclusive_hi = bounds
                    if value < lo or value > hi or (value == hi and not inclusive_hi):
                        raise ValueError("coordinate outside declared domain")
        point_map[point_id] = point
    state_map = {}
    for status in statuses:
        if type(status) is not dict:
            raise ValueError("invalid status object")
        key = status.get("point_id")
        if type(key) is not str or key not in point_map or key in state_map:
            raise ValueError("status set contains unknown/repeated point")
        if status.get("computation_status") not in (
            "COMPLETED_WITH_ACCESS", "COMPLETED_NO_ACCESS", "COMPUTATION_ERROR",
            "NOT_COMPUTED_BUDGET"
        ):
            raise ValueError("unknown computation status")
        state_map[key] = status
    if len(state_map) != len(point_map):
        raise ValueError("status set does not cover fixed point set")
    event_map = {key: [] for key in point_map}
    for event_index in range(len(events)):
        event = events[event_index]
        if type(event) is not dict:
            raise ValueError("invalid event object")
        key = event.get("point_id")
        if type(key) is not str or key not in event_map:
            raise ValueError("event references undeclared point")
        if any(type(event.get(k)) is not str or not event[k] for k in ("sat_id", "sensor_id")):
            raise ValueError("event lacks sensor/satellite identity")
        beginning = _finite(event.get("start_epsec"), "event start")
        ending = _finite(event.get("stop_epsec"), "event stop")
        if beginning > ending:
            raise ValueError("event is reversed")
        event_map[key].append((event_index, event, beginning, ending))
    for key, status in state_map.items():
        count = len(event_map[key])
        state = status["computation_status"]
        if state == "COMPLETED_WITH_ACCESS":
            if count == 0:
                raise ValueError("access status lacks raw events")
        elif count != 0:
            raise ValueError("raw events contradict no-access/error/unrun status")
        if "raw_interval_count" in status:
            declared = status["raw_interval_count"]
            if declared is None and state in ("COMPUTATION_ERROR", "NOT_COMPUTED_BUDGET"):
                if count:
                    raise ValueError("unknown incomplete count cannot accompany exported events")
            elif type(declared) is not int or declared < 0 or declared != count:
                raise ValueError("raw interval count mismatch")
    return duration, tolerance, state_map, event_map


def _sweep(clipped, tolerance):
    changes = {}
    for interval in clipped:
        a, b = interval["start_epsec"], interval["stop_epsec"]
        if a < b:
            changes[a] = changes.get(a, 0) + 1
            changes[b] = changes.get(b, 0) - 1
    occupancy = 0
    opening = None
    components = []
    for endpoint in sorted(changes):
        previous = occupancy
        occupancy += changes[endpoint]
        if previous == 0 and occupancy > 0:
            opening = endpoint
        if previous > 0 and occupancy == 0:
            components.append((opening, endpoint))
            opening = None
        if occupancy < 0:
            raise ValueError("endpoint sweep has negative occupancy")
    if occupancy != 0 or opening is not None:
        raise ValueError("endpoint sweep is unbalanced")
    joined = []
    bridges = []
    index = 0
    while index < len(components):
        left, right = components[index]
        index += 1
        while index < len(components):
            following_start, following_end = components[index]
            empty_duration = following_start - right
            if empty_duration > tolerance:
                break
            bridges.append(empty_duration)
            right = following_end
            index += 1
        joined.append((left, right))
    return joined, bridges


def _aggregate(rows):
    n_done = n_error = n_unrun = n_zero = n_one = n_multi = raw = contacts = 0
    gap_values = []
    for row in rows:
        raw += row["raw_interval_count"]
        contacts += len(row["zero_duration_contacts"])
        state = row["computation_status"]
        if state == "COMPUTATION_ERROR":
            n_error += 1
        elif state == "NOT_COMPUTED_BUDGET":
            n_unrun += 1
        else:
            n_done += 1
            visits = row["merged_visit_count"]
            if visits == 0:
                n_zero += 1
            elif visits == 1:
                n_one += 1
            else:
                n_multi += 1
            gap_values.extend(row["internal_gaps_s"])
    count = len(gap_values)
    total = math.fsum(gap_values) if count else None
    return {
        "declared_point_count": len(rows), "completed_point_count": n_done,
        "computation_error_count": n_error, "not_computed_budget_count": n_unrun,
        "zero_visit_count": n_zero, "one_visit_count": n_one,
        "at_least_two_visit_count": n_multi, "raw_interval_count": raw,
        "zero_duration_contact_count": contacts, "internal_gap_count": count,
        "internal_gap_sum_s": total,
        "mean_internal_gap_s": total / count if count else None,
        "max_internal_gap_s": max(gap_values) if count else None,
        "all_declared_points_computed": n_done == len(rows),
        "all_declared_points_at_least_two_visits": len(rows) > 0 and n_multi == len(rows),
    }


def _legacy_summarize(points, events, statuses, duration_s, merge_tolerance_s,
                      original_records=None):
    duration, tolerance, states, events_by_point = _validate(
        points, events, statuses, duration_s, merge_tolerance_s)
    output = []
    for point in points:
        key = point["point_id"]
        state = states[key]["computation_status"]
        clipped, contacts, raw_records = [], [], []
        outside_count = 0
        for number, original, a, b in events_by_point[key]:
            raw_records.append(copy.deepcopy(original_records[number] if
                original_records is not None else original))
            if a > duration or b < 0:
                outside_count += 1
            else:
                interval = {"raw_event_index": number,
                            "sat_id": original["sat_id"], "sensor_id": original["sensor_id"],
                            "start_epsec": 0.0 if a < 0 else a,
                            "stop_epsec": duration if b > duration else b}
                clipped.append(interval)
                if interval["start_epsec"] == interval["stop_epsec"]:
                    contact = dict(interval)
                    contact["source_zero_duration"] = (a == b)
                    contacts.append(contact)
        completed = state.startswith("COMPLETED_")
        unions, bridges = _sweep(clipped, tolerance)
        gaps = None
        covered = None
        if completed:
            gaps = []
            for index in range(1, len(unions)):
                gaps.append(unions[index][0] - unions[index - 1][1])
            covered = math.fsum(interval[1] - interval[0] for interval in unions)
        has_visits = completed and len(unions) > 0
        output.append({
            "point_id": key, "layer": point["layer"], "point": copy.deepcopy(point),
            "computation_status": state, "raw_interval_count": len(raw_records),
            "raw_intervals": raw_records, "clipped_intervals": clipped,
            "zero_duration_contacts": contacts, "outside_window_interval_count": outside_count,
            "merged_intervals": [{"start_epsec": t[0], "stop_epsec": t[1]} for t in unions]
                if completed else None,
            "merged_visit_count": len(unions) if completed else None,
            "first_hit_s": unions[0][0] if has_visits else None,
            "first_wait_s": unions[0][0] if has_visits else None,
            "tail_wait_s": duration - unions[-1][1] if has_visits else None,
            "no_access_duration_s": duration - covered if completed else None,
            "union_covered_duration_s": covered,
            "internal_gaps_s": gaps,
            "internal_gap_count": len(gaps) if completed else None,
            "gap_sum_s": math.fsum(gaps) if gaps else None,
            "max_internal_gap_s": max(gaps) if gaps else None,
            "insufficient_visits": len(unions) < 2 if completed else None,
            "tolerance_bridge_count": len(bridges) if completed else None,
            "tolerance_bridged_duration_s": math.fsum(bridges) if completed else None,
        })
    layers = {}
    for layer in sorted(set(p["layer"] for p in points)):
        layers[layer] = _aggregate([row for row in output if row["layer"] == layer])
    return {
        "scope": "DIAGNOSTIC_SUBSET_STATISTICS",
        "implementation": "independent_endpoint_sweep_v1",
        "duration_s": duration, "merge_tolerance_s": tolerance,
        "zero_duration_policy": "RETAIN_CONTACT_EXCLUDE_FROM_VISITS_PENDING_FORMAL_CONFIRMATION",
        "official_score": None, "official_readiness": "UNRESOLVED",
        "points": output, "all_declared_point_count": len(output),
        "summary_population": "DECLARED_POINTS_EXCLUDING_CALIBRATION_ONLY",
        "summary": _aggregate([r for r in output if r["layer"] != "CALIBRATION_ONLY"]),
        "calibration_summary": _aggregate([r for r in output if r["layer"] == "CALIBRATION_ONLY"]),
        "layers": layers,
    }


def _audit_queries(points, records, queries, satellites, begin, end):
    if type(satellites) is not list or len(satellites)==0:
        raise ValueError('required satellite list absent')
    if any(type(s) is not str or not s for s in satellites) or len(set(satellites))!=len(satellites):
        raise ValueError('invalid/repeated satellite identity')
    if type(points) is not list or type(records) is not list or type(queries) is not list:
        raise ValueError('input collections must be lists')
    if any(type(p) is not dict or type(p.get('point_id')) is not str or not p['point_id'] for p in points):
        raise ValueError('invalid declared point identity')
    pids=[p['point_id'] for p in points]
    if len(set(pids))!=len(pids):raise ValueError('repeated point identity')
    point_set=set(pids);satellite_set=set(satellites)
    by_id={};by_pair={};counts={}
    allowed=('COMPLETED_WITH_ACCESS','COMPLETED_NO_ACCESS','COMPUTATION_ERROR','NOT_RUN','NOT_COMPUTED_BUDGET')
    for query in queries:
        if type(query) is not dict:raise ValueError('query must be an object')
        pid=query.get('point_id');sid=query.get('sat_id');qid=query.get('query_id')
        if pid not in point_set or sid not in satellite_set or (pid,sid) in by_pair:
            raise ValueError('query has unknown/repeated point-satellite identity')
        if type(qid) is not str or qid=='' or qid in by_id:
            raise ValueError('query ID invalid/repeated')
        _check_window(query.get('query_window_epsec'), begin, end)
        if query.get('computation_status') not in allowed:
            raise ValueError('query window/status invalid')
        by_id[qid]=query;by_pair[pid,sid]=query;counts[qid]=0
    if len(by_pair)!=len(pids)*len(satellites):raise ValueError('required query matrix incomplete')
    identities=set()
    for record in records:
        if type(record) is not dict:raise ValueError('event record must be an object')
        qid=record.get('query_id')
        if qid not in by_id:raise ValueError('event has no declared query')
        q=by_id[qid]
        if q['point_id']!=record.get('point_id') or q['sat_id']!=record.get('sat_id'):
            raise ValueError('event identity disagrees with query')
        if q.get('sensor_object_path'):
            expected=q['sensor_object_path']
            if record.get('sensor_object_path')!=expected or record.get('sensor_id')!=expected.split('/')[-1]:raise ValueError('event sensor disagrees with declared query sensor')
        if 'query_window_epsec' in record:_check_window(record['query_window_epsec'], begin, end)
        if 'solver_sha256' in q:
            if record.get('event_solver_config_sha256') != q['solver_sha256']:
                raise ValueError('event solver disagrees with query solver binding')
        a=_finite(record.get('start_epsec'),'event start');b=_finite(record.get('stop_epsec'),'event stop')
        if a<begin or b>end or b<a:raise ValueError('event outside native query window/reversed')
        identity=(qid,record.get('sensor_id'),a,b)
        if identity in identities:raise ValueError('duplicate raw interval identity')
        identities.add(identity);counts[qid]+=1
    derived=[]
    for pid in pids:
        selected=[by_pair[pid,sid] for sid in satellites]
        n=0;unfinished=0;errors=0
        for query in selected:
            qid=query['query_id'];state=query['computation_status'];count=counts[qid];declared=query.get('raw_interval_count')
            if state=='COMPLETED_WITH_ACCESS' and count<1:raise ValueError('query WITH_ACCESS has no events')
            if state in ('COMPLETED_NO_ACCESS','NOT_RUN','NOT_COMPUTED_BUDGET') and count!=0:raise ValueError('query no-access/unrun contradicts events')
            if declared is None:
                if state.startswith('COMPLETED_'):raise ValueError('complete query lacks count')
            elif type(declared) is not int or declared<0 or declared!=count:raise ValueError('query count disagrees')
            n+=count
            if not state.startswith('COMPLETED_'):unfinished+=1
            if state=='COMPUTATION_ERROR':errors+=1
        if unfinished:state='COMPUTATION_ERROR' if errors else 'NOT_COMPUTED_BUDGET'
        else:state='COMPLETED_WITH_ACCESS' if n else 'COMPLETED_NO_ACCESS'
        derived.append(dict(point_id=pid,computation_status=state,raw_interval_count=n,queries=copy.deepcopy(selected),complete=(unfinished==0)))
    return derived


def _check_window(window, beginning, ending):
    if type(window) is not list or len(window) != 2:
        raise ValueError('invalid query window shape')
    left = _finite(window[0], 'query window left')
    right = _finite(window[1], 'query window right')
    if left != beginning or right != ending:
        raise ValueError('query window endpoint mismatch')


def summarize(points, events, statuses, duration_s, merge_tolerance_s, window_start_s=0.0, required_sat_ids=None):
    duration=_finite(duration_s,'duration');begin=_finite(window_start_s,'window start')
    tolerance=_finite(merge_tolerance_s,'tolerance');end=begin+duration
    if duration<=0 or tolerance<0 or not math.isfinite(end):raise ValueError('invalid time window/tolerance')
    native_queries=required_sat_ids is not None
    audit=_audit_queries(points,events,statuses,required_sat_ids,begin,end) if native_queries else None
    if native_queries:
        observed=[]
        for row in audit:
            observed.append(dict(point_id=row['point_id'],raw_interval_count=row['raw_interval_count'],computation_status='COMPLETED_WITH_ACCESS' if row['raw_interval_count']>0 else 'COMPLETED_NO_ACCESS'))
    else:observed=statuses
    translated=[]
    for event in events:
        if type(event) is not dict:raise ValueError('event must be an object')
        item=dict(event)
        item['start_epsec']=_finite(event.get('start_epsec'),'start_epsec')-begin
        item['stop_epsec']=_finite(event.get('stop_epsec'),'stop_epsec')-begin
        translated.append(item)
    result=_legacy_summarize(points,translated,observed,duration,tolerance,events)
    for row in result['points']:
        for name in ('clipped_intervals','zero_duration_contacts','merged_intervals'):
            if row[name] is not None:
                for interval in row[name]:
                    interval['start_epsec']=interval['start_epsec']+begin
                    interval['stop_epsec']=interval['stop_epsec']+begin
        if row['first_hit_s'] is not None:row['first_hit_s']=row['first_hit_s']+begin
    if native_queries:
        primary=('merged_intervals','merged_visit_count','first_hit_s','last_stop_s','first_wait_s','tail_wait_s','no_access_duration_s','union_covered_duration_s','internal_gaps_s','internal_gap_count','gap_sum_s','mean_internal_gap_s','max_internal_gap_s','insufficient_visits','tolerance_bridge_count','tolerance_bridged_duration_s')
        for index,row in enumerate(result['points']):
            row['mean_internal_gap_s']=row['gap_sum_s']/row['internal_gap_count'] if row['internal_gap_count'] else None
            row['last_stop_s']=row['merged_intervals'][-1]['stop_epsec'] if row['merged_intervals'] else None
            evidence=audit[index]
            row['query_statuses']=evidence['queries'];row['required_query_count']=len(required_sat_ids)
            row['completed_query_count']=sum(q['computation_status'] in ('COMPLETED_WITH_ACCESS','COMPLETED_NO_ACCESS') for q in evidence['queries'])
            row['statistics_complete']=evidence['complete'];row['computation_status']=evidence['computation_status']
            observed_values={name:copy.deepcopy(row[name]) for name in primary}
            observed_values['provisional']=not evidence['complete']
            row['observed_statistics']=observed_values
            row['contributing_satellite_ids']=sorted(set(e['sat_id'] for e in row['raw_intervals'] if e['stop_epsec']>e['start_epsec']))
            if not evidence['complete']:
                for name in primary:row[name]=None
        result['summary']=_aggregate([r for r in result['points'] if r['layer']!='CALIBRATION_ONLY'])
        result['calibration_summary']=_aggregate([r for r in result['points'] if r['layer']=='CALIBRATION_ONLY'])
        result['layers']={layer:_aggregate([r for r in result['points'] if r['layer']==layer]) for layer in sorted(set(p['layer'] for p in points))}
        for section in [result['summary'],result['calibration_summary'],*result['layers'].values()]:section['statistics_status']='COMPLETE' if section['all_declared_points_computed'] else 'INCOMPLETE_REQUIRED_QUERIES'
        result['required_satellite_ids']=list(required_sat_ids)
        result['query_count']=len(statuses)
        result['completed_query_count']=sum(q['computation_status'].startswith('COMPLETED_') for q in statuses)
        result['statistics_status']='COMPLETE' if all(q['complete'] for q in audit) else 'INCOMPLETE_REQUIRED_QUERIES'
        result['incomplete_policy']='Preserve all raw events and observed unions; primary point statistics null until every required satellite query completes; summaries use completed points only and disclose denominator.'
    if native_queries or begin:
        result['window_start_s']=begin;result['window_end_s']=end
        result['implementation']='independent_endpoint_sweep_query_v2'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--merge-tolerance", type=float, required=True)
    parser.add_argument("--window-start", type=float, default=0.0)
    parser.add_argument("--sat-ids", nargs="+")
    args = parser.parse_args()
    try:
        with open(args.input, encoding="utf-8-sig") as stream:
            inputs = json.load(stream)
        result = summarize(inputs["points"], inputs["events"], inputs["statuses"],
                           args.duration, args.merge_tolerance, args.window_start, args.sat_ids)
    except (ValueError, TypeError, KeyError, OSError) as error:
        result = {"status": "FAIL", "error": f"{type(error).__name__}: {error}"}
        code = 1
    else:
        code = 0
    with open(args.out, "w", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
