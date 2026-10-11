# GA102 desktop acceleration investigation

Status: autonomous visual validation and compositor tracing in progress;
GPU pattern/negative controls validated; own-window capture unavailable;
desktop root cause and installed-driver improvement unresolved, 2026-10-11.
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
- **NOT VERIFIED:** latest three-run batch rendered correct patterns while
  visibly ineligible, with no presentation timestamps or display activity.
  Full visual reproducibility, physical scanout and desktop improvement remain
  unverified. Display-linked versus timer pacing needs a naturally active GUI.
- **BLOCKED:** own-window capture authorization, protected WindowServer stack
  access, and full framebuffer build inputs (missing generated `nvkms.h`).
  No permission request, privilege escalation or stub replacement was used.
- **SOURCE VALIDATED only:** shader-cache helper and framebuffer completion
  accounting, within the build/test limits documented below. No changed driver
  has been installed. Existing synchronization waits are preserved.
- **Latest safe work:** durable scoped artifacts, repeated-run acceptance and
  conservative 60 Hz timing gates; 19 Python tests pass. Objective remains open.

## Scope and operating constraints

RTX 3080 Ti / GA102 (`10de:2208`), Intel i9-12900K, MSI Z690, OpenCore,
macOS Sequoia 15.8.1. Preserve the established 3440 × 1440 @ 60 Hz baseline.
No installation, reboot, mode/refresh change, EFI/OpenCore/SIP change, or driver
configuration write is part of this audit. No sudo has been used. Existing Git
history and the uninstalled shader-cache proposal are preserved.

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
