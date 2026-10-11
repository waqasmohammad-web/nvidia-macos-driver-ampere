import unittest
from ga102_runloop_analysis import analyze

class RunLoopTests(unittest.TestCase):
    def fixture(self):
        return {'runloop_trace_enabled':True,'runloop_event_count':20,'runloop_overflow':False,
            'runloop_long_gaps':[dict(start_ms=1,end_ms=20,from_activity=128,to_activity=1,from_lane=1,to_lane=0)],
            'owned_window_event_spans':[dict(start_ms=1.1,end_ms=19.9,subtype=4)],
            'frame_trace':[dict(frame=16,completed_callback_ms=1.2,main_queue_marker_ms=20.1)]}
    def test_event_and_between_loop_overlap_remain_scoped(self):
        r=analyze(self.fixture());self.assertEqual(r['trace_collection'],'PASS')
        correlation=r['delayed_queue_correlations'][0]
        self.assertEqual(correlation['runloop_phase_overlaps'][0]['phase'],'between_runloop_invocations')
        self.assertEqual(correlation['owned_window_event_overlaps'][0]['subtype'],4)
        self.assertEqual(r['root_cause'],'NOT VERIFIED');self.assertEqual(r['physical_scanout'],'NOT VERIFIED')
    def test_application_event_overlap_does_not_invent_probe_target(self):
        m=self.fixture();m['application_dispatcher_instrumented']=True
        m['owned_application_event_spans']=[dict(start_ms=1.1,end_ms=19.9,subtype=4,target_is_probe=0)]
        r=analyze(m);self.assertEqual(r['trace_collection'],'PASS')
        event=r['delayed_queue_correlations'][0]['owned_application_event_overlaps'][0]
        self.assertEqual(event['target_is_probe'],0)
        m['owned_application_event_overflow']=True
        self.assertEqual(analyze(m)['trace_collection'],'NOT VERIFIED')

    def test_overflow_and_missing_cannot_pass(self):
        m=self.fixture();m['runloop_overflow']=True
        self.assertEqual(analyze(m)['trace_collection'],'NOT VERIFIED')
        self.assertEqual(analyze({})['trace_collection'],'NOT VERIFIED')
    def test_reversed_and_overlapping_clock_gaps_fail(self):
        m=self.fixture();m['runloop_long_gaps'][0]['end_ms']=0
        self.assertEqual(analyze(m)['trace_collection'],'FAIL')
        m=self.fixture();m['runloop_long_gaps']*=2
        self.assertEqual(analyze(m)['trace_collection'],'FAIL')
    def test_invalid_event_clock_fails(self):
        m=self.fixture();m['owned_window_event_spans'][0]['start_ms']=float('nan')
        self.assertEqual(analyze(m)['trace_collection'],'FAIL')

if __name__=='__main__':unittest.main()
