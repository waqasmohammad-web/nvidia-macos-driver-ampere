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
    received = evidence.get('capture_received_frames', 0)
    if not evidence.get('capture_permission') or received < 3:
        checks['own_window_capture'] = 'NOT VERIFIED'
    elif evidence.get('capture_correct_frames') != received or evidence.get('capture_distinct_patterns', 0) < 3:
        checks['own_window_capture'] = 'FAIL'
    elif received != frames:
        checks['own_window_capture'] = 'NOT VERIFIED'
    else:
        checks['own_window_capture'] = 'PASS'
    if evidence.get('continuous') is True:
        stream=evidence.get('stream_analysis',{})
        content=stream.get('captured_reference_contents','NOT VERIFIED')
        checks['own_window_capture']=('FAIL' if content=='FAIL' else 'PASS' if
            evidence.get('stream_started') is True and content=='PASS' and stream.get('capture_id_coverage')=='PASS'
            else 'NOT VERIFIED')
        visibility=evidence.get('full_visibility_samples',[])
        if len(visibility)<5 or not all(v is True for v in visibility):checks['visible_window_state']='NOT VERIFIED'
        if evidence.get('display_linked') and evidence.get('missed_display_ticks')!=0:checks['visible_window_state']='NOT VERIFIED'
        pacing=evidence.get('steady_reported_presentation',{})
        checks['reported_presentation_cadence']=('NOT VERIFIED' if pacing.get('samples',0)<100 or
            not isinstance(pacing.get('p95_ms'),(int,float)) or not isinstance(pacing.get('max_ms'),(int,float))
            else 'PASS' if pacing.get('p95_ms')<=20 and pacing.get('max_ms')<=25 and pacing.get('above_25ms')==0 else 'FAIL')
    deltas = correlation.get('deltas', {})
    errors = ('debug.nvaccel_iop_async_drop', 'debug.nvaccel_iop_async_refused', 'debug.nvaccel_iop_fail')
    checks['system_display_activity'] = ('FAIL' if any(deltas.get(k, 0) > 0 for k in errors) else
        'PASS' if deltas.get('debug.nvrmfb_flip_n', 0) > 0 and all(k in deltas and deltas[k] >= 0 for k in errors) else 'NOT VERIFIED')
    overall = 'FAIL' if 'FAIL' in checks.values() else 'PASS' if all(v == 'PASS' for v in checks.values()) else 'NOT VERIFIED'
    return {'automated_visual_validation': overall, 'checks': checks,
            'physical_scanout': 'NOT VERIFIED', 'installed_driver_fixed': False}


def repeated_result(runs, requested_runs, source_sha256, negative_control=None, check_names=None):
    """Aggregate scoped verdicts, never infer validation from a process exit code.

    Only verdicts and numeric probe metrics enter the durable artifact. Raw logs,
    process identities, paths and environment variables are deliberately excluded.
    Three independent process runs are required for reproducibility, but this
    slow content probe cannot establish 60 Hz desktop animation performance.
    """
    checks = {}
    names = check_names or ('gpu_frame_contents', 'presentation_timestamps', 'visible_window_state',
             'own_window_capture', 'system_display_activity')
    if check_names is None and any(r.get('metrics',{}).get('continuous') is True for r in runs):
        names=(*names,'reported_presentation_cadence')
    complete = len(runs) == requested_runs and all(r.get('exit_code') == 0 for r in runs)
    for name in names:
        values = [r.get('verdict', {}).get('checks', {}).get(name, 'NOT VERIFIED') for r in runs]
        checks[name] = ('FAIL' if 'FAIL' in values else 'PASS'
                        if complete and values and all(v == 'PASS' for v in values)
                        else 'NOT VERIFIED')
    execution = 'PASS' if complete else 'FAIL'
    overall = ('FAIL' if execution == 'FAIL' or 'FAIL' in checks.values() else
               'PASS' if all(v == 'PASS' for v in checks.values()) else 'NOT VERIFIED')
    return {'schema_version': 1, 'probe': 'ga102_visual_present',
            'probe_source_sha256': source_sha256, 'negative_control': negative_control,
            'requested_runs': requested_runs, 'completed_runs': len(runs),
            'execution': execution, 'checks': checks,
            'automated_visual_validation': overall,
            'reproducibility': 'PASS' if overall == 'PASS' and len(runs) >= 3 else 'NOT VERIFIED',
            'physical_scanout': 'NOT VERIFIED', 'desktop_smoothness': 'NOT VERIFIED',
            'installed_driver_fixed': False, 'runs': runs}
