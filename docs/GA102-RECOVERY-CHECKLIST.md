# GA102 framebuffer experiment: recovery preparation

This checklist and USB backup prepare for a future, separately approved live
test. They do not authorize installation, reboot, driver unloading, a macOS
reinstall or graphics-service changes. EFI, OpenCore, SIP, login security,
display mode and refresh rate must remain unchanged.

## What the USB backup contains

- The authentic original NullMoth 1.11.0 installer archive, verified against the
  published release digest.
- `rollback-NVRMFB.tar.gz`: original framebuffer bundle, preserving its binary,
  plist, directory structure and required root/wheel ownership metadata.
- `AuxiliaryKernelExtensions.kc`: a read-only backup of the pre-test installed
  auxiliary kernel collection. Inspection confirmed all four NullMoth kexts.
- A private copy of the current `nvrm610.conf`; the installed configuration
  differs from the release default and must not be overwritten by a test.
- Hash manifests for the USB files, original framebuffer, unchanged driver
  components and boot/system kernel collections.

No experimental driver binary is included in this USB recovery folder. Do not
run the original installer's `install.sh` as a shortcut: it changes more than
the single framebuffer and may perform operations outside our authorization.

## Before approving any live test

1. Preserve this USB and the complete backup folder. Keep an additional local
   copy. Verify `SHA256SUMS` from inside the backup folder.
2. Confirm the USB boots its existing macOS Recovery/installer entry and can
   mount the *current* Sequoia System/Data volume group. Prior installation with
   this USB proves it booted then, not that current recovery access works now.
   FileVault is disabled according to the user. Do not erase or reinstall.
3. Confirm Recovery Terminal can read the backup and has write access to the
   correct Data volume. Record its actual mounted path; names can gain numeric
   suffixes. System and Data volumes must belong to the same APFS volume group.
4. Immediately before any installation, recheck the current installed binaries
   and auxiliary/boot/system collections against the saved manifests. If an OS
   update or driver change occurred, regenerate the backup before proceeding.
5. Obtain explicit approval for the single-framebuffer replacement, any required
   privileged collection build and reboot. No hot swap is permitted.

## If an approved test cannot reach a usable desktop

The following is a manual recovery procedure, **not an executable script**.
Execute it only during separately approved recovery. A boot test, access check,
or rollback has NOT been performed by the agent.

1. Boot the existing USB through the machine's normal boot selection, select
   Recovery/installer and open Utilities → Terminal. Do not start installation.
2. Use `diskutil apfs list` and `ls /Volumes` to identify and, if necessary,
   mount the Sequoia System and Data volumes. Do not guess disk identifiers.
   Confirm `/Library/Extensions` on the selected Data volume contains the four
   expected NullMoth bundles. Recovery Terminal normally runs as root; check
   `id -u` and stop if it is not `0` rather than changing security settings.
3. Set these variables to the actual mounted paths. The strings below are
   placeholders and must be replaced:

   ```sh
   USB='/Volumes/OPENCORE/GA102-Recovery'
   SYSTEM='/Volumes/ACTUAL-SEQUOIA-SYSTEM-VOLUME'
   DATA='/Volumes/ACTUAL-SEQUOIA-DATA-VOLUME'
   ```

4. Verify the backups and the unchanged dependency set:

   ```sh
   (cd "$USB" && shasum -a 256 -c SHA256SUMS)
   (cd "$SYSTEM" && shasum -a 256 -c "$USB/BASE-SYSTEM-SHA256SUMS")
   (cd "$DATA" && shasum -a 256 -c "$USB/UNCHANGED-DRIVER-SHA256SUMS")
   tar -tzf "$USB/rollback-NVRMFB.tar.gz"
   ```

   Every hash must match. Archive members must stay inside `NVRMFB.kext/`.
   If any dependency or system collection differs, stop: this cached rollback
   is not qualified for a changed OS or mixed driver installation.

5. Before writing anything, preserve the failed framebuffer and collection in
   a new directory outside `Library/Extensions`. For example, use
   `$DATA/GA102-Before-Rollback`; refuse to overwrite an existing directory.
   Copy the full NVRMFB bundle and current auxiliary collection into it using
   `ditto`. Do not delete either live file first.
6. With explicit rollback approval, restore the saved original bundle and
   original auxiliary collection:

   ```sh
   tar -xpf "$USB/rollback-NVRMFB.tar.gz" -C "$DATA/Library/Extensions"
   chown -R root:wheel "$DATA/Library/Extensions/NVRMFB.kext"
   cp "$USB/AuxiliaryKernelExtensions.kc" \
      "$DATA/Library/KernelCollections/AuxiliaryKernelExtensions.kc"
   chown root:wheel "$DATA/Library/KernelCollections/AuxiliaryKernelExtensions.kc"
   chmod 0744 "$DATA/Library/KernelCollections/AuxiliaryKernelExtensions.kc"
   (cd "$DATA" && shasum -a 256 -c "$USB/ORIGINAL-FRAMEBUFFER-SHA256SUMS")
   shasum -a 256 "$DATA/Library/KernelCollections/AuxiliaryKernelExtensions.kc"
   ```

   Compare the last hash with the saved USB collection hash in `SHA256SUMS`.
   The recorded original collection mode on this system is 0744; FAT32 does
   not preserve Unix ownership/modes, hence the explicit restoration above.
   These commands change only the approved framebuffer/auxiliary collection
   and their required ownership; they do not alter SIP or other security policy.
7. On this Intel installation, the inspected original installer publishes the
   auxiliary collection at `Library/KernelCollections/AuxiliaryKernelExtensions.kc`.
   Restoring the saved collection is the proposed exact-state rollback, avoiding
   an unverified Recovery/KDK build procedure. This is technically justified by
   the installer and matching baseline; actual boot recovery remains untested.
   Do not delete collections, run panic-medic, reset NVRAM, modify Preboot/EFI,
   bypass approval checks or improvise a reinstall if restoration fails.
8. Only after every restore/hash check succeeds and reboot is explicitly
   approved, restart into the existing Sequoia installation. Confirm the
   original desktop returns. If it does not, stop and preserve the recovery
   state for review.

## Acceptance state

Backup content and hash verification: PASS once the USB preparation completes.
USB previously booted the installer: user-confirmed.
Current Sequoia recovery mount/write access and actual rollback boot: NOT VERIFIED.
Live candidate installation and performance improvement: NOT VERIFIED.
