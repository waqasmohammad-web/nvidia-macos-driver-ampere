import unittest
from tools.ga102_core_validation import evaluate
from tools.ga102_suite import plan, summarize, failure_requires_stop


class CoreTests(unittest.TestCase):
    def test_compute_and_render(self):
        for probe, good in [('ga102_metal_smoketest', {'values': [2, 4, 6, 8], 'checked_elements': 4}),
                            ('ga102_metal_render_smoketest', {'rgba': [64, 127, 191, 255], 'width': 16, 'height': 16, 'checked_pixels': 1})]:
            self.assertEqual(evaluate(probe, [good], 0)['automated_core_validation'], 'PASS')
            self.assertEqual(evaluate(probe, [], 0)['automated_core_validation'], 'NOT VERIFIED')
            self.assertEqual(evaluate(probe, [good], 1)['automated_core_validation'], 'FAIL')
        self.assertEqual(evaluate('ga102_metal_smoketest', [{'values': [1, 2, 3, 4]}], 0)['automated_core_validation'], 'FAIL')

    def test_composite_requires_every_case(self):
        records = [dict(mode=m, layers=n, pixels='PASS', checked_pixels=16, width=3440, height=1440)
                   for m in ('private', 'iosurface') for n in (16, 32)]
        self.assertEqual(evaluate('ga102_metal_composite', records, 0)['automated_core_validation'], 'PASS')
        self.assertEqual(evaluate('ga102_metal_composite', records[:-1], 0)['automated_core_validation'], 'FAIL')

    def test_event_and_crossprocess_coverage(self):
        cases = [('ga102_metal_events', dict(iterations=16, consumer_first_iterations=8, checked_bytes=65536, output='PASS')),
                 ('ga102_metal_crossprocess', dict(frames=8, processes=2, cpu_producer_frames=4,
                     gpu_producer_frames=4, checked_bytes=262144, output='PASS'))]
        for probe, record in cases:
            self.assertEqual(evaluate(probe, [record], 0)['automated_core_validation'], 'PASS')
            record['checked_bytes'] -= 1
            self.assertEqual(evaluate(probe, [record], 0)['automated_core_validation'], 'FAIL')

    def test_suite_scope_plan_and_no_missing_pass(self):
        self.assertEqual(len(plan('correctness', 1)), 5)
        self.assertEqual(len(plan('all', 3)), 21)
        self.assertTrue(all(j[2] == 1 for j in plan('negative-controls', 3)))
        self.assertEqual(summarize([])['acceptance'], 'NOT VERIFIED')
        r = summarize([{'acceptance': 'PASS'}])
        self.assertEqual(r['acceptance'], 'PASS')
        self.assertEqual(r['desktop_smoothness'], 'NOT VERIFIED')
        self.assertFalse(r['installed_driver_fixed'])
        self.assertEqual(summarize([{'acceptance': 'BLOCKED'}])['acceptance'], 'BLOCKED')

    def test_only_healthy_cadence_failure_can_continue(self):
        checks=dict(gpu_frame_contents='PASS',presentation_timestamps='PASS',visible_window_state='PASS',
                    system_display_activity='PASS',own_window_capture='NOT VERIFIED',reported_presentation_cadence='FAIL')
        r={'runs':[{'exit_code':0,'verdict':{'checks':checks}}]}
        self.assertFalse(failure_requires_stop(r))
        checks['known_adjacent_reported_cadence']='FAIL'
        self.assertFalse(failure_requires_stop(r))
        for key in ('gpu_frame_contents','system_display_activity','visible_window_state'):
            checks[key]='FAIL';self.assertTrue(failure_requires_stop(r));checks[key]='PASS'
        r['runs'][0]['exit_code']=124;self.assertTrue(failure_requires_stop(r))
        self.assertTrue(failure_requires_stop({}))
