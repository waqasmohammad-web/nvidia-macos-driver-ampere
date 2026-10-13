"""Synthetic verdict controls only; these are not GPU qualification results."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).parent))
from ga102_sustained_verdict import qualify


class SustainedVerdictTests(unittest.TestCase):
    def evidence(self):
        rows=[]
        for i in range(3600):
            t=i*1000/60
            rows.append(dict(frame=i, draw_start_ms=t, acquisition_ms=.1, encode_ms=.1,
                commit_start_ms=t, commit_return_ms=t+.1, scheduled_callback_ms=t+.2,
                completed_callback_ms=t+.5, presented_time_available=int(i>1), presented_time_ms=t+20))
        return dict(attempted=3600,completed=3600,command_errors=0,outstanding=0,timer_skips=0,
            presented_frame_ids=list(range(2,3600)),presented_times=[(i*1000/60+20)/1000 for i in range(2,3600)],
            frame_trace=rows,preflight_ready=True,visibility_samples=[dict.fromkeys([
                'window_visible','window_on_active_space','window_unoccluded','window_in_onscreen_list',
                'session_on_console','display_active'],True)],render_width=1920,render_height=1080,
            composite_layers=8,drawable_count=3,display_width=3440,display_height=1440,display_refresh_hz=60)

    def test_control_and_missing_timestamps(self):
        d=self.evidence(); self.assertEqual(qualify(d)['verdict'],'PASS')
        self.assertEqual(qualify(d)['presentation']['missing_frame_ids'],[0,1])
        d['presented_frame_ids'].pop();d['presented_times'].pop()
        self.assertEqual(qualify(d)['verdict'],'NOT VERIFIED')

    def test_late_frames_preserved(self):
        d=self.evidence()
        for i in range(100,len(d['presented_times'])):d['presented_times'][i]+=.02
        r=qualify(d);self.assertEqual(r['verdict'],'FAIL');self.assertEqual(r['presentation']['late_intervals'],1)
        self.assertEqual(r['command_completion'],'PASS')

    def test_eligibility_and_commands(self):
        for k,v in [('preflight_ready',False),('composite_layers',4),('display_refresh_hz',75)]:
            d=self.evidence();d[k]=v;self.assertEqual(qualify(d)['verdict'],'NOT VERIFIED')
        d=self.evidence();d['completed']=3599;self.assertEqual(qualify(d)['verdict'],'FAIL')

    def test_invalid_clocks_and_empty_result(self):
        for v in [0,float('nan'),float('inf')]:
            d=self.evidence();d['presented_times'][20]=v;self.assertEqual(qualify(d)['verdict'],'FAIL')
        self.assertEqual(qualify({})['verdict'],'FAIL')
