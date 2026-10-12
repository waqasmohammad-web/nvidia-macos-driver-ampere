#!/usr/bin/env python3
"""Sequential, bounded GA102 probe suite. No installation or system settings.

Each runner owns its compiler/probe deadlines and process groups. The suite waits
for that runner rather than imposing a second timeout that could orphan a probe.
Raw output stays in private scratch. --output writes a new sanitized artifact.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
try:
    from .ga102_core_validation import CORE_PROBES
except ImportError:
    from ga102_core_validation import CORE_PROBES

ROOT = Path(__file__).resolve().parent.parent


def plan(profile, repeat):
    jobs = []
    if profile in ('correctness', 'all'):
        jobs += [(probe, [], repeat, None) for probe in CORE_PROBES]
    if profile in ('presentation', 'all'):
        jobs += [('ga102_visual_present', ['--capture-bridge'], repeat, None),
                 ('ga102_ca_visual', ['--capture-bridge'], repeat, None),
                 ('ga102_ca_visual', ['--capture-bridge', '--continuous'], repeat, None),
                 ('ga102_visual_present', ['--capture-bridge', '--continuous', '--display-linked'], repeat, None),
                 ('ga102_metal_present', [], repeat, None),
                 ('ga102_metal_present', ['--display-linked'], repeat, None)]
    if profile in ('negative-controls', 'all'):
        jobs += [('ga102_visual_present', ['--capture-bridge', '--negative-control', mode], 1, expected)
                 for mode, expected in (('static', 'FAIL'), ('timestamps', 'NOT VERIFIED'), ('hidden', 'NOT VERIFIED'))]
        jobs += [('ga102_ca_visual', ['--capture-bridge', '--negative-control', mode], 1, expected)
                 for mode, expected in (('static', 'FAIL'), ('hidden', 'NOT VERIFIED'))]
        jobs += [('ga102_ca_visual', ['--capture-bridge', '--continuous', '--negative-control', mode], 1, 'NOT VERIFIED')
                 for mode in ('static', 'hidden')]
        jobs += [('ga102_visual_present', ['--capture-bridge', '--continuous', '--display-linked', '--negative-control', mode], 1, expected)
                 for mode, expected in (('static','FAIL'),('timestamps','NOT VERIFIED'),('hidden','NOT VERIFIED'))]
    return jobs


def summarize(jobs):
    statuses = [j['acceptance'] for j in jobs]
    overall = ('FAIL' if 'FAIL' in statuses else 'BLOCKED' if 'BLOCKED' in statuses else
               'PASS' if statuses and all(s == 'PASS' for s in statuses) else 'NOT VERIFIED')
    return {'schema_version': 1, 'scope': 'selected bounded probe checks', 'acceptance': overall,
            'jobs': jobs, 'physical_scanout': 'NOT VERIFIED', 'desktop_smoothness': 'NOT VERIFIED',
            'installed_driver_fixed': False}


def failure_requires_stop(report):
    """Only isolated cadence failures with proven healthy GPU work may continue."""
    runs=report.get('runs',[])
    if not runs or any(r.get('exit_code') != 0 for r in runs):return True
    for run in runs:
        checks=run.get('verdict',{}).get('checks',{})
        failed={k for k,v in checks.items() if v=='FAIL'}
        if not failed or not failed.issubset({'reported_presentation_cadence','known_adjacent_reported_cadence'}):return True
        if any(checks.get(k) != 'PASS' for k in ('gpu_frame_contents','presentation_timestamps',
            'visible_window_state','system_display_activity')):return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('correctness', 'presentation', 'negative-controls', 'all'), default='correctness')
    parser.add_argument('--repeat', type=int, choices=(1, 2, 3), default=1,
                        help='Use 3 for reproducibility; controls always run once')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--plugin', type=Path, help='Use explicit process-local plugin binding for the correctness profile only')
    args = parser.parse_args()
    if args.plugin and args.profile != 'correctness': parser.error('--plugin requires --profile correctness')
    if args.output.exists(): parser.error('--output must name a new file')
    scratch = Path(tempfile.mkdtemp(prefix='ga102-suite-'))
    print(f'Private suite scratch: {scratch}', flush=True)
    results = []
    stop_reason = None
    available = sys.platform == 'darwin' and shutil.which('xcrun') is not None
    for index, (probe, options, repeat, expected) in enumerate(plan(args.profile, args.repeat)):
        job = {'probe': probe, 'options': options, 'requested_runs': repeat}
        if stop_reason:
            job.update(acceptance='NOT VERIFIED', reason=stop_reason)
        elif args.plugin and probe not in ('ga102_metal_smoketest', 'ga102_metal_render_smoketest', 'ga102_metal_events'):
            job.update(acceptance='BLOCKED', reason='IOSurface may load installed plugin; candidate class isolation unavailable')
        elif not available:
            job.update(acceptance='BLOCKED', reason='macOS and Xcode command-line tools required')
        else:
            artifact = scratch / f'job-{index}.json'
            command = [sys.executable, str(ROOT / 'tools/ga102_run_metal.py'), probe,
                       '--isolated-cache', '--repeat', str(repeat), '--result-json', str(artifact), *options]
            if args.plugin: command += ['--plugin', str(args.plugin.resolve())]
            print(f'Running {probe} {" ".join(options)} ({repeat} run(s))', flush=True)
            with (scratch / f'job-{index}.log').open('w') as log:
                code = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT).returncode
            if artifact.exists():
                report = json.loads(artifact.read_text())
                actual = next((report[k] for k in ('automated_core_validation', 'automated_visual_validation',
                                                  'automated_pacing_validation', 'automated_ca_validation') if k in report), 'NOT VERIFIED')
                acceptance = actual
                if expected is not None:
                    acceptance = 'PASS' if actual == expected and report.get('completed_runs') == 1 else 'FAIL'
                elif code != 0:
                    acceptance = 'FAIL'
                job.update(acceptance=acceptance, runner_exit_code=code, evidence=report)
                if expected is not None: job['expected_rejection'] = expected
            else:
                job.update(acceptance='FAIL', runner_exit_code=code, reason='runner produced no evidence artifact')
        results.append(job)
        if job['acceptance'] == 'FAIL':
            if failure_requires_stop(job.get('evidence',{})):
                stop_reason = 'remaining GPU launches skipped after unexpected failure; inspect private evidence before retrying'
            else:
                job['reason']='cadence failure with correct GPU frames, eligible visibility and clean counters; bounded independent checks continue'
        print(f'{job["acceptance"]}: {probe}', flush=True)
    report = summarize(results)
    report['profile'] = args.profile
    report['cache_policy'] = 'Mesa/AIR isolation requested; release plugin strips AIR override; globally cold compilation NOT VERIFIED'
    with args.output.open('x') as output:
        json.dump(report, output, indent=2, sort_keys=True, allow_nan=False); output.write('\n')
    print(f'{report["acceptance"]}: selected probe checks; desktop smoothness and physical scanout NOT VERIFIED')
    return 1 if report['acceptance'] == 'FAIL' else 0


if __name__ == '__main__':
    raise SystemExit(main())
