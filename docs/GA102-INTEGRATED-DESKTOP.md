# Integrated desktop candidate — installation checkpoint

Production source is verified diagnostics `92fbfd7ced2f752d105f95242da854c9bbe7d46f`.
The modified NVMTL plugin, translator and complete source NVK were actually built
and installed on Darwin x86_64 / macOS 15.8.1 / RTX 3080 Ti. Fresh ordinary Metal
processes load the three candidate binaries with matching mapped Mach-O UUIDs.
**WindowServer still maps the original binaries before restart. Desktop improvement
is not established. This checkpoint is not ENDGAME completion.**

## Production composition

NVMTL remains Apple's production `NVMTLDevice` bundle, with its release constructor
and policy intact. Metal/AIR libraries use its bundled translator and existing AIR
LLVM/zstd runtime. NVMTL opens source NVK directly at its production canonical path.
NVK's Darwin NVRM backend talks to the existing NVIDIA 610.57.04 RM/IOKit interfaces;
NVAccel, NVRMFB and NVRMAGDC retain their existing surface/display roles. Their
working binaries and kernel collections are unchanged.

Only `NVMTLDriver.bundle` and `nvmtl/libvulkan_nouveau.dylib` were published. Existing
NVIDIAShared, media libraries, AIR runtime, allow-list, firmware and driver
configuration are preserved. No synthetic NVIDIA implementation was substituted.
Full NVRM rebuilding still lacks the authenticated Darwin vendor port/build recipe,
`compile_cmds.sh`, `libnvkernel.a`, `libnvkms.a` and complete release link recipe.
Those missing inputs do not block this narrower qualified user-space path.

Mesa is pinned to `17ca6174dcc6cb22059ac343bc29f8af7800f42e`, with the complete
qualified macOS patch and real 610.57.04 headers. Retained real Mesa CLC/LLVM 19.1.7
tools supplied the native build; one build job was used. A fresh build against SDK
zlib 1.2.12 removes the former MacPorts runtime dependency. NVK links only macOS
system libraries/frameworks. Its RTLD_NOW/export/interface-7 and cold/reused-cache
physical GPU boundary gates pass, including actual selected ICD image checks.

The production plugin uses release O1, SDK 15.5 and Apple clang 17; translator uses
Rust 1.99.0, opt3/codegen16/incremental off and one job. There is no diagnostic
namespace or performance instrumentation in installed production artifacts.

## Packaging and recovery

Standard bundle signing rejected executable license text under `MacOS/air-runtime`.
The installed original also failed strict resource-signature verification. The
candidate relocates the three unchanged license texts to `Resources/air-runtime`
with data-file permissions, preserves all runtime binary bytes, and passes strict
bundle signature verification. NullMoth attribution and licensing remain intact.

The exact working stack/configuration/firmware, ownership/modes/flags, all relevant
kernel collections, and current SSD/connected USB EFI contents are backed up
privately. Independent copies were byte-hash verified. The owner confirmed tested
independent Recovery/current Data-volume access and retains control of that route.
The new user-space rollback script requires the exact current Data-volume UUID
and verifies the archive/binary hashes. Its syntax passes; execution in Recovery
has not been observed. It restores only NVMTL/NVK and needs no collection rebuild.
No security setting or EFI content was changed.

An actual in-OS rollback restored both original targets byte-for-byte, and a fresh
ordinary Metal process completed correct GPU work on the restored driver. The
candidate was then reinstalled and its fresh-process mapped images rechecked.
This verifies the live user-space rollback path; the new Recovery script remains
unexecuted.

The installer preserves original targets, uses the existing installer lock and
rolls back synchronous publication failures. Tests exercise all five publication
failure boundaries. Two target renames are **not crash-atomic**; independent
backups cover process death/power loss. Existing processes retain old mapped
images until restart. Original restricted flags stay in the recovery archive;
ordinary candidate copying preserves contents/modes without trying to set system
flags on build artifacts.

## Measurements and limits

The matched original-driver baseline uses 1920×1080, eight blended draws and a
640×360 window on the unchanged 3440×1440/60 Hz desktop. Both runs complete all
120 commands without errors. Steady observed presentation timing, ms:

| Run | p50 | p95 | p99 | maximum | >25 ms |
|---|---:|---:|---:|---:|---:|
| Original 1 | 16.686 | 17.435 | 17.471 | 17.536 | 0 |
| Original 2 | 16.729 | 17.322 | 17.489 | 32.673 | 1 |

The second run fails the existing pacing gate; the requested third run was not
launched. A prior compiler-overlap trace is retained as a diagnostic failure and
excluded from this baseline. These are public API presentation observations, not
physical scanout measurements or everyday application compatibility coverage.

Installed-candidate fresh processes pass compute with exact mapped-image UUIDs,
eight serialized two-process IOSurface roundtrips (262,144 checked bytes), and
sampled full-resolution alpha composition in four private/IOSurface 16/32-layer
cases. These checks establish production path loading and scoped correctness;
they do not establish a candidate WindowServer result or desktop speedup.

111 standard-library Python tests pass. Remaining limitations include the qualified
uniform-wave allocation p95 trade-off, bulk pitched-import preparation regression,
uncertain-resource quarantine, previously retired framebuffer boot failure, and
unresolved screenshot-versus-physical opacity/blur. The existing successful
isolated publication/coalescing results are in `GA102-ENDGAME-ENCORE.md`; they are
not recast as desktop benefits.

Normalized installation hashes, UUIDs and baseline timing evidence:
[ga102-integrated-installation.json](evidence/ga102-integrated-installation.json).
Private recovery media, configuration, images, binaries and raw logs stay outside Git.

## NEXT-STEPS

After the authorized restart, first run:

```sh
/Users/waqy/Developer/ga102-integrated-session/active-metal-images
```

Verify its mapped UUIDs against the evidence and obtain root `lsof`/`vmmap` proof
that WindowServer now maps the candidate file inodes, with all original kernel
UUIDs unchanged. Then run the identical production presentation workload:

```sh
python3 -S tools/ga102_run_metal.py ga102_metal_present --repeat 3 --render-size 1920x1080 --composite-layers 8 --result-json /Users/waqy/Developer/ga102-integrated-session/candidate-postboot-presentation.json
```

Continue ordinary application/sustained composition and capture correctness
validation. Retain failures and match workload/cache/session state before any
performance claim. Decide whether to keep the candidate only from post-restart
correctness, stability and desktop evidence; that decision is pending.
