# ENDGAME Cloud candidate — 13 October 2026

Base: verified `65b3ed56460ef047141c02f2d527b1837e92e813`.
Branch: `dev/ga102-endgame-cloud`. The initial in-progress port was stashed,
fast-forwarded from `a56c78f`, then restored. No local Mac filesystem was accessed.
The main diagnostics branch is unchanged by Cloud work.

## Selective surface and upload integration

NullMoth Systems retains original authorship and licensing. Source attribution:

- `bee05d1e5d57fd448ad6bea9371d3a395b0eb385`: weak committed surface writers,
  per-plane publication/import monitors, weak private-image backing cache, and
  detach-before-NVK-client-pooling. Failed detach closes instead of pooling.
- `68ba3a8`: prerequisite recording-local clear ownership. Clear encoding no
  longer marks global CPU seed state as current before execution; abandoned
  recordings leave CPU import available. Encoder imports consult recorded and
  committed ownership. Full-overwrite blit optimizations and 3D changes are excluded.
- `77e4c9839f5925a7087357d552790a7edcc978fa`: synchronous, bounded per-thread
  upload staging. This branch already had synchronous uploads and reusable staging;
  this port separates upload command/storage lifetime, caps normal retention at
  32 MiB per thread, and retains uncertain `-2` resources instead of freeing them.
  This is not evidence of a new upload speedup. TLS-key failure fails closed;
  null input and overflowing pitched spans are rejected.
- Readback layout/dependency transition from the same pinned upstream surface
  implementation: a fence alone does not change sampled/storage image layout
  to transfer-source layout.

No upstream kernel, installer, display policy, swizzle, storage-twin feature or
streaming WC-copy change is included. Swizzle/twin lifetime fixes depend on features
absent from this base. The coordinated NVRM change requires a separately built
source NVK ICD; using an older installed ICD does not test it.

Linux verification: 91 Python tests (87 inherited + 4 source-wiring controls),
actual upload helper ASan/UBSan with real Vulkan-Headers v1.3.290 at
`b379292b2ab6df5771ba9870d53cf8b2c9295daf`, actual descriptor opener ASan/UBSan,
and extracted actual NVRM close/pool ASan/UBSan (1,000 reuse cycles, detach
ordering/failure, live mappings, full pool). Upload controls cover pitched/tight
bytes, reuse, synchronous submit, >32 MiB eviction, thread exit, begin/create/
submit failures and uncertain completion. Vulkan/IOKit calls are test doubles,
not real GPU or IOKit operations. Complete patch syntax parses with
`git apply --numstat nvk/nvk-macos.patch`; full pinned-Mesa application/build is
still required. LICENSE and NOTICE are unchanged.

The Foundation concurrency probes are preserved as
`ga102_surface_queue_test.py` and `ga102_surface_publication_test.py`, credited to
NullMoth's regression tools with synthetic IOSurface type declarations corrected.
They explicitly refuse Linux. Their compilation, weak-map behavior and actual
Objective-C synchronization remain UNQUALIFIED. Portable wiring controls do not
substitute for these tests. No Darwin plugin/Metal build or RTX validation is claimed.

## Required macOS qualification

Use a new clean worktree and new private artifacts; preserve uncommitted Local
experiments. Never install candidate components as part of offscreen qualification.
Pin baseline `65b3ed5` and each Cloud candidate to full SHAs. Retain matched
translator inputs/settings, real SPIRV-Tools, explicit isolated ICD/LLVM paths,
namespace ownership, dependency hashes and owned cache proofs from the existing
hardware runbook. Build separate baseline/candidate NVK ICDs from the pinned Mesa
base and complete patches. Qualify real loader exports and dependency closure
before GPU execution. No installed ICD extraction fallback.

Exact CPU commands on macOS, before GPU testing:

```sh
python3 tools/ga102_surface_queue_test.py
python3 tools/ga102_surface_publication_test.py
python3 tools/ga102_fd_pool_test.py
python3 tools/ga102_upload_lifetime_test.py --vulkan-headers "$GA102_HEADERS/include"
python3 tools/ga102_host_pool_test.py
```

Then rebuild the namespaced plugin and translator with the current
`build/build_isolated_plugin.py --graphics-performance` profile and existing
runbook, explicitly selecting the compatible source ICD. Run normal v2 pixel,
cache, ABI and real shader validation first. Surface testing must cover same-buffer
clear/read, committed queued clear/read, compatible aliases (including read-only
usage), partial updates preserving all other pixels, cross-queue event ordering,
CPU edits after completion, abandoned recordings, private fallback and shared
family VRAM. Require both baseline/candidate results, zero unexpected errors,
verified actual backing mode, independent pixel oracles, weak lifetime cleanup
and bounded process timeouts. Never treat an unsupported shared import as shared
coverage. Include immediate texture destruction after upload, multithreaded
uploads, large one-off eviction and error handling. Do not intentionally fault
or reset the physical GPU to test timeout handling.

Known limits: pending-writer entries track the latest committed writer per queue/
plane; applications still need queue/event dependencies. Monitors are process-local,
not cross-process GPU synchronization. A later CPU seed invalidates suppression.
Private backing keys include dimensions, format, writable capability, resource
options and framebuffer-only state. Incompatible wrappers are not promised alias
coherence. Normal retention is per-thread, not a global 32 MiB budget; uncertain
GPU resources intentionally remain retained until process termination. Steady
allocation waves, desktop presentation and other applications remain unmeasured.

## Allocation p95 investigation and coalescing candidate

Reanalysis of the published 128-request waves finds **exactly** 4/2/2 requests
above 1 ms per baseline cold/reuse wave, and 16/8/8 per 8 MiB wave, in every
one of five trials. Thus warm-wave incidence crosses the 5% quantile boundary:
2/128 = 1.5625% versus 8/128 = 6.25%. These are real retained Local samples,
not Cloud allocation measurements. Uniform fully released waves do not require
fragmentation to explain this percentile shift. Their maximum and total stall
improve while p95 necessarily includes a growth event more often.

Actual source inspection found a separate reuse defect: `pool_block_give` returns
when it finds its first adjacent hole and fails to join a second neighbor. It can
also skip idle reset on that early-return path. New code consumes every adjacent
range, returns an enlarged tail to the bump allocator and resets fully idle blocks
first. It preserves 8 MiB host blocks, 64 MiB idle capacity and all VRAM sizing.
The retained 8 MiB block control allocates eight 1 MiB ranges, frees ranges 0/2/1
with a sentinel still live, then requests 3 MiB. Baseline needlessly grows another
block; candidate reuses offset zero in the existing block. The same assertion
fails baseline and passes candidate under ASan/UBSan. 5,000 deterministic varied-
size allocation/free operations verify that live ranges never overlap, in addition
to existing growth, rollback, trimming and VRAM controls. This establishes CPU
range-reuse correctness, not measured GPU latency or resolution of wave p95.

Do not raise idle block count when experimenting with variable block sizes:
retention must use bytes. A first-8/later-16 MiB policy would reduce growth incidence
but could increase individual stalls and peak capacity. First-8/later-32 MiB risks
moving the original 9 ms stall later. Background preallocation also competes with
submission and can relocate spikes; it needs demand prediction, cancellation and
lock-contention evidence. No adaptive policy is enabled here. Measure realistic
working sets and per-frame allocation clustering before choosing a percentile
trade-off. Existing growth holds `g_pool_lock` across allocation/mapping, so one
slow growth can block unrelated allocator threads; changing lock scope requires
reservation/publication/trim lifetime redesign and concurrency qualification.

Required Local allocator comparison: baseline `65b3ed5`, surface-only commit,
and coalescing commit separately. Repeat the existing physical waves/boundaries
and descriptor-growth qualification, then keep sentinel buffers live while freeing
alternating adjacent ranges and requesting combined spans. Verify exact copied
bytes, live-range/accounting return, peak and retained capacity; report per-request
p50/p95/p99/max, >1 ms incidence and whole-frame totals. Include multithreaded
mixed-size creation, CPU upload, render and event-dependent readback before a
policy is considered suitable for application workloads.

## Scheduling and representative workload fixtures

The owned diagnostic build now records atomic pool request/failure counts,
request duration, allocator lock wait, growth count/time and growth with enough
aggregate free bytes (fragmented between holes/blocks). Production builds have
no new timers. The generated C instrumentation compiles and passes the same
actual allocator controls under ASan/UBSan (`--pool-telemetry`); source-transform
controls require unique sites and reject double application. Counters cover host
and VRAM pool attempts together, include failed growth, and snapshots should be
compared after quiescence. Growth time includes CPU heap creation/mapping/logging,
not an NVK compiler phase. Atomic fields are individually consistent, not a
transactional snapshot. Instrumentation overhead needs a diagnostic/plain control.
The profile records the helper transform hash and transformed-source hashes.

New `surface_stress.swift` is inserted by the existing owned runner with
`--surface-only`: eleven modes, twenty 640x360 exact-alpha/tolerance-one RGB
readbacks per mode, per-process cold/reuse conditions. It retains all ordinary
v2 qualification and image/cache/dependency/SPIR-V gates. It records actual
backing (family/private), CPU frame preparation, commit/scheduled/completed
callbacks, writer/reader GPU intervals and pool telemetry. Family imports must
actually succeed; silent fallback is a failure. Test-only forced-private mode
uses a separate `GA102_TEST_SURFACE_PRIVATE` knob in the copied source and leaves
production config clearing intact. CPU-seed changes, partial alias updates and
cross-queue shared-event dependencies are included. Callback ordering, coverage,
backing mismatches, missing/nonfinite GPU timestamps, bad pixels and incomplete/
regressing telemetry fail portable acceptance tests. Test controls are synthetic
records and are never hardware evidence. Compilation and GPU behavior remain
NEEDS MACOS VALIDATION, including current baseline behavior and timestamp support.

After the separate Local session authorizes isolated execution, rebuild both arms
using the latest harness commit, then run each with independently reviewed source
ICD closure. Use fresh output directories for each arm/backing:

```sh
python3 tools/ga102_allocation_probe.py --surface-only --surface-backing family \
  --plugin "$GA102_PLUGIN" --metallib "$GA102_METALLIB" \
  --dependency-manifest "$GA102_DEPENDENCY_MANIFEST" \
  --output "$GA102_SESSION/surface-family" --execute-reviewed
python3 tools/ga102_allocation_probe.py --surface-only --surface-backing private \
  --plugin "$GA102_PLUGIN" --metallib "$GA102_METALLIB" \
  --dependency-manifest "$GA102_DEPENDENCY_MANIFEST" \
  --output "$GA102_SESSION/surface-private" --execute-reviewed
```

These are offscreen scheduling/surface fixtures, not frame-pacing or display
measurements. To move beyond small startup work without duplicating the already
published presentation investigations, the existing six-second
`ga102_metal_present.swift` fixture now accepts independent render resolution and
0–16 full-target alpha-blended owned draws per frame. The window remains 640x360;
render resolution can be 1920x1080, 2560x1440 or 3840x2160 without changing display
mode. Existing eligibility, drawable acquisition, encode/commit/callback timings,
GPU intervals, frame/surface identities and API presentation traces remain.
Workload metadata is recorded with the result. Defaults preserve the old clear
probe. The composition shader/PSO is prepared before the timed frame trace.

This is a synthetic bandwidth/submission composition workload, not an application
benchmark. It is source-prepared only. The existing runner still rejects explicit
isolated plugin binding for windowed probes. **Do not install the Cloud candidate
or bypass that gate to run it.** The following is for a later separately authorized
installed-stack baseline session, not candidate qualification:

```sh
python3 tools/ga102_run_metal.py ga102_metal_present --display-linked \
  --render-size 1920x1080 --composite-layers 4 --repeat 3 \
  --result-json "$GA102_SESSION/pacing-1080p-four-layers.json"
```

Compare clear-only versus 4/8 layers at identical render size, display/visibility,
queue depth and system load; retain p50/p95/p99/max, skipped frames, startup frames
and steady intervals separately. Repeat timer/display-link and double/triple
buffer controls as in the earlier pacing investigation. Match presented frame
identities to independent owned-window capture with
`ga102_visual_present.swift`, `ga102_pacing_validation.py`, and the existing
capture/delivery validators before claiming visible delivery. A positive drawable
`presentedTime` or completed GPU command alone does not prove compositor receipt
or physical scanout. Capture permissions are never changed/requested to pass.
Candidate desktop qualification still needs a separately reviewed route that
proves the active system component/dependency images; it is not supplied here.

## Architectural follow-up

- `pool_buffer_create_in`: slow heap growth/mapping is under the global pool lock.
  New lock-wait telemetry can separate allocator contention from raw allocation.
  Coalescing helps fragmented reuse; it cannot remove capacity growth costs.
- `nvmtl_surface_in_for_cb` and SurfaceOut: CPU import/readback is synchronous;
  changing it to asynchronous requires destination-image retention, staging
  ownership, seed/generation publication and queue/event dependencies together.
  Fence removal by itself reintroduces use-after-free and stale content hazards.
- `nvmtl_pump_buffers` / `nvmtlAdvancePart`: the single execution worker finishes
  submissions across queues. A long wait/readback can delay otherwise independent
  queues. Segment and callback traces should measure this before changing scheduling.
  Do not parallelize the worker without reservation/part/event/ownership controls.
- `waitUntilScheduled` in `NVMTLObjects.m`: WindowServer deliberately waits for
  pixels before handing a surface to scanout because the display-pipe swap cannot
  currently be ordered after an NVK fence. This is an architectural dependency;
  shortening callbacks or changing the label cannot remove it safely.
- Translation and synchronous Vulkan pipeline creation remain workload-sensitive:
  warm sampler/compiler savings and cold linear regressions are retained in the
  earlier evidence. Correlate actual compile/cache misses with late frame IDs
  before optimizing more startup-only cases. No new translator/NVK compiler change
  is made here; the native translator suite was not rerun for these non-translator
  commits. The real validator remains available for subsequent source work.

## Cloud validation and next command

Final portable suite: **100 PASS** with `python3 -S`, no exclusions. C controls
use GCC 14.2.0 / Python 3.12.14 on Linux and ASan+UBSan. Actual readback extraction
additionally checks sampled/general/transfer-destination/transfer-source prior
layouts, transfer-read dependency and pitched row padding. A baseline NVRM patch
fails the detach oracle; candidate passes. The coalescing baseline fails the joined
span oracle; candidate passes. Neither deliberate negative control ran on a GPU.
Initial instrumentation extraction rejected an ambiguous lock site, and a captured
readback test failed warning-as-error compilation; unique line matching and braces
repaired those failures before success. Foundation fixture declarations were
source-corrected, but their Apple compilation remains untested.

Exact next Cloud command:
`python3 tools/ga102_host_pool_test.py --pool-telemetry`.
Exact next Local command: `python3 tools/ga102_surface_queue_test.py`, followed
by the publication probe, **before** candidate Apple builds/GPU execution. Preserve
all private Local experiments. No installation, reboot, wake/display/security
change or physical performance claim is part of this handoff.

The [normalized Cloud evidence](evidence/ga102-endgame-cloud.json) records source
hashes, command/count summaries, negative controls, toolchain and scope limits.
Readback failure-before-submit additionally restores its previous tracked layout;
its captured-call test requires unchanged destination bytes and layout on failure.
This avoids retrying a transition from a layout that never reached the GPU.
