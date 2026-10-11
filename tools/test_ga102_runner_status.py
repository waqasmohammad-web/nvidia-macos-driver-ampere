import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import ga102_run_metal as runner


class RunnerStatusTests(unittest.TestCase):
    def test_validation_failure_does_not_rewrite_child_exit(self):
        evidence=dict(probe='visual',frames=12,gpu_correct_frames=1,gpu_distinct_patterns=1,
                      positive_timestamps=12,distinct_timestamps=12,timestamps_increasing=True,
                      visible_frames=12,capture_permission=True,capture_received_frames=12,
                      capture_correct_frames=12,capture_distinct_patterns=12)
        def fake_child(command,log,*args):
            if command[0]!='xcrun':log.write('result: '+json.dumps(evidence)+'\n')
            return 0
        counters={'debug.nvrmfb_flip_n':0,'debug.nvaccel_iop_async_drop':0,
                  'debug.nvaccel_iop_async_refused':0,'debug.nvaccel_iop_fail':0}
        with tempfile.TemporaryDirectory() as directory:
            scratch=Path(directory)/'scratch';scratch.mkdir()
            result=Path(directory)/'result.json'
            with patch.object(runner.tempfile,'mkdtemp',return_value=str(scratch)), \
                 patch.object(runner,'run_owned',side_effect=fake_child), \
                 patch.object(runner,'display_counters',side_effect=[counters,{**counters,'debug.nvrmfb_flip_n':100}]), \
                 patch('sys.argv',['runner','ga102_visual_present','--result-json',str(result)]), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.main(),1)
            data=json.loads(result.read_text())
            self.assertEqual(data['runs'][0]['exit_code'],0)
            self.assertEqual(data['runs'][0]['validation_exit_code'],1)
            self.assertEqual(data['execution'],'PASS')
            self.assertEqual(data['automated_visual_validation'],'FAIL')
