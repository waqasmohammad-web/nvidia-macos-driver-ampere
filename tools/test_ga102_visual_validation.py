import unittest
from tools.ga102_visual_validation import evaluate, repeated_result
class VisualValidationTests(unittest.TestCase):
    def evidence(self):
        return dict(frames=12,gpu_correct_frames=12,gpu_distinct_patterns=12,positive_timestamps=10,timestamps_increasing=True,distinct_timestamps=10,
                    visible_frames=12,capture_permission=True,capture_attempted=12,capture_received_frames=12,capture_correct_frames=12,capture_distinct_patterns=12)
    def correlation(self):
        return {'deltas':dict(zip(('debug.nvrmfb_flip_n','debug.nvaccel_iop_async_drop','debug.nvaccel_iop_async_refused','debug.nvaccel_iop_fail'),(120,0,0,0)))}
    def test_positive_still_not_physical(self):
        r=evaluate(self.evidence(),self.correlation())
        self.assertEqual(r['automated_visual_validation'],'PASS');self.assertEqual(r['physical_scanout'],'NOT VERIFIED')
        self.assertFalse(r['installed_driver_fixed'])
    def test_static_and_wrong_capture(self):
        e=self.evidence();e.update(gpu_distinct_patterns=1,gpu_correct_frames=1)
        self.assertEqual(evaluate(e,self.correlation())['automated_visual_validation'],'FAIL')
        e=self.evidence();e['capture_correct_frames']=0
        self.assertEqual(evaluate(e,self.correlation())['automated_visual_validation'],'FAIL')
    def test_missing_timestamps_hidden_permission_and_activity(self):
        for key,value in [('positive_timestamps',0),('visible_frames',0),('capture_permission',False),('capture_received_frames',0),('timestamps_increasing',False),('distinct_timestamps',1)]:
            e=self.evidence();e[key]=value
            self.assertEqual(evaluate(e,self.correlation())['automated_visual_validation'],'NOT VERIFIED')
        self.assertEqual(evaluate(self.evidence(),{})['automated_visual_validation'],'NOT VERIFIED')
    def test_no_gpu_evidence(self):
        self.assertEqual(evaluate({}, {})["automated_visual_validation"], "NOT VERIFIED")
    def test_stream_coverage_and_cadence_are_separate(self):
        e=self.evidence();e.update(frames=120,gpu_correct_frames=120,gpu_distinct_patterns=120,visible_frames=120,positive_timestamps=118,distinct_timestamps=118,
            continuous=True,stream_started=True,full_visibility_samples=[True]*5,
            steady_reported_presentation=dict(samples=109,p95_ms=17,max_ms=18,above_25ms=0),
            stream_analysis=dict(captured_reference_contents='PASS',capture_id_coverage='NOT VERIFIED'))
        self.assertEqual(evaluate(e,self.correlation())['automated_visual_validation'],'NOT VERIFIED')
        e['stream_analysis']['capture_id_coverage']='PASS'
        self.assertEqual(evaluate(e,self.correlation())['automated_visual_validation'],'PASS')
        e['steady_reported_presentation']['max_ms']=34
        v=evaluate(e,self.correlation())
        self.assertEqual(v['checks']['reported_presentation_cadence'],'FAIL')
        r=repeated_result([dict(exit_code=0,metrics={'continuous':True},verdict=v)],1,'synthetic')
        self.assertEqual(r['automated_visual_validation'],'FAIL')
    def test_shortened_continuous_scope_cannot_pass(self):
        e=self.evidence();e.update(continuous=True,stream_started=True,full_visibility_samples=[True]*5,
            steady_reported_presentation=dict(samples=109,p95_ms=17,max_ms=18,above_25ms=0),
            stream_analysis=dict(captured_reference_contents='PASS',capture_id_coverage='PASS'))
        self.assertEqual(evaluate(e,self.correlation())['checks']['gpu_frame_contents'],'FAIL')

    def test_trace_overflow_prevents_full_and_repeated_pass(self):
        e=self.evidence();e.update(runloop_trace_enabled=True,runloop_event_count=20,runloop_long_gaps=[],runloop_overflow=True)
        v=evaluate(e,self.correlation())
        self.assertEqual(v['automated_visual_validation'],'NOT VERIFIED')
        r=repeated_result([dict(exit_code=0,metrics=e,verdict=v)]*3,3,'synthetic')
        self.assertEqual(r['checks']['runloop_trace_collection'],'NOT VERIFIED')
        self.assertEqual(r['automated_visual_validation'],'NOT VERIFIED')

    def test_incomplete_coverage_does_not_hide_known_adjacent_stall(self):
        e=self.evidence();e.update(continuous=True,frame_trace=[dict(frame=10,draw_start_ms=0,reported_presented_ms=1),dict(frame=11,draw_start_ms=16,reported_presented_ms=34)])
        r=evaluate(e,self.correlation())
        self.assertEqual(r['checks']['known_adjacent_reported_cadence'],'FAIL')
        e['frame_trace'][1]['frame']=12
        self.assertEqual(evaluate(e,self.correlation())['checks']['known_adjacent_reported_cadence'],'NOT VERIFIED')

    def test_drop(self):
        c=self.correlation();c['deltas']['debug.nvaccel_iop_async_drop']=1
        self.assertEqual(evaluate(self.evidence(),c)['automated_visual_validation'],'FAIL')
    def test_counter_reset_is_not_healthy_activity(self):
        c = self.correlation(); c['deltas']['debug.nvaccel_iop_fail'] = -2
        self.assertEqual(evaluate(self.evidence(), c)['checks']['system_display_activity'], 'NOT VERIFIED')

    def run_result(self, evidence=None, exit_code=0):
        return {'exit_code': exit_code, 'verdict': evaluate(evidence or self.evidence(), self.correlation())}

    def test_repeat_gate_and_claim_scope(self):
        one = repeated_result([self.run_result()], 1, 'hash')
        self.assertEqual(one['automated_visual_validation'], 'PASS')
        self.assertEqual(one['reproducibility'], 'NOT VERIFIED')
        three = repeated_result([self.run_result()] * 3, 3, 'hash')
        self.assertEqual(three['reproducibility'], 'PASS')
        self.assertEqual(three['physical_scanout'], 'NOT VERIFIED')
        self.assertEqual(three['desktop_smoothness'], 'NOT VERIFIED')
        self.assertFalse(three['installed_driver_fixed'])

    def test_repeated_controls_and_missing_evidence(self):
        for key, value, expected in [('gpu_distinct_patterns', 1, 'FAIL'),
                                     ('positive_timestamps', 0, 'NOT VERIFIED'),
                                     ('visible_frames', 0, 'NOT VERIFIED'),
                                     ('capture_permission', False, 'NOT VERIFIED')]:
            e = self.evidence(); e[key] = value
            r = repeated_result([self.run_result(e)] * 3, 3, 'hash')
            self.assertEqual(r['automated_visual_validation'], expected)
            self.assertEqual(r['reproducibility'], 'NOT VERIFIED')
        for runs in ([], [self.run_result()], [{'exit_code': 0}] * 3):
            r = repeated_result(runs, 3, 'hash')
            self.assertNotEqual(r['automated_visual_validation'], 'PASS')
        r = repeated_result([self.run_result(exit_code=124)], 1, 'hash')
        self.assertEqual(r['execution'], 'FAIL')
