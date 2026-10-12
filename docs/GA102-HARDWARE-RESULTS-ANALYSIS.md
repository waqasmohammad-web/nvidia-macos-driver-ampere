# GA102 sampler and pipeline preparation follow-up

## Starting point and hardware evidence

Development starts from fetched `origin/dev/ga102-3080ti-diagnostics` at
`68f57d3bff2a7e9cc67735c5dd90904a2541b4ee`, on that branch, with a clean tree.
The original local `work` branch at `40f018b` is preserved. No reset, main merge,
installed-driver change or GPU execution is part of this follow-up.

The owner reports successful qualification on macOS Sequoia 15.8.1 and an
RTX 3080 Ti Founders Edition: all 24 extended offscreen runs passed rendering,
isolation and shader validation. Harness `68f57d3`, baseline `8fd5960`, candidate
`acb7241`. The following are supplied paired summaries, not independently
reanalysed raw logs. Raw per-process times, absolute hardware savings, spread,
confidence intervals, thermal history and cache-hit attribution are unavailable.

| Operation | Paired median change (positive = faster) | Faster pairs |
| --- | ---: | ---: |
| Reused nearest sampler ABI | +2.06% | 5/5 |
| Reused linear sampler ABI | +2.26% | 4/5 |
| Cold nearest sampler ABI | +1.59% | 3/5 |
| Cold linear sampler ABI | -0.10% | 2/5 |
| Cold initial Vulkan pipeline | +1.89% | 3/5 |
| Cold nearest Vulkan pipeline | -4.92% | 1/5 |

Qualification establishes correctness for those artifacts and that workload.
Five pairs do not establish causality or general desktop improvement. A relative
percentage alone cannot determine whether a stall consumes a frame budget.

## Why the sampler gain is small

`acb7241` replaces the second default reflection of *the same specialized AIR*
with `formatless_options_reflected(&reflection, caps)` in the actual Rust sampler
ABI. It does not change nearest/linear sampling, function-constant specialization,
SPIR-V emission or NVK compilation. Earlier Linux ABI checks found byte-identical
outputs and only 25–33 microsecond fragment savings on their owned fixtures.
Those absolute Linux times cannot be transferred to this Mac.

Each miss still decodes JSON and function constants, specializes AIR, reflects
resources, selects active sampler states, emits/transforms SPIR-V and allocates
output. Pixel-linear translation emits a more complex fetch/interpolation program
than nearest. The eliminated reflection is a small fraction of total compilation;
its relative importance depends on source size and shader features.

"Reuse" here means persistent caches in a new process. Graphics sampler variants
have no SPIR-V disk cache, so the ABI still executes on the measured miss draws.
Within a process, local/device variant hits bypass the ABI and Vulkan creation;
reflection reuse has no benefit on that hit path. This explains why an ABI
microbenchmark does not measure ordinary steady-state desktop drawing.

The reused ABI results agree in direction with the prior Linux small-gain result.
Cold results vary with process startup, allocation and competing work. Without
raw pairs, attributing the variation to any specific factor would be speculation.

## Cold nearest pipeline investigation

The measured `vk_pipeline` span is the actual `pvkCreateGraphicsPipelines` call
inside `nvmtl_opaque_CreateGraphicsPipelines`, after Rust translation. The original
reflection change cannot directly remove work inside that call. Byte-identical
SPIR-V is a useful negative control, but does not rule out indirect timing effects
or establish identical compiler-cache state on every run.

On a graphics variant miss, `nvmtlBindSamplerPipeline` synchronously performs:

1. Sampler normalization, JSON key creation and local lookup under the PSO monitor.
2. Device-wide key construction/lookup; descriptor description and AIR digests.
3. Stage specialization (an empty sampler dictionary reuses the existing stage).
4. Render PSO creation: address lowering, vertex-input/resource scans, render pass,
   descriptors, shader modules, pipeline layout and finally the timed NVK call.
5. Shader-module cleanup, variant publication, resource retention and binding.

The initial pipeline, nearest miss and linear miss execute in that fixed order in
the qualified harness. Thus nearest is the first *specialized* graphics pipeline
in the process; linear is later. First-use/compiler initialization, cache state
and shader complexity are confounded with filter order. The -4.92% / 1-of-5 result
is a concern to retain, not a reason to revert a byte-preserving frontend change
or invent a pipeline-cache fix. `VK_NULL_HANDLE` application pipeline caches do
not imply Mesa has no internal/disk shader cache. File persistence is not a hit.

The follow-up isolated profile adds an inclusive `pipeline_total` span around
`nvmtl_vk_pipeline_create_impl` and retains `vk_pipeline` unchanged. Their
difference estimates preparation plus cleanup outside the driver call, including
instrumentation overhead. It does not attribute that residual to a specific NVK
phase. Both counts must match, and inclusive time must contain driver time.
Address-lowering time remains separately available; spans can overlap and must
not be summed indiscriminately.

`--sampler-first linear` reverses miss/local-hit and device-hit filter order while
retaining the same shaders, descriptors and per-filter pixel oracles. Use separate
matched sessions for nearest-first and linear-first, alternating session order.
Baseline/candidate arm order still alternates within each session. Pair cold and
reuse separately; exclude qualification runs; retain absolute saved nanoseconds,
paired relative changes and faster-pair counts. No significance or FPS claim is
generated. The new schema accepts old v1 records for offline validation, but live
v2 runs require rebuilt, hash-matched profile proofs and the requested order.

## Safe optimisation priorities

The implemented candidate shares AIR text lowering and stage-metadata parsing
between reflection and constructed translation within a single ABI call. The
prepared object binds its input and stage and stores no sampler options or global
state. Reflection/translation still validate their own options. Unused-sampler
fallback reuses the already computed reflection for formatless-image selection,
while preserving capability gating, threadgroup lengths and default retry policy.
There is no additional cache, eviction, Vulkan lifetime or GPU ordering change.

Further opportunities, gated by measurements:

| Opportunity | Likely responsiveness benefit | Required evidence / boundary |
| --- | --- | --- |
| Avoid repeated frontend analysis on a miss | Shorter synchronous preparation stalls | Actual ABI differential correctness and CPU benchmarks; implemented here |
| Cache graphics sampler SPIR-V across processes | Avoid frontend work on repeated app starts | Real miss frequency; exact keys covering AIR/constants/stage/caps/threadgroup policy/translator identity; corruption and bounded-size controls |
| Reuse encoder sampler key/selection | Reduce repeated hit-path JSON/lookup work | Hit-path absolute cost; invalidate on pipeline/sampler mutation, preserve resource retention and binding |
| Coalesce concurrent equivalent PSO misses | Avoid duplicate compilations across PSOs | Concurrent-miss trace; careful ownership, failure/retry, lock ordering and key equivalence |
| Share Vulkan layouts/modules or use a pipeline cache | Reduce driver preparation/compilation | NVK phase attribution, thread safety and lifetime tests; no speculative application cache patch |
| Replace clear-all variant eviction with bounded retention | Reduce bursts of recompilation | Actual eviction frequency and retained memory, correct lifetime/release behaviour |

Prefer the first two preparation measurements before changing pipeline sharing.
This work does not tune GPU math, clocks, power/reset, display or installed files.

## Validation and next steps

Linux results and exact build handover are recorded in the investigation's latest
checkpoint and `docs/evidence/ga102-prepared-air.json`. Native tests use actual
SPIRV-Tools. Wrapper ABI benchmarks call no Vulkan/GPU API and use real owned AIR
fixtures, output equality and invalid-state/error controls. Darwin compilation
and the new candidate's rendering/isolation remain pending, regardless of the
earlier candidate's successful physical qualification.

Use the updated hardware runbook for source-pinned builds in owned directories.
Any future GPU execution requires separate authorization; the prior reported
session does not authorize another. Leave working installed graphics binaries
in place. Compare the new translator against `acb7241` to isolate this incremental
change using identical plugin sources and the same v2 harness revision for both.
