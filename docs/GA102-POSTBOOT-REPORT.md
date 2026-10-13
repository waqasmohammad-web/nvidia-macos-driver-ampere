# GA102 post-reboot engineering report — 13 October 2026

The modified production driver is running in WindowServer and ordinary Metal
processes on the RTX 3080 Ti. **A measurable improvement in desktop graphics has
not been demonstrated.** Short steady presentation is comparable to the original,
but an early post-login run and a longer run contain substantial frame-time spikes.
Browser WebGL compatibility fails, and screenshot-versus-monitor correctness
remains unresolved. This is an integrated experimental candidate, not ENDGAME success.

Production source: `92fbfd7ced2f752d105f95242da854c9bbe7d46f`.
Installation checkpoint: `598c4b3b6af547ec72e1b61d2805e4fb0a9c7c7f`.
Actual environment: Darwin x86_64, macOS 15.8.1, RTX 3080 Ti / NVK GA102-A.
`sudo -n id -u` returns `0`; all new privileged operations used noninteractive sudo.
No further driver replacement, reboot, display or security change occurred.

## What is actually running

The existing `active-metal-images` executable completed ordinary production Metal
work with values 17/34/51/68. Its queue-method implementation belongs to the canonical
installed NVMTL image. Mapped Mach-O UUIDs and file hashes match the installation
evidence. Independent privileged `lsof` proves WindowServer maps the same current
file inodes; `vmmap` confirms the canonical image paths. A separate three-second
WindowServer `sample` also reports all three matching mapped UUIDs.

| Component | Mapped UUID | Installed SHA-256 |
|---|---|---|
| NVMTLDriver | `9276DA1F-436C-3EC4-A881-7E54E44F0356` | `c845d7532b842de12b436035cdcb64e4874894e70aef0a4e6182b18854b33b7b` |
| Translator | `2B2B6E56-1A23-3AA7-9557-3C31BA8D3501` | `60e239a170b56d21f2a1ddb6f74ff1f341308f42a7632c4ed04b0d1840b2284c` |
| Source NVK | `52210F7A-4A40-350B-A222-8CA14E15F34B` | `ec8849463c61d559a29320fd2d340d7621b36550ed0ecd4736d9268adfe2b08b` |

Canonical locations are the NVMTL bundle's `Contents/MacOS` directory and
`/Library/GPUBundles/nvmtl/libvulkan_nouveau.dylib`. There are no process-local
driver overrides or diagnostic class namespaces in these production checks.
This is mapped-image identity evidence, not a byte-for-byte process-memory dump.

All 31 retained dependency/configuration/firmware/collection file hashes match the
pre-installation baseline. Original loaded kernel/display UUIDs remain:

| Component | Original loaded UUID, unchanged |
|---|---|
| NVRM | `A3EEEB46-9C19-3968-A257-144E56568245` |
| NVAccel | `772BE080-9CA2-3866-A26D-5E7FCAD55A5C` |
| NVRMFB | `CC151F75-1305-3928-AA0F-B8BC96EF30A3` |
| NVRMAGDC | `3713FCA7-6969-327F-A9C1-C0E5F3C90736` |

The user-space replacement operates with the retained working kernel/display
stack. The missing authenticated Darwin RM/modeset archive producer still prevents
a fully rebuilt kernel stack; it did not prevent this integrated desktop deployment.

## Matched presentation workload

The documented workload is unchanged: 1920×1080 render target, eight alpha-blended
draws, 640×360 application window, existing 3440×1440/60 Hz display and 120 frames.
Steady distributions omit the first ten positive presentation observations, exactly
as before. Missing startup timestamps and every failed run remain retained.

| Run | Positive timestamps / commands | p50 ms | p95 ms | p99 ms | Maximum ms | Steady intervals >25 ms |
|---|---:|---:|---:|---:|---:|---:|
| Original 1 | 118 / 120 | 16.686 | 17.435 | 17.471 | 17.536 | 0 / 107 |
| Original 2, pacing FAIL | 119 / 120 | 16.729 | 17.322 | 17.489 | 32.673 | 1 / 108 |
| Candidate early post-login, pacing FAIL | 118 / 120 | 17.466 | 49.255 | 50.468 | 50.644 | 50 / 107 |
| Candidate steady 1, PASS | 118 / 120 | 16.625 | 17.437 | 17.521 | 17.631 | 0 / 107 |
| Candidate steady 2, PASS | 119 / 120 | 16.657 | 17.342 | 17.469 | 17.532 | 0 / 108 |
| Candidate steady 3, PASS | 119 / 120 | 16.713 | 17.507 | 17.706 | 17.721 | 0 / 108 |

All commands in these runs complete with zero command errors and timer skips.
Each failing repeated-run session stopped at its first failed pacing verdict;
unexecuted repeats are not counted. The original compiler-overlap failure remains
excluded from the matched baseline and retained separately.

The early candidate artifact was written approximately 246 seconds after kernel
boot, and its login validator started approximately 157 seconds after boot. These
include login interaction/scheduling and are **not boot/login duration measurements**.
The owner reports noticeably slower boot/login and a desktop that seemed fine once
loaded. There is no matched boot/login stopwatch or event baseline. The early trace
has client draw-interval p99 59.970 ms and maximum 91.717 ms, with GPU p50 0.318 ms.
Client scheduling delay contributes to that failure. Boot restoration, shader/cache
warming and other activity remain hypotheses; the cause is not proven.

Across per-run quantile medians, short steady presentation p95 is
17.378→17.437 ms and p99 17.480→17.521 ms. These differences provide no noticeable
improvement. GPU p50 is 0.319→0.314 ms, while client commit-to-completion p50 is
0.537→0.622 ms and p99 0.609→0.958 ms. The additional fractions of a millisecond
are measurable observations, not a demonstrated cause of the large presentation
spikes. Two original versus three candidate processes are not paired/randomised;
cache identity and boot/session activity differ. No statistical speedup is claimed.

## Sustained desktop composition

One owned production Metal window ran 3,600 frames at the same render size/load.
Only frame count, deadline and visibility-sampling bounds were extended in a private
source snapshot; hashes and transformation details are retained. No installed
source or display configuration changed. This is a 60-second target with a 64-second
deadline, not an hours-long soak or an original/candidate sustained A/B.

- 3,600/3,600 commands complete; zero command errors, timer skips or outstanding work.
- 3,598 positive timestamps; missing startup IDs 0 and 1 are preserved.
- All 62 sampled visibility/session/display states meet the eligibility conditions.
- Presentation p50/p95/p99: **16.683 / 17.477 / 32.885 ms**; maximum **50.517 ms**.
- **49/3,587 steady intervals exceed 25 ms (1.37%).** Submission success does not
  qualify this as a clean pacing pass.
- GPU p50/p95/p99: 0.319 / 0.364 / 0.382 ms; maximum 0.406 ms.
- Client commit-to-completion p50/p95/p99: 0.648 / 0.744 / 0.800 ms; maximum 1.530 ms.

For 40 of the 49 late intervals, both adjacent commands completed within 2 ms and
commits remained within 20 ms. Nine intervals fall into the client-delay/callback
timing category. Thus client startup delay cannot explain all sustained spikes.
Compositor/display scheduling or publication remains relevant, but CPU callbacks
and reported presentation timestamps do not identify a raw fence or physical scanout
event. The first such late interval is 33.641 ms despite 0.844 ms client completion
and 0.322 ms GPU work. Its reported presentation follows completion by 64.961 ms.

System display counter deltas over the surrounding test interval show zero failed,
dropped or refused submissions. Counters include other desktop activity; they are
not a complete per-process GPU-error census. No hang or WindowServer restart was
observed in this bounded session.

## Real applications and the upload bottleneck

Owned local pages ran in actual Safari and Firefox, with a reproducible WebGL2
texture/readback oracle and a separately labelled CSS composition mode. No sandbox,
browser security or driver setting was changed to force a pass.

| Application case | Actual outcome |
|---|---|
| Safari WebGL2 | Shader setup fails; renderer/vendor queries return null; zero qualified frames or pixels |
| Firefox WebGL2 | Context creation returns null; zero qualified frames or pixels |
| Safari CSS, 60 s | 3,593 intervals; callback p50/p95/p99 17/18/18 ms; 10 >25 ms; timing NOT VERIFIED because focus was lost for 2,723 samples |
| Firefox CSS, 30 s | 916 intervals; callback p50/p95/p99 33.340/50.320/50.940 ms; 691 >25 ms; visibility/focus eligibility passes |

CSS has no pixel oracle and browser callback timing is not physical presentation.
Safari's early CSS segment overlaps compilation of the separate sustained probe;
that trace is also unsuitable for a controlled performance comparison. No original
browser workload exists, so neither browser failure nor callback latency is proven
to be a new candidate regression. Browser UI can function while WebGL acceleration
does not. These checks do not qualify general application compatibility.

Safari's failure has a concrete first failing layer: its WebKit GPU process reports
**filesystem sandbox blocked `mmap()` of canonical `NVMTLDriver`**, and process
inspection confirms no candidate driver image mapped there. This precedes driver
shader execution. The candidate and original executables both retain restricted
file flags. The evidence does not justify clearing flags, changing SIP, disabling
the sandbox, inventing a replacement component or attributing the fault to SPIR-V.
The supported loader/sandbox integration must be understood, with an original
canonical-installation control before calling this a newly introduced regression.

A separate three-second WindowServer sample establishes desktop relevance for
surface uploads: of 2,244 main-thread samples, 467 occur beneath fragment texture
binding, 454 beneath `nvmtlSurfaceIn`, 396 in the image-write `memmove`, and 52 in
its synchronous fence-wait path. These are inclusive sampled stacks, not measured
per-frame import durations or percentages of overall CPU utilisation. There is no
original-driver profile or event-correlated causal proof.

The route `setFragmentTexture → nvmtlSurfaceIn → nvmtl_vk_image_write` therefore
connects the retained bulk-import concern to actual WindowServer work. The highest
value graphics investigation is whether cross-process backing/publication causes
redundant CPU imports and waits. Copy/wait suppression would require independently
proven seed, alias, lifetime and fence correctness. The allocator p95 trade-off and
large pitched-import regression remain; their contribution to this desktop trace
is not quantified. No new synthetic allocator tuning was performed.

## Correctness and screenshot capture

Post-login production checks pass eight serialized two-process IOSurface roundtrips
(262,144 checked bytes), sampled private/IOSurface 16/32-layer alpha composition,
and 12 distinct owned GPU frames with positive presentation timestamps. This is
scoped correctness, not broad application compatibility or proof of improved
desktop pixels relative to the original.

The fresh owned-window capture preflight remains false: zero capture attempts and
no privacy permission changes. GPU frame contents pass; captured contents and
physical scanout remain NOT VERIFIED.

Both owner-provided screenshots are 3440×1440, eight-bit RGBA PNGs. Native ImageIO
decoding finds alpha 255 in **all 4,953,600 pixels** in each. Their embedded ICC
profiles are byte-identical: 3,352 bytes, SHA-256
`69e7162df29b98c34e52296b835a4264ea6c2b6347ed2bf4c1f369df57b46627`.
The older profile was already ColorSync-validated. A changed embedded ICC profile
or transparent PNG alpha does not explain the difference. The apparent window
transparency is in captured RGB data. The new capture still shows background
content through About This Mac, but no synchronized candidate monitor photograph
exists. Capture flattening, composition/publication and display colour processing
remain separate possibilities. The discrepancy is not declared fixed.

## Failures, retained evidence and recommendation

The automatic root verifier collided with an existing output directory. Independent
privileged inode/path/sample-UUID verification resolved that tooling failure; its
original log is retained. An initial dependency-proof read required sudo, the
sample UUID parser initially confused a bundle path with a binary name, and Pillow
was unavailable. Those setup failures remain recorded; corrected inspection and
native ImageIO/standard-library PNG analysis supplied real results. One-time
validation jobs were cleaned up. No failing graphics workload was repeatedly run
unchanged to manufacture a pass.

116 standard-library regression tests pass, with no exclusions. Browser verdict
controls reject invalid clocks, software-renderer hardware claims and empty failure
samples; CSS never receives a GPU pixel-correctness pass. Raw logs, process inventory,
images, private configuration, recovery material and binaries remain outside Git.
Normalized hashes, distributions, missing IDs, late traces and numeric samples are
in [ga102-postboot-hardware.json](evidence/ga102-postboot-hardware.json).

**Recommendation:** retain provisionally only as an experimental development target
on this dedicated machine. There is no evidence-based desktop performance reason
to prefer it over the original, and no general upgrade recommendation. The candidate
remains installed as requested, with the working original and rollback retained.
Startup delay is owner-noticeable, sustained pacing remains imperfect, WebGL fails
in both tested browsers, and screenshot correctness is unresolved. These limitations
prevent calling the primary objective achieved.

## NEXT-STEPS

Exact read-only provenance command: `sudo -n lsof -p $(pgrep -x WindowServer) -Ffni`.
For subsequent engineering, prioritise supported WebKit driver loading and
event-correlated cross-process IOSurface import/publication. Establish original
browser and sustained/startup controls before attributing those regressions.
Preserve the current evidence and recovery route; do not restart microbenchmark
optimisation or change unrelated components to hide these failures.
