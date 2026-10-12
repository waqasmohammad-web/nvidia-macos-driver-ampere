# GA102 isolated graphics validation runbook

Status after portable harness preparation: **READY for Linux source/policy checks;
NEEDS MACOS VALIDATION for all Darwin compilation and GPU claims; BLOCKED for
meaningful performance conclusions until cold/reuse and sampler-path qualification
passes.** No Mac access, build or execution occurred. No hardware testing is being
requested by this checkpoint.

This supersedes the original runbook's missing-harness placeholders. Production
source pins remain baseline `8fd5960d0bda6bde25f435b8f05b2cd35c58f431` and candidate
`acb724185daba72de472e5954e69d3cec6221c51`. Use the **new published harness revision**
for both; record its full commit/tree SHA. These source pins have identical plugin
inputs and isolate translator reflection reuse. They do not independently measure
all historical plugin fixes or saturation versus its original implementation.

## Scope and entry conditions

An owner-present, stable Intel/x86_64 Sequoia RTX 3080 Ti (`10de:2208`) session is
required later. Existing installed kernel/RM/NVK remains unchanged and common to
both arms. Do not replace/install a plugin, dylib, kext or configuration; build
kernel collections; change EFI/OpenCore/SIP, display/security settings; create
windows/capture/present; reboot/logout/restart services or attempt recovery.
Namespaced user-space execution still shares the GPU/kernel and is not a hardware
sandbox. Stop if the desktop is already unstable or another build/test is running.

Read-only inventory comes first, only in a separately authorized Mac session:
`git status --short`, branch/HEAD/tree, `uname -m`, `sw_vers`, `xcrun --sdk macosx
--show-sdk-version`, `xcrun --find clang`, `xcrun --find swiftc`, `rustc --version`,
`cargo --version`, `rustup target list --installed`, `spirv-val --version`, and
relevant existing hardware inventory. Do not enumerate Metal devices as a
read-only shortcut: enumeration can initialize the graphics stack. Even the old
`--initialize-only` probe opens GPU channels and is an execution step.

Choose new absolute task-owned paths outside installed graphics directories.
Examples use `GA102_REPO` (production Git repo), `GA102_HARNESS` (clean checkout of
this harness revision), `GA102_SESSION` (new private session directory),
`GA102_HEADERS` (Vulkan-Headers checkout), `GA102_ICD` (retained installed NVK dylib)
and `GA102_AIR_RUNTIME` (existing compatible runtime directory). Record these
privately. Do not infer provenance from a directory name or a previously built
candidate. No build from `$HOME/nvmtl-build/bindless` is assumed.

## What changed and what is actually proven

`build/build_isolated_plugin.py --graphics-performance` applies
`build/ga102_perf_instrumentation.py` **only to copied, namespaced source**. Ordinary
builds retain their old behavior. No production plugin/translator source changes
or unconditional tracing were added. The copied profile retains x86_64/O1,
`NVMTL_RELEASE=1`, hidden C symbols and private Objective-C class/protocol/global
names. The actual release environment-clearing/config constructor stays identical.

That constructor intentionally removes inherited `NVMTL_*`, `NVK_*`, `NAK_*` and
`NVRM_*` tuning knobs before reading production configuration. The private profile
uses a separate `GA102_TEST_CACHE`/token contract, survives that clearing without
changing it, and replaces **only the copied AIR selector** with fail-closed owned
routing. The launcher creates a new mode-0700 root using `mkdtemp`, a mode-0600
64-character token marker, and mode-0700 `air/`, `spvcache/`, `mesa/`, `capture/`
leaves. C and Python reject wrong tokens, owners/modes, canonical-path mismatches
and symlinks. No cache root is adopted, cleared or deleted. Existing AIR index,
reflection, function-constant and SPIR-V paths derive from that owned selector.
Mesa's requested root is set before the copied Vulkan initialization; effective
child environment is checked. Mesa file counts still do not prove driver hits.

The copied profile embeds explicit translator/ICD paths. An absent translator
refuses compilation; failed direct ICD loading terminates rather than using the
Vulkan loader/installed fallback. Failed in-memory AIR extraction stops rather
than spawning installed `air-opt`. It does not bypass an isolation check to get a
passing result. Unknown loaded non-system libraries fail against an independently
reviewed closure manifest; known installed dependencies are explicit, not fallback.

Counters are inserted on the actual branches of `nvmtlBindSamplerPipeline`:
local lookup/hit/miss, device lookup/hit/miss and successful variant build.
`nvmtl_translate_samplers`' actual C ABI pointer is separately wrapped/timed.
Nearest/linear first draws require one local miss, device miss, sampler ABI call,
variant build and Vulkan creation each. Same-PSO repetitions require local hits
and zero ABI/Vulkan creations; equivalent-new-PSO draws require device hits and
zero ABI/Vulkan creations. A nil/unstable device key or disabled cache is a failed
claim, not a hit. Release logs are suppressed/rate-limited, so log counts are never
used as these metrics.

**READY evidence (Linux):** 79 standard-library GA102 Python tests pass. Portable
C cache/clock/atomic metrics/capture controls compile/run with ASan+UBSan, including
four workers × 1000 increments and fail-closed cache controls. Tests transform
actual production sites, preserve its release constructor/original input bytes,
reject moved/duplicate instrumentation sites, and reject missing/wrong branch,
pixel, image, dependency, timing and cold/reuse evidence. Real Linux sampler ABI
regressions re-pass SPIRV-Tools validation and baseline/candidate byte equality,
including capability and sampler-state negative controls. These do not compile
the new Metal source or prove Objective-C cache hits on a GPU.

**NEEDS MACOS VALIDATION:** all new Objective-C/Swift/Metal compilation, private
framework ABI compatibility, the two gradient outputs, actual selector/ICD
ownership, persistent-cache behavior and all timings. Preparation-proof files
contain no binary identity and cannot authorize execution.

## Dependencies and Cloud preparation

Cloud can review the transformer, generate namespaced sources, test policy/
acceptance negative controls, and validate the owned textual-AIR ABI fixtures.
It cannot generate/qualify Apple binaries. No full LLVM/Mesa/NVRM rebuild is needed.

```sh
python3 -S -m unittest discover -s tools -p 'test_ga102_*.py'
python3 build/build_isolated_plugin.py --prepare-only --graphics-performance \
  --source-root "$GA102_SOURCE" --output work/ga102-perf-prepared \
  --translator "$GA102_FUTURE_TRANSLATOR" --icd "$GA102_FUTURE_ICD" \
  --air-runtime "$GA102_FUTURE_AIR_RUNTIME"
```

`GA102_SOURCE` is a clean pinned worktree. The three future paths are explicit
absolute artifact/dependency paths; prepare-only does not assert that those files
exist. Output must be new. Inspect `preparation-proof.json` and generated source;
`binary_sha256=null` and `runtime_executed=false` are intentional. Never promote
this to compiled isolation proof. Mac-only CLI commands reject Linux before work.

Mac dependencies, to inventory without installing/modifying anything:

- Same Rust >=1.87/SDK/toolchain for both arms, existing `x86_64-apple-darwin` target,
  Apple linker and wrapper's locked crates (`metal2vulkan` with serde, serde_json,
  rspirv and transitives). Build `--lib`, not the source-built validator dev tests.
- Existing Apple clang/Swift/macOS SDK with Foundation/Metal/IOSurface/IOKit and
  normal CoreFoundation/Objective-C/libSystem dependencies. Apple `metal` and
  `metallib` tools must exist for the one common owned fixture; absent tools block
  preparation. No private compositor corpus is required or substituted.
- Vulkan-Headers include root; historical revision
  `c46850864f4661461b0f6cb9922c058ffea4915e`. Pin that or explicitly review/hash a
  compatible replacement. Checked-in plugin shader headers suffice; no generated
  kernel/shader binary rebuild. Plugin is one included translation unit.
- Explicit compatible `air-runtime/libLLVM.dylib` and complete non-system closure.
  Existing installed bundle runtime may be read/retained unchanged. Required C
  bitcode/IR-print APIs and existing optional unroll API behavior must match both
  arms. This performance profile forbids extraction fallback; do not rebuild a
  replacement LLVM just to continue.
- Explicit retained `/Library/GPUBundles/nvmtl/libvulkan_nouveau.dylib` and closure;
  installed NVAccel/RM/kernel interfaces and Apple Metal frontend support. Pin
  hashes, not just paths. Hash/read relevant production configuration privately;
  never edit it. Inherited DYLD overrides are refused. Disabled sampler/cache
  configuration may block the experiment; alternate vendor/Apple pipeline settings
  explicitly fail in the private profile rather than being disabled. Do not change
  installed config to pass.
- Real SPIRV-Tools, Python >=3.10 and measured memory/disk budget for one build job.
  No Linux `.so` or previous Mach-O hash counts as this candidate's build identity.

## Mac build-only steps: proposed, not executed

These require later authorization. Building is separate from submitting GPU work.
Record clean commits and exact source inputs first:

```sh
mkdir -m 700 "$GA102_SESSION"
git -C "$GA102_REPO" worktree add --detach "$GA102_SESSION/baseline-src" 8fd5960d0bda6bde25f435b8f05b2cd35c58f431
git -C "$GA102_REPO" worktree add --detach "$GA102_SESSION/candidate-src" acb724185daba72de472e5954e69d3cec6221c51
```

For each `GA102_ARM` (`baseline`, then `candidate`):

```sh
python3 "$GA102_HARNESS/tools/ga102_graphics_perf.py" prepare-translator \
  --source-root "$GA102_SESSION/$GA102_ARM-src" \
  --output "$GA102_SESSION/$GA102_ARM-translator" \
  --target-dir "$GA102_SESSION/cargo-target"
python3 "$GA102_HARNESS/build/build_isolated_plugin.py" --graphics-performance \
  --source-root "$GA102_SESSION/$GA102_ARM-src" \
  --output "$GA102_SESSION/$GA102_ARM-plugin" \
  --vulkan-headers "$GA102_HEADERS/include" \
  --translator "$GA102_SESSION/$GA102_ARM-translator/libnvmtl_translate.dylib" \
  --icd "$GA102_ICD" --air-runtime "$GA102_AIR_RUNTIME"
```

The translator helper records successful Cargo command/log, clean source commit/
tree and tracked translator hashes, Rust/SDK, release opt-level 3/codegen 16/
incremental off/one job, final dylib SHA256. It copies an arm only after successful
completion, before reusing the target directory. The private builder requires that
`translator-proof.json` matches its source and explicit dylib; records original
and transformed inputs, instrumentation identities and dependency hashes.
Failure/missing locked crates stops preparation; no stale artifact is copied.

Prepare a **single common owned metallib**, then use exactly those bytes in both
arms through `newLibraryWithData`, without timing differing frontend compilations:

```sh
python3 "$GA102_HARNESS/tools/ga102_graphics_perf.py" prepare-metallib \
  --output "$GA102_SESSION/fixture"
```

This executes `xcrun --sdk macosx metal -c runtime_sampler.metal` and `metallib`,
retains command/log/source/module hashes and SDK in `fixture-proof.json`. It does
not enumerate devices, submit GPU work or use a compositor shader. Inspect final
`lipo -archs`, `otool -L`/`-l`, `nm -gU`, signature status and SHA256 for both plugin
and translator. Require x86_64, the consumed `nvmtl_*` ABI, expected dependencies
and isolation exports. Hash after any separately reviewed private signing step;
no signing policy change. Source pin plus successful build/input provenance is
required; a binary hash alone does not prove its origin.

Review the complete resolved **non-system dependency closure** using read-only
`otool -L`/LC_RPATH inspection. Supply private `dependencies.json`:

```json
{"reviewed": true, "files": {"/canonical/resolved/non-system/image": "64-character-SHA256"}}
```

Use real paths/hashes for every closure image, including permitted installed
NVMTL image if Apple loading may introduce it, NVK, LLVM and any non-system Swift/
Apple compiler dependency. Baseline/candidate core artifact hashes are recorded
independently. Do not auto-accept an unexpected runtime image into this manifest;
stop and investigate first. System images under `/System/Library/`, `/usr/lib/`
and `/Library/Apple/System/Library/` are separately recognized. All manifested
files are rehashed before/after each child; unknown non-system dyld images fail.

## Execution gate and workload contract

**No current GPU claim is READY.** Before meaningful timings, the code above must
compile on Mac and the owner must review final source/build/dependency manifests
and isolate the child. Do not request physical testing merely because portable
mocks pass. A later separately authorized execution uses the exact runner below;
`--execute-reviewed` is a guard flag, not evidence of permission by itself.

```sh
python3 "$GA102_HARNESS/tools/ga102_graphics_perf.py" run \
  --baseline-plugin "$GA102_SESSION/baseline-plugin/NVMTLDriver" \
  --candidate-plugin "$GA102_SESSION/candidate-plugin/NVMTLDriver" \
  --baseline-commit 8fd5960d0bda6bde25f435b8f05b2cd35c58f431 \
  --candidate-commit acb724185daba72de472e5954e69d3cec6221c51 \
  --metallib "$GA102_SESSION/fixture/runtime_sampler.metallib" \
  --dependency-manifest "$GA102_SESSION/dependencies.json" \
  --output "$GA102_SESSION/graphics-qualification" --pairs 1 --execute-reviewed
```

This builds one common optimized Swift child and binding helper with independent
class/IMP/resource identity checks, no device enumeration. Each operation's
actual Rust, sampler, lowering and Vulkan function images must match selected
artifacts. LLVM attribution is required when AIR extraction executes; an unloaded
LLVM on a persistent hit is explicitly unused, not a fabricated executed path.
Exit namespace/ordinary/lowering markers and final hashes are independently
required. Candidate render/sampler/draw implementations and resource objects
cannot belong to installed classes. ICD fallback, extraction fallback or unknown
image fails. Original installed classes may coexist only under the established
namespace rules; duplicate/unknown driver warnings fail.

Fixture: full-screen triangle to a **private offscreen 32×32 RGBA8** target. An
8×8 shared gradient has RGBA `[32*x,32*y,16*(x+y),255]`. Fragment uses a runtime
sampler at Metal index **3**, samples pixel coordinates `(2.25,3.75)`, and binds
nearest or linear/clamp/no-mip/no-aniso samplers with fixed LOD clamps. No
constexpr sampler, IOSurface, drawable or display APIs. CPU oracle: nearest
`[64,96,80,255]`; bilinear (texel-center offset .5) `[56,104,80,255]`. Readback checks
**all 1024 pixels per draw**, maximum error 2/channel, and nearest/linear must
differ. A Mac disagreement stops qualification; do not loosen the oracle.

One child executes these exact categories:

1. Load common metallib/functions; create initial public render PSO.
2. Nearest first draw: local/device miss + sampler ABI + variant build + Vulkan
   pipeline creation. Nearest repeated draw: local hit, no recompile.
3. Linear first draw: separate miss/build; linear repeated draw: local hit.
4. Create equivalent new public PSO; nearest and linear draws require device-cache
   hits without ABI/variant builds/Vulkan creations for those draws. Creating the
   new public PSO itself is separately recorded as one Vulkan pipeline creation.
5. Complete/read back every draw with bounded waits and correct pixels.

The runner first performs a **qualification pair**, cold then reuse for each arm,
on new arm-owned roots with SPIR-V capture enabled outside timed ABI spans. Real
`spirv-val --target-env vulkan1.2 --scalar-block-layout` validates every captured
ordinary/sampler/lowered module. The two sampler modules must differ; baseline/
candidate multisets must be byte-identical for each cache condition. Captures
remain owned; they are not fake validators or replacement shader inputs.

Only after qualification passes does the runner perform requested timed pairs,
using **different new roots** and no capture I/O. Order alternates baseline/
candidate. Within each arm/trial, cold starts with empty AIR/SPIR-V/Mesa leaves;
reuse is a fresh second process using the same root and identical metallib/states.
Cold must show AIR miss/extraction and ordinary Rust/SPIR-V misses; persistent
reuse must show index/SPIR-V hits and zero new AIR extraction/ordinary compilation.
Both fresh processes still build their two runtime variants; same-process local/
device reuse is distinct from disk reuse. Unexpected behavior fails qualification.
No production cache is cleared, replaced or modified.

## Measurements, stops and evidence

Separate cumulative counts/ns are snapshotted around each operation:

| Span/event | Meaning and limit |
| --- | --- |
| AIR extraction | In-memory bitcode parsing/unroll/IR-print on an actual miss; memory/disk/index hits separately counted. No extraction duration invented on a hit. |
| Reflection ABI | Actual `nvmtl_reflect` / `_fc` call duration where invoked. Internal sampler reflection stays inside sampler ABI time; **not separately resolved**. |
| Ordinary Rust / sampler ABI | Actual selected exported functions, including their compilation work. Reuse zeros must have independent persisted-hit evidence. |
| Local/device lookup + sampler bind | Measured dictionary/device lookup plus explicit branch counts; total sampler-bind includes keys/locks/resource binding and nested work. Do not add overlapping spans. |
| Vulkan graphics creation | Exact `pvkCreateGraphicsPipelines` duration/count/status in the bridge, excluding the public wrapper's other setup. Same retained NVK in both arms. |
| Public PSO / draw / GPU / readback | Wall spans separate PSO creation, encoding, submit-to-completion and blit/readback. GPU timestamps only when present/ordered; missing timestamps remain unavailable. |

Start with `--pairs 1`; a pass is qualification/attribution, not statistical
performance evidence. Only a later approved, stable run may use up to `--pairs 10`
with a new output directory. Reports preserve each category's sample count,
median, nearest-rank p95, min/max/IQR/CV and raw paired samples. Do not pool shaders,
phases or hit/miss categories. Ten cold samples do not establish a reliable tail.
This is *owned-cache cold*, not globally cold: OS/Apple/internal driver caches,
GPU clocks and scheduling remain. Mesa persistence is not explicit NVK cache-hit
attribution. No desktop/FPS, physical scanout or wake/stability claim follows.

Stop the sequence on any source/build/ABI/hash/ownership mismatch, unknown image,
cache-route/permission/token failure, missing/incorrect branch counter, shader
refusal/validation failure, pixel mismatch, command error/timeout, OOM/device loss,
GPU fault/reset or new desktop instability. Available Vulkan error-severity
callbacks are independently counted before log rate limiting and invalidate
acceptance; unavailable callbacks do not prove absence of faults. No automatic retry, config adjustment,
forced recovery or acceptance through another installed stack. Preserve first
failure/logs. Owned process-group deadlines: 600 s Rust build, 90 s probe compile,
45 s execution, 10 s GPU completion and validator calls. Terminating the child
cannot guarantee cancellation of submitted GPU work; never reset services/GPU.

Expected evidence: pinned clean source/tree and build proofs; original/transformed
source and artifact hashes; tools/SDK/header/dependency manifest; actual class/IMP/
function-image/dyld inventory; effective owned cache root and cold/reuse snapshots;
common source/metallib and validated captured SPIR-V hashes; operation counters/
times/statuses; all pixel verdicts and missing GPU timestamps; failures and owner
health observations. Private logs retain paths, addresses/configuration/machine
identities and binaries. Publish only normalized hashes, counts, timings/verdicts
and limitations. Raw counters cannot alone assert a GPU succeeded; correct pixels
cannot alone prove candidate compilation executed.

Next useful step is review and Mac **build-only** qualification of this source in
a future separately authorized session. Physical testing is not requested now.
If actual Mac cold/reuse or device-cache behavior disagrees with the contract,
report precisely **BLOCKED** and investigate before any performance comparison.
