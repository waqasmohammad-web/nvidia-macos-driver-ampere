"""Acceptance controls for source-prepared surface probe records, never GPU evidence."""
import contextlib
import io
from unittest.mock import patch
from tools import ga102_run_metal as runner
import math
import unittest
from tools.ga102_allocation_probe import SURFACE_MODES, validate_surfaces


class SurfaceAcceptanceTests(unittest.TestCase):
    def control(self, backing='family'):
        trace=dict(requests=1,failures=0,request_ns=1,lock_wait_ns=0,growths=1,growth_ns=1,fragmented_growths=0)
        return [dict(mode=mode,frame=frame,backing=0 if mode=='private' else 2 if backing=='family' else 1,
                     checked_pixels=640*360,max_error=0,frame_start_ns=1,encode_end_ns=2,commit_ns=3,scheduled_ns=4,completed_ns=5,
                     gpu_start_s=1.0,gpu_end_s=1.1,pool_before=trace.copy(),pool_after=trace.copy())
                for mode in SURFACE_MODES for frame in range(20)]

    def test_presentation_workload_cannot_bypass_offscreen_binding_gate(self):
        for args in [['ga102_metal_present','--plugin','/missing','--render-size','1920x1080'],
                     ['ga102_metal_smoketest','--composite-layers','4'],
                     ['ga102_metal_present','--composite-layers','99']]:
            with patch('sys.argv',['runner']+args), patch.object(runner,'run_owned') as child, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):runner.main()
                child.assert_not_called()

    def test_accepts_coverage_contract(self):
        for backing in ('family','private'):validate_surfaces(self.control(backing),backing)

    def test_rejects_partial_or_duplicate_coverage(self):
        rows=self.control()
        for malformed in (rows[:-1],rows[1:]+[rows[-1]]):
            with self.assertRaises(ValueError):validate_surfaces(malformed,'family')

    def test_rejects_fallback_as_family_qualification(self):
        rows=self.control();rows[0]['backing']=1
        with self.assertRaises(ValueError):validate_surfaces(rows,'family')

    def test_requires_ordered_callbacks_and_real_timestamps(self):
        for field,value in [('scheduled_ns',2),('completed_ns',3),('gpu_start_s',0),('gpu_end_s',math.nan)]:
            rows=self.control();rows[0][field]=value
            with self.assertRaises(ValueError):validate_surfaces(rows,'family')

    def test_rejects_incorrect_pixels(self):
        rows=self.control();rows[0]['max_error']=2
        with self.assertRaises(ValueError):validate_surfaces(rows,'family')

    def test_requires_monotonic_complete_trace(self):
        rows=self.control();rows[0]['pool_after']['requests']=0
        with self.assertRaises(ValueError):validate_surfaces(rows,'family')
        rows=self.control();del rows[0]['pool_before']['growths']
        with self.assertRaises(ValueError):validate_surfaces(rows,'family')


if __name__=='__main__':unittest.main()
