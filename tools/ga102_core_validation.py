"""Scoped evidence checks for the unattended Metal/coherency regression set."""
try:
    from .ga102_visual_validation import repeated_result
except ImportError:
    from ga102_visual_validation import repeated_result

CORE_PROBES = ('ga102_metal_smoketest', 'ga102_metal_render_smoketest',
               'ga102_metal_composite', 'ga102_metal_events', 'ga102_metal_crossprocess')
FIELDS = ('probe', 'values', 'checked_elements', 'rgba', 'width', 'height', 'checked_pixels',
          'mode', 'layers', 'gpu', 'encode_to_completion', 'pixels', 'iterations',
          'consumer_first_iterations', 'checked_bytes', 'commit_to_consumer_completion_ms_in_order',
          'output', 'frames', 'processes', 'cpu_producer_frames', 'gpu_producer_frames',
          'roundtrip_ms_in_order')


def evaluate(probe, records, exit_code):
    status = 'NOT VERIFIED'
    if exit_code != 0:
        status = 'FAIL'
    elif records:
        if probe == 'ga102_metal_smoketest':
            status = 'PASS' if len(records) == 1 and records[0].get('values') == [2, 4, 6, 8] and records[0].get('checked_elements') == 4 else 'FAIL'
        elif probe == 'ga102_metal_render_smoketest':
            r = records[0]; rgba = r.get('rgba', [])
            status = 'PASS' if (len(records) == 1 and r.get('width') == r.get('height') == 16 and
                                r.get('checked_pixels') == 1 and len(rgba) == 4 and
                                all(abs(a - b) <= 2 for a, b in zip(rgba, [64, 128, 191, 255]))) else 'FAIL'
        elif probe == 'ga102_metal_composite':
            cases = {(r.get('mode'), r.get('layers')) for r in records}
            status = 'PASS' if (len(records) == 4 and cases == {(m, n) for m in ('private', 'iosurface') for n in (16, 32)} and
                                all(r.get('pixels') == 'PASS' and r.get('checked_pixels') == 16 and
                                    r.get('width') == 3440 and r.get('height') == 1440 for r in records)) else 'FAIL'
        elif probe == 'ga102_metal_events':
            r = records[0]
            status = 'PASS' if len(records) == 1 and all(r.get(k) == v for k, v in
                dict(iterations=16, consumer_first_iterations=8, checked_bytes=65536, output='PASS').items()) else 'FAIL'
        elif probe == 'ga102_metal_crossprocess':
            r = records[0]
            status = 'PASS' if len(records) == 1 and all(r.get(k) == v for k, v in
                dict(frames=8, processes=2, cpu_producer_frames=4, gpu_producer_frames=4,
                     checked_bytes=262144, output='PASS').items()) else 'FAIL'
    return {'automated_core_validation': status, 'checks': {'scoped_gpu_correctness': status},
            'physical_scanout': 'NOT VERIFIED', 'desktop_smoothness': 'NOT VERIFIED',
            'installed_driver_fixed': False}


def repeated_core_result(probe, runs, requested_runs, source_sha256):
    result = repeated_result(runs, requested_runs, source_sha256,
                             check_names=('scoped_gpu_correctness',))
    result['probe'] = probe
    result['automated_core_validation'] = result.pop('automated_visual_validation')
    return result
