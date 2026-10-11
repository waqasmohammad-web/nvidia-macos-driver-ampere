#!/usr/bin/env python3
"""Prepare offline framebuffer candidate/rollback bundles against release 1.11.0.

This is reproducible assembly using authentic prebuilt dependencies, not a
complete NVRM source build. Nothing is installed, loaded or executed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent.parent
RELEASE_SHA = '6e568e28ee34c3b41f4dfda980fd8feb50fdd0a69cf6d0f6e54338873b8ec2e7'
SOURCE_REV = 'e404ab30b94d6588bdf63b3724d59f1e713ad963'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--release', required=True, type=Path)
    p.add_argument('--release-source', required=True, type=Path)
    p.add_argument('--display-build', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    if digest(a.release) != RELEASE_SHA:
        p.error('Release does not match the published 1.11.0 digest')
    rev = subprocess.check_output(['git', '-C', str(a.release_source),
                                   'rev-parse', 'HEAD'], text=True).strip()
    if rev != SOURCE_REV:
        p.error('Wrong 1.11.0 source revision')
    if subprocess.check_output(['git', '-C', str(a.release_source), 'diff',
                                'HEAD', '--name-only'], text=True).strip():
        p.error('Release source has tracked modifications')
    # Every existing kernel input except the instrumented TU must match baseline.
    checked = {}
    for path in sorted((ROOT / 'kexts').rglob('*')):
        relative = path.relative_to(ROOT)
        baseline = a.release_source / relative
        if not path.is_file() or not baseline.is_file():
            continue
        if str(relative) == 'kexts/NVRMFB/fb/nvrm-fb.cpp':
            continue
        if digest(path) != digest(baseline):
            p.error('Kernel baseline mismatch: ' + str(relative))
        checked[str(relative)] = digest(path)
    build = json.loads((a.display_build / 'build-proof.json').read_text())
    for name, expected in build['source_inputs'].items():
        if name.startswith('kexts/') and digest(ROOT / name) != expected:
            p.error('Candidate kernel sources changed since build: ' + name)
    candidate = a.display_build / 'NVRMFB.kext'
    executable = candidate / 'Contents/MacOS/NVRMFB'
    if digest(executable) != build['components']['NVRMFB']['binary_sha256']:
        p.error('Candidate binary differs from build proof')
    if a.output.exists():
        p.error('Output exists; refusing to overwrite')
    a.output.mkdir(parents=True)
    shutil.copytree(candidate, a.output / 'candidate/NVRMFB.kext')
    base = 'pkgroot/Library/Extensions/NVRMFB.kext/'
    release_files = {}
    with tarfile.open(a.release, 'r:gz') as archive:
        for member in archive:
            if not member.isfile() or not member.name.startswith(base):
                continue
            relative = Path(member.name[len(base):])
            if '..' in relative.parts or relative.is_absolute():
                p.error('Unsafe release member')
            dest = a.output / 'rollback/NVRMFB.kext' / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(archive.extractfile(member).read())
            dest.chmod(member.mode & 0o777)
            release_files[str(relative)] = digest(dest)
    if 'Contents/MacOS/NVRMFB' not in release_files:
        p.error('Missing original framebuffer binary')
    proof = {'release_tag': 'v1.11.0', 'release_sha256': RELEASE_SHA,
             'release_source_revision': SOURCE_REV,
             'candidate_binary_sha256': digest(executable),
             'rollback_files': release_files, 'matched_kernel_inputs': checked,
             'complete_source_build': False, 'installed_or_loaded': False,
             'scope': 'NVRMFB completion observability only; preserve every other installed component and configuration',
             'build': build}
    (a.output / 'candidate-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
    print('Candidate and original rollback framebuffer prepared; NOT live validated.')


if __name__ == '__main__':
    main()
