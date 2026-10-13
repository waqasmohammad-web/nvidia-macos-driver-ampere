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
