# Sequoia ENDGAME comparison preparation — 13 October 2026

The ENDGAME candidate remains installed and mapped in WindowServer. **No desktop
performance improvement has been established.** Official NullMoth 1.15.0 is now
pinned, its binary archive authenticated against GitHub's asset digest, and its
source compared with the installed candidate. No driver, kernel collection, EFI,
display, security setting or session restart was changed in this investigation.
Owner approval is required before the next installation or reboot.

## Preservation and current provenance

Diagnostics starting point: `9dd7c65e9f9cbb77f942adb4d7ddd181779cddfc`.
Installed source: `92fbfd7ced2f752d105f95242da854c9bbe7d46f`.
Actual host: Darwin x86_64, Sequoia 15.8.1 / 24H32. `sudo -n id -u` returns 0.
Both unpublished Swift experiments remain unchanged and have separate file copies
and a binary Git patch. Existing branches, build directories, rollback jobs and
all prior failed/unqualified benchmark evidence remain intact.

A fresh exact installed-userland archive was saved privately and copied to the
reconnected tested Recovery USB; both copies hash to
`695fe45200e0742361c7e806ad26944531f323e3f075fac7ca4b4d253ab1db4d`.
Raw process inspection, installation metadata, configurations, images and binaries
stay outside Git, under the private local comparison directory.

Fresh ordinary Metal dispatch passes 17/34/51/68. `lsof` inode records and independent
privileged WindowServer `sample` mapped UUIDs match these installed files:

| Component | SHA-256 | Mapped UUID |
|---|---|---|
| NVMTL | c845d7532b842de12b436035cdcb64e4874894e70aef0a4e6182b18854b33b7b | 9276DA1F-436C-3EC4-A881-7E54E44F0356 |
| Translator | 60e239a170b56d21f2a1ddb6f74ff1f341308f42a7632c4ed04b0d1840b2284c | 2B2B6E56-1A23-3AA7-9557-3C31BA8D3501 |
| Source NVK | ec8849463c61d559a29320fd2d340d7621b36550ed0ecd4736d9268adfe2b08b | 52210F7A-4A40-350B-A222-8CA14E15F34B |

All **34 entries in the retained dependency manifest** match (the previous report
counted 31 retained files; this check uses the complete current job manifest).
`kmutil showloaded` independently reports the original kernel/display UUIDs:
NVRM A3EEEB46-9C19-3968-A257-144E56568245;
NVAccel 772BE080-9CA2-3866-A26D-5E7FCAD55A5C;
NVRMFB CC151F75-1305-3928-AA0F-B8BC96EF30A3;
NVRMAGDC 3713FCA7-6969-327F-A9C1-C0E5F3C90736.
The archived original bundle/NVK and installed candidate match their package
manifests. The current dispatch also emitted cache-directory permission and
copy-engine fallback warnings; successful dispatch does not erase those warnings.
They do not establish a new regression without matched prior controls.

## Official release and exact source comparison

Official [release v1.15.0](https://github.com/nullmoth/nvidia-macos-driver/releases/tag/v1.15.0)
was published at 2026-10-13 09:26:10 UTC, commit
`56bc4f9ae3105df052eefd3ea094c782e56853c3`. Downloaded driver archive:
371,718,424 bytes, SHA-256
`6101cf8c37e4a500059ea8ce4d9f131ea107e35ccbeafcbb124d78a97e37e3ec`.
The release identifies itself as the last Sequoia release. Its installer selects
`Library/NullMoth/kexts/15/NVAccel.kext` on this OS. The package also contains Tahoe
files; those are not Sequoia installation targets.

The offline source worktree is detached at the exact release commit. No upstream
merge or cherry-pick was applied. The machine-readable evidence records **all 64
changed production component files**, before/after Git blob IDs, plus the **22
additional HighDelay component differences**. Reproduce the complete content diff:

```sh
git diff 92fbfd7ced2f752d105f95242da854c9bbe7d46f 56bc4f9ae3105df052eefd3ea094c782e56853c3 -- plugin nvk translator kexts
git diff 56bc4f9ae3105df052eefd3ea094c782e56853c3 407e128651e60ea16e24bec31cd974e87c5d9bc6 -- plugin nvk translator kexts
```

Source equivalence below concerns the stated paths, not equality of entire stacks.

| Fix / path | ENDGAME status versus official 1.15.0 | Practical significance |
|---|---|---|
| Queued IOSurface publication, backing aliases and pooled client detach (`bee05d1`, local `7c85310`) | Core path already ported and physically qualified | Do not count the release's stale-content fix as entirely new to us. |
| Completion monitor/queue locking (`4f48b3d`), viewport depth (`3a5abdb`) | Already ported | Unity lock fix is not a missing ENDGAME fix. |
| Surface writer-map locking (`b25058b`) | Missing explicit recursive class lock in registration | Completion thread shares the map; retain as a correctness fix, not an assumed frame-rate improvement. |
| Completed-buffer overwrite set cleanup | Missing `_surfOverwrites` release in finishExecution | Retained completed buffers can extend surface/VRAM lifetime. |
| Embedded argument textures | Candidate still directly calls SurfaceIn; official uses `nvmtl_surface_in_for_cb` | The selected surface port was incomplete for this binding path; queued overwrite protection must cover embedded textures too. |
| Streaming surface import (`1baebac`) | Missing; candidate uses memcpy | Official uses SSE4.1 streaming loads for aligned sources >=4096 bytes, fences, unaligned stores and memcpy tails; pitched rows retain per-row handling. Relevant to observed WindowServer memmove, but 35x is not GA102 desktop evidence. |
| Full replaceRegion overwrite import avoidance | Missing narrowly gated full 2D RGBA/BGRA overwrite fast path | Can avoid importing contents about to be overwritten; partial regions, views and unsupported formats retain import. |
| Bounded per-thread upload staging (`77e4c98`) | Present, with additional local uncertain-completion quarantine | Official still waits synchronously. Do not import the superseded unsafe deferred-wait staging experiment. |
| Browser device handles (`e4d8ca8`, `9634d91`) | Missing O_RDONLY handles and owned EOF-pipe fallback | Fixes a device-access gate; not proof that Safari's earlier driver mmap denial is fixed. |
| Browser memory query (`df1d24a`, `b25058b`) | Missing NVK-only sysconf import rebinding/host_info fallback, with table bounds checks | Addresses Chromium sandbox memory-size denial after loading; no sandbox weakening. |
| ANGLE NVIDIA Metal (`6a233a0`) | Missing default enablement; official retains NVMTL_ANGLE_METAL=0 opt-out | Chromium/Electron path, not a generic Safari/Firefox cure. Release still lists possible Chromium corruption and sandboxed software video decode. |
| Linked sampler stages (`40e3a60`), helper order (`ceea01d`) | Missing | RenderBox/CoreImage/Settings compatibility; preserve local prepared-AIR cache if selectively ported later. |
| Sampler-specialized threadgroup lengths (`2009ced`, PR180) | Already equivalent: local prepared path calls apply_tg in both branches | Do not overwrite our memoization or claim this source fix newly helps us. Upstream adds direct regression coverage. |
| Stage-output type remapping (`4b0a8c7`) | Missing | Stage-output correctness after buffer remap; source candidate with its upstream fixture. |
| Texture swizzles/storage twins/AIR argument layout (`721b86f`, `bb1fddf`, `77e4c98`) | Missing coordinated feature paths | Icon gray/alpha and HDR/compute outputs; not proof of fixing screenshot blur. |
| Default sample positions (`a98c546`), internal MSAA copy (`c9c9377`), null descriptors | Missing | Avoid empty/aborted draws or crashes; zeros from a null descriptor remain a correctness defect when a real resource was expected. |
| Kernel freshness, pending cleanup, WC mapping, boot/display policy (`c2af33d`, `79e1c2f`, `1baebac` and later release commits) | Installed original kernel lacks later versions | Full official comparison changes these layers. Userland-only performance cannot qualify these fixes. |
| Small BAR unmap (`4406276`), display-power revert (`531faec`), retained contiguity diagnostics / `-nvrmsmallbar` | Official kernel additions/changes; not installed | No new boot argument, wake experiment, display change or kernel rebuild was undertaken. Big-page fallback `66469f7` was reverted by `c3cba3a`; do not port the reverted version. |

ENDGAME-only changes absent from official include 8 MiB host blocks (official32),
full hole coalescing, initial256 descriptor sets with unchanged total budget,
thread-safe device queue/config access, bounded address-module/AIR cache retention,
prepared sampler translation, volatile-load ordering protections and uncertain
upload lifetime handling. Replacing our source wholesale would discard these.
The isolated startup savings and fragmentation gains remain real; their desktop
benefit and the growth p95 trade-off remain unproven.

## HighDelay extras: optional source only

Pinned [HighDelay fork](https://github.com/HighDelay/nvidia-macos-driver) HEAD
`407e128651e60ea16e24bec31cd974e87c5d9bc6`; merge `63bba13` incorporates official1.15.
Additional source candidates include robustBufferAccess/imageCubeArray (`49fec32`),
fixed-center 1x versus programmable MSAA (`fb85cc5`), vector fast_ldexp (`f6e7ea8`),
loop-exit/SSA repairs (`9c78237`), cube arrays/gradient samples/image selects/fcmp
(`c6976b8`) and glyph-related translator changes. These require application-specific
pixel/validator controls, especially bounds handling's performance cost. No fork
binary was installed or credited with GA102 improvement.

`5efad31` offers **opt-in** schedule-after-surface-write behavior, default off.
It suppresses MarkScheduled during normal execution and calls it at entry to
FinishExecution; the latter precedes the cleanup loop finishing residual inflight
parts. Normal successful parts publish earlier in execution, but error/residual
paths and ordering need proof. Do not treat the commit title as an unconditional
cross-process correctness guarantee. Tahoe signing/staging and accelerator metadata
fallback are packaging changes, not substitutes for missing authentic kernel
archives. Tahoe framebuffer personalities are excluded from this Sequoia plan.
LICENSE and NOTICE match between ENDGAME and official; preserve NullMoth and
contributor attribution in any subsequent selected source port.

## Recovery and installation scope

The tested independent Recovery USB was initially disconnected, then reconnected
by the owner. All **seven** recovery-manifest files hash-check with zero changes,
including original stack/manifest and EFI backups. The manifest retains the owner's
successful current-Data access confirmation. The earlier actual in-OS userland
rollback restored original binaries and passed Metal dispatch. The generated
Recovery restore script passes shell syntax checking; it has not itself been run
in Recovery. No extra recovery reboot was requested or performed.

Important scope boundary: that script restores **only the two ENDGAME user-space
targets**. It is not a complete rollback executor for an official kernel-stack
upgrade. The full original archive contains kernel collections/kexts/configs and
EFI, but availability is not an executed full restoration test. Before the official
full-stack arm, prepare and verify an offline restore sequence for exact changed
kexts, cached OS15 accelerator, auxiliary collections and other installed package
files against the current Data volume. Do not use the old failed framebuffer
candidate or assume a live KC restore can bypass restricted-file protection.

Official NVMTL/translator/NVK hashes and UUIDs are recorded in the JSON. Official
NVRM, OS15 NVAccel and NVRMFB differ; NVRMAGDC is byte-identical. NVK depends on system
zlib1.2.12, IOKit, libc++ and libSystem. Translator's build-path LC_ID_DYLIB is its
own install name, not an external runtime dependency. The extracted NVMTL bundle
passes strict codesign verification. Four archive links were recorded without
following them; two Vulkan links target canonical installed paths. Initial safe
extraction rejected these absolute links; regular-file extraction then completed.
An unprivileged cached-accelerator inventory read was denied and repeated with
sudo -n. Both tooling failures remain privately recorded.

The official installer is **not a two-file switch**: it replaces kexts, caches OS
variants, replaces shared runtime/allowlist/firmware components and builds/publishes
an auxiliary collection. Its operations must be inventoried/backed up before owner
approval. Its legacy BASELINE-IDENTITY scope/qualification text is not evidence of
physical GA102 qualification. No installer was executed, and no new kernel build
was launched. A userland-only official arm would be labelled **1.15 hybrid on
original kernel**, separately from the official full stack. Compatibility must be
qualified rather than assumed. A hybrid is optional follow-up attribution, not a
replacement for the requested official arm.

## Controlled three-arm protocol

Freeze source/binaries, workload executable, browser versions, Sequoia build,
3440x1440/60Hz mode, power/display settings, allowlist and a recorded configuration
policy. Stock release configs must be diffed privately with current custom config;
retain required GA102 settings and label every deliberate deviation. Never silently
carry unsupported candidate settings into official1.15. No OS/browser update or
compilation during measurements. Record background load without terminating owned
applications or services. Persist results outside Git, with unique directories;
never overwrite a failed result.

Arms:
A = current ENDGAME userland + original kernel;
B = exact original userland + same original kernel (not a rebuild);
C = authenticated official1.15 complete OS15 production stack with declared config.
Collect A first, then obtain approval for B rollback/reboot, then separate approval
for the fully recoverable C install/reboot. If a result requires further attribution,
request a second matched A/B block; do not infer driver causality from one boot each.
Each restart must be owner-authorized. Keep a cold first-run series and a warmed
steady series separate; no cache deletion or forced cold state. Between binaries,
cache keys necessarily differ; record this confound.

1. After every boot, prove ordinary-process and WindowServer mapped UUIDs/inodes,
   kernel UUIDs and all expected dependencies. A successful install message is
   insufficient. Capture warnings and missing expected images before graphics tests.
2. Measure reboot-to-login-window, submit-login-to-usable-desktop and boot-to-desktop
   separately with owner stopwatch/video of the physical display and consistent
   login behavior. Add kernel boot time/login-agent event records as corroboration,
   not replacements for those intervals. Fixed startup recording must be staged
   before an approved reboot; delayed agent execution is not boot duration.
3. First run a command/pixel/cross-process IOSurface qualification. Preserve failures
   and stop to diagnose a command error, hang, wrong pixel or unmapped driver. Do
   not change SIP/sandbox/security to turn a failed browser into a pass.
4. Run the frozen **3,600-frame**,1920x1080,eight-draw workload at the same 640x360
   window, triple buffering and display cadence. First startup run and steady run
   after the same five-minute settling interval are separate results. Target three
   predeclared eligible steady repetitions per arm. A pacing failure is retained;
   diagnose it before further repetitions, not rerun until PASS. Keep missing IDs,
   all late pairs and both startup/steady intervals. If visibility is lost, mark
   NOT VERIFIED and preserve that run before a separately labelled replacement.
5. Use identical local WebGL2 texture/readback and CSS pages in Safari/Firefox.
   Add Chrome only if already present, using a declared identical version and an
   ordinary sandboxed profile; current harness accepts Safari/Firefox only. Distinguish
   context/setup failure, image-not-mapped, software renderer and wrong pixels.
   Preserve renderer, GPU process UUIDs, byte oracle and context-loss results.
   rAF latency is browser callback timing, not physical scanout.
6. For real launch response, use fixed Safari/Firefox and one Metal application,
   with owned local content: time cold-process launch request to first visible
   usable window and owned-content first draw separately, then warm repeat10times.
   Record existing process state and restored windows; do not quit unsaved user
   sessions to manufacture a cold launch. If cold launch cannot be controlled,
   report warm activation only. OS open-command return, page-navigation timestamps
   and GPU callback times must never be labelled application startup durations.
7. Repeat serial and overlapping cross-process IOSurface patterns, CPU lock/seed
   publication, held completed buffers and immediate caller texture release.
   Use known pixel oracles, not successful command completion alone. Photograph
   the same About This Mac/window composition immediately with its screenshot,
   matching wallpaper/window position; keep images private and compare RGB regions
   after alignment/exposure/color caveats. Existing TCC denial stays NOT VERIFIED.
8. Correlate WindowServer sampled copy/wait paths with long-run late events, and
   record visible corruption, crashes, hung channels and WindowServer PID changes
   during the same bounded sustained application interval per arm. No deliberate
   sleep/wake, display-mode change or unrelated stress workload.

Report per-run p50/p95/p99/max presentation, acquisition, submission/completion,
GPU times, startup/launch durations, >25ms and >50ms intervals, missing timestamps,
qualification/visibility, command errors and pixel results. Publish raw numeric
samples and median-of-run summaries; retain failed runs alongside qualified ones.
No pooling into a single favourable quantile or dismissal of cold-start failures.
A desktop upgrade recommendation requires matched improvement exceeding ordinary
run variability without application correctness/stability regressions. Three runs
are descriptive evidence, not a strong statistical guarantee.

## Existing measurements and attribution limits

| Result | Original | ENDGAME | Attribution |
|---|---:|---:|---|
| Short steady median run p95 ms |17.378341|17.436540|No useful gain;2 original versus3 candidate, not paired |
| Short steady median run p99 ms |17.480053|17.521460|No useful gain |
| Early post-login p95/p99 ms |No matched startup control|49.254940/50.467762|Candidate-observed failure; not proven candidate-specific |
| Sustained p50/p95/p99 ms |Not collected|16.682814/17.477272/32.884675|No original or official matched3600 control |
| Sustained late >25ms |Not collected|49/3587,1.37%|40 prompt-client pairs; compositor/display/publication lead, not proof |
| Safari/Firefox WebGL |Not collected|mmap denial / no context|Not proven newly introduced; official fix claims still need this machine |
| Boot/login |Not timed|Owner reports slower|Regression concern, unquantified |

The new sustained verdict independently replays retained numeric evidence:
command completion PASS, pacing FAIL, missing IDs0/1 preserved, physical scanout
NOT VERIFIED. It does not create a new physical measurement. The frozen Swift
probe compiles locally; its old window title says six seconds but its count/deadline
are3600/64seconds, exactly matching the prior retained source. Its exit0 only means
collection completed; the new verdict rejects that as a pacing pass.
120 standard-library tests pass, including four synthetic verdict-control tests;
those controls are not physical GPU results. No new translator/NVK build or broad
optimization campaign was undertaken.

Highest-value next action: matched original browser/startup/sustained control,
followed by recoverable official1.15 qualification. If source integration follows,
prioritize streaming surface copies and missing coordinated surface/browser fixes
while preserving our allocator/lifetime safeguards. HighDelay extras await specific
application evidence. Current recommendation remains experimental retention only;
there is no measured reason yet to prefer ENDGAME over the original.

## NEXT-STEPS

Read-only first command: `sudo -n id -u`.
After approving the A/B sequence, run the frozen workload using a fresh output:

```sh
xcrun swiftc -O tools/ga102_metal_sustained.swift -o "$COMPARISON_OUTPUT/sustained-probe"
"$COMPARISON_OUTPUT/sustained-probe" --render-size 1920x1080 --composite-layers 8 > "$COMPARISON_OUTPUT/run.log" 2>&1
# Preserve the full log; extract the single result JSON into a fresh result.json.
python3 -S tools/ga102_sustained_verdict.py "$COMPARISON_OUTPUT/result.json"
```

`COMPARISON_OUTPUT` must be a new private directory; prepare/compile once before
measurements, then reuse the identical hashed executable across all arms. Approval
for B rollback/reboot does not authorize C kernel/collection publication. Finish
C's full restore procedure and provide its exact change inventory for approval first.
