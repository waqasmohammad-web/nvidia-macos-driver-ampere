#!/usr/bin/env python3
"""Restore the pinned pre-test files on disk; never reboot or load a kext."""
import argparse
import json
import os
from pathlib import Path
import subprocess

import ga102_deploy_framebuffer as deploy

ORIGINAL_KC = '362eb218919f7783440035cf19f02fb05b73a749836fa942e8a9b90f1d973526'
CANDIDATE_KC = 'e1b211830911b6cef21f2aec310a46a61d3bcdce69149ef1f1caf8f2909aed6d'


def preflight():
    # Darwin SF_RESTRICTED. Check both the directory and collection before any
    # bundle move; root authentication alone cannot bypass SIP protection.
    for path in (deploy.KC.parent, deploy.KC):
        deploy.require(not (getattr(path.stat(), 'st_flags', 0) & 0x00080000),
                       'Kernel collection is SIP-restricted; use USB Recovery rollback. '
                       'Do not disable SIP or retry this live helper.')
    deploy.bundle(deploy.JOB / 'OriginalNVRMFB.kext', deploy.ORIGINAL_HASH)
    deploy.require(deploy.sha(deploy.JOB / 'OriginalAuxiliaryKernelExtensions.kc')
                   == ORIGINAL_KC, 'Original collection hash mismatch')
    deploy.bundle(deploy.TARGET, deploy.CANDIDATE_HASH)
    deploy.require(deploy.sha(deploy.KC) == CANDIDATE_KC,
                   'Installed collection changed; refuse unqualified rollback')
    deploy.manifest(deploy.USB / 'BASE-SYSTEM-SHA256SUMS', Path('/'))
    deploy.manifest(deploy.USB / 'UNCHANGED-DRIVER-SHA256SUMS', Path('/'))
    deploy.require(not (deploy.JOB / 'Rollback').exists(),
                   'Rollback directory exists; inspect before retrying')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    preflight()
    print('PASS: original backups, candidate files and unchanged dependencies', flush=True)
    if args.check:
        return
    deploy.require(os.geteuid() == 0, 'Run in Terminal with sudo; no password through chat')
    deploy.LOCK.mkdir()  # Never bypass another installer lock.
    try:
        work = deploy.JOB / 'Rollback'
        work.mkdir(mode=0o755)
        staged = work / 'StagedOriginal.kext'
        subprocess.run(['/usr/bin/ditto', str(deploy.JOB / 'OriginalNVRMFB.kext'),
                        str(staged)], check=True)
        staged_kc = work / 'StagedOriginal.kc'
        subprocess.run(['/usr/bin/ditto',
                        str(deploy.JOB / 'OriginalAuxiliaryKernelExtensions.kc'),
                        str(staged_kc)], check=True)
        staged_kc.chmod(0o744)
        deploy.bundle(staged, deploy.ORIGINAL_HASH)
        deploy.require(deploy.sha(staged_kc) == ORIGINAL_KC, 'Staged collection mismatch')
        deploy.bundle(deploy.TARGET, deploy.CANDIDATE_HASH)
        deploy.require(deploy.sha(deploy.KC) == CANDIDATE_KC, 'Collection changed during staging')
        # The tested publication routine preserves the pre-rollback candidate in
        # Rollback/Original*, while the pre-test backups remain untouched in JOB.
        deploy.publish(deploy.TARGET, staged, deploy.KC, staged_kc, work)
        deploy.bundle(deploy.TARGET, deploy.ORIGINAL_HASH)
        deploy.require(deploy.sha(deploy.KC) == ORIGINAL_KC, 'Restored collection mismatch')
        state = json.loads((deploy.JOB / 'status.json').read_text())
        state['status'] = 'original_restored_on_disk_boot_not_verified'
        state['candidate_boot_result'] = 'FAIL: user-reported stuck boot; USB boot recovered OS'
        (deploy.JOB / 'status.json').write_text(json.dumps(state, indent=2) + '\n')
        print('PASS: original framebuffer and collection restored on disk; failed files preserved.')
        print('No reboot scheduled. Normal internal boot remains NOT VERIFIED.')
    finally:
        deploy.LOCK.rmdir()


if __name__ == '__main__':
    main()
