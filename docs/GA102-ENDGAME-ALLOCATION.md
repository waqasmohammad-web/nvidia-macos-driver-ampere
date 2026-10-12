# Final local allocation milestone

Baseline: `a56c78f`. Published source: `ad48444`. Driver/instrumentation inputs match the locally GPU-tested `61b5b0f`; publication adds the separately qualified boundary mode and manifest checks. The complete published source tree equals local `4864b79`. No installed binary, configuration, display mode, boot or security component changed. Existing Swift experiments and historical results remain intact.

## Attribution and targeted change

Actual PFN instrumentation shows that the dummy buffer dominates descriptor dummy-resource setup. Five paired processes per cache condition measure:

| Component | Cold median ms, baseline / candidate | Reuse median ms, baseline / candidate |
| --- | ---: | ---: |
| Dummy buffer total | 9.349 / 2.349 | 9.151 / 2.126 |
| Host Vulkan allocation | 9.161 / 2.142 | 8.815 / 2.000 |
| Host mapping | 0.151 / 0.131 | 0.198 / 0.097 |
| Sampled image | 0.113 / 0.103 | 0.099 / 0.085 |
| Storage image | 0.072 / 0.067 | 0.067 / 0.064 |
| Texel view | 0.006 / 0.005 | 0.004 / 0.004 |
| Sampler | 0.015 / 0.013 | 0.016 / 0.013 |

The original 256-byte dummy buffer creates a 32 MiB host pool. The candidate uses 8 MiB blocks for the host pool, preserves its 4 MiB maximum pooled request and 64 MiB idle capacity, and leaves the separate VRAM block size/retention unchanged. It does not defer a 32 MiB allocation to a later first-use path. Subsequent host growth also uses 8 MiB blocks. NullMoth source attribution and licensing remain unchanged.

## Controlled pipeline comparison

Both arms use identical release translator inputs/settings, the same diagnostic harness, common metallib and retained ICD/LLVM closure. One-pair qualification precedes each five-pair comparison. Qualification is excluded from statistics; positive savings mean faster candidate. Times are milliseconds.

| Order | Cache | Inclusive median, baseline / candidate | p95, baseline / candidate | Paired saved | Faster |
| --- | --- | ---: | ---: | ---: | ---: |
| nearest-first | cold | 14.533 / 7.774 | 15.411 / 8.113 | 6.777 | 5/5 |
| nearest-first | reuse | 12.514 / 6.086 | 13.794 / 7.446 | 6.760 | 5/5 |
| linear-first | cold | 15.050 / 8.214 | 15.386 / 9.596 | 6.836 | 5/5 |
| linear-first | reuse | 13.091 / 6.356 | 14.151 / 7.242 | 6.720 | 5/5 |

All twenty process pairs improve inclusive initial preparation. At five samples, nearest-rank p95 is the maximum sample; it is not a reliable population tail estimate. Public PSO wall samples, exact hashes and raw paired observations are retained in the normalized evidence.

## Later allocation costs and the retained regression

Five additional A/B trials alternate arm order. Each cold/reuse process first qualifies the shader/cache/namespace contract, then runs three 128 MiB buffer allocation waves. Each wave copies all 64 MiB of source data on the GPU and verifies every destination word before releasing resources. Source and destination buffers remain concurrently alive through completion. The 64 MiB idle budget prevents the regression that retaining only two smaller blocks would introduce.

| Cache / wave | Allocation total median, baseline / candidate ms | Request maximum median ms | Request p95 median ms | Faster allocation-total pairs |
| --- | ---: | ---: | ---: | ---: |
| cold / 0 | 80.682 / 75.953 | 10.173 / 2.964 | 0.386 / 2.587 | 5/5 |
| cold / 1 | 44.679 / 43.108 | 9.569 / 3.016 | 0.369 / 2.502 | 5/5 |
| cold / 2 | 45.645 / 43.076 | 10.038 / 3.058 | 0.409 / 2.512 | 5/5 |
| reuse / 0 | 82.403 / 74.948 | 9.895 / 3.111 | 0.432 / 2.546 | 5/5 |
| reuse / 1 | 45.034 / 42.053 | 9.939 / 2.977 | 0.383 / 2.478 | 5/5 |
| reuse / 2 | 45.217 / 42.711 | 9.637 / 2.994 | 0.411 / 2.505 | 5/5 |

**Trade-off:** per-request p95 worsens in every paired wave because allocation spikes are smaller but more frequent. The candidate reduces the measured maximum stall and total allocation/wave duration, not every latency percentile. All thirty allocation-total and full-wave paired comparisons are faster; GPU copy/completion directions remain mixed. No GPU execution-throughput gain is claimed.

Peak host-pool capacity falls from 160 to 136 MiB; after completed waves it falls from 96 to 72 MiB. The idle capacity remains 64 MiB; the difference comes from the smaller active block. Pooled live-buffer counts return to their pre-wave value in every process.

## Physical growth and correctness

- Three 1536-draw command buffers per stress process alternate two texture bindings, forcing actual new descriptor snapshots. The first holds 1568 allocated sets and grows to two pools / 4352 reserved sets. Each completion returns live sets to zero and allocated/freed totals match. Later rounds reuse the same two pools. Expected initial pool exhaustion is handled by growth; no unhandled allocation, free or command failure is accepted.
- Each stress command checks its final 1024 pixels exactly. This does not claim that every intermediate overwritten draw has a separate readback.
- Every buffer wave checks all 64 MiB; both initial trials and twenty paired stress processes pass. Actual captured SPIR-V event/hash multisets match across arms for all five trials and both cache conditions, and every capture passes the real validator.
- Additional candidate cold/reuse processes verify exact GPU copies at 1, 255, 256, 257, 4096, 65535, 4 MiB minus one, 4 MiB and 4 MiB plus one bytes, covering alignment and the pooled/dedicated transition. Live pooled counts return after each case.
- 87 standard-library GA102 tests pass. Actual host allocator functions pass ASan/UBSan controls for failed heap/placement rollback, growth, fragmented free order, reuse, trimming, unchanged VRAM policy and full cleanup. Descriptor opener sanitizer controls retain the exact 262144-set ceiling and failure accounting.

The failed initial diagnostic compilation and test-extraction fixes are recorded in evidence; they occurred before candidate qualification. No check was weakened to produce a pass.

## Evidence and Cloud continuation

[Normalized evidence](evidence/ga102-endgame-allocation.json) retains timings, raw allocation samples, resource snapshots, source/artifact hashes and coverage limits. Full commands, build proofs, shader captures, binaries, cache roots and raw logs remain in the task-owned private session directory outside Git.

The compiled plugin/translator and instrumentation files are unchanged between tested `61b5b0f` and publication. The standard stress Swift input also remains unchanged; the final tool additionally supports the separately tested boundary mode. Build provenance retains actual local pins rather than relabeling existing binaries.

Exact next portable commands:

```sh
python3 -S -m unittest discover -s tools -p 'test_ga102_*.py'
python3 tools/ga102_host_pool_test.py
python3 tools/ga102_descriptor_pool_test.py --vulkan-headers "$GA102_HEADERS/include"
```

The C extraction requires a real C compiler and ASan/UBSan; descriptor checks require real Vulkan headers. Missing dependencies are failures/limitations, not replacement stubs. Native Rust is unchanged; retain one Cargo build job and test thread and real SPIRV-Tools for future translator work. The allocation/GPU runner rejects Linux execution.

Further source work should preserve the idle byte budget, improve fragmentation/reuse with actual source controls, and investigate the per-request p95 trade-off. Any altered block policy still requires physical qualification. Full descriptor-budget saturation, broad concurrent multi-queue workloads, desktop/frame pacing and installation are outside this milestone. Owned-cache cold does not control OS/internal-driver caches or clocks; available Vulkan error callbacks are not exhaustive hardware-fault telemetry.
