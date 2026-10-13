#!/usr/bin/env python3
"""Finite owned-page qualification in a real Safari/Firefox application.

Reports browser rAF callback intervals, not physical presentation or GPU timestamps.
No baseline performance claim without matched original-driver browser measurements.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
from pathlib import Path
import secrets
import subprocess
import time


def summarize(data):
    values = data.get('interval_ms', [])
    if not all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in values):
        raise ValueError('Invalid browser clock samples')
    ordered = sorted(values)
    distributions = {name: ordered[min(len(ordered)-1, math.ceil(len(ordered)*q)-1)]
                     for name, q in [('p50', .5), ('p95', .95), ('p99', .99)]} if ordered else {}
    software = 'swiftshader' in data.get('unmasked_renderer', '').lower()
    correct = (data.get('correct') is True and data.get('checked_bytes') == 524288
               and not data.get('gl_errors') and not data.get('lost_context') and not software
               and not data.get('failure'))
    css = data.get('mode') == 'css'
    timing = ((correct or (css and not data.get('failure'))) and len(values) >= 100 and data.get('hidden_samples') == 0
              and data.get('unfocused_samples') == 0
              and data.get('observed_duration_ms', 0) >= data.get('duration_ms', 1))
    return {'correctness': 'NOT VERIFIED' if css else 'PASS' if correct else 'FAIL',
            'timing_eligibility': 'PASS' if timing else 'NOT VERIFIED',
            'interval_ms': distributions, 'intervals_above_25ms': sum(v > 25 for v in values),
            'samples': len(values), 'scope': 'browser callbacks; not physical scanout'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--app', choices=['Safari', 'Firefox'], required=True)
    p.add_argument('--seconds', type=int, choices=range(10, 181), default=60)
    p.add_argument('--mode', choices=['webgl','css'], default='webgl')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(mode=0o700)
    content = Path(__file__).with_name('ga102_browser_workload.html').read_bytes()
    (args.output/'workload-source.html').write_bytes(content)
    token = secrets.token_hex(24)
    result = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            if self.path.split('?')[0] != '/workload':
                self.send_error(404); return
            self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content))); self.end_headers(); self.wfile.write(content)
        def do_POST(self):
            if self.path != '/result?token='+token:
                self.send_error(403); return
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4000000:
                self.send_error(413); return
            data = json.loads(self.rfile.read(length)); result.append(data)
            self.send_response(200); self.end_headers()
    server = HTTPServer(('127.0.0.1', 0), Handler); server.timeout = 1
    url = f'http://127.0.0.1:{server.server_port}/workload?token={token}&seconds={args.seconds}&mode={args.mode}'
    subprocess.run(['/usr/bin/open', '-a', args.app, url], check=True)
    deadline = time.monotonic() + args.seconds + 90
    while not result and time.monotonic() < deadline:
        server.handle_request()
    server.server_close()
    if not result:
        (args.output/'failure.json').write_text(json.dumps({'failure':'no callback before deadline','app':args.app}))
        raise SystemExit('FAIL: browser did not deliver results; retain timeout evidence')
    report = {'app':args.app, 'html_sha256':hashlib.sha256(content).hexdigest(),
              'raw':result[0], 'summary':summarize(result[0])}
    (args.output/'results.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(json.dumps(report['summary']))
    if args.mode == 'webgl' and report['summary']['correctness'] != 'PASS': raise SystemExit(1)


if __name__ == '__main__': main()
