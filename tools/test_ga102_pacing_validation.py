import copy
import unittest
from tools.ga102_pacing_validation import STATE_KEYS, evaluate, repeated_pacing_result


class PacingTests(unittest.TestCase):
    def evidence(self):
        state = {key: True for key in STATE_KEYS}; state['display_asleep'] = False
        return dict(attempted=120, completed=120, command_errors=0, outstanding=0,
                    preflight_ready=True,
                    timer_skips=0, visibility_samples=[state] * 4,
                    display_width=3440, display_height=1440, display_refresh_hz=59.973,
                    presented_frame_ids=list(range(118)), presented_times=[1 + i / 60 for i in range(118)])

    def correlation(self):
        return {'deltas': {'debug.nvrmfb_flip_n': 283, 'debug.nvaccel_iop_async_drop': 0,
                           'debug.nvaccel_iop_async_refused': 0, 'debug.nvaccel_iop_fail': 0}}

    def test_positive_and_repeated_scope(self):
        verdict = evaluate(self.evidence(), self.correlation())
        self.assertEqual(verdict['automated_pacing_validation'], 'PASS')
        result = repeated_pacing_result([{'exit_code': 0, 'verdict': verdict}] * 3, 3, 'hash')
        self.assertEqual(result['reproducibility'], 'PASS')
        for key in ('physical_scanout', 'desktop_smoothness', 'frame_contents'):
            self.assertEqual(result[key], 'NOT VERIFIED')

    def test_inactive_missing_configuration_and_timestamps(self):
        for key, value in [('preflight_ready', False), ('visibility_samples', []), ('display_refresh_hz', 0),
                           ('display_width', 640), ('presented_times', [])]:
            e = self.evidence(); e[key] = value
            self.assertEqual(evaluate(e, self.correlation())['automated_pacing_validation'], 'NOT VERIFIED')
        e = self.evidence(); e['visibility_samples'] = copy.deepcopy(e['visibility_samples'])
        e['visibility_samples'][1]['display_asleep'] = True
        # Hidden-session pacing is not scored, even with a long observed interval.
        e['presented_times'][-1] += .1
        self.assertEqual(evaluate(e, self.correlation())['checks']['api_frame_pacing_60hz'], 'NOT VERIFIED')

    def test_stalls_repeated_reversed_and_missing_frame_ids(self):
        for change in ('stall', 'repeat', 'reverse', 'gap', 'skips'):
            e = self.evidence()
            if change == 'stall': e['presented_times'][-1] += 1 / 60
            if change == 'repeat': e['presented_times'][50] = e['presented_times'][49]
            if change == 'reverse': e['presented_times'][50] = e['presented_times'][49] - .001
            if change == 'gap': e['presented_frame_ids'][-1] += 1
            if change == 'skips': e['timer_skips'] = 1
            self.assertEqual(evaluate(e, self.correlation())['checks']['api_frame_pacing_60hz'], 'FAIL', change)

    def test_errors_override_inactive_and_resets_do_not_pass(self):
        e = self.evidence(); e['visibility_samples'] = []; e['command_errors'] = 1
        self.assertEqual(evaluate(e, self.correlation())['automated_pacing_validation'], 'FAIL')
        c = self.correlation(); c['deltas']['debug.nvaccel_iop_fail'] = -1
        self.assertEqual(evaluate(self.evidence(), c)['checks']['system_display_activity'], 'NOT VERIFIED')

    def test_no_draws_without_readiness_is_not_driver_failure(self):
        e = self.evidence(); e.update(preflight_ready=False, attempted=0, completed=0,
                                      presented_times=[], presented_frame_ids=[])
        self.assertEqual(evaluate(e, self.correlation())['automated_pacing_validation'], 'NOT VERIFIED')
        e.pop('preflight_ready')
        self.assertEqual(evaluate(e, self.correlation())['automated_pacing_validation'], 'NOT VERIFIED')


if __name__ == '__main__':
    unittest.main()
