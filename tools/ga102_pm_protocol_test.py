#!/usr/bin/env python3
"""Offline superclass-forwarding test of the experimental framebuffer patch.

Applies the actual patch to an owned copy of the production translation unit,
then compiles its power callback with a CPU-only superclass stub. This verifies
exact ordinal/device/ack forwarding and absence of premature notifications,
not IOGraphics runtime behavior, GPU resume or safe kernel deployment.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PREAMBLE = r'''
#include <cstdint>
#include <cstdio>
using IOReturn = uint32_t;
class IOService {};
static constexpr IOReturn kIOPMAckImplied=0;
static constexpr int kIOFBNotifyDidPowerOn=8, kIOFBNotifyWillPowerOff=7;
#define FBLOG(...) ((void)0)
class Base {
public:
    unsigned calls=0, notifications=0;
    unsigned long seenOrdinal=0;
    IOService *seenDevice=nullptr;
    IOReturn answer=0;
    virtual IOReturn setPowerState(unsigned long ordinal,IOService *device) {
        ++calls;seenOrdinal=ordinal;seenDevice=device;return answer;
    }
    void handleEvent(int) { ++notifications; }
};
class NVRMNVDAFramebuffer:public Base {
public: IOReturn setPowerState(unsigned long,IOService *) override;
};
#define super Base
'''
MAIN = r'''
int main() {
    IOService service;
    unsigned checked=0;
    for (unsigned long ordinal:{0ul,1ul,2ul})
    for (IOReturn answer:{0u,45000000u,0xe00002bcu}) {
        NVRMNVDAFramebuffer fb;fb.answer=answer;
        IOReturn got=fb.setPowerState(ordinal,&service);
        if (got!=answer || fb.calls!=1 || fb.notifications || fb.seenOrdinal!=ordinal || fb.seenDevice!=&service) {
            puts("FAIL: superclass acknowledgement/forwarding contract");return 1;
        }
        ++checked;
    }
    puts("PASS: 9 exact superclass/acknowledgement cases; no premature notification");
    return checked==9 ? 0:1;
}
'''


def method(source):
    begin=source.index('IOReturn NVRMNVDAFramebuffer::setPowerState(')
    return source[begin:source.index('IOReturn NVRMNVDAFramebuffer::setAttribute(',begin)]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    staging=args.output/'source';staging.mkdir()
    file=staging/'kexts/NVRMFB/fb/nvrm-fb.cpp';file.parent.mkdir(parents=True)
    source=(ROOT/'kexts/NVRMFB/fb/nvrm-fb.cpp').read_text();file.write_text(source)
    patch=ROOT/'build/experimental/ga102-framebuffer-pm.patch'
    subprocess.run(['git','apply','--check',str(patch)],cwd=staging,check=True,timeout=10)
    subprocess.run(['git','apply',str(patch)],cwd=staging,check=True,timeout=10)
    rows=[]
    for label,text in [('original',source),('candidate',file.read_text())]:
        callback=method(text)
        unit=args.output/(label+'.cpp');unit.write_text(PREAMBLE+'\n#include <initializer_list>\n'+callback+MAIN)
        exe=args.output/label
        subprocess.run(['xcrun','clang++','-std=c++17','-O1','-fsanitize=address,undefined',str(unit),'-o',str(exe)],check=True,timeout=30)
        r=subprocess.run([str(exe.resolve())],capture_output=True,text=True,timeout=10)
        (args.output/(label+'.private.log')).write_text(r.stdout+r.stderr)
        row={'variant':label,'exit_code':r.returncode,'callback_sha256':hashlib.sha256(callback.encode()).hexdigest()}
        rows.append(row)
        if label=='candidate' and r.returncode:raise SystemExit('FAIL: candidate forwarding; private evidence retained')
        if label=='original' and r.returncode==0:raise SystemExit('FAIL: negative control did not reproduce bypass')
    (args.output/'results.json').write_text(json.dumps({'scope':'CPU-only callback contract; real superclass replaced with stub',
        'patch_sha256':hashlib.sha256(patch.read_bytes()).hexdigest(),'results':rows,'wake_recovery':'NOT VERIFIED'},indent=2)+'\n')
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
