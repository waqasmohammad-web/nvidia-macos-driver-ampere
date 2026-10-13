# Controlled original-driver comparison: stopped before rollback

13 October 2026. Owner approved only the original two-target userland rollback
and one reboot, conditional on the matched candidate block and rollback verification.
The first candidate sustained block failed. No driver change or reboot occurred;
ENDGAME remains installed. No original or official control was executed.

The frozen 3,600-frame/64-second workload submitted 3,408 commands and observed
3,407 completions, one outstanding command, zero command errors and zero timer
skips at the deadline. There were 3,402 positive presentation timestamps and 58
eligible visibility samples. This is an incomplete failed run, not a qualified
3,600-frame result and not a proven GPU hang.

| Available observations | p50 ms | p95 ms | p99 ms | Maximum ms |
|---|---:|---:|---:|---:|
| Presentation,3,391 steady intervals |16.761352|33.457266|49.995253|84.019784|
| GPU,3,407 completed commands |0.319488|0.363456|0.378880|0.407552|
| Commit to completion callback |0.656646|0.743476|0.795219|2.839530|
| CPU draw interval |16.684780|33.420434|50.013966|100.840716|

398 steady presentation intervals exceed25ms (11.74%). Client draw cadence also
slows; no causal driver attribution follows from this unmatched run. The incomplete
per-frame trace is NOT VERIFIED. No failed run was rerun selectively.

The full combined stdout/stderr log is retained privately. One stderr failure
message interrupted the JSON string. The original log was not edited: a derived
JSON removes exactly that known failure message and requires one complete object
with a whitespace-only remainder. Both hashes, source/executable hashes and numeric
summary are published in evidence/ga102-controlled-ab-candidate-failure.json.
Raw log SHA256:9cf2b80c2459e109d0f3d2bcd00626dfe0d8f889b1d2e26d8679270491092579.
The collection/JSON parse failure is not erased by this derivation.

Safari and Firefox were already running. A private warm-activation observer was
compiled before measurement, but was not executed after the sustained failure.
No user application was quit; no cold-launch duration is claimed. Independent
Recovery USB is mounted; prior backup checks remain retained, but this session did
not proceed to the immediate pre-rollback gates or the privileged rollback command.
The owner-authorized reboot has not been consumed.

NEXT-STEPS: stop for owner review of this failed qualification boundary. Read this
checkpoint and the retained log before any continuation. Do not treat submission
success, a partial timing distribution or previous backup verification as permission
to bypass the conditional measurement/rollback gates. No1.15 installation or further
reboot is authorized. Preserve the two unrelated dirty Swift experiments.
