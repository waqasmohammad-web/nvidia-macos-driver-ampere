#!/usr/bin/env python3
"""Approved, single-NVRMFB deployment. Never changes EFI, policy or display mode.

--check performs read-only preflight. Deployment requires Terminal sudo
authentication; --reboot schedules the already-approved restart after success.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

CANDIDATE_HASH = '11c3151b83ba67f02785f585990d97cdee11e499d852d23d60bae47d76f32c53'
ORIGINAL_HASH = 'a2a3cf961df1aae872d500142b8c146ecd660a369f364d843f42c3fb4bd21e71'
PLIST_HASH = 'a44dcb9ece863a7de948ea377e558c74c036d8a126268c834458bf0f3cd781cd'
ARTIFACT = Path(__file__).resolve().parents[2] / 'ga102-release-artifacts/daa4210-framebuffer'
USB = Path('/Volumes/OPENCORE/GA102-Recovery')
TARGET = Path('/Library/Extensions/NVRMFB.kext')
KC = Path('/Library/KernelCollections/AuxiliaryKernelExtensions.kc')
JOB = Path('/Library/GA102-Framebuffer-Test')
LOCK = Path('/Library/NullMoth/install.lock')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1048576), b''):
            h.update(data)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def manifest(path, base):
    for line in path.read_text().splitlines():
        expected, name = line.split('  ', 1)
        relative = Path(name)
        require(not relative.is_absolute() and '..' not in relative.parts,
                'Unsafe manifest path')
        require(sha(base / relative) == expected, 'Baseline changed: ' + name)


def bundle(path, binary_hash):
    require(not any(p.is_symlink() for p in path.rglob('*')), 'Unexpected bundle symlink')
    files = {str(p.relative_to(path)) for p in path.rglob('*') if p.is_file()}
    require(files == {'Contents/MacOS/NVRMFB', 'Contents/Info.plist'},
            'Unexpected framebuffer bundle contents')
    require(sha(path / 'Contents/MacOS/NVRMFB') == binary_hash, 'Wrong framebuffer binary')
    require(sha(path / 'Contents/Info.plist') == PLIST_HASH, 'Wrong framebuffer plist')


def preflight(require_new_job=True):
    bundle(ARTIFACT / 'candidate/NVRMFB.kext', CANDIDATE_HASH)
    bundle(TARGET, ORIGINAL_HASH)
    require(USB.is_dir(), 'Recovery USB must stay connected')
    usb_hashes = dict((name, h) for h, name in
                      (line.split('  ', 1) for line in (USB / 'SHA256SUMS').read_text().splitlines()))
    for name in ['rollback-NVRMFB.tar.gz', 'AuxiliaryKernelExtensions.kc',
                 'BASE-SYSTEM-SHA256SUMS', 'UNCHANGED-DRIVER-SHA256SUMS']:
        require(sha(USB / name) == usb_hashes[name], 'Recovery backup mismatch: ' + name)
    require(sha(KC) == sha(USB / KC.name), 'Current collection changed since backup')
    manifest(USB / 'BASE-SYSTEM-SHA256SUMS', Path('/'))
    manifest(USB / 'UNCHANGED-DRIVER-SHA256SUMS', Path('/'))
    if require_new_job:
        require(not JOB.exists(), 'Deployment directory already exists; inspect prior status before retrying')


def snapshot(directory):
    return {str(p.relative_to(directory)): sha(p) for p in directory.rglob('*') if p.is_file()}


def publish(target, candidate, collection, new_collection, job, checkpoint=lambda stage: None):
    """Atomic publication with preserved originals; failed candidates are retained."""
    original = job / 'OriginalNVRMFB.kext'
    original_kc = job / 'OriginalAuxiliaryKernelExtensions.kc'
    shutil.copyfile(collection, original_kc)
    moved = installed = cache_installed = False
    try:
        target.rename(original)
        moved = True
        checkpoint('original_saved')
        candidate.rename(target)
        installed = True
        checkpoint('candidate_published')
        os.replace(new_collection, collection)
        cache_installed = True
        checkpoint('collection_published')
    except BaseException:
        if installed:
            target.rename(job / 'FailedCandidate.kext')
        if moved:
            original.rename(target)
        if cache_installed:
            restore = job / 'RestoreAuxiliary.kc'
            shutil.copyfile(original_kc, restore)
            restore.chmod(0o744)
            os.replace(restore, collection)
        raise


def run_logged(args, name, timeout=180):
    with (JOB / name).open('w') as log:
        subprocess.run(args, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=timeout)


def identifiers(collection, log_name):
    text = subprocess.check_output(['/usr/bin/kmutil', 'inspect', '-a', 'x86_64',
                                    '-A', str(collection), '--show-kext-uuids'], text=True, timeout=60)
    (JOB / log_name).write_text(text)
    return set(re.findall(r'com\.nullmoth\.[A-Za-z0-9]+', text))


def matching_uuid(lines, identifier, uuid):
    for line in lines:
        fields = line.replace('\\t', '\t').split()
        if fields and fields[0].lower() == identifier.lower() and uuid.lower() in line.lower():
            return True
    return False


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check', action='store_true')
    p.add_argument('--reboot', action='store_true')
    a = p.parse_args()
    require(not (a.check and a.reboot), '--check cannot reboot')
    preflight()
    print('PASS: pinned candidate, installed baseline and critical recovery hashes', flush=True)
    if a.check:
        return
    require(os.geteuid() == 0, 'Run in Terminal with sudo; do not send a password to the agent')
    LOCK.mkdir()  # Existing installer locks are never removed or bypassed.
    try:
        (LOCK / 'owner').write_text('GA102 framebuffer experiment\n')
        JOB.mkdir(mode=0o755)
        repo = JOB / 'repository'
        repo.mkdir()
        before = snapshot(Path('/Library/Extensions'))
        for source in Path('/Library/Extensions').glob('*.kext'):
            chosen = ARTIFACT / 'candidate/NVRMFB.kext' if source == TARGET else source
            run_logged(['/usr/bin/ditto', str(chosen), str(repo / source.name)],
                       source.name + '.copy.log', 60)
        staged = repo / 'NVRMFB.kext'
        bundle(staged, CANDIDATE_HASH)
        for entry in [staged] + list(staged.rglob('*')):
            os.chown(entry, 0, 0)
        new_kc = JOB / 'CandidateAuxiliaryKernelExtensions.kc'
        # Same auxiliary-only build method used by the authentic 1.11.0 installer.
        command = ['/usr/bin/kmutil', 'create', '-n', 'aux', '--volume-root', '/',
                   '--allow-missing-kdk', '-B', '/System/Library/KernelCollections/BootKernelExtensions.kc',
                   '-S', '/System/Library/KernelCollections/SystemKernelExtensions.kc',
                   '--repository', str(repo), '-A', str(new_kc), '-z']
        kernel = Path('/System/Library/Kernels/kernel')
        if kernel.is_file():
            command += ['--kernel', str(kernel)]
        print('Building isolated candidate auxiliary collection; installed files untouched.', flush=True)
        run_logged(command, 'collection-build.log')
        expected = {'com.nullmoth.' + name for name in ['NVRM', 'NVAccel', 'NVRMFB', 'NVRMAGDC']}
        require(identifiers(new_kc, 'candidate-inspect.log') == expected,
                'Candidate collection lacks the exact four NullMoth components')
        inspected = (JOB / 'candidate-inspect.log').read_text().lower().splitlines()
        for name in ['NVRM', 'NVAccel', 'NVRMFB', 'NVRMAGDC']:
            binary = repo / (name + '.kext') / 'Contents/MacOS' / name
            uuid_text = subprocess.check_output(['/usr/bin/dwarfdump', '--uuid', str(binary)],
                                                text=True, timeout=15)
            uuid = re.search(r'UUID: ([0-9A-F-]+) \(x86_64\)', uuid_text)
            require(uuid is not None, 'Missing x86_64 UUID: ' + name)
            require(matching_uuid(inspected, 'com.nullmoth.' + name, uuid.group(1)),
                    'Collection contains wrong binary UUID: ' + name)
        require(new_kc.stat().st_size > 0, 'Empty candidate collection')
        preflight(require_new_job=False)
        require(snapshot(Path('/Library/Extensions')) == before,
                'Installed extension repository changed during collection build')
        new_kc.chmod(0o744)
        state = {'candidate_binary_sha256': CANDIDATE_HASH,
                 'original_binary_sha256': ORIGINAL_HASH,
                 'candidate_collection_sha256': sha(new_kc),
                 'original_collection_sha256': sha(KC),
                 'status': 'collection_validated_before_publication',
                 'performance_improvement': 'NOT VERIFIED'}
        (JOB / 'status.json').write_text(json.dumps(state, indent=2) + '\n')
        publish(TARGET, staged, KC, new_kc, JOB)
        state['status'] = 'installed_on_disk_pending_reboot'
        (JOB / 'status.json').write_text(json.dumps(state, indent=2) + '\n')
        print('Installed only NVRMFB and its matched auxiliary collection. Originals preserved in ' + str(JOB), flush=True)
    finally:
        owner = LOCK / 'owner'
        if owner.is_file():
            owner.unlink()
        LOCK.rmdir()
    if a.reboot:
        print('Approved reboot scheduled in one minute. No live acceleration improvement is claimed.', flush=True)
        subprocess.run(['/sbin/shutdown', '-r', '+1'], check=True)


if __name__ == '__main__':
    main()
