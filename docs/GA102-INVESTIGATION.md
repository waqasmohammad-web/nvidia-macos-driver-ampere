# GA102 desktop acceleration investigation

Status: architecture audit and passive diagnostics in progress, 2026-10-11.
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

No driver implementation has been modified during this audit. Proposed
implementation changes will be explained with their evidence, rollback and
acceptance test before they are made or pushed.
