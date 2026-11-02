"""R28 grouped diagnostic statistics; no official coverage/performance scores.

Production method: sort all sensor intervals for each fixed point and extend the
current union.  Zero-duration contacts are retained but excluded from visits;
their formal treatment remains unconfirmed.  Input events are never changed.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from collections import Counter
from pathlib import Path

COMPLETE = {"COMPLETED_WITH_ACCESS", "COMPLETED_NO_ACCESS"}
STATES = COMPLETE | {"COMPUTATION_ERROR", "NOT_COMPUTED_BUDGET"}


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label}: expected a JSON number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label}: non-finite value")
    return value


def _inputs(points, events, statuses, duration_s, merge_tolerance_s):
    duration = _number(duration_s, "duration_s")
    tolerance = _number(merge_tolerance_s, "merge_tolerance_s")
    if duration <= 0 or tolerance < 0:
        raise ValueError("duration must be positive and tolerance nonnegative")
    if not all(isinstance(x, list) for x in (points, events, statuses)):
        raise ValueError("points, events, and statuses must be lists")
    ids = []
    id_set = set()
    for p in points:
        if not isinstance(p, dict):
            raise ValueError("point is not an object")
        key = p.get("point_id")
        if not isinstance(key, str) or not key or key in id_set:
            raise ValueError("missing, empty, or duplicate point ID")
        if not isinstance(p.get("layer"), str) or not p["layer"]:
            raise ValueError(f"{key}: missing layer")
        for field in ("latitude_geodetic_deg", "longitude_deg", "height_m"):
            if field in p:
                value = _number(p[field], f"{key}.{field}")
                if field == "latitude_geodetic_deg" and not -90 <= value <= 90:
                    raise ValueError(f"{key}: invalid latitude")
                if field == "longitude_deg" and not -180 <= value < 180:
                    raise ValueError(f"{key}: noncanonical longitude")
        ids.append(key)
        id_set.add(key)
    status_map = {}
    for s in statuses:
        if not isinstance(s, dict):
            raise ValueError("status is not an object")
        key = s.get("point_id")
        if not isinstance(key, str) or key not in id_set or key in status_map:
            raise ValueError("unknown or duplicate status point ID")
        if s.get("computation_status") not in STATES:
            raise ValueError(f"{key}: invalid computation status")
        status_map[key] = s
    if set(status_map) != set(ids):
        raise ValueError("missing point status")
    grouped = {key: [] for key in ids}
    for index, e in enumerate(events):
        if (not isinstance(e, dict) or not isinstance(e.get("point_id"), str)
                or e["point_id"] not in grouped):
            raise ValueError("invalid event or unknown event point ID")
        for field in ("sat_id", "sensor_id"):
            if not isinstance(e.get(field), str) or not e[field]:
                raise ValueError(f"event {index}: missing {field}")
        start = _number(e.get("start_epsec"), f"event {index}.start_epsec")
        stop = _number(e.get("stop_epsec"), f"event {index}.stop_epsec")
        if stop < start:
            raise ValueError(f"event {index}: negative interval duration")
        grouped[e["point_id"]].append((index, e, start, stop))
    for key in ids:
        count = len(grouped[key])
        s = status_map[key]
        state = s["computation_status"]
        if (state == "COMPLETED_WITH_ACCESS") != (count > 0):
            raise ValueError(f"{key}: event count contradicts computation status")
        if "raw_interval_count" in s:
            declared = s["raw_interval_count"]
            unknown_incomplete_count = declared is None and state not in COMPLETE and count == 0
            if not unknown_incomplete_count and (type(declared) is not int or declared < 0 or declared != count):
                raise ValueError(f"{key}: declared raw count mismatch")
    return duration, tolerance, status_map, grouped


def _layer_summary(rows):
    counts = Counter(row["computation_status"] for row in rows)
    completed = [r for r in rows if r["computation_status"] in COMPLETE]
    gaps = [g for row in completed for g in row["internal_gaps_s"]]
    return {
        "declared_point_count": len(rows),
        "completed_point_count": len(completed),
        "computation_error_count": counts["COMPUTATION_ERROR"],
        "not_computed_budget_count": counts["NOT_COMPUTED_BUDGET"],
        "zero_visit_count": sum(r["merged_visit_count"] == 0 for r in completed),
        "one_visit_count": sum(r["merged_visit_count"] == 1 for r in completed),
        "at_least_two_visit_count": sum(r["merged_visit_count"] >= 2 for r in completed),
        "raw_interval_count": sum(r["raw_interval_count"] for r in rows),
        "zero_duration_contact_count": sum(len(r["zero_duration_contacts"]) for r in rows),
        "internal_gap_count": len(gaps),
        "internal_gap_sum_s": math.fsum(gaps) if gaps else None,
        "mean_internal_gap_s": math.fsum(gaps) / len(gaps) if gaps else None,
        "max_internal_gap_s": max(gaps) if gaps else None,
        "all_declared_points_computed": len(completed) == len(rows),
        "all_declared_points_at_least_two_visits": bool(rows) and len(completed) == len(rows)
            and all(r["merged_visit_count"] >= 2 for r in completed),
    }


def _legacy_summarize(points, events, statuses, duration_s, merge_tolerance_s,
                      original_events=None):
    """Validate the fixed denominator and compute per-point diagnostic unions.

    COMPLETED_WITH_ACCESS refers to a nonempty raw interval export.  Positive
    intervals clipped to [0, duration_s] define visits. Contacts are reported
    separately; out-of-window records are counted and preserved. Error/unrun
    points must have no events and receive null statistics, never zero visits.
    An incomplete status may declare raw_interval_count=null. The returned raw
    count describes exported records (zero), never an assertion of no access.
    """
    duration, tolerance, status_map, grouped = _inputs(
        points, events, statuses, duration_s, merge_tolerance_s)
    rows = []
    for point in points:
        key = point["point_id"]
        source = grouped[key]
        state = status_map[key]["computation_status"]
        clipped = []
        contacts = []
        outside = 0
        for index, event, start, stop in source:
            if stop < 0 or start > duration:
                outside += 1
                continue
            a, b = max(0.0, start), min(duration, stop)
            entry = {"raw_event_index": index, "sat_id": event["sat_id"],
                     "sensor_id": event["sensor_id"], "start_epsec": a,
                     "stop_epsec": b}
            clipped.append(entry)
            if a == b:
                contacts.append({**entry, "source_zero_duration": start == stop})
        ordered = sorted((c["start_epsec"], c["stop_epsec"]) for c in clipped
                         if c["stop_epsec"] > c["start_epsec"])
        merged = []
        bridge_lengths = []
        for start, stop in ordered:
            if not merged or start - merged[-1][1] > tolerance:
                merged.append([start, stop])
            else:
                if start > merged[-1][1]:
                    bridge_lengths.append(start - merged[-1][1])
                merged[-1][1] = max(merged[-1][1], stop)
        done = state in COMPLETE
        visits = len(merged) if done else None
        gaps = [b[0] - a[1] for a, b in zip(merged, merged[1:])] if done else None
        coverage = math.fsum(b - a for a, b in merged) if done else None
        row = {
            "point_id": key, "layer": point["layer"], "point": copy.deepcopy(point),
            "computation_status": state,
            "raw_interval_count": len(source),
            "raw_intervals": [copy.deepcopy(original_events[item[0]] if
                original_events is not None else item[1]) for item in source],
            "clipped_intervals": clipped,
            "zero_duration_contacts": contacts,
            "outside_window_interval_count": outside,
            "merged_intervals": [{"start_epsec": a, "stop_epsec": b} for a, b in merged]
                if done else None,
            "merged_visit_count": visits,
            "first_hit_s": merged[0][0] if done and merged else None,
            "first_wait_s": merged[0][0] if done and merged else None,
            "tail_wait_s": duration - merged[-1][1] if done and merged else None,
            "no_access_duration_s": duration - coverage if done else None,
            "union_covered_duration_s": coverage,
            "internal_gaps_s": gaps,
            "internal_gap_count": len(gaps) if done else None,
            "gap_sum_s": math.fsum(gaps) if gaps else None,
            "max_internal_gap_s": max(gaps) if gaps else None,
            "insufficient_visits": visits < 2 if done else None,
            "tolerance_bridge_count": len(bridge_lengths) if done else None,
            "tolerance_bridged_duration_s": math.fsum(bridge_lengths) if done else None,
        }
        rows.append(row)
    return {
        "scope": "DIAGNOSTIC_SUBSET_STATISTICS",
        "implementation": "production_sorted_union_v1",
        "duration_s": duration, "merge_tolerance_s": tolerance,
        "zero_duration_policy": "RETAIN_CONTACT_EXCLUDE_FROM_VISITS_PENDING_FORMAL_CONFIRMATION",
        "official_score": None, "official_readiness": "UNRESOLVED",
        "points": rows,
        "all_declared_point_count": len(rows),
        "summary_population": "DECLARED_POINTS_EXCLUDING_CALIBRATION_ONLY",
        "summary": _layer_summary([r for r in rows if r["layer"] != "CALIBRATION_ONLY"]),
        "calibration_summary": _layer_summary([r for r in rows if r["layer"] == "CALIBRATION_ONLY"]),
        "layers": {layer: _layer_summary([r for r in rows if r["layer"] == layer])
                   for layer in sorted({p["layer"] for p in points})},
    }


def _query_inputs(points, events, statuses, sat_ids, start, stop):
    """Validate the required satellite x point matrix before any point is done."""
    if not isinstance(sat_ids, list) or not sat_ids or any(type(x) is not str or not x for x in sat_ids) or len(set(sat_ids)) != len(sat_ids):
        raise ValueError('required_sat_ids must be a nonempty unique string list')
    if any(not isinstance(value, list) for value in (points, events, statuses)):
        raise ValueError('points/events/statuses must be lists')
    if any(not isinstance(p, dict) or type(p.get('point_id')) is not str or not p['point_id'] for p in points):
        raise ValueError('invalid point identity')
    point_ids=[p['point_id'] for p in points]
    if len(set(point_ids)) != len(point_ids):raise ValueError('duplicate point ID')
    required={(p,s) for p in point_ids for s in sat_ids}
    pairs={};query_ids={};query_counts={}
    for q in statuses:
        if not isinstance(q, dict):raise ValueError('query status must be an object')
        pair=(q.get('point_id'),q.get('sat_id'));qid=q.get('query_id')
        if pair not in required or pair in pairs:raise ValueError('unknown/duplicate satellite-point query')
        if type(qid) is not str or not qid or qid in query_ids:raise ValueError('missing/duplicate query ID')
        _query_window(q.get('query_window_epsec'), start, stop)
        if q.get('computation_status') not in COMPLETE | {'COMPUTATION_ERROR','NOT_RUN','NOT_COMPUTED_BUDGET'}:raise ValueError('unknown query status')
        pairs[pair]=q;query_ids[qid]=q;query_counts[qid]=0
    if set(pairs)!=required:raise ValueError('missing required query status; declare NOT_RUN explicitly')
    seen=set()
    for e in events:
        if not isinstance(e, dict):raise ValueError('event must be an object')
        qid=e.get('query_id')
        if qid not in query_ids:raise ValueError('event references unknown query ID')
        q=query_ids[qid]
        if (e.get('point_id'),e.get('sat_id'))!=(q['point_id'],q['sat_id']):raise ValueError('event/query identity conflict')
        if q.get('sensor_object_path'):
            if e.get('sensor_object_path')!=q['sensor_object_path'] or e.get('sensor_id')!=q['sensor_object_path'].rsplit('/',1)[-1]:raise ValueError('event/query sensor identity conflict')
        if 'query_window_epsec' in e:_query_window(e['query_window_epsec'], start, stop)
        if 'solver_sha256' in q and e.get('event_solver_config_sha256') != q['solver_sha256']:
            raise ValueError('event/query solver binding mismatch')
        a=_number(e.get('start_epsec'),'event start');b=_number(e.get('stop_epsec'),'event stop')
        if not start<=a<=b<=stop:raise ValueError('event outside declared native query window or reversed')
        identity=(qid,e.get('sensor_id'),a,b)
        if identity in seen:raise ValueError('duplicate event identity within query')
        seen.add(identity);query_counts[qid]+=1
    point_status=[]
    for p in point_ids:
        qs=[pairs[p,s] for s in sat_ids]
        for q in qs:
            n=query_counts[q['query_id']];state=q['computation_status'];count=q.get('raw_interval_count')
            if state=='COMPLETED_WITH_ACCESS' and n==0:raise ValueError('WITH_ACCESS query without events')
            if state in {'COMPLETED_NO_ACCESS','NOT_RUN','NOT_COMPUTED_BUDGET'} and n:raise ValueError('no-access/unrun query has events')
            if count is None:
                if state in COMPLETE:raise ValueError('completed query requires known raw count')
            elif type(count) is not int or count<0 or count!=n:raise ValueError('query raw count mismatch')
        done=all(q['computation_status'] in COMPLETE for q in qs)
        n=sum(query_counts[q['query_id']] for q in qs)
        state=('COMPLETED_WITH_ACCESS' if n else 'COMPLETED_NO_ACCESS') if done else ('COMPUTATION_ERROR' if any(q['computation_status']=='COMPUTATION_ERROR' for q in qs) else 'NOT_COMPUTED_BUDGET')
        point_status.append(dict(point_id=p,computation_status=state,raw_interval_count=n,queries=copy.deepcopy(qs),complete=done))
    return point_status


def _query_window(value, start, stop):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('query window requires two numbers')
    if [_number(value[0], 'query start'), _number(value[1], 'query stop')] != [start, stop]:
        raise ValueError('query window mismatch')


def summarize(points, events, statuses, duration_s, merge_tolerance_s, window_start_s=0.0, required_sat_ids=None):
    """R27 query-aware statistics. Partial observations never imply completeness.

    The original R26 sorted-union implementation is retained as the observed
    interval calculation. Complete query evidence is validated separately;
    incomplete points retain raw/observed intervals but have null primary metrics.
    All window lengths and tolerances must be supplied by consumers.
    """
    duration=_number(duration_s,'duration');start=_number(window_start_s,'window_start')
    tolerance=_number(merge_tolerance_s,'merge_tolerance')
    if duration<=0 or tolerance<0:raise ValueError('invalid duration/tolerance')
    stop=start+duration
    if not math.isfinite(stop):raise ValueError('nonfinite window end')
    query_mode=required_sat_ids is not None
    derived=_query_inputs(points,events,statuses,required_sat_ids,start,stop) if query_mode else None
    # Observed interval union is meaningful even when another required query failed.
    observed_statuses=[dict(point_id=p['point_id'],computation_status='COMPLETED_WITH_ACCESS' if p['raw_interval_count'] else 'COMPLETED_NO_ACCESS',raw_interval_count=p['raw_interval_count']) for p in derived] if query_mode else statuses
    shifted=[]
    for original in events:
        if not isinstance(original, dict):raise ValueError('event must be an object')
        e=dict(original)
        e['start_epsec']=_number(original.get('start_epsec'),'start_epsec')-start
        e['stop_epsec']=_number(original.get('stop_epsec'),'stop_epsec')-start
        shifted.append(e)
    result=_legacy_summarize(points,shifted,observed_statuses,duration,tolerance,events)
    for row in result['points']:
        for key in ['clipped_intervals','zero_duration_contacts','merged_intervals']:
            for interval in row[key] or []:
                interval['start_epsec']+=start;interval['stop_epsec']+=start
        if row['first_hit_s'] is not None:row['first_hit_s']+=start
    if query_mode:
        metric_fields=['merged_intervals','merged_visit_count','first_hit_s','last_stop_s','first_wait_s','tail_wait_s','no_access_duration_s','union_covered_duration_s','internal_gaps_s','internal_gap_count','gap_sum_s','mean_internal_gap_s','max_internal_gap_s','insufficient_visits','tolerance_bridge_count','tolerance_bridged_duration_s']
        for row,q in zip(result['points'],derived):
            row['mean_internal_gap_s']=row['gap_sum_s']/row['internal_gap_count'] if row['internal_gap_count'] else None
            row['last_stop_s']=row['merged_intervals'][-1]['stop_epsec'] if row['merged_intervals'] else None
            row['query_statuses']=q['queries'];row['required_query_count']=len(required_sat_ids)
            row['completed_query_count']=sum(s['computation_status'] in COMPLETE for s in q['queries'])
            row['statistics_complete']=q['complete'];row['computation_status']=q['computation_status']
            row['observed_statistics']={k:copy.deepcopy(row[k]) for k in metric_fields}
            row['observed_statistics']['provisional']=not q['complete']
            row['contributing_satellite_ids']=sorted({e['sat_id'] for e in row['raw_intervals'] if e['stop_epsec']>e['start_epsec']})
            if not q['complete']:
                for field in metric_fields:row[field]=None
        result['summary']=_layer_summary([r for r in result['points'] if r['layer']!='CALIBRATION_ONLY'])
        result['calibration_summary']=_layer_summary([r for r in result['points'] if r['layer']=='CALIBRATION_ONLY'])
        result['layers']={layer:_layer_summary([r for r in result['points'] if r['layer']==layer]) for layer in sorted({p['layer'] for p in points})}
        for section in [result['summary'],result['calibration_summary'],*result['layers'].values()]:section['statistics_status']='COMPLETE' if section['all_declared_points_computed'] else 'INCOMPLETE_REQUIRED_QUERIES'
        result['required_satellite_ids']=list(required_sat_ids)
        result['query_count']=len(statuses)
        result['completed_query_count']=sum(q['computation_status'] in COMPLETE for q in statuses)
        result['statistics_status']='COMPLETE' if all(q['complete'] for q in derived) else 'INCOMPLETE_REQUIRED_QUERIES'
        result['incomplete_policy']='Preserve all raw events and observed unions; primary point statistics null until every required satellite query completes; summaries use completed points only and disclose denominator.'
    if query_mode or start:
        result['window_start_s']=start;result['window_end_s']=stop
        result['implementation']='production_sorted_union_query_v2'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="JSON object: points, events, statuses")
    parser.add_argument("--out", required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--merge-tolerance", type=float, required=True)
    parser.add_argument("--window-start", type=float, default=0.0)
    parser.add_argument("--sat-ids", nargs="+")
    args = parser.parse_args()
    try:
        data = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
        result = summarize(data["points"], data["events"], data["statuses"],
                           args.duration, args.merge_tolerance, args.window_start, args.sat_ids)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        result = {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}
        exit_code = 1
    else:
        exit_code = 0
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                        allow_nan=False) + "\n", encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
