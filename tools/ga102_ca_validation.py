"""Scoped Core Animation reference-content validation, not animation/scanout."""
try:
    from .ga102_visual_validation import evaluate as evaluate_visual, repeated_result
except ImportError:
    from ga102_visual_validation import evaluate as evaluate_visual, repeated_result

CHECKS = ('reference_pattern_submission', 'visible_window_state',
          'own_window_capture', 'system_display_activity')


def evaluate(evidence, correlation):
    base = evaluate_visual(evidence, correlation)['checks']
    checks = {key: base[key] for key in CHECKS if key in base}
    checks['reference_pattern_submission'] = ('PASS' if evidence.get('frames') == 12 and
        evidence.get('transactions') == 12 else 'NOT VERIFIED')
    if evidence.get('preflight_ready') is not True:
        checks['visible_window_state'] = 'NOT VERIFIED'
    if checks['own_window_capture'] == 'PASS' and evidence.get('capture_distinct_patterns') != 12:
        checks['own_window_capture'] = 'FAIL'
    overall = ('FAIL' if 'FAIL' in checks.values() else
               'PASS' if all(v == 'PASS' for v in checks.values()) else 'NOT VERIFIED')
    return {'automated_ca_validation': overall, 'checks': checks,
            'physical_scanout': 'NOT VERIFIED', 'animation_frame_pacing': 'NOT VERIFIED',
            'gpu_completion': 'NOT VERIFIED', 'installed_driver_fixed': False}


def repeated_ca_result(runs, requested, source_hash, negative_control=None):
    result = repeated_result(runs, requested, source_hash, negative_control, CHECKS)
    result['probe'] = 'ga102_ca_visual'
    result['automated_ca_validation'] = result.pop('automated_visual_validation')
    result['scope'] = '12 held Core Animation reference patterns; extra animated layers not pixel-validated'
    result['animation_frame_pacing'] = 'NOT VERIFIED'
    result['gpu_completion'] = 'NOT VERIFIED'
    return result
