# Null-Moth source integration audit

Credit: NullMoth Systems created the original driver. This work selectively
extends that driver and preserves its licensing and third-party notices.
Upstream: https://github.com/nullmoth/nvidia-macos-driver .

Direct Git fetch pins main to `1baebac4db587114019e833351e2d438276359d3`.
The GitHub releases API reports latest non-prerelease `v1.14.7`, published
2026-10-12 21:30:24 UTC, targeting `eb1acea2487bdd88b80d98045c4204a022439f48`.
Main contains three subsequent runtime commits; the tag and main are different
qualification targets. Release notes say 1.14.7 repairs app/installer behavior
while retaining the 1.14.6 runtime payload. No release was installed here.

Our comparison starts at `b1067da`, after the controlled v2/pool experiments.
Common ancestor is upstream `e404ab3` (1.11.0). Therefore this branch is missing
more than the latest maintenance changes. A blanket merge would overwrite local
translator, PM, cache and diagnostics work. LICENSE and NOTICE are byte-identical
between upstream main and our comparison branch; their terms remain in force.

## Relevant source classifications

| Area / upstream commits | Classification | Engineering disposition |
| --- | --- | --- |
| Completion monitors `4f48b3d` | Missing; now selectively integrated | Atomic once-only capacity release; queue/command-buffer class monitors for internal lazy state. Actual release-method oracle: baseline 0/200 progress while caller holds monitor, candidate 200/200, repeated concurrent releases signal once. |
| Viewport depth `3a5abdb` | Missing; now selectively integrated | Clamp Vulkan depths while preserving reversed depth and Metal NaN defaults. Extracted actual function: 64 pairs pass ASan/UBSan; original function fails the same oracle. |
| Page-off scanout reversion `732bd2a` | Already equivalent at patch sites | Our retained earlier logic matches the final reversion. Do not import the intervening unsafe scanout-retention change. |
| Existing 1.11 driver / event scheduler | Already inherited at common ancestor | This is ancestry evidence, not qualification of later synchronization fixes. |
| Read-only NVK handle `e4d8ca8`; permission fallback `9634d91` | Missing; latter conflicts with local bridge context | Our NVK patch still opens placeholder handles O_RDWR. Port the read-only change and owned EOF fallback together; run real-descriptor/sandbox controls before browser qualification. Never change sandbox/security preferences to pass. |
| Linked sampler variants `40e3a60`; raw-cursor helper ordering `ceea01d` | Missing; clean patch applicability | Worth independent shader/linked-stage semantic controls. Do not confuse existing gradient qualification with linked RenderBox or CoreImage coverage; retain PreparedNativeAir and native regression repairs. |
| Sample-position fallback `a98c546`; internal-copy MSAA `c9c9377` | Missing; clean patch applicability | Default positions currently require programmable-position support. Upstream avoids empty/aborted draws. Port with default-position and MSAA readback controls, preserving our current Vulkan lifetime fixes. |
| Texture swizzle `721b86f`; safe staging/twin lifetime `77e4c98` | Missing/conflicting source context | User-space compatibility priority. Port synchronization/lifetime changes before optimizing upload throughput. Our profile forbids installed extraction fallbacks; preserve that gate. |
| Queued IOSurface publication, alias backing and pooled-client detach `bee05d1` | Missing/conflicting; coordinated plugin + NVK change | Highest desktop correctness target: upstream reproduces successful clear followed by stale/black read, including partial-update corruption. Needs shared/private surface, alias, CPU seed, cross-queue and weak lifetime controls plus an isolated compatible source NVK build. |
| Pending surface cleanup / wake retry `79e1c2f` | Missing/conflicting kernel paths | Resource-owner cleanup is relevant; wake retries cannot be validated with the offscreen harness. Port into an independent kernel candidate, retain private backups/recovery and supervised hardware boundary before installation. |
| Streaming surface import / boot timing / monitor flags `1baebac` | Missing/conflicting; mixed user/kernel change | Separate the byte-preserving copy helper from display policy. Upstream reports large WC-copy savings on its RTX 5060 fixture, not desktop FPS or GA102 evidence. Validate alignment/tails and actual GA102 mapping before adopting it. |
| ACPI gating `fb98e8d`, copy-path frame freshness `c2af33d`, high-refresh boot `7c7b2a4` | Missing/conflicting or clean kernel patches | Keep source candidates separate from loaded components; no live changes or display-mode tests in this session. Reconcile with our PM diagnostics rather than replacing them. |
| AMD/Intel/NPU drivers, laptop brightness and unrelated installer policy | Not applicable to current isolated GA102 qualification | Do not import broad platform/boot changes solely because they accompany a newer release. |

The [machine-readable audit](evidence/ga102-upstream-audit.json) retains all
production-path file diff counts and exact selected commit pins. Patch
applicability alone is not semantic equivalence: combined/conflicting changes
are explicitly left for manual review. The two selected fixes apply exactly;
all remaining entries are review findings, not a claim of complete integration.

## Performance interpretation and highest-value next work

The separate [v2 result report](GA102-V2-LOCAL-RESULTS.md) establishes a 4.76–6.24 ms
initial pipeline preparation saving from smaller first-pool allocation. It does
not establish desktop responsiveness. Warm sampler ABI savings are small; cold
linear ABI regressions remain in both orders. Reversed order changes absolute
specialized creation and binding costs, demonstrating order sensitivity; it does
not uniquely explain the earlier v1 cold-nearest regression or remove it.

For real desktop correctness, prioritize queued IOSurface publication and safe
surface upload lifetime next. For further measured process-start performance,
dummy resource allocation remains approximately 9 ms after the pool fix. A
representative surface/frame-time fixture should quantify how often these paths
run. Changes to installed components, sleep/wake or display configuration remain
outside this isolated source qualification.

## Completed selected-backport qualification

Published source `e29e0df` has the identical complete Git tree as locally tested
`a4471b1`. Both inherit the measured pool and prepared-AIR changes. The integration
is independently attributable to NullMoth Systems commits `4f48b3d` and `3a5abdb`;
no upstream kernel or installer change is included.

The rebuilt translator/plugin passes normal v2 qualification (eight processes,
48 exact-pixel draws), using the same candidate artifact in both arms. This is
qualification, not an additional timing comparison. Two supplemental cold/reuse
processes then pass while the caller holds both command-buffer and queue monitors
through render and readback completion. Two further processes pass with the same
held monitors plus out-of-range nearest depths and NaN linear depths. All 24
supplemental draws match the pixel oracle, shader capture passes real Vulkan 1.2
validation, actual image/namespace/dependency/cache gates pass, and measured
Vulkan error counts remain zero.

The first supplemental probe compile failed because its queue variable was out
of scope. That output remains private; using `command.commandQueue` repaired the
probe before launch. No deliberately deadlocking baseline GPU workload ran.

NEXT-STEPS: run `python3 tools/ga102_completion_lock_test.py`, then
`python3 tools/ga102_viewport_depth_test.py --vulkan-headers "$GA102_HEADERS/include"`.
Prioritize an independently pinned queued-surface publication fixture and safe
upload lifetime port before WC-copy optimization. Separately exercise physical
pool growth beyond 256 simultaneous sets. Keep all installed components intact.
