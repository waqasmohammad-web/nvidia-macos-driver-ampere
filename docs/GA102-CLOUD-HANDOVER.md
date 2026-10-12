# GA102 cloud development handover

Target: `dev/ga102-3080ti-diagnostics`. Select this branch explicitly when starting
cloud work; do not resume the default branch by accident. The handover commit
contains the finished source changes and the config-helper fix. Previous baseline:
`8c54ce4170feaf8f29285cd07b08b878c505d658`. Read the latest investigation checkpoint,
not the entire historical audit. No cloud task or perpetual background execution
has been started by preparing this handover.

## Current engineering checkpoint

The native macOS NVK build completed without interruption. Its config helper now
uses `pthread_once`, exact line-key matching and a per-thread borrowed-value ring;
NVRM callers share the helper while preserving environment precedence. Extracted
production-source tests reproduce original parser failures and TSan races; the
candidate passes. The rebuilt NVK dylib links. This is build/CPU evidence, not GPU
qualification or a sleep/wake fix. Installed components remain unchanged.

Published work also includes plugin queue initialization and cache accounting,
volatile memory semantics, malformed address-space rejection, conservative load
fusion and semantic regression repairs. See `docs/evidence/` and the latest
sections of `GA102-INVESTIGATION.md`. Two recovered Swift presentation experiments
remain unfinished and preserved locally; they are excluded from this cloud baseline.
Do not import private artifact directories to recover them.

Linux continuation on 2026-10-12 repaired the six stale native regressions and
then fixed the genuine generic callback table/store refusal. Full native suite:
2159 PASS / zero FAIL / zero ignored, with observable stores and validated negative
controls. Optimized release saturation compilation improves the largest owned
workload's median by 34.28% (100 samples per variant); actual desktop gains remain
unqualified. Extracted config tests pass Linux ASan+UBSan and TSan. Read the latest
investigation checkpoint and `evidence/ga102-callback-release.json` for current
results; the initial priorities below describe the original handover.

Latest Linux runtime audit confirms saturation optimization reaches cold native
NVMTL translations, while warm caches bypass it. Published sampler ABI reflection
reuse preserves byte-identical validated output on owned fixtures: 200 samples
per variant/workload show 1–3% fragment median savings and 9.98% in an unused-
sampler storage-write case. These are small compilation gains, not desktop
acceleration. Next meaningful qualification is synchronous NVK graphics pipeline
creation/cache reuse on verified candidate images and actual hardware. See the
latest investigation and `evidence/ga102-runtime-translation.json`.

The optional isolated graphics harness is now source-prepared with runtime-bound
nearest/linear samplers, token-verified owned cache routing and actual-path/ABI/
Vulkan counters. Portable qualification: 79 Python tests plus real C ASan+UBSan
controls and actual Linux sampler ABI/SPIR-V checks. Production source remains
unchanged. Apple compilation, GPU output, cold/reuse and hit claims NEED MACOS
VALIDATION; meaningful performance remains BLOCKED until qualification. Read
`GA102-HARDWARE-VALIDATION-RUNBOOK.md` and
`evidence/ga102-graphics-harness-preparation.json`. No physical testing requested.

## What can move

| Workflow | Hosted Linux suitability / dependencies |
| --- | --- |
| Python GA102 validators and mocked harness tests | Standard-library Python 3.10+; no GPU APIs are invoked by the selected unit suite. 72 tests pass locally with site packages disabled; Linux execution still needs an initial qualification run. |
| Native Rust translator parser, lowering, emitter and regression work | Rust >=1.87, C linker, locked Cargo dependencies and real `spirv-val` on PATH. Authored textual LLVM IR avoids AIR generation and `llvm-dis`. |
| Extracted NVK config helper tests | C11 compiler, pthreads and compiler sanitizer runtime. `--cc clang` supports Linux; TSan may be blocked by container address-space restrictions. Unsanitized results never count as race validation. |
| Wrapper load fusion / CPU SPIR-V tests | Rust plus C++/CMake tools; dev dependency `spirv-tools-sys` builds substantial native code. Optional after resource review. Two corpus tests are ignored and two private-fixture tests require explicit skips below. |
| PM protocol and source review | Review staged callback delegation, construct portable state/protocol tests. Current PM/queue/cache extraction scripts use `xcrun` or Foundation and need porting for Linux; no actual wake recovery can be validated there. |
| Mesa/NAK algorithms and patch review | Portable portions can be inspected/tested selectively. Full macOS patch is Darwin-specific; Linux NVK success would not qualify its NVRM bridge. |
| Plugin/Swift probes, isolated binding, Darwin NVK and kext builds | macOS, Xcode command-line tools / Apple SDKs and frameworks. AIR compilation needs Apple Metal tools. Hosted Linux cannot produce or validate equivalent Darwin binaries. |
| Acceleration, compositor/frame pacing, VRAM, synchronization, display power | Physical RTX 3080 Ti running the target macOS stack. Offscreen candidate tests need verified dependency/image hashes; kernel deployment and sleep/wake require later supervised sessions. |

No Apple SDK, installed-driver dump, private shader corpus, credentials or local
Mach-O binary needs uploading. Do not execute install/deploy, EFI, boot or driver
maintenance helpers as part of cloud setup.

## Minimal environment setup

Connect the repository through the cloud product's GitHub integration and select
the target branch. Use `.codex/cloud-setup.sh` as the manual setup command:
`bash .codex/cloud-setup.sh`. It fetches only native translator dependencies and
runs the lightweight Python suite; it does not compile LLVM, Mesa or the wrapper.
On a cached environment, run the same command as maintenance to refresh the
lockfile dependencies. If the setup checkout lacks this script, configure the
handover revision first/reset the cache rather than falling back to old setup.

Provide Python 3.10+, Rust >=1.87, `cc`, and real SPIRV-Tools CLI. For an Ubuntu
image lacking these tools, install `build-essential`, `spirv-tools` and optionally
`clang` during setup using the image's permitted package manager. Use the image's
Rust version selector or a pinned rustup toolchain if Rust is too old. Record
actual tool versions; existing local evidence used Rust 1.99.0 and SPIRV-Tools
v2026.4. Distro versions are not automatically equivalent or prequalified.
No Python packages, LLVM, Mesa, bindgen or Apple SDK are needed for the default path.

Set `CARGO_BUILD_JOBS=1` and `RUST_TEST_THREADS=1` in environment settings.
Setup shell exports do not persist into the agent phase. Cargo fetch needs
registry access in setup; agent-phase commands use `--offline --locked`. Keep
agent internet disabled unless a specific task needs it. Repository/GitHub write
access is supplied through the product integration, not committed tokens.
See [official cloud environment documentation](https://learn.chatgpt.com/docs/environments/cloud-environment).

Inspect the setup's cgroup-aware RAM and disk report before compiling. Treat
4 GiB RAM and 4 GiB free disk as an initial planning gate for a single native
Rust debug build, not a guaranteed fit. Below that, continue Python/source work.
Use one target directory, one build job, one test thread, no duplicate debug/release
builds. Measure consumption and stop starting new expensive work before the quota
is exhausted; never interrupt someone else's build. Wrapper native dependencies,
full LLVM/Clang/libclc and full Mesa are excluded from the default budget. Only
attempt them after measuring source/build/cache sizes and proving headroom; prefer
compatible distro toolchains and selected targets. Never assume the local full
LLVM/Mesa build fits a cloud container.

## First commands and continuation priorities

From the repository root, check `git branch --show-current` and `git log -1`.
Then:

```sh
python3 -S -m unittest discover -s tools -p 'test_ga102_*.py'
CARGO_BUILD_JOBS=1 cargo test --offline --locked --manifest-path translator/translator/Cargo.toml --lib parse -- --test-threads=1
CARGO_BUILD_JOBS=1 cargo test --offline --locked --manifest-path translator/translator/Cargo.toml --lib volatile -- --test-threads=1
CARGO_BUILD_JOBS=1 cargo test --offline --locked --manifest-path translator/translator/Cargo.toml --lib memcpy -- --test-threads=1
# Only after the small groups and resource checks:
CARGO_BUILD_JOBS=1 cargo test --offline --locked --manifest-path translator/translator/Cargo.toml --lib -- --test-threads=1
# Separate optional CPU sanitizer run; output stays outside Git:
python3 tools/ga102_nvk_config_test.py --cc clang --baseline --output "$(mktemp -d)/config-proof"
```

1. Qualify this minimal path on Linux. A missing validator, tool crash, zero
   selected tests or container sanitizer failure is a blocker, not PASS. Do not
   enable `external-validation-fixtures` without the three actual external files.
2. Triage the remaining native regressions individually: two buffer tests with
   stale typed-zero / no-helper assumptions, then four texture metadata/banding
   tests with old flat-binding assumptions versus default bindless tier 2.
   Latest full suite before subsequent repairs: 2146 pass, 11 fail, 1 ignored.
   Five failures were repaired in targeted groups; six are expected to remain,
   but a new full run is needed to establish the exact current baseline. Require
   real SPIR-V validation and semantic negative controls when changing assertions.
3. Improve config parser boundaries/borrowed-pointer tests and portable PM protocol
   coverage without implementing speculative hardware reset sequences.
4. Review resource/cache/synchronization hypotheses using owned synthetic shader
   fixtures. Optional wrapper command after fetching its locked dependencies:
   `cargo test --locked --manifest-path translator/wrapper/Cargo.toml --lib -- --test-threads=1 --skip ca_named_modules_validate --skip compositor_pixel_sampler_spirv_validates`.
   Document the two skips and ignored corpus coverage; never manufacture fixtures.
5. Prepare explicit source-NVK dependency selection and per-function image/hash
   provenance for the next local offscreen GPU session. Return source changes,
   normalized evidence and exact local validation commands, not a deployment.

Cloud tests cannot establish desktop improvement, boot safety or wake recovery.
Preserve a short NEXT-STEPS after each meaningful change; continue independent
portable work if hardware is unavailable. Completed cloud tasks need further
cloud tasks/follow-ups for continued execution; this handover does not schedule
an automatic restart or guarantee indefinite execution.
