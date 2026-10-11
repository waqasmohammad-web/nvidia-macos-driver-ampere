"""Conservative 60 Hz API frame-pacing gates, separate from pixel/scanout checks."""
import math
try:
    from .ga102_visual_validation import repeated_result
except ImportError:
    from ga102_visual_validation import repeated_result

STATE_KEYS = ('window_visible', 'window_on_active_space', 'window_unoccluded',
              'window_in_onscreen_list', 'session_on_console', 'display_active')


def evaluate(evidence, correlation):
    states = evidence.get('visibility_samples', [])
    eligible = evidence.get('preflight_ready') is True and bool(states) and all(all(s.get(k) is True for k in STATE_KEYS)
                                   and s.get('display_asleep') is False for s in states)
    attempted = evidence.get('attempted', 0)
    commands = ('FAIL' if evidence.get('command_errors', 0) > 0 or
                evidence.get('outstanding', 0) > 0 or evidence.get('completed') != attempted
                or (eligible and attempted != 120)
                else 'PASS' if attempted == 120 else 'NOT VERIFIED')
    checks = {'command_completion': commands, 'sampled_visible_eligibility': 'PASS' if eligible else 'NOT VERIFIED'}
    configuration = (evidence.get('display_width') == 3440 and evidence.get('display_height') == 1440
                     and 59 <= evidence.get('display_refresh_hz', 0) <= 61)
    checks['target_display_configuration'] = 'PASS' if configuration else 'NOT VERIFIED'
    times = evidence.get('presented_times', [])
    ids = evidence.get('presented_frame_ids', [])
    valid = (len(times) >= 118 and len(times) == len(ids) and
             all(isinstance(t, (int, float)) and math.isfinite(t) and t > 0 for t in times))
    pacing = 'NOT VERIFIED'
    metrics = {}
    if eligible and configuration and valid:
        intervals = [(b - a) * 1000 for a, b in zip(times[10:], times[11:])]
        gaps = sum(b != a + 1 for a, b in zip(ids[10:], ids[11:]))
        ordered = sorted(intervals)
        p95 = ordered[math.ceil(len(ordered) * .95) - 1]
        metrics = {'interval_samples': len(intervals), 'p95_ms': p95,
                   'max_ms': max(intervals), 'late_intervals': sum(t > 25 for t in intervals),
                   'frame_id_gaps': gaps}
        pacing = 'PASS' if (all(b > a for a, b in zip(times, times[1:])) and
                            all(isinstance(i, int) and 0 <= i < 120 for i in ids) and
                            all(b > a for a, b in zip(ids, ids[1:])) and
                            gaps == 0 and p95 <= 20 and max(intervals) <= 25 and
                            evidence.get('timer_skips', 0) == 0) else 'FAIL'
    checks['api_frame_pacing_60hz'] = pacing
    deltas = correlation.get('deltas', {})
    errors = ('debug.nvaccel_iop_async_drop', 'debug.nvaccel_iop_async_refused', 'debug.nvaccel_iop_fail')
    checks['system_display_activity'] = ('FAIL' if any(deltas.get(k, 0) > 0 for k in errors) else
        'PASS' if deltas.get('debug.nvrmfb_flip_n', 0) > 0 and all(k in deltas and deltas[k] >= 0 for k in errors) else 'NOT VERIFIED')
    overall = 'FAIL' if 'FAIL' in checks.values() else 'PASS' if all(v == 'PASS' for v in checks.values()) else 'NOT VERIFIED'
    return {'automated_pacing_validation': overall, 'checks': checks, 'metrics': metrics,
            'physical_scanout': 'NOT VERIFIED', 'frame_contents': 'NOT VERIFIED', 'installed_driver_fixed': False}


def repeated_pacing_result(runs, requested_runs, source_sha256):
    result = repeated_result(runs, requested_runs, source_sha256,
                             check_names=('command_completion', 'sampled_visible_eligibility',
                                          'target_display_configuration', 'api_frame_pacing_60hz', 'system_display_activity'))
    result['probe'] = 'ga102_metal_present'
    result['automated_pacing_validation'] = result.pop('automated_visual_validation')
    result['frame_contents'] = 'NOT VERIFIED'
    result['thresholds'] = {'target_hz': 60, 'warmup_presentations_excluded': 10,
                            'minimum_positive_timestamps': 118, 'p95_ms_max': 20,
                            'interval_ms_max': 25, 'frame_id_gaps_max': 0,
                            'timer_skips_max': 0}
    return result
