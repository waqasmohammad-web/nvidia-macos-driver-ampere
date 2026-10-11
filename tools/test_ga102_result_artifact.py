"""Exercise durable result handling without launching Metal or touching displays."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import ga102_run_metal as runner


class ResultArtifactTests(unittest.TestCase):
    def test_repeated_missing_permission_keeps_scoped_success(self):
        evidence = dict(probe='visual', frames=12, gpu_correct_frames=12,
                        gpu_distinct_patterns=12, positive_timestamps=12,
                        timestamps_increasing=True, distinct_timestamps=12,
                        visible_frames=12, capture_permission=False,
                        private_path='/private/example', process_id=12345)
        def fake_run(command, log, timeout, env=None):
            if timeout == 45:
                log.write('driver private data\nresult: ' + json.dumps(evidence) + '\n')
            return 0
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / 'results.json'
            scratch = Path(directory) / 'scratch'; scratch.mkdir()
            with patch('sys.argv', ['probe', 'ga102_visual_present', '--repeat', '3', '--result-json', str(result)]), \
                 patch.object(runner.tempfile, 'mkdtemp', return_value=str(scratch)), \
                 patch.object(runner, 'run_owned', side_effect=fake_run), \
                 patch.object(runner, 'display_counters', return_value={}), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.main(), 0)
            raw = result.read_text(); report = json.loads(raw)
            self.assertEqual(report['checks']['gpu_frame_contents'], 'PASS')
            self.assertEqual(report['automated_visual_validation'], 'NOT VERIFIED')
            self.assertEqual(report['completed_runs'], 3)
            for private in ('private_path', 'process_id', 'private/example', 'driver private data'):
                self.assertNotIn(private, raw)

    def test_deadline_saves_incomplete_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / 'results.json'
            scratch = Path(directory) / 'scratch'; scratch.mkdir()
            with patch('sys.argv', ['probe', 'ga102_visual_present', '--result-json', str(result)]), \
                 patch.object(runner.tempfile, 'mkdtemp', return_value=str(scratch)), \
                 patch.object(runner, 'run_owned', side_effect=subprocess.TimeoutExpired('compiler', 90)), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.main(), 124)
            report = json.loads(result.read_text())
            self.assertEqual(report['execution'], 'FAIL')
            self.assertEqual(report['completed_runs'], 0)
            self.assertEqual(report['physical_scanout'], 'NOT VERIFIED')


if __name__ == '__main__':
    unittest.main()
