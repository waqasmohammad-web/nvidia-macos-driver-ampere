# GA102 desktop acceleration investigation

Status: post-reinstall accelerated stack verified; explicit isolated user-space
plugin execution established; texture-transfer queue race correction and fresh
desktop baseline in progress, 2026-10-12. Installed desktop improvement unresolved.
Branch: `dev/ga102-3080ti-diagnostics`. Starting revision: `c52e088`.

## Current progress at a glance

- **PASS, installed-runtime scope:** compute/render smoke, bounded composite
  pixels, cross-process synthetic IOSurface round trips, shared-event ordering,
  and changing GPU patterns. These do not prove complete desktop acceleration.
- **PASS, previously sampled active-window scope:** three isolated timer runs
  had presentation p95 17.266–17.417 ms and zero intervals above 25 ms. These
  predate the new raw-timestamp/target-mode gate; do not retroactively label them
  full-suite PASS. Core Animation animation phases increased WindowServer CPU
  to about 44–45% of one core, with clean flip counters; causality is unresolved.
- **PASS, owned-window capture scope:** authorized Python broker captured and
  checked 36/36 changing frames over three runs after explicit sRGB tagging.
  GPU pixels, sampled visibility, ordered timestamps and clean display counters
  also passed. Screenshots do not verify physical scanout or desktop smoothness.
- **NOT VERIFIED:** physical scanout and desktop improvement remain unverified.
  After a bounded window-readiness check, timer and display-link modes each have
  three steady-state pacing PASS runs. Acquisition waits vary with scheduling
  phase; a reproducible early 33 ms interval is retained in startup evidence.
  No ongoing desktop-performance defect or installed-driver fix is established.
- **BUILD UPDATE:** the missing `nvkms.h` was a checked-in upstream header,
  not a generated file. The full framebuffer now compiles and links. Complete
  release reconstruction still lacks the Darwin NVIDIA core build recipe,
  archives and remaining user-space dependencies; see build remediation below.
  Protected WindowServer stack access remains blocked. Capture works in the broker process.
  No permission request, privilege escalation or stub replacement was used.
- **SOURCE VALIDATED only:** shader-cache helper and framebuffer completion
  accounting, within the build/test limits documented below. No changed driver
  has been installed. Existing synchronization waits are preserved.
- **Latest safe work:** isolated capture broker, explicit color-space matching,
  private source snapshots and scoped acceptance; per-frame submission traces and
  a two/three-drawable startup comparison and owned Core Animation reference
  capture and bounded SCStream reference IDs; 37 Python tests pass.
  Objective remains open.

## Scope and operating constraints

RTX 3080 Ti / GA102 (`10de:2208`), Intel i9-12900K, MSI Z690, OpenCore,
macOS Sequoia 15.8.1. Preserve the established 3440 × 1440 @ 60 Hz baseline.
No installation, reboot, mode/refresh change, EFI/OpenCore/SIP change, or driver
configuration write is part of this audit. No sudo has been used. Existing Git
history and the uninstalled shader-cache proposal are preserved.
The current live-development restriction is absolute: no reboots, logouts,
WindowServer/graphics-service restarts, disabling login security, hot-swapping
loaded kexts or changing the active framebuffer. Build artifacts stay outside
active graphics-system locations. Before executing any experimental component,
review its initialization and isolation path; source-only candidates that cannot
be safely isolated remain **AWAITING LIVE VALIDATION**. Broader filesystem access
does not relax these operational restrictions.

Evidence labels used below:

- **Observed:** read from the current machine during this audit.
- **Recorded:** earlier results in `RTX3080TI-GA102-BASELINE.md`; not rerun here.
- **Source:** behavior in the checked-out code; installed-binary equivalence
  still needs verification.
- **Hypothesis:** a candidate explanation requiring measurements.

## Milestone 1 — architecture and initial runtime evidence

### Current conclusion

The desktop cannot presently be described as wholly unaccelerated. Existing
tests demonstrate small correct GPU workloads, and live kernel counters show
tens of thousands of successful asynchronous zero-copy display flips. This
does **not** establish consistently smooth frames or acceptable input latency.
No root cause for subjective sluggishness has been demonstrated yet.

The immediate priority is to measure rendering, CPU submission, resource
transfers, and presentation separately. The shader-cache warning is a proven
cache failure in earlier test processes, not a proven explanation for ongoing
desktop sluggishness.

### Architecture map

| Stage | Source and entry points | Responsibility / audit concern |
|---|---|---|
| PCI and RM startup | `kexts/NVRM/NVRM.cpp`: `NVRM::start`, `readBARs`, `autoGo`, `go` | PCI ownership, BAR placement, boot hold, RM/GSP startup and display-stack arming |
| NVIDIA OS/firmware layer | `kexts/NVRM/os-xnu.cpp`, `os-xnu2.cpp`: `nv_xnu_fw_path`, `nv_get_firmware` | XNU adaptation of NVIDIA 610.57.04; GA10x firmware selection and loading |
| Vulkan backend | `nvk/nvk-macos.patch`, `nvk/MESA_BASE` (`17ca6174`) | Mesa NVK + NAK, custom NVRM memory and execution contexts instead of Linux DRM |
| Metal device/backend | `plugin/NVMTLDevice.m`, `plugin/nvmtl_vk.c`: `nvmtl_vk_initialize`, `nvmtl_vk_queue_create` | Metal API objects, Vulkan initialization, allocation and submission |
| Shader compilation | `plugin/NVMTLLibraryLoad.m`, `translator/wrapper/src/lib.rs`, `translator/translator/`; optional `NVMTLVendorCompiler.m` | Apple AIR → SPIR-V → NAK/NVIDIA code; separate AIR/SPIR-V and Mesa caches; optional vendor compiler path |
| Command completion | `plugin/NVMTLEventSync.m`: `nvmtlSubmitWithEvents`, `nvmtl_pump_buffers`, `nvmtlAdvancePart` | Queue reservations, submit-ahead, completion waits, resource synchronization and event publication |
| Shared surfaces | `NVMTLDevice.m`: `nvmtl_surface_image_create`; `NVMTLObjects.m`: `nvmtlSurfaceIn/Out`; `kexts/NVRM/accel/nvrm-accel.cpp`: surface-share/pageoff code | Import IOSurface VRAM, track which copy is current, transfer when sharing is unavailable |
| WindowServer display pipe | `kexts/NVRM/accel/nvrm-accel.cpp`: `NVDisplayPipe::performTransaction`, `nvAccelIopFlip`, `nvAccelIopAsyncRun` | Scan out shared VRAM, or fall back to CPU copying into the scanout buffer |
| Framebuffer / pacing | `kexts/NVRMFB/fb/nvrm-fb.cpp`: `submitConfig`, `flipToMemory`, `hwVblIntr`, `hwVblDeliver`, `vblFire` | NVKMS primary-surface flips, completion polling, hardware vblank with timer fallback |
| Display policy | `kexts/NVRMAGDC/` | Apple's graphics-device-control integration |

The tree also contains older/nested framebuffer and AGDC sources under
`kexts/NVRM/fb` and `kexts/NVRM/agdc`. The documented release paths are
`kexts/NVRMFB` and `kexts/NVRMAGDC`; do not patch a duplicate by assumption.
The paired modeset completion archive is described in
`kexts/NVRM/patches/README.md`.

### Previously recorded evidence

- Four kexts loaded: NVRM, NVAccel, NVRMFB, NVRMAGDC.
- Metal compute smoke test returned `[2, 4, 6, 8]` correctly.
- Offscreen 16 × 16 render returned RGBA `[64, 127, 191, 255]` correctly.
- Mesa could not create its default shader-cache directory. A process-local
  `MESA_SHADER_CACHE_DIR` override removed that warning; the alternate cache
  subsequently contained 9 files / approximately 2 MB.
- The source cache-path proposal at `8516ac8` has not been built or installed.
  There is no cold/warm timing comparison and no evidence yet about
  WindowServer's cache directory or cache hits.
- NVK reported BAR1 8192 MB / VRAM 12288 MB, mapped-local allocations placed in
  system RAM, a copy-engine context fallback, and sector-promotion status 0x56.

### Passive checks completed on the current machine

Observed OS: **15.8.1 (24H32), x86_64**. CPU readback: **12th Gen Intel Core
i9-12900K**. `system_profiler` identifies RTX 3080 Ti, PCIe x16, 12 GB, and
Metal support. That report alone is not an execution or throughput test.

First live counter snapshot (boot/session cumulative; individual reads are
not atomic):

| Counter (`debug.` prefix omitted) | Value |
|---|---:|
| `nvaccel_iop`, `nvaccel_iop_flip`, `nvaccel_iop_async` | 1, 1, 1 |
| `nvaccel_heads_published`, `nvaccel_heads_registered`, `nvaccel_heads_piped` | 1, 1, 1 |
| `nvaccel_iop_ok` | 51,270 |
| `nvaccel_iop_flips`, `nvaccel_iop_async_flips` | 51,268 each |
| `nvaccel_iop_fail`, `nvaccel_iop_async_refused`, `nvaccel_iop_async_drop` | 0 each |
| `nvaccel_iop_flip_lock` | 1 |
| `nvaccel_iop_flip_novram`, `nvaccel_iop_flip_stale`, `nvaccel_iop_flip_refused` | 0 each |
| `nvrmfb_flip_n` | 51,268 |
| `nvrmfb_flip_us_sum`, `nvrmfb_flip_us_max` | 657,375,044 µs; 18,716 µs |
| `nvrmfb_flip_latch_timeouts` | 0 (coverage still under audit) |
| `nvrmfb_vram_budget_bytes`, `nvrmfb_vram_mapped_bytes` | 4,294,967,296; 388,890,624 |

**Interpretation:** zero-copy asynchronous scanout is actively exercised;
persistent CPU scanout copying is not supported by this snapshot. The
approximately 12.82 ms average flip call includes completion/vsync waiting
inside `submitConfig`; it is not GPU render time or an FPS measurement.
The mapped allocation count is about 371 MiB of a 4 GiB grant budget, not
total GPU memory consumption. Counter semantics and installed source identity
must be checked before making stronger claims.

Sandbox restrictions initially blocked sysctl. The named read-only counters
were then read with approved execution outside the sandbox. I/O Registry and
loaded-kext refresh attempts inside the sandbox failed; these failures are
diagnostic access limitations, not evidence of driver failure. Further passive
collection is in progress.

### Highest-priority hypotheses and next checks

1. **WindowServer serialization / frame pacing.** Source
   `NVMTLCommandBuffer::commitAndWaitUntilSubmitted` explicitly waits for full
   completion in WindowServer because NVAccel cannot order a display swap
   after an NVK fence. Separately, `submitConfig` polls display completion in
   1 ms increments. Measure CPU encode/commit/wait time, GPU time, and actual
   presentation intervals. Do not remove the wait without a replacement
   render-fence-to-scanout ordering mechanism.
2. **Memory placement / transfers.** The recorded `LOCAL+mapped → system RAM`
   warning is explained by `nvrm_local_map_stays_vram` and
   `nvkmd_nvrm_alloc_tiled_mem` in the NVK patch. The VRAM path requires an
   explicit override **and** BAR1 covering all VRAM; 8 GiB does not cover this
   card's 12 GiB. This is not proof that private textures or imported IOSurfaces
   use system RAM. Compare bounded shared/managed/private workloads and count
   copy bytes before considering placement changes. No BAR/EFI changes.
3. **Cold compilation / cache behavior.** Time device, library and pipeline
   creation separately from repeated execution. Use fresh test-owned cache
   directories for cold/warm runs without deleting production caches. A cache
   fix needs evidence for service identities as well as the interactive user.
4. **Copy-engine compatibility.** `nvkmd_nvrm_create_exec_ctx` deliberately
   retries failed copy-engine creation on a graphics channel; the patch cites
   a GA104 class/engine mismatch. GA102's exact failed RM call still needs
   tracing. The plugin requests one graphics+compute Vulkan queue, so the
   startup warning alone does not establish that normal Metal work uses a
   separate copy queue or loses measured overlap.
5. **Vblank / resource pressure.** Verify hardware-vblank registration and
   delivery, timer fallback, allocation failures and interval deltas. Current
   flip success does not prove uniform vblank delivery or low input latency.

### Proposed diagnostic sequence and acceptance criteria

1. Finish passive provenance, startup, framebuffer timing and counter
   collection; record missing/denied data explicitly. Confirm that current
   transactions continue to advance with no new refusals or drops.
2. Add a bounded standalone offscreen benchmark with separate CPU/GPU timings,
   warmup and p50/p95/p99 results; test representative texture sizes and memory
   storage modes. Validate pixels/buffer data, select the intended NVIDIA
   device, and use an external process deadline as well as callback deadlines.
3. Add an IOSurface producer/consumer correctness test, including repeated
   writes and visibility across processes. This closes a gap left by the
   existing offscreen test.
4. Add a short ordinary windowed CAMetalLayer presentation probe at the
   existing mode. Record presented timestamps separately from command-buffer
   completion; do not equate a callback or CVDisplayLink tick with physical
   scanout. Compare a continuously animated test with a separately recorded
   idle baseline; idle desktops need not submit 60 new frames per second.
5. For a controlled 60 Hz animation, target presentation intervals near
   16.67 ms, quantify intervals above 25 ms (late-frame indicator), and require
   no new display errors. Use at least three repeat runs before attributing a
   change; an initial optimization target is ≥10% improvement in the affected
   p95 metric with correct output and no pacing regression. These are proposed
   acceptance targets, not results.

At milestone 1, no driver implementation had been modified. Proposed
implementation changes will be explained with their evidence, rollback and
acceptance test before they are made or pushed.

## Milestone 2 — startup verified and bounded offscreen measurements

### Startup and presentation observations

With ordinary user access outside the tool sandbox, I/O Registry reports:

```text
nvrm-autogo: up
nvrm-autogo-settle-ms: 500
nvrm-boot-hold: display armed
nvrm-display: heads 0x1 accel 4 agdc 1 k5 1 iop 1
nvrm-flip: on
BAR0: 0x81000000 + 0x1000000
BAR1: 0x7c00000000 + 0x200000000 (8 GiB)
BAR2: 0x7e00000000 + 0x2000000
```

These are GPU PCI memory addresses, not personal machine identifiers. The
recorded boot raster is approximately 59.973 Hz. The framebuffer trace says
hardware vblank registered on head 0 after 60 mode ticks and delivered its
first real VBL, period 16,674,276 absolute-time units. Registration/delivery at
startup does not establish the current jitter distribution or continuous
absence of timer fallback. Unsupported `dpir` and `hdci` interrupt requests are
also recorded; there is no evidence yet tying them to responsiveness.

`kmutil showloaded --list-only` successfully refreshed all four loaded kexts.
The earlier sandboxed failure was an access restriction. The GA10x firmware
files exist at the documented 610.57.04 location (`gsp_ga10x.bin`, 84,310,168
bytes; `ucodes_ga10x.bin`, 31,744 bytes). Runtime startup and working execution
support successful bring-up; firmware integrity and GSP performance telemetry
have not been independently qualified.

**Important diagnostic correction:** the current NVRMFB source declares
`gFlipLatchWaits`, `gFlipLatchTimeouts`, and `gFlipLatchMaxUs` but has no sites
that update them. The legacy sysctl names remain exported. Therefore a zero
`nvrmfb_flip_latch_timeouts` is not evidence of zero completion stalls in this
source. `submitConfig` uses a separate completion-query polling path and a
fault latch. Future instrumentation must cover that actual path.

### Installed-binary provenance

All inspected bundle versions are `0.1`, which does not identify package
release 1.11.0. Installed-file SHA-256 values were recorded for reproducibility
(not proof that disk files equal currently resident binaries):

| Installed component | SHA-256 |
|---|---|
| NVMTLDriver | `853cc88e3e414815384d7d60bc01dd4d5cb67708c20d10472f59506a60a9c5cb` |
| NVRM | `4c74eb5a5be05e8819f2d8bd6ec41e09978b6ef9dccbd06de54f4ac927c32d96` |
| NVAccel | `ed6b1fbf360d7b44a2aa6a037f52036c8fc22a16393a9ddf932dfc4357d1e681` |
| NVRMFB | `a2a3cf961df1aae872d500142b8c146ecd660a369f364d843f42c3fb4bd21e71` |
| NVRMAGDC | `270f9ef9ac9d2482689ed4d63d422e705e439509d0e3b62fc6bc96fdc9e693ed` |
| NVK library | `372c257b551cc0c4591239003151f6ac3cb80a947765b5639acfdb5a80e74ebc` |

The installed plugin contains the old `has no writable HOME` cache diagnostic
and lacks the new per-user cache diagnostic. This independently supports the
baseline statement that the experimental cache patch is not installed.

### Tests completed

Both existing Metal smoke tests were compiled and rerun with external execution
deadlines: compute `[2,4,6,8]` **PASS**, offscreen RGBA `[64,127,191,255]` **PASS**.
Sandbox-only runs returned no Metal device; those are not GPU failures.

Added `tools/ga102_run_metal.py`: private test scratch, compilation deadline
90 seconds, execution deadline 45 seconds, maximum three processes per run,
no production-cache deletion. `--isolated-cache` redirects only the test
process's Mesa and AIR caches. Raw logs stay in local temporary storage; the
public report records selected measurements only.

Added `tools/ga102_metal_benchmark.swift`: target-device selection, three
offscreen sizes (256², 1024², 3440 × 1440), shared/private/IOSurface targets,
three warmups plus 24 measured submissions per case, separate encode/commit/
completion/GPU/readback timing, and three pixel checks. Two isolated-cache
processes completed all nine cases with correct output and valid reported GPU
timestamps. These measurements characterize a simple triangle, not full Core
Animation composition, throughput, or desktop FPS.

| 3440 × 1440 case | Run 1 GPU p50 / p95 (ms) | Run 2 GPU p50 / p95 (ms) | Run 1 / 2 encode-to-completion p95 (ms) |
|---|---:|---:|---:|
| shared, RGBA8 | 0.0584 / 0.0594 | 0.0584 / 0.0594 | 0.1433 / 0.4382 |
| private, RGBA8 | 0.0594 / 0.0594 | 0.0593 / 0.0594 | 0.1498 / 0.1457 |
| IOSurface, BGRA8 | 0.5724 / 0.5755 | 0.5714 / 0.5744 | 1.2919 / 1.2557 |

IOSurface GPU duration is approximately 10× the ordinary texture cases here,
but still below 1 ms. Pixel format and layout differ; a same-format comparison
is required before attributing the gap to shared linear memory. Plain texture
storage-mode labels also do not establish physical placement: the current
`newTextureWithDescriptor` ordinary image path does not select allocation
placement from that label. Do not infer shared-memory bandwidth from that pair.

Device creation: 165.4 / 159.2 ms. Library creation: 99.3 / 0.73 ms. First
render pipeline: 22.5 / 18.6 ms; subsequent identical pipelines in each process:
approximately 0.07–0.18 ms. Both Mesa and AIR caches were redirected together,
so the library improvement cannot be attributed to the Mesa cache alone. The
first pipeline in a new process still costs approximately one 60 Hz frame.
All measured simple GPU draws are well below the approximately 16.67 ms frame
budget; complex effects and multiple passes remain unmeasured.

### Validated narrow cache fix

The audit explained the planned change before editing it. Production cache
selection was moved to `plugin/nvmtl_mesa_cache.h` and used by
`nvmtl_vk_initialize`, with the same per-user → Darwin preference and explicit
environment opt-outs. The final directory must be a real searchable writable
directory; the Darwin path no longer accepts a regular file/symlink. Writable
`Library/Caches` is allowed even when HOME itself is read-only. `setenv` uses
overwrite=0 consistently.

An extracted copy of the prior `8516ac8` production block reproduced both edge
cases in owned temporary fixtures: read-only HOME incorrectly selected the
Darwin alternative despite writable Caches, and a writable regular-file Darwin
path was exported as the cache directory. This is a source-confirmed defect,
not evidence that either edge case occurs in this user's desktop session.

`python3 -m unittest tools/test_mesa_cache.py -v`: **43 production C assertions
PASS**, with AddressSanitizer and UndefinedBehaviorSanitizer. Cases include
first/existing directory, read-only HOME, explicit empty environment settings,
missing HOME, Darwin fallback, file/link rejection, search permissions,
relative/truncated paths, oversized/empty HOME, and an existing writable cache
under a read-only searchable parent. Full plugin Objective-C syntax checking passed
with official Khronos Vulkan headers in test-owned `/tmp`; existing compiler
warnings remain. The complete release plugin also linked successfully as an
x86_64 bundle against Foundation, Metal and IOSurface, with zero compiler
errors; the artifact remains in test-owned temporary storage. It was not loaded.
Runtime testing of a rebuilt plugin is not performed against
the installed driver. This fix is not a claimed desktop-speed improvement.

### Publication

The first HTTPS push lacked credentials. The report was initially published
through the connected GitHub integration (`2d8e615`); local commit `5defc6e`
was retained, and a history-preserving merge (`2866980`) reconciled the copies.
After GitHub CLI setup, `gh auth status` succeeded with keyring access outside
the sandbox; `git push` successfully published the merged documentation.
Sandbox-only auth failures should not be mistaken for invalid host credentials.
No credentials, raw kernel pointers, user paths, serials, or hostnames are
included in the report contents.

## Milestone 3 — cache correction validated

Changed `plugin/nvmtl_vk.c::nvmtl_vk_initialize` and added
`plugin/nvmtl_mesa_cache.h`; production logic is exercised by
`tools/mesa_cache_tests/main.c` through `tools/test_mesa_cache.py`.
Acceptance: the two reproduced path-selection defects are corrected, explicit
environment choices remain untouched, unsuitable directories are rejected,
43 assertions pass under ASan/UBSan, and the release plugin links.
No claim of improved WindowServer cache hits or desktop frame pacing is made:
the installed binary remains unchanged. Rollback is a normal revert of this
source commit, with no system rollback necessary.

## Milestone 4 — rendering, memory and presentation separated

### Matching-format IOSurface comparison

`tools/ga102_metal_benchmark.swift --surface-comparison` compares native-size
BGRA8 private and IOSurface targets. Two processes passed all changing-frame
pixel checks and supplied 24 valid GPU samples per case:

| Target | GPU p50 / p95, run 1 (ms) | GPU p50 / p95, run 2 (ms) | Completion p95, runs 1 / 2 (ms) |
|---|---:|---:|---:|
| BGRA8 private | 0.0584 / 0.0625 | 0.0594 / 0.0604 | 0.1668 / 0.7010 |
| BGRA8 IOSurface | 0.5714 / 0.5734 | 0.5714 / 0.5744 | 0.9138 / 0.9038 |

The roughly 9.6× GPU-duration difference survives pixel-format matching.
**Hypothesis:** linear imported-surface layout versus ordinary tiled VRAM is a
contributor; residency and cache behavior require profiling to establish cause.
Do not generalize this simple draw ratio to all compositing workloads.
Fresh process-owned AIR/Mesa directories did not restore the initial 99 ms
library cost: later new directories yielded approximately 0.7 ms. Apple compiler
services or other caches remain outside this isolation; these are not globally
cold compiler measurements.

### Memory placement workload

Added `tools/ga102_metal_memory.swift`: 4 MiB buffers, eight sequential compute
passes per storage mode, separate transfers, and all 1,048,576 output elements
checked per mode. Shared, managed and private all **PASS**.

| Buffer | Reported GPU duration per pass (ms) | Final readback (ms) |
|---|---:|---:|
| shared | 0.229–0.268 | 0.952 |
| managed | 0.011–0.014 | 0.214 |
| private | 0.011–0.012 | 0.223 |

This is an observed approximately 20× shared-buffer penalty in a bandwidth-heavy
compute workload, consistent with source allocation paths. It is not a measured
WindowServer penalty or justification to relocate CPU-accessible shared memory
blindly. Managed upload can be deferred until command execution; the CPU initial
upload times are not equivalent end-to-end DMA measurements. Full-buffer checks
also exercise producer-to-compute-to-readback ordering.

### Sampled alpha compositing

Added `tools/ga102_metal_composite.swift`: BGRA8 3440 × 1440 targets, 16/32
full-screen layers, three sampled premultiplied-alpha source textures, changing
source order per frame, blending, separate blit readback, and 16 distributed
pixel checks. Two warmups and eight measured frames per case; all four cases
**PASS**, with eight valid GPU samples each.

| Layers / target | GPU p50 / p95 (ms) | Encode-to-completion p95 (ms) |
|---|---:|---:|
| 16 / private | 0.799 / 0.807 | 0.995 |
| 16 / IOSurface | 1.312 / 1.347 | 1.521 |
| 32 / private | 1.571 / 1.617 | 1.804 |
| 32 / IOSurface | 2.087 / 2.101 | 2.451 |

The IOSurface penalty is much smaller as a ratio in this layered workload.
These samples remain below a 60 Hz frame budget. This exercises sampled texture
bindings and alpha blending, but does not reproduce blur, masks, sRGB conversion,
video surfaces, Core Animation's actual shader mix, or cross-process ownership.
Eight samples make p95 close to the maximum; this is a screening result, not a
statistically established optimization or comparison against another driver.

### Windowed presentation and visibility limitations

Added `tools/ga102_metal_present.swift`: a six-second ordinary 640 × 360
CAMetalLayer window, 120 submissions at a 60 Hz timer cadence, maximum three
outstanding commands, existing display mode, and automatic window closure.
No display-setting API is called. External runner deadline remains 45 seconds.

Three runs completed all 120 command buffers without errors, backlog or timer
skips. The first run returned 120 presented callbacks, 118 positive timestamps,
and 107 post-warmup intervals: p50 **16.667 ms**, p95 **17.646 ms**, max
**17.820 ms**, none above 25 ms. The two subsequent runs returned 120 callbacks
but **zero positive presentation timestamps**. The final run's framebuffer flip
count stayed **115285 → 115285** throughout the window lifetime. Consequently,
those runs provide GPU-completion evidence but no visible-presentation evidence.
Visibility/session/display activity was not forced or changed to investigate it.
The two initially zero timestamps and later missing timing remain unexplained.

[Apple documents `presentedTime`](https://developer.apple.com/documentation/metal/mtldrawable/presentedtime)
as presentation timing; this probe does not independently verify physical scanout
or input-to-photon latency. A successful callback alone cannot establish a visible
frame. The one usable run is insufficient to claim consistently smooth desktop
pacing. The test reports timing **UNAVAILABLE** separately from submission PASS.

Later passive counters were: transactions 115286, flips 115285, refusals/failures/
async drops/non-VRAM/stale flip counters all zero. This supports successful
zero-copy display operation during the investigation; unchanged counters during
an individual test must be retained as a visibility caveat.

### NVK warnings and control/provenance limitations

A process-only `NVRM_610_CECHAN=0` comparison was attempted using the runner's
`--graphics-copy-queue` option. The checked-out `nvrm610_on` honors this setting,
but the installed binary still emitted the dedicated-copy failure/fallback
warning. Therefore the run is **not a verified queue A/B experiment**. Correct
pixels and durations similar to the default run do not prove the dedicated-copy
fallback is cheap or costly. Identify installed-binary/source correspondence and
log the exact failed RM allocation/control plus chosen engine before making
changes. No production configuration was modified.

The fallback creates a copy queue on a graphics channel; it does not establish
CPU copies or shader-emulated copies. Existing optional sector-promotion status
0x56 is `NV_ERR_NOT_SUPPORTED`, not a fatal initialization failure. BAR1 remains
8 GiB for 12 GiB VRAM; forcing mapped-local VRAM would violate the current
source's full-aperture requirement. No such override was attempted.

### Other source findings and deferred changes

- `NVMTLCommandBuffer::commitAndWaitUntilSubmitted` and
  `NVMTLEventSync::nvmtlFinishExecution` serialize scanout preparation with GPU
  completion. This remains a plausible pacing/latency bottleneck; the wait is
  presently required for correct render-to-scanout ordering. Removing it without
  a fence bridge is not a justified low-risk fix.
- Active `NVRMFB::submitConfig` completion polling uses 1 ms sleeps. Existing
  legacy latch counters have no update sites. Instrument this actual completion
  loop before optimizing polling or declaring timeout counts clean.
- NVK `nvmtl_cfg_getenv`, duplicated `nvmtl_conf_getenv`, and `nvrm610_on` in
  `nvk/nvk-macos.patch` use first-match `strstr` followed by a line-start check.
  **Source defect:** a comment such as `# CECHAN=0` before `CECHAN=1` can hide the
  valid assignment. Static initialization/value buffers are also unsynchronized;
  concurrent use is a potential race, not reproduced in these workloads. No
  evidence makes either the current desktop cause. Defer parser consolidation
  until a complete Mesa build and production-parser regression tests are available.
- Main graphics/compute pipeline creation passes `VK_NULL_HANDLE` for Vulkan
  pipeline cache; Mesa's internal shader cache still exists. Metal binary archive
  membership serialization is not a persisted compiled-pipeline cache. Measure
  actual cold/warm service behavior before choosing a persistence implementation.
- Current grant counters do not indicate pressure. Residency/pager wait budgets
  in source are potential stalls under pressure, not observed failures here.

### Prioritized next work and acceptance

1. **Visible-session frame trace:** repeat the presentation probe while its
   window is verifiably visible; correlate WindowServer CPU/GPU timing, actual
   display counter deltas and intervals. Require three usable runs, no errors,
   report frames above 25 ms and explicit timestamp availability. Capture complex
   effects and input latency separately; do not manipulate display modes.
2. **Cross-process IOSurface correctness:** synchronized producer/consumer GPU
   writes and reads, repeated updates, then mixed textures/blur/masks. Existing
   same-process tests do not establish cross-process coherence or lifetime safety.
3. **Fence-to-display bridge and observability:** add actual NVK fence/completion
   and NVKMS polling measurements in source, build the paired display stack in
   isolation, design a scanout ordering replacement before relaxing waits.
4. **NVK provenance/copy queue:** reproduce the failed RM operation with a
   known matching build, then compare copy/graphics overlap and transfer sizes.
   Acceptance requires verified engine selection, correct data and repeatable
   improvement; silencing a warning is not an optimization.
5. **Cache deployment evaluation:** the source-only correction passes its local
   acceptance tests. With future explicit installation approval, verify writable
   cache paths and hit rates for the actual WindowServer identity and compare
   first library/pipeline latency. Current tests do not prove service cache hits.

## Consolidated outcome

GA102 firmware/startup, GPU compute, render targets, sampled alpha blending,
managed/private transfers and observed zero-copy display flips work in the tested
paths. Metal 3 reporting alone never served as acceptance evidence. Proven issues
include the recorded default-cache failure, two corrected source path-selection
bugs, misleading inactive latch counters, and the source parser edge case.
Observed costs include first-pipeline creation near one frame, shared-buffer
bandwidth and imported-surface rendering overhead. None yet establishes the
root cause of subjective desktop sluggishness.

At milestone 4, the only driver implementation change made was the regression-tested cache policy
correction (`f3ebd0c`); it was built but not installed or loaded. Test additions
and this report are independently reviewable. No system/graphics configuration,
installed driver, EFI, SIP, system permissions, display mode or refresh rate was changed;
no sudo, reboot, service interruption or production-cache deletion occurred.

## Milestone 5 — visible presentation, handoff coherence and completion instrumentation

Continued from `98a3db8`; prior architecture and offscreen benchmarks were not
repeated. The window probe was rerun specifically to explain missing presentation
evidence and measure submission phases.

### Visibility now measured instead of assumed

`tools/ga102_metal_present.swift` records only non-identifying booleans for Quartz
session availability, console/login state, display awake/active state, active
Space, window visibility/occlusion, and presence of this process's window in
CoreGraphics' on-screen list. It does not capture screen pixels or other window
titles. `ga102_run_metal.py` reads named display counters immediately before/after
execution, computes deltas, and leaves unavailable/idle evidence unverified.
Four Python regression cases cover missing, idle, active, partial and reset data.

All new window runs reported an active logged-in console, awake active display,
and visible/unoccluded/on-screen window throughout sampled checkpoints. Four
runs produced 118–119 positive timestamps from 120 completed submissions, with
presentation p50 approximately 16.65–16.66 ms and p95 17.10–17.58 ms; none of the
measured intervals exceeded 25 ms. The earliest one or two zero timestamps remain
unexplained. Three counter-correlated runs advanced 364, 268 and 281 pure flips,
with zero deltas for refusal/drop/failure counters. These are system-wide counts
and cannot be attributed exclusively to the test window.

**Confirmed:** the probe can obtain OS-visible presentation evidence on the
current console; missing timestamps are not a universal failure of this path.
**Unresolved:** the earlier all-zero runs cannot be retrospectively classified
because visibility/session/display-power state was not recorded. Hidden or
inactive-session behavior remains a hypothesis. No display-power or session
state was changed to force a result.

For physical confirmation, the user was asked to run, in repository Terminal:

```sh
python3 tools/ga102_run_metal.py ga102_metal_present --isolated-cache
```

Leave the six-second “GA102 bounded presentation probe” window unobstructed;
report whether its slowly changing color is visible and whether it stutters.
Human observation is pending. Software flags and callbacks do not independently
establish scanout or input-to-photon latency.

### Application-side latency versus display completion

The final instrumented visible run measured 120 commands:

| Phase | p50 (ms) | p95 (ms) | Maximum (ms) |
|---|---:|---:|---:|
| acquire drawable | 0.051 | 0.067 | 2.196 |
| encode | 0.055 | 0.096 | 1.041 |
| commit return | 0.010 | 0.036 | 0.057 |
| commit to scheduled callback | 0.031 | 0.057 | 0.126 |
| commit to completed callback | 0.208 | 0.258 | 10.837 |
| reported GPU duration | 0.005 | 0.006 | 0.006 |

Callback times include worker/dispatch scheduling and are not exact hardware
fence times. No persistent application-side submission stall is demonstrated by
this simple clear workload; the completion outlier remains worth retaining.
Across three correlated runs the mean framebuffer flip-call duration was
11.285, 11.201 and 11.174 ms. This includes NVKMS completion/vblank waiting; it
is not pure apply-call cost, GPU drawing time, FPS or proof of a harmful stall.
One run had drawable-acquisition p95 8.91 ms while maintaining timed presentation;
acquisition latency depends on scheduling phase/backpressure, not only GPU work.

A process-only `NVMTL_PERF_LOG=1` attempt emitted **zero PERFSUB records** from the
installed plugin. No internal phase timing was inferred from that absence.
A single three-second unprivileged `sample` attempt on WindowServer was denied
by macOS for insufficient privileges. This experiment is **blocked** under the
current permissions. No sudo, permission change, or retry was used. Actual
WindowServer CPU stacks and mandatory-wait durations remain unmeasured.

### Cross-process IOSurface coherence

Added `tools/ga102_metal_crossprocess.swift`: one persistent 64² BGRA8 surface,
two independent processes/imported textures, eight explicitly synchronized
roundtrips. Four producer frames use CPU lock/write/unlock, four GPU clears;
the consumer validates all pixels through GPU blit readback, writes a distinct
GPU response, and the producer validates all response pixels through its reused
texture. **262144 byte checks PASS**, with no stale response detected.

The initial non-global surface could not be looked up by ID in the consumer;
it failed before GPU testing. This was a test transport failure, not a proven
driver-coherency defect. The passing variant explicitly makes the owned synthetic
surface global and shares its ID. This legacy transport contains only generated
colors. Production sharing should transfer a Mach/XPC right, as described by
[Apple's IOSurfaceCreateMachPort documentation](https://developer.apple.com/documentation/IOSurface/IOSurfaceCreateMachPort%28_%3A%29).
It does not establish the production Mach-right ownership/lifetime path.
Roundtrip times 6.56–18.28 ms include 5 ms file polling and process scheduling;
they are **not GPU transfer benchmarks**. Concurrent unsynchronized access,
process termination during ownership, and compositor-owned surfaces remain untested.

### Cross-queue event ordering

Added `tools/ga102_metal_events.swift`: two queues, one shared event, 16 changing
signal/wait values and private-buffer producer fill → consumer readback. Eight
iterations deliberately commit the waiting consumer before its producer.
**65536 byte checks PASS**; all event values advanced. Commit-to-consumer-callback
time was 0.070–0.759 ms (first iteration largest). No deadlock/stale data was
observed in this bounded workload. This does not stress external shared-event
handles or all WindowServer event patterns.

### Source-only NVKMS completion observability

Changed active `kexts/NVRMFB/fb/nvrm-fb.cpp::submitConfig`, using the new production
`nvrm-flip-wait.h` helper. New read-only `debug.nvrmfb_completion_*` counters cover
prior/submitted wait counts and microseconds, queries, sleeps, failed status
queries, poll exhaustion, waits above 25 ms and an atomic maximum duration.
Unlike the inactive legacy latch counters, these update at the actual completion
loops. Tick durations are converted through `absolutetime_to_nanoseconds`.

Synchronization is preserved: 100 status queries, existing 1 ms sleeps,
query failure/exhaustion are not successful completion, and the original fault
latch and surface lifetime behavior remain. Bootstrap/cursor-only paths retain
their existing exceptions. No sleep reduction or early surface retirement was
introduced. This is an observability correction, **not a demonstrated smoothness
optimization**. Future deployed measurements can separate prior versus newly
submitted waits and detect long-tail stalls without relying on inert counters.

`python3 -m unittest tools.test_flip_wait tools.test_ga102_display_counters -v`:
**5 tests PASS**, including **39 production C++ poll assertions under ASan/UBSan**.
The new accounting function and all counter declarations compile against the real
kernel SDK with `-Werror`. Full framebuffer translation-unit checking stops at
missing generated `nvkms.h`; full kext build/link and deployed behavior are
**unvalidated**. No stub was substituted to pretend this check passed. No modified
component was installed or loaded. Rollback is a normal source revert.

### Current blockers and next experiments

- At milestone 5, physical window observation was pending. That request is
  superseded by milestone 6 automated validation. The earlier plan was to continue with
  the user's visibility/stutter report; prior offscreen success is not a substitute.
- WindowServer CPU stack sampling is blocked by macOS privileges. A permitted
  compositor trace/profiling route is needed to directly quantify its waits;
  the current application callback measurements cannot answer that question.
- New kernel counters cannot be read from the unchanged installed driver.
  Obtain the matching generated NVKMS header/build context, compile/link the
  paired stack in isolation, and seek explicit installation approval only after
  it is concrete and reviewable. Deployment remains outside current authorization.
- If visible simple rendering is smooth but desktop effects stutter, record a
  controlled real UI action (window drag, Mission Control, transparency/blur)
  with activity and timing correlation. Do not optimize completion ordering
  or remove mandatory waits based solely on the 11 ms average flip call.

The primary objective remains open: no measured improvement to the installed
macOS desktop is claimed. This stage closes several missing-evidence gaps and
prepares reliable wait instrumentation; it does not establish a root cause.

## Milestone 6 — user-run presentation reproduced; desktop-compositing probe in progress

**User-reported instrumented run**, exit 0: 120/120 commands completed without
errors; 118 positive presentation timestamps; interval p50 16.592 ms, p95
17.389 ms, none over 25 ms. Drawable acquisition p50 5.55 ms, p95 6.34 ms;
reported GPU duration p50 approximately 0.005 ms. System-wide flips advanced
283 with no new refusals/errors/drops. All four samples reported on-screen,
unoccluded active-desktop visibility. This is successful instrumented windowed
presentation, **not verified physical scanout or full desktop acceleration**.
The report does not substitute these measurements for a physical observation.

Three bounded repetitions are being collected to assess reproducibility and
variation in acquisition versus presentation. A new ordinary Core Animation
window uses 32 translucent rounded layers with shadows, explicit animations,
and idle/animation/idle phases. It records visibility and counter deltas; client
presentation-layer positions and timer intervals will not be labeled displayed
frames or GPU completion. Required synchronization remains unchanged.

### Repetition results and test-design correction

The requested three repetitions completed all 120 commands in each process with
awake/unoccluded active-session samples. Runs 1/2 had presentation p95 17.292 /
17.418 ms and no measured post-warmup intervals over 25 ms. Run 3 had p95
**33.451 ms**, maximum 34.006 ms and **16 intervals over 25 ms**, while reported
GPU duration stayed approximately 0.005 ms. Drawable acquisition p95 was
0.022 / 0.021 / **21.424 ms** respectively. Mean system-wide flip-call duration
was 10.505 / 10.100 / 9.849 ms with no new failure/drop/refusal counts. Thus
smooth timing is **not yet reproducible across all runs**. The acquisition/late-
frame correlation is observed, not proof that acquisition or synchronization is
defective. Client pacing, backpressure, other desktop work and vblank phase are
still candidates. New per-frame late-interval/acquisition/CPU-draw correlations
have been added to the timing probe.

The user's physical observation was a window appearing nearly static. The old
red oscillation was subtle; this is a test-design weakness, not a proven driver
failure. Routine human observation is no longer an acceptance dependency.
The timing probe now uses plainly distinct red/green/blue phases, and a separate
`ga102_visual_present.swift` renders explicit binary frame identifiers, a moving
white bar and contrasting RGB backgrounds. Each of 12 slow-changing frames is
read back by GPU blit and checked at 24 positions against an independent CPU
pattern model. Slow changes keep this a correctness test, not a 60 Hz benchmark.

### Automated visual verdict and negative controls

`ga102_visual_validation.py` evaluates each claim separately. Correct distinct
GPU pixels, increasing distinct presentation times, visible-window state,
matched distinct own-window captures and clean system display activity are
required for full automated visual PASS. Physical scanout is always
**NOT VERIFIED**, even when screenshot validation passes. The evaluator also
never declares the installed driver fixed. Nine Python regression tests pass
across visual verdicts and display-counter handling, including static output,
wrong capture pixels, absent/constant timing, hidden presentation, permission
absence, missing/reset counters and display drops.

Sequential live controls, with one probe window at a time:

| Case | Correct / distinct GPU patterns | Positive timestamps | Visible samples | Automated visual verdict |
|---|---:|---:|---:|---|
| normal | 12 / 12 | 11 | 12 | NOT VERIFIED: capture unavailable; other measured categories PASS |
| deliberately static | 1 / 1 | 11 | 12 | FAIL: changing expected pixels contradicted |
| timing suppressed | 12 / 12 | 0 | 12 | NOT VERIFIED |
| deliberately hidden | 12 / 12 | 0 | 0 | NOT VERIFIED |

The hidden control still had 137 additional **system-wide** flips. This proves
that GPU completion and advancing global flip counters cannot alone validate a
specific window. It also reproduces zero presentation timestamps without a GPU
rendering failure. Earlier all-zero runs remain retrospectively unclassified,
but hidden/occluded presentation is now an experimentally supported explanation.
An initial overlapping own Core Animation probe occluded the visual window:
only 3 visible samples / 4 positive timestamps were obtained despite 12 correct
GPU patterns. It was classified NOT VERIFIED and excluded from isolated timing
comparisons; later live controls were explicitly serialized.

Screen capture uses `CGPreflightScreenCaptureAccess` without requesting access.
When already permitted, ScreenCaptureKit selects only the current process's
window ID and uses `SCContentFilter(desktopIndependentWindow:)`; it captures no
other window/display pixels. Captured images are normalized in memory and
compared with expected sample pixels and across frame identifiers; images are
not saved. **Capture permission is currently unavailable**, so capture-image
comparison remains NOT VERIFIED; the capture method is blocked by that external
permission. No authorization prompt or permission change was made. The capture
branch compiles but has not been runtime-validated on this machine.

### Ordinary Core Animation observations

Added `ga102_core_animation.swift`: a normal 960 × 600 AppKit window with 32
translucent rounded layers and shadows, explicit animations, and idle / four-
second animation / idle phases. The initial run observed 234 changing client
presentation-layer positions; animation phase advanced 230 global flips over
3.902 seconds, with no new errors. Client timer p95 was 17.385 ms. This collects
real Core Animation workload activity, but client presentation-tree interpolation
is not a rendered-frame timestamp or independent pixel check. Visual validation
and physical scanout remain NOT VERIFIED. The initial run overlapped another
probe and is exploratory only.

Unprivileged cumulative WindowServer CPU time is readable through `ps`, even
though protected stack sampling remains blocked. The next version adds phase
CPU deltas and will run separately, allowing an idle-versus-animation comparison
without privileged sampling. This is process-wide correlation, not exclusive
attribution to this window or a replacement for actual GPU/compositor profiling.
No required completion wait has been removed or shortened.

### Final pattern validation and isolated compositor CPU measurements

The final high-contrast probe passed **12/12 expected GPU patterns**, all 12
patterns distinct, **12/12 increasing distinct presentation times**, and 12
visible-window samples. Global flips advanced 158 with no new errors. Overall
automated visual status remains **NOT VERIFIED** solely because own-window
capture permission is unavailable; physical scanout remains NOT VERIFIED.
No human observation is required to run these checks.

Two sequential, isolated Core Animation runs produced:

| Phase | Run 1 WindowServer CPU s / elapsed s | Run 2 CPU s / elapsed s | Run 1 / 2 global flips |
|---|---:|---:|---:|
| idle before | 0.31 / 1.834 | 0.34 / 1.847 | 55 / 62 |
| animation | 1.84 / 4.202 | 1.88 / 4.202 | 249 / 247 |
| idle after | 0.37 / 2.101 | 0.45 / 2.087 | 70 / 86 |

Animation correlates with approximately **44–45% of one CPU core** in WindowServer,
versus approximately 17–22% during these idle phases. Both runs observed 241
changing client presentation-layer positions, active visible-window samples,
and zero new display errors/drops/refusals. Animation flip-call means were
approximately 6.68 / 6.42 ms, versus approximately 11.1–11.3 ms during idle phases.
This phase dependence is evidence against treating a high average completion
wait as inherently defective; it includes vblank phase and scheduling effects.
CPU statistics are cumulative `ps` time differences (centisecond resolution)
and process-wide; background desktop activity is not eliminated.

Client timer p95 was approximately 18.18 / 18.34 ms during animation. These are
client wakeups, not measured composited frame timestamps; no pixel-level
Core Animation validation or physical scanout claim follows. This workload
contains shadows and translucency but does not reproduce every real desktop
application or Mission Control. A filtered ten-minute unprivileged unified-log
query found zero matching WindowServer NVMTL/NVK events; absent/suppressed logs
cannot prove absence of graphics failures.

The earlier three-repeat batch overlapped source typechecking during part of
its lifetime. That background CPU load is an additional possible confound for
its third-run stall. Three isolated per-frame traces are now being collected;
no driver optimization is justified by the confounded outlier alone.

### Isolated timer trace follow-up

Three isolated high-contrast timer traces completed 120/120 commands each,
returned 118 positive presentation times per run, and showed all visibility
samples active/unoccluded. Presentation p95 was **17.417 / 17.266 / 17.275 ms**;
all three had zero intervals above 25 ms and no new display errors. Acquisition
p95 was **4.120 / 7.992 / 8.026 ms**, while GPU p50 remained approximately 0.005 ms.
Per-frame late-interval lists were empty. The earlier 33 ms outlier did not
recur in these isolated runs. This supports reproducible simple timed
presentation under these conditions, not universal desktop smoothness.

An optional `--display-linked` pacing mode now uses AppKit's `NSView.displayLink`
to compare client scheduling against the existing timer. It changes no display
mode, refresh, vsync or synchronization contract. Three controlled runs are
being collected before assessing whether acquisition costs are scheduling-
phase effects. No driver defect or optimization is inferred in advance.

### Display-linked comparison blocked by inactive display

The first display-linked run completed no draw callbacks. Crucially, its state
snapshot reported **display_active=false, display_asleep=true**, an occluded
window, and zero display-counter deltas. The SDK documents that `NSView` display
link callbacks stop when the view is hidden or not on a display. This is
**NOT VERIFIED: inactive display**, not evidence of an NVIDIA callback defect.
The comparison is blocked by current display activity; no wake operation,
mode/refresh setting or power-setting change was attempted.

The timing probe initially mislabeled this condition FAIL because it expected
120 calls unconditionally. It now checks visible eligibility before that
acceptance criterion, while retaining FAIL for actual command errors or
unfinished submitted commands. Ineligible presentation never gets a full timing
PASS. This is a substantiated **test-classification correction**, not an installed
driver correction. Screen capture remains unavailable without authorization;
no request is made. Routine human observation has been removed as a dependency.

Current next priorities are a display-linked versus timer comparison when the
session becomes naturally active, and frame-content validation of the Core
Animation workload if window-only capture becomes available. The high-contrast
GPU checks, negative controls and existing coherence/event checks can run without
panel observation. Protected WindowServer stacks, deployed NVKMS completion
counters and physical scanout remain unverified/blocked under current access.
No substantiated execution/synchronization defect was found that warrants
removing or shortening any mandatory wait. No installed-driver speed improvement
is claimed.

Final verification: nine Python verdict/counter tests pass; high-contrast Metal
and Core Animation probes compiled and executed. The final timing and compositor
sources pass typechecking; the timing source retains a Swift 6 concurrency-mode
warning under the current default Swift 5 mode. Callbacks that inspect AppKit
state are scheduled on the main run loop; strict Swift 6 migration is unvalidated.
No source-only change in this milestone modifies driver execution. All additions
are diagnostics, validation logic and documentation. Installed components,
system graphics, EFI, SIP and display/power settings remain unchanged.

### Durable repeated-run acceptance milestone

The high-contrast probe now supports `--result-json NEW_FILE` in
`tools/ga102_run_metal.py`. The artifact records probe-source SHA256, numeric
metrics, per-run verdicts and system-wide display counter deltas. It excludes
raw driver logs, paths, environment variables and process identities. Existing
files are never overwritten. `tools/ga102_visual_validation.py::repeated_result`
requires evidence from every requested run; exit code zero alone cannot imply
visual validation. Three complete visual PASS runs are required for the
aggregate reproducibility PASS. Even then physical scanout, desktop smoothness
and installed-driver improvement remain separate, unverified claims. This
300 ms/frame correctness workload is not a 60 Hz performance benchmark.

A substantiated verdict defect was corrected: a negative/reset error-counter
delta could previously satisfy healthy display activity. Reset error counters
now yield NOT VERIFIED, while positive errors still yield FAIL. Mandatory GPU
completion and framebuffer waits are unchanged.

Fourteen Python regression tests PASS, including durable-artifact privacy,
deadline/incomplete execution, missing evidence, repeated negative controls and
counter-reset handling. A new isolated three-process runtime batch completed:
each verified **12/12 correct GPU frames and 12 distinct patterns**; each had
**zero visible eligibility samples, zero positive timestamps and zero framebuffer
flip deltas**, with zero new errors. Consequently GPU frame contents PASS,
but presentation, capture and full visual reproducibility are NOT VERIFIED.
The sanitized durable evidence is
[`evidence/ga102-visual-ineligible-repeat.json`](evidence/ga102-visual-ineligible-repeat.json).
This reproduces GPU success without eligible presentation and confirms that
the validator does not mistake it for visible output. No display wake or setting
change was attempted, and screen-capture permission was not requested.

Reproduction when the session is naturally active:

```sh
python3 tools/ga102_run_metal.py ga102_visual_present --repeat 3 --isolated-cache --result-json /private/tmp/ga102-visual-new-results.json
python3 -m unittest tools.test_ga102_result_artifact tools.test_ga102_visual_validation tools.test_ga102_display_counters
```

Remaining targeted experiments are the display-linked/timer pacing comparison
and own-window capture of the Core Animation workload. The former needs a
naturally active GUI session; the latter is BLOCKED by unavailable capture
authorization, with no repeated permission request. Protected WindowServer
stack sampling and full framebuffer compilation remain blocked as documented
above. Source review of `NVMTLObjects.m::commitAndWaitUntilSubmitted` and
`NVRMNVDAFramebuffer::submitConfig` still provides no verified alternative that
would justify removing completion waits. These are diagnostic/test corrections,
not an installed-driver fix. The desktop responsiveness objective remains open.

### Explicit frame-pacing regression gate

`tools/ga102_pacing_validation.py::evaluate` now scores the timing probe using
raw positive presentation timestamps and frame IDs, rather than trusting its
collection PASS string or process exit code. The Swift probe previously
discarded non-positive interval differences; repeated/reversed API times could
therefore disappear from its statistics. All differences are now retained.
No timing/synchronization behavior in the driver was modified.

Acceptance is deliberately limited to this simple 60 Hz workload: sampled
visibility eligible throughout, reported 3440×1440 mode with 59–61 Hz refresh,
120 commands completed without errors, at least 118 positive timestamps,
strict timestamp/frame-ID order, no gaps after ten warm-up presentations,
no skipped draws, p95 interval at most 20 ms and maximum interval at most 25 ms,
plus positive system-wide flip activity and no incrementing/reset error counters.
The 20 ms p95 allows modest scheduling jitter around 16.67 ms; 25 ms detects
intervals appreciably beyond one nominal refresh. These are initial regression
thresholds, not proof of perceptual quality or a universal performance standard.
Unknown refresh, inactive visibility or insufficient timestamps yield
NOT VERIFIED; measured stalls/order violations in an eligible run yield FAIL.
Command errors remain FAIL even when presentation is inactive.

The runner's `--result-json` also supports `ga102_metal_present`; artifacts retain
pacing mode, raw timing/IDs, counter deltas, thresholds, metrics and scoped
verdicts. Three full pacing PASS runs are required for pacing reproducibility.
Frame-content checks remain a separate probe, and physical scanout/desktop
smoothness/installed-driver improvement cannot become PASS from timing alone.

Nineteen Python tests PASS, covering injected stalls, repeated/reversed times,
missing IDs, skipped draws, hidden sessions, unknown/wrong display mode, resets,
errors, repeated aggregation and end-to-end artifact routing with mocked GUI
execution. Updated Swift passes default-mode typechecking with a scratch module
cache; the previously documented Swift 6 concurrency warning remains. The first
typecheck used the compiler's default non-writable cache and failed; redirecting
the cache resolved that tooling restriction. The revised timing gate has not
yet been exercised against an eligible live window. No redundant inactive GUI
benchmark batch was run at this milestone.

Next eligible-session commands (each artifact path must be new):

```sh
python3 tools/ga102_run_metal.py ga102_metal_present --repeat 3 --isolated-cache --result-json /private/tmp/ga102-timer-new-results.json
python3 tools/ga102_run_metal.py ga102_metal_present --repeat 3 --isolated-cache --display-linked --result-json /private/tmp/ga102-linked-new-results.json
```

Run these sequentially without another probe/compiler workload overlapping;
compare acquisition, scheduling/completion, raw intervals and late-frame
correlations before attributing latency to any mandatory wait. Previous isolated
GPU execution was roughly 0.005 ms while acquisition varied by several ms,
which motivates the scheduling-phase experiment but does not prove a defect.

### Sequential unattended regression suite and override-policy finding

`tools/ga102_suite.py` connects the bounded runner to correctness, presentation,
negative-control and combined profiles. Every probe runs sequentially with
private logs and structured evidence. Compiler and probe deadlines remain owned
by the runner, avoiding a second process-group timeout that could orphan its
children. Unexpected failures stop further GPU launches in that batch; expected
static-control rejection does not. Unavailable macOS/compiler resources yield
BLOCKED. Missing/hidden presentation evidence yields NOT VERIFIED. Suite PASS
means only that every selected scoped check passed; desktop smoothness and
physical scanout remain NOT VERIFIED. Three repetitions are explicitly requested
for reproducibility; the default single run avoids unnecessary GPU usage.

The two smoke tests previously selected the system-default Metal adapter.
They now explicitly select the RTX 3080 Ti, matching the other targeted probes,
and emit independently checked structured compute values/rendered RGBA data.
`tools/ga102_core_validation.py` checks coverage as well as process success:
four-element compute, one offscreen pixel, all four compositing cases with 16
pixels each, 16 shared-event iterations including eight consumer-first commits,
and eight two-process IOSurface round trips covering 262144 checked bytes.
This remains synthetic serialized coherence coverage, not production
cross-process lifetime/Mach-right validation or arbitrary concurrent access.

Twenty-three Python tests PASS. The first end-to-end correctness suite also
PASSed all five installed-runtime probes. This justified one repeat of existing
workloads to validate the new evidence plumbing and explicit adapter selection;
it is not a new full desktop benchmark. Shared-event completion ranged
0.071–0.920 ms. For 32-layer offscreen compositing, private GPU p50/p95 was
1.579/2.129 ms and IOSurface 2.085/2.111 ms; encode-to-completion p95 was
2.692/3.347 ms respectively (eight samples each). No driver optimization follows
from this single small timing sample. Sanitized source hashes, metrics and
verdicts are saved in [`evidence/ga102-core-suite.json`](evidence/ga102-core-suite.json).
One run does not satisfy reproducibility, and no source-only driver change ran.

```sh
python3 tools/ga102_suite.py --profile correctness --output /private/tmp/ga102-core-new-results.json
python3 tools/ga102_suite.py --profile presentation --repeat 3 --output /private/tmp/ga102-presentation-new-results.json
python3 tools/ga102_suite.py --profile negative-controls --output /private/tmp/ga102-controls-new-results.json
python3 -m unittest discover -s tools -p 'test_ga102*.py'
```

**Confirmed installed-code policy, not a desktop defect:**
`plugin/NVMTLObjects.m::nvmtl_conf_knobs`, in release builds, removes inherited
`NVMTL_*`, `NVK_*`, `NAK_*` and `NVRM_*` environment variables before loading
the production configuration. Read-only disassembly of the installed plugin
(unchanged SHA256 `853cc88e3e414815384d7d60bc01dd4d5cb67708c20d10472f59506a60a9c5cb`)
confirms the matching prefix comparisons and `unsetenv` loop before `fopen`.
The readable installed configuration has no explicit CECHAN assignment.
Thus the earlier environment-only `NVRM_610_CECHAN=0` attempt could not establish
a graphics-copy-channel comparison: the release constructor strips it. No
configuration change or additional ineffective comparison was performed.

This also corrects prior cache-isolation wording: `--isolated-cache` requests
both Mesa and AIR paths, but release initialization strips `NVMTL_AIRCACHE`.
`MESA_SHADER_CACHE_DIR` is outside those prefix filters. AIR isolation and globally
cold compilation must not be claimed. The runner now warns explicitly; previous
correctness results remain valid, but cannot prove AIR-cache isolation. The
environment-clearing policy is preserved because its production purpose has not
been shown to be a correctness/performance defect.

**Experimental component isolation review:** the source provides a process-only
`NVMTL_ICD_LIB` path override, but the installed release constructor also strips
that variable. Merely setting it cannot validate an alternate backend. Direct
loading an uninstalled Metal bundle has constructors that register/replace
Objective-C methods in the loading process, read production configuration and
mutate process environment; device initialization then uses private
`MTLIOAccelDevice`/accelerator-port interfaces and opens NVK channels. A verified
isolated device-binding harness is not yet established. No experimental bundle
was executed, no active component replaced, and no graphics services restarted.
Previously built candidates remain AWAITING LIVE VALIDATION. Offline tests and
source development continue independently of this deployment limitation.

### ScreenCaptureKit owned-window validation after app restart

Permission is process-dependent in this session: three temporary Swift probe
runs still returned `CGPreflightScreenCaptureAccess=false`, while a separate
read-only call in the Python diagnostic process returned true. Those Swift runs
had 12/12 correct GPU patterns, positive ordered timestamps and visibility in
each run, but no capture. This supports different effective authorization for
the temporary executable; no permission database, security setting or additional
authorization prompt was accessed. A separate authorization for that executable
was avoided by moving capture into the already authorized Python process.

`tools/ga102_window_capture.m` is a small helper dylib loaded only into that
diagnostic process, not a driver/plugin replacement. It links public AppKit,
Foundation, CoreGraphics and ScreenCaptureKit, has no NVK/driver initialization,
and captures only a `desktopIndependentWindow` filter matched against both the
owned child's PID and window ID. `tools/ga102_capture_bridge.py` also verifies
the request belongs to its live child before calling the helper. A private
request/response channel keeps each rendered pattern stable until capture ends.
Only 24 synthetic RGB sample points are returned; no screenshot files or pixels
from other windows are collected. Process/window identifiers stay in private
scratch and are excluded from public evidence. An unavailable API stops further
capture calls in that run, and a missing broker response stops retries in the
Swift child. The suite's presentation/control profiles now select this broker.

Two harness failures were resolved transparently. The first helper attempt
aborted because ScreenCaptureKit required an initialized AppKit/CoreGraphics
client in the Python host. Only the surviving owned probe group was terminated,
after verifying its executable and process-group identity. The helper now creates
an accessory NSApplication client without focus activation or service changes.
A subsequent build failed because the source changed during compilation; the
runner now compiles private source snapshots and hashes those exact bytes.
Neither failure indicates a GPU/WindowServer defect. No experimental driver
component, kext or active framebuffer was replaced.

The first functioning capture run correctly yielded **FAIL**: GPU output was
12/12 correct and captured frames were all distinct, but only 4/12 captured
frames matched the original expected RGB values. This reproduced in a second
run. Sampled red was `[242,55,20]`, green `[99,253,60]`, and blue `[0,0,249]`.
A CPU-owned BGRA fixture independently passed the helper's RGB normalization
control. SDK headers document that a nil CAMetalLayer colorspace performs no
color matching and capture defaults to the display's color space. The test
previously compared these unspecified color semantics against canonical sRGB.
Explicit sRGB on both the probe layer and capture configuration resolved the
mismatch without increasing the existing tolerance or altering display settings.
This substantiates a test color-space definition error; the exact contribution
of each of the two tagging changes was not separately isolated. It does not
establish an installed-driver color or performance defect.

**PASS, repeated owned-window validation:** three sRGB broker runs each had
12/12 correct, distinct GPU patterns; 12/12 correct, distinct captured frames;
12 positive ordered timestamps; and 12 eligible visibility samples. System-wide
successful flip deltas were 318/318/317, with no new drops/refusals/failures.
Thus all claimed automated visual categories and three-run reproducibility PASS.
Physical scanout and real desktop smoothness remain NOT VERIFIED. This slow
300 ms/frame correctness probe does not measure 60 Hz animation performance.

**PASS, live negative-control rejection:** reusing the same built probe/helper
avoided recompilation. Static output yielded GPU/capture correctness 1/12 and
one distinct pattern, hence visual FAIL. Forced zero timestamps had 12/12 correct
captured patterns but remained NOT VERIFIED. Hidden output had correct GPU
patterns, zero visible samples/timestamps and zero captured frames, hence
NOT VERIFIED. No control received a full visual-validation PASS. Twenty-six
Python tests PASS, including independent pattern sampling, owner rejection,
hidden-window refusal, source snapshots and existing acceptance gates. The
capture helper compiles with `-Wall -Wextra -Werror`.

Public evidence: [`evidence/ga102-visual-capture-srgb.json`](evidence/ga102-visual-capture-srgb.json),
[`evidence/ga102-visual-untagged-capture-failure.json`](evidence/ga102-visual-untagged-capture-failure.json),
and [`evidence/ga102-capture-negative-controls.json`](evidence/ga102-capture-negative-controls.json).
Probe/helper hashes identify exact built snapshots. The direct probe remains
available, while `--capture-bridge` supplies the authorized-process capture path.

An active-session three-run timer batch also completed 120 commands per run
with no display errors and no intervals above 25 ms. Two runs passed the new
gate (p95 17.159/17.257 ms); the middle run had only 117 positive timestamps,
for IDs 3–119, and remains NOT VERIFIED under the unchanged minimum-118 rule
despite steady-state p95 17.126 ms. The gate was not relaxed to force a PASS.
Acquisition p95 varied from 0.062/7.965/0.079 ms while completion-callback p95
was 0.261/0.227/0.252 ms; this variation motivates the pending display-linked
comparison rather than removal of mandatory waits. Saved timing evidence is
[`evidence/ga102-timer-active.json`](evidence/ga102-timer-active.json).

### Window readiness and matched pacing comparison

The first display-linked batch had one pacing PASS and two NOT VERIFIED runs:
their first sampled AppKit occlusion state was not eligible and only 117
timestamps were positive. That is retained in
[`evidence/ga102-linked-active-before-readiness.json`](evidence/ga102-linked-active-before-readiness.json).
The timing probe now allows 250 ms for initial AppKit state publication, then
waits at most two seconds for eligible window/session/display metadata before
starting the timed workload. It never activates the app, raises its window,
wakes the display or changes mode/refresh. If readiness is unavailable, no
draws begin and the result is NOT VERIFIED. All eligibility samples taken
during the workload still have to pass. The Python gate requires an explicit
readiness result; hidden/inactive or missing preflight evidence cannot pass.
The six-second observation period and command/error/timestamp/interval criteria
are otherwise unchanged. This is a test-startup correction, not a driver fix.

Both modes then completed three isolated runs at reported 3440×1440, approximately
60 Hz, without overlapping capture/probe/compiler workloads during drawing.
Each completed 120/120 commands with clean counters, no skipped draws and no
steady-state interval above 25 ms. The readiness samples were all eligible.

| Pacing | Positive timestamps | Steady-state interval p95 (ms) | Drawable acquisition p95 (ms) |
|---|---|---|---|
| AppKit display link | 119 / 119 / 119 | 17.509 / 17.457 / 17.198 | 0.066 / 0.043 / 0.053 |
| 60 Hz timer | 118 / 118 / 119 | 17.232 / 17.265 / 17.250 | 11.697 / 11.481 / 0.067 |

Both meet the existing **steady-state** pacing gate and three-run reproducibility.
The large timer acquisition waits did not coincide with slower steady-state
presentation; the third timer run also had almost no acquisition wait. This
supports scheduling-phase/backpressure as a hypothesis for the wait, without
proving its underlying implementation or justifying removal of synchronization.
GPU work remained approximately 0.005 ms and completion-callback p95 stayed
sub-millisecond. The display-link result does not establish an end-to-end input
latency improvement or full desktop performance fix.

**Startup remains measured separately:** all three display-link runs had a
33.091–33.629 ms interval at frame 2; the third timer run had 32.932 ms there too.
These occur inside the ten-presentation warm-up exclusion already defined by
the gate. They remain in raw timestamps and late-frame correlations and are
not hidden by the steady-state PASS. Correlated acquisition was 0.776–1.391 ms
for display-linked startup and 4.361 ms for that timer startup, with client draw
intervals around one refresh. The cause is not yet attributed to WindowServer,
first-surface setup, command completion or shader compilation. Further per-frame
submission/completion evidence is needed before changing driver code.

Twenty-seven Python tests PASS, including no-draw/missing-preflight classification.
The timing probe compiled and ran in both modes; existing default-mode Swift 6
concurrency warnings remain. Evidence:
[`evidence/ga102-linked-ready.json`](evidence/ga102-linked-ready.json) and
[`evidence/ga102-timer-ready.json`](evidence/ga102-timer-ready.json).
Capture validation remains a separate sampled-content experiment; these timing
runs do not independently verify every rendered frame or physical scanout.
All active graphics components and synchronization contracts remain unchanged.


### Per-frame completion tracing and drawable-pool control

Added read-only, process-local tracing in `tools/ga102_metal_present.swift::draw`:
relative draw/acquisition/encode/commit/scheduled/completed/presented clocks,
GPU duration, and six startup samples of the existing system flip counter.
IOSurface identities are mapped to local slot numbers; global surface IDs are
not exported. The runner retains full traces privately and adds independent
analysis from `tools/ga102_presentation_trace.py::analyze` to future pacing
verdicts. Its classification is separate from the pacing gate and does not
claim a raw GPU fence timestamp or a driver root cause. Missing traces are
NOT VERIFIED; invalid or reversed clocks FAIL. No completion wait changed.

**PASS, controlled observation:** three display-linked runs each at two and
three drawables completed 120/120 commands, 119 positive timestamps, no skipped
draws, eligible sampled visibility and clean error/drop counters. Steady-state
p95 intervals remain below 20 ms in all six. Only the probe's own CAMetalLayer
`maximumDrawableCount` changed between groups, using the SDK-supported 2/3
values. This does not alter the active framebuffer or display configuration.

**Confirmed startup symptom:** all six retain a frame-2 interval of
32.991–34.292 ms. Frame 2 completed 0.197–0.243 ms after commit, with the preceding
frame completing 0.120–0.139 ms after commit. Commit spacing was
16.502–17.223 ms. Reported presentation followed completion by 32.127–33.145 ms;
two additional system-wide flips occurred between the two presented callbacks.
The GPU duration was about 0.005–0.006 ms. These CPU callbacks include the
plugin's completion bookkeeping; they are not hardware fence instants.

With three drawables the local slot sequence is 0/1/2/0/1/2; with two it is
0/1/0/1/0/1. The same late frame 2 therefore occurs on a reused surface in the
two-drawable group. **The hypothesis that first use of the third drawable alone
causes this startup gap is not supported.** Nor does the evidence support
removing GPU completion waits, changing the desktop drawable count, or treating
the shared flip-call mean as this window's latency. First-command completion
still takes about 10 ms, but the later frame-2 gap persists after prompt client
completion and is a separate observation.

Public, aggregated evidence with exact compiled source hashes:
[`evidence/ga102-drawable-startup-trace.json`](evidence/ga102-drawable-startup-trace.json).
Full numeric traces remain private. Thirty-one Python tests PASS. Both Swift
modes compiled and executed; the existing default-mode concurrency warning
remains. These are test/instrumentation changes, not an installed-driver fix.
Physical scanout and actual desktop responsiveness remain NOT VERIFIED.
Next: extend window-only capture to ordinary Core Animation content so that
compositor output, rather than only a CAMetalLayer client, is independently
validated before pursuing a rendering/synchronization correction.


### Independent ordinary Core Animation content validation

`tools/ga102_ca_visual.swift` is an ordinary accessory AppKit client with CALayers,
not a replacement Metal plugin. It opens only a 640×360 borderless window,
performs twelve disabled-action reference transactions held for at least 300 ms,
and closes. The reference includes primary colors, mirrored binary frame strips
and a moving white bar. Thirty-two additional translucent rounded layers with
shadows animate between the reference sample rows. Their motion is a compositor
workload, but is explicitly **not** pixel-validated by this test.

The existing authorized Python/ScreenCaptureKit broker selects only that child's
PID/window ID; it compares 24 RGB reference points per capture to the independent
Python frame model. No desktop image, other-window image, screenshot file or
process/window identifier enters public evidence. No activation, display wake,
permission prompt or graphics-system mutation occurs. The capture helper and
its independent CPU color-normalization fixture are unchanged.

**PASS, sampled compositor reference content:** three independent processes each
submitted twelve reference transactions and produced twelve correct, distinct
captured patterns (36/36), with all sampled window/session eligibility checks
passing. System-wide flips increased by 379/374/370 with no new errors, refused
flips or drops. The captured pixels establish changing ordinary Core Animation
reference output in this owned-window capture path, rather than only successful
CAMetalLayer/GPU completion callbacks. They do not verify physical scanout,
every animation frame, the extra animated layers, GPU completion, or desktop
input-to-display latency. These remain NOT VERIFIED.

**PASS, negative-control rejection:** the same built probe/helper was reused.
Static rendering yielded only 1/12 correct expected patterns and one distinct
pattern, so validation FAIL was correctly detected. Hidden output had zero
eligible/captured frames and remained NOT VERIFIED. A process-only simulated
unavailable-capture flag likewise produced zero capture calls and NOT VERIFIED;
no actual TCC permission was revoked or claimed unavailable. All three controls
rejected a full compositor-content PASS.

`tools/ga102_ca_validation.py` enforces the scoped content/eligibility/display
checks; `ga102_run_metal.py` saves exact source/helper hashes and `ga102_suite.py`
includes the new probe in presentation/all profiles and its static/hidden
controls in negative-controls/all. Thirty-three Python tests PASS. Swift and
capture-helper compilation PASS. Source changes affect diagnostics only.

Evidence: [`evidence/ga102-ca-owned-capture.json`](evidence/ga102-ca-owned-capture.json)
and [`evidence/ga102-ca-capture-controls.json`](evidence/ga102-ca-capture-controls.json).
The observed screenshot IPC round trips (roughly 148–230 ms) include SCK setup,
capture, polling and normalization and are **not** compositor rendering latency.
They make per-frame SCScreenshotManager calls unsuitable for measuring 60 Hz
animation. Next safe experiment: one bounded owned-window SCStream with encoded
reference frame IDs, keeping capture loss distinct from actual panel drops.


### Bounded owned-window SCStream and observation overhead

The broker now supports one window-only `SCStream` with BGRA/sRGB, a requested
1/60-second minimum frame interval, queue depth 3 and no audio/cursor/recording.
It accepts only its live child's window ID/PID, retains at most 512 numeric
24-point records, and exports decoded frame IDs with relative capture PTS.
Full images are never retained or written. Raw RGB/absolute PTS stay private.
The callback samples a read-only pixel buffer on a serial queue. Stop/drain
is explicit; runner cleanup stops only this stream on child failure/deadline.
No active graphics-system component is replaced. Sources:
`ga102_window_capture.m::ga102_stream_start/stop`, `ga102_stream_capture.py`,
`ga102_ca_visual.swift --continuous`, and the runner/suite.

**FAIL correctly detected, initial test design:** the first stream captured a
236/236/236 AppKit placeholder before reference rendering. Subsequent 130 records
were correct and included all 120 IDs, but the extra invalid record correctly
failed validation. The probe now publishes frame zero *after* window readiness
before starting the stream. It does not discard malformed captured frames or
widen RGB tolerance. Subsequent captured references have zero invalid samples.

**Confirmed observer cost:** the initial continuous client called synchronous
session/window/display queries each frame, then slept for 16.667 ms. It actually
submitted at about 33 ms spacing, so captured 33 ms changes could not establish
a compositor delay. Reducing only CGWindowList queries did not resolve this;
other synchronous eligibility calls still blocked. The instrumented control
measured `CGSessionCopyCurrentDictionary` around 15.7 ms mean with every-frame
queries, while cached AppKit visibility checks took about 0.0013 ms. This is
client observation overhead, not proof of a synchronization defect in NVMTL.

The final continuous probe takes full session/on-screen/display snapshots at
readiness, frames 0/30/60/90 and the end. Between them it reads cached AppKit
visibility/occlusion only. All full snapshots must be eligible. Timing and
query-component costs are preserved, including pauses at full snapshots.
It does not claim full-session eligibility was independently sampled every
frame. The every-frame-query option remains as an explicit diagnostic control.
No mandatory GPU, resource or framebuffer completion wait was removed.

**PASS, captured-content scope / NOT VERIFIED, complete capture coverage:**
three faster clients submitted 120 references each, with client interval p95
18.925–18.961 ms, but the stream decoded only 63/64/63 distinct IDs. All captured
reference samples were correct and ordered; stop succeeded, with no stream
overflow/failure or new framebuffer errors/drops. Full 120-ID coverage remains
NOT VERIFIED and the continuous overall gate therefore does not PASS. Missing
IDs or capture PTS gaps cannot establish dropped physical/compositor frames:
SCK may omit/coalesce output, and its minimum interval requests a maximum
capture rate rather than guaranteeing all client frames. A matched same-binary
every-frame-query control submitted around 33 ms and captured all 120 IDs,
passing its content/coverage scope; animation pacing remains NOT VERIFIED.

A held-reference regression still passed 12/12 pixels after the stream helper
extension. Live continuous static/hidden controls remain NOT VERIFIED and never
receive a full validation PASS. Thirty-seven Python tests PASS, covering wrong
owner rejection, malformed pixels, reversed capture clocks, missing IDs,
static output, stop failure and scoped aggregation. The helper compiled with
warnings-as-errors and the Swift probe compiled and ran. Presentation/all and
negative-controls/all suite plans now include the continuous experiment.

Evidence: [`evidence/ga102-ca-stream-reference.json`](evidence/ga102-ca-stream-reference.json)
retains the initial FAIL and subsequent controls/aggregates with exact source
hashes. No physical-scanout or desktop-improvement claim is made. Next useful
control is an encoded Metal client under the same stream, correlated with its
independent GPU readback and presented callbacks, to distinguish capture-rate
limitations from ordinary Core Animation content delivery.

## Matched frame delivery and capture backpressure (2026-10-11)

The primary desktop-sluggishness cause is **NOT VERIFIED**. These diagnostic
changes do not modify the installed driver, graphics services, display mode or
mandatory synchronization. Physical scanout is **NOT VERIFIED** throughout.

### Controlled Metal / Core Animation comparison

Both clients now use an NSView display link, a 640×360 owned window, the same
120 encoded primary-color/bit-strip/moving-bar references, and the same Python
ScreenCaptureKit broker (BGRA/sRGB, requested 60 Hz maximum, queue depth 3).
`ga102_ca_visual.swift --reference-only` removes the 32 extra animated layers
for this comparison; the existing workload remains the default. Metal performs
independent pixel readback after every real command completion. Only the
probe-owned window is captured; no images or desktop contents are published.
Full visibility snapshots remain mandatory at periodic checkpoints; their CPU
cost is recorded separately from render/transaction work. Three repetitions
per condition completed, with all local visibility checks eligible, no missed
link ticks and no new system-wide framebuffer errors/drops.

| Condition, three runs | Submitted / correct GPU frames | Distinct captured IDs | Steady interval p50 / p95 / p99 (ms, ranges across runs) |
| --- | --- | --- | --- |
| Metal + SCK | 120 / 120 each | 120 each | Reported presentation: 33.343–33.351 / 34.277–34.374 / 34.343–34.458 |
| CA reference-only + SCK | 120 transactions each; GPU fence unavailable | 65 / 66 / 66 | Client submission: 16.674–16.675 / 16.738–16.768 / 16.774–16.825 |
| Same Metal binary, capture disabled | 120 / 120 each | Not applicable | Reported presentation: 16.636–16.684 / 17.333–17.354 / 17.486–17.625 |

Quantiles use nearest rank. Steady measurements use frame IDs >=10 (109
intervals); the initial deliberate frame-zero hold and capture setup are
retained separately, not silently included in a steady p99. CA submission
spacing is **not** a measured presentation interval. CA does not expose a
per-frame GPU completion/drawable presentation callback in this test.

**Confirmed:** capture-on changes this encoded Metal client's delivery rate.
Acquisition p50 rises from 0.013–0.017 ms without SCK to 17.500–17.518 ms with
SCK. GPU p50 stays around 0.062 ms; acquisition p95 is 17.649–17.680 ms,
whereas encoding p95 is 0.106–0.113 ms, GPU p95 about 0.0635 ms, and CPU
reference readback p95 0.030–0.032 ms. All capture-on steady intervals exceed
25 ms; the unchanged cadence gate correctly reports **FAIL**. One run includes
a 50.59 ms presentation maximum and occasional ~18–20 ms completion callback
latency despite short GPU execution. That requires separating actual callback
invocation from MainActor resumption/presentation work before attribution.

A prior same-binary metadata-only stream, which never obtains/locks/reads a
pixel buffer, still produced acquisition p95 17.638 ms and presentation p95
34.421 ms. Pixel sampling alone therefore cannot explain the sustained delay.
Periodic eligibility work has separate tails (~18.6 ms maximum with capture,
~5.3 ms without in the matched runs); cached checks are approximately 0.001 ms.
An earlier capture-disabled run had three isolated long intervals. It remains
a retained **FAIL**, rather than being erased by these later steady successes.
The new three-run baseline passes the cadence check but overall remains
**NOT VERIFIED** because capture was deliberately disabled.

**Missing-frame interpretation:** all 120 CA references were submitted, with
no interval exceeding 25 ms, but only 65–66 IDs were observed. This excludes
"never submitted" as their explanation in these runs, but cannot separate
compositor coalescing from SCK sampling/omission. Metal captured all 120 correct
IDs even when only 119/117/120 positive presentation timestamps were returned;
missing callback timestamps therefore cannot automatically mean missing window
contents. Timestamp validation remains **NOT VERIFIED** for the 117-callback
run (minimum 118 unchanged). SCK and GPU clocks are not used to claim physical
scanout or exclusive compositor latency. System flip deltas are shared across
all clients, not a count of these reference frames.

Shader/pipeline initialization measured 258.6 ms on the first process and
47.9–50.8 ms subsequently, entirely before frame timing. This can affect probe
startup, but does not explain the sustained capture-on drawable waits.

Sources: `tools/ga102_visual_present.swift`, `ga102_ca_visual.swift`,
`ga102_window_capture.m`, `ga102_stream_capture.py`, and
`ga102_delivery_analysis.py`. Evidence:
[`evidence/ga102-matched-frame-delivery.json`](evidence/ga102-matched-frame-delivery.json)
and [`evidence/ga102-metal-capture-backpressure.json`](evidence/ga102-metal-capture-backpressure.json).
The latter preserves earlier source hashes, the old content-only verdict and
its subsequent stricter cadence reassessment. No tolerance or synchronization
requirement was weakened. The runner now distinguishes actual process exit
from validation failure; an exit-zero process cannot launder a cadence FAIL.

### Startup interval: controlled first-draw phase experiment

A same-binary clear-only client was run three times normally and three times
with only its first draw deferred 8.333 ms. The display link and display mode
were unchanged. Normal runs reproduced frame-2 intervals 32.858–34.128 ms,
with acquisition 0.812–1.084 ms, commit spacing 16.365–16.764 ms, command
completion callbacks 0.203–0.244 ms after commit, GPU 0.005–0.007 ms, and
31.961–33.200 ms from completion to reported presentation. Two shared system
flips occur between the corresponding callbacks. This corroborates prompt
client/GPU completion before the startup presentation gap. Clear-only drawing
has no shader pipeline compilation, excluding shader initialization for this
specific gap. Prior two/three-drawable tests already ruled out first use of
only the third drawable as a sufficient explanation.

The shifted condition had **no observed** long intervals, but only 117 positive
timestamps in every run, versus 119 normally. The missing early observations
prevent calling this an improvement or claiming that a refresh boundary was
avoided. Its timestamp gate remains **NOT VERIFIED**. No inference is made
from an absent frame-2 timestamp. Phase-dependent initial publication/callback
behavior is a hypothesis, not evidence of an unavoidable boundary or a fix.
Compositor selection, layer startup, callback reporting and NVKMS scheduling
remain candidates; current public timestamps cannot isolate those components.
Evidence: [`evidence/ga102-startup-phase-control.json`](evidence/ga102-startup-phase-control.json).

### Priority ranking for ordinary desktop responsiveness

1. **Render-to-present synchronization / compositor scheduling.** Highest
   plausible impact: `plugin/NVMTLObjects.m::commitAndWaitUntilSubmitted`
   deliberately waits for complete GPU execution in WindowServer because
   NVAccel cannot attach this NVK fence to an NVKMS flip. Separately,
   `plugin/NVMTLEventSync.m::nvmtlFinishExecution` executes presentation actions
   before marking completion/calling completion handlers. The observed short
   GPU work with occasional long completion callbacks warrants instrumenting
   scheduled/completed callback invocation versus client resumption. Capture
   backpressure is proven in this probe, not proven to affect ordinary desktop
   use. Smallest safe next experiment: record those distinct CPU stages in the
   same capture-on/off binary, without changing waits or deployment.
2. **NVKMS flip completion / polling.** Existing synchronous completion polling
   can consume a substantial refresh budget (shared flip-call means often
   ~6–12 ms). Duration includes legitimate refresh synchronization, not pure
   wasted CPU time. Global counters cannot attribute a wait to a WindowServer
   frame. Per-phase query-count/duration instrumentation exists source-only;
   validation in the installed kernel remains **AWAITING LIVE VALIDATION**.
   Protected WindowServer stack sampling is unavailable without elevation;
   do not retry, restart services or request elevated access.
3. **IOSurface placement/coherency/copies.** `nvmtlSurfaceIn/Out` have import,
   VRAM sharing and fallback upload/readback paths. Previous matching full-size
   synthetic composite costs (~1.57 ms private, ~2.09 ms IOSurface) support a
   possible contribution, not a reproduced desktop defect. Smallest next
   discriminating test is a matched producer/consumer workload with explicit
   synchronization and transfer stage timing, not removal of coherency waits.
4. **Shared-memory bandwidth.** Prior shared versus private 4 MiB workloads
   differ greatly relatively (~0.23 versus ~0.011 ms GPU), but their absolute
   cost is small against 16.7 ms and WindowServer usage is unmeasured. Lower
   priority until a real critical-path transfer is identified. Dedicated copy
   engine fallback remains GPU execution, with no validated desktop A/B.

A separate bounded capability check confirms installed `newSharedEventHandle`
returns nil; source `NVMTLObjects.m` and `NVMTLDevice.m::newSharedEventWithHandle`
explicitly lack cross-process event export/import. Event creation and same-
process value roundtrip pass; export **FAIL**, import/cross-process ordering
**NOT VERIFIED**. Existing serial IOSurface correctness tests do not validate
this API. This is a substantiated capability gap, not established desktop
causality. A fake process-local condition/handle would not be a safe fix.
Evidence: [`evidence/ga102-event-handle-capability.json`](evidence/ga102-event-handle-capability.json).

Validation at this milestone: Swift clients compiled and executed; capture
helper compiled with warnings-as-errors; 44 Python regression tests PASS,
including independent per-ID correlations, negative controls and actual-exit
versus validation-exit reporting. Source-only diagnostics are not a deployed
performance fix. Any future deployment needs separate evidence, expected
benefit, risks, rollback procedure and explicit approval; no deployment is
proposed by these findings.

### Follow-up: completion-handler invocation versus client resumption

The next diagnostic was completed rather than stopping at the capture
milestone. `ga102_visual_present.swift::complete` now timestamps commit return,
scheduled-handler invocation and completed-handler invocation on their actual
callback threads, before resuming the awaiting MainActor. The existing real
GPU completion wait, readback ordering and presentation action are preserved.
All clocks are relative; no process identities or pixel buffers are exported.

Three capture-on and three same-binary capture-disabled runs reproduced the
cadence difference. All 720 GPU frame readbacks were correct, all full
visibility samples eligible, and framebuffer error/drop deltas zero. Capture-on
runs each captured all 120 IDs and returned 120/119/118 positive timestamps;
their cadence gate remains **FAIL**. Capture-disabled runs returned 119 each,
passed cadence and remain overall **NOT VERIFIED** for deliberately absent
capture. Per-ID callback traces are complete and CPU ordering consistent.

**Confirmed client scheduling stall:** each capture-on run has one long
frame-16 commit-to-client-resumption interval. Completed-handler invocation is
only 0.289–0.369 ms after commit; subsequent MainActor resumption takes
18.141–18.331 ms. GPU execution is 0.061–0.062 ms. Across steady frames,
completion-handler p95 is 0.358–0.368 ms and p99 0.382–0.386 ms; resumption p95
is 0.029–0.042 ms, p99 0.373–0.389 ms, with the isolated >18 ms maximum retained.
Commit-return p95 is 0.038–0.042 ms; scheduled-handler p95 0.075–0.104 ms.
The three capture-disabled controls have no >5 ms client completion intervals;
resumption maxima are 0.042–0.079 ms. This directly distinguishes the observed
long client wait from a long GPU completion-handler wait. It does not identify
which AppKit/run-loop task or scheduling mechanism blocked the MainActor.

This isolated resumption stall also does **not** explain the sustained
17.5 ms drawable-acquisition wait/33 ms capture-on cadence; those remain separate
observations. SCK interaction with compositor/surface recycling is the leading
capture-specific hypothesis, but no kernel fence or NVKMS fault is demonstrated.
Existing source `nvmtlFinishExecution` still orders presentation before completed
callbacks; measuring a callback is not measuring the raw GPU fence instant.
No mandatory synchronization was changed and no performance fix was deployed.

Evidence: [`evidence/ga102-command-callback-stages.json`](evidence/ga102-command-callback-stages.json).
The independent analysis rejects reversed CPU callback/resumption clocks and
separates callback latency from actor latency; 45 regression tests PASS.
The meaningful next diagnostic is own-client main-queue/run-loop timing around
this repeatable stall, paired with capture metadata timestamps. For the actual
ordinary desktop bottleneck, per-phase WindowServer/NVAccel/NVKMS fence and
flip observations remain unavailable in the installed build; synthetic client
results cannot substitute for them. Source-only counters remain awaiting live
validation, under the unchanged prohibition on replacing active components.

### Follow-up: main-queue delivery and an independently correlated SCK omission

A plain `DispatchQueue.main.async` marker now enters the queue from the GPU
completed handler immediately before resuming the Swift continuation. Three
capture-on and three capture-disabled repetitions completed with correct GPU
pixels, eligible visibility, no missed link ticks and clean error/drop counters.
Capture-on still fails the 60 Hz cadence check; capture-disabled passes that
check and remains overall NOT VERIFIED because capture is intentionally absent.
The marker adds observation work only; it does not change graphics components.

In capture-on runs the long client waits also delay the plain main-queue marker:
18.614–19.246 ms after handler invocation versus 18.619–19.250 ms for MainActor
resumption. Handler invocation itself takes 0.299–0.340 ms after commit and GPU
execution 0.061–0.063 ms for those frames. Without capture, marker maxima are
0.026–0.043 ms. This is evidence of delayed main-queue delivery, not merely a
Swift actor scheduling anomaly or a long observed GPU completion. It cannot
identify whether AppKit flush/surface publication, synchronous system calls,
CPU descheduling or another main-thread task caused it. The stall moves to
frames 12–18 with this extra instrumentation; frame 16 was specific to the
previous binary, not a proven frame-ID-dependent driver failure.

**Concrete capture omission correlated by identity:** the first two runs
capture 119 IDs, omitting frame 4. Frame 4 was submitted, its GPU readback was
correct, and its drawable returned a positive reported presentation timestamp.
Therefore that ID's absence is not explained by lack of submission, bad GPU
contents or unavailable presentation timestamp. It remains absent from the
capture observer. This does not prove physical scanout, but demonstrates why
SCK omission cannot be counted as a measured display drop. The third run
captures all 120. Complete coverage stays NOT VERIFIED for the 119-ID runs;
no records are fabricated or acceptance thresholds relaxed. Early unavailable
positive presentation IDs (1 or 1/2) are tracked separately from missing capture
ID 4. Root attribution between SCK/compositor sampling remains unavailable.

Evidence: [`evidence/ga102-main-queue-markers.json`](evidence/ga102-main-queue-markers.json).
All per-frame main-queue markers were collected; independent analysis checks
CPU ordering, and 46 regression tests PASS. These stages narrow the observer
limitation and reject several incorrect delay explanations. They do not
establish the everyday desktop cause. The next useful runtime observation is
an own-client main-thread/run-loop trace around the capture-specific stall;
identifying an actual WindowServer render-to-flip bottleneck still needs
per-phase fence/flip instrumentation unavailable in the installed driver.
No speculative performance change, wait removal or deployment is justified
by the current evidence.

## Own-client run-loop and AppKit event attribution (2026-10-11)

This continuation made new runtime progress. The ordinary desktop bottleneck
is still NOT VERIFIED; installed graphics components remain unchanged.

The opt-in `ga102_visual_present.swift --runloop-trace` brackets the probe's
main run-loop observers at early/late orders. An early before-wait notification
alone does not prove the thread has slept: other observers may still execute.
The initial all-notification buffer filled at 8192 entries in every run and
is retained as **NOT VERIFIED** for complete tracing. The implementation now
counts every notification but retains only consecutive gaps >=0.25 ms, capped
at 2048. Subsequent three-run capture-on/off controls have no trace overflow.
Event timings retain framework-defined events only, never keys, mouse input,
text, coordinates, event window IDs or other applications' contents.

**Measured location of the isolated queue stall:** approximately 18 ms overlaps
an interval between a run-loop exit and its next entry. It does not overlap the
bracketed before-wait observers. These are wall-time phases, not evidence of
continuous CPU execution or proof of descheduling. Normal frame rendering and
drawable acquisition remain separately instrumented.

A bounded unprivileged `/usr/bin/sample` of only the owned probe (one second,
1 ms interval; three capture-on and three capture-disabled runs) succeeds.
Private reports are not published. The public artifact retains only counts for
an explicit allowlist of public/framework symbol names, with no addresses,
thread IDs, paths or binary-image metadata. All capture-on samples include the
path `NSApplication sendEvent -> NSWindow _windowMoved -> NSCGSDisplayConfiguration
displaysWillChange -> SLSIsDisplayChangedSeedValid -> mach_msg2_trap`, with
15/16/15 sampled observations at the display-seed query. They also show the
known drawable semaphore wait. Aggregate sampling cannot by itself identify
the stack for an exact frame/instant. No private graphics API is called by the
test; these names are observations from its own stacks.

The probe's NSWindow subclass did not capture the late event (only one fast
initial framework event per run), so attributing it directly to that window
would be unsupported. A source-only NSApplication subclass now times its
normal `super.sendEvent` routing, preserving dispatch. In three further
capture-on runs, it processes two framework events, including an additional
**window-moved subtype 4** event lasting 18.348–18.469 ms. That event overlaps
18.129–18.252 ms of the corresponding 18.354–18.480 ms main-queue delivery stall.
The capture-disabled controls process one framework event and have no slow
dispatch span. The event's window-number comparison does not identify it as
the probe window; its precise target is therefore **NOT VERIFIED**, and no
window identifier is exported. A framework method called `displaysWillChange`
is not evidence that the display mode changed. No display-setting API was used.

**Confirmed narrow explanation:** the isolated observed main-queue delay is
largely spent in this application's framework event dispatch. Combined stack
samples support a synchronous display-seed IPC wait inside that path; they do
not identify why the server delays the reply. This is distinct from GPU
execution and from the sustained drawable wait. It is not a demonstrated
ordinary WindowServer defect and does not justify suppressing events, caching
private display state, skipping GPU waits, or replacing active components.
The capture-on steady cadence remains FAIL; capture-disabled cadence remains
PASS with full captured-content validation NOT VERIFIED. GPU pixels and
visibility remain correct with clean framebuffer error/drop deltas.

The optional runner exports scoped phase/event analysis and includes trace
completeness in aggregation: overflow cannot produce a full or repeated PASS.
A further validation defect was corrected: continuous Metal validation must
actually contain all 120 distinct GPU reference frames, rather than accepting
a shortened held-reference run carrying unrelated pacing statistics. This is
a stricter diagnostic gate, not a driver-performance change. Existing live
120-frame evidence meets the count requirement; historical cadence failures
are preserved. Swift compilation of the current probe is successful; 53 Python
regression tests PASS, including overflow, reversed/overlapping clocks,
non-probe event attribution and shortened-run rejection.

Evidence: [`evidence/ga102-runloop-event-attribution.json`](evidence/ga102-runloop-event-attribution.json)
contains exact source hashes, initial partial tracing, subsequent controls,
allowlisted sample counts, event durations and per-frame overlaps. No screenshots
or raw process samples are committed. Next discriminating experiment: measure
public read-only WindowServer query roundtrips under matched capture-on/off
conditions, separating server IPC response latency from local GPU work and
capture pixel sampling. This could establish whether capture perturbs more
than drawable recycling, but still cannot substitute for unavailable
per-phase WindowServer/NVKMS fence/flip instrumentation.

### Follow-up: independent public session-query roundtrips

A separate bounded, unprivileged query child calls the public
`CGSessionCopyCurrentDictionary` 12 times with 125 ms pauses. It exports only
index, elapsed time, dictionary availability and on-console boolean; the
returned dictionary's private values are never printed. Three capture-on and
three capture-disabled probe runs accompany it. The executable compiled with
warnings-as-errors, exits successfully, and all 72 queries have available,
on-console results. Deadlines apply only to owned children. No WindowServer
sampling, capture permission request or system write is involved.

The first call is retained separately because it may include connection/API
initialization. Pooling the remaining 11 calls per run gives 33 measurements
per condition:

| Condition | Subsequent query p50 / p95 / p99 / max (ms) |
| --- | --- |
| Capture on | 1.991 / 7.237 / 8.435 / 8.435 |
| Capture disabled | 0.292 / 5.236 / 5.371 / 5.371 |

First-call latencies are 8.528/1.650/18.284 ms with capture and
1.779/1.681/1.823 ms without it. These sparse p99 estimates are near the maximum,
not robust population estimates. One capture-disabled repetition has several
~5 ms responses, unlike the other two; global activity and request phase are
uncontrolled. The measurements suggest capture-associated IPC latency, but
**do not establish a universal 18 ms delay on WindowServer queries**, explain
the specific private display-seed query, or establish ordinary desktop causality.
This distinction prevents overgeneralizing the event-dispatch stall.

All probe GPU readbacks remain correct and visibility eligible, with clean
error/drop counters. Capture-on cadence remains FAIL (~33.3 ms median), and
capture-disabled cadence passes (~16.7 ms median), while absent capture remains
NOT VERIFIED. Query measurement PASS covers valid API measurements only; it is
not a responsiveness or graphics-acceleration PASS. Evidence:
[`evidence/ga102-session-query-comparison.json`](evidence/ga102-session-query-comparison.json).
Sources: `tools/ga102_session_roundtrip.m`, `ga102_query_analysis.py`;
56 Python regression tests PASS, including missing/inactive query data, invalid
clocks and process failure. Source diagnostic validation is distinct from
installed-driver performance validation. A useful remaining client-level
control is drawable-paced submission versus explicitly waiting for each display
link tick, to determine whether the probe's scheduling combines with drawable
backpressure to create the sustained 33 ms cadence. Any such control must keep
real GPU completion/readback ordering and full frame/presentation gates intact.

### Follow-up: drawable-paced client control

The optional `--drawable-paced` continuous Metal experiment removes only the
probe's extra display-link wait/16.667 ms sleep, allowing drawable availability
to pace its next iteration. Actual GPU completion, shared-buffer readback reuse,
visibility checks and final settling are unchanged. The default linked and
held-reference baselines are preserved; this is not a production optimization.
The runner rejects simultaneous drawable-paced/display-linked options.

Three capture-on and three capture-disabled runs each produce 120 different,
correct GPU references with clean error/drop counters and eligible visibility.
Capture-on still submits at ~33.18–33.31 ms median: acquisition p50 becomes
32.76–32.87 ms instead of ~17.5 ms. Thus eliminating the separate tick wait
moves the time into drawable acquisition rather than restoring delivery rate.
It rules out a duplicated explicit client pacing wait as the *sole* explanation
of sustained 33 ms capture-on delivery. Timing/capture coverage gets worse:
positive timestamps 97/71/98, captured IDs 98/74/100. Reported interval medians
remain 33.27–33.34 ms. Capture-disabled repetitions vary: one has 118 positive
timestamps with clean steady cadence, others return only 57/107 and have an
observed ~50 ms interval. Bursty producer scheduling/callback coalescing remains
a hypothesis, not a measured physical-display drop or accepted workaround.

A validation edge case was exposed: insufficient callback count caused the
existing cadence gate to say NOT VERIFIED even when *adjacent known frame IDs*
had measured >25 ms reported intervals. An additional independent check now
reports those contradictions as FAIL without interpreting a gap across missing
IDs as a measured frame drop. It does not lower the minimum callback/sample
coverage required for PASS. Reanalysis finds 86/70/96 adjacent known intervals
over 25 ms in the capture-on runs, so all three correctly FAIL this additional
check. Original verdicts remain retained alongside the stricter reanalysis.
A skip from ID 10 to 12 alone stays NOT VERIFIED, covered by a regression test.
Bounded independent suite checks may continue after these cadence-only failures
only when real execution, GPU contents, presentation timestamps, visibility and
display error counters are all healthy; FAIL remains in the aggregate.

Evidence: [`evidence/ga102-drawable-paced-control.json`](evidence/ga102-drawable-paced-control.json),
including submitted/captured/timestamp identities and source hashes.
57 Python regression tests PASS; the experimental Swift client compiled and
ran. No installed-driver fix is claimed. The remaining capture-specific
question is whether an independently updating uncaptured client changes the
captured layer's cadence, separating per-layer recycling/capture behavior from
an entire compositor scheduling limit. Real desktop root attribution remains
unresolved, with installed fence/flip phase instrumentation unavailable under
the current no-deployment restrictions.

### Engineering decision: stop diagnostic expansion; gate a synchronization fix

The user's direction supersedes the preceding suggested capture experiments.
No further ScreenCaptureKit, run-loop, AppKit or synthetic presentation runs
were started for this decision. Two local diagnostic files from the preceding
sequence remain parked, uncommitted; they are not a driver performance patch.

**Selected candidate:** serialization of WindowServer rendering and framebuffer
flip completion. `plugin/NVMTLObjects.m::commitAndWaitUntilSubmitted` waits for
GPU completion in WindowServer because NVAccel cannot currently order its swap
after an NVK fence. `plugin/NVMTLEventSync.m::nvmtlFinishExecution` includes
presentation actions before publishing completion.
`kexts/NVRMFB/fb/nvrm-fb.cpp::submitConfig` checks prior primary completion,
applies the request, and waits for submitted completion with 1 ms polling.
This is the release framebuffer source; the nested `kexts/NVRM/fb` duplicate
must not be patched by assumption. These mechanisms establish potential
serialization, **not proven redundant waits**.

**Existing supporting evidence, not a new benchmark:** three already completed
capture-disabled runs paired the Metal client with a separate uncaptured Core
Animation client. All produced 120 correct, different Metal GPU frames, 119
positive presentation timestamps and 240 companion client submissions, with
zero new flip errors/drops. Excluding startup, Metal reported intervals were:

| Run | p50 ms | p95 ms | p99 ms | Intervals >25 ms |
| --- | ---: | ---: | ---: | ---: |
| 1 | 16.701 | 17.303 | 17.541 | 0 |
| 2 | 16.671 | 17.398 | 33.701 | 3 |
| 3 | 16.762 | 33.088 | 33.659 | 8 |

At those late adjacent frames, client commit intervals were approximately
16.3–18.1 ms, acquisition at most 2.36 ms, GPU execution approximately 0.062 ms
and completion callbacks approximately 0.20–0.31 ms after commit. This supports
late delivery after prompt client GPU completion in a multi-client workload
without capture. It does not identify WindowServer's own GPU execution/wait,
NVKMS polling, refresh scheduling or callback reporting as the cause. Companion
submissions do not prove companion presentation. Software cannot establish
physical scanout here. Shared flip-call means were 11.05–12.08 ms; these global
durations include legitimate completion/refresh synchronization and cannot be
assigned to individual late frames. Missing capture frames are excluded from
this argument. Existing sanitized measurements are preserved in
[`evidence/ga102-engineering-decision.json`](evidence/ga102-engineering-decision.json).

**Correction decision:** no performance implementation change is justified yet.
In particular, changing WindowServer to wait only for submission, reducing
completion deadlines, or retiring a surface before verified completion can
expose unfinished pixels or freed memory. IOSurface copy costs have not been
shown to dominate this real path, so a copy or placement optimization is not
selected. Shader-cache correctness work remains source-only and does not prove
an improvement to this presentation symptom.

**One missing experiment:** in an approved maintenance window, use an
instrumented driver build retaining every synchronization and lifetime rule to
correlate WindowServer GPU-wait duration with prior-flip wait, NVKMS apply time
and submitted-flip wait during one fixed everyday desktop animation/scroll
workload, with capture disabled at 3440×1440/60 Hz. Existing source-only
`debug.nvrmfb_completion_*` counters at commit `b6b9505` supply aggregate
prior/submitted wait accounting; they do not yet supply per-frame WindowServer
correlation or prove a wasted wait. The exact missing measurement is how much
of a late frame's critical path is required GPU execution, actual pending
scanout, poll detection latency, or compositor scheduling. No new general
diagnostic framework is proposed and this experiment was not run.

If redundant serial waiting is demonstrated, the correction should transfer
the render-completion dependency to the display submission using a supported
fence, retaining surfaces until actual flip completion. Availability and
correctness of that fence bridge are **NOT VERIFIED**; this is a conditional
design, not a patch ready for deployment. Expected benefit cannot honestly be
quantified until the critical-path measurement exists. A subsequent controlled
baseline/candidate comparison must use the same everyday workload and measure
steady frame-interval p95/p99, counts above 25 ms and input-to-presentation
latency where available. Target: delivery near the 16.67 ms refresh interval,
fewer 33 ms intervals, no correctness or lifetime regressions. Faster synthetic
GPU execution alone would not meet the target.

**Risk, rollback and blocker:** changing this dependency can cause corruption,
tearing, hangs or a black desktop. Source rollback is an ordinary revert;
live rollback must restore the exact retained working 1.11.0 component set
through a prearranged recovery path. That procedure is technically necessary
but has not been tested, and cannot be guaranteed without an approved restart
and recovery window. Existing poll-helper tests passed 39 ASan/UBSan assertions
and SDK accounting checks, but the full framebuffer build remains blocked on
generated `nvkms.h`; no deployable artifact is asserted. No code was installed,
no mandatory wait changed, and no system/display setting changed.

**Status:** measured software delivery excursions **FAIL** the existing pacing
target in two of three runs; actual desktop root cause and physical scanout
remain **NOT VERIFIED**. Selecting and validating a driver performance fix is
**BLOCKED** by missing live critical-path evidence and the current prohibition
on replacing active graphics components/restarting the session. A performance
A/B test is necessary once a supported fix exists; an instrumentation-only
live run must precede it. No installation approval is requested for an
unbuilt/unvalidated candidate. This cycle ends at that decision rather than
starting another client-side diagnostic sequence.

### Build remediation — 11 October 2026

Resumed with build remediation only; no presentation/performance experiments
were run. Corrected the earlier diagnosis: NVIDIA tag `610.57.04`, commit
`e4a5faa2567f28c8eabe0ebb6422b6d0abcf37eb`, contains the real header at
`kernel-open/nvidia-modeset/nvkms.h`. It includes `nvkms-kapi.h` from
`kernel-open/common/inc`. Both paths were missing from the earlier syntax check.
Neither generation, fabricated declarations nor stubs are required.
Upstream source: [NVIDIA 610.57.04 header](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/e4a5faa2567f28c8eabe0ebb6422b6d0abcf37eb/kernel-open/nvidia-modeset/nvkms.h).

Added `build/build_display.py`: accepts explicit vendor/output directories,
pins the vendor revision and rejects tracked vendor edits or existing output.
It compiles and links the actual release-path NVRMFB, NVAccel and NVRMAGDC into
new, isolated kext bundles. Optional Vulkan headers also build the NVMTL release
binary with `NVMTL_RELEASE=1`. No root operations, installation, loading,
signing-policy changes or live graphics replacement occur. Proof records source
revision/input hashes, vendor revision, SDK/compiler, configuration and binary
hashes without personal paths. This is a build remediation, not an optimization.

**Verified:** all three kexts compile and link as x86_64 Mach-O kext bundles;
two independent builds yielded byte-identical kernel binaries. The final command
also linked the release NVMTL bundle binary, with no strong dynamically looked-up
symbols. NVMTL bundle packaging/loading is not verified. Existing-output refusal
passed. Existing completion helper passed 39 ASan/UBSan assertions; compiled
framebuffer contains the actual `nvrmfb_completion_*` counters. Existing compiler
warnings remain; this is not a warnings-free qualification.
Evidence: [`evidence/ga102-release-build-remediation.json`](evidence/ga102-release-build-remediation.json).

**Complete release: NOT VERIFIED / remaining build gap.** The upstream command
`make -C src/nvidia-modeset -j2 TARGET_OS=Darwin TARGET_ARCH=x86_64` stops at absent
`xz`. Independently selecting `_out/Darwin_x86_64/nvkms-kapi.o` fails the real
`nvUnixVersion.h` platform guard and leaves `NV_VERSION_STRING` undefined.
Do not spoof Linux/BSD macros to silence that guard. Upstream shader embedding
uses ELF/GNU `ld -r -z noexecstack --format=binary` and `objcopy`; the required
Darwin Mach-O adaptation is not in this checkout. The stock target produces
`nv-modeset-kernel.o`, not the Darwin `libnvkms.a` consumed by our archive helper.
The repository contains no complete NVRM/vendor Darwin archive producer;
`rmcc.py` and `build-completion-archive.py` consume previously built Darwin
`compile_cmds.sh` and archives. These inputs are absent, not generated by the
documented `accel_build.sh` (which builds NVAccel alone).

The correct dependency sequence is: recover/implement the pinned Darwin vendor
build recipe → build matching RM and modeset archives/compile commands → run
`build-completion-archive.py` for the completion-patched modeset archive → build
and link NVRM plus the matched display components → build the patched Mesa NVK
and translator → assemble and verify the complete release. Rust, Meson/Ninja,
the documented Mesa/build trees and original Darwin archives are absent here;
the active tools are Command Line Tools, not full Xcode. No complete release or
deployable matched NVRM set is claimed from the successful component builds.
The immediate next source-build task is obtaining the upstream Darwin archive
recipe/patches or explicitly reconstructing that port, not another GPU test.

**Optimization readiness:** the existing instrumentation-only framebuffer is
now compiled and linked with its mandatory 100-query/1 ms completion waits,
fault latch and surface lifetime rules intact. No performance wait was shortened
or removed. This is the smallest existing candidate for flip-phase evidence,
but it cannot be deployed as a qualified standalone replacement before matching
NVRM/archive provenance and complete build qualification. WindowServer's own
render-wait attribution is still missing. No quantified desktop benefit is claimed.

**Installed baseline and rollback prerequisites:** read-only on-disk metadata
reports version `0.1` for all four installed kexts and the NVMTL bundle; binary
SHA-256 identities are recorded in the evidence. Thus “working 1.11.0” remains
the user's package identification, not a version inferred from these plists;
on-disk files alone do not prove which exact bytes are loaded. Preserve the
original working installer and back up the entire matched four-kext, plugin,
NVK/translator set locally before any approved deployment, verifying hashes
against this baseline. Ensure a tested external recovery route that can restore
those components if the desktop cannot start. No EFI-dependent recovery route is
assumed ready. Restoring the matched set and rebuilding the kernel collection
requires separately approved privileges/restart; no such steps were executed.
Black-screen/boot failure, unresolved kernel symbols, GPU hangs and render
corruption remain live risks despite successful component linking.

A later approved baseline/candidate comparison must hold 3440×1440/60 Hz and
the same everyday animation/scroll workload fixed, with capture disabled,
comparing frame pacing tails and >25 ms intervals alongside corruption/errors.
The candidate must first explain the selected critical-path wait, then preserve
ordering while measurably reducing it. **No live deployment approval is requested
yet:** the complete release and recovery prerequisites are not ready.

### Authentic dependency search and minimal candidate — 11 October 2026

Bounded search covered local build/cache/download/application-support artifacts,
all local Git history, upstream main and relevant support branches, upstream
1401 tree and release listings. No Darwin archive producer, `compile_cmds.sh`,
`libnvkernel.a` or `libnvkms.a` was found in those sources. The initial commit's
only `libnvkernel.a` reference is `rmcc.py` consuming prior build commands.
This establishes unavailable inputs in the searched published/local material,
not proof that the author lacks them or that they are proprietary. Stop
speculative port reconstruction. Missing inputs remain the authenticated
610.57.04 Darwin vendor patches/build recipe, paired archives/compile commands
and complete NVRM link/packaging command. A full NVRM/Mesa source build remains
**BLOCKED**, and no complete source-built release is claimed.

**Concrete alternative:** downloaded the authentic
[NullMoth v1.11.0 release](https://github.com/nullmoth/nvidia-macos-driver/releases/tag/v1.11.0),
verified SHA-256 `6e568e28ee34c3b41f4dfda980fd8feb50fdd0a69cf6d0f6e54338873b8ec2e7`
against GitHub's asset digest, and checked its 100 archive members. It contains
finished NVRM/NVK/translator/Metal binaries, no build archives or recipe. The
locally retained original installer has the same digest. Of 39 regular payload
files compared under Extensions/GPUBundles, 38 match installed on-disk files.
Only `nvrm610.conf` differs; its contents are neither published nor replaced.
These checks do not establish exact loaded bytes or physical runtime behavior.

Pinned release source is `e404ab30b94d6588bdf63b3724d59f1e713ad963`.
All 82 corresponding existing kernel inputs except the instrumented framebuffer
translation unit match our checkout, including shared VRAM/GPUVA/surface ABI
headers, NVAccel implementation and `610-display-completion.patch`. NVRM's
published binary contains 610.57.04 identity strings. Keep this matched prebuilt
core and user-space stack fixed rather than mixing an unqualified reconstructed
RM with our framebuffer.

Resolved missing `xz` locally using `build/compress_nvkms_shaders.py`, a narrowly
scoped equivalent of the exact upstream `-ce -C none` invocation. Python LZMA
uses XZ format, preset 6/extreme and CHECK_NONE. The real upstream Ampere shader
target built; decompression reproduced every source byte and confirmed CHECK_NONE.
No system tool install or shader replacement occurred. This removes an ordinary
tool blocker, not the absent Darwin port/ELF-to-Mach-O recipe.

**Prepared artifact:** `build/prepare_fb_candidate.py` verifies the published
release digest, pinned clean baseline source, unchanged shared kernel inputs,
current built kernel-input hashes and framebuffer binary proof. It creates a
new offline candidate bundle plus the original rollback bundle, and refuses
existing output. It copies no replacement Metal/NVK/NVRM binaries and no graphics
configuration. Candidate uses the existing completion-observability change from
`b6b9505`; its 100-query/1 ms sleep contracts, query-failure behavior, fault latch
and surface pinning are preserved. Read-only prior/submitted wait counts,
durations, poll/sleep totals and long-tail counters enable the selected flip-wait
measurement. This does not directly measure WindowServer GPU waits or constitute
a performance optimization. Accounting overhead and loaded behavior are untested.

Static validation: x86_64 Mach-O kext, rollback binary byte-identical to installed
on-disk framebuffer, 82 matching baseline kernel inputs, verified candidate hash,
existing-output rejection. Compared undefined imports add only
`_absolutetime_to_nanoseconds`, already imported by the installed driver set;
none are removed. Kernel-loader compatibility is **NOT VERIFIED** by that check.
The earlier repeated component build and 39 sanitizer assertions remain the
correctness baseline; no GPU or presentation experiments were repeated.
Evidence: [`evidence/ga102-authentic-baseline-candidate.json`](evidence/ga102-authentic-baseline-candidate.json).

Candidate and rollback bundles are retained locally in
`/private/tmp/ga102-fb-instrumentation-candidate/`; this temporary location must be
copied to durable recovery media before deployment. Reproduce assembly after the
documented component build using:

```bash
python3 build/prepare_fb_candidate.py --release /path/to/nullmoth-nvidia-1.11.0.tar.gz --release-source /path/to/clean/v1.11.0-source --display-build /path/to/display-build --output /new/candidate-directory
```

**Next approval decision:** authorize a supervised maintenance window, first
confirming a tested external recovery route, APFS access/unlock credentials and
a durable copy of the original working installer/rollback bundle. Only after
that prerequisite is met should a separately approved single-framebuffer
replacement, privileged kernel-collection rebuild and necessary reboot be
considered. No hot swap or graphics-service restart is proposed. Rollback must
restore the original entire NVRMFB bundle and required owner/modes, rebuild the
appropriate kernel collection and restart; if boot fails, do this from the
prevalidated recovery environment. The installer and byte-identical rollback
binary are verified; recovery boot/access/rebuild remains **NOT VERIFIED**.
Do not assume an EFI uninstall entry exists or alter EFI to create one.

With approval and recovery in place, run one fixed everyday animation/scroll
workload at unchanged 3440×1440/60 Hz with capture disabled, collecting counter
deltas against existing frame-pacing evidence. Distinguish prior from submitted
completion waits and detect query failures/exhaustion. If legitimate pending
scanout dominates, retain the waits; a large wait alone is not wasted work.
This measurement gates any later supported fence/polling optimization and its
baseline/candidate comparison. No source performance benefit, live fix or safe
boot guarantee is claimed. No installed component or system setting changed.

Candidate retention update: copied all five candidate/rollback/proof files to
`~/Developer/ga102-release-artifacts/daa4210-framebuffer` outside temporary storage
and verified every copied SHA-256 against the prepared artifacts. This is durable
local retention, not tested external recovery media. No installation occurred;
live approval and recovery-access verification remain outstanding.

### User-authorized recovery USB preparation — 11 October 2026

The user authorized a recovery checklist and original-driver backup on the
existing installer USB, and confirmed FileVault is disabled. The connected USB
was identified as external USB storage with a writable FAT32 volume. Created
only a new `GA102-Recovery` folder on its data volume; no EFI/OpenCore or recovery
boot file was changed. Content-hash comparisons of both protected trees passed.

Ten backup/checklist/manifest files were copied and hash-verified, including the
authentic original 1.11.0 installer, original framebuffer archive, current
auxiliary kernel collection, private current driver configuration backup and
recovery hash manifests. The collection was inspected read-only and contains
all four NullMoth kext identifiers. The recovery archive preserves required
ownership/mode metadata even though FAT32 does not. Private configuration,
collection bytes and system manifests remain on the USB/local backup only; none
is committed. Public evidence records preparation outcomes only:
[`evidence/ga102-recovery-usb-preparation.json`](evidence/ga102-recovery-usb-preparation.json).

[`GA102-RECOVERY-CHECKLIST.md`](GA102-RECOVERY-CHECKLIST.md) documents separately
approved recovery, correct APFS System/Data selection, dependency hash gates,
backup of failed artifacts and restoration of the original bundle and saved
auxiliary collection. Cached rollback follows the actual Intel installer's
publication path and avoids assuming a Recovery/KDK rebuild succeeds. It is a
technically justified plan, not a boot-tested guarantee. The USB previously
booted the installer according to the user; access to the current Sequoia Data
volume, write access and actual rollback boot remain NOT VERIFIED.

Preparation is PASS. No candidate was copied to the USB, installed or loaded;
no sudo, reboot, service restart, display change or system-permission change was
performed. Live testing still requires separate approval and confirmed recovery
access. The USB folder is ready; this authorization was preparation only.

### Approved live-test handoff — 11 October 2026

The user explicitly approved replacing only NVRMFB, privileged auxiliary
collection preparation and a reboot, and asked not to repeat approval requests.
The user's assurance that the existing USB boots Recovery is accepted. EFI,
OpenCore, SIP, login security, display configuration and loaded graphics-service
replacement remain outside the test scope. Actual Recovery Data-volume access
and rollback boot remain untested risks, not additional approval requests.

`sudo -n true` returned “a password is required.” No privileged mutation occurred.
This is an administrator-authentication limitation of this tool session; no
password is requested through chat and sudo policy is not changed.

Prepared `tools/ga102_deploy_framebuffer.py` for one authenticated Terminal
invocation. Read-only preflight verifies pinned candidate/plist hashes, original
on-disk framebuffer, USB rollback/collection/manifests, unchanged dependency
files and boot/system collections. Preflight PASS. Five bounded tests PASS: exact
UUID/component matching, successful publication with both originals retained,
and injected failures after original save, bundle publication and collection
publication, all restoring original files in temporary directories. These test
file transactions; they do not prove root execution, kernel linkage or boot.

After authentication, the helper acquires the existing installer lock without
bypassing/removing an existing lock; stages all installed kexts with only the
framebuffer changed; uses the authentic installer's auxiliary-only build method;
inspects the new collection and requires the UUIDs of all four staged NullMoth
binaries. It rechecks the installed repository and baseline before publishing.
The original framebuffer and collection are retained under
`/Library/GA102-Framebuffer-Test`; publication failure preserves failed artifacts
and restores originals. Status/logs remain local. Only after successful
publication does `--reboot` schedule the approved restart one minute later.
No driver load/unload, EFI/Preboot edit, security-setting change, display change
or graphics-service restart is performed. The original installer's
`--allow-missing-kdk` and `-z` flags are used solely for the approved offline
auxiliary build against the existing kernel/boot/system collections; they do
not modify system security policy or omit kernel linkage/UUID validation.

**Current status:** deployment command is prepared, SOURCE VALIDATED for the
stated preflight/publication tests only. Actual candidate collection build,
installation, reboot and INSTALLED DRIVER validation are pending Terminal
administrator authentication. The agent has not installed anything or rebooted.
After restart, inspect the helper's local `status.json`, verify loaded framebuffer
UUID against the pinned candidate and read actual completion counters before
using the one agreed capture-disabled desktop workload. An installed file hash
alone will not be called proof that the new framebuffer is loaded. No
performance improvement is claimed from this instrumentation-only candidate.

### Live boot failure and rollback handoff — 11 October 2026

**FAIL: boot/stability acceptance.** The user ran the approved deployment helper;
its saved status and on-disk hashes confirm candidate publication. The user then
reported a stuck boot and recovered access to macOS using the existing OpenCore
USB. This does not identify whether the framebuffer binary, auxiliary collection
or boot configuration caused the failure. No performance improvement is claimed.
Do not repeat deployment or start performance workloads in this recovery state.

Read-only checks after recovery found the candidate framebuffer still installed
on disk, both original backups matching their pinned hashes, no NullMoth kexts
listed by `kmutil showloaded`, and the new completion counter unavailable. The
current session therefore cannot validate candidate acceleration. No EFI,
OpenCore or security changes were made by the agent to recover the boot.

`tools/ga102_rollback_framebuffer.py` restores only the original NVRMFB bundle
and saved auxiliary collection, preserving both pre-test backups and failed
candidate files. It checks pinned hashes and unchanged system/driver dependencies,
uses the existing tested transactional publication routine, and schedules no
reboot or kext loading. Read-only rollback preflight PASS; the five publication
regression tests PASS. This is not proof of successful rollback boot.

Administrator authentication is unavailable to the tool session (`sudo -n`
requires a password). Actual restoration therefore awaits one Terminal command;
no additional permission request is necessary. Original internal-disk boot remains
NOT VERIFIED until restoration and a later user-directed restart. Root-cause
analysis is deferred until the known working installation is restored; neither
successful linking nor static collection inspection established boot compatibility.

### Rollback rejected by SIP — 11 October 2026

The user executed the rollback helper with administrator authentication. Collection
replacement failed with EPERM. Read-only inspection confirms SIP enabled and
`restricted` flags on the auxiliary collection and its parent directory. Root
authentication does not establish permission to publish into this protected path.
No security policy or file flags were changed to bypass this restriction.

Post-failure hashes confirm the transactional failure handler restored the
pre-rollback candidate bundle and candidate collection. Both pre-test originals
remain intact at their pinned hashes in `/Library/GA102-Framebuffer-Test` and
the USB backup remains available. The helper's `Rollback/FailedCandidate.kext`
actually contains the attempted original bundle in this reverse transaction;
that generic filename is not evidence of its binary identity. Hashes establish
identity. Live rollback has NOT succeeded; normal internal boot is NOT VERIFIED.

The live rollback helper now rejects Darwin SF_RESTRICTED on either collection
or parent before moving a bundle. No retry, kext load, reboot or further
performance experiment is appropriate in the current session. Restoration must
use the existing USB Recovery checklist with verified Sequoia System/Data paths,
original framebuffer and original saved auxiliary collection. If Recovery also
rejects writes, stop rather than disabling SIP, clearing flags or improvising
security changes. Recovery restoration and successful original boot remain
BLOCKED on execution outside the running OS. The prior preparation was insufficient
to guarantee live rollback under the USB-booted session's security policy.

### Authorized recovery escalation

The user explicitly authorized SIP changes and necessary recovery work. This
supersedes the previous prohibition on changing SIP for this recovery; it does
not establish that broader security changes or another candidate deployment are
needed. Local `csrutil` usage confirms disabling/enabling SIP is available only
in Recovery OS. The agent cannot enter Recovery while retaining this live session.

Prepared `tools/ga102_recover_original.sh` and copied it, hash-verified, to the
existing USB backup as `RESTORE-ORIGINAL.sh`. Shell syntax validation PASS;
Recovery execution NOT VERIFIED. The helper takes explicit System/Data mount
paths, requires matching APFS volume groups, refuses the active OS Library,
verifies backup and unchanged dependency manifests, preserves pre-restore files
in a fresh directory, restores only original collection/framebuffer and verifies
their hashes. It does not alter EFI/security policy, load kexts or reboot.
If Recovery denies collection writes, the user's authorization permits
`csrutil disable` in Recovery and returning to Recovery after restart before
retrying restoration. No authenticated-root change is justified. Restoring SIP
after successful recovery is a separate recovery step; OpenCore boot policy may
affect effective SIP state, so the command alone cannot prove the next boot's
security state. Normal original-driver boot remains NOT VERIFIED.

### Recovery confirmed; failed candidate retired — 11 October 2026

**Original stack restoration PASS. Experimental boot/stability FAIL. No further
live deployment authorized.** The user reports successful normal SSD OpenCore
boot after restoring the saved original framebuffer and auxiliary collection.
USB OpenCore had permitted OS access without the NVIDIA stack (generic 22 MB
graphics), so that session was not evidence of candidate acceleration or a
working NVIDIA boot. The following read-only checks now independently confirm
the restored desktop's driver identity:

- All four NullMoth kexts loaded: NVRM, NVAccel, NVRMAGDC and NVRMFB.
- Loaded NVRMFB UUID `CC151F75-1305-3928-AA0F-B8BC96EF30A3`, the original;
  candidate UUID `9E00EE15-E50D-3106-A8C1-8B6D053962E9` is not loaded.
- Installed framebuffer SHA256
  `a2a3cf961df1aae872d500142b8c146ecd660a369f364d843f42c3fb4bd21e71`;
  installed auxiliary collection SHA256
  `362eb218919f7783440035cf19f02fb05b73a749836fa942e8a9b90f1d973526`.
  Both equal the pre-test baseline. Original framebuffer, unchanged driver
  components and base-system manifests all PASS.
- System profiler recognises RTX 3080 Ti, device `0x2208`, PCIe x16,
  12 GB VRAM and Metal 3.
- One existing bounded compute test PASS (2, 4, 6, 8); one existing offscreen
  render test PASS (RGBA8 64, 127, 191, 255). Both explicitly identify
  NVMTL over NVK GA102-A. These establish restored scoped GPU correctness,
  not physical scanout verification or smoothness/performance improvement.

**Actual recovery:** user entered USB Recovery, ran `csrutil disable`, still
encountered a rejected live restoration, then returned to USB Recovery and ran
`GO.sh`. Inspection of the saved script shows it copied the original collection,
restored the original framebuffer archive and ownership before its final `cmp`
checks. Recovery lacked `cmp`, so those final checks did not run. The successful
SSD boot and current full-file hashes now provide the missing verification.
The prepared shell helper also depended on `shasum`, which was unavailable in
the user's Recovery environment. Desktop utility availability is insufficient
to qualify a recovery plan. Its required utilities are now explicitly checked
before any mutation; Recovery execution remains unqualified if a dependency is
missing. No new Recovery deployment framework is being developed.

**Effective security:** current `csrutil status` reports a custom configuration:
kext-signing, filesystem and NVRAM protections disabled; debugging, DTrace and
BaseSystem verification enabled. This is neither fully enabled nor a blanket
disabled result. Separate `csrutil authenticated-root status` reports disabled;
this is distinct from the BaseSystem-verification line. Its pre-test state is
not established, and no agent change was made. Current `csr-active-config`
decodes to `0x0a43`. The earlier
fully enabled observation came from USB OpenCore and cannot establish the prior
SSD configuration. The original effective SSD security mask was not recorded
before deployment. SSD OpenCore policy affecting effective SIP is a hypothesis;
no SSD EFI configuration was mounted or changed. Do not blindly run
`csrutil enable`: the original unsigned driver stack's required policy must be
established from the SSD OpenCore configuration and a trustworthy pre-test
backup before proposing a change. Current policy remains unchanged by the agent.

**Offline failure evidence:** inspection of original and failed collections
finds the same six kext identifiers; all UUIDs except NVRMFB match (the collection
UUID also changes). Build log contains only release-variant notices, no captured
link/build error. No panic report is available in the system diagnostic-report
directory. Returning the original bundle and collection restored normal SSD
boot, implicating the experimental package, but does not isolate rebuilt
collection/runtime linkage from replacement framebuffer behavior. Both changed
together. Matching source inputs, UUIDs, compile success and collection inspection
did not establish binary ABI, initialization or boot compatibility. Neither SIP
nor OpenCore is proven to have caused the initial hang; SIP protection is proven
to have blocked live rollback. Runtime initialization/sysctl instrumentation,
compiler/SDK compatibility and collection construction remain hypotheses,
not diagnosed defects. A boot transcript/panic or an independently qualified
unchanged-baseline build is needed before assigning a specific cause.

Preserved `/Library/GA102-Framebuffer-Test`, original backups and failed binaries;
made an additional local copy at
`~/Developer/ga102-release-artifacts/failed-live-20261011`, verified every copied
deployment file's hash and saved the actual USB `GO.sh`. Raw logs, private paths,
configuration and binaries stay local. Original backups and USB evidence were
not overwritten. The failed deployment helper now refuses non-check execution
before root operations; candidate is retired. Existing five publication tests
PASS and Recovery-helper shell syntax PASS. Those checks still do not qualify
boot/recovery behavior.

**Next safe engineering work:** review the replacement binary's initialization
and ABI differences against the authentic framebuffer and qualify an isolated,
unchanged-baseline build/collection before considering instrumentation changes.
Resolve Recovery utility availability and protected-file rollback on the exact
target environment before any future deployment proposal. Preserve the mandatory
render-to-scanout waits. The existing shader-cache correctness patch remains
source-only; user-space correctness/build work is the safer optimization route
while kernel boot compatibility remains unresolved. No new performance fix,
installed collection build, security change, reboot or live experiment is approved
or performed. Desktop performance improvement remains NOT VERIFIED.

### Focused offline baseline control — 11 October 2026

Previous recovery verification was progress: it established the actual loaded
original stack and correct GPU results. This continuation performed no live
presentation/performance experiment. Its single control rebuild asks whether
binary layout differences are specific to the completion instrumentation.

Restored the exact NVIDIA 610.57.04 checkout at
`e4a5faa2567f28c8eabe0ebb6422b6d0abcf37eb` in durable local artifact storage;
the prior `/private/tmp` vendor checkout was gone after restart. Exported the
authentic v1.11.0 `kexts` tree from
`e404ab30b94d6588bdf63b3724d59f1e713ad963` into an isolated artifact directory.
Used the display builder's actual compile/include/link flags to compile and
link only this unchanged NVRMFB source, with existing SDK/compiler. No driver
or collection was installed or loaded; no system collection was built.

**SOURCE BUILD PASS; RUNTIME COMPATIBILITY NOT VERIFIED.** Unchanged-source
binary SHA256:
`8cfe426c3987b7b55f8538fd6c21b6dddd36a66adc25dbeedda336517de11ac4`.
Its undefined-import set and external-definition set both exactly match the
authentic installed framebuffer. Its constructor and destructor tables each
contain one 8-byte entry, as do the authentic binary and failed candidate.
Vtable/constant-section size, writable-data size and BSS size match the authentic
binary. Text size differs (`0x114be` rebuilt versus `0x112ae` authentic), and
the linker places `__got` before the initialization tables rather than after
the writable data. The same ordering appears in the failed candidate. Therefore
that section-order difference is not instrumentation-specific. Neither section
order nor text-size difference is proven invalid or causal.

The failed candidate adds only one undefined import,
`_absolutetime_to_nanoseconds`; the loaded original NVRM already imports it.
No existing external framebuffer definitions are removed. Its additional
exports are the ten completion sysctl records. SDK `sys/sysctl.h` explicitly
requires manual `sysctl_register_oid` calls for IOKit/kext sysctls; that pattern
was already used by the baseline. The diff preserves the 100-query/1 ms-sleep
completion contract, fault handling and pinned-surface lifetime. These facts
exclude an obvious missing-import, additional-init-entry or deliberately
removed-wait explanation; they do not prove the timing calls, registration or
binary work correctly during boot.

All outputs, exact commands, symbol/section comparison and restored vendor
sources remain under local `ga102-release-artifacts` storage, outside the public
repository. No private build commands/paths or raw diagnostics are published.
No source optimization is justified by these observations. Before further
kernel experimentation, obtain the authentic release compiler/linker recipe
or explain the unchanged-source binary differences and acquire boot-stage
evidence sufficient to distinguish initialization from collection linkage.
The failed candidate remains retired; the working baseline remains untouched.

### Bounded retained-log check

The preceding unchanged-source control rebuild was progress, not runtime
validation. One read-only retained unified-kernel-log query was then attempted
to obtain the missing boot-stage evidence without another live experiment.
The query filtered only NVRM/NullMoth/kxld messages and had a 25-second deadline.
It timed out; incomplete JSON was retained privately alongside the existing
failed-deployment evidence. Review decoded 42,028 complete entries from the
partial output. They contained no explicit kxld/unresolved-import, vtable,
panic or presentation-completion-fault messages and no candidate UUID mention.
Only one boot identity occurred and it was not the current recovered boot.
Coverage of the failed boot could not be established. These observations do
not prove that the failed boot lacked errors, reached driver initialization,
or even persisted relevant logging. No raw log content or boot identifiers are
published. No repeated or broader log query is planned.

This specific failure-attribution experiment is **BLOCKED** on reliable failed-
boot evidence or authentic build provenance. A new live boot is not authorized,
and no kernel source correction is substantiated by the available observations.
The full desktop-optimization objective remains incomplete; this boundary must
not be disguised as success or used to restart synthetic presentation research.

### Bounded build baseline and user-space cache correction

The user resumed development with two specific offline objectives, retaining
the prohibition on installation, live replacement, reboot and system/security
changes. This cycle did not repeat GPU/presentation benchmarks or construct
another diagnostic framework.

**Unchanged NVRMFB reproducibility PASS. Authentic runtime compatibility NOT
VERIFIED.** Replayed the saved compile/link commands for the authentic v1.11.0
source into a second isolated output directory. The two binaries are byte-for-
byte identical, SHA256
`8cfe426c3987b7b55f8538fd6c21b6dddd36a66adc25dbeedda336517de11ac4`,
UUID `2B261484-77F7-32BB-BB87-D43DCCE70AEA`. The working authentic release has
SHA256 `a2a3cf961df1aae872d500142b8c146ecd660a369f364d843f42c3fb4bd21e71`
and UUID `CC151F75-1305-3928-AA0F-B8BC96EF30A3`. Imports/exports, initializer
counts and relevant data sizes match; text and section ordering differ as
documented above. Local settings are Apple clang 17.0.0, SDK 15.5, x86_64,
O2, kernel/kext flags, NM_TAHOE unset. UUID agreement between repeated builds
proves local determinism, not equivalence to the working binary.

Read the authenticated v1.11.0 archive's installer without executing it. Its
auxiliary construction uses `kmutil create -n aux --volume-root /`, existing
Boot/System collections, `--allow-missing-kdk`, optional existing kernel,
`--repository`, output `-A` and `-z`, matching the experimental helper's main
construction flags. The original installer stages four NullMoth kexts for its
preflight and uses the installed extension repository for final construction;
our failed collection used the staged installed repository. Existing inspection
establishes the same six component identities and only a changed NVRMFB UUID.
This does not prove equivalence of collection linkage, fixups or boot behavior.
No new collection was constructed during this cycle. Exact original release
compiler/linker settings and successful unchanged-rebuild runtime compatibility
remain missing. That is the precise compatibility blocker; stop reconstructing
the baseline here rather than claiming the deterministic local build is trusted
for deployment. Full NVRM archive/source-build limitations remain unchanged.

**Selected user-space improvement: cache-directory selection correctness.**
Review of the existing Mesa policy correction found two related remaining
problems:

1. `nvmtl_mesa_cache_configure` accepted empty HOME, constructing
   `/Library/Caches` instead of using the supplied Darwin fallback. This can
   select a different shared namespace and made the purportedly isolated test
   depend on host permissions. The first test run reproduced the defect and
   created an empty directory there. Only that newly created, user-owned empty
   fixture was removed; no pre-existing cache contents were deleted. HOME must
   now be absolute and nonempty; explicit cache policies remain unchanged.
2. `nvmtl_aircache_dir` used `access(W_OK)` for automatic cache selection.
   Writable files and directories lacking search permission pass that predicate
   although child cache files cannot be accessed. The shared cache header now
   provides `nvmtl_cache_directory_usable`; AIR's global, user and Darwin checks
   require a directory with write/search permission. Legitimate AIR directory
   symlinks remain supported via stat; Mesa's existing final-symlink rejection
   remains unchanged. Explicit AIR overrides and the last-resort path behavior
   are unchanged. No GPU ordering, pipeline format or shader key changes.

Validation of final source: **SOURCE VALIDATED for these cache checks**, 51
production-code assertions in each of three fresh-fixture ASan/UBSan runs.
Negative cases demonstrate the old write-only predicate accepting both a file
and an unsearchable directory, while the new check rejects them. Tests cover
valid directories/symlinks, null paths, empty/relative HOME, Darwin fallback
and preservation of explicit Mesa policy. They exercise production C policy
and AIR's new predicate, not execution of the complete installed AIR selector
or Mesa compiler cache hits.

Isolated release NVMTL plugin compiles and links, x86_64/O1/NVMTL_RELEASE=1,
Apple clang 17.0.0, SDK 15.5. Vulkan-Headers revision pinned in local evidence:
`c46850864f4661461b0f6cb9922c058ffea4915e`. Final binary SHA256
`20da21ae0c8db59f8bf004423e570e6d0c9aeab40408b99f905e3ebecef376d8`.
Direct library dependencies are Foundation, Metal, IOSurface, CoreFoundation,
libobjc and libSystem; no artifact-directory library dependency. Private logs,
commands and artifacts remain local. No bundle was installed or loaded.

**Performance benefit NOT VERIFIED.** This is a concrete cache-persistence/path
correctness correction, not a measured optimization. It removes invalid
automatic choices that can prevent reuse, but no shader compilation or real
desktop latency improvement has been measured. Future candidate validation
would need actual cache stores/hits and repeated library/pipeline latency on
matched shader inputs before claiming benefit; installation is not authorized.
The safe cycle ends with a reviewable user-space source change and a precise
kernel compatibility blocker. The working original stack is untouched.

### Isolated AIR cache A/B: measured fault-case benefit

Continued with the proposed focused comparison after the user challenged the
premature handoff. No candidate graphics plugin was loaded. An ordinary owned
Metal compute library was compiled on the working driver; its original AIR
bitcode was exported through NVMTLLibrary's `_fns` ivar. The exporter requests
no queue, pipeline or command-buffer submission; creating a Metal device still
initializes the installed driver. This is not installed-candidate validation.
Reassembling printed AIR with the installed air-opt initially failed on newer
`captures(none)` syntax. The comparison instead uses original exported bitcode
unchanged; no IR syntax was rewritten.

`tools/air_cache_tests/cache_ab.py` compiles extracted production selectors and
the unchanged AIR decoder as standalone CPU programs. Old selector: `0176303`;
corrected selector: `96864e4`. Foundation directory search is redirected to
owned fixtures. The original CPU LLVM runtime is loaded read-only via a local
path symlink; its direct dependencies are ordinary CPU libraries. No NVK/NVRM
or candidate Metal plugin entry points are included in these executables.
Only logging is quieted; parsing and disk cache operations are production code.

Three fresh processes per condition/variant, fresh cache each time, 21 calls
per process. Checks require the owned shader entry, identical IR within each
process, matching IR SHA256 across all variants/processes and exact hit/miss/
store counts. A fourth process reuses the last cache to test disk persistence;
its single first-call measurement is not a latency distribution.

| Condition / selector | Hits / misses / stores per fresh-cache process | Warm p50 / p95 (ms; 60 samples) | First call in cache-reuse process (ms) |
|---|---|---|---|
| Valid directory / original | 20 / 1 / 1 | 0.0217 / 0.0431 | 0.0551 |
| Valid directory / corrected | 20 / 1 / 1 | 0.0206 / 0.0365 | 0.0587 |
| Writable file / original | 0 / 21 / 0 | 0.1498 / 0.2801 | 36.6381 |
| Writable file / corrected | 20 / 1 / 1 | 0.0210 / 0.0359 | 0.1051 |

**PASS: identical output and cache persistence.** Under the deliberately
invalid writable-file path, the fix restores caching and reduces repeated AIR
decode/cache-lookup p50 by about 7×. The separate reuse process has 21 hits and
no misses with the correction, versus 21 misses originally. First fresh-cache
calls cost roughly 34–40 ms in both versions, including CPU LLVM initialization.
This measures AIR decoding/cache lookup, not Vulkan pipeline compilation,
Metal front-end compilation or frame latency. Healthy-directory hit counts
agree; no healthy-case speedup or statistical equivalence is established.

The invalid path was induced under the test directory, not observed in the
running WindowServer. **Normal desktop improvement remains NOT VERIFIED.**
Numeric evidence: `docs/evidence/ga102-air-cache-ab.json`. Raw samples, generated
source and owned shader remain in durable local artifact storage. No desktop
data, screenshots or private system logs are published. No capture experiment,
installed-component, security, EFI, display or reboot change occurred.

Reproduction (ordinary user; new paths; stop if an exporter command fails):

```sh
CACHE_AB_DIR=$(mktemp -d)
xcrun clang -fobjc-arc tools/air_cache_tests/export_fixture.m -framework Foundation -framework Metal -o "$CACHE_AB_DIR/export"
"$CACHE_AB_DIR/export" "$CACHE_AB_DIR/owned-shader.ll"
python3 tools/air_cache_tests/cache_ab.py --bitcode "$CACHE_AB_DIR/owned-shader.ll.bc" --output "$CACHE_AB_DIR/comparison"
```

The focused A/B is complete. The induced-fault benefit must not be generalized
to everyday desktop performance; that needs representative actual cache/compiler
behavior and, for candidate integration, separately authorized live validation.

### Installed-driver Mesa pipeline reuse comparison

Continued safe development rather than stopping at the AIR milestone. New
`tools/air_cache_tests/mesa_pipeline_probe.swift` creates eight owned compute
kernels and independently checks all four outputs after bounded GPU completion.
`mesa_pipeline_ab.py` runs three processes per arm: normal Mesa policy, empty
owned cache, then fresh-process reuse of that owned cache. Inherited Mesa/XDG
cache overrides are removed only in children; the owned arm supplies its own
`MESA_SHADER_CACHE_DIR`. Release initialization preserves this variable. No
installed graphics component, system configuration or display is changed.

72/72 dispatches produced correct results. Each owned cold run created 35 files,
2,112,820 bytes; reuse retained that count/size. Across 24 pipeline creations per
arm, p50/p95 were: default 0.358/16.718 ms; owned cold 1.182/18.575 ms; owned reuse
0.348/17.526 ms. Aggregate pipeline time was 65.43/81.13/61.82 ms respectively.
These percentiles combine eight distinct kernels, not 24 identical samples.
Front-end/AIR caches were retained, so this is not globally cold compilation.
First baseline library creation took 97.88 ms; subsequent samples were roughly
0.8–1.2 ms. It would be misleading to attribute that first-library warmup to
Mesa pipeline persistence. Evidence: `docs/evidence/ga102-mesa-pipeline-ab.json`.

**PASS: correct compute and owned cache persistence. NOT VERIFIED: explicit
Mesa hit counts or a default-policy performance improvement.** The earlier
permission-denied warning was not reproduced in these controlled processes.
Owned reuse is faster than intentionally empty owned cache, but matches the
current default median. This rules out claiming that merely supplying a cache
path improves this current baseline. It does not establish WindowServer cache
health or the cause of desktop sluggishness. No further cache-path timing repeats
are justified by these results.

Next justified source objective: reduce repeated AIR text disk reads in
`NVMTLLibraryLoad.m::nvmtl_air_to_text`. Existing code hashes the immutable AIR
and reads the same persisted IR on every call. The prior healthy-cache A/B
measured about 20 microseconds per hit. A bounded process-local text cache can
avoid those reads without touching GPU ordering, pipeline lifetimes or shader
translation. Validate exact IR equality, key separation, bounded retention and
thread safety before claiming any measured benefit.

### User-space improvement: bounded AIR text reuse and initialization race fix

Implemented a process-local AIR text cache in `plugin/nvmtl_air_text_cache.h`,
used by `NVMTLLibraryLoad.m::nvmtl_air_to_text`. It keys immutable text by the
existing SHA256/option/directory path, preserving disk filenames, shader text
and unroll-policy separation. A synchronized dictionary copies keys/values,
retains at most 128 entries and 16 MiB of counted UTF-16 key/text payload,
clearing its entries when either limit would be exceeded. Foundation object
and allocator overhead is additional. Oversized entries are not retained.
Disk lookup, decoding and persistence remain the miss path. Concurrent misses
may duplicate decoding; no GPU lock, fence, wait, resource lifetime or command
submission changes were made. Memory hits contribute to the existing hit count;
`gAirMemoryHit` separately counts them for the focused comparison.

Also corrected `nvmtl_air_unroll_wanted`'s unsynchronized static `off` read/write
initialization using `dispatch_once`. The source-extracted original function
produced one ThreadSanitizer data-race warning and aborted (exit -6) with the
policy enabled. The candidate passed enabled/disabled and empty-input checks,
16 concurrent workers × 100 assertions. This is a confirmed correctness defect;
its impact on real desktop performance is not established. Reproducer:
`tools/air_cache_tests/unroll_thread_test.py --output <new-owned-directory>
--baseline`. Raw sanitizer logs are private. Sanitized numeric evidence:
`docs/evidence/ga102-air-unroll-concurrency.json`.

`memory_cache_test.m` passed AddressSanitizer/UndefinedBehaviorSanitizer and
ThreadSanitizer: immutable snapshots after caller mutation, separate option
keys, count/payload eviction, oversized rejection and concurrent values.
`cache_ab.py --memory-cache` compares production code from `005d714` against the
candidate with the same corrected directory selector and original owned AIR.
Three fresh processes per condition/variant, 21 calls each, plus one process
reusing persisted disk entries. All IR SHA256 values agree. Each candidate has
20 memory hits, one miss and one disk store; each baseline has 20 disk hits,
one miss and one store. Reuse processes have 21 total hits and zero misses,
with 20 served from candidate memory after the initial disk hit.

| Corrected directory condition | Baseline repeated lookup p50 / p95 | Candidate p50 / p95 |
|---|---|---|
| Valid global cache | 20.67 / 24.66 microseconds | 10.17 / 13.02 microseconds |
| Fallback from file to valid user cache | 20.64 / 24.85 microseconds | 10.21 / 13.00 microseconds |

**PASS: measured repeated AIR lookup improvement, approximately 2× in this
comparison.** Earlier implementation comparisons showed about 1.6–2×; magnitude
varies with scheduling. The savings are roughly 7–10 microseconds per repeated
lookup, not milliseconds of frame time. Evidence:
`docs/evidence/ga102-air-memory-ab.json`. One final baseline first call took
1,514 ms (others roughly 39–64 ms); no cold-start improvement or cause is claimed.
A separate hexadecimal formatting variant showed no clear incremental benefit
and was reverted, keeping the patch focused.

The complete isolated x86_64/O1/NVMTL_RELEASE=1 user-space plugin linked with
Apple clang 17, SDK 15.5, pinned Vulkan-Headers. Binary SHA256:
`ad776d88a83afa0fe97f90837289608c7d7cf58f002eab4d81248e73990b2ba1`.
Only the expected system Foundation/Metal/IOSurface/CoreFoundation/Objective-C/
libSystem dependencies were present. It was not installed or loaded.

**Everyday desktop benefit and candidate integration remain NOT VERIFIED.**
Memory retention and batch eviction can affect workloads with many shaders;
reverting this source change restores disk-first behavior without changing
cache formats. No live rollback is necessary because installed files remain
unchanged. The next justified performance question is repeated creation of the
same Metal pipeline: current measurements combine different kernels and include
roughly 17–19 ms first-pipeline initialization. Those samples do not justify a
Vulkan pipeline cache or pipeline-object sharing patch. A bounded same-function
comparison is required before selecting such a change. No further kernel build
reconstruction, capture experiments or live-driver deployment is authorized.

### Follow-on pipeline comparison BLOCKED: current NVIDIA stack unavailable

Added optional `--same-function` to the existing bounded pipeline probe: retain
one Metal function and recreate eight pipeline states, still checking every GPU
output. The Swift executable compiles. Runtime validation is **BLOCKED**, not a
passing measurement. Two launches failed before obtaining a GA102 device/queue,
including a launch under the source's explicitly accepted `nvmtltest` name.
No driver allow-list was edited. No pipeline timing or GPU completion result was
obtained. The attempt to distinguish process-name admission from device absence
ended with independent read-only confirmation that Metal enumerates zero devices.

Current observed state after the source milestone:

- macOS 15.8.1, build 24H32.
- `kmutil showloaded` via `kextstat -l`: no NVRM/NVAccel/NullMoth matches.
- `debug.nvaccelfb`: unknown sysctl OID.
- `MTLCopyAllDevices()`: empty.
- System Profiler: NVIDIA PCI ID 0x2208, PCIe x16, generic 22 MB VRAM,
  "No Kext Loaded", display resolution still 3440×1440.
- SIP enabled; authenticated-root enabled. This differs from the previously
  recorded recovered SSD session's custom SIP mask/authenticated-root disabled.
- Installed NVRMFB still matches original baseline SHA256
  `a2a3cf961df1aae872d500142b8c146ecd660a369f364d843f42c3fb4bd21e71`.
- Installed auxiliary collection SHA256 now
  `68033b5f1c897245f1889c5381a365f4ad0626919dd46e19047aa5e7a5477071`,
  differing from the recorded original restored collection
  `362eb218919f7783440035cf19f02fb05b73a749836fa942e8a9b90f1d973526`.

**Confirmed: the current observed desktop does not expose the previously working
accelerated stack.** The earlier 72-dispatch installed-driver cache comparison
completed successfully; these later checks must not be merged into that earlier
state or presented as a result of the source-only cache patch. Cause and timing
of the state change are **NOT VERIFIED**. An alternate boot configuration is a
hypothesis consistent with the prior USB recovery observation, not established
by these checks. No EFI inspection/change, security change, install, kernel
collection replacement, reboot or service restart was performed in this cycle.

GPU experiments are stopped rather than repeatedly retrying. CPU/source work
has delivered the validated cache performance improvement and concurrency fix
in `2707eeb`. Resolving this new installed-stack/boot-state blocker requires user
clarification and separately authorized system recovery if needed. Do not
blindly disable SIP or install the candidate. The compiled same-function probe
is ready for the original working driver once that stack is available; it is
not justification for a pipeline-sharing performance patch.


## Post-reinstall autonomous development — 12 October 2026

The new user authorization permits builds, ordinary GPU workloads and isolated
user-space candidates. It supersedes earlier source-only experiment restrictions,
while retaining no reboot/logout, WindowServer restart, display-mode change,
EFI/security change or active kernel/collection replacement. The failed
framebuffer candidate remains retired.

**Recovered state preserved:** branch `dev/ga102-3080ti-diagnostics` at `44ed7c7`,
exactly the two reported Swift files modified, `core.fileMode=false`. Existing
local patch exists; an additional exact patch and source hashes were retained
in a new durable private artifact directory. Those edits are not included in
these commits. Restored vendor, Vulkan headers, CPU fixtures, built plugins and
failed-boot evidence are available. CLT clang 17, SDK 15.5 and Python 3.9.6 work.
Rust/Meson/Ninja and GitHub CLI are absent. HTTPS push lacks local credentials;
the authenticated GitHub connector is available as a publication route.

**Installed runtime restored, independently observed:** all four NullMoth
extensions loaded; NVRMFB UUID is the original
`CC151F75-1305-3928-AA0F-B8BC96EF30A3`. On-disk Metal plugin and framebuffer
hashes match the original working baseline. RTX 3080 Ti, 12 GB, PCI `10de:2208`,
3440×1440 at 60 Hz are reported. Effective SIP remains custom and
authenticated-root disabled; neither was changed. Named flip counters exist
and advance, with zero observed error/drop counters. These are system counts.
Python screen-capture preflight is permitted after reinstall.

**Fresh installed-driver correctness PASS:** existing suite verifies compute,
offscreen pixels, all four layered composite cases, 16 shared-event iterations,
and eight bidirectional cross-process IOSurface roundtrips. This is one run per
check, not repeated qualification or proof of desktop fluidity. A separate
three-run presentation baseline is in progress.

### Explicit process-local candidate binding

`tools/ga102_isolated_plugin_probe.m` opens exactly the requested driver image,
without calling Metal device enumeration. It binds `NVMTLDevice` to the existing
NVAccel IOKit service using its expected accelerator service right. Before
work, class ownership and key method implementation images must match the
requested binary; another Metal driver image is rejected. It creates only
owned offscreen resources and keeps the image resident until exit. The plugin's
constructor and forwarding changes affect only this child process. Installed
files, WindowServer and active kernel components are untouched. The original
CPU translator/runtime and NVK backend remain dependencies.

**Initial isolated candidate runtime PASS:** original and current release plugin
were loaded in separate processes, each with eight correct bounded GPU dispatches.
The rebuilt binary is byte-identical to the prior source-only `2707eeb` artifact,
SHA256 `ad776d88a83afa0fe97f90837289608c7d7cf58f002eab4d81248e73990b2ba1`.
This closes the previously missing process-local binding route; it does not
qualify WindowServer integration or install the AIR/cache changes.

First same-function compute pipeline creation was 19.388 ms original / 19.822 ms
candidate; subsequent creations were 0.037–0.084 / 0.045–0.076 ms. This small
initial screening gives no justification for pipeline-object sharing. Library
times of 96.17 / 1.02 ms are confounded by first-process compiler warmup and
**must not be called a candidate speedup**. Repeat comparisons must alternate
order and separate initialization from warm repeated creation.

The runner now offers `--plugin /path/to/NVMTLDriver` for offscreen correctness,
memory and benchmark probes only. It compiles a private source snapshot that
shadows enumeration with the explicitly bound device, preserving original probe
files. Binding checks run at process exit, and absence of the provenance marker
or a changed binary hash fails acceptance. Reports retain source/binary hashes,
not private paths. Windowed/capture use is refused because AppKit could load
another plugin implicitly. Five focused regression cases verify ownership-gate
reporting, changed-binary rejection, offscreen restrictions and snapshot behavior;
eleven relevant Python tests pass including existing runner/core checks.
Full candidate suite execution is next, and is not claimed by the initial probe.

Evidence: [`evidence/ga102-post-reinstall-binding.json`](evidence/ga102-post-reinstall-binding.json).
Private compiler logs and artifacts remain in durable local storage.

### Queue initialization correction and candidate isolation boundary

**Confirmed source concurrency defect:** `nvmtl_device_queue` initialized a
shared texture-transfer queue using an unsynchronized `made` flag. Concurrent
first callers can each clear/write the same queue and overwrite its command-pool
handle. The production helper extracted from `44ed7c7` produced three
ThreadSanitizer race warnings in each first-use/retry fixture process. An initial
asserting fixture aborted on partially initialized queue reads before sanitizer
reporting; it is retained privately. The final fixture records those reads so
the sanitizer can report the underlying races.

The correction initializes a temporary queue under a mutex and publishes it
with release/acquire atomic ordering only after success. The established fast
path takes one acquire load; failed construction remains retryable. No command
submission, GPU wait, resource-retirement or memory-placement policy changes.
Candidate passes 16 workers × 100 reads in both modes, with zero sanitizer
warnings, exactly one successful creation and two failed creations retried in
the fault case. The fixture executes the production initializer with a CPU-only
delayed backend stub; it does not stress native concurrent Vulkan allocation.

**Build and scoped isolated runtime PASS:** release plugin SHA256
`d58620670530065c5716e06f6c2865dd06cacc5369f6568f84f4ba6b9e660d24`
compiles/links. Explicitly bound candidate passed three compute smoke processes,
three offscreen render processes and three shared-event processes, the latter
checking all 48 iterations including 24 consumer-first submissions. Binary and
class provenance gates passed. This exercises real candidate code with the
installed kernel/NVK/translator. It remains undeployed, with no measured desktop
benefit or claimed wake fix.

**Isolation FAIL, correctly rejected:** the full candidate suite stopped at its
first IOSurface compositing process. Although all sampled pixels were correct,
IOSurface initialization implicitly loaded the installed Metal bundle beside
the candidate, producing duplicate Objective-C classes. The exit gate failed;
these pixels/timings do not qualify the candidate. No further mixed-plugin
workload was launched. The runner now refuses IOSurface/composite/cross-process/
benchmark and all windowed candidate routes before launch. Candidate-suite jobs
requiring those paths are BLOCKED while independent supported checks continue.
The supported set is compute, ordinary offscreen render, events and memory.
The helper refactor's first compile also exposed an integer return in its new
object-returning binding function; it was corrected before Swift candidate
execution. The successful standalone binding result remains valid.

67 Python regression tests PASS, including changed-binary/missing-provenance
rejection and new prelaunch IOSurface restrictions. User-recovered Swift file
hashes still match their exact pre-work values. Evidence:
[`evidence/ga102-queue-initialization.json`](evidence/ga102-queue-initialization.json).

### Fresh installed desktop baseline

Three held-reference Metal processes each validated all twelve GPU/captured
patterns, and three ordinary Core Animation processes each validated twelve
captured references. The existing continuous CA stream remains NOT VERIFIED for
full frame coverage. The continuous Metal/SCK run reproduced sustained 33.37 ms
median / 34.33 ms p95 reported intervals, 109 steady intervals above 25 ms; the
runner retained FAIL and stopped further repeats of that condition. This is
capture-associated backpressure, not evidence that normal desktop delivery is
limited to 30 Hz.

Capture-independent timing: three timer runs each PASS, p95
17.614/17.588/17.487 ms; three display-linked runs each PASS, p95
17.602/17.501/17.553 ms. All are at the retained 3440×1440/60 Hz mode, with
clean display error/drop deltas. These simple workload results resemble prior
ready-session evidence and establish no post-reinstall speedup or full desktop
responsiveness acceptance. Evidence:
[`evidence/ga102-post-reinstall-presentation.json`](evidence/ga102-post-reinstall-presentation.json).

### New user-observed sleep/wake failure

The user reports system sleep followed by a black display on wake and has
disabled automatic sleep. **USER-OBSERVED FAIL: display restoration.** No agent
sleep/wake test, power-setting write, reboot or service restart occurred. A
bounded read-only pmset history retains one sleep and one wake; raw metadata
stays private. After the update, all four original NullMoth kexts are loaded,
`debug.nvaccelfb=1`, with zero observed failure/drop counters. An original-plugin
explicit smoke process checked eight correct GPU dispatches. Thus the current
execution path works; this does not explain or disprove the reported wake fault.

**Source gap:** NVRMFB's `setPowerState` emits WillPowerOff/DidPowerOn and always
returns implied acknowledgement. It bypasses the superclass power worker.
Connection-power requests return success without hardware work. NVRM and the
NVAccel port contain no coordinated RM/NVKMS system suspend/resume callbacks.
Pinned NVIDIA 610.57.04 explicitly coordinates KAPI notifications, PM locking
and `nvKmsSuspend`/`nvKmsResume`; these are not replaced by a framebuffer client
notification. [Pinned NVIDIA suspend/resume implementation](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/e4a5faa2567f28c8eabe0ebb6422b6d0abcf37eb/kernel-open/nvidia-modeset/nvidia-modeset-linux.c).

Apple's public framebuffer implementation queues `pendingPowerChange`, starts
controller work and returns an asynchronous acknowledgement interval from
`setPowerState`. Completion notifications occur later through controller work.
[Apple IOFramebuffer source](https://github.com/apple-oss-distributions/IOGraphics/blob/main/IOGraphicsFamily/IOFramebuffer.cpp).
This supports a protocol-delegation investigation, not an assertion that simply
calling the superclass fixes GPU resume. The public source is a reference, not
proof of Sequoia's exact resident implementation.

A single bounded retained driver-log query completed: ten setPowerState entries
(two off/eight on), no matching completion-unavailable or explicit NVIDIA
suspend/resume messages. Boot/wake coverage and suppressed-message behavior
prevent assigning cause from absence. Existing completion fault latches and mode/
vblank state are not reset on wake; clearing them without restoring GPU state
and verifying pending surface ownership would violate safety requirements.
Next: stage and offline-test the narrow superclass protocol correction separately
from a complete RM/NVKMS power lifecycle. Any kernel candidate remains AWAITING
SUPERVISED DEPLOYMENT and blocked on known unchanged-build boot compatibility
and verified recovery. No black-screen repair is claimed.

### Offline framebuffer power-protocol candidate

Prepared `build/experimental/ga102-framebuffer-pm.patch`; the production
framebuffer file is unchanged. The experiment replaces its unconditional
notification/implied-ack stub with `super::setPowerState(ordinal, device)`,
letting IOFramebuffer own pending controller work and acknowledgement. It
does not implement RM power transitions, change flip waits or clear surface
fault/lifetime state. Expected benefit is restoring framework power-protocol
participation, not a demonstrated display-wake repair.

`tools/ga102_pm_protocol_test.py` applies the actual patch to an owned copy and
compiles the extracted callback with a CPU-only superclass stub under ASan/UBSan.
Original callback fails the forwarding control; candidate passes nine exact
ordinal/device/return-value cases, including asynchronous acknowledgement and
error values, without issuing premature completion notifications. This tests
forwarding only; real IOGraphics execution and GPU restoration are untested.

Built the full experimental framebuffer from the authentic `e404ab30` source
using the preserved pinned vendor/compile/link recipe. Only the PM callback
source differs; the retired completion instrumentation is excluded. Candidate
SHA256 `c16184bb0e77f4cdfe419d9b790c84388e100eed3f50051860e3279e356916d1`.
The undefined-import set matches the original. Candidate and byte-verified
original rollback bundles are staged in durable local artifacts.
**AWAITING SUPERVISED DEPLOYMENT**, with unchanged-source boot compatibility and
Recovery qualification still missing. No kernel or auxiliary collection was
loaded/replaced/built for deployment. No candidate wake cycle was executed.

Rollback must use the current original bundle and the current pre-deployment
auxiliary collection with verified hashes, required ownership/modes and tested
Recovery access. Prior pre-reinstall collection backups are not assumed current.
A separate approved maintenance window must first qualify unchanged-build boot
compatibility and recovery. If a future experiment fails, restore those exact
originals from the tested recovery route. No deployment command is enabled here.
Evidence: [`evidence/ga102-wake-protocol-candidate.json`](evidence/ga102-wake-protocol-candidate.json).

### Memory correctness and ordinary compositor cost

Three installed and three explicitly bound candidate memory processes each
checked shared/managed/private modes, all 1,048,576 elements per mode. All
eighteen mode executions PASS. GPU median per pass (installed / candidate):
shared 0.2294 / 0.2289 ms; managed and private 0.0123 / 0.0123 ms. This preserves
the earlier shared-memory cost finding and establishes no performance benefit
from the queue initializer correction. Source/candidate execution is separated
from the installed stack. Evidence:
[`evidence/ga102-memory-post-reinstall.json`](evidence/ga102-memory-post-reinstall.json).

Three ordinary Core Animation runs with 32 translucent rounded/shadowed layers
measured WindowServer at 43.3/42.8/42.7% of one core during animation, versus
about 16–20% in their idle phases. These process-wide correlations resemble the
previous 44–45% observation. Client timers/presentation-tree motion do not
qualify composited frame timing, physical scanout or complete desktop fluidity.
Evidence: [`evidence/ga102-ca-cpu-post-reinstall.json`](evidence/ga102-ca-cpu-post-reinstall.json).

### IOSurface candidate isolation established with private classes

The prior single-image rejection remains valid. Rather than accept duplicate
classes, `build/build_isolated_plugin.py` creates an owned source snapshot with
all 62 Objective-C classes and one private protocol in an `NVMTLGA102_` namespace.
Literal class lookup strings are rewritten consistently; C definitions are
hidden and the resource-device global is explicitly renamed. Original sources
are untouched. The transformation is reversible byte-for-byte in the regression
test and changes no GPU algorithm or lifetime/synchronization operation.

The optional runner/suite `--namespaced-plugin --plugin <binary>` requires a
matching namespace build proof. This mode permits the known installed bundle
to autoload under its separate original classes, while checking every candidate
class image, the selected device method images, and a candidate buffer's exact
device identity at exit. Unknown driver images, changed candidate bytes, wrong
class ownership or absent independent namespace proof markers fail acceptance.
The ordinary unnamespaced route retains its single-image gate and IOSurface
refusal. All windowed/capture candidate routes remain prohibited in the harness.

**PASS, namespaced candidate offscreen runtime:** candidate SHA256
`167d176d8b70507a9dce7926373dc67436d5cddcb41731749928c1c5cfbfedf5`
passed all four full-size private/IOSurface compositing cases, including 32
sampled blended layers. Three independent cross-process tests passed 24
bidirectional surface roundtrips and 786432 checked bytes. Both participants
use the explicit namespace; child failures/provenance failures propagate to the
parent verdict. No duplicate-class warnings occur in the successful path.
These are real rebuilt user-space candidate executions with retained installed
RM/NVK/translator, not an installed-driver or desktop-speed qualification.

Seven focused isolation tests pass, including whole-source reversible namespace
conversion, literal forwarding lookup conversion, and rejection when the
namespace marker is missing even with correct GPU records. Evidence:
[`evidence/ga102-namespaced-isolation.json`](evidence/ga102-namespaced-isolation.json).

### Bounded shader-transform memo retention

`nvmtl_address_shader_g` memoized up to 4096 complete input-byte keys, lowered
modules and alignment metadata, with no byte cap. CPU fixtures executing the
production memo helper retained 72 MiB of output across only six entries, and
a single 65 MiB result stayed cached. These are constructed retention controls,
not evidence of that memory consumption in WindowServer or real shader mixes.

The source now retains at most 64 MiB of counted key/module/metadata payload
and 4096 entries. Oversized entries return the actual lowering result without
retaining it. Batch eviction preserves the prior clear-on-cap strategy. A
concurrent replacement subtracts the previous entry before charging the new
one, with all dictionary/accounting updates under the existing mutex. Input
keys, lowering flags, returned bytes, alignment metadata and negative-result
cache behavior are unchanged. Foundation/allocator overhead, transient decoded
values and results retained by callers are additional to this cache budget.

**CPU retention/ownership PASS:** candidate maximum tracked cached output in the
six-entry fixture is 60 MiB, versus 72 MiB originally; a 65 MiB oversized result
leaves zero cached output versus 65 MiB originally, and is recomputed on reuse.
ASan/UBSan validates flag/input separation, negative caching and 4096-entry
eviction. TSan validates 16 workers × 100 memo calls with correct result bytes
and metadata and no race warning. Lowering is a deterministic CPU stub here,
so shader semantics are not established by those fixture assertions.

**Actual rebuilt candidate GPU correctness PASS:** namespaced release plugin
SHA256 `4e2ee35c636b6edf36a294682458b5e1a7e06cbadb9453a9a39b09104a3f00e9`
passed the complete five-probe correctness suite, three independent repetitions
each: compute, offscreen pixels, layered private/IOSurface compositing, shared
events and bidirectional cross-process surfaces. Class/method/device provenance
checks passed in every process. No installed graphics component was changed.

The correction bounds process-local driver memory retention; it is not a
measured desktop-speed improvement. A working set above the cap can incur
additional CPU lowering after eviction; no cache-size tuning claim is made.
Source rollback restores the former count-only memo policy. Evidence:
[`evidence/ga102-shader-transform-retention.json`](evidence/ga102-shader-transform-retention.json).

### Build readiness continuation

The recovered tools lacked Rust and Mesa dependencies. Installed the official
checksum-verified rustup bootstrap into task-owned CARGO/RUSTUP homes using
`--no-modify-path` and a minimal profile. Rust 1.99.0 is available without shell
profile or system/security changes. Task-owned Python 3.12 tooling supplies
Meson/Ninja/Mako/PyYAML/packaging. A copied, lockfile-pinned translator source
release build is running with two compiler jobs and private logs. No rebuilt
translator has been executed or installed yet.

Resolved the short Mesa base to official commit
`17ca6174dcc6cb22059ac343bc29f8af7800f42e` and downloaded its source archive
from Mesa's GitLab. The complete NVK patch applies to the extracted official source, with real
pinned vendor headers linked. Isolated Meson setup and bindgen bootstrap are
in progress. This pursues NVK source-build readiness independently of the
still-missing Darwin NVRM archive recipe; a successful NVK build is not yet claimed.

### Translator ordering guard and real candidate compiler execution

The restored source translator now builds with a lockfile-pinned Rust toolchain.
The first wrapper run found five false test failures: scalar-load census counted
only four-byte alignment, ignoring unmerged 32-bit loads retaining valid eight-
byte alignment. Census now checks scalar result type; expected load counts and
positive/negative merge expectations are unchanged. These five results were a
test-accounting defect, not five demonstrated shader defects.

New valid SPIR-V controls show the optimizer merging ordinary adjacent word
loads across an intervening volatile or Vulkan visibility-bearing load (eleven
prior controls pass, both new no-crossing controls fail before correction).
The fusion scan now classifies the complete instruction and stops at loads with
semantics beyond ordinary/Aligned access. This conservative guard preserves
flagged-operation ordering; it does not remove synchronization or alter ordinary
wide-load fusion. Input/output modules validate against Vulkan 1.2, and all
thirty available self-contained wrapper tests now pass. Two ignored corpus
tests and two unavailable private-fixture tests are not counted as validated.
The [Khronos memory-operand specification](https://registry.khronos.org/SPIR-V/specs/unified1/SPIRV.html)
distinguishes visibility/inter-thread and volatile semantics from alignment.
This is a compiler ordering safeguard, not proof of the reported wake cause or
an observed ordinary desktop pixel failure.

**Release build and isolated GPU integration PASS:** rebuilt CPU translator
SHA256 `0fe056bed48259a6ad9901e3b5e33906caac6a92aa5651a0bd4604eb2a6558d0`,
with the same exported `nvmtl_*` ABI set as the installed release. Its private
namespace plugin SHA256
`839d6d34abd412546f83b1e66603e2a6689024d78cb788c43f4767e468ba3601`
passed all five GPU correctness probes in three processes each. Installed
RM/NVK/kernel/WindowServer components remain unchanged.

The private builder accepts `--translator`, hashes that explicit CPU dependency,
exports a selected-function image probe and wraps the primary translation call
with a relaxed atomic counter in the copied source only. The harness checks
actual function image and unchanged file hash. An initial smoke process executed
one real call in the rebuilt translator. Subsequent first render/composite
processes executed two calls each; repeated processes can hit persisted SPIR-V
and report zero calls. Event/copy-only probes did not load the translator.
Thus library loading, primary compiler execution and correct GPU results remain
separate evidence. A broader source-library integration PASS does not mean
every probe exercised the new flagged-load control. Eight focused isolation
tests and seventy total GA102 Python tests pass. Evidence:
[`evidence/ga102-wide-load-ordering.json`](evidence/ga102-wide-load-ordering.json).

### Native test/build infrastructure limits

Three native unit tests referenced unshipped external fixtures via unconditional
`include_str!`, blocking every native test from compiling. They now require the
explicit `external-validation-fixtures` feature; README states exact required
files and the coverage exclusion. No substitute fixtures are fabricated. The
native Cargo.lock was stale for its current manifest; synchronized it by removing
149 unused packages, with no changed version/checksum among the sixteen retained
packages and no additions. This is test/build readiness, not production shader
behavior. The source translator release wrapper's separate lock remained pinned.

The newly compiling default native suite recorded 1659 PASS / 496 FAIL / one
ignored. Sampled failures require an absent `spirv-val` executable; these are
retained as failures, not reclassified en masse without rerunning. The official
SPIRV-Tools source and pinned required headers are being built into private CLI
tools. The first attempted reuse of Cargo's vendored subset failed because it
lacks upstream CMake metadata; no stub validator was introduced. Native tests
will be rerun only after real validator/assembler tools are available.

Pinned Mesa setup now recognizes Rust, bindgen, cbindgen and a source-built
Khronos glslang 16.6.0; it stops at missing **mesa_clc**. NVK source build is
BLOCKED on the real OpenCL-to-SPIR-V compiler and its LLVM/Clang/SPIR-V dependencies,
not the previously missing basic tools. No fake compiler, skipped kernel
generation or deployable NVK binary is claimed.

### NEXT-STEPS

1. Finish the active official SPIRV-Tools CLI build, then rerun native translator
   tests with `--locked --lib -- --test-threads=2` and the private CLI directory
   on PATH. Retain failures and investigate actual semantic defects if any.
2. Extend isolated execution counters to the source address-lowering entry points
   when distinguishing frontend cache hits from the specific fusion guard path.
3. Evaluate a real isolated mesa_clc dependency build; otherwise pursue validated
   translator/plugin defects independently of the blocked full NVK build.
4. Preserve the staged PM protocol candidate for supervised boot/wake work only.

## Address-lowering execution and native parser follow-up

The private plugin now wraps both address-lowering entry points with relaxed
atomic call counters and reports the actual implementation image. A correct GPU
record without the required lowering marker fails validation. Seventy-one GA102
Python tests pass, including a negative missing-marker control. The isolated
composite candidate passed, with zero primary translation calls and **two real
address-lowering calls** in the rebuilt CPU library. Shared, managed and private
buffer checks also passed. This distinguishes frontend cache reuse from lowering
execution; it does not establish execution of the flagged-load branch. Evidence:
[`evidence/ga102-lowering-execution.json`](evidence/ga102-lowering-execution.json).

With real official SPIRV-Tools validator and assembler on PATH, the native suite
recorded **2137 PASS / 18 FAIL / one ignored**. This replaces the earlier
missing-validator result. Three failures additionally need the real disassembler;
that target is being built. Two suspect discarded-store failures actually retain
the stores through guarded-load helpers; their direct-ID assertions do not follow
helper return values. No emitter behavior was changed on that evidence.

A real parser defect accepted `i32 addrspace(x)*` as address space zero. Explicit
malformed trailing address-space annotations now return an error instead of
falling through the function-pointer allowance. Tests include empty, negative,
signed, mixed and overflowing annotations; all fifteen parser tests pass. Valid
typed pointers and function-pointer spellings remain covered. This is input
validation correctness, with no measured desktop performance claim.

### NEXT-STEPS

1. Finish `cmake --build <private SPIRV-Tools build> --target spirv-dis -j 2`;
   rerun the three native reloop tests with the real CLI directory on PATH.
2. Inspect emitted SPIR-V for `native_helper_alloca_keeps_parameter_pointer_chain_real`;
   distinguish shared guarded-load helper bodies from lost buffer reads, then
   repair regression assertions only when they preserve semantic coverage.
3. Rerun the native suite after validated fixes; keep remaining failures visible.
4. Continue independent source improvements while mesa_clc/full NVRM builds remain
   blocked. Keep the staged PM candidate for supervised boot/wake validation.

## Confirmed volatile memory translation defect and isolated candidate fix

A fresh bounded four-float Metal kernel compiled with the byte-identical installed
CPU translator contains one volatile LLVM load and store, but its cached SPIR-V
contains **zero volatile loads and zero volatile stores**. Its numeric GPU output
still passes, so a plain arithmetic correctness test would miss this defect.
No sleep/wake or desktop symptom is attributed to it without further evidence.

The native typed carrier now preserves the LLVM volatile qualifier on loads and
stores. Emission adds the SPIR-V volatile mask to the memory operations produced
for that access while preserving existing alignment operands. Guarded physical
address load helpers include volatility in their cache key and emitted load mask;
ordinary and volatile accesses cannot share an incorrectly qualified helper.
This retains access semantics; it does not add atomicity or synchronization fences.

CPU controls cover ordinary/volatile buffers and mixed physical-address loads in
both helper creation orders, with real SPIR-V validation. The old missing-mask
control fails. A separate fault control removing volatility from the helper key
also fails. The improved existing buffer regression verifies two helper calls at
distinct addresses, subtraction of both values and the output store, rather than
counting two identical helper bodies. Seventy-two GA102 Python tests pass. The
full native suite records **2142 PASS / 14 FAIL / one ignored**. Remaining failures
are retained; an arbitrary-hash-map-phi selection makes one test unstable. All
three reloop cases pass with the official disassembler available.

The rebuilt CPU dylib SHA256 is
`6b8d9fe0b5c0928844af6ed728e20d890d0182fb5fff600ad88bfb851ad19233`,
with the same exported translator ABI as the installed release. It is copied
into an immutable-by-workflow owned artifact before candidate linking, so later
source builds cannot silently change this candidate dependency. The fresh
`--volatile-smoke` route changes only a copied shader's qualifier and unique
entry-point name. Its isolated GPU run passes `[2,4,6,8]`, executes one primary
translation and one address-lowering call, and retains **one volatile load and
one volatile store in cached SPIR-V**. Offscreen render and all four private/
IOSurface composite cases pass with the same CPU candidate. The loaded driver
and original recovered Swift edits remain unchanged. Evidence:
[`evidence/ga102-volatile-memory.json`](evidence/ga102-volatile-memory.json).

### NEXT-STEPS

1. Extend volatile controls to constant-space and vector/pointer payload paths;
   preserve the current isolated CPU binary while making further source changes.
2. Replace arbitrary phi selection in the loop-carried-address regression with
   loop-header identification and guarded-helper return provenance.
3. Diagnose the remaining native failures individually: diagnostic-text changes,
   guarded-helper provenance, opt-in trig behavior and bindless descriptor bands.
4. Continue source-level PM/NVK work independently of missing mesa_clc/full Darwin
   archive producers; keep kernel PM deployment and wake validation supervised.

### Volatile pointer/vector coverage and copy rejection follow-up

Constant-space scalar, vector and pointer-payload volatile access controls pass
translation and real SPIR-V validation. A separate volatile `llvm.memcpy` control
proved that an unmodeled destination lets the unsupported copy disappear without
an error. The emitter now explicitly rejects volatile memcpy before ordinary
copy paths and unmodeled-pointer fallback. All thirty-three memcpy-group tests
pass, including that new regression. This source-only boundary fix makes affected
inputs fail translation rather than falsely reporting successful no-op copying;
it does not implement volatile memcpy or change the already-preserved GPU-tested
CPU artifact. Ordinary memcpy behavior remains covered by the group tests.

### NEXT-STEPS

1. Configure the pinned LLVM/Clang source build into private artifacts as the
   first real mesa_clc dependency; retain compiler/link failures if encountered.
2. Repair loop-header/guarded-return provenance in the unstable pointer regression.
3. Continue individual native-failure triage and source PM diagnostics. The
   supervised-only kernel/wake boundaries remain in force.

### Stable native provenance regressions and real compiler dependencies

The pointer regression now selects the 64-bit phi in an actual loop header, then
follows guarded helper returns to the child-address load. It passes in twenty
fresh processes with independent hash-map seeds. A valid SPIR-V negative control
replacing child loads with zero fails the provenance check as intended. Owned
texel tests retain invalid/error-classification and exact diagnostic-summary
checks while permitting appended diagnostic details. The native suite recorded
2146 PASS / 11 FAIL / one ignored before the next buffer-array repairs.

Two buffer-array regressions now follow direct loads, copy/guard phis and helper
returns rather than requiring all loads to be inline. Both previously failed
stored-value/two-hop checks pass; four buffer-array tests pass as a group. No
emitter behavior was changed for those test repairs. Remaining failures will be
retained and assessed individually.

Pinned LLVM/Clang 19.1.7 built with two jobs; selected libraries, headers and tools
are installed into the private artifact prefix. The actual Clang compiles a
bounded OpenCL kernel to LLVM bitcode. The required SPIR-V optimizer/link libraries
also built; packaging the complete real toolchain is underway. Matching
SPIRV-LLVM-Translator source commit `2f18fc9e7f3a6e1776c9dd232d2292d83ef0e9a6`
and its pinned headers `575b6512579ebde466ed3dfc04e413439d14d95d` are prepared.
No mesa_clc/NVK build success is claimed yet; no system toolchain or active driver
was changed.

### NEXT-STEPS

1. Finish private SPIRV-Tools packaging and pkgconf build/test/install. Configure
   the matching SPIRV-LLVM translator against the real LLVM build-tree package.
2. Build libclc SPIR-V builtins and real mesa_clc, then resume the pinned NVK build.
3. Validate the buffer-provenance inspector with a lost-load negative control and
   rerun the native buffer group; triage remaining failures without blanket skips.
4. Preserve the loaded driver and the supervised-only kernel/wake boundaries.

### Native groups and compiler bootstrap checkpoint

The buffer-provenance inspector passes a valid lost-read negative control; the
buffer group records 284 PASS / two FAIL / one ignored. The remaining failures
expect an old typed-zero placeholder path and forbid guarded helper calls. They
are not reclassified without semantic checks. All sixty-eight intrinsic tests
pass after checking NaN-to-zero conversion dataflow and testing the opt-in trig
flush in a child process with explicit environment, avoiding global environment
mutation. Finite packing checks and normal production math remain unchanged.

Private pkgconf 3.0.8 passes thirty tests. SPIRV-Tools packages and the matching
SPIRV-LLVM translator now build/install. Corrected stale generated package prefix
metadata and explicitly set Darwin library search paths in the private CMake
recipe; no system paths/binaries were modified. The real pipeline compiles OpenCL
to LLVM bitcode, translates it to SPIR-V, then passes `spirv-val --target-env
opencl2.2`. Building the pinned libclc `spirv-mesa3d-` / `spirv64-mesa3d-` targets
is the next active dependency phase. Exact private command manifests retain the
resume commands. No real mesa_clc or NVK binary is claimed yet.

### NEXT-STEPS

1. Finish the active libclc build/install; configure a standalone real mesa_clc
   build using the private LLVM, SPIRV-LLVM, SPIRV-Tools and libclc dependencies.
2. Resume pinned NVK setup after mesa_clc validates a real source kernel.
3. Continue remaining native failure triage with valid negative controls; retain
   unresolved shader-interface and placeholder-path assertions as failures.
4. Keep the existing loaded driver and supervised-only PM/wake restrictions.

### mesa_clc bootstrap build in progress

Both pinned libclc SPIR-V targets built and installed. Standalone Mesa CLC setup
now succeeds against real private LLVM 19.1.7, LLVMSPIRVLib 19.1.0.0 and SPIRV-Tools
dependencies. The actual `mesa_clc` and `vtn_bindgen2` targets are being compiled
with two jobs. This clears configuration dependency blockers; executable/kernel
validation and NVK build readiness remain to be established. Exact resume command
is retained in the private `mesa-clc-build-command.private.json` manifest.

### NEXT-STEPS

1. Finish `meson compile -C <private mesa-clc-build> mesa_clc vtn_bindgen2 -j 2`;
   validate a real OpenCL kernel with the built tools before retrying NVK setup.
2. Preserve the now-validated regression repairs and continue remaining native
   shader-interface/placeholder failure triage.
3. Retain supervised-only kernel/wake boundaries and original loaded components.

## Real mesa_clc readiness and LLVM header compatibility fix

The local macOS patch added an unguarded `clang/Options/OptionUtils.h` include,
breaking LLVM 19 after standalone CLC configuration succeeded. The pinned Mesa
base already includes that header under `LLVM_VERSION_MAJOR >= 22`. Removed the
redundant patch addition, preserving the existing version guard. The complete
revised macOS patch dry-runs successfully against fifty-one original pinned-base
files. The repaired `mesa_clc` and `vtn_bindgen2` targets compile/link with real
LLVM 19.1.7; LLVM 22 compilation is not claimed.

The built CLC executable compiles an actual OpenCL kernel to valid SPIR-V. A
separate ordinary exported library function produces nonempty callable helper
definitions in both generated C/header output, avoiding reliance on kernel-only
binding output. Private OpenCL-to-LLVM-to-SPIR-V validation also passes. Both
libclc SPIR-V builtins targets are built/installed. Real toolchain versions and
binary identities are recorded in
[`evidence/ga102-mesa-clc-bootstrap.json`](evidence/ga102-mesa-clc-bootstrap.json).

Pinned NVK setup now succeeds using these actual tools. The `vulkan_nouveau` target
is being compiled with two jobs in the owned artifact tree. This advances
experimental driver build readiness; it does not qualify NVK linking, Darwin RM
archive production, boot compatibility or hardware behavior. Installed driver,
kernel collections and display/power settings remain unchanged.

### NEXT-STEPS

1. Continue `meson compile -C <private mesa-build> vulkan_nouveau -j 2` using the
   exact private `nvk-build-command.private.json` and CLC/toolchain PATH. Preserve
   the first real source/linker failure and diagnose it without stub dependencies.
2. Push the validated header compatibility patch and toolchain evidence.
3. Continue the six remaining native test failures individually; test repairs
   must preserve shader-interface and memory-access semantics.
4. Keep loaded components and supervised-only kernel/wake boundaries intact.

### NVK native link and CPU-only loader qualification

The full native `vulkan_nouveau` target compiled and linked, including Rust NAK
and Darwin NVRM sources. Artifact SHA256 is
`f16166ab72e9b40e4abab8928fea9d757071fb94c43866926b50c71cd929dd20`.
It is an x86_64 Mach-O dylib depending only on system libraries/frameworks.
All 611 undefined NVK entrypoint references are optional weak imports, matching
the installed reference's count; no hard undefined NVK/NVRM imports were found.
An owned CPU-only process loads it with `RTLD_NOW`, resolves the three ICD exports
and negotiates requested ICD versions 5/6/7 successfully to 5/5/5. No Vulkan
instance, GPU device, command submission or installed component change occurred.
This establishes native build/link/load readiness. Hardware correctness and the
separate standalone framebuffer/NVRM archive/boot work remain unqualified.

### NEXT-STEPS

1. Preserve/push the header compatibility fix and successful NVK build evidence.
2. Reproduce the known config-helper static-buffer/parser hazards with extracted
   real source and CPU sanitizers; prepare source fixes without editing system
   configuration or invoking hardware power/reset paths.
3. Prepare explicit isolated NVK dependency selection/provenance before any
   source-NVK GPU test. Keep the loaded driver and supervised PM boundaries.

### Cloud handover and NVK configuration synchronization

The active two-job NVK rebuild finished successfully before handover preparation.
The config-helper candidate uses pthread_once publication, exact line keys and
thread-local borrowed buffers. NVRM delegates its duplicate lookup while retaining
prefixed environment precedence. Original source fails parser controls and emits
TSan races; candidate parser/first-use/ring tests pass without warnings. The revised
complete patch was dry-run checked against the pinned Mesa base and rebuilt into
a native NVK dylib. See `evidence/ga102-nvk-config.json`. No candidate GPU behavior
or sleep/wake recovery is claimed; installed components remain unchanged.

The selected Python suite passes 72 tests with site packages disabled. Native
Rust tests and pure C config extraction are suitable cloud candidates; initial
Linux qualification remains pending. See `GA102-CLOUD-HANDOVER.md` for dependency,
resource and platform gates. Two recovered unfinished Swift presentation edits
remain preserved locally, outside the published baseline.

### NEXT-STEPS

1. Select dev/ga102-3080ti-diagnostics in cloud; run bash .codex/cloud-setup.sh.
2. Run the handover's small native parse/volatile/memcpy groups with one job/thread;
   establish the current full baseline only after resource checks.
3. Repair remaining buffer/texture semantic regressions with negative controls.
4. Keep source-NVK GPU provenance and PM deployment/wake validation for macOS
   and the physical card under the existing supervision boundaries.

### Linux translator regression qualification and saturation compilation

Rust 1.87.0 / real SPIRV-Tools v2026.4 reproduce the handover baseline:
2151 PASS / six FAIL / one pre-existing ignored. The six failures are outdated
test assumptions, not confirmed production translation defects:

| Regression | Finding and replacement proof |
| --- | --- |
| Forward device GEP phi / typed zero | Old entry lacks AIR parameter bindings and discards its return. A metadata-backed, observable fixture instead executes both selected addresses and the 24-byte record stride, preserving high address bits and exact output float bits. Pointer phi/select prohibition remains. |
| Forced unchecked i64 load / no helper | A guarded helper preserves the real physical read at source address + 8. CPU execution checks both output words and null-base suppression; validated lost-read and wrong-offset mutations fail the semantic check. |
| Texture/sampler metadata | Default texture 5 routes through heap set 2/binding 0 and address-table element 69; sampler remains set 0/binding 162. |
| High/last texture and sampler indices | Textures 40/127 route through elements 104/191; samplers 8/15 retain bindings 168/175. |
| Sampled/storage views of texture 40 | Sampled view uses the heap through element 104; storage view retains binding 520. |
| Unused 1D texture | Metadata dimension remains 1D; default route uses table element 64. |

All four texture tests retain their original flat-band checks in an explicit
flat-mode subprocess and independently prove the default heap route, slot mask,
image shape and NonUniform decorations. Valid wrong-slot, wrong-dimension and
wrong-set mutations are detected. Buffer group: 286 PASS / one existing ignored;
texture group: 148 PASS. Final full native suite: 2158 PASS / zero FAIL / one
pre-existing ignored (100.54 seconds). A bounded CPU SPIR-V executor checks the buffer fixtures;
unsupported instructions and unspecified memory fail loudly. No production
memory semantics, expected buffer results, exclusions or ignores were relaxed.

The performance change removes whole-type-table copying in `clamp_edges`, using
the existing single-type lookup for saturation/tanh bounds. Identical owned
color-filter workloads, alternating baseline/candidate processes and nine samples
per variant show median debug compilation times of 539.55 -> 419.95 ms (22.17%
reduction) for 256 float4 operations, 112.41 -> 104.23 ms (7.27%) for 64 float4
operations, and 93.27 -> 86.93 ms (6.79%) for 64 scalar operations. Fast float4:
113.02 -> 104.54 ms (7.50%). The 16-operation case shows only 1.75%; container
outliers overlap. All five SPIR-V outputs are byte-identical and really validated.
The timed native pipeline excludes validator subprocesses. These unoptimized
Linux compilation results do not establish optimized-build or desktop/FPS gains.
The new saturation contract test covers scalar and 2/3/4 lanes in float16/float32,
precise NClamp versus fast FClamp, exact zero/one bounds, and 32 valid negative
controls that collapse the clamp interval.

The next portable task also completed: extracted current NVK config source passes
parser/first-use/ring cases under GCC 14 ASan+UBSan and TSan. Original source fails
its functional controls and reproduces first-use/ring races (2/9 TSan warnings).
No config-helper source change was needed. Python GA102 suite: 72 PASS.
Normalized samples, classifications and sanitizer results are in
[`evidence/ga102-linux-translator.json`](evidence/ga102-linux-translator.json).
The existing ignored generic-callback cursor/store defect remains unresolved;
external private fixtures and actual RTX 3080 Ti behavior remain unqualified.

### NEXT-STEPS

1. Reproduce portable qualification with one job/thread:
   `CARGO_BUILD_JOBS=1 RUST_TEST_THREADS=1 cargo test --offline --locked --manifest-path translator/translator/Cargo.toml --lib -- --test-threads=1`.
2. Reproduce the owned benchmark outside Git:
   `cargo run --offline --locked --manifest-path translator/translator/Cargo.toml --example benchmark_saturation -- work/saturation-benchmark 9`.
   Compare against the handover implementation with the same example and profile;
   optimized-build measurements are a separate later qualification.
3. Next source task: investigate the already-ignored generic callback cursor/store
   refusal with the exact focused command
   `cargo test --offline --locked --manifest-path translator/translator/Cargo.toml --lib native_generic_callback_table_cursor_keeps_its_store -- --ignored --exact native::tests::buffers::native_generic_callback_table_cursor_keeps_its_store --test-threads=1`.
   Keep explicit refusal until a real stored-address proof supports a fix.
4. Actual Sequoia/RTX 3080 Ti validation must later check candidate shader rendering,
   optimized compilation, compositor pacing and stability with verified source/image
   provenance. No macOS build, physical-host access or installed-component change
   was performed in this Linux session.

### Generic callback store fix and optimized compilation qualification

The explicitly executed ignored callback regression reproduced a genuine emitter
defect: its device store was refused because the preceding generic table-pointer
load became an unmodeled placeholder. Existing typed analysis already recognizes
non-escaping generic device-pointer tables. Field/aggregate load paths consumed
that proof, but the raw-buffer load path accepted only address-space 1/2 pointer
results. It now also materializes recognized address-space 0 table loads as real
64-bit device addresses, using existing guarded loads, offset calculation and
access flags. Other generic pointer uses retain their previous handling.

The original regression is now enabled after mandatory real SPIR-V validation and
observable memory proof. Original slot 1, runtime slots 0/1/2 and a volatile variant
store exactly integer 7 into the selected four bytes, preserving every other byte
and nontrivial high address halves. Executed volatile accesses check both 8-byte
pointer reads and the 4-byte store, including shared guarded-helper reuse. Valid
lost-store and wrong-slot SPIR-V mutations fail the memory oracle. The former
refusal regression now supplies an actual mixed table/data use, which still fails
explicitly rather than losing its read/store. Buffer group: 287 PASS / zero ignored.

Release builds fit the existing cloud budget: Rust 1.87, optimization level 3,
16 codegen units, incremental disabled, one job and offline locked dependencies.
Baseline/candidate builds took 205.55/194.79 seconds, with sampled total cgroup
memory peaks below 4.7 GiB of the 8 GiB limit. The only benchmark implementation
difference is the original versus optimized `clamp_edges`; callback code and
workloads are identical. No LLVM/Mesa/wrapper or macOS toolchain was rebuilt.

Ten alternating paired process rounds provide **100 samples per variant per
workload**. Timing includes the native compilation pipeline and excludes validator
subprocesses and byte comparisons. Every measured shader equals its validated
warmup; all twenty process outputs and source workloads match across variants.
Warmup and final modules pass real SPIRV-Tools v2026.4 validation.

| Workload | Median ms, original -> optimized | p95 ms, original -> optimized | Median reduction | CV %, original -> optimized |
| --- | --- | --- | --- | --- |
| 16 precise float4 operations | 3.41 -> 3.23 | 5.64 -> 5.04 | 5.45% | 30.00 -> 33.49 |
| 64 precise float4 operations | 10.97 -> 9.55 | 11.54 -> 10.71 | 12.98% | 15.99 -> 5.83 |
| 256 precise float4 operations | 55.71 -> 36.61 | 57.78 -> 40.60 | 34.28% | 2.22 -> 6.67 |
| 64 precise scalar operations | 9.02 -> 7.79 | 9.41 -> 8.16 | 13.61% | 1.88 -> 2.05 |
| 64 fast float4 operations | 10.98 -> 9.46 | 11.39 -> 10.04 | 13.81% | 2.88 -> 3.79 |

The debug improvement remains meaningful in this optimized comparison. The
primary 256-operation case improves in all ten pairs; a 20,000-resample bootstrap
of paired process-median reductions gives a 95% interval of 33.56–35.11%. This
interval estimates the paired-median reduction, separately from the overall
sample-median ratio in the table. The smallest case has substantial variability;
no general small-shader or actual desktop/FPS improvement is established. Exact
samples, IQR/ranges, byte hashes and build settings are in
[`evidence/ga102-callback-release.json`](evidence/ga102-callback-release.json).
Full native suite: **2159 PASS / zero FAIL / zero ignored** (102.00 seconds).
Python GA102 tests: 72 PASS. Actual Sequoia/RTX 3080 Ti behavior remains untested.

### NEXT-STEPS

1. Reproduce the now-enabled store proof:
   `CARGO_BUILD_JOBS=1 RUST_TEST_THREADS=1 cargo test --offline --locked --manifest-path translator/translator/Cargo.toml --lib native_generic_callback -- --test-threads=1`.
2. Reproduce optimized workloads outside Git:
   `CARGO_BUILD_JOBS=1 CARGO_PROFILE_RELEASE_CODEGEN_UNITS=16 CARGO_PROFILE_RELEASE_INCREMENTAL=false cargo run --offline --locked --release --manifest-path translator/translator/Cargo.toml --example benchmark_saturation -- work/release-saturation 10`.
   Compare original/optimized bounds lookup with otherwise identical source and
   alternate process order; keep binaries and generated shaders outside Git.
3. A later authorized hardware session must validate rendering and stability for
   callback-bearing shaders and profile compilation/desktop pacing with verified
   candidate image provenance. No physical-host access or installed-system changes
   were made in this Linux work.

### Runtime path audit and bounded sampler translation improvement (Linux)

Source audit at `8fd5960` establishes the candidate path; it does not establish
which binaries a physical desktop has loaded. `NVMTLLibraryLoad.m` loads the
bundled/fallback `libnvmtl_translate.dylib`, sets capabilities to 3, and calls the
wrapper C ABI. Ordinary, function-constant, linked and sampler translations enter
the native constructed translator. The saturation lookup optimization therefore
applies to cold translations containing those operations, including sampler
variants. It does not accelerate SPIR-V/pipeline cache hits or NVK's backend.
`build/build_xlate.sh` defaults to a separate `$HOME/nvmtl-build/bindless` checkout;
a later build must explicitly select the intended source and verify loaded image
hashes rather than assume these commits affect an installed stack.

| Runtime layer | Existing reuse and remaining work |
| --- | --- |
| Metallib/AIR | Lazy entry indexing; bounded 128 MiB strong index cache; AIR text disk cache and process cache of 128 entries/16 MiB. Extraction and reflection are distinct costs. |
| Ordinary/functions/links | SPIR-V disk keys incorporate input, stage and translator content tag (`c3`); FC/link inputs have their own keys. Hits bypass Rust compilation. Reflection also has a disk path. |
| Compute specialization | `nvmtl_translate_variant` persists sampler/threadgroup variants in `variant1` SPIR-V cache. |
| Graphics sampler specialization | `nvmtlBindSamplerPipeline` normalizes sampler keys and consults per-pipeline and device-wide caches. On a miss it synchronously translates vertex/fragment stages and creates a render pipeline while holding the pipeline monitor. This particular `nvmtl_translate_samplers` helper has no SPIR-V disk cache; the global cache clears at 1024 entries. |
| Address lowering/NVK | Address-lowering results have bounded process reuse. `nvmtl_vk.c` creates shader modules and graphics/compute pipelines through the selected Vulkan ICD, using `VK_NULL_HANDLE` application pipeline caches. Mesa disk caching is configured separately; a null application cache does **not** prove absent driver caching. The repository carries a Darwin NVK patch, not a complete standalone Mesa source checkout. |

References: `plugin/NVMTLLibraryLoad.m` (`nvmtl_xlate_ready`,
`nvmtl_spvcache_path`, `nvmtl_compile_library_entry`, `nvmtl_translate_variant`,
`nvmtl_translate_samplers`); `plugin/NVMTLObjects.m` (`nvmtl_sampvar_*`,
`nvmtlBindSamplerPipeline`); `plugin/nvmtl_vk.c` (`nvmtl_vk_initialize`, pipeline
creation); `translator/wrapper/src/lib.rs`; `nvk/nvk-macos.patch`.

Repeated work is plausible when new processes/pipeline states encounter variant
misses, cache eviction or concurrent misses across distinct pipeline objects.
The source does not prove their desktop frequency. No cache key, eviction policy,
Foundation concurrency or GPU pipeline lifetime was changed without that evidence.

The bounded confirmed issue is duplicate reflection in the actual sampler ABI:
reflection of specialized AIR was immediately followed by an identical default
reflection to select formatless storage-image options. A shared helper now derives
those options from the existing reflection. Input specialization, sampler-index
filtering, capabilities, storage-image options, fallback errors and memory semantics
are preserved. This removes one reflection even when no declared sampler matches;
the existing translation fallback is unchanged.

The optimized Linux wrapper builds with Rust 1.87, opt-level 3, 16 codegen units,
incremental disabled and one job. Baseline build: 237 s; candidate wrapper-only
rebuild: 6.99 s. No LLVM/Mesa/macOS build was attempted. The explicit C ABI harness
uses existing fragment sampling, vertex-position and storage-write Rust fixtures;
there are no generated amplification shaders or private compositor substitutes.
Two runs each alternate ten paired baseline/candidate batches, with 100 timed
calls per variant/workload/run after five warmups. Timing covers the ABI call,
including reflection and translation; output copying/freeing and validation are
outside timing. Builds/tests were not concurrent with measurements.

| Owned workload | Median ms, baseline -> candidate | p95 ms, baseline -> candidate | Median reduction | CV %, baseline -> candidate |
| --- | --- | --- | --- | --- |
| Fragment nearest/pixel | 1.363 -> 1.329 | 1.779 -> 1.602 | 2.45% | 10.27 -> 9.52 |
| Fragment linear/pixel | 2.076 -> 2.051 | 2.186 -> 2.314 | 1.21% | 4.23 -> 4.47 |
| Fragment linear/normalized | 0.994 -> 0.965 | 1.127 -> 1.108 | 2.84% | 6.11 -> 5.81 |
| Vertex, unused bound sampler | 0.846 -> 0.823 | 0.941 -> 0.917 | 2.70% | 5.05 -> 5.78 |
| Storage write, unused bound sampler | 1.242 -> 1.118 | 1.379 -> 1.188 | 9.98% | 8.99 -> 4.33 |

Each aggregate contains **200 samples per variant**, retaining both trials and
raw samples in [`evidence/ga102-runtime-translation.json`](evidence/ga102-runtime-translation.json).
The largest reduction is a storage-image fallback case, not a compositor shader.
Fragment savings are only 25–33 microseconds in these fixtures; linear/pixel p95
worsens. This is a small measured miss-path improvement, not general latency/FPS
or desktop acceleration evidence.

All measured outputs equal the validated warmups, and baseline/candidate modules
are byte-identical. Real SPIRV-Tools v2026.4 validates Vulkan 1.2 outputs, including
all capability settings 0/1/2/3. Nearest/linear and pixel/normalized programs must
differ; unsupported active sampler state, malformed constant keys and malformed AIR
must fail identically. An undeclared sampler must leave output unchanged; real
validation must reject corrupted SPIR-V magic. Native texture regressions: 148
PASS / zero FAIL / zero ignored. Python GA102 suite: 72 PASS. The full wrapper
unit suite was not run: it requires source-built SPIRV-Tools and unavailable
private fixtures. Direct ABI regression coverage uses the external real validator
without skipping tests or changing their assertions.

The next substantial path to qualify is **synchronous NVK pipeline creation on
graphics variant misses**, together with its cache reuse. Historical owned-compute
[`evidence/ga102-mesa-pipeline-ab.json`](evidence/ga102-mesa-pipeline-ab.json) shows
pipeline p95 18.575 ms owned-cold / 17.526 ms owned-reuse despite improved median
reuse. Those eight small kernels and three processes per condition do not isolate
NVK compilation, initialization or a desktop bottleneck; cache files are not hit
counters. No current hardware profile identifies the dominant desktop cost.
Further cache/pipeline source changes would be speculative without that profile.

### NEXT-STEPS

1. Reproduce ABI regression/measurement with baseline `8fd5960` and this candidate
   built using identical release settings and explicit source checkouts. Preserve
   each shared library outside Git, then run:
   `python3 tools/ga102_runtime_translation_test.py --baseline work/runtime-wrapper-baseline.so --candidate work/runtime-wrapper-candidate.so --output work/runtime-abi-recheck --rounds 10 --samples 10`.
   Put real `spirv-val` on PATH; an absent validator is a failure. Build only with
   `cargo build --offline --locked --release --manifest-path translator/wrapper/Cargo.toml --lib --target-dir translator/translator/target` and one job.
2. The most useful subsequent step requires a separately authorized RTX 3080 Ti /
   Sequoia session: verify isolated candidate translator/plugin/ICD image hashes,
   then use owned offscreen composite workloads to separate AIR extraction,
   reflection/translation, sampler variant hit/miss, address lowering and Vulkan
   pipeline creation, with identical cold/reuse workloads and pixel correctness.
   Correlate these costs with frame pacing before changing caches or claiming
   desktop gains. Existing `tools/air_cache_tests/mesa_pipeline_probe.swift` is a
   compute reference only; representative graphics execution is still required.
3. No physical-host access, installed-component change, macOS build or display
   operation occurred. Further meaningful desktop qualification is hardware-bound;
   this Linux phase ends with the measured bounded fix rather than more diagnostics.

### First new GA102 hardware session: runbook prepared, execution pending

[`GA102-HARDWARE-VALIDATION-RUNBOOK.md`](GA102-HARDWARE-VALIDATION-RUNBOOK.md)
pins candidate `acb7241` and baseline `8fd5960`, separates Cloud preparation from
Mac read-only inventory/builds and GPU execution, and specifies final artifact,
source, actual function image and dependency provenance. No Mac command/build or
hardware access occurred; execution awaits explicit user approval.

Existing namespace correctness harnesses remain useful but cannot yet attribute
this graphics timing experiment: composite uses a constexpr sampler; ordinary
translation counters do not count the sampler ABI; ICD pointer attribution and
per-operation timings/cache counters are absent. Release initialization strips
AIR-cache/ICD overrides, so the existing isolated-cache flag is not sufficient.
The runbook blocks launches under its no-production-cache-write plan until
reviewed owned-cache routing and sampler/ICD provenance exist. It defines a bounded
runtime-sampler gradient oracle, first-miss/local-hit/device-reuse sequence, paired
owned-cold/persistent-reuse processes, failure stops and required evidence.
Cloud namespace/provenance/core regression suite: 72 PASS. No new harness or
current Darwin candidate binary is claimed.

### NEXT-STEPS

Await user approval of the runbook. Before any timing execution, prepare/review
the specified copied-source cache routing and sampler/pipeline instrumentation
with exact invocations and negative controls. Retain installed kernel/RM/NVK
unchanged; no deployment, display or recovery operation is authorized here.
