import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from tools.ga102_capture_bridge import CaptureBroker, correct_samples, expected_samples


class CaptureTests(unittest.TestCase):
    def test_independent_pattern_and_static_negative(self):
        patterns = [expected_samples(i) for i in range(12)]
        self.assertEqual(len({tuple(p) for p in patterns}), 12)
        for i, pattern in enumerate(patterns):
            self.assertTrue(correct_samples(i, pattern))
            self.assertEqual(correct_samples(i, patterns[0]), i == 0)
        self.assertFalse(correct_samples(0, patterns[0][:-1]))
        self.assertFalse(correct_samples(0, [127] * 72))

    def test_wrong_process_never_calls_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            broker = CaptureBroker.__new__(CaptureBroker)
            broker.directory = Path(directory); broker.library = Mock(); broker.allowed = True; broker.signatures = set()
            (broker.directory / 'request.json').write_text(json.dumps(dict(pid=456, window_id=789, frame=0)))
            with self.assertRaises(ValueError): broker.poll(SimpleNamespace(pid=123))
            broker.library.ga102_capture_window.assert_not_called()

    def test_hidden_invalid_window_never_captures_other_windows(self):
        with tempfile.TemporaryDirectory() as directory:
            broker = CaptureBroker.__new__(CaptureBroker)
            broker.directory = Path(directory); broker.library = Mock(); broker.allowed = True; broker.signatures = set()
            (broker.directory / 'request.json').write_text(json.dumps(dict(pid=123, window_id=-1, frame=0)))
            broker.poll(SimpleNamespace(pid=123))
            broker.library.ga102_capture_window.assert_not_called()
            result = json.loads((broker.directory / 'response-0.json').read_text())
            self.assertFalse(result['received']); self.assertEqual(result['code'], -4)
            self.assertFalse(broker.allowed)


if __name__ == '__main__': unittest.main()
