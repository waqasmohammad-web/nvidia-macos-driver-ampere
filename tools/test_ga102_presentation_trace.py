import unittest
from tools.ga102_presentation_trace import analyze


class TraceTests(unittest.TestCase):
    def evidence(self):
        rows = []
        for i in range(4):
            t = i * 16.667
            rows.append(dict(frame=i, draw_start_ms=t, acquisition_ms=.05, encode_ms=.02,
                commit_start_ms=t+.1, commit_return_ms=t+.12, scheduled_callback_ms=t+.14,
                completed_callback_ms=t+.3, gpu_ms=.005, presented_time_available=1,
                presented_time_ms=t+20+(16.667 if i>=2 else 0),
                system_flips_at_presented_callback=100+i+(1 if i>=2 else 0)))
        return {'attempted': 4, 'frame_trace': rows}

    def test_prompt_completion_late_presentation(self):
        r = analyze(self.evidence())
        self.assertEqual(r['trace_collection'], 'PASS')
        self.assertEqual(len(r['late_intervals']), 1)
        late = r['late_intervals'][0]
        self.assertEqual(late['classification'], 'client_completed_promptly')
        self.assertEqual(late['system_flip_delta_between_callbacks'], 2)
        self.assertTrue(late['startup'])
        self.assertEqual(r['physical_scanout'], 'NOT VERIFIED')

    def test_delayed_client_and_inconsistent_clock(self):
        e = self.evidence(); e['frame_trace'][2]['completed_callback_ms'] += 20
        self.assertEqual(analyze(e)['late_intervals'][0]['classification'], 'client_delay_or_callback_timing_candidate')
        e = self.evidence(); e['frame_trace'][2]['completed_callback_ms'] = -1
        self.assertEqual(analyze(e)['trace_collection'], 'FAIL')

    def test_missing_evidence_and_skipped_timestamp(self):
        self.assertEqual(analyze({})['trace_collection'], 'NOT VERIFIED')
        e = self.evidence(); e['frame_trace'].pop()
        self.assertEqual(analyze(e)['trace_collection'], 'NOT VERIFIED')
        e = self.evidence(); e['frame_trace'][0]['presented_time_available'] = 0
        self.assertEqual(analyze(e)['trace_collection'], 'PASS')

    def test_invalid_and_reversed_presentation_clock(self):
        for value in (float('nan'), float('inf'), None, -1):
            e = self.evidence(); e['frame_trace'][2]['presented_time_ms'] = value
            self.assertEqual(analyze(e)['trace_collection'], 'FAIL')
