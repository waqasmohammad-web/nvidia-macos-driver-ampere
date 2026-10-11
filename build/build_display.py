#!/usr/bin/env python3
"""Build release display components in a new directory; never install or load.

NVRM and its Darwin NVIDIA archives must be built separately. This command does
not claim that these components constitute a complete driver release.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
VENDOR_REVISION = 'e4a5faa2567f28c8eabe0ebb6422b6d0abcf37eb'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True,
                        help='New directory; existing directories are refused')
    parser.add_argument('--vulkan-headers', type=Path,
                        help='Optional Vulkan-Headers include directory to also link the release plugin')
    args = parser.parse_args()
    vendor, out = args.vendor.resolve(), args.output.resolve()
    revision = subprocess.check_output(
        ['git', '-C', str(vendor), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != VENDOR_REVISION:
        parser.error('Expected the exact NVIDIA 610.57.04 revision')
    if subprocess.check_output(['git', '-C', str(vendor), 'diff', 'HEAD',
                                '--name-only'], text=True).strip():
        parser.error('Vendor tracked files must match the pinned revision')
    if out.exists():
        parser.error('Output directory already exists; refusing to overwrite')
    if args.vulkan_headers and not (args.vulkan_headers / 'vulkan/vulkan_core.h').is_file():
        parser.error('Missing Vulkan-Headers include/vulkan/vulkan_core.h')
    includes = ['kernel-open/nvidia-modeset', 'kernel-open/common/inc',
                'src/common/sdk/nvidia/inc', 'src/common/sdk/nvidia/inc/hw',
                'src/common/shared/inc', 'src/common/inc',
                'src/common/unix/common/inc',
                'src/common/unix/common/utils/interface', 'src/common/modeset',
                'src/nvidia-modeset/kapi/interface',
                'src/nvidia-modeset/kapi/include',
                'src/nvidia-modeset/interface', 'src/nvidia-modeset/include',
                'src/nvidia-modeset/os-interface/include']
    header = vendor / 'kernel-open/nvidia-modeset/nvkms.h'
    if not header.is_file():
        parser.error('Missing real upstream nvkms.h')
    sdk = subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip()
    out.mkdir(parents=True, exist_ok=False)
    flags = ['-arch', 'x86_64', '-fapple-kext', '-mkernel', '-nostdinc',
             '-I' + sdk + '/System/Library/Frameworks/Kernel.framework/Headers',
             '-DKERNEL', '-DKERNEL_PRIVATE', '-DDRIVER_PRIVATE', '-DAPPLE',
             '-DNeXT', '-std=c++17', '-fno-rtti', '-fno-exceptions',
             '-fno-builtin', '-fno-common', '-O2',
             '-Wno-inconsistent-missing-override', '-Wno-unused-parameter',
             '-ffile-prefix-map=' + str(ROOT) + '=/src',
             '-ffile-prefix-map=' + str(vendor) + '=/vendor',
             '-ffile-prefix-map=' + str(Path.home()) + '=/build']
    flags += ['-I' + str(vendor / path) for path in includes]
    flags += ['-I' + str(ROOT / path) for path in
              ['kexts/NVRM', 'kexts/NVRM/accel', 'kexts/NVRM/accel/re',
               'kexts/NVRM/accel/iofam', 'kexts/NVRMFB', 'kexts/NVRMAGDC']]
    components = [('NVRMFB', 'kexts/NVRMFB/fb/nvrm-fb.cpp',
                   'kexts/NVRMFB/fb/Info.plist'),
                  ('NVAccel', 'kexts/NVRM/accel/nvrm-accel.cpp',
                   'kexts/NVRM/accel/Info.plist'),
                  ('NVRMAGDC', 'kexts/NVRMAGDC/nvrm-agdc.cpp',
                   'kexts/NVRMAGDC/Info.plist')]
    proof = {'vendor_revision': revision, 'source_revision':
             subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse',
                                      'HEAD'], text=True).strip(),
             'configuration': 'macOS 15 x86_64, O2, NM_TAHOE unset',
             'compiler': subprocess.check_output(['xcrun', 'clang++', '--version'],
                                                 text=True).splitlines()[0],
             'sdk_version': subprocess.check_output(['xcrun', '--show-sdk-version'],
                                                    text=True).strip(),
             'nvkms_header_sha256': hashlib.sha256(header.read_bytes()).hexdigest(),
             'complete_driver_release': False, 'components': {}}
    proof['source_inputs'] = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for directory in ['kexts', 'plugin', 'build']
        for path in sorted((ROOT / directory).rglob('*'))
        if path.is_file() and path.suffix in {'.h', '.cpp', '.c', '.m', '.inc', '.plist', '.py'}
    }
    for name, source, plist in components:
        binary = out / (name + '.kext') / 'Contents/MacOS' / name
        binary.parent.mkdir(parents=True)
        obj = out / (name + '.o')
        with (out / (name + '.log')).open('w') as log:
            subprocess.run(['xcrun', 'clang++'] + flags +
                           ['-c', str(ROOT / source), '-o', str(obj)],
                           stdout=log, stderr=subprocess.STDOUT, check=True,
                           timeout=120)
            subprocess.run(['xcrun', 'clang++', '-arch', 'x86_64',
                            '-fapple-kext', '-nostdlib', '-Xlinker', '-kext',
                            '-lkmodc++', '-lkmod', '-lcc_kext', str(obj),
                            '-o', str(binary)], stdout=log,
                           stderr=subprocess.STDOUT, check=True, timeout=60)
        shutil.copyfile(ROOT / plist, binary.parent.parent / 'Info.plist')
        proof['components'][name] = {
            'source_sha256': hashlib.sha256((ROOT / source).read_bytes()).hexdigest(),
            'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
        print(name + ': compiled and linked; not installed')
    if args.vulkan_headers:
        binary = out / 'NVMTLDriver'
        with (out / 'NVMTLDriver.log').open('w') as log:
            subprocess.run(['xcrun', 'clang', '-arch', 'x86_64', '-bundle',
                            '-fobjc-arc', '-O1', '-DNVMTL_RELEASE=1',
                            '-Wno-protocol', '-Wno-incomplete-implementation',
                            '-I' + str(args.vulkan_headers.resolve()),
                            '-ffile-prefix-map=' + str(ROOT) + '=/src',
                            '-ffile-prefix-map=' + str(Path.home()) + '=/build',
                            '-o', str(binary), str(ROOT / 'plugin/NVMTLDevice.m'),
                            '-framework', 'Foundation', '-framework', 'Metal',
                            '-framework', 'IOSurface'], stdout=log,
                           stderr=subprocess.STDOUT, check=True, timeout=120)
        proof['components']['NVMTLDriver'] = {
            'configuration': 'NVMTL_RELEASE=1, x86_64, O1',
            'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
        print('NVMTLDriver: release binary linked; bundle packaging not performed')
    (out / 'build-proof.json').write_text(json.dumps(proof, indent=2) + '\n')


if __name__ == '__main__':
    main()
