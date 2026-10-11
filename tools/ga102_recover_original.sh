#!/bin/sh
# Run from USB Recovery Terminal with the verified System and Data mount paths.
# Never disables security, changes EFI, loads a kext, or reboots automatically.
set -eu
fail() { echo "STOP: $*" >&2; exit 1; }
# Recovery omits utilities available on the desktop. Detect every dependency
# before backing up or changing files; command presence is not boot validation.
for utility in id dirname stat diskutil plutil shasum cut tar mktemp ditto cp chown chmod; do
    command -v "$utility" >/dev/null 2>&1 || fail "Required Recovery utility missing: $utility. No files changed."
done
[ "$#" -eq 2 ] || fail 'Usage: sh RESTORE-ORIGINAL.sh /Volumes/SYSTEM /Volumes/DATA'
SYSTEM=$1
DATA=$2
USB=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
[ "$(id -u)" = 0 ] || fail 'Run in Recovery Terminal as root.'
case "$SYSTEM" in /Volumes/*) ;; *) fail 'System must be a mounted volume under /Volumes.' ;; esac
case "$DATA" in /Volumes/*) ;; *) fail 'Data must be a mounted volume under /Volumes.' ;; esac
[ "$SYSTEM" != "$DATA" ] || fail 'System and Data paths must differ.'
SYSTEM_GROUP=$(diskutil info -plist "$SYSTEM" | plutil -extract APFSVolumeGroupID raw -o - -)
DATA_GROUP=$(diskutil info -plist "$DATA" | plutil -extract APFSVolumeGroupID raw -o - -)
[ -n "$SYSTEM_GROUP" ] && [ "$SYSTEM_GROUP" = "$DATA_GROUP" ] || fail 'System/Data APFS volume groups differ.'
[ -d "$DATA/Library/Extensions/NVRMFB.kext" ] || fail 'Target framebuffer missing.'
# Refuse the current live Library even when reached through an alternate mount.
[ "$(stat -f '%d:%i' "$DATA/Library")" != "$(stat -f '%d:%i' /Library)" ] || fail 'Refusing the active OS. Boot USB Recovery first.'
(cd "$USB" && shasum -a 256 -c SHA256SUMS) || fail 'USB backup verification failed.'
(cd "$SYSTEM" && shasum -a 256 -c "$USB/BASE-SYSTEM-SHA256SUMS") || fail 'Wrong System volume or changed OS.'
(cd "$DATA" && shasum -a 256 -c "$USB/UNCHANGED-DRIVER-SHA256SUMS") || fail 'Wrong Data volume or changed driver dependencies.'
KC="$DATA/Library/KernelCollections/AuxiliaryKernelExtensions.kc"
[ -f "$KC" ] || fail 'Target auxiliary collection missing.'
EXPECTED_KC=362eb218919f7783440035cf19f02fb05b73a749836fa942e8a9b90f1d973526
[ "$(shasum -a 256 "$USB/AuxiliaryKernelExtensions.kc" | cut -d ' ' -f 1)" = "$EXPECTED_KC" ] || fail 'Original collection is not the pinned backup.'
# The archive was prepared locally with exactly the original framebuffer files.
tar -tzf "$USB/rollback-NVRMFB.tar.gz" | while IFS= read -r member; do
    case "$member" in NVRMFB.kext|NVRMFB.kext/*) ;; *) fail 'Unexpected archive member.' ;; esac
    case "$member" in *../*|/*) fail 'Unsafe archive path.' ;; esac
done
SAVE=$(mktemp -d "$DATA/GA102-Recovery-Restore.XXXXXX")
ditto "$DATA/Library/Extensions/NVRMFB.kext" "$SAVE/BeforeRestore-NVRMFB.kext"
ditto "$KC" "$SAVE/BeforeRestore-AuxiliaryKernelExtensions.kc"
# Restore collection first: if protection rejects it, do not change the bundle.
cp "$USB/AuxiliaryKernelExtensions.kc" "$KC" || fail 'Collection write rejected. Do not boot the internal disk; inspect Recovery security state.'
chown root:wheel "$KC"
chmod 0744 "$KC"
tar -xpf "$USB/rollback-NVRMFB.tar.gz" -C "$DATA/Library/Extensions"
chown -R root:wheel "$DATA/Library/Extensions/NVRMFB.kext"
(cd "$DATA" && shasum -a 256 -c "$USB/ORIGINAL-FRAMEBUFFER-SHA256SUMS") || fail 'Restored framebuffer hash mismatch.'
[ "$(shasum -a 256 "$KC" | cut -d ' ' -f 1)" = "$EXPECTED_KC" ] || fail 'Restored collection hash mismatch.'
echo 'PASS: original framebuffer and collection restored and hash-verified.'
echo 'No reboot performed. Internal boot and desktop stability remain NOT VERIFIED.'
