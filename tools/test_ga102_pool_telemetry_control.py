"""Timing-off control restores production allocation; it is never GPU evidence."""
from pathlib import Path
import unittest
from build import ga102_pool_instrumentation as trace
from build import ga102_pool_telemetry_control as control

ROOT=Path(__file__).resolve().parents[1]


class PoolTimingControlTests(unittest.TestCase):
    def test_actual_production_body_restored(self):
        production=(ROOT/'plugin/nvmtl_vk.c').read_text()
        copied=trace.instrument(production)
        restored=control.disable(copied,production)
        self.assertEqual(restored,production)
        unavailable=control.disable_export('before\n'+trace.EXPORT+'after\n',trace.EXPORT)
        self.assertIn('available',unavailable)
        self.assertIn('false',unavailable)
        self.assertNotIn('atomic_load',unavailable)
        self.assertNotIn('request_ns',unavailable)

    def test_moved_duplicate_or_repeated_control_rejected(self):
        production=(ROOT/'plugin/nvmtl_vk.c').read_text();copied=trace.instrument(production)
        for source in (production,copied+control.START,copied.replace(control.END,'moved')):
            with self.assertRaises(ValueError):control.disable(source,production)
        for unit in ('',trace.EXPORT+trace.EXPORT,control.UNAVAILABLE):
            with self.assertRaises(ValueError):control.disable_export(unit,trace.EXPORT)
