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
