# ENDGAME ENCORE — local source qualification, 13 October 2026

Qualified on actual Darwin x86_64 / macOS 15.8.1 / RTX 3080 Ti. Baseline:
`65b3ed56460ef047141c02f2d527b1837e92e813`; surface/upload arm: `7c85310`;
coalescing candidate and current Cloud harness: `706f226096cd2b1d4e846f842baa7820d10453cd`.
NullMoth Systems attribution and existing licensing are preserved.

The Cloud candidate is qualified for the tested **isolated user-space workloads**.
Installed graphics components, kernel collections, EFI/OpenCore, display and
security settings were not changed. Existing Swift experiments and earlier
benchmark artifacts remain preserved. This does not establish desktop improvement.

## Source builds and gates

Both baseline and candidate NVK ICDs were built from the complete respective
patches and the pinned Mesa `17ca6174dcc6cb22059ac343bc29f8af7800f42e` archive
(SHA256 `602ae1e398fd07c8ac5e0389051836f7cccff77de82c43ec97acdfdfeab3fc0d`).
Existing NVIDIA 610.57.04 headers supplied the required NVRM dependency; no
replacement was invented. The 2,285-header manifest is hashed in the evidence.
Mesa used identical debugoptimized settings and one build job. Existing real
Mesa CLC, vtn_bindgen2, glslang and Rust tools were retained rather than rebuilt.

Both ICDs pass RTLD_NOW loading, all three loader exports, negotiation at interface
7, x86_64 inspection and dependency review. The source builds link the same
reviewed zlib 1.3.2 dependency. Installed NVK is retained in the closure because
Apple loading can introduce it; actual Vulkan function images must match the
selected source ICD. No installed-ICD extraction fallback was used.

Three separately built translators have identical tracked inputs/settings:
Rust 1.99.0, SDK 15.5, release opt3/codegen16/incremental-off/one job.
Three namespaced plugin arms use the same v2 profile and one new common metallib.
Every accepted GPU process passes binary/source/hash/namespace/function-image/
closure/owned-cache/pixel/error gates and real SPIRV-Tools 2026.4 validation.
Twenty paired capture multisets are byte-identical across the two coalescing arms.
Raw paths, binaries, logs, captures, commands and machine inventory remain private.
Normalized hashes, counts, raw numeric samples and distributions are in
[evidence/ga102-encore-hardware.json](evidence/ga102-encore-hardware.json).

## Publication and lifetime correctness

Baseline family backing fails alias frame 10: green byte 0 instead of 128.
Baseline forced-private backing fails queued frame 1 with the same incorrect byte.
Each first failure was retained; unchanged failing sequences were not retried.

Both the surface-only arm and coalescing candidate pass 480 cases per backing
(cold/reused caches), **960 per arm**. Actual backing must be family VRAM or the
explicit test-only private fallback as requested. Coverage includes queued/same-
buffer clear-read, compatible/read-only aliases, partial updates preserving all
other pixels, shared-event cross-queue ordering, CPU edits, abandoned recordings,
translucent alpha and ordinary textures. Each surface checks all 640×360 GPU
pixels; CPU pixels are independently checked after a read-only IOSurface lock.
RGB tolerance is one byte; alpha is exact. Mode-level p50/p95/p99 and raw timing
samples are retained. At 20 frames/mode/process, empirical p99 is the maximum.
The first alpha=0.5 diagnostic produced 127 against a strict 128 oracle; that
finding remains recorded. The exact-alpha case specifies 128/255, with no relaxed
tolerance. This is a fixture/input correction, not a driver alpha fix.

All three source arms pass four-thread, mixed-size CPU surface imports with
256 bytes of row padding, immediate release of application texture/surface
references before command commit, and exact GPU byte readback. A 4096×2049 import
exceeds the 32 MiB staging cap, followed by a small import. Source-ASan/UBSan
controls independently cover eviction, TLS exit, key/begin/create/submit failure
and uncertain completion retention; no physical fault/timeout was injected.

Large pitched import preparation/completion (one process/cache per arm, ms):

| Arm | Cold prepare / complete | Reuse prepare / complete |
|---|---:|---:|
| Baseline | 62.063 / 12.142 | 60.613 / 13.503 |
| Surface-only | 65.007 / 13.923 | 64.178 / 12.214 |
| Coalescing | 66.312 / 12.399 | 64.551 / 12.188 |

Following small imports vary from 0.681 to 8.706 ms across arms. This is correctness
qualification, not an upload speedup or absence-of-later-stalls claim. Thread-local
retention and uncertainty handling are proven by the CPU controls; no global
physical staging-retention counter is claimed. Weak-map cleanup is covered by
Foundation controls, not a physical cross-process lifetime oracle.

## Physical allocator comparison

The test holds 31 one-MiB buffers, frees ranges 0/2/1 while sentinels remain live,
requires **three actual retirements**, and requests one three-MiB joined range.
All 31 MiB of surviving/joined data are copied on the GPU and byte-checked each
round. Five paired fresh-process trials alternate arm order, with cold/reuse
conditions and three rounds each. Only coalescing production source differs
between the surface-only and final arms; both use the same source ICD.

| First joined request, ms | Surface-only | Coalescing |
|---|---:|---:|
| Cold median | 3.257674 | 0.189616 |
| Cold p95 / p99 / max | 3.344826 | 0.198449 |
| Reuse median | 2.878792 | 0.174222 |
| Reuse p95 / p99 / max | 3.584014 | 0.197043 |

All ten first-request pairs improve; paired median savings are 3.068058 ms cold
and 2.704570 ms reused. Baseline/surface-only grow from 32 to 40 MiB; the candidate
stays at 32 MiB. First requests above 1 ms fall 5/5→0/5 in each cache condition.
Subsequent rounds reuse retained capacity, so they do not claim repeated heap-growth
savings. Five process samples give empirical tails, not a population guarantee.

The first fixture incorrectly kept autorelease references alive (live buffers did
not decrease). Those results are **not fragmented-reuse evidence**, despite the
old acceptance function accepting the byte copies. Nested allocation autorelease
pools and a fail-closed live-count gate repaired the workload; all published paired
fragmentation measurements use the corrected fixture.

Uniform 128-request waves still have 16/128 requests above 1 ms initially, then
8/128, putting growth into p95. Five-pair first-wave medians initially worsen:
cold 71.224→74.740 ms; reuse 72.427→77.050 ms. That direction is not consistent
in three additional instrumented attribution pairs: cold 72.593→72.521 ms;
reuse 70.972→70.198 ms. No general uniform-wave speedup is claimed. Representative
first-trial-set cold request p95/p99 are 2.477/2.884→2.523/3.029 ms. Full raw
samples, wave totals and per-condition distributions remain in the evidence.

Attribution pairs observe exactly 16 growths initially. Cold growth consumes
34.771/34.898 ms (surface/candidate), versus 0.009/0.008 ms lock wait. In this
single-thread workload growth, not lock contention, dominates pool duration.
This does not qualify contention under arbitrary concurrent allocation.

An explicit private pool-timer-off control restores the actual production pool
body, declares telemetry unavailable, records transform/source/binary hashes,
and retains the other qualification gates. Three alternating pairs pass the
physical waves and retirement. First-wave on/off medians: cold
71.857/71.347 ms; reuse 71.871/71.838 ms. Later-wave differences change direction.
Other tracing stays common; this is not a fully uninstrumented production benchmark.
Timer-disabled binaries cannot claim surface/fragmentation telemetry qualification.

All allocation sessions also hold 1,568 live descriptor sets, grow reservation
256→4,352 across two pools, retire to zero with allocated=freed, and reuse both
pools. Three 64 MiB GPU copies/process check every byte and pooled-buffer live
counts return to their pre-wave value. Both arms pass the nine original buffer
boundary sizes, including below/at/above the four-MiB pooled/dedicated threshold.
No physical 262,144-set saturation is claimed.

## Installed-stack composition and screenshot discrepancy

The unchanged installed stack runs three 120-frame controls per load, at 1920×1080
render resolution in a 640×360 window, using clear-only/four/eight blended draws.
All 1,080 commands complete without command errors or timer skips. Median GPU
intervals across runs are approximately 0.033/0.184/0.323 ms. Steady observed
presentation p99 ranges 17.202–17.750 ms, after the first ten positive observations.
Clear startup traces include 32.713/33.684 ms intervals despite prompt client
completion; these are observations, not a WindowServer root-cause attribution.

One four-layer run has only 117 positive timestamps: startup frames 0/1/2 are
missing. Its original NOT VERIFIED pacing verdict remains; the threshold was
not changed. Other eight runs pass API pacing gates. System flip counters are
shared, not exclusive to this window. No composition pixel, physical scanout,
application-benchmark or candidate desktop improvement claim follows.

The owned-window visual probe verifies 12 distinct GPU frames and positive
presentation timestamps. Its capture preflight returns false: zero capture
attempts, no permission request or security change. New capture matching is
therefore unqualified.

The supplied screenshot has alpha 255 in every pixel; the transparency-like
appearance is already in its RGB data. Its embedded ICC profile passes ColorSync
verification without errors/warnings and creates a CoreGraphics colour space.
The phone photo shows greater opacity/frosting, but is not a synchronized or
calibrated pixel oracle. The reproduced source-baseline publication faults make
stale surface data worth investigating, but **do not establish this screenshot's
cause**. WindowServer composition, CPU page-off/publication, capture flattening
and colour conversion remain distinct hypotheses. ScreenCaptureKit exposes its
own colour-space configuration ([Apple documentation](https://developer.apple.com/documentation/screencapturekit/scstreamconfiguration)); that is not evidence
of a particular conversion error here. Reference images/profile bytes stay private.

## Regressions, failures and continuation

107 standard-library Python tests pass with no exclusions. Actual-source host
and descriptor allocators and FD/upload/readback controls pass ASan/UBSan; Darwin
Foundation queue/publication probes pass. Rust source is unchanged, so no new
full native Rust-suite claim is made. Apple compilation found and repaired the
publication fixture's IOKit macro collision and nonoptional IOSurface pointers.
Setup/build/logging/control compilation failures are retained and listed in the
normalized evidence; none was converted into a hardware pass.

Next portable command:
`python3 -S -m unittest discover -s tools -p 'test_ga102_*.py'`.
Then `python3 tools/ga102_host_pool_test.py --pool-telemetry` and the actual upload
control with real Vulkan headers. Do not launch a full Mesa/LLVM build in Cloud
by default. Prioritize cross-process publication/capture correctness and bulk
surface preparation costs; retain the uniform-wave p95 trade-off.

A future physical comparison must use new owned directories and reviewed
source-ICD closures. Example joined-hole command (explicit approved hardware only):

```sh
python3 tools/ga102_allocation_probe.py --fragmentation-only \
  --plugin "$GA102_PLUGIN" --metallib "$GA102_METALLIB" \
  --dependency-manifest "$GA102_DEPENDENCY_MANIFEST" \
  --output "$GA102_SESSION/new-fragmentation" --execute-reviewed
```

Integrated candidate presentation needs independently recoverable backups,
rollback verification and proof of active component images before deployment.
Git history supplies none of those. No installation-level experiment was performed.
