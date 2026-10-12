#!/usr/bin/env python3
"""Build a private Objective-C class namespace for isolated offscreen testing.

Only copied sources are rewritten. Class names and their literal lookup strings
are renamed together; C symbols are hidden. No driver installation, kernel
collection, configuration or graphics-service operation is performed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
PREFIX='NVMTLGA102_'


def snapshot(directory):
    files=[f for f in (ROOT/'plugin').iterdir() if f.is_file()]
    names=set()
    for f in files:
        if f.suffix in ('.m','.h','.c'):
            names.update(re.findall(r'@(?:interface|implementation|protocol)\s+(NVMTL\w+)',f.read_text()))
    if 'NVMTLDevice' not in names:raise ValueError('device declaration unavailable')
    mapping={name:PREFIX+name[5:] for name in sorted(names)}
    pattern=re.compile(r'\b('+ '|'.join(map(re.escape,mapping))+r')\b')
    hashes={}
    for f in files:
        original=f.read_bytes();hashes[f.name]=hashlib.sha256(original).hexdigest()
        if f.suffix in ('.m','.h','.c'):
            transformed=pattern.sub(lambda m:mapping[m[0]],original.decode())
            # This global is returned by resource -device methods; keep it private
            # even if the installed bundle is subsequently loaded by IOSurface.
            transformed=re.sub(r'\bgNVMTLMainDevice\b','gGA102MainDevice',transformed)
            (directory/f.name).write_text(transformed)
        else:(directory/f.name).write_bytes(original)
    return mapping,hashes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--vulkan-headers',type=Path,required=True)
    args=parser.parse_args()
    if not (args.vulkan_headers/'vulkan/vulkan_core.h').is_file():parser.error('Vulkan include directory required')
    args.output.mkdir(parents=True,exist_ok=False)
    source=args.output/'source';source.mkdir()
    mapping,hashes=snapshot(source)
    binary=args.output/'NVMTLDriver'
    cmd=['xcrun','clang','-arch','x86_64','-bundle','-fobjc-arc','-O1','-DNVMTL_RELEASE=1',
         '-fvisibility=hidden','-Wno-protocol','-Wno-incomplete-implementation',
         '-I'+str(args.vulkan_headers.resolve()),'-o',str(binary),str(source/'NVMTLDevice.m'),
         '-framework','Foundation','-framework','Metal','-framework','IOSurface']
    with (args.output/'build.private.log').open('w') as log:
        subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=90)
    for name in ['libnvmtl_translate.dylib','air-runtime']:
        target=Path('/Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS')/name
        if not target.exists():raise FileNotFoundError('installed CPU translator/runtime dependency absent')
        (args.output/name).symlink_to(target)
    proof={'schema_version':1,'class_prefix':PREFIX,'class_mapping':mapping,
           'source_sha256':hashes,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
           'installed':False,'runtime_executed':False,'c_symbols_hidden':True,
           'limits':'experimental namespace build; GPU correctness/provenance require separate execution'}
    (args.output/'isolation-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    (args.output/'command.private.json').write_text(json.dumps(cmd,indent=2)+'\n')
    print(json.dumps({'binary_sha256':proof['binary_sha256'],'renamed_classes_and_protocols':len(mapping),'installed':False}))


if __name__=='__main__':main()
