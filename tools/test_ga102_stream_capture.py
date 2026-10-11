import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock
from tools.ga102_stream_capture import analyze_stream, StreamBroker
from tools.ga102_capture_bridge import expected_samples


class StreamTests(unittest.TestCase):
    def fixture(self):
        return dict(stopped=True, failed=False, overflow=False, statuses={'0':4},
                    records=[dict(samples=expected_samples(i),pts_seconds=100+i/60) for i in range(4)])

    def test_expected_sequence_and_scope(self):
        r=analyze_stream(self.fixture(),4)
        self.assertEqual(r['captured_reference_contents'],'PASS')
        self.assertEqual(r['capture_id_coverage'],'PASS')
        self.assertEqual(r['physical_scanout'],'NOT VERIFIED')

    def test_loss_static_wrong_pixels_reversal_and_stop(self):
        e=self.fixture();e['records'].pop(1)
        r=analyze_stream(e,4)
        self.assertEqual(r['captured_reference_contents'],'PASS')
        self.assertEqual(r['capture_id_coverage'],'NOT VERIFIED')
        self.assertEqual(r['missing_capture_ids'],[1])
        e=self.fixture()
        for row in e['records']:row['samples']=expected_samples(0)
        self.assertEqual(analyze_stream(e,4)['captured_reference_contents'],'NOT VERIFIED')

    def test_other_child_cannot_start_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            broker=object.__new__(StreamBroker);broker.directory=Path(directory);broker.library=Mock()
            (broker.directory/'request.json').write_text(json.dumps({'pid':2,'operation':'stream-start','window_id':100}))
            with self.assertRaises(ValueError):broker.poll(Mock(pid=1))
            broker.library.ga102_stream_start.assert_not_called()

    def test_metadata_never_verifies_pixels(self):
        e=self.fixture();e['pixel_sampling_enabled']=False
        for row in e['records']:row.pop('samples')
        r=analyze_stream(e,4)
        self.assertEqual(r['metadata_capture'],'PASS')
        self.assertEqual(r['captured_reference_contents'],'NOT VERIFIED')
        self.assertEqual(r['capture_id_coverage'],'NOT VERIFIED')
        e=self.fixture();e['records'][1]['samples'][3]=128
        self.assertEqual(analyze_stream(e,4)['captured_reference_contents'],'FAIL')
        e=self.fixture();e['records'].reverse()
        self.assertEqual(analyze_stream(e,4)['captured_reference_contents'],'FAIL')
        e=self.fixture();e['stopped']=False
        self.assertEqual(analyze_stream(e,4)['captured_reference_contents'],'NOT VERIFIED')
