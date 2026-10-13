# Post-reboot status: validation failed; stop

The authorized reboot completed on Sequoia15.8.1/24H32. Original userland disk
hashes remain correct, but WindowServer maps none of the expected original images.
No NullMoth kext appears in kmutil showloaded; NVAccel/NVRMFB registry queries are
empty. Of34 retained entries,33 match and AuxiliaryKernelExtensions.kc changed
across reboot. No collection rebuild/replacement was issued by the agent; the cause
is unknown. Raw private expected/current collection hashes and inventory are retained.

The ordinary Metal probe has zero output. Parsing that empty output failed. A shell
sequence incorrectly continued into the original workload after the failed gate;
it immediately returned `FAIL: RTX 3080 Ti / queue unavailable`, with no timings.
That gating mistake is recorded; no subsequent graphics workload was executed.
Browser/application controls and the matched driver comparison are incomplete.

STOP boundary: no additional installed component repair, security/settings change
or reboot. Original userland and preserved ENDGAME archives remain intact. Do not
attribute this failed kernel activation to original versus ENDGAME performance.
The one reboot authorization is consumed. Investigate the unexpected collection
change before any separately authorized repair. See evidence/ga102-original-postboot-failure.json.

---

# Original userland rollback — post-reboot checkpoint

13 October 2026. The owner explicitly accepted the failed ENDGAME block as negative
evidence and authorized original-userland rollback despite that failure, plus one
reboot after successful checks. No candidate workload was rerun or modified.

The immediate checks pass: frozen workload/executable, failed raw/derived evidence
and both candidate archive copies retain their recorded hashes. Recovery USB is
mounted, all recovery-manifest checks pass, current Data identity matches its
restore script, and the owner-tested independent boot/access confirmation remains
retained. The Recovery script itself remains syntax-checked, not newly executed.
The rollback source hash cb75c8b372f6c289bdc04fdb15f13b3048e087a3aa98f4e8ba6e72e4e3c3196d
matches the previously tested installation checkpoint598c4b3.

A newly downloaded original1.11.0 archive matches the authenticated retained digest
6e568e28ee34c3b41f4dfda980fd8feb50fdd0a69cf6d0f6e54338873b8ec2e7.
All15 regular release files in the two rollback targets match the saved originals.

The existing rollback procedure completed successfully, replacing only
`NVMTLDriver.bundle` and `nvmtl/libvulkan_nouveau.dylib` under GPUBundles.
The former includes the original translator. All34 retained dependency hashes are
unchanged. ENDGAME targets are preserved in the existing installation job's
`rollback/original` directory, with independently hash-verified archives retained.
No kext, collection, EFI, OpenCore, firmware, security or display setting changed.

| Original component | SHA256 | UUID |
|---|---|---|
|NVMTL|853cc88e3e414815384d7d60bc01dd4d5cb67708c20d10472f59506a60a9c5cb|E672B810-6E4F-352B-81C7-61B8A7A89ED0|
|Translator|0ad9ab8b8fa1c28519a033c1e7e5367692463de5c81b8651c78ea8d382b3fd57|9C9EF855-568D-3F52-A930-0C9480D4844E|
|NVK|372c257b551cc0c4591239003151f6ac3cb80a947765b5639acfdb5a80e74ebc|132E6A91-D8E4-3487-A980-54455B5B700D|

A fresh-process ordinary Metal probe maps all three original UUIDs and passes
17/34/51/68 GPU values. This verifies restored application behavior before reboot;
WindowServer still needs independent post-reboot mapped-image inspection.
The checkpoint is published before issuing the one authorized reboot.
Post-reboot desktop validation and original-driver measurements remain pending.

## Exact continuation

First verify sudo-n UID0, fresh active-metal-images original UUIDs/GPU oracle,
WindowServer lsof current inodes plus independent sample mapped UUIDs, unchanged
four kernel UUIDs and all34 dependency entries against the retained private
precheck. Stop if any expected image, binary or retained component differs.
Do not execute rollback again or issue another reboot.

Private output root:
`/Users/waqy/Developer/ga102-sequoia-comparison-20261013/controlled-ab`.
Use the existing hashed `sustained-probe` (296dbee8c63b5573a6abb6916baf27c0a68caca6700fdcb27b6a3afc85960e15),
with `--render-size 1920x1080 --composite-layers 8` exactly once initially.
Preserve stdout and stderr separately to avoid known interleaving; do not change
workload or infer qualification from exit0. Compare the retained ENDGAME failure
against this original control descriptively, including incomplete runs.

Run existing Safari/Firefox WebGL and CSS controls, retaining failures, renderer
and GPU process mapping evidence. Use the previously compiled warm-activation
observer; it measures frontmost observation, not first pixels, startup or usability.
Cold launches/actual boot durations require separately qualified observations;
do not invent them from tool reconnect time or login interaction.
Capture bounded background-load observations before/after benchmarks without
compiling, profiling or concurrently stressing the measured run. Keep raw process
inventory/private paths outside Git. Publish normalized evidence and conclusions.
Only original control is authorized; official1.15 requires separate full recovery
and approval. Preserve the unrelated dirty Swift experiments.
