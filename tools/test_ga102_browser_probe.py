"""CPU verdict controls; no browser or GPU qualification is implied."""
import math
import unittest
from tools.ga102_browser_probe import summarize


class VerdictControls(unittest.TestCase):
    def css(self):
        return {'mode':'css', 'interval_ms':[16.7]*120, 'duration_ms':2000,
                'observed_duration_ms':2004, 'hidden_samples':0, 'unfocused_samples':0}

    def test_css_never_claims_pixel_correctness(self):
        report = summarize(self.css())
        self.assertEqual(report['correctness'], 'NOT VERIFIED')
        self.assertEqual(report['timing_eligibility'], 'PASS')

    def test_focus_or_visibility_loss_disqualifies_timing(self):
        for key in ('hidden_samples', 'unfocused_samples'):
            row = self.css(); row[key] = 1
            self.assertEqual(summarize(row)['timing_eligibility'], 'NOT VERIFIED')

    def test_invalid_clocks_refused(self):
        for value in (0, -1, math.nan, math.inf):
            row = self.css(); row['interval_ms'][0] = value
            with self.assertRaises(ValueError): summarize(row)

    def test_early_failure_never_becomes_zero_latency_pass(self):
        report = summarize({'mode':'webgl', 'failure':'context unavailable', 'interval_ms':[]})
        self.assertEqual(report['correctness'], 'FAIL')
        self.assertEqual(report['timing_eligibility'], 'NOT VERIFIED')
        self.assertEqual(report['interval_ms'], {})

    def test_software_renderer_cannot_qualify_hardware_pixels(self):
        row = self.css(); row.update(mode='webgl', correct=True, checked_bytes=524288,
                                   gl_errors=[], lost_context=False, unmasked_renderer='ANGLE SwiftShader')
        self.assertEqual(summarize(row)['correctness'], 'FAIL')


if __name__ == '__main__': unittest.main()
