# GA102 desktop acceleration investigation

Status: initial architecture audit and bounded investigation completed; validated
cache source fix published; desktop root cause unresolved, 2026-10-11.
Branch: `dev/ga102-3080ti-diagnostics`. Starting revision: `c52e088`.

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

The only driver implementation change made is the regression-tested cache policy
correction (`f3ebd0c`); it was built but not installed or loaded. Test additions
and this report are independently reviewable. No system/graphics configuration,
installed driver, EFI, SIP, system permissions, display mode or refresh rate was changed;
no sudo, reboot, service interruption or production-cache deletion occurred.
