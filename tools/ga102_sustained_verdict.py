#!/usr/bin/env python3
"""Qualify retained 3,600-frame API observations; never certify physical scanout."""
import argparse
import json
import math
from pathlib import Path

from ga102_presentation_trace import analyze


def qualify(data):
    reasons = []
    ids = data.get('presented_frame_ids', [])
    times = data.get('presented_times', [])
    valid = (len(ids) == len(times) and len(set(ids)) == len(ids)
             and all(type(i) is int and 0 <= i < 3600 for i in ids)
             and ids == sorted(ids) and all(type(t) in (int, float) and math.isfinite(t) and t > 0 for t in times)
             and all(b > a for a, b in zip(times, times[1:])))
    missing = sorted(set(range(3600)) - set(ids)) if valid else []
    intervals = [(b-a)*1000 for a, b in zip(times[10:], times[11:])] if valid else []
    ordered = sorted(intervals)
    summary = {k: ordered[min(len(ordered)-1, math.ceil(len(ordered)*q)-1)]
               for k, q in [('p50_ms', .5), ('p95_ms', .95), ('p99_ms', .99)]} if ordered else {}
    summary.update(samples=len(intervals), maximum_ms=max(intervals, default=None),
                   late_intervals=sum(v > 25 for v in intervals), missing_frame_ids=missing)
    command_pass = (data.get('attempted') == 3600 and data.get('completed') == 3600
                    and all(data.get(k) == 0 for k in ['command_errors', 'outstanding', 'timer_skips']))
    if not command_pass: reasons.append('incomplete commands, command errors, outstanding work or skips')
    trace = analyze(data)
    if not valid or trace['trace_collection'] == 'FAIL': reasons.append('invalid or inconsistent clocks/IDs')
    states = data.get('visibility_samples', [])
    eligibility = data.get('preflight_ready') is True and bool(states) and all(
        all(s.get(k) is True for k in ['window_visible', 'window_on_active_space', 'window_unoccluded',
                                    'window_in_onscreen_list', 'session_on_console', 'display_active']) for s in states)
    matched = all(data.get(k) == v for k, v in [('render_width',1920), ('render_height',1080),
                       ('composite_layers',8), ('drawable_count',3), ('display_width',3440), ('display_height',1440)])
    refresh = data.get('display_refresh_hz')
    matched = matched and type(refresh) in (int,float) and math.isfinite(refresh) and abs(refresh-60) <= .1
    sufficient = valid and len(times) >= 3598 and set(missing) <= {0,1} and trace['trace_collection'] == 'PASS'
    if reasons: verdict = 'FAIL'
    elif not eligibility or not matched or not sufficient:
        verdict = 'NOT VERIFIED'
        reasons.append('ineligible visibility/workload or missing presentation/trace evidence')
    elif summary['late_intervals']:
        verdict = 'FAIL'; reasons.append('steady presentation intervals exceed 25 ms')
    else: verdict = 'PASS'
    return {'verdict':verdict, 'command_completion':'PASS' if command_pass else 'FAIL',
            'reasons':reasons, 'presentation':summary, 'trace':trace,
            'physical_scanout':'NOT VERIFIED'}


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('input',type=Path)
    args=p.parse_args(); result=qualify(json.loads(args.input.read_text()))
    print(json.dumps(result,indent=2,allow_nan=False))
    return {'PASS':0,'NOT VERIFIED':2,'FAIL':1}[result['verdict']]


if __name__=='__main__': raise SystemExit(main())
