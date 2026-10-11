import unittest
from tools.ga102_visual_validation import evaluate
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
    def test_drop(self):
        c=self.correlation();c['deltas']['debug.nvaccel_iop_async_drop']=1
        self.assertEqual(evaluate(self.evidence(),c)['automated_visual_validation'],'FAIL')
