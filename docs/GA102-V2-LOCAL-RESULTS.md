# GA102 v2 local hardware results

Local Darwin x86_64 / macOS 15.8.1 execution compared baseline `acb7241` with candidate `4095041`. Both arms used the v2 harness at `4095041`, Rust 1.99.0, SDK 15.5, one release build job and the same retained NVK/LLVM closure. Existing Swift experiments and earlier results were preserved in their original worktrees and output directories. Installed components and configuration were unchanged.

The one-pair session passed eight processes. Each five-pair session passed 24 processes (four qualification processes and twenty timed processes). Both filter orders passed all 1024 pixels per draw with zero channel error, all required sampler/cache branches, actual image attribution, dependency hashes and real Vulkan 1.2 SPIR-V validation. All measured Vulkan error counters were zero; this is callback/command evidence, not a claim of exhaustive hardware fault monitoring.

## Prepared-AIR comparison

Positive paired change means faster candidate. Each row has five process pairs; qualification is excluded. Times are microseconds. p95 at n=5 is the maximum sample and is not a reliable population tail estimate.

| Order | Cache | Filter | ABI paired change | Saved us | Faster pairs | Binding paired change |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| nearest-first | cold | nearest | +9.37% | +247.0 | 4/5 | +4.23% |
| nearest-first | cold | linear | -12.73% | -318.0 | 2/5 | -5.78% |
| nearest-first | reuse | nearest | +3.24% | +97.0 | 3/5 | -3.13% |
| nearest-first | reuse | linear | +1.99% | +43.0 | 4/5 | +1.87% |
| linear-first | cold | nearest | +4.75% | +84.0 | 4/5 | -1.36% |
| linear-first | cold | linear | -16.67% | -452.0 | 0/5 | -14.12% |
| linear-first | reuse | nearest | +6.53% | +102.0 | 4/5 | +5.78% |
| linear-first | reuse | linear | +1.48% | +58.0 | 3/5 | -3.57% |

The candidate reduces nearest ABI paired medians in all four conditions. Cold linear ABI regresses in both orders; reuse linear ABI improves modestly, while binding direction remains mixed. Initial/reused pipeline totals vary independently of the sampler fix. No universal latency or tail improvement is established.

The common owned metallib AIR was then fed directly to the actual baseline/candidate sampler ABI: twenty alternating batches of ten calls after five warmups, without compilation or GPU work running concurrently. Nearest improves 3.33% / 50.27 us (17/20 faster batches); linear improves 2.61% / 54.94 us (18/20). Output bytes match and pass real SPIR-V validation. Repeated CPU calls support a warm translation benefit; they do not explain away the observed cold-process regression.

## Actual preparation bottleneck

Initial inclusive pipeline preparation is roughly 17–19 ms outside the Vulkan creation call. Separate opt-in diagnostic builds preserve the original timing artifacts. Across eight diagnostic processes, descriptor setup median is 17.04 ms: layout 0.061 ms, descriptor pool 5.279 ms, dummy resources 9.178 ms, dummy zeroing 0.357 ms, bindless heap 2.181 ms. These are process-start observations, not per-frame costs or named NVK compiler phases.

The original first pool reserves 4096 sets. The candidate reserves 256 initially, then uses existing 4096-set pools. One additional pool slot and a capped final 3840-set pool preserve the original 262144-set total budget. Creation failures do not advance either count. Locking, set allocation/freeing and exhaustion fallback remain unchanged.

The extracted production pool opener passes ASan/UBSan with real pinned Vulkan headers and a captured-call test double, covering both mutable and ordinary descriptor counts, first/later/final capacities, failure accounting and ceiling refusal. This CPU test does not replace actual GPU qualification or validate saturation on the physical driver.

## Validated pool-sizing improvement

The locally committed source candidate `7ad6e18` was rebuilt with identical translator
source inputs and qualified against `4095041`. The explicit descriptor-pool
comparison permits only `nvmtl_vk.c` to differ; other plugin inputs, translator
inputs/settings, dependency closure and diagnostic logging settings remain gated.
Both qualification and five-pair sessions pass. The repeat runs linear-first
before nearest-first, reversing the original session order.

| Order | Cache | Inclusive median ms, baseline / candidate | p95 ms, baseline / candidate | Paired improvement | Paired saved ms | Faster |
| --- | --- | ---: | ---: | ---: | ---: | ---: |

| nearest-first | cold | 19.909 / 15.103 | 20.052 / 15.417 | 24.33% | 4.758 | 5/5 |
| nearest-first | reuse | 18.145 / 13.411 | 19.965 / 14.316 | 29.32% | 5.285 | 5/5 |
| linear-first | cold | 19.878 / 14.293 | 20.981 / 14.639 | 29.50% | 5.880 | 5/5 |
| linear-first | reuse | 18.824 / 12.603 | 20.727 / 13.369 | 33.11% | 6.238 | 5/5 |

All twenty process pairs improve initial inclusive preparation. The public Metal
PSO wall medians also improve: 21.71 → 16.60 ms / 18.96 → 14.32 ms for
nearest-first cold/reuse; 21.36 → 16.21 ms / 19.60 → 13.37 ms for linear-first.
This is a process-start preparation improvement. Later variant/Vulkan timings
remain mixed; it is not a shader execution, steady frame or compiler improvement.

A separate diagnostic pair attributes the change to the initial pool: median
creation falls from 5.38 to 0.44 ms. Dummy-resource creation remains the next
large cost. The change reserves less memory initially; later growth may move an
allocation stall to workloads exceeding 256 simultaneously reserved sets.
Full pool growth/saturation is covered with captured Vulkan calls under
sanitizers; physical GPU growth/saturation has not been qualified.

Across all original, diagnostic and improvement runs, 136 processes and 816
render/readback draws passed; every checked channel matched exactly and measured
Vulkan error counts were zero. All draw GPU timestamps were present. This does
not establish unobserved hardware fault counters or broad application coverage.

The published source commit `a1d3538` has the identical complete Git tree as the
locally tested `7ad6e18`; publication recreates only commit metadata. Evidence
retains the actual build pins and records the verified tree equivalence.

## Limits and retained evidence

All raw logs, binaries, source/build manifests, caches and exact commands are retained outside Git in the new private session directory. The [normalized evidence](evidence/ga102-v2-local.json) contains source/artifact hashes, individual paired samples, absolute medians/p95, wall/encoding/GPU/readback statistics, correctness counters and diagnostic spans.

Cold means new owned AIR/SPIR-V/Mesa roots; Apple/OS/internal driver caches, clocks and scheduling remain uncontrolled. Mesa persistence is not an explicit NVK cache-hit counter. Internal sampler reflection remains inside the ABI span. No desktop FPS, responsiveness, scanout, sleep/wake or installed-stack improvement is claimed.
