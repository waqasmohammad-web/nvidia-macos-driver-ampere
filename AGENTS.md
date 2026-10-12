# GA102 development continuation

Read `docs/GA102-CLOUD-HANDOVER.md` first. Continue the existing investigation;
use the end of `docs/GA102-INVESTIGATION.md` for the latest checkpoints.

Cloud default: portable source work, standard-library Python tests, and native
Rust translator tests with real SPIRV-Tools. Use one build job and one test thread.
Do not launch the full LLVM/Mesa build or wrapper's source-built SPIRV-Tools by
default. Report unavailable dependencies and resource limits honestly; never use
stub validators, invented fixtures, or blanket test exclusions to manufacture a pass.

Never change installed drivers, kernel collections, EFI/OpenCore, SIP/security,
or display configuration. No reboot, logout, WindowServer restart, deliberate
sleep/wake, or live kext replacement. PM candidates await supervised validation.
Do not interrupt existing builds. No remote access to the physical host is needed
for cloud tasks. Keep credentials, private logs, machine data and binaries outside Git.

Preserve unrelated local edits. Commit meaningful validated source changes;
use the requested branch `dev/ga102-3080ti-diagnostics` when supported, or return a
reviewable cloud diff/PR for integration without force-pushing. Include
`Generated-by: LLM` for Mesa-derived source changes. Keep a concise NEXT-STEPS
checkpoint with the exact next command and honest validation limitations.
