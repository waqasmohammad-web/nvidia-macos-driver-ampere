"""Correlate CPU observations and reported presentation; never infer scanout."""
import math


def analyze(evidence):
    rows = evidence.get('frame_trace', [])
    required = ('frame', 'draw_start_ms', 'acquisition_ms', 'encode_ms', 'commit_start_ms',
                'commit_return_ms', 'scheduled_callback_ms', 'completed_callback_ms')
    complete = (evidence.get('attempted', 0) > 0 and len(rows) == evidence['attempted'] and
                [r.get('frame') for r in rows] == list(range(evidence['attempted'])) and
                all(all(isinstance(r.get(k), (int, float)) and math.isfinite(r[k]) for k in required) for r in rows))
    if not complete:
        return {'trace_collection': 'NOT VERIFIED', 'late_intervals': [],
                'note': 'per-frame callback evidence incomplete'}
    if any(r['completed_callback_ms'] < r['commit_start_ms'] or
           r['commit_return_ms'] < r['commit_start_ms'] for r in rows):
        return {'trace_collection': 'FAIL', 'late_intervals': [], 'note': 'inconsistent CPU trace ordering'}
    if any(r.get('presented_time_available') == 1 and
           (not isinstance(r.get('presented_time_ms'), (int, float)) or
            not math.isfinite(r['presented_time_ms'])) for r in rows):
        return {'trace_collection': 'FAIL', 'late_intervals': [], 'note': 'invalid positive presentation clock'}
    shown = [r for r in rows if r.get('presented_time_available') == 1 and 'presented_time_ms' in r]
    if any(b['presented_time_ms'] <= a['presented_time_ms'] for a, b in zip(shown, shown[1:])):
        return {'trace_collection': 'FAIL', 'late_intervals': [], 'note': 'non-increasing reported presentation clock'}
    late = []
    for previous, current in zip(shown, shown[1:]):
        interval = current['presented_time_ms'] - previous['presented_time_ms']
        if interval <= 25: continue
        commit_interval = current['commit_start_ms'] - previous['commit_start_ms']
        completion = current['completed_callback_ms'] - current['commit_start_ms']
        previous_completion = previous['completed_callback_ms'] - previous['commit_start_ms']
        after_completion = current['presented_time_ms'] - current['completed_callback_ms']
        flips = None
        if all('system_flips_at_presented_callback' in r for r in (previous, current)):
            flips = current['system_flips_at_presented_callback'] - previous['system_flips_at_presented_callback']
        late.append({'frame': current['frame'], 'previous_frame': previous['frame'],
                     'startup': current['frame'] < 10, 'presentation_interval_ms': interval,
                     'commit_interval_ms': commit_interval,
                     'commit_to_completion_ms': completion,
                     'previous_commit_to_completion_ms': previous_completion,
                     'completion_to_reported_presentation_ms': after_completion,
                     'acquisition_ms': current['acquisition_ms'], 'gpu_ms': current.get('gpu_ms'),
                     'surface_slot': current.get('surface_slot'),
                     'system_flip_delta_between_callbacks': flips,
                     'classification': 'client_completed_promptly' if completion <= 2 and
                         previous_completion <= 2 and commit_interval <= 20 and after_completion >= 0
                         else 'client_delay_or_callback_timing_candidate'})
    return {'trace_collection': 'PASS', 'late_intervals': late,
            'physical_scanout': 'NOT VERIFIED',
            'note': 'CPU callback observations are not raw fence instants; system counters are shared; classification is not a root-cause attribution'}
