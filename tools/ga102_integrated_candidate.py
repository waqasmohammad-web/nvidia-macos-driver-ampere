#!/usr/bin/env python3
"""Stage and transactionally publish only the production NVMTL bundle and NVK.

No kext, kernel collection, configuration, cache, EFI or security operations.
The caller must establish independent Recovery access before installation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

TARGETS = ('NVMTLDriver.bundle', 'nvmtl/libvulkan_nouveau.dylib')
LICENSES = ('LLVM-LICENSE.txt', 'ZSTD-COPYING.txt', 'ZSTD-LICENSE.txt')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def snapshot(path):
    """Contents, symlinks and permissions, independent of staging ownership."""
    path = Path(path)
    result = {}
    for entry in [path] + (sorted(path.rglob('*')) if path.is_dir() else []):
        key = str(entry.relative_to(path))
        st = entry.lstat()
        value = {'mode': st.st_mode & 0o7777}
        if entry.is_symlink():
            value['link'] = os.readlink(entry)
        elif entry.is_file():
            value['sha256'] = sha(entry)
        else:
            value['directory'] = True
        result[key] = value
    return result


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        target.symlink_to(os.readlink(source))
    elif source.is_dir():
        target.mkdir(mode=source.stat().st_mode & 0o7777)
        for entry in source.iterdir():
            copy(entry, target / entry.name)
    else:
        # copystat also copies Darwin restricted flags, which an ordinary build
        # process cannot set. Preserve contents/modes without copying those flags
        # into a new candidate; original metadata remains in the recovery archive.
        shutil.copyfile(source, target)
        target.chmod(source.stat().st_mode & 0o7777)


def publish(root, stage, job, checkpoint=lambda name: None):
    """Preserve originals and roll back all publications on synchronous failure.

    Each rename is atomic, but the two-target transaction is not crash-atomic.
    Independent external backups are required for power loss or process death.
    Loaded processes retain old mappings until an authorized restart.
    """
    require(not job.exists(), 'Deployment job already exists')
    job.mkdir()
    saved, installed = [], []
    try:
        for name in TARGETS:
            target, candidate = root / name, stage / name
            original = job / 'original' / name
            original.parent.mkdir(parents=True, exist_ok=True)
            target.rename(original)
            saved.append(name)
            checkpoint('saved:' + name)
            candidate.rename(target)
            installed.append(name)
            checkpoint('published:' + name)
        checkpoint('complete')
    except BaseException:
        for name in reversed(saved):
            target = root / name
            if name in installed:
                failed = job / 'failed' / name
                failed.parent.mkdir(parents=True, exist_ok=True)
                target.rename(failed)
            (job / 'original' / name).rename(target)
        raise


def prepare(root, binaries, output, revision):
    require(not output.exists(), 'Output already exists')
    output.mkdir()
    baseline = {name: snapshot(root / name) for name in TARGETS}
    stage = output / 'payload'
    for name in TARGETS:
        copy(root / name, stage / name)
    macos = stage / TARGETS[0] / 'Contents/MacOS'
    for name in ('NVMTLDriver', 'libnvmtl_translate.dylib'):
        shutil.copy2(binaries / name, macos / name)
        (macos / name).chmod(0o755)
    shutil.copy2(binaries / 'libvulkan_nouveau.dylib', stage / TARGETS[1])
    (stage / TARGETS[1]).chmod(0o755)
    # Apple's signer treats executable text beneath MacOS as nested unsigned
    # code. Keep these original license bytes in the standard Resources area.
    resources = stage / TARGETS[0] / 'Contents/Resources/air-runtime'
    resources.mkdir(parents=True)
    for name in LICENSES:
        old = macos / 'air-runtime' / name
        new = resources / name
        require(old.is_file(), 'Missing runtime license: ' + name)
        old.rename(new)
        new.chmod(0o644)
    subprocess.run(['codesign', '-f', '-s', '-', str(stage / TARGETS[0])], check=True)
    for path in (stage / TARGETS[0], stage / TARGETS[1]):
        subprocess.run(['codesign', '--verify', '--strict', str(path)], check=True)
    candidate = {name: snapshot(stage / name) for name in TARGETS}
    allowed = {'Contents/MacOS/NVMTLDriver', 'Contents/MacOS/libnvmtl_translate.dylib',
               'Contents/_CodeSignature/CodeResources', 'Contents/Resources',
               'Contents/Resources/air-runtime'}
    for name in LICENSES:
        old, new = 'Contents/MacOS/air-runtime/' + name, 'Contents/Resources/air-runtime/' + name
        allowed.update((old, new))
        require(baseline[TARGETS[0]][old]['sha256'] == candidate[TARGETS[0]][new]['sha256'],
                'Runtime license bytes changed: ' + name)
    for key in set(baseline[TARGETS[0]]) | set(candidate[TARGETS[0]]):
        if key not in allowed:
            require(baseline[TARGETS[0]].get(key) == candidate[TARGETS[0]].get(key),
                    'Unexpected bundle change: ' + key)
    proof = {'source_revision': revision, 'baseline': baseline, 'candidate': candidate,
             'targets': list(TARGETS), 'installed': False, 'loaded': False,
             'desktop_improvement': 'NOT VERIFIED'}
    (output / 'package.private.json').write_text(json.dumps(proof, indent=2) + '\n')


def preflight(package, recovery):
    proof = json.loads((package / 'package.private.json').read_text())
    require(proof['targets'] == list(TARGETS), 'Unexpected replacement scope')
    root = Path('/Library/GPUBundles')
    for name in TARGETS:
        require(snapshot(root / name) == proof['baseline'][name], 'Installed baseline changed: ' + name)
        require(snapshot(package / 'payload' / name) == proof['candidate'][name], 'Candidate changed: ' + name)
    verify_recovery(recovery, proof)
    return proof


def verify_recovery(recovery, proof):
    recovery_proof = json.loads((recovery / 'recovery.private.json').read_text())
    require(recovery_proof['tested_current_data_access'] is True, 'Recovery access is unverified')
    for name, digest in recovery_proof['files'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'Invalid recovery path')
        require(sha(recovery / name) == digest, 'Recovery backup changed: ' + name)
    require(recovery_proof['baseline'] == proof['baseline'], 'Recovery does not match current driver')
    # Kernel binaries and collections are gates, never installation targets.
    for path, digest in recovery_proof['unchanged_components'].items():
        require(sha(Path(path)) == digest, 'Working dependency changed: ' + path)


def rollback(package, recovery, job):
    require(os.geteuid() == 0, 'Administrator authentication required')
    require(job.parent == Path('/Library') and job.name.startswith('GA102-UserSpace-')
            and not job.is_symlink(), 'Unexpected deployment job')
    proof = json.loads((package / 'package.private.json').read_text())
    require(proof['targets'] == list(TARGETS), 'Unexpected replacement scope')
    verify_recovery(recovery, proof)
    root = Path('/Library/GPUBundles')
    for name in TARGETS:
        require(snapshot(root / name) == proof['candidate'][name], 'Active files changed: ' + name)
        require(snapshot(job / 'original' / name) == proof['baseline'][name], 'Original backup changed: ' + name)
    lock = Path('/Library/NullMoth/install.lock')
    lock.mkdir()
    try:
        def checkpoint(point):
            if point == 'complete':
                for name in TARGETS:
                    require(snapshot(root / name) == proof['baseline'][name], 'Rollback mismatch: ' + name)
                (job / 'rollback-status.json').write_text(json.dumps({
                    'state': 'original_restored_on_disk', 'loaded': 'requires independent image inspection'},
                    indent=2) + '\n')
        publish(root, job / 'original', job / 'rollback', checkpoint)
        print('PASS: originals restored, candidate preserved; no restart performed')
    finally:
        lock.rmdir()


def install(package, recovery):
    require(os.geteuid() == 0, 'Administrator authentication required')
    proof = preflight(package, recovery)
    lock = Path('/Library/NullMoth/install.lock')
    lock.parent.mkdir(exist_ok=True)
    lock.mkdir()  # Never bypass another installer.
    try:
        import time
        job = Path('/Library') / ('GA102-UserSpace-' + str(time.time_ns()))
        stage = Path('/Library/GPUBundles') / ('.ga102-stage-' + str(time.time_ns()))
        stage.mkdir(mode=0o755)
        for name in TARGETS:
            copy(package / 'payload' / name, stage / name)
        for entry in [stage] + list(stage.rglob('*')):
            os.chown(entry, 0, 0, follow_symlinks=False)
        preflight(package, recovery)
        def checkpoint(point):
            if point != 'complete':
                return
            for name in TARGETS:
                require(snapshot(Path('/Library/GPUBundles') / name) == proof['candidate'][name],
                        'Post-publication mismatch: ' + name)
            (job / 'status.json').write_text(json.dumps({
                'state': 'installed_on_disk_pending_restart', 'source_revision': proof['source_revision'],
                'candidate': proof['candidate'], 'loaded': False,
                'desktop_improvement': 'NOT VERIFIED'}, indent=2) + '\n')
        publish(Path('/Library/GPUBundles'), stage, job, checkpoint)
        shutil.rmtree(stage)
        print(job, flush=True)
    finally:
        lock.rmdir()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='operation', required=True)
    stage = sub.add_parser('prepare')
    stage.add_argument('--installed', type=Path, default=Path('/Library/GPUBundles'))
    stage.add_argument('--binaries', type=Path, required=True)
    stage.add_argument('--output', type=Path, required=True)
    stage.add_argument('--revision', required=True)
    for action in ('check', 'install', 'rollback'):
        cmd = sub.add_parser(action)
        cmd.add_argument('--package', type=Path, required=True)
        cmd.add_argument('--recovery', type=Path, required=True)
        if action == 'rollback':
            cmd.add_argument('--job', type=Path, required=True)
    args = p.parse_args()
    if args.operation == 'prepare':
        prepare(args.installed, args.binaries, args.output, args.revision)
    elif args.operation == 'check':
        preflight(args.package, args.recovery)
        print('PASS: package, installed baseline, dependencies and recovery hashes')
    elif args.operation == 'rollback':
        rollback(args.package, args.recovery, args.job)
    else:
        install(args.package, args.recovery)


if __name__ == '__main__':
    main()
