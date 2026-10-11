"""Unavailable or inactive display evidence must never look like success."""
import unittest
from tools.ga102_run_metal import display_delta
class DisplayCounterTests(unittest.TestCase):
    def test_missing(self):
        d = display_delta({}, {})
        self.assertEqual(d['visible_presentation'], 'unverified')
        self.assertIsNone(d['mean_flip_call_us'])
    def test_idle(self):
        d = display_delta({'debug.nvrmfb_flip_n': 20}, {'debug.nvrmfb_flip_n': 20})
        self.assertEqual(d['visible_presentation'], 'unverified')
    def test_active(self):
        d = display_delta({'debug.nvrmfb_flip_n': 10, 'debug.nvrmfb_flip_us_sum': 100},
                          {'debug.nvrmfb_flip_n': 12, 'debug.nvrmfb_flip_us_sum': 220})
        self.assertEqual(d['visible_presentation'], 'candidate')
        self.assertEqual(d['mean_flip_call_us'], 60)
    def test_partial_and_reset(self):
        d = display_delta({'debug.nvrmfb_flip_n': 10}, {'debug.nvrmfb_flip_n': 12})
        self.assertIsNone(d['mean_flip_call_us'])
        d = display_delta({'debug.nvrmfb_flip_n': 100}, {'debug.nvrmfb_flip_n': 2})
        self.assertEqual(d['visible_presentation'], 'unverified')
