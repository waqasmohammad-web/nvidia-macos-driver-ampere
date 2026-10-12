# GA102 Sequoia isolated user-space validation runbook

Status: **PREPARED IN CLOUD; NO MAC BUILD OR HARDWARE EXECUTION AUTHORIZED OR PERFORMED.**
Target source: `acb724185daba72de472e5954e69d3cec6221c51` on
`dev/ga102-3080ti-diagnostics`. A later documentation commit does not change this
source pin. This runbook requires the user's approval before any Mac work.

## Decision and scope

Rebuild the translator and a namespaced plugin from pinned source; retain the
existing installed kernel/RM/NVK as common dependencies. Test only owned offscreen
resources in fresh child processes. Never install the resulting bundle/dylib.
Preparation and device initialization are separate: even `--initialize-only`
loads constructors and opens GPU channels, so it belongs to hardware execution.

**Current readiness: build recipe and correctness probes exist; the requested
attributed graphics timing experiment is BLOCKED pending bounded harness work.**
The gates below are mandatory. Approval of this document does not turn an absent
measurement/provenance control into a pass. Do not run the performance phase until
its reviewed implementation and exact invocation have been added to this runbook.

No installed graphics file/configuration write, kext load, kernel-collection build,
EFI/OpenCore/SIP change, display/window/capture operation, reboot, logout, graphics
service restart or remote host access is part of this procedure. User-space GPU
execution still shares the physical GPU and can affect its stability; namespace
isolation is attribution, not a separate GPU or kernel sandbox.

## What the repository establishes

| Existing component | Use and limitation |
| --- | --- |
| `build/build_isolated_plugin.py` | Copies plugin sources, renames classes/protocols and literal lookups into `NVMTLGA102_`, hides C symbols and renames the resource-device global. Builds one x86_64/O1/release-mode translation unit. Accepts explicit `--translator`; otherwise silently selects installed translator. Always links `air-runtime` to the installed bundle. Use an explicit translator. |
| `tools/ga102_isolated_plugin_probe.m` | Explicit `dlopen`, class/method image checks, NVAccel service binding and RTX 3080 Ti name check. Namespaced mode tolerates only the known installed plugin under original classes, including IOSurface autoload. At exit checks all candidate class images, buffer/device identity and ordinary translator/lowering function images. It does not currently expose sampler or ICD function provenance. |
| `tools/ga102_run_metal.py` | Builds an owned Swift snapshot with enumeration shadowed by explicit binding; requires matching plugin/translator hashes and exit markers; external compiler/process deadlines. `--repeat` is 1–3 fresh processes, not repeated draws in one process. Windowed/capture explicit-candidate routes are refused. |
| `ga102_metal_render_smoketest.swift` | 16×16 offscreen RGBA8 render; center pixel near `[64,128,191,255]`, tolerance 2. Correctness only, no render-pipeline timing. |
| `ga102_metal_composite.swift` | Four 3440×1440 private/IOSurface cases, 16/32 blended layers; 16 sampled pixels per case, tolerance 3, eight timed frames after two warmups. Uses **constexpr nearest/normalized sampler**, so it does not exercise bound-runtime sampler specialization. One pipeline creation is outside frame timing. |
| `air_cache_tests/mesa_pipeline_probe.swift` and `mesa_pipeline_ab.py` | Eight installed-stack compute kernels, direct device enumeration. Not an explicit-candidate graphics harness. Do not use unchanged for candidate attribution. |
| `ga102_runtime_translation_test.py` | Actual translator ABI with owned textual AIR, real SPIR-V validation and byte equality. Linux CPU evidence, not GPU execution or Objective-C cache/NVK timing. |

Historical namespaced GPU passes and old dylib hashes in the investigation are
useful precedents, **not identities for these new builds**. Latest Linux evidence:
2159 native tests previously pass; sampler-reflection comparison has 200 samples
per variant/workload with byte-identical validated SPIR-V, about 25–33 µs fragment
median savings. Historical compute pipeline p95 18.575/17.526 ms cold/reuse does
not isolate graphics compilation or prove a desktop bottleneck. Sources:
[`GA102-INVESTIGATION.md`](GA102-INVESTIGATION.md),
[`evidence/ga102-runtime-translation.json`](evidence/ga102-runtime-translation.json),
[`evidence/ga102-namespaced-isolation.json`](evidence/ga102-namespaced-isolation.json),
[`evidence/ga102-mesa-pipeline-ab.json`](evidence/ga102-mesa-pipeline-ab.json).

## Preparation responsibilities

| Cloud, no Mac needed | Mac, only after approval |
| --- | --- |
| Pin/review source and workload specification; run portable namespace/provenance negative tests; prepare manifests and result schema. | Read-only host/tool/dependency inventory; verify Sequoia/GA102 and available build budget. |
| Implement/review the missing copied-source instrumentation, owned-cache routing and runtime-sampler workload before timing execution. | Compile x86_64 Mach-O translator/plugin/probe using Apple SDK; record final hashes and dependencies. |
| Validate emitted owned SPIR-V on Linux; prepare software pixel oracle and baseline/candidate equality controls. | Resolve private Apple Metal frontend/accelerator ABI compatibility; execute isolated children and read actual GPU outputs. |
| Check documentation and publish approved preparation source. | Observe GPU faults/desktop health and retain private logs, image inventories and raw timings. |

This turn prepares documentation only. No new measurement harness is claimed.
Cloud cannot produce or qualify these Darwin binaries. No full LLVM/Mesa/NVRM or
kernel rebuild is necessary for the proposed translator/plugin comparison.

## Entry conditions and read-only Mac preflight

User approval must identify this source pin, the allowed phases and the final
reviewed harness revision. The owner must be present, the desktop stable, and no
other build/test or driver maintenance running. If instability is already present,
stop; this is not a recovery procedure. Preserve the existing display mode.

Choose absolute task-owned paths outside installed graphics locations. In the
examples, `GA102_REPO`, `GA102_SESSION` and `GA102_HEADERS` are owner-selected
absolute paths; `GA102_SESSION` must be a new directory. Do not use the repository
home build scripts' default `$HOME/nvmtl-build/bindless` checkout by assumption.

Proposed **read-only** preflight commands, not executed in Cloud:

```sh
git -C "$GA102_REPO" status --short
git -C "$GA102_REPO" branch --show-current
git -C "$GA102_REPO" rev-parse HEAD
git -C "$GA102_REPO" cat-file -e acb724185daba72de472e5954e69d3cec6221c51^{commit}
uname -m
sw_vers
xcrun --sdk macosx --show-sdk-version
xcrun --find clang
xcrun --find swiftc
xcrun clang --version
xcrun swiftc --version
rustc --version
cargo --version
rustup target list --installed
spirv-val --version
git -C "$GA102_HEADERS" rev-parse HEAD
```

Use existing read-only hardware inventory to confirm PCI `10de:2208` / RTX 3080 Ti
and Intel/x86_64 Sequoia. Do not run Metal enumeration as a preflight shortcut:
it can load/initialize the installed GPU stack. Record only relevant inventory,
not a full private machine dump. Later explicit binding must independently confirm
RTX 3080 Ti and actual selected Vulkan device/chip. Missing tools/dependencies
are a blocker; installation/security changes are not an implied step.

### Exact dependency set

- Rust >=1.87, Cargo, existing `x86_64-apple-darwin` target and Apple linker. Pin
  the **same Rust version** for both arms. Wrapper's own Cargo.lock and the native
  path dependency must come from the pinned worktree. Needed library crates:
  `metal2vulkan` with `serde`, `serde_json`, `rspirv` and locked transitives.
  `cargo build --lib` avoids dev dependency `spirv-tools-sys`; do not substitute
  `cargo test` and inadvertently rebuild SPIRV-Tools.
- Existing Xcode/CLT providing Apple clang, Swift, macOS SDK and Foundation,
  Metal, IOSurface, IOKit, CoreFoundation, Objective-C and libSystem frameworks/
  libraries. Past builds used clang 17/SDK 15.5; that is a precedent, not a required
  SDK identity. Record current versions and use the same SDK for both arms.
- Plugin build inputs are the checked-in `plugin/` source/header/shader-header
  files copied by the builder; no generated kernel binary or shader-header rebuild
  is required. `NVMTLDevice.m` includes the other plugin units in one translation
  unit. Do not add unrelated toolchain/build scripts.
- Vulkan-Headers include root with `vulkan/vulkan_core.h`. Historical pin is
  `c46850864f4661461b0f6cb9922c058ffea4915e`; use that revision if available, or
  review and record an explicit replacement before building. Builder takes its
  `include/` directory, not the repository root.
- Existing known `air-runtime/libLLVM.dylib` dependency at
  `/Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/air-runtime/`. Builder
  symlinks this directory. Hash the resolved library and its non-system dependency
  closure. It needs the LLVM C bitcode/parser/IR-print APIs; optional pass-builder
  and IR-walk APIs enable the existing AIR unroll path. If unavailable, source
  falls back to `/Library/GPUBundles/nvmtl/air-opt`; hash that tool/closure and record
  fallback, or stop. Do not invent/rebuild a substitute AIR frontend.
- Existing `/Library/GPUBundles/nvmtl/libvulkan_nouveau.dylib` and its resolved
  non-system dependency closure, installed NVAccel/RM/kernel interfaces and private
  Apple `MTLIOAccelDevice`/Metal source compiler support. Keep them unchanged and
  common to both arms. Read-only hash `/Library/GPUBundles/nvmtl/nvrm610.conf` and
  check relevant overrides locally; do not publish its contents or edit it.
  A configured alternate/vendor path must be disclosed and attributed, or stop.
- Real `spirv-val` (Linux qualification used SPIRV-Tools v2026.4), standard-library
  Python 3.10+ and enough measured RAM/disk for one release build job. No Mesa,
  NAK, LLVM source build, kext or boot work belongs to this session.

## Mac preparation: reproducible builds, no GPU execution

Perform only after approval. Baseline `8fd5960` and candidate `acb7241` isolate the
reflection-reuse change; plugin source is identical between these two pins.
Thus this A/B cannot independently measure every historical plugin change or
saturation optimization. Both arms test current plugin integration; comparison
to an unknown installed source revision is a separate observational reference.

```sh
mkdir -m 700 "$GA102_SESSION"
git -C "$GA102_REPO" worktree add --detach "$GA102_SESSION/baseline-src" 8fd5960d0bda6bde25f435b8f05b2cd35c58f431
git -C "$GA102_REPO" worktree add --detach "$GA102_SESSION/candidate-src" acb724185daba72de472e5954e69d3cec6221c51
```

Verify each worktree's exact HEAD and clean tracked source before building. Record
its full tree SHA, Cargo.lock hashes, builder/probe/runner hashes and all plugin
input hashes. Do not stash, reset or discard unrelated edits. For each `GA102_ARM`
(`baseline`, then `candidate`), in a controlled shell with the recorded Rust/SDK:

```sh
GA102_SOURCE="$GA102_SESSION/$GA102_ARM-src"
GA102_OUT="$GA102_SESSION/$GA102_ARM"
mkdir -m 700 "$GA102_OUT"
CARGO_BUILD_JOBS=1 CARGO_PROFILE_RELEASE_CODEGEN_UNITS=16 CARGO_PROFILE_RELEASE_INCREMENTAL=false \
  cargo build --offline --locked --release --lib --target x86_64-apple-darwin \
  --manifest-path "$GA102_SOURCE/translator/wrapper/Cargo.toml" \
  --target-dir "$GA102_SESSION/cargo-target" > "$GA102_OUT/translator-build.log" 2>&1
cp "$GA102_SESSION/cargo-target/x86_64-apple-darwin/release/libnvmtl_translate.dylib" "$GA102_OUT/libnvmtl_translate.dylib"
python3 "$GA102_SOURCE/build/build_isolated_plugin.py" \
  --output "$GA102_OUT/plugin" --vulkan-headers "$GA102_HEADERS/include" \
  --translator "$GA102_OUT/libnvmtl_translate.dylib"
```

Check each exit status immediately; never copy a prior artifact after a failed
build. The shared target directory saves dependencies; copy each completed arm
before the next build. If offline crates are missing, record the exact dependency
blocker and prepare the locked cache separately. Keep compilation and measurement
non-concurrent. Do not run `build/build_xlate.sh`: it defaults to a separate checkout
and performs stripping/install-name/signing operations outside this recipe.

The command above is the **existing builder's build-only recipe**, not permission
to launch it. It does not close the cache or timing gates below. A reviewed builder
extension must preserve release-mode behavior, namespace and hidden C symbols;
record the original and transformed source hashes, its diff and instrumentation
revision identically for both arms. Do not switch to debug mode to recover logs.

Inspect final artifacts without loading them:

```sh
lipo -archs "$GA102_OUT/libnvmtl_translate.dylib"
lipo -archs "$GA102_OUT/plugin/NVMTLDriver"
otool -L "$GA102_OUT/libnvmtl_translate.dylib"
otool -L "$GA102_OUT/plugin/NVMTLDriver"
nm -gU "$GA102_OUT/libnvmtl_translate.dylib"
nm -gU "$GA102_OUT/plugin/NVMTLDriver"
shasum -a 256 "$GA102_OUT/libnvmtl_translate.dylib" "$GA102_OUT/plugin/NVMTLDriver"
```

Record `otool -l` UUIDs and code-signature status too. If a private-artifact signing
step is required, review it separately and hash **after** the final change; never
change signing policy. Require x86_64 and all plugin-consumed `nvmtl_*` exports.
Compare the complete export sets; missing ABI entries stop execution. No dependency
may resolve to an unknown task artifact. A content hash alone does not prove the
source: retain successful build command/log plus clean pinned input and manifests.

## Mandatory provenance and cache gates before any GPU launch

1. Match `isolation-proof.json.binary_sha256` against final plugin bytes; require
   `class_prefix=NVMTLGA102_`, hidden C symbols and reversible namespace mapping.
   Match every `source_sha256` input to the selected worktree. New instrumentation
   requires separate transformed-source hashes; proof flags alone are insufficient.
2. Canonicalize the sibling translator symlink; require it to resolve to the
   explicit arm artifact, not installed release. Hash must equal the isolation proof
   and independent build manifest. Old historical hashes and Linux `.so` files are
   not accepted as Darwin candidate provenance.
3. Pin/hash AIR runtime, fallback tools if permitted, ICD and non-system dependency
   closure before and after execution. Require actual function-pointer `dladdr`
   attribution for ordinary translation, **sampler translation**, lowering and
   Vulkan dispatch/pipeline creation, plus the dyld image inventory. Ordinary
   translation may be cached/unused; sampled variants need their own execution
   counter/image proof. ICD basename, environment or file presence is insufficient.
4. Preserve existing class/method/device/exit checks. Extend checks to render-pipeline
   creation, sampler creation, render encoder/draw, textures, pipeline objects and
   resources used by the measurement. A known installed image may coexist under
   original classes; none may own candidate operation implementations/resources.
   Unknown/duplicate class warnings or wrong IMP ownership stop the run.
5. **Owned-cache routing is currently blocked.** Release `nvmtl_conf_knobs` strips
   `NVMTL_*`, `NVK_*`, `NAK_*`, `NVRM_*` before reading production configuration.
   `--isolated-cache` sets `NVMTL_AIRCACHE`, which is stripped. AIR/SPIR-V may then
   write/trim production caches. `NVMTL_ICD_LIB` is stripped too. Do not claim either
   override worked or launch a cold test with them as the only control.
6. Required bounded preparation: in the copied namespaced source only, route AIR
   and its sibling SPIR-V/reflection/index caches to an explicit owned run root;
   reject a missing/unwritable/escaping root, prohibit production fallback and
   report canonical effective paths. Preserve production environment-clearing
   policy and all shader/cache semantics. Handle installed-bundle autoload without
   resetting the owned route. Set Mesa cache per child using `MESA_SHADER_CACHE_DIR`
   (not stripped by this constructor), verify effective behavior and report any
   warning/unavailable evidence. Do not clear system caches. Until reviewed routing
   exists, even otherwise valid correctness commands below remain **NOT READY**
   under this no-production-cache-write plan.

The current binding helper accepts `binding_translator_verified: unused` and
zero ordinary calls on a cached shader. That is legitimate scoped correctness,
not proof the new compilation branch executed. Release logging is suppressed/
rate-limited; counting log messages is not a reliable sampler miss/hit metric.

## Proposed execution sequence after gates and user approval

**A. One process, minimal initialization.** Build the existing standalone helper
with the pinned SDK, preserving strict warnings:

```sh
xcrun clang -arch x86_64 -fobjc-arc -O1 -Wall -Wextra -Werror \
  "$GA102_SOURCE/tools/ga102_isolated_plugin_probe.m" \
  -framework Foundation -framework Metal -framework IOKit \
  -o "$GA102_OUT/initialize-probe"
```

Use the runner's `run_owned` process-group deadline to invoke, with
`GA102_PLUGIN_NAMESPACE=NVMTLGA102_`, the argument array
`[GA102_OUT/initialize-probe, GA102_OUT/plugin/NVMTLDriver, --initialize-only]`,
45 seconds maximum, private output. This is a proposed use of an existing Python
function, not a new CLI flag. Require explicit device/class/method/single-image
checks. It does not load/verify the translator or prove GPU pixels. Stop and review
its inventory before compiling/submitting shaders; no in-process unload/reload.

**B. One compute smoke, then one 16×16 render smoke per arm.** After all gates close,
these are existing exact runner invocations (not executed in this preparation):

```sh
python3 "$GA102_SOURCE/tools/ga102_run_metal.py" ga102_metal_smoketest \
  --plugin "$GA102_OUT/plugin/NVMTLDriver" --namespaced-plugin --repeat 1 \
  --result-json "$GA102_OUT/compute.json"
python3 "$GA102_SOURCE/tools/ga102_run_metal.py" ga102_metal_render_smoketest \
  --plugin "$GA102_OUT/plugin/NVMTLDriver" --namespaced-plugin --repeat 1 \
  --result-json "$GA102_OUT/render.json"
```

Expected compute `[2,4,6,8]`, four elements; render center pixel and tolerance as
specified above. Require all independent provenance markers, unchanged hashes,
command completion and no new GPU/ICD failure. A runner `PASS` without the added
ICD/sampler/cache gates is insufficient for this experiment.

**C. Bounded runtime-sampler graphics experiment: not yet executable.** The existing
composite and compute cache probes cannot provide this phase. Required owned probe:
full-screen triangle to 32×32 RGBA8 private offscreen target, no drawable/IOSurface
initially; fragment `texture2d<float> [[texture(0)]]` and a **bound sampler at Metal
index 3**, sampling an 8×8 gradient at pixel coordinates `(2.25,3.75)`. Input pixel
`(x,y)` is RGBA `[32*x,32*y,16*(x+y),255]`. Two explicit pixel-coordinate sampler
states: nearest and linear, clamp-to-edge, no mip/compare/aniso, same fixed LOD
clamps. Hold source, textures, descriptors, constants and all other inputs identical
across cold/reuse and baseline/candidate. Preserve input/AIR/metallib/state hashes.
For the core translation/NVK comparison, prepare one owned metallib and feed those
exact bytes through `newLibraryWithData` in both arms; retain an owned source hash
and compiler provenance. If the Apple frontend cannot provide reusable library
data safely, stop that comparison. Time `newLibraryWithSource` separately as an
end-to-end frontend experiment; do not mix it into identical-AIR compiler results.
The reviewed harness must provide the extraction/loading steps and exact command;
no such metallib-extraction CLI is claimed by this document.

Software oracle before hardware: nearest expected `[64,96,80,255]`; bilinear
expected `[56,104,80,255]`, derived with texel-center offset 0.5. GPU readback must
check all 1024 pixels, tolerance at most 2 per channel; nearest/linear must differ.
Validate the oracle/coordinate convention against the emitted program before
execution; a disagreement blocks the workload, not a relaxed expected result.

Within each fresh child: create one library/functions; record initial render PSO
creation. Bind nearest and draw/readback (first variant miss), bind nearest again
with the same PSO (local hit), bind linear (new miss), linear again (local hit),
then create an equivalent new PSO and repeat nearest/linear (device-cache reuse).
Require operation-specific counters proving these categories and GPU correctness
for **every draw**. A cleared/unavailable global key, refusal or key mismatch is
reported explicitly, not silently categorized as a hit.

Instrumentation must time separate spans using one monotonic clock: library/AIR
extraction, ordinary/FC/sampler ABI compilation, reflection if available, address
lowering, public render PSO creation, each `vkCreateGraphicsPipelines`, sampler
lookup/miss construction and draw encoding, submission-to-completion, readback.
Record entry/exit, count, return status, stage and workload ID outside hot-path I/O.
Do not double-count nested spans as additive totals. Public PSO time includes
other setup; first draw encoding can include sampler compilation. Record GPU
start/end only when valid; missing timestamps are NOT VERIFIED, not zero time.
Snapshot per-PSO and device-cache hit/miss/build counters around each operation;
verify actual sampler ABI calls and Vulkan creation call counts. Preserve locks,
ordering, caches and allocation/lifetime semantics. No production logging switch
or configuration write to obtain timings.

**D. Identical owned-cold and persistent-reuse A/B.** Start with one diagnostic
paired trial; stop for review of attribution/results. Then at most ten paired
trials, alternate baseline/candidate order. Each arm/trial owns a new cache root
with `air/`, sibling `spvcache/`, and separate `mesa/`. Cold process starts empty;
reuse is a second fresh process with the **same** arm/trial root and identical
workload. Never share roots across arms or remove production caches. Same-process
local/device hits from C are separate from cross-process disk reuse. Do not change
function names or use `--volatile-smoke` in timed A/B, since it changes the input.

Call the condition *owned-cache cold*, not globally cold: Apple frontend, OS,
installed-driver/internal caches, GPU clocks and system scheduling remain. Cache
files/bytes prove persistence, not Mesa hit counts. If driver hit instrumentation
is unavailable, report that part NOT VERIFIED. Separate first-device/first-pipeline
initialization from later compilations. Ten cold samples cannot support a precise
tail claim: report sample count, nearest-rank p95, median, range, IQR, CV and paired
trial values without pooling distinct shaders/stages/cache categories.

**E. Larger representative correctness only after C/D pass.** Run existing
`ga102_metal_composite` through the same explicit namespaced runner, `--repeat 1`
initially, then up to three independent repetitions if stable, with new result
files. It tests private/IOSurface blended pixels and may autoload the installed
bundle. Recheck candidate object/IMP/ICD ownership after that autoload. Retain its
constexpr-sampler and sampled-pixel coverage limitations. Do not call its
encode-to-completion measurements runtime sampler compilation timings or desktop
FPS. Cross-process/events/windowed/full suite are not required in this first phase.

## Negative controls, stops and evidence

Run provenance-negative controls in Cloud mocks first: wrong plugin/translator
hash, missing marker, source mismatch, disallowed image, candidate-byte mutation,
unwritable/escaping cache path and missing counter must prevent acceptance/launch.
On Mac do not deliberately provoke GPU faults, invalid memory or long-running
shaders. An owned correct completed image with a deliberately wrong software
expected color must fail the result validator. Baseline/candidate ordinary and
sampler SPIR-V, where captured before lowering, must really validate and remain
byte-identical for this refactor; validate post-lowering modules separately and
record declared layout flags. No fake validator or private shader substitution.

Stop the entire sequence on build/ABI/hash/ownership mismatch, unknown backend,
missing independent marker/counter, cache isolation failure or required fallback,
shader refusal/validation failure, pixel mismatch, command-buffer error, missing
completion, outer deadline, OOM/device loss/GPU fault/reset, new desktop instability
or unexpected system/display operation. Preserve the first failure; no automatic
retry, forced recovery or continuation with a different installed stack. Existing
probes have 10–15 s GPU waits; the runner has 45 s execution and 60/90 s compilation
deadlines. Kill only the owned child process group on timeout. That cannot promise
to cancel already submitted GPU work; never reset the GPU/services to rescue it.

Expected private evidence: approved phase/harness revision; clean source/tree and
original/transformed hashes; toolchain/SDK/header/lock versions; build commands and
exit codes; final artifact/UUID/signature/dependency manifests before/after; actual
class/IMP/translator/sampler/lowering/ICD pointer image inventory; GPU identity;
cache effective paths and initial/final snapshots; AIR/metallib/SPIR-V hashes and
validator outputs; full operation timings/counters/statuses; every pixel verdict;
process deadlines, fault observations and raw trial samples. Observe only relevant
existing fault/status channels read-only; no broad desktop logging or captures.

Publish normalized evidence only: source and artifact hashes, workload/state
hashes, category counts, statistics, correctness/validation verdicts, gate failures
and scope. Keep paths, addresses, identities, configuration contents, raw system
logs and binaries private. Missing data remains missing. Report offscreen GPU
correctness and isolated CPU/GPU timings separately from desktop acceleration,
physical scanout, real FPS, sleep/wake or installed-driver stability.

## Approval boundary and next action

Await approval of the prepared runbook. The next useful Cloud task is the narrowly
specified harness/cache/provenance extension needed for C/D; publish and review
its exact source and invocation before hardware use. If that cannot safely prove
candidate sampler/ICD execution and owned cache routing, mark graphics timing
**BLOCKED** and return the reason. Never fall back to enumeration of the installed
stack, disable ownership checks, trust stripped environment overrides or relabel
old artifacts. No Mac action has been performed by preparing this document.
