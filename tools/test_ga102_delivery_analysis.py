import unittest
from ga102_delivery_analysis import analyze,distribution

class DeliveryTests(unittest.TestCase):
    def test_missing_capture_is_not_missing_submission_or_panel_proof(self):
        r=analyze({'probe':'visual','frames':2,'frame_trace':[{'frame':0,'draw_start_ms':0,'reported_presented_ms':1},{'frame':1,'draw_start_ms':33,'reported_presented_ms':34}], 'stream_analysis':{'captured_changes':[{'frame':0}]}})
        self.assertEqual(r['reported_presented_without_capture_ids'],[1])
        self.assertEqual(r['not_submitted_ids'],[])
        self.assertEqual(r['submitted_late_after_ids'],[0])
        self.assertEqual(r['capture_loss_is_panel_loss'],'NOT VERIFIED')
    def test_never_submitted_is_separate(self):
        r=analyze({'probe':'ca_visual','frames':2,'samples':[{'frame':0,'transaction_start_ms':0}]})
        self.assertEqual(r['not_submitted_ids'],[1])
        self.assertNotIn('reported_presented_without_capture_ids',r)
    def test_prompt_callback_and_late_actor_are_separate(self):
        row={'frame':16,'draw_start_ms':0,'commit_ms':1,'scheduled_callback_ms':1.1,'commit_return_ms':1.02,
             'completed_callback_ms':1.3,'completed_ms':19.6,'commit_to_completion_callback_ms':0.3,
             'completion_callback_to_actor_ms':18.3,'commit_to_completed_ms':18.6,'gpu_ms':0.06}
        r=analyze({'probe':'visual','frames':120,'frame_trace':[row]})
        self.assertEqual(r['callback_trace_collection'],'PASS')
        self.assertEqual(r['long_client_completion_observations'][0]['classification'],'actor_resumption_delay')
        row['completed_ms']=1.2
        self.assertEqual(analyze({'probe':'visual','frame_trace':[row]})['callback_trace_collection'],'FAIL')

    def test_main_queue_marker_cannot_precede_completion_invocation(self):
        row={'frame':0,'draw_start_ms':0,'commit_ms':1,'scheduled_callback_ms':1.1,'commit_return_ms':1.02,
             'completed_callback_ms':1.3,'completed_ms':1.4,'main_queue_marker_ms':1.2}
        self.assertEqual(analyze({'probe':'visual','frame_trace':[row]})['callback_trace_collection'],'FAIL')

    def test_quantiles_and_unavailable_data(self):
        self.assertEqual(distribution(range(1,101))['p99_ms'],99)
        self.assertEqual(distribution([None,float('nan')])['samples'],0)

if __name__=='__main__':unittest.main()
