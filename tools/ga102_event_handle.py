#!/usr/bin/env python3
"""Bounded shared-event handle capability check, no XPC service or GPU commands."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
try:
    from .ga102_run_metal import run_owned
except ImportError:
    from ga102_run_metal import run_owned


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('output must name a new evidence file')
    report={'scope':'API event handle export/reimport only, no cross-process transfer or GPU work',
            'acceptance':'BLOCKED','physical_scanout':'NOT VERIFIED','desktop_causality':'NOT VERIFIED',
            'installed_driver_fixed':False}
    if sys.platform=='darwin' and shutil.which('xcrun'):
        root=Path(tempfile.mkdtemp(prefix='ga102-event-handle-'))
        source=(Path(__file__).parent/'ga102_metal_event_handle.m').read_bytes()
        (root/'probe.m').write_bytes(source)
        report['probe_source_sha256']=hashlib.sha256(source).hexdigest()
        try:
            with (root/'compile.log').open('w') as log:
                code=run_owned(['xcrun','clang','-fobjc-arc','-Wall','-Wextra','-Werror',str(root/'probe.m'),
                    '-framework','Foundation','-framework','Metal','-o',str(root/'probe')],log,30)
            report['compiler_exit']=code
            if code==0:
                with (root/'run.log').open('w') as log:code=run_owned([str(root/'probe')],log,20)
                report['runner_exit_code']=code
                evidence=next((json.loads(x[8:]) for x in (root/'run.log').read_text().splitlines() if x.startswith('result: ')),{})
                report['evidence']=evidence
                statuses=[evidence.get(key,'NOT VERIFIED') for key in
                          ('same_process_value_roundtrip','handle_export','same_process_handle_import')]
                report['acceptance']='FAIL' if 'FAIL' in statuses else 'PASS' if code==0 and all(s=='PASS' for s in statuses) else 'NOT VERIFIED'
            else:report['reason']='capability probe did not compile; private diagnostic logs retained'
        except subprocess.TimeoutExpired:
            report.update(acceptance='FAIL',reason='owned compiler/probe deadline exceeded')
    else:report['reason']='macOS and Xcode command-line tools required'
    with args.output.open('x') as out:json.dump(report,out,indent=2,sort_keys=True);out.write('\n')
    print(json.dumps(report,sort_keys=True))
    return 1 if report['acceptance']=='FAIL' else 0


if __name__=='__main__':raise SystemExit(main())
