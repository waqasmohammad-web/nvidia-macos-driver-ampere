import unittest
from tools.ga102_ca_validation import evaluate, repeated_ca_result


class CAValidationTests(unittest.TestCase):
    def fixture(self):
        return dict(frames=12, transactions=12, preflight_ready=True, visible_frames=12,
                    capture_permission=True, capture_received_frames=12,
                    capture_correct_frames=12, capture_distinct_patterns=12)

    def correlation(self):
        return {'deltas': {'debug.nvrmfb_flip_n': 120, 'debug.nvaccel_iop_async_drop': 0,
                          'debug.nvaccel_iop_async_refused': 0, 'debug.nvaccel_iop_fail': 0}}

    def test_pass_is_scoped(self):
        verdict = evaluate(self.fixture(), self.correlation())
        self.assertEqual(verdict['automated_ca_validation'], 'PASS')
        self.assertEqual(verdict['gpu_completion'], 'NOT VERIFIED')
        r = repeated_ca_result([dict(exit_code=0, verdict=verdict)]*3, 3, 'synthetic')
        self.assertEqual(r['reproducibility'], 'PASS')
        self.assertEqual(r['physical_scanout'], 'NOT VERIFIED')
        self.assertEqual(r['animation_frame_pacing'], 'NOT VERIFIED')

    def test_static_hidden_denied_and_incomplete(self):
        for key, value, expected in [('capture_correct_frames', 1, 'FAIL'),
                                     ('capture_distinct_patterns', 1, 'FAIL'),
                                     ('visible_frames', 0, 'NOT VERIFIED'),
                                     ('capture_permission', False, 'NOT VERIFIED'),
                                     ('preflight_ready', False, 'NOT VERIFIED'),
                                     ('transactions', 0, 'NOT VERIFIED')]:
            e = self.fixture(); e[key] = value
            self.assertEqual(evaluate(e, self.correlation())['automated_ca_validation'], expected)

    def test_stream_missing_ids_cannot_be_full_pass(self):
        e=dict(continuous=True,frames=120,transactions=120,preflight_ready=True,
               visible_frames=120,full_visibility_samples=[True]*5,stream_started=True,
               stream_analysis={'captured_reference_contents':'PASS','capture_id_coverage':'NOT VERIFIED'})
        v=evaluate(e,self.correlation())
        self.assertEqual(v['automated_ca_validation'],'NOT VERIFIED')
        e['stream_analysis']['capture_id_coverage']='PASS'
        v=evaluate(e,self.correlation())
        self.assertEqual(v['automated_ca_validation'],'PASS')
        r=repeated_ca_result([dict(exit_code=0,verdict=v)]*3,3,'synthetic',continuous=True)
        self.assertEqual(r['automated_ca_validation'],'PASS')
        self.assertEqual(r['animation_frame_pacing'],'NOT VERIFIED')
