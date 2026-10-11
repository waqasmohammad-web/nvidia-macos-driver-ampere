"""Evidence categories for the owned-window probe; physical scanout stays separate."""
def evaluate(evidence, correlation):
    frames = evidence.get('frames', 0)
    checks = {}
    if frames < 3 or 'gpu_correct_frames' not in evidence or 'gpu_distinct_patterns' not in evidence:
        checks['gpu_frame_contents'] = 'NOT VERIFIED'
    else:
        checks['gpu_frame_contents'] = 'PASS' if evidence['gpu_correct_frames'] == frames and evidence['gpu_distinct_patterns'] >= 3 else 'FAIL'
    checks['presentation_timestamps'] = 'PASS' if frames >= 3 and evidence.get('positive_timestamps', 0) >= frames - 2 and evidence.get('timestamps_increasing') is True and evidence.get('distinct_timestamps', 0) >= frames - 2 else 'NOT VERIFIED'
    checks['visible_window_state'] = 'PASS' if frames >= 3 and evidence.get('visible_frames') == frames else 'NOT VERIFIED'
    attempted = evidence.get('capture_attempted', 0)
    received = evidence.get('capture_received_frames', 0)
    if not evidence.get('capture_permission') or received < 3:
        checks['own_window_capture'] = 'NOT VERIFIED'
    elif evidence.get('capture_correct_frames') != received or evidence.get('capture_distinct_patterns', 0) < 3:
        checks['own_window_capture'] = 'FAIL'
    elif received != frames:
        checks['own_window_capture'] = 'NOT VERIFIED'
    else:
        checks['own_window_capture'] = 'PASS'
    deltas = correlation.get('deltas', {})
    errors = ('debug.nvaccel_iop_async_drop', 'debug.nvaccel_iop_async_refused', 'debug.nvaccel_iop_fail')
    checks['system_display_activity'] = ('FAIL' if any(deltas.get(k, 0) > 0 for k in errors) else
        'PASS' if deltas.get('debug.nvrmfb_flip_n', 0) > 0 and all(k in deltas for k in errors) else 'NOT VERIFIED')
    overall = 'FAIL' if 'FAIL' in checks.values() else 'PASS' if all(v == 'PASS' for v in checks.values()) else 'NOT VERIFIED'
    return {'automated_visual_validation': overall, 'checks': checks,
            'physical_scanout': 'NOT VERIFIED', 'installed_driver_fixed': False}
